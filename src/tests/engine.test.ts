/**
 * TypeScript engine unit tests. Completely offline: no subprocess, no network.
 * Cross-engine agreement is asserted separately in parity.test.ts.
 */
import { describe, expect, it } from 'vitest';

import snapshotJson from '../../data/nifty100_snapshot.json';
import { NIFTY100_FALLBACK_SYMBOLS, NIFTY100_PROVENANCE } from '../data/nifty100Snapshot';
import { SAMPLE_SCREENER_CSV_STRING } from '../data/sampleScreenerData';
import { sampleUniverseSplit } from './helpers/sample';
import { CleanedStock } from '../types';
import {
  BENCHMARK_SYMBOL,
  buildConfigDocument,
  compareCodePoints,
  describePriceHistory,
  normalizeHeader,
  parseCsv,
  parseSavedRun,
  validSnapshotEntries,
  parsePriceHistoryCsv,
  technicalsFromHistory,
  validateConfigDocument,
  cleanNumeric,
  clamp,
  computeRankingChanges,
  computeTechnicalIndicators,
  calculateTechnicalScore,
  DEFAULT_APP_CONFIG,
  DEFAULT_SCREENING_CONFIG,
  dedupeStocks,
  detectColumnMapping,
  emptyTechnicals,
  escapeCsvCell,
  escapeHtml,
  evaluateStock,
  fmt1,
  generateHtmlReport,
  generateRankingChangesCsv,
  generateWatchlistCsv,
  parseStrictDecimal,
  processScreenerPipeline,
  round1,
  sectorMedians,
  sortByScoreThenTicker,
  validateCustomFilters,
} from '../utils/screenerEngine';

function makeStock(overrides: Partial<CleanedStock> = {}): CleanedStock {
  return {
    id: 'test', name: 'Test Co', ticker: 'TEST', bseCode: null,
    sector: 'Computers - Software', currentPrice: 100, marketCap: 10000,
    salesGrowth: 20, profitGrowth: 20, roce: 25, roe: 25, debtToEquity: 0,
    interestCoverage: 10, operatingCashFlow: 100, promoterHolding: 60,
    promoterPledge: 0, peRatio: 15, pbRatio: 2, dividendYield: 1,
    sales: null, returnOnAssets: null, grossNpa: null, netNpa: null,
    capitalAdequacy: null, casa: null, financingMargin: null,
    technicals: emptyTechnicals(), rawRow: {}, ...overrides,
  };
}

const APP = { ...DEFAULT_APP_CONFIG, minimum_total_score: 0, enable_technical_confirmation: false };
const prices = (n: number) => Array.from({ length: n }, (_, i) => 100 + i * 0.5);

describe('Unit-aware number parsing', () => {
  it('resolves crore and lakh against the crore contract', () => {
    expect(cleanNumeric('1 CRORE', 'crore')).toBe(1);
    expect(cleanNumeric('1 CR', 'crore')).toBe(1);
    expect(cleanNumeric('100 LAKH', 'crore')).toBe(1);
    expect(cleanNumeric('10 LAKH', 'crore')).toBeCloseTo(0.1, 12);
    expect(cleanNumeric('1,500.50', 'crore')).toBe(1500.5);
  });

  it('rejects monetary suffixes on percentages and ratios', () => {
    expect(cleanNumeric('15 CR', 'percent')).toBeNull();
    expect(cleanNumeric('15 LAKH', 'percent')).toBeNull();
    expect(cleanNumeric('1 CR', 'ratio')).toBeNull();
    expect(cleanNumeric('1 LAKH', 'ratio')).toBeNull();
    expect(cleanNumeric('1500 CR', 'price')).toBeNull();
  });

  it('rejects a percent sign on ratios and prices but accepts it on percentages', () => {
    expect(cleanNumeric('0.5%', 'ratio')).toBeNull();
    expect(cleanNumeric('10%', 'price')).toBeNull();
    expect(cleanNumeric('15.5%', 'percent')).toBe(15.5);
  });

  it('strips currency symbols, commas and quotes', () => {
    expect(cleanNumeric('₹ 1,500.50', 'price')).toBe(1500.5);
    expect(cleanNumeric('"1,000.50"', 'ratio')).toBe(1000.5);
    expect(cleanNumeric('1 500', 'ratio')).toBe(1500);
  });

  it('rejects malformed input rather than guessing', () => {
    for (const bad of ['1500abc', '', 'N/A', '--', '.', '-']) {
      expect(cleanNumeric(bad, 'ratio'), bad).toBeNull();
    }
    expect(cleanNumeric(Number.POSITIVE_INFINITY, 'ratio')).toBeNull();
    expect(cleanNumeric(Number.NaN, 'ratio')).toBeNull();
    expect(cleanNumeric(true, 'ratio')).toBeNull();
  });

  it('parseStrictDecimal rejects hex, underscores and non-finite values', () => {
    expect(parseStrictDecimal('0x10')).toBeNull();
    expect(parseStrictDecimal('1_0')).toBeNull();
    expect(parseStrictDecimal('Infinity')).toBeNull();
    expect(parseStrictDecimal(' 12 ')).toBe(12);
    expect(parseStrictDecimal(true)).toBeNull();
  });
});

describe('Canonical rounding', () => {
  it('rounds half-up at one decimal', () => {
    expect(round1(74.55)).toBe(74.6);
    expect(round1(81.45)).toBe(81.5);
    expect(round1(0.05)).toBe(0.1);
    expect(round1(74.53)).toBe(74.5);
    expect(round1(100)).toBe(100);
    expect(round1(null)).toBeNull();
  });

  it('formats to a fixed single decimal', () => {
    expect(fmt1(80)).toBe('80.0');
    expect(fmt1(80.44)).toBe('80.4');
    expect(fmt1(null)).toBe('');
  });

  it('clamps within bounds', () => {
    expect(clamp(-5, 0, 10)).toBe(0);
    expect(clamp(50, 0, 10)).toBe(10);
    expect(clamp(5, 0, 10)).toBe(5);
  });
});

