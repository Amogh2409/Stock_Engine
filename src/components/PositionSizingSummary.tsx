import { Coins, Info, ShieldAlert } from 'lucide-react';
import React from 'react';

import { fmt1, round1, SizingSummary, STOP_ATR_MULTIPLE } from '../utils/screenerEngine';

interface PositionSizingSummaryProps {
  sizing: SizingSummary;
  /** How many companies are in the sized basket. */
  holdings: number;
}

const MEASURE_LABEL: Record<string, string> = {
  atrPct: 'ATR as a percentage of price',
  volatility30D: '30-day annualised volatility',
};

/**
 * What the sizing pass decided for the whole run.
 *
 * This exists because the per-company weights are meaningless without it. They
 * sum to less than 100 by design, and with nothing on screen to say why, a
 * deliberate risk decision reads as an arithmetic bug. The wording follows the
 * sentence the Python run already prints, so one run described in two places
 * does not read as two different answers.
 *
 * Two percentages are shown rather than one because they answer different
 * questions and can differ. Deployment is what the volatility target permitted,
 * measured before any cap. Invested is what the per-position risk ceiling and
 * the position and sector caps actually left. Showing only one would hide which
 * mechanism moved the money into cash.
 */
export const PositionSizingSummary: React.FC<PositionSizingSummaryProps> = ({ sizing, holdings }) => {
  const invested = sizing.investedPct;
  // Null figures mean "not measured", never "measured zero", so the unsized
  // state says so in words instead of rendering a confident 0%.
  if (sizing.deploymentPct === null || invested === null) {
    return (
      <div
        className="bg-amber-50/70 border border-amber-200 rounded-xl px-5 py-4 text-xs text-amber-900"
        data-testid="sizing-summary"
      >
        <span className="font-semibold flex items-center gap-1.5">
          <ShieldAlert className="w-4 h-4 text-amber-600" />
          No position sizes for this run
        </span>
        <p className="mt-1 text-amber-800">{sizing.basis}</p>
        <p className="mt-1 text-[11px] text-amber-700">
          Relative weights on their own would read as &ldquo;invest all of this&rdquo;, which is a
          claim about total exposure that nothing in this run measured. So no weight is shown
          rather than one that cannot be justified.
        </p>
      </div>
    );
  }

  const cash = round1(100 - invested);
  const measure = sizing.measure ? MEASURE_LABEL[sizing.measure] ?? sizing.measure : 'unknown';

  return (
    <div
      className="bg-white border border-slate-200 rounded-xl p-5 shadow-xs space-y-3"
      data-testid="sizing-summary"
    >
      <div>
        <h2 className="text-sm font-semibold text-slate-900 tracking-tight flex items-center gap-1.5">
          <Coins className="w-4 h-4 text-emerald-600" />
          Position sizing for this run
        </h2>
        <p className="text-xs text-slate-500 mt-0.5">
          Equal risk by {measure}, across {holdings} holding{holdings === 1 ? '' : 's'}.
        </p>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="p-3 bg-emerald-50/70 border border-emerald-200 rounded-xl">
          <span className="text-[10px] font-semibold uppercase text-emerald-700 tracking-wider block">
            Invested
          </span>
          <div className="text-2xl font-bold font-mono text-emerald-900 mt-0.5">{fmt1(invested)}%</div>
          <span className="text-[10px] text-emerald-600 mt-0.5 block">After every cap</span>
        </div>

        <div className="p-3 bg-slate-50 border border-slate-200 rounded-xl">
          <span className="text-[10px] font-semibold uppercase text-slate-600 tracking-wider block">
            Held in cash
          </span>
          <div className="text-2xl font-bold font-mono text-slate-900 mt-0.5">{fmt1(cash)}%</div>
          <span className="text-[10px] text-slate-500 mt-0.5 block">Deliberate, not a shortfall</span>
        </div>

        <div
          className="p-3 bg-slate-50 border border-slate-200 rounded-xl"
          title="What the volatility target permitted, measured on the equal-risk weights before any cap was applied."
        >
          <span className="text-[10px] font-semibold uppercase text-slate-600 tracking-wider block">
            Target allowed
          </span>
          <div className="text-2xl font-bold font-mono text-slate-900 mt-0.5">
            {fmt1(sizing.deploymentPct)}%
          </div>
          <span className="text-[10px] text-slate-500 mt-0.5 block">Before caps</span>
        </div>

        <div className="p-3 bg-slate-50 border border-slate-200 rounded-xl">
          <span className="text-[10px] font-semibold uppercase text-slate-600 tracking-wider block">
            Portfolio volatility
          </span>
          <div className="text-2xl font-bold font-mono text-slate-900 mt-0.5">
            {sizing.portfolioVolatilityPct === null ? '—' : `${fmt1(sizing.portfolioVolatilityPct)}%`}
          </div>
          <span className="text-[10px] text-slate-500 mt-0.5 block">
            Target {fmt1(sizing.targetVolatilityPct)}%
          </span>
        </div>
      </div>

      <div className="bg-slate-50 rounded-xl p-3 border border-slate-100 space-y-1">
        <span className="text-[11px] font-semibold text-slate-700 flex items-center gap-1">
          <Info className="w-3.5 h-3.5 text-blue-600" />
          Why the weights do not add up to 100
        </span>
        <p className="text-xs text-slate-600 leading-relaxed">
          Cash is the volatility target doing its job. Fewer holdings, or more correlated ones,
          raise the portfolio&rsquo;s volatility, which lowers how much is put to work. The gap
          between <strong>{fmt1(sizing.deploymentPct)}%</strong> and{' '}
          <strong>{fmt1(invested)}%</strong> is what the per-position and sector caps removed on
          top of that.
        </p>
        <p className="text-[11px] text-slate-500">
          Stops are set in advance at {fmt1(round1(STOP_ATR_MULTIPLE))}x ATR. That multiple is our
          own and matches no figure in the sources; see knowledge/rulebook.md before treating a
          stop as a protection the books endorse.
        </p>
        <p className="text-[10px] text-slate-400 font-mono">Volatility basis: {sizing.basis}</p>
      </div>
    </div>
  );
};
