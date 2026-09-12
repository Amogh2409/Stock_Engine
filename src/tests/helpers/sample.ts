import { NIFTY100_FALLBACK_SYMBOLS } from '../../data/nifty100Snapshot';
import { SAMPLE_SCREENER_CSV_STRING } from '../../data/sampleScreenerData';
import { parseCsv } from '../../utils/screenerEngine';

/**
 * How the bundled sample splits across the pinned Nifty 100, derived from the
 * two files rather than hard-coded: the index is rebalanced and the sample can
 * change, and neither should break unrelated tests.
 */
export function sampleUniverseSplit(): { total: number; inIndex: number; outside: number } {
  const index = new Set<string>(NIFTY100_FALLBACK_SYMBOLS);
  const tickers = parseCsv(SAMPLE_SCREENER_CSV_STRING).map((row) =>
    String(row['NSE code'] ?? '').trim().toUpperCase(),
  );
  const inIndex = tickers.filter((ticker) => index.has(ticker)).length;
  return { total: tickers.length, inIndex, outside: tickers.length - inIndex };
}
