import {
  ArrowDownRight,
  ArrowUpRight,
  Download,
  GitCompare,
  Minus,
  Sparkles,
  TrendingDown,
  TrendingUp,
} from 'lucide-react';
import React from 'react';

import { RankingChange, RankingChangeType } from '../types';
import { downloadText } from '../utils/download';
import { fmt1, generateRankingChangesCsv, SavedRun } from '../utils/screenerEngine';

interface RankingChangesViewProps {
  isFirstRun?: boolean;
  rankingChanges: RankingChange[];
  /** The baseline these deltas are measured against, for provenance. */
  savedRun?: SavedRun | null;
}

const BADGES: Record<RankingChangeType, { label: string; className: string; icon: React.ReactNode }> = {
  NEW_ENTRY: {
    label: 'NEW_ENTRY',
    className: 'bg-emerald-100 text-emerald-800',
    icon: <Sparkles className="w-3 h-3" />,
  },
  REMOVED_ENTRY: {
    label: 'REMOVED_ENTRY',
    className: 'bg-rose-100 text-rose-800',
    icon: <Minus className="w-3 h-3" />,
  },
  RANK_UP: {
    label: 'RANK_UP',
    className: 'bg-blue-100 text-blue-800',
    icon: <ArrowUpRight className="w-3 h-3" />,
  },
  RANK_DOWN: {
    label: 'RANK_DOWN',
    className: 'bg-amber-100 text-amber-800',
    icon: <ArrowDownRight className="w-3 h-3" />,
  },
  STABLE: {
    label: 'STABLE',
    className: 'bg-slate-100 text-slate-600',
    icon: null,
  },
};

/** Signed display for a delta that may legitimately be undefined. */
function signed(value: number | null, digits: 0 | 1): string {
  if (value === null) return '—';
  const text = digits === 0 ? String(value) : fmt1(value);
  return value > 0 ? `+${text}` : text;
}

