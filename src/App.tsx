import {
  AlertTriangle,
  BarChart3,
  Calendar,
  Code2,
  Database,
  Download,
  FileText,
  FileUp,
  GitCompare,
  Globe,
  LineChart,
  RefreshCw,
  Save,
  ShieldCheck,
  Sparkles,
  XCircle,
} from 'lucide-react';
import React, { useCallback, useEffect, useMemo, useState } from 'react';

import { ColabCellsViewer } from './components/ColabCellsViewer';
import { ConfigPanel } from './components/ConfigPanel';
import { DataInspectionView } from './components/DataInspectionView';
import { RankingChangesView } from './components/RankingChangesView';
import { RejectedTable } from './components/RejectedTable';
import { TestsRunner } from './components/TestsRunner';
import { Visualizations } from './components/Visualizations';
import { WatchlistTable } from './components/WatchlistTable';
import { NIFTY100_PROVENANCE } from './data/nifty100Snapshot';
import { SAMPLE_SCREENER_CSV_STRING } from './data/sampleScreenerData';
import { AppConfig, ScreeningConfig, WatchlistSnapshotEntry } from './types';
import { NOTEBOOK_FILENAME, serializeNotebook } from './utils/colabNotebookGenerator';
import { downloadText, todayStamp } from './utils/download';
import {
  BENCHMARK_SYMBOL,
  computeRankingChanges,
  DEFAULT_APP_CONFIG,
  DEFAULT_SCREENING_CONFIG,
  describePriceHistory,
  generateHtmlReport,
  parseCsv,
  parsePriceHistoryCsv,
  parseSavedRun,
  PriceHistory,
  processScreenerPipeline,
  SavedRun,
  SAVED_RUN_KEY,
  toSnapshot,
} from './utils/screenerEngine';

type ActiveTab =
  | 'watchlist'
  | 'changes'
  | 'rejected'
  | 'inspection'
  | 'config'
  | 'visualizations'
  | 'colab'
  | 'tests';

/** CSV only. XLSX support was removed with the vulnerable parser it required. */
const ACCEPT_ATTRIBUTE = '.csv,text/csv';

interface Notice {
  kind: 'error' | 'info';
  message: string;
}

interface LoadedPrices {
  fileName: string;
  history: PriceHistory;
}

const tickerCount = (n: number) => `${n} ticker${n === 1 ? '' : 's'}`;

/**
 * Read the CSV chosen in a file input. A rejected or unreadable file reports an
 * error and changes nothing else; onText runs only after a successful read.
 */
function readCsvInput(
  input: HTMLInputElement,
  reexportHint: string,
  onText: (file: File, text: string) => void,
  onError: (message: string) => void,
): void {
  const file = input.files?.[0];
  if (!file) return;
  if (!file.name.toLowerCase().endsWith('.csv')) {
    onError(`"${file.name}" was not loaded. This engine is CSV-only - ${reexportHint}.`);
    input.value = '';
    return;
  }
  const reader = new FileReader();
  reader.onerror = () => {
    input.value = '';
    onError(`Could not read "${file.name}".`);
  };
  reader.onload = () => {
    input.value = '';
    const text = typeof reader.result === 'string' ? reader.result : '';
    if (text.trim() === '') {
      onError(`"${file.name}" appears to be empty.`);
      return;
    }
    onText(file, text);
  };
  reader.readAsText(file);
}

/**
 * What GET /api/data-store answers with. Declared here rather than imported
 * from src/server/dataStore so no bundler is ever tempted to pull node:fs into
 * the browser build; the server test pins the two shapes together.
 */
interface DataStoreSnapshot {
  available: boolean;
  root: string;
  fundamentals: { name: string; modifiedMs: number; bytes: number } | null;
  prices: { name: string; modifiedMs: number; bytes: number } | null;
}

