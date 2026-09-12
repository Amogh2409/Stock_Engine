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
 * Interpreter used for parity. run_checks.sh sets PARITY_PYTHON to the
 * interpreter inside its pinned virtualenv; falling back to python3 keeps
 * `npm test` usable locally. A missing interpreter is a hard failure.
 */
export const PARITY_PYTHON = process.env.PARITY_PYTHON || 'python3';

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
        `cannot be verified. Set PARITY_PYTHON to a valid interpreter. Cause: ${
          error instanceof Error ? error.message : String(error)
        }`,
    );
  }
  try {
    execFileSync(PARITY_PYTHON, ['-c', 'import pandas, numpy'], { stdio: 'pipe' });
  } catch (error) {
    throw new Error(
      `Required Python dependencies (pandas, numpy) are missing from "${PARITY_PYTHON}" ` +
        `(${version}). Install requirements-test.txt. Cause: ${
          error instanceof Error ? error.message : String(error)
        }`,
    );
  }
}

const DRIVER = path.resolve(__dirname, '..', 'fixtures', 'parity_driver.py');

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
  const file = path.resolve(__dirname, '..', '..', 'data', 'sampleScreenerData.ts');
  const text = readFileSync(file, 'utf8');
  const match = /`([\s\S]*?)`/.exec(text);
  if (!match) throw new Error('Could not extract the sample CSV literal from sampleScreenerData.ts');
  return match[1];
}