describe('Identifier-safe column resolution', () => {
  it('keeps NSE and BSE columns distinct', () => {
    const m = detectColumnMapping(['Name', 'NSE Code', 'BSE Code']);
    expect(m.ticker).toBe('NSE Code');
    expect(m.bseCode).toBe('BSE Code');
  });

  it('shares a lone BSE column as both ticker and bseCode', () => {
    const m = detectColumnMapping(['Name', 'BSE Code']);
    expect(m.ticker).toBe('BSE Code');
    expect(m.bseCode).toBe('BSE Code');
  });

  it('maps a lone NSE column with no bseCode', () => {
    const m = detectColumnMapping(['Name', 'NSE Code']);
    expect(m.ticker).toBe('NSE Code');
    expect(m.bseCode).toBeUndefined();
  });

  it('is independent of header order', () => {
    expect(detectColumnMapping(['Price to Earning', 'BSE Code', 'NSE Code', 'Name'])).toEqual(
      detectColumnMapping(['Name', 'NSE Code', 'BSE Code', 'Price to Earning']),
    );
  });

  it('does not let a loose price alias steal the P/E column', () => {
    const m = detectColumnMapping(['Name', 'Price to Earning', 'Price to book value']);
    expect(m.peRatio).toBe('Price to Earning');
    expect(m.pbRatio).toBe('Price to book value');
    expect(m.currentPrice).toBeUndefined();
  });

  it('still prefers a real price column when one exists', () => {
    const m = detectColumnMapping(['Name', 'Current Price', 'Price to Earning']);
    expect(m.currentPrice).toBe('Current Price');
    expect(m.peRatio).toBe('Price to Earning');
  });

  it('does not map "Operating cash flow" to P/E', () => {
    const m = detectColumnMapping(['Ticker', 'Operating cash flow', 'ROCE', 'ROE']);
    expect(m.peRatio).toBeUndefined();
    expect(m.operatingCashFlow).toBe('Operating cash flow');
  });

  it('ignores unrelated headers that merely contain short alias letters', () => {
    const m = detectColumnMapping([
      'Ticker', 'Hope', 'Cupboard', 'Shoe', 'Procedure', 'Pocfield',
      'Hide', 'Micro', 'Rump/ear', 'Up/back', 'Od/even', 'Camp', 'Macform',
    ]);
    for (const field of ['peRatio', 'pbRatio', 'roe', 'roce', 'operatingCashFlow', 'debtToEquity', 'interestCoverage', 'currentPrice']) {
      expect(m[field], field).toBeUndefined();
    }
  });
});

describe('Deduplication', () => {
  it('removes duplicates by ticker, BSE code and normalised name', () => {
    const { unique, duplicatesRemoved } = dedupeStocks([
      makeStock({ ticker: 'A', bseCode: '1', name: 'Alpha' }),
      makeStock({ ticker: 'A', bseCode: '9', name: 'Other' }),
      makeStock({ ticker: 'B', bseCode: '1', name: 'Beta' }),
      makeStock({ ticker: 'C', bseCode: '3', name: 'Alpha' }),
      makeStock({ ticker: 'D', bseCode: '4', name: 'Delta' }),
    ]);
    expect(unique.map((s) => s.ticker)).toEqual(['A', 'D']);
    expect(duplicatesRemoved).toBe(3);
  });

  it('does not collapse rows whose name is Unknown', () => {
    const { unique } = dedupeStocks([
      makeStock({ ticker: 'A', bseCode: null, name: 'Unknown' }),
      makeStock({ ticker: 'B', bseCode: null, name: 'Unknown' }),
    ]);
    expect(unique).toHaveLength(2);
  });
});

describe('Technical history semantics', () => {
  it('requires 252 sessions for a 52-week high', () => {
    for (const [n, expected] of [[20, false], [199, false], [200, false], [251, false], [252, true], [300, true]] as [number, boolean][]) {
      const tech = computeTechnicalIndicators(prices(n));
      expect(tech.available.high52Week, `n=${n}`).toBe(expected);
      if (expected) expect(tech.high52Week, `n=${n}`).not.toBeNull();
      else {
        expect(tech.high52Week, `n=${n}`).toBeNull();
        expect(tech.distFrom52WHighPct, `n=${n}`).toBeNull();
      }
    }
  });

  it('computes the 52-week high from the last 252 sessions only', () => {
    const series = Array.from({ length: 300 }, () => 100);
    series[10] = 9999; // a spike 290 sessions ago must not count
    const tech = computeTechnicalIndicators(series);
    expect(tech.available.high52Week).toBe(true);
    expect(tech.high52Week).toBe(100);
  });

  it('awards no 52-week-high points when it is unavailable', () => {
    const result = calculateTechnicalScore(computeTechnicalIndicators(prices(251)), true);
    expect(result.breakdown.some((b) => b.includes('52W high unavailable'))).toBe(true);
    expect(result.score).not.toBeNull();
  });

  it('reports availability explicitly at each level', () => {
    expect(computeTechnicalIndicators([]).data_status).toBe('UNAVAILABLE');
    expect(computeTechnicalIndicators(prices(60)).data_status).toBe('PARTIAL');
    const bench = Array.from({ length: 300 }, (_, i) => 50 + i * 0.1);
    expect(computeTechnicalIndicators(prices(300), bench).data_status).toBe('COMPLETE');
  });

  it('returns a null score when technical confirmation is disabled', () => {
    const result = calculateTechnicalScore(computeTechnicalIndicators(prices(300)), false);
    expect(result.score).toBeNull();
    expect(result.breakdown).toEqual(['Technical screening disabled']);
  });

  it('gives each chart indicator its own minimum history', () => {
    // 30 rising sessions: past RSI's 15 and Bollinger's 20, short of MACD's 34
    // and of the 64 a three-month rate of change needs.
    const tech = computeTechnicalIndicators(Array.from({ length: 30 }, (_, i) => 100 + i * 0.3));
    expect(tech.rsi14).not.toBeNull();
    expect(tech.bollingerPercentB).not.toBeNull();
    expect(tech.roc1M).not.toBeNull();
    expect(tech.drawdownFromPeakPct).not.toBeNull();
    expect(tech.macdLine).toBeNull();
    expect(tech.roc3M).toBeNull();
    expect(tech.roc12M).toBeNull();
    // No highs or lows were supplied, so the range indicators stay absent
    // rather than substituting the close for them.
    expect(tech.atr14).toBeNull();
    expect(tech.adx14).toBeNull();
  });

  it('computes range indicators only from real highs and lows', () => {
    const closes = Array.from({ length: 120 }, (_, i) => 100 + i * 0.4);
    const highs = closes.map((c) => c + 1.5);
    const lows = closes.map((c) => c - 1.5);
    const withRange = computeTechnicalIndicators(closes, null, null, 't', null, highs, lows);
    expect(withRange.atr14).not.toBeNull();
    expect(withRange.adx14).not.toBeNull();
    expect(withRange.atrPct).not.toBeNull();
    // One missing high inside the window disables them, rather than letting a
    // single gap pass as a real range.
    const gappedHighs: (number | null)[] = [...highs];
    gappedHighs[gappedHighs.length - 3] = null;
    const gapped = computeTechnicalIndicators(closes, null, null, 't', null, gappedHighs, lows);
    expect(gapped.atr14).toBeNull();
    expect(gapped.adx14).toBeNull();
  });

  it('treats a flat series as undefined rather than as maximum strength', () => {
    expect(computeTechnicalIndicators(Array.from({ length: 60 }, (_, i) => 100 + i)).rsi14).toBe(100);
    const flat = Array.from({ length: 100 }, () => 100);
    const flatTech = computeTechnicalIndicators(flat, null, null, 't', null, flat, flat);
    expect(flatTech.rsi14).toBe(50);
    expect(flatTech.bollingerPercentB).toBeNull();
    expect(flatTech.adx14).toBeNull();
  });

  it('reads the direction of volume as OBV pressure', () => {
    const volumes = Array.from({ length: 30 }, () => 1000);
    expect(
      computeTechnicalIndicators(Array.from({ length: 30 }, (_, i) => 100 + i), null, volumes).obvPressure20D,
    ).toBe(100);
    expect(
      computeTechnicalIndicators(Array.from({ length: 30 }, (_, i) => 100 - i), null, volumes).obvPressure20D,
    ).toBe(-100);
  });

  it('merges technical-unavailable warnings into the displayed flags', () => {
    const ev = evaluateStock(makeStock(), DEFAULT_SCREENING_CONFIG, {
      ...APP, enable_technical_confirmation: true,
    });
    expect(ev.warningFlags).toContain('Technical Data Missing');
  });
});