export default function App() {
  const [rawCsv, setRawCsv] = useState<string>(SAMPLE_SCREENER_CSV_STRING);
  const [fileName, setFileName] = useState<string>('bundled_sample.csv');
  const [appConfig, setAppConfig] = useState<AppConfig>(DEFAULT_APP_CONFIG);
  const [screeningConfig, setScreeningConfig] = useState<ScreeningConfig>(DEFAULT_SCREENING_CONFIG);
  const [activeTab, setActiveTab] = useState<ActiveTab>('watchlist');
  const [isSampleData, setIsSampleData] = useState<boolean>(true);
  const [fileLastModified, setFileLastModified] = useState<number | undefined>(undefined);
  const [prices, setPrices] = useState<LoadedPrices | null>(null);
  const [savedRun, setSavedRun] = useState<SavedRun | null>(null);
  const [notice, setNotice] = useState<Notice | null>(null);
  // Prices fetched from the data-store but not yet matched against the screened
  // universe. See the two effects below for why this is a two-step load.
  const [pendingPrices, setPendingPrices] = useState<{ fileName: string; text: string } | null>(null);

  useEffect(() => {
    try {
      const stored = localStorage.getItem(SAVED_RUN_KEY);
      // Anything unusable -- an older shape, a hand-edited or half-written
      // value -- is discarded rather than handed to the delta code, which used
      // to throw during render and leave the page blank.
      setSavedRun(stored ? parseSavedRun(JSON.parse(stored)) : null);
    } catch {
      setSavedRun(null);
    }
  }, []);

  /**
   * Load whatever the CLI last wrote, so opening the page after a run shows
   * that run rather than the bundled sample.
   *
   * Runs once, on mount, and only ever replaces the SAMPLE: a person who has
   * uploaded a file has said what they want screened, and a background fetch
   * must not overrule them. Every failure path -- no route, no server, no
   * data-store, an empty file -- leaves the sample in place silently, because
   * `data-store/**` is gitignored and its absence is the normal state of a
   * fresh clone rather than a fault worth interrupting anyone about.
   *
   * Prices are staged rather than applied here. Matching them against the
   * screened tickers needs the pipeline to have re-run on the new fundamentals
   * first, which has not happened yet at this point.
   */
  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const indexResponse = await fetch('/api/data-store');
        if (!indexResponse.ok) return;
        const snapshot = (await indexResponse.json()) as DataStoreSnapshot;
        if (cancelled || !snapshot.available || snapshot.fundamentals === null) return;

        const csvResponse = await fetch('/api/data-store/fundamentals');
        if (!csvResponse.ok) return;
        const text = await csvResponse.text();
        if (cancelled || text.trim() === '') return;

        setRawCsv(text);
        setFileName(snapshot.fundamentals.name);
        setIsSampleData(false);
        setFileLastModified(snapshot.fundamentals.modifiedMs);

        if (snapshot.prices !== null) {
          const priceResponse = await fetch('/api/data-store/prices');
          if (priceResponse.ok) {
            const priceText = await priceResponse.text();
            if (!cancelled && priceText.trim() !== '') {
              setPendingPrices({ fileName: snapshot.prices.name, text: priceText });
            }
          }
        }
      } catch {
        // Offline, or a server without these routes. The sample stands.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const result = useMemo(
    () =>
      processScreenerPipeline(
        parseCsv(rawCsv),
        appConfig,
        screeningConfig,
        fileLastModified,
        prices?.history ?? null,
        fileName,
      ),
    [rawCsv, screeningConfig, appConfig, fileLastModified, prices, fileName],
  );
  const { inspectionReport: report, watchlist, rejected, evaluations: allEvaluations } = result;

  /**
   * Apply the staged price file, now that the pipeline has re-run on the
   * fundamentals from disk and `result` names the tickers that were actually
   * screened. Counting matches against the sample's tickers would have reported
   * a match rate for a universe nobody is looking at.
   *
   * Mirrors handlePriceUpload's checks rather than trusting the file: a
   * data-store CSV is no more guaranteed to parse, or to use bare NSE symbols,
   * than one a person picked by hand.
   */
  useEffect(() => {
    if (pendingPrices === null || isSampleData) return;
    setPendingPrices(null);
    let parsed: ReturnType<typeof parsePriceHistoryCsv>;
    try {
      parsed = parsePriceHistoryCsv(pendingPrices.text);
    } catch {
      return;
    }
    const screened = new Set(result.evaluations.map((e) => e.stock.ticker));
    const matched = Object.keys(parsed.history).filter((t) => screened.has(t)).length;
    if (matched === 0) return;
    setPrices({ fileName: pendingPrices.fileName, history: parsed.history });
    setNotice({
      kind: 'info',
      message:
        `Loaded from data-store: "${fileName}" and "${pendingPrices.fileName}" — ` +
        `${matched} of the ${screened.size} screened tickers have prices. ` +
        'This is the newest run on disk; re-run the engine and reload to refresh it.',
    });
  }, [pendingPrices, isSampleData, result, fileName]);

  const currentSnapshot = useMemo(() => toSnapshot(watchlist), [watchlist]);

  const rankingChanges = useMemo(
    () => computeRankingChanges(currentSnapshot, savedRun?.entries ?? null),
    [currentSnapshot, savedRun],
  );

  const priceSummary = useMemo(() => (prices ? describePriceHistory(prices.history) : null), [prices]);

  const handleSaveSnapshot = useCallback(() => {
    // The saved run is the only baseline the deltas compare against, so it is
    // never replaced by illustrative data, by nothing, or without asking.
    if (isSampleData) {
      setNotice({
        kind: 'error',
        message:
          'The bundled sample is illustrative data, so it cannot be saved as a baseline. ' +
          'Upload your own Screener.in CSV first.',
      });
      return;
    }
    if (currentSnapshot.length === 0) {
      setNotice({
        kind: 'error',
        message: 'Nothing passed the screen, so there is no watchlist to save as a baseline.',
      });
      return;
    }
    if (savedRun) {
      const saved = savedRun.savedAt ? new Date(savedRun.savedAt).toLocaleString() : 'an earlier run';
      const from = savedRun.fileName ? ` from "${savedRun.fileName}"` : '';
      const replace = window.confirm(
        `Replace the saved run of ${savedRun.entries.length} candidates${from}, saved ${saved}?\n\n` +
          'The deltas are measured against it, and the old one cannot be recovered.',
      );
      if (!replace) return;
    }
    // Persist the minimal snapshot shape plus what produced it. rawRow is
    // deliberately excluded: it is large, it is not needed for delta tracking,
    // and including it used to blow the localStorage quota on real exports.
    const run: SavedRun = {
      savedAt: new Date().toISOString(),
      fileName,
      appConfig,
      screeningConfig,
      entries: currentSnapshot,
    };
    try {
      localStorage.setItem(SAVED_RUN_KEY, JSON.stringify(run));
      setSavedRun(run);
      setNotice({
        kind: 'info',
        message: `Saved ${currentSnapshot.length} candidates from "${fileName}" as the comparison baseline.`,
      });
    } catch (error) {
      const isQuota =
        error instanceof DOMException &&
        (error.name === 'QuotaExceededError' || error.name === 'NS_ERROR_DOM_QUOTA_REACHED');
      setNotice({
        kind: 'error',
        message: isQuota
          ? 'Browser storage is full, so the snapshot was not saved. Clear site data and try again.'
          : `Could not save the snapshot: ${error instanceof Error ? error.message : String(error)}`,
      });
    }
  }, [currentSnapshot, isSampleData, savedRun, fileName, appConfig, screeningConfig]);

  const showError = useCallback((message: string) => setNotice({ kind: 'error', message }), []);

  const handleFileUpload = useCallback(
    (event: React.ChangeEvent<HTMLInputElement>) =>
      readCsvInput(
        event.target,
        're-export from Screener.in as CSV',
        (file, text) => {
          // Commit displayed state only after the read succeeds.
          setRawCsv(text);
          setFileName(file.name);
          setIsSampleData(false);
          setFileLastModified(file.lastModified);
          setNotice(null);
        },
        showError,
      ),
    [showError],
  );

  const handlePriceUpload = useCallback(
    (event: React.ChangeEvent<HTMLInputElement>) =>
      readCsvInput(
        event.target,
        'save the price history as CSV',
        (file, text) => {
          let parsed: ReturnType<typeof parsePriceHistoryCsv>;
          try {
            parsed = parsePriceHistoryCsv(text);
          } catch (error) {
            showError(`"${file.name}" was not loaded: ${error instanceof Error ? error.message : String(error)}.`);
            return;
          }
          const summary = describePriceHistory(parsed.history);
          if (summary.tickers === 0) {
            showError(`"${file.name}" has no usable price rows for any ticker.`);
            return;
          }
          // What matters is not how many tickers the file holds, but how many
          // of the screened ones it actually covers: a Yahoo-style export
          // (TCS.NS) matches nothing here.
          const screened = new Set(result.evaluations.map((e) => e.stock.ticker));
          const matched = Object.keys(parsed.history).filter((t) => screened.has(t)).length;
          const skipped = parsed.skipped > 0 ? ` ${parsed.skipped} malformed rows were skipped.` : '';
          if (matched === 0) {
            showError(
              `"${file.name}" holds ${tickerCount(summary.tickers)} but none of them match the ` +
                `${screened.size} screened tickers, so every technical score stays N/A. Tickers must ` +
                'match the screener exactly: Yahoo-style symbols need the .NS or .BO suffix removed ' +
                `(TCS.NS to TCS).${skipped}`,
            );
            return;
          }
          setPrices({ fileName: file.name, history: parsed.history });
          setNotice({
            kind: 'info',
            message:
              `Loaded daily prices from "${file.name}": ${matched} of the ${screened.size} screened ` +
              `tickers matched (file holds ${tickerCount(summary.tickers)}).` +
              (matched < screened.size
                ? ' Tickers that did not match may carry a .NS or .BO suffix.'
                : '') +
              skipped,
          });
        },
        showError,
      ),
    [showError, result],
  );

  const handleResetToSample = useCallback(() => {
    setRawCsv(SAMPLE_SCREENER_CSV_STRING);
    setFileName('bundled_sample.csv');
    setIsSampleData(true);
    setFileLastModified(undefined);
    setNotice(null);
  }, []);

  const tabs: { id: ActiveTab; label: string; icon: React.ReactNode; count?: number }[] = [
    { id: 'watchlist', label: `Watchlist (top ${appConfig.top_n})`, icon: <Sparkles className="w-3.5 h-3.5" />, count: watchlist.length },
    { id: 'changes', label: 'Run deltas', icon: <GitCompare className="w-3.5 h-3.5" />, count: rankingChanges.length },
    { id: 'rejected', label: 'Rejected audit', icon: <XCircle className="w-3.5 h-3.5" />, count: rejected.length },
    { id: 'config', label: 'Universe & config', icon: <Globe className="w-3.5 h-3.5" /> },
    { id: 'visualizations', label: 'Charts & factors', icon: <BarChart3 className="w-3.5 h-3.5" /> },
    { id: 'colab', label: 'Colab script', icon: <Code2 className="w-3.5 h-3.5" /> },
    { id: 'inspection', label: 'Data schema', icon: <Database className="w-3.5 h-3.5" /> },
    { id: 'tests', label: 'Unit tests', icon: <ShieldCheck className="w-3.5 h-3.5" /> },
  ];

  const headerButton =
    'inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors';

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 font-sans antialiased flex flex-col">
      <header className="bg-white border-b border-slate-200 sticky top-0 z-30">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-3 flex flex-col md:flex-row md:items-center md:justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-blue-600 text-white flex items-center justify-center font-bold text-lg">
              ₹
            </div>
            <div>
              <div className="flex items-center gap-2 flex-wrap">
                <h1 className="text-base font-bold tracking-tight">Indian Stock Screening Engine</h1>
                <span className="text-[10px] font-semibold bg-blue-50 text-blue-700 px-2 py-0.5 rounded border border-blue-100 uppercase">
                  {appConfig.universe_mode === 'nifty100' ? 'Nifty 100' : 'Custom universe'}
                </span>
                <span className="text-[11px] font-mono text-slate-500 hidden sm:inline-block">
                  NSE / BSE equities (₹ crore)
                </span>
              </div>
              <p className="text-xs text-slate-500">
                Deterministic medium-term research screen. Fundamentals from Screener.in CSV exports.
              </p>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <label
              htmlFor="screener-csv-file-input"
              className={`${headerButton} bg-blue-50 text-blue-700 hover:bg-blue-100 border border-blue-200 cursor-pointer focus-within:ring-2 focus-within:ring-blue-500`}
            >
              <FileUp className="w-3.5 h-3.5 text-blue-600" />
              <span>Upload Screener.in CSV</span>
              {/* sr-only, not hidden: a display:none input cannot be tabbed to. */}
              <input
                type="file"
                accept={ACCEPT_ATTRIBUTE}
                onChange={handleFileUpload}
                className="sr-only"
                id="screener-csv-file-input"
              />
            </label>

            <label
              htmlFor="price-history-file-input"
              className={`${headerButton} bg-purple-50 text-purple-700 hover:bg-purple-100 border border-purple-200 cursor-pointer focus-within:ring-2 focus-within:ring-purple-500`}
              title="Daily prices as Date,Ticker,Close[,Volume] - the file the Python engine saves in data-store/market_data/"
            >
              <LineChart className="w-3.5 h-3.5 text-purple-600" />
              <span>Upload prices</span>
              <input
                type="file"
                accept={ACCEPT_ATTRIBUTE}
                onChange={handlePriceUpload}
                className="sr-only"
                id="price-history-file-input"
              />
            </label>

            {!isSampleData && (
              <button
                onClick={handleResetToSample}
                className={`${headerButton} bg-slate-100 hover:bg-slate-200 text-slate-700 font-medium`}
                title="Reload the bundled sample export"
              >
                <RefreshCw className="w-3 h-3 text-slate-500" />
                Reset sample
              </button>
            )}

            <button
              onClick={handleSaveSnapshot}
              className={`${headerButton} bg-emerald-600 hover:bg-emerald-700 text-white`}
              title="Save this watchlist so the next run can be compared against it"
            >
              <Save className="w-3.5 h-3.5" />
              Save run
            </button>

            <button
              onClick={() => downloadText(serializeNotebook(), NOTEBOOK_FILENAME, 'application/json')}
              className={`${headerButton} bg-blue-600 hover:bg-blue-700 text-white`}
              title="Download the executable Colab notebook"
            >
              <Download className="w-3.5 h-3.5" />
              Download .ipynb
            </button>

            <button
              onClick={() =>
                downloadText(
                  generateHtmlReport(
                    watchlist, result.passedBelowCutOff, rejected, report, appConfig,
                    result.fundamentalOnly, result.sizing,
                  ),
                  `research_report_${todayStamp()}.html`,
                  'text/html',
                )
              }
              className={`${headerButton} bg-white border border-slate-200 hover:bg-slate-50 text-slate-700`}
              title="Download a standalone HTML research report"
            >
              <FileText className="w-3.5 h-3.5 text-purple-600" />
              HTML report
            </button>
          </div>
        </div>

        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex overflow-x-auto space-x-1 border-t border-slate-100">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`py-2 px-3 text-xs font-semibold border-b-2 transition-colors whitespace-nowrap flex items-center gap-1.5 ${
                activeTab === tab.id
                  ? 'border-blue-600 text-blue-600'
                  : 'border-transparent text-slate-600 hover:text-slate-900'
              }`}
            >
              {tab.icon}
              {tab.label}
              {tab.count !== undefined && (
                <span className="ml-1 text-[10px] px-1.5 bg-slate-100 text-slate-700 rounded-full font-mono">
                  {tab.count}
                </span>
              )}
            </button>
          ))}
        </div>
      </header>

      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-5 space-y-5">
        {notice && (
          <div
            role={notice.kind === 'error' ? 'alert' : 'status'}
            className={`rounded-xl px-4 py-3 text-xs flex items-start justify-between gap-3 border ${
              notice.kind === 'error'
                ? 'bg-rose-50 border-rose-200 text-rose-900'
                : 'bg-emerald-50 border-emerald-200 text-emerald-900'
            }`}
          >
            <div className="flex items-start gap-2">
              <AlertTriangle className="w-4 h-4 flex-shrink-0 mt-0.5" />
              <span>{notice.message}</span>
            </div>
            <button
              onClick={() => setNotice(null)}
              className="text-[11px] underline flex-shrink-0"
              aria-label="Dismiss notice"
            >
              dismiss
            </button>
          </div>
        )}

        {report.configErrors.length > 0 && (
          <div role="alert" className="bg-rose-50 border border-rose-200 rounded-xl px-4 py-3 text-xs text-rose-900">
            <strong>Configuration rejected:</strong> {report.configErrors.join('; ')}. No rows were screened.
          </div>
        )}

        {report.isStale && (
          <div className="bg-amber-50 border border-amber-200 rounded-xl px-4 py-3 flex items-start justify-between text-xs text-amber-900">
            <div className="flex items-start gap-2.5">
              <AlertTriangle className="w-4 h-4 text-amber-600 flex-shrink-0 mt-0.5" />
              <div>
                <strong>Fundamentals are stale:</strong> {report.fileAgeDays} days old, over the{' '}
                {appConfig.fundamentals_stale_after_days}-day threshold.
                <div className="text-[11px] text-amber-700 mt-0.5">
                  Last modified {report.fileModifiedDate}. Re-export from Screener.in after quarterly results.
                </div>
              </div>
            </div>
            <span className="text-[10px] font-mono bg-amber-200/60 text-amber-800 px-2 py-0.5 rounded font-bold">
              STALE
            </span>
          </div>
        )}

        <div className="bg-slate-100/70 border border-slate-200/80 rounded-xl px-4 py-2 flex flex-wrap items-center justify-between gap-2 text-xs text-slate-600">
          <div className="flex items-center gap-2 flex-wrap">
            <Calendar className="w-3.5 h-3.5 text-blue-600" />
            <span title={report.dataDate ? `Data date ${report.dataDate}` : undefined}>
              Fundamentals:{' '}
              <strong>
                {isSampleData
                  ? 'illustrative sample, figures are made up'
                  : report.fileAgeDays === null
                  ? 'no date available'
                  : `${report.fileAgeDays} days old`}
              </strong>
              {report.dateSource && ` (by ${report.dateSource})`}
            </span>
            <span className="text-slate-400">•</span>
            <span>
              Universe: <strong>{appConfig.universe_mode}</strong> ({allEvaluations.length} evaluated
              {result.outsideUniverseCount > 0 &&
                `, ${result.outsideUniverseCount} outside the ${
                  appConfig.universe_mode === 'nifty100' ? 'Nifty 100' : 'symbol list'
                }`}
              )
            </span>
            {result.outsideUniverseCount > 0 && (
              <button
                onClick={() => setAppConfig({ ...appConfig, universe_mode: 'custom', custom_symbols: [] })}
                className="text-[11px] font-semibold text-blue-700 underline"
                title="Switch to a custom universe with no symbol list, so every row in the file is screened"
              >
                Screen all rows
              </button>
            )}
            <span className="text-slate-400">•</span>
            <span title={`SHA-256 ${NIFTY100_PROVENANCE.sha256_of_source_csv}`}>
              Nifty 100 snapshot: <strong>cached, as of {NIFTY100_PROVENANCE.as_of_date}</strong>
            </span>
            <span className="text-slate-400">•</span>
            <span>
              Prices:{' '}
              {prices && priceSummary ? (
                <>
                  <strong>
                    {tickerCount(priceSummary.tickers)}, as of {priceSummary.asOf ?? 'unknown'}
                  </strong>
                  {!priceSummary.hasBenchmark && (
                    <span className="text-amber-700"> (no {BENCHMARK_SYMBOL} rows, so no relative strength)</span>
                  )}{' '}
                  <button
                    onClick={() => setPrices(null)}
                    className="text-[11px] font-semibold text-blue-700 underline"
                    aria-label="Clear price history"
                  >
                    clear
                  </button>
                </>
              ) : (
                <strong>none loaded</strong>
              )}
            </span>
            {result.duplicatesCount > 0 && (
              <>
                <span className="text-slate-400">•</span>
                <span className="text-rose-600 font-semibold">{result.duplicatesCount} duplicates removed</span>
              </>
            )}
          </div>
          <span className="text-[11px] font-mono text-slate-500">File: {fileName}</span>
        </div>

        {activeTab === 'watchlist' && (
          <WatchlistTable
            watchlist={watchlist}
            belowCutOff={result.passedBelowCutOff}
            fundamentalOnly={result.fundamentalOnly}
            priceHistory={prices?.history ?? null}
            sizing={result.sizing}
          />
        )}
        {activeTab === 'changes' && (
          <RankingChangesView
            rankingChanges={rankingChanges}
            isFirstRun={savedRun === null}
            savedRun={savedRun}
          />
        )}
        {activeTab === 'rejected' && <RejectedTable rejected={rejected} />}
        {activeTab === 'config' && (
          <ConfigPanel
            appConfig={appConfig}
            onAppConfigChange={setAppConfig}
            screeningConfig={screeningConfig}
            onScreeningConfigChange={setScreeningConfig}
          />
        )}
        {activeTab === 'visualizations' && <Visualizations allEvaluations={allEvaluations} />}
        {activeTab === 'colab' && <ColabCellsViewer />}
        {activeTab === 'inspection' && (
          <DataInspectionView report={report} duplicateCompanies={result.duplicatesCount} />
        )}
        {activeTab === 'tests' && <TestsRunner />}
      </main>

      <footer className="bg-white border-t border-slate-200 py-3 mt-auto text-xs text-slate-500">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex flex-col sm:flex-row items-center justify-between gap-2">
          <span>Research signals only. Not investment advice. No orders are placed.</span>
          <span>CSV-only ingestion • deterministic rules • scores to one decimal</span>
        </div>
      </footer>
    </div>
  );
}