export const RankingChangesView: React.FC<RankingChangesViewProps> = ({
  rankingChanges,
  isFirstRun,
  savedRun = null,
}) => {
  const counts = {
    entries: rankingChanges.filter((r) => r.changeType === 'NEW_ENTRY').length,
    removals: rankingChanges.filter((r) => r.changeType === 'REMOVED_ENTRY').length,
    moves: rankingChanges.filter(
      (r) => r.changeType === 'RANK_UP' || r.changeType === 'RANK_DOWN' || r.changeType === 'STABLE',
    ).length,
  };

  const downloadChangesCsv = () =>
    downloadText(generateRankingChangesCsv(rankingChanges), 'ranking_changes.csv', 'text/csv;charset=utf-8');

  if (isFirstRun) {
    return (
      <div className="p-8 text-center bg-white border border-slate-200 rounded-xl">
        <GitCompare className="w-12 h-12 text-slate-300 mx-auto mb-4" />
        <h3 className="text-base font-semibold mb-2">No comparison snapshot yet</h3>
        <p className="text-sm text-slate-500 max-w-md mx-auto">
          Press <strong>Save run</strong> to store this watchlist. The next run will be compared
          against it and every entry, exit, rank move and newly-raised warning will be listed here.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6" id="ranking-changes-container">
      <div className="bg-white border border-slate-200 rounded-xl p-5 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <GitCompare className="w-5 h-5 text-blue-600" />
            <h3 className="text-sm font-semibold">Run-over-run deltas</h3>
          </div>
          {savedRun && (
            <p className="text-[11px] text-slate-600 mt-1 font-mono" data-testid="saved-run-details">
              Baseline: {savedRun.entries.length} candidates
              {savedRun.fileName ? ` from ${savedRun.fileName}` : ''}
              {savedRun.savedAt ? `, saved ${new Date(savedRun.savedAt).toLocaleString()}` : ''}
              {savedRun.appConfig
                ? ` · universe ${savedRun.appConfig.universe_mode}, top ${savedRun.appConfig.top_n}, min score ${savedRun.appConfig.minimum_total_score}`
                : ''}
              {savedRun.screeningConfig
                ? ` · ROCE ≥ ${savedRun.screeningConfig.minRocePct}%, D/E ≤ ${savedRun.screeningConfig.maxDebtToEquity}`
                : ''}
            </p>
          )}
          <p className="text-xs text-slate-500 mt-1 max-w-xl leading-relaxed">
            Compared against the snapshot saved in this browser. The exported CSV uses the same
            columns and change types as the Colab notebook, so runs from either engine can be
            compared directly. <code>RankDelta = PreviousRank − CurrentRank</code>, so a positive
            value means the stock moved up.
          </p>
        </div>
        <button
          onClick={downloadChangesCsv}
          className="inline-flex items-center gap-1.5 px-3 py-2 bg-white border border-slate-200 hover:bg-slate-50 text-slate-700 text-xs font-semibold rounded-lg transition-colors flex-shrink-0"
        >
          <Download className="w-3.5 h-3.5 text-blue-600" />
          ranking_changes.csv
        </button>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="p-4 bg-emerald-50/70 border border-emerald-200 rounded-xl">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-emerald-800">New entries</span>
            <Sparkles className="w-4 h-4 text-emerald-700" />
          </div>
          <div className="text-2xl font-bold font-mono text-emerald-900 mt-1">{counts.entries}</div>
        </div>
        <div className="p-4 bg-rose-50/70 border border-rose-200 rounded-xl">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-rose-800">Removed</span>
            <TrendingDown className="w-4 h-4 text-rose-700" />
          </div>
          <div className="text-2xl font-bold font-mono text-rose-900 mt-1">{counts.removals}</div>
        </div>
        <div className="p-4 bg-blue-50/70 border border-blue-200 rounded-xl">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-blue-800">Retained</span>
            <TrendingUp className="w-4 h-4 text-blue-700" />
          </div>
          <div className="text-2xl font-bold font-mono text-blue-900 mt-1">{counts.moves}</div>
        </div>
      </div>

      <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
        <div className="px-5 py-3.5 bg-slate-50 border-b border-slate-100 flex items-center justify-between">
          <h4 className="text-xs font-semibold uppercase tracking-wider">All changes</h4>
          <span className="text-xs text-slate-500 font-mono">{rankingChanges.length} rows</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-50 text-slate-500 font-medium border-b border-slate-100 uppercase tracking-wider text-[11px]">
              <tr>
                <th className="py-3 px-4">Ticker</th>
                <th className="py-3 px-3 text-center">ChangeType</th>
                <th className="py-3 px-3 text-center">Prev rank</th>
                <th className="py-3 px-3 text-center">Rank</th>
                <th className="py-3 px-3 text-center">Rank Δ</th>
                <th className="py-3 px-3 text-right">Score Δ</th>
                <th className="py-3 px-4">New warnings</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {rankingChanges.length === 0 && (
                <tr>
                  <td colSpan={7} className="py-6 px-4 text-center text-slate-400">
                    No changes since the saved snapshot.
                  </td>
                </tr>
              )}
              {rankingChanges.map((change) => {
                const badge = BADGES[change.changeType];
                return (
                  <tr key={`${change.ticker}-${change.changeType}`} className="hover:bg-slate-50/80">
                    <td className="py-3 px-4">
                      <div className="font-semibold">{change.ticker}</div>
                      <div className="text-[11px] text-slate-500 truncate max-w-[180px]">{change.name}</div>
                    </td>
                    <td className="py-3 px-3 text-center">
                      <span
                        className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold font-mono ${badge.className}`}
                      >
                        {badge.icon}
                        {badge.label}
                      </span>
                    </td>
                    <td className="py-3 px-3 text-center font-mono">
                      {change.previousRank === null ? '—' : `#${change.previousRank}`}
                    </td>
                    <td className="py-3 px-3 text-center font-mono">
                      {change.currentRank === null ? 'OUT' : `#${change.currentRank}`}
                    </td>
                    <td
                      className={`py-3 px-3 text-center font-mono ${
                        change.rankDelta === null
                          ? 'text-slate-400'
                          : change.rankDelta > 0
                          ? 'text-emerald-600'
                          : change.rankDelta < 0
                          ? 'text-rose-600'
                          : 'text-slate-500'
                      }`}
                    >
                      {signed(change.rankDelta, 0)}
                    </td>
                    <td
                      className={`py-3 px-3 text-right font-mono ${
                        change.scoreDelta === null
                          ? 'text-slate-400'
                          : change.scoreDelta > 0
                          ? 'text-emerald-600'
                          : change.scoreDelta < 0
                          ? 'text-rose-600'
                          : 'text-slate-500'
                      }`}
                    >
                      {signed(change.scoreDelta, 1)}
                    </td>
                    <td className="py-3 px-4">
                      {change.newWarnings.length > 0 ? (
                        <span className="text-rose-600">{change.newWarnings.join('; ')}</span>
                      ) : (
                        <span className="text-slate-400">—</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