describe('Screening and scoring', () => {
  it('produces the arithmetic score for fully specified inputs', () => {
    // Valuation is judged against the file's own sectors, so a stock evaluated
    // on its own has no yardstick and earns nothing for valuation:
    // 18.75 quality + 16.7 growth + 20 balance + 0 valuation + 9 governance.
    const ev = evaluateStock(makeStock(), DEFAULT_SCREENING_CONFIG, APP);
    expect(ev.score).toBe(64.4);
    expect(ev.passed).toBe(true);
    expect(ev.coveragePct).toBe(100);
    expect(ev.categoryScores.valuation.score).toBe(0);
    expect(ev.scoreLines.some((line) => line.includes('no P/E yardstick'))).toBe(true);
  });

  it('scores valuation against the sector median when the file supplies one', () => {
    // Five identical companies make their industry its own median, so this
    // stock sits exactly on the yardstick and earns half the valuation marks.
    const peers = [0, 1, 2, 3, 4].map((i) => makeStock({ ticker: `P${i}` }));
    const medians = sectorMedians(peers);
    const ev = evaluateStock(makeStock(), DEFAULT_SCREENING_CONFIG, APP, medians);
    expect(ev.categoryScores.valuation.score).toBe(7.5);
    expect(ev.score).toBe(71.9);
    expect(ev.scoreLines.some((line) => line.includes('Computers - Software median'))).toBe(true);
    // Half the sector's P/E earns full marks; half again above it earns none.
    const cheap = evaluateStock(
      makeStock({ peRatio: 7.5, pbRatio: 1 }), DEFAULT_SCREENING_CONFIG, APP, medians,
    );
    const dear = evaluateStock(
      makeStock({ peRatio: 30, pbRatio: 4 }), DEFAULT_SCREENING_CONFIG, APP, medians,
    );
    expect(cheap.categoryScores.valuation.score).toBe(15);
    expect(dear.categoryScores.valuation.score).toBe(0);
  });

  it('does not scale a sparse company upward', () => {
    const ev = evaluateStock(
      makeStock({
        marketCap: null, salesGrowth: null, profitGrowth: null, roe: null,
        debtToEquity: null, interestCoverage: null, operatingCashFlow: null,
        promoterHolding: null, promoterPledge: null, peRatio: null,
        pbRatio: null, dividendYield: null,
      }),
      DEFAULT_SCREENING_CONFIG,
      APP,
    );
    expect(ev.passed).toBe(false);
    expect(ev.score).toBeLessThanOrEqual(15);
    expect(ev.rejectionReasons.some((r) => r.includes('Insufficient Data'))).toBe(true);
  });

  it('keeps scores inside bounds for extreme inputs', () => {
    const huge = makeStock({
      roce: 1e9, roe: 1e9, salesGrowth: 1e9, profitGrowth: 1e9,
      interestCoverage: 1e9, promoterHolding: 1e9,
    });
    expect(evaluateStock(huge, DEFAULT_SCREENING_CONFIG, APP).score).toBeLessThanOrEqual(100);
    const negative = makeStock({
      roce: -1e9, roe: -1e9, salesGrowth: -1e9, profitGrowth: -1e9,
      debtToEquity: -1e9, interestCoverage: -1e9, promoterHolding: -1e9, promoterPledge: -1e9,
    });
    expect(evaluateStock(negative, DEFAULT_SCREENING_CONFIG, APP).score).toBeGreaterThanOrEqual(0);
  });

  it('enforces P/E and P/B ceilings only under the strict screen', () => {
    const stock = makeStock({ peRatio: 1000, pbRatio: 1000 });
    // By default an expensive company is ranked low, not thrown away.
    const relaxed = evaluateStock(stock, DEFAULT_SCREENING_CONFIG, APP);
    expect(relaxed.rejectionReasons).not.toContain('P/E above maximum');
    const strict = evaluateStock(stock, DEFAULT_SCREENING_CONFIG, { ...APP, strict_screen: true });
    expect(strict.rejectionReasons).toContain('P/E above maximum');
    expect(strict.rejectionReasons).toContain('P/B above maximum');
    // The strict screen filters; it does not change what a company scores.
    expect(strict.score).toBe(relaxed.score);
  });

  it('routes a financial company to the financial model instead of excluding it', () => {
    const ev = evaluateStock(makeStock({ sector: 'Banking' }), DEFAULT_SCREENING_CONFIG, APP);
    expect(ev.scoringModel).toBe('financial');
    // Without the bank columns it names exactly what is missing, rather than
    // being scored on ratios that do not describe a lender.
    expect(ev.notScored).toBe(
      'Not scored: missing bank metrics (Return on assets, Gross NPA %, Net NPA %, Capital adequacy ratio)',
    );

    const scored = evaluateStock(
      makeStock({
        sector: 'Banking', returnOnAssets: 1.8, grossNpa: 2.1, netNpa: 0.5,
        capitalAdequacy: 16, operatingCashFlow: -900,
      }),
      DEFAULT_SCREENING_CONFIG,
      APP,
    );
    expect(scored.notScored).toBeNull();
    // A negative operating cash flow is ordinary for a growing loan book, so
    // it must not be a red flag here.
    expect(scored.redFlags).toEqual([]);
    expect(scored.score).toBeGreaterThan(0);
    expect(scored.scoreLines.some((line) => line.startsWith('Return on assets'))).toBe(true);
  });

  it('raises all three fundamental warning flags', () => {
    const ev = evaluateStock(
      makeStock({ dividendYield: 0, marketCap: 400, promoterPledge: 5 }),
      DEFAULT_SCREENING_CONFIG,
      APP,
    );
    expect(ev.warningFlags).toContain('Low Dividend Yield');
    expect(ev.warningFlags).toContain('Micro Cap');
    expect(ev.warningFlags).toContain('Promoter Pledged');
  });

  it('builds a factual, non-empty explanation', () => {
    const ev = evaluateStock(makeStock(), DEFAULT_SCREENING_CONFIG, APP);
    expect(ev.explanation).toContain('Total fundamental score 64.4/100');
    expect(ev.explanation).toContain('Strongest factor');
    expect(ev.explanation).toContain('ROCE 25.0%');
    expect(ev.explanation).toContain('Passed every configured screening rule');

    // Weak returns cost points rather than rejecting, so the rejected case
    // needs a hard red flag.
    const rejected = evaluateStock(makeStock({ promoterPledge: 50 }), DEFAULT_SCREENING_CONFIG, APP);
    expect(rejected.explanation).toContain('Rejected because');
    expect(rejected.explanation.length).toBeGreaterThan(60);
  });
});

