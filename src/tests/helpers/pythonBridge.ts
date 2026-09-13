/**
 * Bridge to the Python engine for cross-engine parity tests.
 *
 * FAIL-CLOSED CONTRACT. Every failure mode below throws, which fails the
 * calling test. Nothing here returns a placeholder, a stub, a skip or a
 * hard-coded expected result:
 *   - the notebook cannot be generated or has no code cells
 *   - python3 is not runnable
 *   - pandas/numpy are missing
 *   - the subprocess exits non-zero
 *   - stdout is not valid JSON
 *   - the payload is missing required keys
 *   - the engine reports zero rows
 */
import { execFileSync } from 'node:child_process';
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';

import type { TechnicalBlocks } from '../../types';
import {
  buildColabNotebookJson,
  notebookCodeCells,
} from '../../utils/colabNotebookGenerator';

/**
 * Interpreter used for parity, resolved exactly as scripts/venv-python.sh
 * resolves it: PARITY_PYTHON if set, else the project's own virtualenv.
 *
 * It used to fall back to a bare `python3`, which meant one missing virtualenv
 * produced two very different failures. `npm run screen` goes through
 * venv-python.sh and gets a sentence telling you what to create; `npm test`
 * bypassed that script entirely and died with ModuleNotFoundError: pandas from
 * whichever python3 happened to be on PATH. Same cause, and only one of them
 * told you the cause. Both entry points now default to the same interpreter and
 * fail with the same instructions.
 */
// Resolved from the working directory rather than from __dirname, which is
// undefined in ES module scope: Vitest transpiles this to CJS so __dirname
// happens to work there, and tsc never evaluates it, so both pass while a
// plain ESM import of this module throws at load. Every npm script in this
// repo runs from the repo root, and run_checks.sh sets PARITY_PYTHON
// explicitly, so cwd is the dependable anchor.
const VENV_PYTHON = path.resolve(process.cwd(), '.venv', 'bin', 'python');
export const PARITY_PYTHON = process.env.PARITY_PYTHON || VENV_PYTHON;

/** The instructions scripts/venv-python.sh prints, so both routes say one thing. */
const VENV_INSTRUCTIONS =
  `This needs the project's virtualenv, which is missing or incomplete:\n  ${PARITY_PYTHON}\n\n` +
  'Create it once with:\n' +
  '  python3 -m venv .venv\n' +
  '  .venv/bin/pip install -r requirements-test.txt     # offline runs and tests\n' +
  '  .venv/bin/pip install -r requirements-network.txt  # adds live prices and the NSE refresh\n\n' +
  'Or point PARITY_PYTHON at an interpreter that has pandas and numpy.';

export interface UnitCase {
  label: string;
  value: string;
  unit: 'crore' | 'percent' | 'ratio' | 'price' | 'plain';
}

export interface MappingCase {
  label: string;
  headers: string[];
}

/** An extra screen run by both engines: same rows, config and price history. */
export interface ScreenSpec {
  label: string;
  csv: string;
  app_config: Record<string, unknown>;
  screening_config: Record<string, unknown>;
  price_csv?: string;
}

export interface ParityJob {
  csv: string;
  app_config: Record<string, unknown>;
  screening_config: Record<string, unknown>;
  delta_fixture: {
    current: Record<string, unknown>[];
    previous: Record<string, unknown>[] | null;
  };
  expected_rows?: number;
  unit_cases?: UnitCase[];
  escape_cases?: string[];
  technical_sizes?: number[];
  mapping_cases?: MappingCase[];
  screens?: ScreenSpec[];
  number_cases?: number[];
  strict_decimal_cases?: string[];
  whitespace_cases?: string[];
  header_cases?: string[];
  config_cases?: unknown[];
  price_parse_cases?: string[];
}

