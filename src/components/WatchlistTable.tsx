import { AlertTriangle, ChevronRight, Download, Info, Sparkles, TrendingUp } from 'lucide-react';
import React, { useState } from 'react';

import { StockEvaluation, TechnicalIndicators } from '../types';
import { downloadText, todayStamp } from '../utils/download';
import { fmt1, generateWatchlistCsv, PriceHistory } from '../utils/screenerEngine';
import { PriceChart } from './PriceChart';

interface WatchlistTableProps {
  watchlist: StockEvaluation[];
  /** Passed every rule but ranked below top_n. Shown so nothing that passed is hidden. */
  belowCutOff?: StockEvaluation[];
  /**
   * Passed every rule, but this run priced other companies and not these, so
   * their composite has no technical half and is not on the same scale as the
   * watchlist. Shown separately for the same reason: nothing that passed is
   * hidden, and nothing is ranked against a scale it never faced.
   */
  fundamentalOnly?: StockEvaluation[];
  /**
   * The loaded closes, so the detail panel can chart the selected company. The
   * indicators on the evaluation are derived values; this is the series they
   * were derived from, and nothing here recomputes them.
   */
  priceHistory?: PriceHistory | null;
}

/**
 * Selection is keyed by ticker, not by object or row id, so after a new upload
 * or a threshold change the panel follows the same company if it is still
 * listed and otherwise falls back to the top row -- it never keeps describing a
 * stock from data that is no longer loaded.
 */
function selectionKey(item: StockEvaluation): string {
  return item.stock.ticker || item.stock.id;
}

type Tone = 'good' | 'bad' | 'neutral' | 'na';

const TONE_CLASS: Record<Tone, string> = {
  good: 'text-emerald-600',
  bad: 'text-rose-600',
  neutral: 'text-slate-900',
  na: 'text-slate-400',
};

interface IndicatorCell {
  label: string;
  value: string;
  tone: Tone;
}

/** Every cell reads "—" unless its indicator actually had enough history. */
function indicatorCells(t: TechnicalIndicators): IndicatorCell[] {
  const flag = (available: boolean, value: boolean | null, yes: string, no: string) =>
    !available || value === null
      ? { value: '—', tone: 'na' as Tone }
      : value
      ? { value: yes, tone: 'good' as Tone }
      : { value: no, tone: 'bad' as Tone };
  const rs = t.available.relativeStrength6M ? t.relativeStrength6M : null;
  const dist = t.available.high52Week ? t.distFrom52WHighPct : null;
  return [
    { label: 'Price vs 50 SMA', ...flag(t.available.sma50, t.isAboveSma50, 'Above', 'Below') },
    { label: 'Price vs 200 SMA', ...flag(t.available.sma200, t.isAboveSma200, 'Above', 'Below') },
    { label: '50 vs 200 SMA', ...flag(t.available.smaCross, t.isSma50Above200, '50 > 200', '50 ≤ 200') },
    {
      label: '6M rel. strength',
      value: rs === null ? '—' : `${rs > 0 ? '+' : ''}${fmt1(rs)}%`,
      tone: rs === null ? 'na' : rs > 0 ? 'good' : 'bad',
    },
    {
      label: '20D volume ratio',
      value: t.volumeRatio20D === null ? '—' : `${t.volumeRatio20D.toFixed(2)}x`,
      tone: t.volumeRatio20D === null ? 'na' : 'neutral',
    },
    {
      label: 'From 52W high',
      value: dist === null ? '—' : `${fmt1(dist)}%`,
      tone: dist === null ? 'na' : 'neutral',
    },
  ];
}

function ratio(value: number | null, suffix = ''): string {
  return value === null ? '—' : `${fmt1(value)}${suffix}`;
}

interface ExtraListProps {
  items: StockEvaluation[];
  id: string;
  title: string;
  blurb: React.ReactNode;
  fileName: string;
}

/**
 * A secondary list under the watchlist: companies that passed every rule but
 * sit outside it, either because they rank below top_n or because this run
 * could not price them. Both exist so that nothing which passed is ever hidden,
 * and neither is mixed into the watchlist's ordering.
 */