describe('Ordering and pipeline', () => {
  it('sorts by score descending then ticker ascending', () => {
    // promoterHolding 75 saturates governance (5/5) where 60 gives 4/5, so MMM
    // scores 100 and the other two tie at 99 and break alphabetically.
    const items = ['ZZZ', 'AAA', 'MMM'].map((t) =>
      evaluateStock(
        makeStock({ ticker: t, promoterHolding: t === 'MMM' ? 75 : 60 }),
        DEFAULT_SCREENING_CONFIG,
        APP,
      ),
    );
    expect(sortByScoreThenTicker(items).map((e) => e.stock.ticker)).toEqual(['MMM', 'AAA', 'ZZZ']);
  });

  it('assigns contiguous 1-based ranks and honours top_n', () => {
    const csv = [
      'Name,NSE Code,Market Capitalization,Sales growth 3Years,Profit growth 3Years,ROCE,Return on equity,Debt to equity,Interest Coverage,Cash flow from operations,Promoter holding,Pledged percentage,Price to Earning,Price to book value,Dividend yield',
      'A Ltd,AAA,5000,20%,20%,25%,25%,0.1,10,500,60%,0%,15,2,1%',
      'B Ltd,BBB,5000,20%,20%,25%,25%,0.1,10,500,60%,0%,15,2,1%',
      'C Ltd,CCC,5000,20%,20%,25%,25%,0.1,10,500,60%,0%,15,2,1%',
    ].join('\n');
    const result = processScreenerPipeline(
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      (require('papaparse') as any).parse(csv, { header: true, skipEmptyLines: true }).data,
      { ...APP, universe_mode: 'custom', custom_symbols: [], top_n: 2 },
      DEFAULT_SCREENING_CONFIG,
    );
    expect(result.watchlist).toHaveLength(2);
    expect(result.watchlist.map((w) => w.rank)).toEqual([1, 2]);
    expect(result.watchlist.map((w) => w.stock.ticker)).toEqual(['AAA', 'BBB']);
  });

  it('rejects an invalid custom filter without screening anything', () => {
    const result = processScreenerPipeline(
      [{ Name: 'X', 'NSE Code': 'AAA' }],
      { ...APP, custom_filters: [{ field: 'os.system', operator: '>', value: 1 }] },
      DEFAULT_SCREENING_CONFIG,
    );
    expect(result.inspectionReport.configErrors.length).toBeGreaterThan(0);
    expect(result.evaluations).toHaveLength(0);
  });
});

describe('Custom filter validation', () => {
  it('accepts only whitelisted fields, operators and finite numbers', () => {
    expect(validateCustomFilters([{ field: 'roce', operator: '>', value: '25' }])).toEqual([]);
    expect(validateCustomFilters([{ field: 'roce', operator: '>', value: 'drop table' }])).toHaveLength(1);
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    expect(validateCustomFilters([{ field: '__proto__', operator: '>', value: 1 } as any])).toHaveLength(1);
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    expect(validateCustomFilters([{ field: 'roce', operator: 'exec' as any, value: 1 }])).toHaveLength(1);
  });
});

describe('CSV export safety', () => {
  it('guards all four dangerous leading characters', () => {
    expect(escapeCsvCell('=cmd|')).toBe("'=cmd|");
    expect(escapeCsvCell('+1+1')).toBe("'+1+1");
    expect(escapeCsvCell('-500')).toBe("'-500");
    expect(escapeCsvCell('@SUM(A1:A2)')).toBe("'@SUM(A1:A2)");
  });

  it('guards them behind leading whitespace too', () => {
    expect(escapeCsvCell('  =leading')).toBe("'  =leading");
    expect(escapeCsvCell('\t@tabbed')).toBe("'\t@tabbed");
    expect(escapeCsvCell('\n-newline')).toBe("'\n-newline");
    expect(escapeCsvCell(' +plus')).toBe("' +plus");
  });

  it('leaves ordinary text alone', () => {
    expect(escapeCsvCell('Normal text')).toBe('Normal text');
    expect(escapeCsvCell('Tata Consultancy')).toBe('Tata Consultancy');
    expect(escapeCsvCell('')).toBe('');
  });

  it('keeps numeric columns numeric in the watchlist export', () => {
    const ev = evaluateStock(makeStock({ ticker: 'AAA' }), DEFAULT_SCREENING_CONFIG, APP);
    const csv = generateWatchlistCsv([{ ...ev, rank: 1 }]);
    const [header, row] = csv.split('\n');
    expect(header.startsWith('Rank,Ticker,Name')).toBe(true);
    const cells = row.split(',');
    expect(cells[0]).toBe('1');       // rank stays a bare number
    expect(cells[6]).toBe('64.4');    // score stays a bare number
    expect(cells[6].startsWith("'")).toBe(false);
  });

  it('guards a hostile company name in the export', () => {
    const ev = evaluateStock(makeStock({ ticker: '=EVIL', name: '-Corp' }), DEFAULT_SCREENING_CONFIG, APP);
    const csv = generateWatchlistCsv([{ ...ev, rank: 1 }]);
    expect(csv).toContain("'=EVIL");
    expect(csv).toContain("'-Corp");
  });

  it('escapes HTML in user-derived text', () => {
    expect(escapeHtml('<script>alert(1)</script>')).toBe(
      '&lt;script&gt;alert(1)&lt;/script&gt;',
    );
    expect(escapeHtml(`"'&`)).toBe('&quot;&#039;&amp;');
  });
});

