import { BarChart3, PieChart, TrendingUp } from 'lucide-react';
import React from 'react';
import { StockEvaluation } from '../types';

interface VisualizationsProps {
  allEvaluations: StockEvaluation[];
}

export const Visualizations: React.FC<VisualizationsProps> = ({ allEvaluations }) => {
  if (allEvaluations.length === 0) {
    return (
      <div className="bg-white border border-slate-200 rounded-xl p-8 text-center" id="visualizations-empty">
        <BarChart3 className="w-10 h-10 text-slate-300 mx-auto mb-3" />
        <h3 className="text-base font-semibold text-slate-800">No companies were evaluated</h3>
        <p className="text-sm text-slate-500 mt-1 max-w-md mx-auto">
          There is nothing to chart yet. Either no row in the file is in the selected universe
          (try <strong>Screen all rows</strong> in the status bar), or the configuration was
          rejected. The Data schema tab shows what was read from the file.
        </p>
      </div>
    );
  }

  // 1. Score distribution over the five bands labelled below.
  const buckets = [
    { label: '0–29 (Low)', count: 0, color: 'bg-rose-500' },
    { label: '30–49 (Fair)', count: 0, color: 'bg-amber-500' },
    { label: '50–69 (Good)', count: 0, color: 'bg-sky-500' },
    { label: '70–84 (High)', count: 0, color: 'bg-blue-600' },
    { label: '85–100 (Prime)', count: 0, color: 'bg-emerald-600' },
  ];

  let totalScoreSum = 0;
  let maxScore = 0;
  let minScore = 100;

  allEvaluations.forEach((item) => {
    const s = item.score;
    totalScoreSum += s;
    if (s > maxScore) maxScore = s;
    if (s < minScore) minScore = s;

    if (s < 30) buckets[0].count++;
    else if (s < 50) buckets[1].count++;
    else if (s < 70) buckets[2].count++;
    else if (s < 85) buckets[3].count++;
    else buckets[4].count++;
  });

  const avgScore = (totalScoreSum / allEvaluations.length).toFixed(1);
  const maxBucketCount = Math.max(...buckets.map((b) => b.count), 1);

  // 2. Sector Performance (Average Score by Industry)
  const sectorMap: Record<string, { total: number; count: number }> = {};
  allEvaluations.forEach((item) => {
    const sector = item.stock.sector || 'Other';
    if (!sectorMap[sector]) {
      sectorMap[sector] = { total: 0, count: 0 };
    }
    sectorMap[sector].total += item.score;
    sectorMap[sector].count += 1;
  });

  const sectorAverages = Object.entries(sectorMap)
    .map(([sector, data]) => ({
      sector,
      avg: Math.round((data.total / data.count) * 10) / 10,
      count: data.count,
    }))
    .sort((a, b) => b.avg - a.avg)
    .slice(0, 7);

  // 3. Category Average Attainment
  const categoryAvgs = [
    {
      name: 'Financial Quality',
      max: 30,
      avg:
        allEvaluations.reduce((acc, e) => acc + e.categoryScores.financialQuality.score, 0) /
        allEvaluations.length,
      color: 'bg-blue-500',
    },
    {
      name: 'Growth Track',
      max: 25,
      avg:
        allEvaluations.reduce((acc, e) => acc + e.categoryScores.growth.score, 0) /
        allEvaluations.length,
      color: 'bg-emerald-500',
    },
    {
      name: 'Balance Sheet',
      max: 20,
      avg:
        allEvaluations.reduce((acc, e) => acc + e.categoryScores.balanceSheetSafety.score, 0) /
        allEvaluations.length,
      color: 'bg-amber-500',
    },
    {
      name: 'Valuation Ratio',
      max: 15,
      avg:
        allEvaluations.reduce((acc, e) => acc + e.categoryScores.valuation.score, 0) /
        allEvaluations.length,
      color: 'bg-purple-500',
    },
    {
      name: 'Governance',
      max: 10,
      avg:
        allEvaluations.reduce((acc, e) => acc + e.categoryScores.governance.score, 0) /
        allEvaluations.length,
      color: 'bg-sky-500',
    },
  ];

  return (
    <div className="space-y-6" id="visualizations-container">
      {/* Top Statistical Summary */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-xs">
          <span className="text-xs text-slate-500 font-medium uppercase tracking-wider block mb-1">
            Mean Score
          </span>
          <div className="text-2xl font-bold font-mono text-slate-900">{avgScore}</div>
          <span className="text-[11px] text-slate-400">Across {allEvaluations.length} equities</span>
        </div>
        <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-xs">
          <span className="text-xs text-slate-500 font-medium uppercase tracking-wider block mb-1">
            Highest Score
          </span>
          <div className="text-2xl font-bold font-mono text-emerald-600">{maxScore.toFixed(1)}</div>
          <span className="text-[11px] text-slate-400">Top factor performer</span>
        </div>
        <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-xs">
          <span className="text-xs text-slate-500 font-medium uppercase tracking-wider block mb-1">
            Lowest Score
          </span>
          <div className="text-2xl font-bold font-mono text-rose-500">{minScore.toFixed(1)}</div>
          <span className="text-[11px] text-slate-400">Weakest evaluated company</span>
        </div>
        <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-xs">
          <span className="text-xs text-slate-500 font-medium uppercase tracking-wider block mb-1">
            Score 70 or more
          </span>
          <div className="text-2xl font-bold font-mono text-blue-600">
            {allEvaluations.filter((e) => e.score >= 70).length}
          </div>
          <span className="text-[11px] text-slate-400">
            Across all evaluated companies, including rejected ones
          </span>
        </div>
      </div>

      {/* Distribution Histogram & Sector Breakdown */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Score Distribution Chart */}
        <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-xs">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h3 className="text-sm font-semibold text-slate-900 flex items-center gap-1.5">
                <BarChart3 className="w-4 h-4 text-blue-600" />
                Score Distribution Histogram (0–100)
              </h3>
              <p className="text-xs text-slate-500 mt-0.5">
                How many evaluated companies fall in each score band.
              </p>
            </div>
          </div>

          <div className="space-y-3 pt-2">
            {buckets.map((b, idx) => {
              const pct = Math.round((b.count / allEvaluations.length) * 100);
              const barHeightPct = (b.count / maxBucketCount) * 100;
              return (
                <div key={idx} className="space-y-1">
                  <div className="flex justify-between text-xs">
                    <span className="font-medium text-slate-700">{b.label}</span>
                    <span className="font-mono text-slate-500">
                      {b.count} stocks ({pct}%)
                    </span>
                  </div>
                  <div className="w-full bg-slate-100 h-3 rounded-full overflow-hidden">
                    <div
                      className={`${b.color} h-full rounded-full transition-all duration-500`}
                      style={{ width: `${barHeightPct}%` }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Sector Comparison Chart */}
        <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-xs">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h3 className="text-sm font-semibold text-slate-900 flex items-center gap-1.5">
                <TrendingUp className="w-4 h-4 text-emerald-600" />
                Sector / Industry Average Scores
              </h3>
              <p className="text-xs text-slate-500 mt-0.5">
                Mean fundamental score per sector (top seven).
              </p>
            </div>
          </div>

          <div className="space-y-3 pt-2">
            {sectorAverages.map((s, idx) => {
              const widthPct = (s.avg / 100) * 100;
              return (
                <div key={idx} className="space-y-1">
                  <div className="flex justify-between text-xs">
                    <span className="font-medium text-slate-700 truncate max-w-[200px]">
                      {s.sector}
                    </span>
                    <div className="flex items-center gap-2">
                      <span className="text-[11px] text-slate-400">({s.count} cos)</span>
                      <span className="font-mono font-semibold text-slate-900">{s.avg.toFixed(1)}</span>
                    </div>
                  </div>
                  <div className="w-full bg-slate-100 h-2.5 rounded-full overflow-hidden">
                    <div
                      className="bg-blue-600 h-full rounded-full transition-all duration-500"
                      style={{ width: `${widthPct}%` }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* Category Factor Averages */}
      <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-xs">
        <h3 className="text-sm font-semibold text-slate-900 mb-3 flex items-center gap-1.5">
          <PieChart className="w-4 h-4 text-purple-600" />
          Factor Category Average Attainment
        </h3>
        <div className="grid grid-cols-1 sm:grid-cols-5 gap-3">
          {categoryAvgs.map((c, i) => {
            const pct = Math.round((c.avg / c.max) * 100);
            return (
              <div key={i} className="p-3 bg-slate-50 rounded-xl border border-slate-100">
                <span className="text-xs text-slate-600 font-medium block truncate">{c.name}</span>
                <div className="text-lg font-bold font-mono text-slate-900 mt-1">
                  {c.avg.toFixed(1)}{' '}
                  <span className="text-xs text-slate-400 font-normal">/ {c.max}</span>
                </div>
                <div className="w-full bg-slate-200 h-1.5 rounded-full mt-2 overflow-hidden">
                  <div className={`${c.color} h-full`} style={{ width: `${pct}%` }} />
                </div>
                <span className="text-[10px] text-slate-500 mt-1 block">{pct}% attainment</span>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};
