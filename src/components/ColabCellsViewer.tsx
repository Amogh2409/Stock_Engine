import { Check, Code2, Copy, Download, FileCode, Play } from 'lucide-react';
import React, { useMemo, useState } from 'react';

import { NIFTY100_PROVENANCE } from '../data/nifty100Snapshot';
import {
  extractScriptSections,
  NOTEBOOK_FILENAME,
  PYTHON_ENGINE_SOURCE,
  ScriptSection,
  serializeNotebook,
} from '../utils/colabNotebookGenerator';
import { downloadText } from '../utils/download';

const FULL_SECTION_ID = '__full__';

/**
 * Displays the notebook's Python.
 *
 * Every snippet shown here is sliced out of PYTHON_ENGINE_SOURCE at render
 * time, which is the same string that generates the downloadable notebook.
 * There are no hand-maintained copies, so what you read is what ships.
 */
export const ColabCellsViewer: React.FC = () => {
  const sections = useMemo<ScriptSection[]>(() => extractScriptSections(), []);
  const [selectedId, setSelectedId] = useState<string>(FULL_SECTION_ID);
  const [copied, setCopied] = useState(false);
  const [copyError, setCopyError] = useState<string | null>(null);

  const fullLineCount = PYTHON_ENGINE_SOURCE.split('\n').length;

  const active: ScriptSection =
    selectedId === FULL_SECTION_ID
      ? {
          id: FULL_SECTION_ID,
          title: 'Complete engine (single execution cell)',
          code: PYTHON_ENGINE_SOURCE,
          lineCount: fullLineCount,
        }
      : sections.find((s) => s.id === selectedId) ?? {
          id: FULL_SECTION_ID,
          title: 'Complete engine (single execution cell)',
          code: PYTHON_ENGINE_SOURCE,
          lineCount: fullLineCount,
        };

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(active.code);
      setCopied(true);
      setCopyError(null);
      window.setTimeout(() => setCopied(false), 2000);
    } catch (error) {
      // Clipboard access fails on insecure origins and in some browsers.
      // Say so rather than showing a false "Copied!".
      setCopied(false);
      setCopyError(
        `Clipboard unavailable (${error instanceof Error ? error.message : String(error)}). Select the code and copy manually.`,
      );
    }
  };

  const handleDownloadNotebook = () =>
    downloadText(serializeNotebook(), NOTEBOOK_FILENAME, 'application/json');

  return (
    <div className="space-y-6" id="colab-cells-container">
      <div className="bg-white border border-slate-200 rounded-xl p-5 flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="p-1.5 bg-amber-50 text-amber-600 rounded-lg border border-amber-200">
              <Play className="w-4 h-4" />
            </span>
            <h3 className="text-sm font-semibold">Google Colab engine</h3>
          </div>
          <p className="text-xs text-slate-500 mt-1 max-w-2xl leading-relaxed">
            One executable cell. It mounts Drive, reads a Screener.in <strong>CSV</strong> export and
            an optional <code>config.json</code>, downloads daily price history for technical
            confirmation, screens and scores, then writes the watchlist, rejected audit and
            ranking-changes CSVs.
            Importing the code runs nothing — execution happens only via <code>main()</code> under
            the <code>__main__</code> guard, which is what lets the offline tests import it.
          </p>
          <p className="text-[11px] text-slate-400 mt-1 font-mono">
            {fullLineCount} lines · universe snapshot cached as of {NIFTY100_PROVENANCE.as_of_date} ·
            sections extracted live from the shipped source
          </p>
        </div>
        <button
          onClick={handleDownloadNotebook}
          className="inline-flex items-center gap-1.5 px-3 py-2 bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold rounded-lg flex-shrink-0"
        >
          <Download className="w-3.5 h-3.5" />
          Download .ipynb
        </button>
      </div>

      <div className="flex flex-wrap gap-2">
        <button
          onClick={() => setSelectedId(FULL_SECTION_ID)}
          className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold border transition-colors ${
            selectedId === FULL_SECTION_ID
              ? 'bg-blue-600 text-white border-blue-600'
              : 'bg-white text-slate-700 border-slate-200 hover:bg-slate-50'
          }`}
        >
          <FileCode className="w-3.5 h-3.5" />
          Full script
        </button>
        {sections.map((section) => (
          <button
            key={section.id}
            onClick={() => setSelectedId(section.id)}
            className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold border transition-colors ${
              selectedId === section.id
                ? 'bg-blue-600 text-white border-blue-600'
                : 'bg-white text-slate-700 border-slate-200 hover:bg-slate-50'
            }`}
            title={`${section.lineCount} lines`}
          >
            <Code2 className="w-3.5 h-3.5" />
            {section.title}
          </button>
        ))}
      </div>

      <div className="bg-slate-900 rounded-xl overflow-hidden border border-slate-800">
        <div className="px-4 py-2.5 bg-slate-800/80 flex items-center justify-between">
          <span className="text-xs font-mono text-slate-300">
            {active.title} · {active.lineCount} lines
          </span>
          <button
            onClick={handleCopy}
            className="inline-flex items-center gap-1.5 px-2.5 py-1 bg-slate-700 hover:bg-slate-600 text-slate-100 text-[11px] font-semibold rounded"
          >
            {copied ? <Check className="w-3 h-3" /> : <Copy className="w-3 h-3" />}
            {copied ? 'Copied' : 'Copy'}
          </button>
        </div>
        {copyError && (
          <p role="alert" className="px-4 py-2 text-[11px] text-amber-200 bg-amber-900/40">
            {copyError}
          </p>
        )}
        <pre className="p-4 overflow-x-auto text-[11px] leading-relaxed text-slate-100 max-h-[32rem]">
          <code>{active.code}</code>
        </pre>
      </div>
    </div>
  );
};