describe('Delta tracking', () => {
  const previous = [
    { ticker: 'A', name: 'A', rank: 1, score: 90, warningFlags: [] },
    { ticker: 'B', name: 'B', rank: 2, score: 80, warningFlags: ['Micro Cap'] },
    { ticker: 'C', name: 'C', rank: 3, score: 70, warningFlags: [] },
  ];
  const current = [
    { ticker: 'B', name: 'B', rank: 1, score: 85, warningFlags: ['Micro Cap', 'Promoter Pledged'] },
    { ticker: 'A', name: 'A', rank: 2, score: 84, warningFlags: [] },
    { ticker: 'D', name: 'D', rank: 3, score: 75, warningFlags: [] },
  ];

  it('uses the canonical change types and rank-delta sign', () => {
    const byTicker = new Map(computeRankingChanges(current, previous).map((c) => [c.ticker, c]));
    expect(byTicker.get('B')!.changeType).toBe('RANK_UP');
    expect(byTicker.get('B')!.rankDelta).toBe(1);
    expect(byTicker.get('B')!.scoreDelta).toBe(5);
    expect(byTicker.get('B')!.newWarnings).toEqual(['Promoter Pledged']);
    expect(byTicker.get('A')!.changeType).toBe('RANK_DOWN');
    expect(byTicker.get('A')!.rankDelta).toBe(-1);
    expect(byTicker.get('D')!.changeType).toBe('NEW_ENTRY');
    expect(byTicker.get('C')!.changeType).toBe('REMOVED_ENTRY');
  });

  it('leaves deltas null where comparison is undefined', () => {
    const byTicker = new Map(computeRankingChanges(current, previous).map((c) => [c.ticker, c]));
    expect(byTicker.get('D')!.rankDelta).toBeNull();
    expect(byTicker.get('D')!.scoreDelta).toBeNull();
    expect(byTicker.get('D')!.previousRank).toBeNull();
    expect(byTicker.get('C')!.rankDelta).toBeNull();
    expect(byTicker.get('C')!.scoreDelta).toBeNull();
    expect(byTicker.get('C')!.currentRank).toBeNull();
  });

  it('marks every candidate NEW_ENTRY on a first run', () => {
    const changes = computeRankingChanges(current, null);
    expect(changes).toHaveLength(3);
    expect(changes.every((c) => c.changeType === 'NEW_ENTRY')).toBe(true);
  });

  it('emits the canonical CSV header and blank undefined deltas', () => {
    const csv = generateRankingChangesCsv(computeRankingChanges(current, previous));
    const lines = csv.split('\n');
    expect(lines[0]).toBe(
      'Ticker,Name,ChangeType,PreviousRank,CurrentRank,RankDelta,PreviousScore,CurrentScore,ScoreDelta,NewWarnings',
    );
    const newEntry = lines.find((l) => l.includes('NEW_ENTRY'))!;
    expect(newEntry).toBe('D,D,NEW_ENTRY,,3,,,75.0,,');
    const removed = lines.find((l) => l.includes('REMOVED_ENTRY'))!;
    expect(removed).toBe('C,C,REMOVED_ENTRY,3,,,70.0,,,');
  });
});

describe('Universe snapshot', () => {
  it('holds exactly the symbols in data/nifty100_snapshot.json', () => {
    // The whole set, not a spot-check: the browser module is generated from
    // the JSON, and a drifting membership is the failure that matters.
    expect([...NIFTY100_FALLBACK_SYMBOLS]).toEqual(snapshotJson.symbols);
    expect(NIFTY100_FALLBACK_SYMBOLS).toHaveLength(snapshotJson.count);
    expect(new Set(NIFTY100_FALLBACK_SYMBOLS).size).toBe(snapshotJson.count);
    expect(NIFTY100_PROVENANCE).toEqual({
      source_url: snapshotJson.source_url,
      retrieved_at_utc: snapshotJson.retrieved_at_utc,
      as_of_date: snapshotJson.as_of_date,
      sha256_of_source_csv: snapshotJson.sha256_of_source_csv,
      count: snapshotJson.count,
    });
  });

  it('counts rows outside the Nifty 100 instead of silently dropping them', () => {
    const result = processScreenerPipeline(
      parseCsv(SAMPLE_SCREENER_CSV_STRING), DEFAULT_APP_CONFIG, DEFAULT_SCREENING_CONFIG,
    );
    // Derived from the sample and the snapshot: the index is rebalanced, so a
    // hard-coded split would break this test for an unrelated reason.
    const { inIndex, outside } = sampleUniverseSplit();
    expect(inIndex).toBeGreaterThan(0);
    expect(result.evaluations).toHaveLength(inIndex);
    expect(result.outsideUniverseCount).toBe(outside);
  });
});

