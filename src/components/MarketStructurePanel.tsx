import { useMemo, useState } from 'react';
import { computeMarketStructure, PriceSeries } from '../utils/screenerEngine';
import { downloadText } from '../utils/download';
import { OrderFlowRequirements } from './OrderFlowRequirements';

const price = (value: number | null) => value === null ? '—' : value.toFixed(2);

/** User-selected dates are explicit; this panel never changes a ranking. */
export function MarketStructurePanel({ series, ticker }: { series: PriceSeries | null; ticker: string }) {
  const [anchor, setAnchor] = useState('');
  const [asOf, setAsOf] = useState('');
  const result = useMemo(() => series
    ? computeMarketStructure(series, anchor || null, asOf || null)
    : null, [series, anchor, asOf]);
  const profile = result?.volumeProfile;
  const largest = profile?.bins.reduce((m, b) => Math.max(m, b.volume), 0) ?? 0;

  return (
    <section className="p-3 border border-slate-200 rounded-xl space-y-3" aria-label="Price and volume research">
      <div>
        <h4 className="text-sm font-semibold text-slate-900">Price &amp; volume research</h4>
        <p className="text-[11px] text-slate-500 mt-1">
          Daily-bar diagnostics. These do not change the stock ranking or generate trade orders.
        </p>
      </div>
      {!series ? <p className="text-xs text-slate-600">Upload daily High, Low, Close and Volume to use these tools.</p> : <>
        <div className="grid grid-cols-2 gap-2 text-xs">
          <label className="space-y-1">
            <span className="block text-slate-600">Anchor date</span>
            <input type="date" aria-label="Anchor date" value={anchor}
              min={series.dates[0]} max={asOf || series.dates.at(-1)}
              onChange={e => setAnchor(e.target.value)} className="w-full border border-slate-200 rounded p-1.5" />
          </label>
          <label className="space-y-1">
            <span className="block text-slate-600">As-of date</span>
            <input type="date" aria-label="As-of date" value={asOf}
              min={series.dates[0]} max={series.dates.at(-1)}
              onChange={e => setAsOf(e.target.value)} className="w-full border border-slate-200 rounded p-1.5" />
          </label>
        </div>
        <p className="text-[11px] text-slate-500">
          Blank dates use the latest loaded session and an anchor at the first of its last 20 bars.
          Choose an anchor session in the file; weekends are not moved automatically.
        </p>
        {result?.error ? <p role="alert" className="text-xs text-amber-800">{result.error}</p> : result && <>
          <p className="text-[11px] text-slate-500">As of {result.asOf} · Anchor {result.anchorDate ?? 'unavailable'}</p>
          <dl className="text-xs space-y-2">
            <div className="bg-slate-50 rounded p-2">
              <dt className="font-semibold">Anchored VWAP · daily approximation</dt>
              <dd data-testid="anchored-vwap" className="font-mono mt-1">{price(result.anchoredVwap.value)}
                {result.anchoredVwap.distancePct !== null && ` · Close vs VWAP ${price(result.anchoredVwap.distancePct)}%`}</dd>
              <dd className="text-slate-500 mt-1">{result.anchoredVwap.reason ??
                `${result.anchoredVwap.bars} bars; each bar uses (High + Low + Close) / 3 weighted by volume.`}</dd>
            </div>
            <div className="bg-slate-50 rounded p-2">
              <dt className="font-semibold">Liquidity sweep candidate · prior 20 bars</dt>
              <dd data-testid="sweep-candidate" className="mt-1">{result.sweep.reason ?? (
                result.sweep.side === 'sell-side' ? 'Prior low breached, then close reclaimed it.'
                  : result.sweep.side === 'buy-side' ? 'Prior high breached, then close fell back below it.'
                  : result.sweep.side === 'both' ? 'Both sides breached and reclaimed; intraday sequence unknown.'
                  : 'No sweep pattern on the latest bar.'
              )}</dd>
              {result.sweep.referenceLow !== null && <dd className="text-slate-500 mt-1">
                Prior low {price(result.sweep.referenceLow)} · Prior high {price(result.sweep.referenceHigh)}
              </dd>}
              <dd className="text-slate-500 mt-1">Price pattern only; actual stop orders and traded liquidity are not observed.</dd>
            </div>
            <div className="bg-slate-50 rounded p-2">
              <dt className="font-semibold">Wyckoff context · heuristic</dt>
              <dd data-testid="wyckoff-context" className="mt-1">{result.wyckoff.context}</dd>
              <dd className="text-slate-500 mt-1">{result.wyckoff.reason}</dd>
            </div>
          </dl>
          <div className="bg-slate-50 rounded p-2 text-xs space-y-1">
            <h5 className="font-semibold">Auction market context · daily approximation</h5>
            <p>{result.auctionContext.position}</p>
            <p>{result.auctionContext.reason}</p>
            {result.auctionContext.referenceEnd && <p>Prior {result.lookback} bars: {result.auctionContext.referenceStart}–{result.auctionContext.referenceEnd}.
              Estimated value area {price(result.auctionContext.valueAreaLow)}–{price(result.auctionContext.valueAreaHigh)}; POC {price(result.auctionContext.poc)}.</p>}
            <p className="text-slate-500">Excludes the current bar. Independent of the manual VWAP anchor; this is not a TPO Market Profile.</p>
          </div>
          <div className="space-y-2 text-xs">
            <h5 className="font-semibold">Volume profile · daily-bar estimate</h5>
            {profile?.reason ? <p className="text-slate-500">{profile.reason}</p> : profile && <>
              <p>POC {price(profile.poc)} · 70% value area {price(profile.valueAreaLow)}–{price(profile.valueAreaHigh)}</p>
              <svg viewBox="0 0 360 210" role="img" aria-label="Estimated volume by price" className="w-full bg-slate-50 rounded">
                {[...profile.bins].reverse().map((b, i) => {
                  const row = 190 / profile.bins.length;
                  return <g key={i}>
                    <text x="2" y={10 + (i + 0.7) * row} fontSize="8" fill="#475569">{price(b.low / 2 + b.high / 2)}</text>
                    <rect x="70" y={10 + i * row} width={largest > 0 ? b.volume / largest * 280 : 0}
                      height={Math.max(1, row - 1)} fill="#64748b">
                      <title>{price(b.low)}–{price(b.high)}: {b.volume.toFixed(0)} estimated volume</title>
                    </rect>
                  </g>;
                })}
              </svg>
            </>}
            <p className="text-slate-500">Volume is spread uniformly across each daily high–low range. POC and value area are estimates, not observed volume at each price.</p>
          </div>
          <button type="button" onClick={() => downloadText(JSON.stringify({ ticker, ...result }, null, 2),
            `price_volume_${ticker}_${result.asOf}.json`, 'application/json')}
            className="text-xs font-semibold text-blue-700 hover:underline">Download research values</button>
        </>}
      </>}
      <p className="text-xs text-slate-600"><strong>Order flow: unavailable.</strong> Requires aggressor-side trades for delta and order-book events for depth; daily OHLCV cannot supply them.</p>
      <OrderFlowRequirements />
      <p className="text-[11px] text-slate-500">Levels use the uploaded price basis. Adjusted prices, corporate actions or unmatched volume adjustments can distort historical levels. Use consistently adjusted data and completed daily bars.</p>
    </section>
  );
}