const ExtraList: React.FC<ExtraListProps> = ({ items, id, title, blurb, fileName }) => {
  if (items.length === 0) return null;
  return (
    <div className="bg-white border border-slate-200 rounded-xl overflow-hidden shadow-xs" id={id}>
      <div className="px-5 py-4 border-b border-slate-100 flex items-center justify-between gap-3 bg-slate-50/50">
        <div>
          <h2 className="text-sm font-semibold text-slate-900 tracking-tight">
            {title} ({items.length})
          </h2>
          <p className="text-xs text-slate-500 mt-0.5">{blurb}</p>
        </div>
        <button
          onClick={() =>
            downloadText(
              generateWatchlistCsv(items),
              `${fileName}_${todayStamp()}.csv`,
              'text/csv;charset=utf-8',
            )
          }
          className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-white border border-slate-200 hover:bg-slate-50 text-slate-700 text-xs font-semibold rounded-lg flex-shrink-0"
        >
          <Download className="w-3.5 h-3.5 text-blue-600" />
          {fileName}.csv
        </button>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs text-slate-700">
          <thead className="bg-slate-50 text-slate-500 font-medium border-b border-slate-100 uppercase tracking-wider text-[11px]">
            <tr>
              <th className="py-3 px-3 w-10 text-center">#</th>
              <th className="py-3 px-3">Company &amp; Ticker</th>
              <th className="py-3 px-3 text-right">Fund. Score</th>
              <th className="py-3 px-3 text-right">Tech. Score</th>
              <th className="py-3 px-3 text-center">Flags</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {items.map((item) => (
              <tr key={item.stock.id} className="hover:bg-slate-50/80">
                <td className="py-2.5 px-3 text-center font-mono font-semibold text-slate-400">{item.rank}</td>
                <td className="py-2.5 px-3">
                  <span className="font-semibold text-slate-900">{item.stock.name}</span>{' '}
                  <span className="font-mono text-[10px] bg-slate-100 px-1 rounded text-slate-700">
                    {item.stock.ticker}
                  </span>
                </td>
                <td className="py-2.5 px-3 text-right font-mono font-bold">{fmt1(item.score)}</td>
                <td className="py-2.5 px-3 text-right font-mono">
                  {item.technicalScore.score === null ? 'N/A' : `${item.technicalScore.score}/100`}
                </td>
                <td className="py-2.5 px-3 text-center text-[11px] text-amber-700">
                  {item.warningFlags.length > 0 ? item.warningFlags.length : '0'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export const WatchlistTable: React.FC<WatchlistTableProps> = ({
  watchlist,
  belowCutOff = [],
  fundamentalOnly = [],
  priceHistory = null,
}) => {
  const [selectedKey, setSelectedKey] = useState<string | null>(null);

  if (watchlist.length === 0 && belowCutOff.length === 0) {
    return (
      <div className="bg-white border border-slate-200 rounded-xl p-8 text-center" id="empty-watchlist-state">
        <AlertTriangle className="w-10 h-10 text-amber-500 mx-auto mb-3" />
        <h3 className="text-base font-semibold text-slate-800">No companies qualified</h3>
        <p className="text-sm text-slate-500 mt-1 max-w-md mx-auto">
          Nothing in the current universe passed every rule. Widen the universe or loosen the
          thresholds (for example the minimum total score) in Universe &amp; config.
        </p>
      </div>
    );
  }

  const activeStock = watchlist.find((w) => selectionKey(w) === selectedKey) ?? watchlist[0];
  const activeIndex = watchlist.indexOf(activeStock);
  const s = activeStock.stock;
  const t = s.technicals;
  const tech = activeStock.technicalScore;

  return (
    <div className="space-y-6" id="watchlist-container">
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        <div className="lg:col-span-7 bg-white border border-slate-200 rounded-xl overflow-hidden shadow-xs">
          <div className="px-5 py-4 border-b border-slate-100 flex items-center justify-between gap-3 bg-slate-50/50">
            <div>
              <h2 className="text-sm font-semibold text-slate-900 tracking-tight flex items-center gap-2">
                <Sparkles className="w-4 h-4 text-blue-600" />
                Ranked watchlist ({watchlist.length})
              </h2>
              <p className="text-xs text-slate-500 mt-0.5">
                Deterministic fundamental ranking plus a separate technical confirmation score.
              </p>
            </div>
            <button
              onClick={() =>
                downloadText(generateWatchlistCsv(watchlist), `watchlist_${todayStamp()}.csv`, 'text/csv;charset=utf-8')
              }
              className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-white border border-slate-200 hover:bg-slate-50 text-slate-700 text-xs font-semibold rounded-lg flex-shrink-0"
            >
              <Download className="w-3.5 h-3.5 text-blue-600" />
              watchlist.csv
            </button>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs text-slate-700">
              <thead className="bg-slate-50 text-slate-500 font-medium border-b border-slate-100 uppercase tracking-wider text-[11px]">
                <tr>
                  <th className="py-3 px-3 w-10 text-center">#</th>
                  <th className="py-3 px-3">Company & Ticker</th>
                  <th className="py-3 px-3 text-right" title="Latest close when a price history is loaded, otherwise the export's price">
                    CMP (₹)
                  </th>
                  <th className="py-3 px-3 text-right">Fund. Score</th>
                  <th className="py-3 px-3 text-right">Tech. Score</th>
                  <th className="py-3 px-3 text-center">Flags</th>
                  <th className="py-3 px-2 w-8"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {watchlist.map((item, idx) => {
                  const isSelected = item === activeStock;
                  const stock = item.stock;
                  const techScore = item.technicalScore.score;
                  return (
                    <tr
                      key={stock.id}
                      onClick={() => setSelectedKey(selectionKey(item))}
                      className={`cursor-pointer transition-colors ${
                        isSelected ? 'bg-blue-50/70 text-slate-900' : 'hover:bg-slate-50/80'
                      }`}
                    >
                      <td className="py-3 px-3 text-center font-mono font-semibold text-slate-400">
                        {item.rank ?? idx + 1}
                      </td>
                      <td className="py-3 px-3">
                        <div className="font-semibold text-slate-900 truncate max-w-[170px]">{stock.name}</div>
                        <div className="flex items-center gap-1.5 text-[10px] text-slate-500 mt-0.5 font-mono">
                          <span className="bg-slate-100 px-1 rounded text-slate-700 font-semibold">{stock.ticker}</span>
                          <span className="truncate max-w-[100px] text-slate-400">{stock.sector}</span>
                        </div>
                      </td>
                      <td className="py-3 px-3 text-right font-mono font-medium">
                        {(() => {
                          // The export's price is whatever it was when the CSV
                          // was made; an uploaded price history is newer.
                          const tech = stock.technicals;
                          const latest = tech && tech.currentPrice !== null ? tech : null;
                          const price = latest ? latest.currentPrice : stock.currentPrice;
                          if (price === null) return '—';
                          return (
                            <span title={latest ? `Close on ${latest.as_of}` : 'From the fundamentals export'}>
                              ₹{price.toLocaleString('en-IN')}
                              <span className="block text-[10px] font-normal text-slate-400">
                                {latest ? latest.as_of : 'export'}
                              </span>
                            </span>
                          );
                        })()}
                      </td>
                      <td className="py-3 px-3 text-right">
                        <span
                          className={`font-mono font-bold px-2 py-0.5 rounded text-xs ${
                            item.score >= 80
                              ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                              : 'bg-blue-50 text-blue-700 border border-blue-100'
                          }`}
                        >
                          {fmt1(item.score)}
                        </span>
                      </td>
                      <td className="py-3 px-3 text-right">
                        <span
                          className={`font-mono font-bold px-2 py-0.5 rounded text-xs ${
                            techScore !== null && techScore >= 70
                              ? 'bg-purple-50 text-purple-700 border border-purple-200'
                              : 'bg-slate-100 text-slate-600'
                          }`}
                        >
                          {techScore === null ? 'N/A' : `${techScore}/100`}
                        </span>
                      </td>
                      <td className="py-3 px-3 text-center">
                        {item.warningFlags.length > 0 ? (
                          <span
                            className="inline-flex items-center justify-center w-5 h-5 rounded-full bg-amber-100 text-amber-800 text-[10px] font-bold"
                            title={item.warningFlags.join('; ')}
                          >
                            {item.warningFlags.length}
                          </span>
                        ) : (
                          <span className="text-[10px] text-slate-300 font-mono">0</span>
                        )}
                      </td>
                      <td className="py-3 px-2 text-right">
                        <ChevronRight
                          className={`w-4 h-4 transition-transform ${
                            isSelected ? 'text-blue-600 translate-x-0.5' : 'text-slate-300'
                          }`}
                        />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>

        <div
          className="lg:col-span-5 bg-white border border-slate-200 rounded-xl p-5 shadow-xs flex flex-col space-y-4"
          data-testid="watchlist-detail"
        >
          <div className="border-b border-slate-100 pb-3">
            <div className="flex items-center justify-between">
              <div>
                <span className="text-xs font-mono font-bold text-blue-600 bg-blue-50 px-2 py-0.5 rounded">
                  {s.ticker}
                </span>
                <h3 className="text-base font-bold text-slate-900 mt-1">{s.name}</h3>
                <p className="text-xs text-slate-500">{s.sector || 'Unclassified'}</p>
              </div>
              <div className="text-right">
                <div className="text-xs text-slate-400 font-medium">Rank in watchlist</div>
                <div className="text-2xl font-black font-mono text-blue-600">
                  #{activeStock.rank ?? activeIndex + 1}
                </div>
              </div>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="p-3 bg-blue-50/70 border border-blue-200 rounded-xl">
              <span className="text-[10px] font-semibold uppercase text-blue-700 tracking-wider block">
                Fundamental score
              </span>
              <div className="text-2xl font-bold font-mono text-blue-900 mt-0.5">
                {fmt1(activeStock.score)} <span className="text-xs text-blue-500 font-normal">/ 100</span>
              </div>
              <span className="text-[10px] text-blue-600 mt-0.5 block">
                Quality, growth, balance sheet, valuation, governance
              </span>
            </div>

            <div className="p-3 bg-purple-50/70 border border-purple-200 rounded-xl">
              <span className="text-[10px] font-semibold uppercase text-purple-700 tracking-wider block">
                Technical confirmation
              </span>
              <div className="text-2xl font-bold font-mono text-purple-900 mt-0.5">
                {tech.score === null ? 'N/A' : tech.score}{' '}
                <span className="text-xs text-purple-500 font-normal">/ 100</span>
              </div>
              <span className="text-[10px] text-purple-600 mt-0.5 block">
                {tech.score === null ? tech.breakdown[0] : 'Trend, 50/200 SMA, 6M RS, 52W proximity'}
              </span>
            </div>
          </div>

          <div className="bg-slate-50 rounded-xl p-3 border border-slate-100">
            <span className="text-[11px] font-semibold text-slate-700 flex items-center gap-1 mb-1">
              <Info className="w-3.5 h-3.5 text-blue-600" />
              Research rationale
            </span>
            <p className="text-xs text-slate-600 leading-relaxed">{activeStock.explanation}</p>
          </div>

          <div className="space-y-2">
            <span className="text-[11px] font-semibold text-slate-700 flex items-center gap-1">
              <TrendingUp className="w-3.5 h-3.5 text-purple-600" />
              Technical setup (daily closes)
            </span>
            {t === null ? (
              <p className="text-xs text-slate-500 leading-relaxed" data-testid="no-price-history">
                No price history loaded. Use <strong>Upload prices</strong> with a Date, Ticker, Close
                (and optional Volume) CSV. The Python engine saves exactly that file to{' '}
                <code>data-store/market_data/</code> on every networked run.
              </p>
            ) : t.data_status === 'UNAVAILABLE' ? (
              <p className="text-xs text-slate-500" data-testid="short-price-history">
                {t.history_rows > 0 ? (
                  <>
                    The loaded price history has only {t.history_rows} sessions for{' '}
                    <strong>{s.ticker}</strong>; every indicator needs at least 50.
                  </>
                ) : (
                  <>
                    The loaded price history has no sessions for <strong>{s.ticker}</strong>.
                  </>
                )}
              </p>
            ) : (
              <>
                {(() => {
                  // hasOwnProperty, not a bare index: the history is a plain
                  // record, so a ticker that collides with Object.prototype
                  // would otherwise hand back a function instead of a series.
                  const series =
                    priceHistory && Object.prototype.hasOwnProperty.call(priceHistory, s.ticker)
                      ? priceHistory[s.ticker]
                      : null;
                  if (!series) return null;
                  // Each level is drawn only when the score was allowed to use
                  // it, so the chart never shows a line the points ignored.
                  return (
                    <PriceChart
                      closes={series.closes}
                      dates={series.dates}
                      sma50={t.available.sma50 ? t.sma50 : null}
                      sma200={t.available.sma200 ? t.sma200 : null}
                      high52Week={t.available.high52Week ? t.high52Week : null}
                    />
                  );
                })()}
                <div className="grid grid-cols-2 gap-2 text-xs">
                  {indicatorCells(t).map((cell) => (
                    <div
                      key={cell.label}
                      className="p-2 rounded bg-slate-50 border border-slate-100 flex justify-between items-center"
                    >
                      <span className="text-slate-500">{cell.label}:</span>
                      <span className={`font-mono font-semibold ${TONE_CLASS[cell.tone]}`}>{cell.value}</span>
                    </div>
                  ))}
                </div>
                <p className="text-[11px] text-slate-500 font-mono">
                  {t.history_rows} sessions · as of {t.as_of ?? 'unknown'} · {t.data_status}
                </p>
                <ul className="text-[11px] text-slate-600 list-disc list-inside">
                  {tech.breakdown.map((line) => (
                    <li key={line}>{line}</li>
                  ))}
                </ul>
              </>
            )}
          </div>

          {activeStock.warningFlags.length > 0 && (
            <div className="p-3 bg-amber-50/80 border border-amber-200 rounded-xl space-y-1">
              <span className="text-[11px] font-bold text-amber-800 flex items-center gap-1">
                <AlertTriangle className="w-3.5 h-3.5 text-amber-600" />
                Risk &amp; governance flags ({activeStock.warningFlags.length})
              </span>
              <ul className="text-xs text-amber-700 list-disc list-inside space-y-0.5">
                {activeStock.warningFlags.map((flag) => (
                  <li key={flag}>{flag}</li>
                ))}
              </ul>
            </div>
          )}

          <div className="pt-2 border-t border-slate-100 grid grid-cols-3 gap-2 text-center text-xs">
            <div className="p-2 bg-slate-50 rounded">
              <span className="text-[10px] text-slate-400 block">ROCE</span>
              <span className="font-mono font-bold text-slate-800">{ratio(s.roce, '%')}</span>
            </div>
            <div className="p-2 bg-slate-50 rounded">
              <span className="text-[10px] text-slate-400 block">D/E ratio</span>
              <span className="font-mono font-bold text-slate-800">{ratio(s.debtToEquity, 'x')}</span>
            </div>
            <div className="p-2 bg-slate-50 rounded">
              <span className="text-[10px] text-slate-400 block">P/E ratio</span>
              <span className="font-mono font-bold text-slate-800">{ratio(s.peRatio)}</span>
            </div>
          </div>
        </div>
      </div>

      <ExtraList
        items={belowCutOff}
        id="below-cutoff-container"
        title="Passed, below the cut-off"
        fileName="passed_below_top_n"
        blurb={
          <>
            These passed every rule but rank below the watchlist size, so they are not in the
            watchlist above. Raise <strong>Watchlist size (top N)</strong> to include them.
          </>
        }
      />

      <ExtraList
        items={fundamentalOnly}
        id="fundamental-only-container"
        title="Passed, but this run could not price them"
        fileName="passed_unpriced"
        blurb={
          <>
            These passed every rule, but no price history covered them, so their score has no
            technical half. They are ranked separately because a score without one is not on the
            same scale as the watchlist above — mixing them in would reward being absent from the
            price file. Upload prices covering them to rank them alongside the rest.
          </>
        }
      />
    </div>
  );
};
