import { useState } from 'react';
import { MarketStructure, SelectionReview, StockEvaluation } from '../types';
import { compareCodePoints, fmt1, generateSelectionReviewCsv } from '../utils/screenerEngine';
import { downloadText, todayStamp } from '../utils/download';
import { OrderFlowRequirements } from './OrderFlowRequirements';
import { SelectionHeatmap } from './SelectionHeatmap';

const labels: Record<SelectionReview['status'], string> = {
  candidate: 'Review candidates', mixed: 'Mixed patterns', unavailable: 'Incomplete / unaligned data', excluded: 'Failed screen',
};

export function SelectionReviewTable({ evaluations }: { evaluations: StockEvaluation[] }) {
  const [filter, setFilter] = useState<SelectionReview['status'] | 'all'>('candidate');
  const [auction, setAuction] = useState<MarketStructure['auctionContext']['position'] | 'all'>('all');
  const [view, setView] = useState('table');
  const visible = evaluations.filter(e => filter === 'all' || e.selectionReview.status === filter)
    .filter(e => auction === 'all' || (e.marketStructure?.auctionContext.position ?? 'unavailable') === auction)
    .sort((a, b) => b.score - a.score || compareCodePoints(a.stock.ticker, b.stock.ticker));
  return <section className="bg-white border border-slate-200 rounded-xl p-5 space-y-4" aria-label="Experimental selection review">
    <div>
      <h2 className="font-semibold text-slate-900">Selection review · experimental</h2>
      <p className="text-sm text-slate-600 mt-1">Review candidates pass the existing screen, close above anchored VWAP,
        and show a spring or markup candidate without a conflicting sweep. This rule has not been validated against returns.</p>
      <p className="text-xs text-slate-500 mt-2">Includes companies below the watchlist cutoff. Ordered by fundamental score;
        no new combined score or portfolio allocation. Uses the automatic 20-bar anchor, regardless of manual chart settings.</p>
      <p className="text-xs text-slate-500 mt-1">Dates are aligned to the latest session among screened companies in the loaded file.
        This does not certify that the file is current. Daily volume profiles are estimates; order flow remains unavailable.</p>
    </div>
    <OrderFlowRequirements />
    <div className="flex flex-wrap justify-between gap-3 text-xs">
      <label>Show <select aria-label="Selection review filter" value={filter}
        onChange={e => setFilter(e.target.value as typeof filter)} className="border rounded p-2 ml-1">
        {Object.entries(labels).map(([value, label]) => <option key={value} value={value}>
          {label} ({evaluations.filter(e => e.selectionReview.status === value).length})
        </option>)}
        <option value="all">All screened companies ({evaluations.length})</option>
      </select></label>
      <label>Prior value area <select aria-label="Auction context filter" value={auction}
        onChange={e => setAuction(e.target.value as typeof auction)} className="border rounded p-2 ml-1">
        <option value="all">All positions</option>
        {['above value', 'inside value', 'below value', 'unavailable'].map(v => <option key={v} value={v}>{v}</option>)}
      </select></label>
      <label>View <select aria-label="Review display" value={view} onChange={e => setView(e.target.value)} className="border rounded p-2 ml-1">
        <option value="table">Evidence table</option><option value="heatmap">Stock heatmap</option>
      </select></label>
      <button type="button" onClick={() => downloadText(generateSelectionReviewCsv(visible),
        `selection_review_${filter}_${todayStamp()}.csv`, 'text/csv;charset=utf-8')}
        className="font-semibold text-blue-700">Export displayed rows</button>
    </div>
    <p className="text-xs text-slate-500">Auction context compares the close with the estimated value area of the prior 20 bars, excluding the current bar.
      It does not establish acceptance or rejection. Filtering changes this view and its export only.</p>
    {visible.length === 0 ? <p className="text-sm text-slate-500">No companies in this view. Check the other review categories for missing data or conflicting patterns.</p>
      : view === 'heatmap' ? <SelectionHeatmap evaluations={visible} /> : <div className="overflow-x-auto"><table className="w-full text-xs text-left">
        <thead className="text-slate-500 border-b"><tr>
          <th className="p-2">Company</th><th className="p-2">Fundamental score</th><th className="p-2">Price date / anchor</th>
          <th className="p-2">VWAP / close distance</th><th className="p-2">Estimated profile</th><th className="p-2">Auction context</th><th className="p-2">Review evidence</th>
        </tr></thead>
        <tbody>{visible.map(e => <tr key={e.stock.id} className="border-b border-slate-100 align-top">
          <td className="p-2 font-semibold">{e.stock.name}<span className="block font-mono text-slate-500">{e.stock.ticker}</span></td>
          <td className="p-2 font-mono">{fmt1(e.score)} / 100</td>
          <td className="p-2">{e.marketStructure?.asOf ?? '—'}<span className="block text-slate-500">{e.marketStructure?.anchorDate ?? '—'}</span></td>
          <td className="p-2 font-mono">{e.marketStructure?.anchoredVwap.value == null ? '—' : fmt1(e.marketStructure.anchoredVwap.value)}
            <span className="block">{e.marketStructure?.anchoredVwap.distancePct == null ? '—' : `${fmt1(e.marketStructure.anchoredVwap.distancePct)}%`}</span></td>
          <td className="p-2">POC {e.marketStructure?.volumeProfile.poc == null ? '—' : fmt1(e.marketStructure.volumeProfile.poc)}
            <span className="block text-slate-500">Area {e.marketStructure?.volumeProfile.valueAreaLow == null ? '—' :
              `${fmt1(e.marketStructure.volumeProfile.valueAreaLow)}–${fmt1(e.marketStructure.volumeProfile.valueAreaHigh)}`}</span></td>
          <td className="p-2">{e.marketStructure?.auctionContext.position ?? 'unavailable'}
            <span className="block text-slate-500">Reference through {e.marketStructure?.auctionContext.referenceEnd ?? '—'}</span></td>
          <td className="p-2"><strong>{labels[e.selectionReview.status]}</strong>
            <ul className="list-disc pl-4 mt-1 text-slate-600">{e.selectionReview.reasons.map(r => <li key={r}>{r}</li>)}</ul></td>
        </tr>)}</tbody>
      </table></div>}
  </section>;
}
