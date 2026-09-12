/**
 * Builds the downloadable Colab notebook.
 *
 * The Python payload is NOT written here. It lives in python/engine.py and is
 * embedded into src/utils/pythonEngineSource.ts by scripts/build_python_source.mjs.
 * Everything the UI displays is extracted from that same string, so the
 * notebook you download, the notebook on disk and the code shown in the
 * "Google Colab Script" tab cannot drift apart. src/tests/notebook.test.ts
 * enforces that.
 */
import { NIFTY100_PROVENANCE } from '../data/nifty100Snapshot';
import { PYTHON_ENGINE_SOURCE } from './pythonEngineSource';

export { PYTHON_ENGINE_SOURCE };
/** Back-compatible alias. */
export const PYTHON_COLAB_FULL_SCRIPT = PYTHON_ENGINE_SOURCE;

export interface ScriptSection {
  id: string;
  title: string;
  code: string;
  lineCount: number;
}

const SECTION_START = /^# === SECTION:([a-z0-9_]+):(.+) ===$/;
const SECTION_END = /^# === END SECTION:([a-z0-9_]+) ===$/;

/**
 * Extract the marked sections of the real Python source.
 *
 * Sections are delimited in python/engine.py by
 *   # === SECTION:<id>:<Title> ===  ...  # === END SECTION:<id> ===
 * so the viewer shows genuine, currently-shipped code rather than a
 * hand-maintained copy.
 */
export function extractScriptSections(source: string = PYTHON_ENGINE_SOURCE): ScriptSection[] {
  const sections: ScriptSection[] = [];
  const lines = source.split('\n');
  let current: { id: string; title: string; body: string[] } | null = null;

  for (const line of lines) {
    const start = SECTION_START.exec(line);
    if (start) {
      current = { id: start[1], title: start[2].trim(), body: [] };
      continue;
    }
    const end = SECTION_END.exec(line);
    if (end && current && end[1] === current.id) {
      const code = current.body.join('\n').replace(/^\n+|\n+$/g, '');
      sections.push({
        id: current.id,
        title: current.title,
        code,
        lineCount: code === '' ? 0 : code.split('\n').length,
      });
      current = null;
      continue;
    }
    if (current) current.body.push(line);
  }
  return sections;
}

export const NOTEBOOK_FILENAME = 'Indian_Equity_Quantitative_Engine.ipynb';

const INTRO_MARKDOWN = [
  '# Indian Equity Quantitative Screening Engine\n',
  '\n',
  'End-to-end, rule-based screening for Indian equities. Fundamentals come from\n',
  'a **Screener.in CSV export** (CSV only -- XLSX is not supported). Optional\n',
  'daily price history is fetched with `yfinance` for technical confirmation.\n',
  '\n',
  '## How to run\n',
  '1. Run the cell below. It mounts Google Drive and creates the `IndianStockEngine/` folders there.\n',
  '2. Place your Screener.in **CSV** export in `IndianStockEngine/fundamentals/`.\n',
  '3. Optional: put a `config.json` exported from the web app (*Universe & config* tab) in\n',
  '   `IndianStockEngine/config/` to screen with those settings instead of the defaults.\n',
  '4. Re-run the cell. It downloads 18 months of daily prices for the screened tickers\n',
  '   (cached in `market_data/`), then writes the watchlist, rejected audit and\n',
  '   ranking-changes CSVs to `reports/`.\n',
  '\n',
  '## Notes\n',
  '- The price file saved in `market_data/` (Date, Ticker, Close, Volume) can be uploaded\n',
  '  into the web app with *Upload prices* to reproduce the same technical scores there.\n',
  `- The bundled Nifty 100 list is a **cached snapshot as of ${NIFTY100_PROVENANCE.as_of_date}**\n`,
  '  (SHA-256 recorded in `NIFTY100_PROVENANCE`). It is refreshed from NSE at runtime\n',
  '  when the network is available; otherwise it is clearly reported as cached.\n',
  '- Importing this code does not mount Drive, hit the network, or run the pipeline.\n',
  '  Execution happens only through `main()` under the `__main__` guard.\n',
  '- Offline self-tests run before every screening pass and abort the run on failure.\n',
  '- Financial-sector companies (banks, NBFCs, insurers) are explicitly out of scope.\n',
];

export interface NotebookJson {
  nbformat: number;
  nbformat_minor: number;
  metadata: Record<string, unknown>;
  cells: Record<string, unknown>[];
}

export function buildColabNotebookJson(): NotebookJson {
  return {
    nbformat: 4,
    nbformat_minor: 0,
    metadata: {
      colab: { name: NOTEBOOK_FILENAME, provenance: [] },
      kernelspec: { name: 'python3', display_name: 'Python 3' },
      language_info: { name: 'python' },
    },
    cells: [
      { cell_type: 'markdown', metadata: {}, source: INTRO_MARKDOWN },
      {
        cell_type: 'code',
        execution_count: null,
        metadata: {},
        outputs: [],
        source: [PYTHON_ENGINE_SOURCE],
      },
    ],
  };
}

/** Canonical on-disk serialisation. The byte-comparison check depends on this. */
export function serializeNotebook(): string {
  return `${JSON.stringify(buildColabNotebookJson(), null, 2)}\n`;
}

/** Concatenated Python from every code cell, as Python will see it. */
export function notebookCodeCells(nb: NotebookJson = buildColabNotebookJson()): string {
  return nb.cells
    .filter((c) => c.cell_type === 'code')
    .map((c) => (Array.isArray(c.source) ? (c.source as string[]).join('') : String(c.source)))
    .join('\n');
}
