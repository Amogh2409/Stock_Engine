/**
 * Notebook integrity.
 *
 * The Python lives in python/engine.py and is embedded into
 * src/utils/pythonEngineSource.ts by scripts/build_python_source.mjs. These
 * tests fail closed if any link in that chain drifts, if the emitted Python
 * does not compile, or if the notebook regains an import-time side effect.
 */
import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import path from 'node:path';

import { describe, expect, it } from 'vitest';

import {
  buildColabNotebookJson,
  extractScriptSections,
  notebookCodeCells,
  NOTEBOOK_FILENAME,
  PYTHON_ENGINE_SOURCE,
  serializeNotebook,
} from '../utils/colabNotebookGenerator';
import { PARITY_PYTHON } from './helpers/pythonBridge';

const ROOT = path.resolve(__dirname, '..', '..');
const BACKSPACE = '\u0008';

describe('Notebook generation', () => {
  it('produces a well-formed notebook with exactly one code cell', () => {
    const nb = buildColabNotebookJson();
    expect(nb.nbformat).toBe(4);
    expect(nb.cells.filter((c) => c.cell_type === 'code')).toHaveLength(1);
    expect(nb.cells.filter((c) => c.cell_type === 'markdown')).toHaveLength(1);
    expect(notebookCodeCells(nb).length).toBeGreaterThan(1000);
  });

  it('matches the shipped notebook byte for byte', () => {
    const onDisk = readFileSync(path.join(ROOT, NOTEBOOK_FILENAME), 'utf8');
    expect(serializeNotebook()).toBe(onDisk);
  });

  it('embeds exactly the current python/engine.py', () => {
    const engineSource = readFileSync(path.join(ROOT, 'python', 'engine.py'), 'utf8');
    expect(PYTHON_ENGINE_SOURCE).toBe(engineSource);
  });

  it('is in sync according to the codegen check', () => {
    // Fails loudly if engine.py or pythonEngineSource.ts was hand-edited.
    execFileSync('node', [path.join(ROOT, 'scripts', 'build_python_source.mjs'), '--check'], {
      cwd: ROOT,
      stdio: 'pipe',
    });
  });
});

describe('Emitted Python', () => {
  it('compiles', () => {
    execFileSync(
      PARITY_PYTHON,
      ['-c', 'import sys;compile(sys.stdin.read(), "notebook", "exec")'],
      { input: notebookCodeCells(), stdio: 'pipe' },
    );
  });

  it('keeps regex escapes intact', () => {
    // The old generator held this Python in a JS template literal, which
    // silently ate \w, \s and \b. JSON.stringify codegen cannot, but assert it.
    expect(PYTHON_ENGINE_SOURCE).toContain(
      String.raw`_NUMERIC_BODY_RE = re.compile(r"^[+-]?(?:[0-9]+\.?[0-9]*|\.[0-9]+)(?:[eE][+-]?[0-9]+)?$")`,
    );
    expect(PYTHON_ENGINE_SOURCE).toContain(String.raw`"\t\n\x0b\x0c\r \N{NO-BREAK SPACE}\N{OGHAM SPACE MARK}"`);
    expect(PYTHON_ENGINE_SOURCE).toContain(String.raw`r"\b" + re.escape(alias_norm) + r"\b"`);
    // A literal backspace would mean a `\b` was eaten.
    expect(PYTHON_ENGINE_SOURCE).not.toContain(BACKSPACE);
  });

  it('defines every symbol the parity driver requires', () => {
    for (const symbol of [
      'def clamp(', 'def round1(', 'def parse_strict_decimal(', 'def clean_numeric(',
      'def escape_csv_cell(', 'def resolve_columns(', 'def dedupe_stocks(',
      'def compute_technical_indicators(', 'def calculate_technical_score(',
      'def compute_ranking_changes(', 'def ranking_changes_to_csv(',
      'def watchlist_to_csv(', 'def rejected_to_csv(', 'def build_explanation(',
      'class ScreeningEngine', 'class UniverseProvider', 'class FundamentalsAdapter',
      'class MarketDataProvider', 'class EngineTests',
    ]) {
      expect(PYTHON_ENGINE_SOURCE, symbol).toContain(symbol);
    }
  });

  it('guards execution behind a __main__ block so it is importable', () => {
    expect(PYTHON_ENGINE_SOURCE).toContain('def main(argv=None):');
    expect(PYTHON_ENGINE_SOURCE).toContain('if __name__ == "__main__":');
    expect(PYTHON_ENGINE_SOURCE).toContain('sys.exit(main())');
    // Inside Colab/Jupyter the kernel owns argv and sys.exit() prints an
    // exception banner, so a notebook cell calls main([]) without exiting,
    // while `%run engine.py --offline` (which sets __file__) keeps its flags.
    expect(PYTHON_ENGINE_SOURCE).toContain(
      '_exit_code = main(sys.argv[1:] if "__file__" in globals() else [])',
    );
    // setup_storage_paths and run_pipeline must be called only from main().
    const topLevelCalls = PYTHON_ENGINE_SOURCE.split('\n').filter((line) =>
      /^(setup_storage_paths\(|run_pipeline\(|PATHS\s*=)/.test(line),
    );
    expect(topLevelCalls, `unexpected import-time execution: ${topLevelCalls.join(' | ')}`).toEqual([]);
  });

  it('advertises no XLSX support anywhere', () => {
    expect(PYTHON_ENGINE_SOURCE).not.toContain('read_excel');
    expect(PYTHON_ENGINE_SOURCE).not.toContain('openpyxl');
    expect(PYTHON_ENGINE_SOURCE).toContain('SUPPORTED_SUFFIXES = (".csv",)');
  });

  it('marks the network test class optional', () => {
    expect(PYTHON_ENGINE_SOURCE).toContain('class NetworkIntegrationTests');
    expect(PYTHON_ENGINE_SOURCE).toContain('RUN_NETWORK_TESTS');
  });
});

describe('Colab viewer sections', () => {
  it('extracts real sections from the shipped source', () => {
    const sections = extractScriptSections();
    expect(sections.length).toBeGreaterThanOrEqual(8);
    for (const section of sections) {
      expect(section.code.length, section.id).toBeGreaterThan(0);
      // Every displayed line must exist verbatim in the shipped Python.
      expect(PYTHON_ENGINE_SOURCE, section.id).toContain(section.code);
    }
  });

  it('exposes the sections the UI advertises', () => {
    const ids = extractScriptSections().map((s) => s.id);
    for (const id of [
      'imports', 'universe_snapshot', 'helpers', 'csv_safety', 'column_resolution',
      'config', 'universe', 'fundamentals', 'technicals', 'engine', 'deltas',
      'storage', 'tests', 'pipeline',
    ]) {
      expect(ids, id).toContain(id);
    }
  });

  it('contains no hand-written snippet that is absent from the engine', () => {
    // A stale hand-copied example used to document compute_run_deltas(), a
    // function that never existed. Section codes are slices of the real source,
    // so this can only pass if every displayed symbol is genuine.
    expect(PYTHON_ENGINE_SOURCE).not.toContain('compute_run_deltas');
  });
});
