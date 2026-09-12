import { AlertCircle, Download, XCircle } from 'lucide-react';
import React from 'react';
import { StockEvaluation } from '../types';
import { downloadText, todayStamp } from '../utils/download';
import { fmt1, generateRejectedCsv } from '../utils/screenerEngine';

interface RejectedTableProps {
  rejected: StockEvaluation[];
}

export const RejectedTable: React.FC<RejectedTableProps> = ({ rejected }) => {
  return (
    <div className="bg-white border border-slate-200 rounded-xl overflow-hidden shadow-xs" id="rejected-companies-container">
      <div className="px-5 py-4 border-b border-slate-100 flex items-center justify-between bg-slate-50/50">
        <div>
          <h2 className="text-sm font-semibold text-slate-900 tracking-tight flex items-center gap-2">
            <XCircle className="w-4 h-4 text-rose-500" />
            Filtered Out Companies ({rejected.length})
          </h2>
          <p className="text-xs text-slate-500 mt-0.5">
            Transparent audit showing why companies failed hard threshold cutoffs (e.g. excessive leverage, negative CFO, or low growth).
          </p>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          <span className="text-xs font-medium px-2.5 py-1 bg-rose-50 text-rose-700 rounded-full border border-rose-100">
            {rejected.length} Excluded
          </span>
          <button
            onClick={() =>
              downloadText(generateRejectedCsv(rejected), `rejected_${todayStamp()}.csv`, 'text/csv;charset=utf-8')
            }
            className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-white border border-slate-200 hover:bg-slate-50 text-slate-700 text-xs font-semibold rounded-lg"
          >
            <Download className="w-3.5 h-3.5 text-rose-600" />
            rejected.csv
          </button>
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs text-slate-700">
          <thead className="bg-slate-50 text-slate-500 font-medium border-b border-slate-100 uppercase tracking-wider text-[11px]">
            <tr>
              <th className="py-3 px-4">Company & Ticker</th>
              <th className="py-3 px-3">Sector</th>
              <th className="py-3 px-3 text-right">Raw Score</th>
              <th className="py-3 px-4">Failed Screening Thresholds (Rejection Triggers)</th>
              <th className="py-3 px-3 text-center">Warning Flags</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {rejected.map((item) => {
              const s = item.stock;
              return (
                <tr key={s.id} className="hover:bg-slate-50/80 transition-colors" id={`rejected-row-${s.ticker}`}>
                  <td className="py-3 px-4">
                    <div className="font-semibold text-slate-900 text-sm">{s.name}</div>
                    <span className="font-mono text-[11px] font-medium text-slate-500 bg-slate-100 px-1.5 py-0.5 rounded">
                      {s.ticker}
                    </span>
                  </td>
                  <td className="py-3 px-3 text-slate-600">{s.sector || 'Unclassified'}</td>
                  <td className="py-3 px-3 text-right font-mono font-semibold text-slate-700">
                    {fmt1(item.score)}/100
                  </td>
                  <td className="py-3 px-4">
                    <div className="flex flex-wrap gap-1.5 max-w-lg">
                      {item.rejectionReasons.map((reason, idx) => (
                        <span
                          key={idx}
                          className="inline-flex items-center gap-1 text-[11px] bg-rose-50 text-rose-700 border border-rose-100 px-2 py-0.5 rounded"
                        >
                          <AlertCircle className="w-3 h-3 text-rose-500 flex-shrink-0" />
                          {reason}
                        </span>
                      ))}
                    </div>
                  </td>
                  <td className="py-3 px-3 text-center">
                    {item.warningFlags.length > 0 ? (
                      <span className="text-[10px] text-amber-700 bg-amber-50 border border-amber-200 px-2 py-0.5 rounded-full font-medium">
                        {item.warningFlags.join(', ')}
                      </span>
                    ) : (
                      <span className="text-[10px] text-slate-400">—</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
};
