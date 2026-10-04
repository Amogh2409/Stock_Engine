import { StockEvaluation } from '../types';
import { fmt1 } from '../utils/screenerEngine';

const neutral = 'bg-slate-100 text-slate-700';
const above = 'bg-blue-100 text-blue-900';
const below = 'bg-orange-100 text-orange-900';

export function SelectionHeatmap({ evaluations }: { evaluations: StockEvaluation[] }) {
  return <div className="space-y-2">
    <p className="text-xs text-slate-600">Stock evidence heatmap. Blue means above a reference, orange below; colour is not a buy/sell instruction.
      Grey includes unavailable data. This view does not show order-book liquidity or combine evidence into a score.</p>
    <div className="overflow-x-auto"><table className="w-full text-xs text-left" aria-label="Stock evidence heatmap">
      <thead><tr>{['Company', 'Fundamental score', 'Close vs VWAP', 'Sweep', 'Price context', 'Prior value area', 'Review status']
        .map(label => <th className="p-2" key={label}>{label}</th>)}</tr></thead>
      <tbody>{evaluations.map(e => {
        const s = e.marketStructure;
        // Old or incomplete series must not look like current confirmation.
        const available = e.selectionReview.status !== 'unavailable' && e.passed;
        const distance = available ? s?.anchoredVwap.distancePct : null;
        const auction = available ? s?.auctionContext.position : 'unavailable';
        const cell = (label: string, tone = neutral) => <td className={`p-2 border-2 border-white ${tone}`}>{label}</td>;
        return <tr key={e.stock.id}>
          <th className="p-2">{e.stock.ticker}<span className="block font-normal text-slate-500">{s?.asOf ?? 'No price date'}</span></th>
          {cell(`${fmt1(e.score)} / 100`)}
          {cell(distance == null ? 'Unavailable' : `${fmt1(distance)}%`, distance == null || distance === 0 ? neutral : distance > 0 ? above : below)}
          {cell(available ? s?.sweep.side ?? 'Unavailable' : 'Unavailable')}
          {cell(available ? s?.wyckoff.context ?? 'Unavailable' : 'Unavailable')}
          {cell(auction ?? 'unavailable', auction === 'above value' ? above : auction === 'below value' ? below : neutral)}
          {cell(e.selectionReview.status)}
        </tr>;
      })}</tbody>
    </table></div>
  </div>;
}