describe('Cross-engine number and text shapes', () => {
  it('accepts only plain ASCII decimals', () => {
    for (const bad of ['0b101', '0o17', '0x10', '1_0', 'Infinity', String.fromCharCode(0x661, 0x662), '', ' ']) {
      expect(parseStrictDecimal(bad), bad).toBeNull();
    }
    expect(parseStrictDecimal('1e3')).toBe(1000);
    expect(cleanNumeric(String.fromCharCode(0x663), 'ratio')).toBeNull();
  });

  it('uses JavaScript whitespace, which the Python engine mirrors', () => {
    expect(cleanNumeric(`5${String.fromCharCode(0x1f)}`, 'ratio')).toBeNull();
    expect(cleanNumeric(`${String.fromCharCode(0xfeff)}5`, 'ratio')).toBe(5);
    expect(normalizeHeader(`Promoter${String.fromCharCode(0xa0)}holding ${String.fromCharCode(0xe9)}`))
      .toBe('promoter holding');
  });

  it('orders tickers by code point rather than locale collation', () => {
    expect(['AB', 'A_B'].sort(compareCodePoints)).toEqual(['AB', 'A_B']);
    expect(['M-M', 'M&M'].sort(compareCodePoints)).toEqual(['M&M', 'M-M']);
    const tied = ['A_B', 'AB'].map((t) =>
      evaluateStock(makeStock({ ticker: t }), DEFAULT_SCREENING_CONFIG, APP),
    );
    expect(sortByScoreThenTicker(tied).map((e) => e.stock.ticker)).toEqual(['AB', 'A_B']);
  });

  it('passes numbers through the CSV guard untouched', () => {
    expect(escapeCsvCell(-500)).toBe('-500');
    expect(escapeCsvCell(12.5)).toBe('12.5');
  });

  it('writes custom-filter limits as JavaScript number text', () => {
    const ev = evaluateStock(makeStock({ roce: 25 }), DEFAULT_SCREENING_CONFIG, {
      ...APP, custom_filters: [{ field: 'roce', operator: '>', value: '30' }],
    });
    expect(ev.rejectionReasons).toContain('roce <= 30');
  });

  it('reports malformed custom-filter entries instead of throwing', () => {
    expect(validateCustomFilters([null, 'roce > 1', ['roce']])).toHaveLength(3);
  });
});

describe('Price history', () => {
  const days = (n: number) => {
    const out: string[] = [];
    const day = new Date(Date.UTC(2024, 0, 1));
    while (out.length < n) {
      if (day.getUTCDay() % 6 !== 0) out.push(day.toISOString().slice(0, 10));
      day.setUTCDate(day.getUTCDate() + 1);
    }
    return out;
  };

  it('parses Date,Ticker,Close[,Volume] and skips malformed rows', () => {
    const { history, skipped } = parsePriceHistoryCsv([
      'date,SYMBOL,Close,Volume',
      '2025-01-02,tcs,100.5,1000',
      '2025-01-01,TCS,100,',
      '2025-01-02,TCS,101,2000',
      'not-a-date,TCS,1,1',
      '2025-01-03,,1,1',
      '2025-01-03,TCS,abc,1',
      ',,,',
    ].join('\n'));
    expect(skipped).toBe(3);
    expect(history.TCS).toEqual({
      dates: ['2025-01-01', '2025-01-02'],
      closes: [100, 101],
      volumes: [null, 2000],
      // A file written before the OHLCV widening still loads; the missing
      // columns stay absent and are never guessed from the close.
      opens: [null, null],
      highs: [null, null],
      lows: [null, null],
    });
    expect(() => parsePriceHistoryCsv('Date,Close\n2025-01-01,1\n')).toThrow(/Date, Ticker and Close/);
  });

  it('aligns the benchmark to each stock by date', () => {
    const d = days(300);
    const tech = technicalsFromHistory(
      {
        AAA: {
          dates: d,
          closes: d.map((_, i) => 100 + i),
          volumes: d.map(() => 1000),
          opens: d.map(() => null),
          highs: d.map(() => null),
          lows: d.map(() => null),
        },
        [BENCHMARK_SYMBOL]: {
          dates: d.filter((_, i) => i % 2 === 0),
          closes: Array(150).fill(50),
          volumes: Array(150).fill(null),
          opens: Array(150).fill(null),
          highs: Array(150).fill(null),
          lows: Array(150).fill(null),
        },
      },
      ['AAA', 'MISSING'],
    );
    expect(tech.AAA.data_status).toBe('COMPLETE');
    expect(tech.AAA.as_of).toBe(d[299]);
    expect(tech.AAA.volumeRatio20D).toBe(1);
    expect(tech.MISSING.data_status).toBe('UNAVAILABLE');
  });

  it('distinguishes "no price history" from "not in the price history"', () => {
    const rows = parseCsv(SAMPLE_SCREENER_CSV_STRING);
    const app = { ...APP, universe_mode: 'custom' as const, enable_technical_confirmation: true };
    for (const e of processScreenerPipeline(rows, app, DEFAULT_SCREENING_CONFIG).evaluations) {
      expect(e.technicalScore.breakdown).toEqual(['No price history loaded']);
      expect(e.warningFlags).not.toContain('Technical Data Missing');
    }
    const d = days(300);
    const withHistory = processScreenerPipeline(rows, app, DEFAULT_SCREENING_CONFIG, undefined, {
      TCS: {
        dates: d,
        closes: d.map((_, i) => 100 + i * 0.5),
        volumes: d.map(() => null),
        opens: d.map(() => null),
        highs: d.map(() => null),
        lows: d.map(() => null),
      },
    });
    const byTicker = new Map(withHistory.evaluations.map((e) => [e.stock.ticker, e]));
    expect(byTicker.get('TCS')!.technicalScore.score).toBe(85);
    expect(byTicker.get('INFY')!.warningFlags).toContain('Technical Data Missing');
  });

  it('summarises a loaded history', () => {
    expect(
      describePriceHistory({
        TCS: {
          dates: ['2025-01-01', '2025-01-03'], closes: [1, 2], volumes: [null, null],
          opens: [null, null], highs: [null, null], lows: [null, null],
        },
        [BENCHMARK_SYMBOL]: {
          dates: ['2025-01-02'], closes: [1], volumes: [null],
          opens: [null], highs: [null], lows: [null],
        },
      }),
    ).toEqual({ tickers: 1, asOf: '2025-01-03', hasBenchmark: true });
  });
});

