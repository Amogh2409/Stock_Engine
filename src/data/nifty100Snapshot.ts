// GENERATED FILE - DO NOT EDIT BY HAND.
// Source of truth: data/nifty100_snapshot.json
// Regenerate with: npm run build:python
//
// Single shared snapshot of the Nifty 100 constituent list. Both the browser
// engine and the generated Colab notebook derive their fallback universe from
// this file, so the two can never drift apart.
export interface Nifty100Provenance {
  source_url: string;
  retrieved_at_utc: string;
  as_of_date: string;
  sha256_of_source_csv: string;
  count: number;
}

export const NIFTY100_PROVENANCE: Nifty100Provenance = {
  source_url: "https://nsearchives.nseindia.com/content/indices/ind_nifty100list.csv",
  retrieved_at_utc: "2026-09-10T19:09:00Z",
  as_of_date: "2026-09-10",
  sha256_of_source_csv: "1a40e33a0febf458986a178bc76f7b0051f163718f2a8bc11a726ba70a39c0a9",
  count: 100,
};

/**
 * Cached snapshot, NOT a live feed. It was current as of
 * NIFTY100_PROVENANCE.as_of_date; the index is rebalanced periodically, so
 * always describe this list as "cached (as of <as_of_date>)" in the UI.
 */
export const NIFTY100_FALLBACK_SYMBOLS: readonly string[] = [
  'ABB', 'ADANIENSOL', 'ADANIENT', 'ADANIGREEN', 'ADANIPORTS', 'ADANIPOWER', 'AMBUJACEM', 'APOLLOHOSP',
  'ASIANPAINT', 'AXISBANK', 'BAJAJ-AUTO', 'BAJAJFINSV', 'BAJAJHLDNG', 'BAJFINANCE', 'BANKBARODA', 'BEL',
  'BHARTIARTL', 'BOSCHLTD', 'BPCL', 'BRITANNIA', 'CANBK', 'CGPOWER', 'CHOLAFIN', 'CIPLA',
  'COALINDIA', 'CUMMINSIND', 'DIVISLAB', 'DLF', 'DMART', 'DRREDDY', 'EICHERMOT', 'ENRIN',
  'ETERNAL', 'GAIL', 'GODREJCP', 'GRASIM', 'HAL', 'HCLTECH', 'HDFCAMC', 'HDFCBANK',
  'HDFCLIFE', 'HINDALCO', 'HINDUNILVR', 'HINDZINC', 'HYUNDAI', 'ICICIBANK', 'INDHOTEL', 'INDIGO',
  'INFY', 'IOC', 'IRFC', 'ITC', 'JINDALSTEL', 'JIOFIN', 'JSWSTEEL', 'KOTAKBANK',
  'LODHA', 'LT', 'LTM', 'M&M', 'MARUTI', 'MAXHEALTH', 'MAZDOCK', 'MOTHERSON',
  'MUTHOOTFIN', 'NESTLEIND', 'NTPC', 'ONGC', 'PFC', 'PIDILITIND', 'PNB', 'POWERGRID',
  'RECLTD', 'RELIANCE', 'SBILIFE', 'SBIN', 'SHREECEM', 'SHRIRAMFIN', 'SIEMENS', 'SOLARINDS',
  'SUNPHARMA', 'TATACAP', 'TATACONSUM', 'TATAPOWER', 'TATASTEEL', 'TCS', 'TECHM', 'TITAN',
  'TMCV', 'TMPV', 'TORNTPHARM', 'TRENT', 'TVSMOTOR', 'ULTRACEMCO', 'UNIONBANK', 'UNITDSPR',
  'VBL', 'VEDL', 'WIPRO', 'ZYDUSLIFE',
];