export interface ParityEvaluation {
  ticker: string;
  passed: boolean;
  score: number;
  composite: number;
  compositeBasis: string;
  verdict: string;
  coverage: number;
  reasons: string[];
  warningFlags: string[];
  categoryScores: Record<string, number>;
  redFlags: string[];
  notScored: string | null;
  scoringModel: string;
  scoreLines: string[];
  sectorGroup: string | null;
  sectorRelativeStrength6M: number | null;
  sectorRelativeStrengthBasis: string;
  // Position sizing, attached after the top_n cut. Compared because a weight
  // computed differently in the two engines would otherwise stay invisible
  // until it reached someone's money, and because the engines reach these
  // fields by different routes: Python mutates the evaluation dicts, which are
  // aliased into its watchlist, while TypeScript rebuilds them from a Map. That
  // makes "both produce the same numbers" a real assertion rather than a
  // restatement of one implementation.
  positionWeightPct: number | null;
  stopPrice: number | null;
  stopDistancePct: number | null;
  sizingBasis: string;
  techScore: number | null;
  techBreakdown: string[];
  technicalBlocks: TechnicalBlocks | null;
  dataStatus: string;
  explanation: string;
}

export interface ParityScreen {
  mapping: Record<string, string>;
  duplicates_removed: number;
  outside_universe: number;
  price_rows_skipped: number | null;
  evaluations: ParityEvaluation[];
  watchlist: { ticker: string; rank: number; score: number }[];
  passed_below_cutoff: { ticker: string; rank: number; score: number }[];
  fundamental_only: { ticker: string; rank: number; score: number }[];
  watchlist_csv: string;
  passed_below_csv: string;
  rejected_csv: string;
  technicals: Record<string, Record<string, unknown>> | null;
  /**
   * The run-level sizing summary. Worth comparing separately from the
   * per-company weights: the deployment fraction is one number derived from a
   * long sequential sum over the portfolio's return series, which is exactly
   * the shape of calculation where two engines drift in the last bits without
   * any individual weight looking wrong.
   */
  sizing: {
    measure: string | null;
    targetVolatilityPct: number;
    portfolioVolatilityPct: number | null;
    deploymentPct: number | null;
    investedPct: number | null;
    basis: string;
  };
}

export interface ParityPayload {
  engine: 'python';
  mapping: Record<string, string>;
  duplicates_removed: number;
  evaluations: ParityEvaluation[];
  watchlist: { ticker: string; rank: number; score: number }[];
  watchlist_csv: string;
  rejected_csv: string;
  ranking_changes_csv: string;
  /** The primary screen's sizing summary, same shape as ParityScreen['sizing']. */
  sizing: ParityScreen['sizing'];
  screens: Record<string, ParityScreen>;
  universe: {
    count: number;
    symbols: string[];
    provenance: Record<string, string | number>;
  };
  unit_parsing: Record<string, number | null>;
  csv_escapes: Record<string, string>;
  technical_availability: Record<string, boolean>;
  identifier_mappings: Record<string, Record<string, string>>;
  number_text: string[];
  strict_decimals: (number | null)[];
  whitespace_numbers: (number | null)[];
  trimmed: string[];
  headers: string[];
  config_limits: Record<string, [number, number]>;
  config_results: {
    valid: boolean;
    errors: string[];
    app: Record<string, unknown>;
    screening: Record<string, unknown>;
  }[];
  price_parse_results: ({ error: true } | { error: false; history: Record<string, unknown>; skipped: number })[];
}

/**
 * Write the Python from the generated notebook to a temp module.
 * Throws if the notebook cannot be produced or carries no code.
 */
export function materializeNotebookEngine(): { dir: string; modulePath: string; code: string } {
  const notebook = buildColabNotebookJson();
  if (!notebook || !Array.isArray(notebook.cells) || notebook.cells.length === 0) {
    throw new Error('Notebook could not be generated: no cells were produced.');
  }
  const code = notebookCodeCells(notebook);
  if (!code || code.trim() === '') {
    throw new Error('Notebook contains no executable Python; refusing to continue.');
  }
  const dir = mkdtempSync(path.join(tmpdir(), 'screener-parity-'));
  const modulePath = path.join(dir, 'notebook_engine.py');
  writeFileSync(modulePath, code, 'utf8');
  return { dir, modulePath, code };
}

/** Remove a directory materializeNotebookEngine() created. */
export function removeNotebookEngine(dir: string): void {
  rmSync(dir, { recursive: true, force: true });
}