describe('Saved configuration', () => {
  it('merges a partial document over the defaults', () => {
    const { app, screening, errors } = validateConfigDocument({
      app: { top_n: 10, custom_symbols: [' tcs ', ''] },
      screening: { minRocePct: 18 },
    });
    expect(errors).toEqual([]);
    expect([app.top_n, app.custom_symbols, screening.minRocePct]).toEqual([10, ['TCS'], 18]);
    expect(screening.maxPeRatio).toBe(DEFAULT_SCREENING_CONFIG.maxPeRatio);
  });

  it('round-trips its own export', () => {
    const doc = JSON.parse(JSON.stringify(buildConfigDocument(DEFAULT_APP_CONFIG, DEFAULT_SCREENING_CONFIG)));
    expect(Object.keys(doc)).toEqual(['schema_version', 'app', 'screening']);
    expect(validateConfigDocument(doc).errors).toEqual([]);
  });

  it('rejects a minimum P/E above the maximum, which would reject every company', () => {
    const { errors } = validateConfigDocument({ screening: { minPeRatio: 60, maxPeRatio: 55 } });
    expect(errors).toEqual(['screening.minPeRatio (60) must not be above screening.maxPeRatio (55)']);
    expect(validateConfigDocument({ screening: { minPeRatio: 55, maxPeRatio: 55 } }).errors).toEqual([]);
  });

  it('rejects, rather than clamps, anything it cannot honour', () => {
    const bad: unknown[] = [
      { app: { top_n: 0 } }, { app: { top_n: 2.5 } }, { app: { paper_trading_only: true } },
      { screening: { minRocePct: '18' } }, { screening: { requirePositiveOcf: 1 } },
      { app: { custom_filters: [{ field: 'os.system', operator: '>', value: 1 }] } },
      { app: { universe_mode: 'all' } }, { schema_version: 'v5' }, { extra: {} }, [], null,
    ];
    for (const doc of bad) {
      expect(validateConfigDocument(doc).errors.length, JSON.stringify(doc)).toBeGreaterThan(0);
    }
  });
});

describe('Removed entries', () => {
  it('keep the name recorded in the previous snapshot', () => {
    const [removed] = computeRankingChanges([], [
      { ticker: 'GONE', name: 'Gone Ltd', rank: 1, score: 70, warningFlags: [] },
    ]);
    expect(removed.changeType).toBe('REMOVED_ENTRY');
    expect(removed.name).toBe('Gone Ltd');
  });
});

describe('Screening rules found by review', () => {
  it('treats a negative net worth as a hard red flag', () => {
    const ev = evaluateStock(makeStock({ debtToEquity: -3.5 }), DEFAULT_SCREENING_CONFIG, APP);
    expect(ev.redFlags).toEqual(['Negative net worth']);
    expect(ev.rejectionReasons).toContain('Negative net worth');
    expect(ev.rejectionReasons).not.toContain('High D/E');
    expect(ev.passed).toBe(false);
    // Red-flagged but still scored, so a comparison across the index can show
    // the fundamentals beside the flag that disqualifies them: quality 18.8 +
    // growth 16.7 + safety 10 (negative equity earns nothing for D/E, the
    // interest cover still earns its ten) + governance 9.
    expect(ev.score).toBe(54.4);
    expect(ev.categoryScores.balanceSheetSafety.score).toBe(10);
    expect(ev.scoreLines).toContain('D/E -3.5 (+0.0)');
    // A negative P/B reaches the same conclusion on its own.
    expect(
      evaluateStock(makeStock({ pbRatio: -0.3 }), DEFAULT_SCREENING_CONFIG, APP).redFlags,
    ).toEqual(['Negative net worth']);
  });

  it('reports a published zero as a value, never as a missing figure', () => {
    // ITC, L&T, HDFC Bank and ICICI Bank genuinely have no promoter at all.
    // Guarding on `value > 0` made every such company report "Promoter holding
    // missing", and the same truthiness mistake sat in five other fields. None
    // The explanation was stating something untrue about the company, and for
    // promoter holding it also scored it wrongly: having no promoter is an
    // ownership structure, not a governance failing, so it now earns the
    // neutral half of that component.
    const zero = evaluateStock(makeStock({ promoterHolding: 0 }), DEFAULT_SCREENING_CONFIG, APP);
    expect(zero.scoreLines).toContain('Promoter holding 0.0%: no promoter, scored neutral (+2.5)');
    expect(zero.scoreLines).not.toContain('Promoter holding missing (+0.0)');
    expect(zero.categoryScores.governance.score).toBe(7.5);

    // A genuinely absent value still reports itself absent.
    const absent = evaluateStock(makeStock({ promoterHolding: null }), DEFAULT_SCREENING_CONFIG, APP);
    expect(absent.scoreLines).toContain('Promoter holding missing (+0.0)');

    // Coverage already counted the zero as present, so it is not penalised a
    // second time; this pins that it stays that way.
    expect(zero.coveragePct).toBe(100);
    expect(absent.coveragePct).toBeLessThan(zero.coveragePct);

    expect(evaluateStock(makeStock({ roce: 0 }), DEFAULT_SCREENING_CONFIG, APP).scoreLines)
      .toContain('ROCE 0.0% (+0.0)');
    expect(evaluateStock(makeStock({ roe: 0 }), DEFAULT_SCREENING_CONFIG, APP).scoreLines)
      .toContain('ROE 0.0% (+0.0)');
    expect(evaluateStock(makeStock({ interestCoverage: 0 }), DEFAULT_SCREENING_CONFIG, APP).scoreLines)
      .toContain('Interest cover 0.0x (+0.0)');

    const bank = evaluateStock(
      makeStock({
        sector: 'Banking', returnOnAssets: 0, grossNpa: 2.1, netNpa: 0.5, capitalAdequacy: 16,
      }),
      DEFAULT_SCREENING_CONFIG,
      APP,
    );
    expect(bank.scoreLines).toContain('Return on assets 0.0% (+0.0)');

    // Zero debt is the best case, not a missing one, and keeps its ten.
    expect(evaluateStock(makeStock({ debtToEquity: 0 }), DEFAULT_SCREENING_CONFIG, APP).scoreLines)
      .toContain('D/E 0.0 (+10.0)');
  });

  it('treats every Screener.in financial sector name as financial', () => {
    const financial = [
      'Banking', 'Financial - Services', 'Financial Services', 'Capital Markets',
      'Stock Brokers', 'Asset Management', 'Other Financial Services', 'Finance - NBFC',
      'Insurance', 'Depository Services', 'Wealth Management', 'Lending', 'Mutual Funds',
      'Securities', 'Stock Exchange',
    ];
    const industrial = [
      'Capital Goods', 'Trading', 'Computers - Software', 'Infrastructure',
      'Metals - Non Ferrous', 'Pharmaceuticals', 'Abrasives',
    ];
    for (const sector of financial) {
      const ev = evaluateStock(makeStock({ sector }), DEFAULT_SCREENING_CONFIG, APP);
      expect(ev.scoringModel, sector).toBe('financial');
    }
    for (const sector of industrial) {
      const ev = evaluateStock(makeStock({ sector }), DEFAULT_SCREENING_CONFIG, APP);
      expect(ev.scoringModel, sector).toBe('general');
    }
  });

  it('keeps passing stocks that rank below top_n', () => {
    const header = 'Name,NSE Code,Market Capitalization,Sales growth 3Years,Profit growth 3Years,ROCE,Return on equity,Debt to equity,Interest Coverage,Cash flow from operations,Promoter holding,Pledged percentage,Price to Earning,Price to book value,Dividend yield';
    const rows = ['AAA', 'BBB', 'CCC'].map(
      (t) => `${t} Ltd,${t},5000,20%,20%,25%,25%,0.1,10,500,60%,0%,15,2,1%`,
    );
    const result = processScreenerPipeline(
      parseCsv([header, ...rows].join('\n')),
      { ...APP, universe_mode: 'custom' as const, top_n: 2 },
      DEFAULT_SCREENING_CONFIG,
    );
    expect(result.watchlist.map((e) => e.stock.ticker)).toEqual(['AAA', 'BBB']);
    expect(result.passedBelowCutOff.map((e) => [e.stock.ticker, e.rank])).toEqual([['CCC', 3]]);
    // Nothing that passed may be missing from the exports or the report count.
    expect(generateWatchlistCsv(result.passedBelowCutOff)).toContain('CCC');
    const html = generateHtmlReport(result.watchlist, result.passedBelowCutOff, result.rejected, result.inspectionReport, APP);
    expect(html).toContain('<strong>Candidates passed:</strong> 3');
  });

  it('parses rupee-prefixed prices, as clean_numeric documents', () => {
    for (const text of ['Rs 1,500', 'RS. 1,500', 'INR 1500', 'rs 1500', '₹ 1,500']) {
      expect(cleanNumeric(text, 'price'), text).toBe(1500);
    }
    expect(cleanNumeric('Rs 1,500 Cr', 'crore')).toBe(1500);
    expect(cleanNumeric('RSVP', 'price')).toBeNull();
    expect(cleanNumeric('Rs', 'price')).toBeNull();
  });
});

