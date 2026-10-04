/** Daily uploads cannot populate these tools. Missing evidence never earns points. */
export function OrderFlowRequirements() {
  const tools = [
    ['Liquidity heatmap', 'Timestamped bid/ask depth snapshots or order-book events. A stock evidence heatmap is a different view.'],
    ['Time & Sales', 'Individual executed trades with exchange timestamps, price, quantity and trade IDs.'],
    ['Footprint, delta & order flow', 'Trades classified by aggressor side, grouped by price and time. Candle colour cannot identify the aggressor.'],
    ['Session VWAP', 'Intraday prices and volume with an exchange session calendar; trade-level VWAP needs executed trades.'],
    ['Gamma exposure', 'Timestamped options gamma, open interest, strike, expiry, lot size and underlying price. Signed dealer exposure also needs position evidence or disclosed assumptions.'],
    ['Market Profile / TPO', 'Intraday price observations, a tick size and session/time-block definitions. Volume profile is not time at price.'],
  ];
  return <details className="border border-slate-200 rounded-lg p-3 text-xs">
    <summary className="font-semibold cursor-pointer">Order-flow tools · additional data needed</summary>
    <p className="text-slate-600 my-2">Using Angel One? The local SmartAPI collector can export a daily prices.csv for Upload prices.
      Intraday candles, five-level depth snapshots and option Greeks are saved separately; they do not yet feed this view.</p>
    <p className="text-slate-600 my-2">These tools are unavailable with the current daily uploads. They do not influence review status or scores.</p>
    <dl className="space-y-2">{tools.map(([name, need]) => <div key={name}>
      <dt className="font-semibold">{name} · unavailable</dt><dd className="text-slate-600">{need}</dd>
    </div>)}</dl>
  </details>;
}