/** Assert the interpreter exists and has the dependencies the engine needs. */
export function assertPythonEnvironment(): void {
  let version: string;
  try {
    version = execFileSync(PARITY_PYTHON, ['--version'], { encoding: 'utf8' }).trim();
  } catch (error) {
    throw new Error(
      `Python interpreter "${PARITY_PYTHON}" is not runnable, so cross-engine parity ` +
        `cannot be verified.\n\n${VENV_INSTRUCTIONS}\n\nCause: ${
          error instanceof Error ? error.message : String(error)
        }`,
    );
  }
  try {
    execFileSync(PARITY_PYTHON, ['-c', 'import pandas, numpy'], { stdio: 'pipe' });
  } catch (error) {
    throw new Error(
      `Required Python dependencies (pandas, numpy) are missing from "${PARITY_PYTHON}" ` +
        `(${version}), so cross-engine parity cannot be verified.\n\n${VENV_INSTRUCTIONS}\n\nCause: ${
          error instanceof Error ? error.message : String(error)
        }`,
    );
  }
}

// Same reasoning as VENV_PYTHON above: __dirname is undefined in ES module
// scope, and only Vitest's CJS transpilation hides that. Resolved from the
// repo root, which is where every entry point runs from.
const DRIVER = path.resolve(process.cwd(), 'src', 'tests', 'fixtures', 'parity_driver.py');

/** Run the driver against the notebook engine and validate the payload strictly. */
export function runPythonParity(job: ParityJob): ParityPayload {
  assertPythonEnvironment();
  const { dir, modulePath } = materializeNotebookEngine();

  let stdout: string;
  try {
    stdout = execFileSync(PARITY_PYTHON, [DRIVER, modulePath], {
      input: JSON.stringify(job),
      encoding: 'utf8',
      maxBuffer: 64 * 1024 * 1024,
      stdio: ['pipe', 'pipe', 'pipe'],
    });
  } catch (error) {
    const err = error as { status?: number; stderr?: Buffer | string; stdout?: Buffer | string };
    const stderr = err.stderr ? String(err.stderr) : '';
    const out = err.stdout ? String(err.stdout) : '';
    throw new Error(
      `Python parity driver exited with status ${err.status ?? 'unknown'}.\n` +
        `--- stderr ---\n${stderr}\n--- stdout ---\n${out}`,
    );
  } finally {
    // One temp directory per parity run used to be left behind; dozens piled
    // up in $TMPDIR.
    removeNotebookEngine(dir);
  }

  let payload: ParityPayload;
  try {
    payload = JSON.parse(stdout) as ParityPayload;
  } catch (error) {
    throw new Error(
      `Python parity driver produced invalid JSON: ${
        error instanceof Error ? error.message : String(error)
      }\n--- stdout ---\n${stdout.slice(0, 2000)}`,
    );
  }

  const required: (keyof ParityPayload)[] = [
    'engine', 'mapping', 'evaluations', 'watchlist', 'watchlist_csv',
    'rejected_csv', 'ranking_changes_csv', 'universe', 'screens', 'number_text',
    'strict_decimals', 'whitespace_numbers', 'trimmed', 'headers', 'config_limits',
    'config_results', 'price_parse_results',
  ];
  const missing = required.filter((key) => payload[key] === undefined);
  if (missing.length) {
    throw new Error(`Python payload is incomplete; missing: ${missing.join(', ')}`);
  }
  if (payload.engine !== 'python') {
    throw new Error(`Unexpected engine tag in payload: ${String(payload.engine)}`);
  }
  if (!Array.isArray(payload.evaluations) || payload.evaluations.length === 0) {
    throw new Error('Python payload contains zero evaluations.');
  }
  for (const [index, item] of payload.evaluations.entries()) {
    for (const key of ['ticker', 'passed', 'score', 'coverage', 'reasons', 'warningFlags'] as const) {
      if (item[key] === undefined || item[key] === null) {
        throw new Error(`Python evaluation ${index} is missing "${key}".`);
      }
    }
  }
  return payload;
}

/** Read the sample CSV without importing the TS module (keeps the fixture honest). */
export function readSampleCsvFromSource(): string {
  // Same reasoning as VENV_PYTHON and DRIVER above. This one survived the
  // first pass at the __dirname conversion because it sits inside a function
  // rather than at module scope, so an ESM import of the module does not throw
  // on it -- it would only fail when called, and it is only ever called from
  // Vitest, where the CJS transpilation makes __dirname work anyway.
  const file = path.resolve(process.cwd(), 'src', 'data', 'sampleScreenerData.ts');
  const text = readFileSync(file, 'utf8');
  const match = /`([\s\S]*?)`/.exec(text);
  if (!match) throw new Error('Could not extract the sample CSV literal from sampleScreenerData.ts');
  return match[1];
}