describe('Saved run snapshots', () => {
  const entry = { ticker: 'TCS', name: 'TCS Ltd', rank: 1, score: 80, warningFlags: [] };

  it('ignores a stored value that is not a usable snapshot', () => {
    for (const bad of [{}, null, 42, 'snapshot', [42], [{ ticker: 'TCS' }], [{ ...entry, rank: 'one' }]]) {
      expect(validSnapshotEntries(bad), JSON.stringify(bad)).toEqual([]);
    }
  });

  it('keeps a well-formed snapshot and drops only the broken entries', () => {
    expect(validSnapshotEntries([entry])).toEqual([entry]);
    expect(validSnapshotEntries([entry, { ticker: '' }, { ...entry, ticker: 'INFY' }]))
      .toEqual([entry, { ...entry, ticker: 'INFY' }]);
  });

  it('reads both the saved-run object and the older bare array', () => {
    const saved = parseSavedRun({
      savedAt: '2026-09-12', fileName: 'export.csv', entries: [entry],
      appConfig: DEFAULT_APP_CONFIG, screeningConfig: DEFAULT_SCREENING_CONFIG,
    });
    expect(saved?.entries).toEqual([entry]);
    expect(saved?.fileName).toBe('export.csv');
    const legacy = parseSavedRun([entry]);
    expect(legacy?.entries).toEqual([entry]);
    expect(legacy?.fileName).toBeNull();
    expect(parseSavedRun({})).toBeNull();
  });
});

describe('File-format edge cases', () => {
  it('parses price files with any line ending, but only comma-separated', () => {
    for (const text of [
      'Date,Ticker,Close\r\n2025-01-01,TCS,1\n2025-01-02,TCS,2\n',
      'Date,Ticker,Close\r2025-01-01,TCS,1\r2025-01-02,TCS,2\r',
    ]) {
      const { history, skipped } = parsePriceHistoryCsv(text);
      expect([history.TCS.closes, skipped], JSON.stringify(text)).toEqual([[1, 2], 0]);
    }
    expect(() => parsePriceHistoryCsv('Date\tTicker\tClose\n2025-01-01\tTCS\t1\n')).toThrow();
  });

  it('skips impossible calendar dates', () => {
    const days = ['2025-02-30', '2025-13-01', '1900-02-29', '2024-02-29', '2000-02-29'];
    const { history, skipped } = parsePriceHistoryCsv(['Date,Ticker,Close', ...days.map((d) => `${d},TCS,1`)].join('\n'));
    expect(skipped).toBe(3);
    expect(history.TCS.dates).toEqual(['2000-02-29', '2024-02-29']);
  });

  it("needs the latest session's volume for the volume ratio", () => {
    const closes = Array(30).fill(100);
    expect(computeTechnicalIndicators(closes, null, [...Array(29).fill(1000), null]).volumeRatio20D).toBeNull();
    expect(computeTechnicalIndicators(closes, null, [...Array(29).fill(1000), 2000]).volumeRatio20D)
      .toBe(2000 / (21000 / 20));
  });

  it('describes a short history instead of calling it absent', () => {
    const tech = computeTechnicalIndicators(Array.from({ length: 30 }, (_, i) => 100 + i));
    const result = calculateTechnicalScore(tech, true);
    expect(result.breakdown).toEqual(['Only 30 sessions of price history; indicators need at least 50']);
    expect(result.warnings).toEqual(['Technical Data Missing']);
  });

  it('pins the fundamentals delimiter to a comma and normalises line endings', () => {
    expect(Object.keys(parseCsv('Name;NSE Code\r\nAlpha;AAA\r\n')[0])).toEqual(['Name;NSE Code']);
    expect(parseCsv('Name,NSE Code\r\nAlpha,AAA\rBeta,BBB\n')).toHaveLength(2);
  });

  it('writes config errors in code-point key order with JSON-quoted values', () => {
    expect(validateConfigDocument({ zzz: 1, 5: 2 }).errors).toEqual([
      'Unknown configuration section: 5',
      'Unknown configuration section: zzz',
    ]);
    expect(validateCustomFilters([{ field: null, operator: '>', value: 1 }])).toEqual([
      'Invalid custom filter field: null',
    ]);
    expect(validateCustomFilters([{ field: 'roce', operator: '>', value: [1] }])).toEqual([
      'Invalid numeric value in custom filter for roce: [1]',
    ]);
  });
});
