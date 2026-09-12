/**
 * In-app validation suite shown on the "Unit tests" tab and asserted by
 * src/tests/invariants.test.ts.
 *
 * These are real invariants, not restatements of the implementation. Two
 * earlier checks were removed for being unfalsifiable:
 *   - "score is between 0 and 100" merely re-tested the clamp it was reading
 *     from, so it now asserts exact expected scores for pinned inputs.
 *   - "exactly 100 unique constituents" passed while a quarter of the
 *     membership was wrong, so it now asserts symbol-set equality against
 *     data/nifty100_snapshot.json, the file the snapshot module is generated
 *     from.
 */
import NIFTY100_SNAPSHOT_JSON from '../../data/nifty100_snapshot.json';
import { NIFTY100_FALLBACK_SYMBOLS, NIFTY100_PROVENANCE } from '../data/nifty100Snapshot';
import { CleanedStock, TestResult } from '../types';
import {
  BENCHMARK_SYMBOL,
  cleanNumeric,
  compareCodePoints,
  computeTechnicalIndicators,
  parsePriceHistoryCsv,
  parseStrictDecimal,
  technicalsFromHistory,
  DEFAULT_APP_CONFIG,
  DEFAULT_SCREENING_CONFIG,
  dedupeStocks,
  emptyTechnicals,
  escapeCsvCell,
  evaluateStock,
  detectColumnMapping,
  processScreenerPipeline,
  round1,
  sortByScoreThenTicker,
} from './screenerEngine';

/** Build a fully-populated stock so individual tests can vary one field. */
function makeStock(overrides: Partial<CleanedStock> = {}): CleanedStock {
  return {
    id: 'test',
    name: 'Test Co',
    ticker: 'TEST',
    bseCode: null,
    sector: 'Computers - Software',
    currentPrice: 100,
    marketCap: 10000,
    salesGrowth: 20,
    profitGrowth: 20,
    roce: 25,
    roe: 25,
    debtToEquity: 0,
    interestCoverage: 10,
    operatingCashFlow: 100,
    promoterHolding: 60,
    promoterPledge: 0,
    peRatio: 15,
    pbRatio: 2,
    dividendYield: 1,
    sales: null,
    returnOnAssets: null,
    grossNpa: null,
    netNpa: null,
    capitalAdequacy: null,
    casa: null,
    financingMargin: null,
    technicals: emptyTechnicals(),
    rawRow: {},
    ...overrides,
  };
}

const APP = { ...DEFAULT_APP_CONFIG, minimum_total_score: 0, enable_technical_confirmation: false };

/** `n` consecutive weekdays from 2024-01-01 as YYYY-MM-DD. */
function businessDays(n: number): string[] {
  const out: string[] = [];
  const day = new Date(Date.UTC(2024, 0, 1));
  while (out.length < n) {
    const weekday = day.getUTCDay();
    if (weekday !== 0 && weekday !== 6) out.push(day.toISOString().slice(0, 10));
    day.setUTCDate(day.getUTCDate() + 1);
  }
  return out;
}

export function runAllValidations(): TestResult[] {
  const results: TestResult[] = [];

  const runTest = (
    name: string,
    category: string,
    fn: () => { passed: boolean; message: string },
  ) => {
    const start = performance.now();
    try {
      const res = fn();
      results.push({ ...res, name, category, executionTimeMs: round1(performance.now() - start) });
    } catch (e) {
      results.push({
        name,
        category,
        passed: false,
        message: e instanceof Error ? e.message : String(e),
        executionTimeMs: round1(performance.now() - start),
      });
    }
  };

  runTest('Unit-aware crore parsing', 'Parsing', () => {
    const cr = cleanNumeric('1 CRORE', 'crore');
    const lakh100 = cleanNumeric('100 LAKH', 'crore');
    const lakh10 = cleanNumeric('10 LAKH', 'crore');
    const passed = cr === 1 && lakh100 === 1 && Math.abs((lakh10 ?? 0) - 0.1) < 1e-12;
    return { passed, message: `1 CRORE=${cr}, 100 LAKH=${lakh100}, 10 LAKH=${lakh10}` };
  });

  runTest('Monetary suffixes rejected on percent/ratio', 'Parsing', () => {
    const a = cleanNumeric('15 CR', 'percent');
    const b = cleanNumeric('1 CR', 'ratio');
    const c = cleanNumeric('0.5%', 'ratio');
    const d = cleanNumeric('15.5%', 'percent');
    return {
      passed: a === null && b === null && c === null && d === 15.5,
      message: `15 CR%=${a}, 1 CR ratio=${b}, 0.5% ratio=${c}, 15.5%=${d}`,
    };
  });

  runTest('Currency, comma and percent stripping', 'Parsing', () => {
    const a = cleanNumeric('₹ 1,500.50', 'price');
    const b = cleanNumeric('15.5%', 'percent');
    const c = cleanNumeric('"1,000.50"', 'ratio');
    return { passed: a === 1500.5 && b === 15.5 && c === 1000.5, message: `${a}, ${b}, ${c}` };
  });

  runTest('Malformed numerics rejected', 'Parsing', () => {
    const bad = ['1500abc', '', 'N/A', '--', '0x10'].map((v) => cleanNumeric(v, 'ratio'));
    return { passed: bad.every((v) => v === null), message: `results=${JSON.stringify(bad)}` };
  });

  runTest('Only plain ASCII decimals are numbers', 'Parsing', () => {
    const arabicTwelve = String.fromCharCode(0x661, 0x662);
    const rejected = ['0x10', '0b101', '0o17', '1_0', 'Infinity', arabicTwelve].map(parseStrictDecimal);
    const passed = rejected.every((v) => v === null) && parseStrictDecimal(' 12.5 ') === 12.5;
    return { passed, message: `rejected=${JSON.stringify(rejected)}` };
  });

  runTest('Tickers order by code point, not locale', 'Parsing', () => {
    const order = ['AB', 'A_B', 'M-M', 'M&M'].sort(compareCodePoints);
    const passed = JSON.stringify(order) === JSON.stringify(['AB', 'A_B', 'M&M', 'M-M']);
    return { passed, message: order.join(' < ') };
  });

  runTest('round1 is half-up at one decimal', 'Parsing', () => {
    const cases: [number, number][] = [[74.55, 74.6], [81.45, 81.5], [0.05, 0.1], [100, 100]];
    const bad = cases.filter(([input, want]) => round1(input) !== want);
    return {
      passed: bad.length === 0,
      message: bad.length ? `mismatches: ${JSON.stringify(bad)}` : 'all four cases match',
    };
  });

  runTest('Nifty snapshot matches the pinned symbol set', 'Universe', () => {
    // Symbol-set equality against data/nifty100_snapshot.json, the file this
    // module is generated from -- not a spot-check.
    const symbols = [...NIFTY100_FALLBACK_SYMBOLS];
    const expected = [...NIFTY100_SNAPSHOT_JSON.symbols];
    const unique = new Set(symbols);
    const missing = expected.filter((s) => !unique.has(s));
    const unexpected = symbols.filter((s) => !expected.includes(s));
    const sorted = symbols.every((s, i) => i === 0 || symbols[i - 1] <= s);
    const passed =
      symbols.length === NIFTY100_SNAPSHOT_JSON.count &&
      unique.size === symbols.length &&
      missing.length === 0 &&
      unexpected.length === 0 &&
      sorted;
    return {
      passed,
      message:
        `${unique.size} unique, sorted=${sorted}, missing=[${missing.join(', ')}], ` +
        `unexpected=[${unexpected.join(', ')}], as of ${NIFTY100_PROVENANCE.as_of_date}`,
    };
  });

  runTest('Snapshot provenance is recorded', 'Universe', () => {
    const p = NIFTY100_PROVENANCE;
    const passed =
      Boolean(p.source_url) &&
      Boolean(p.retrieved_at_utc) &&
      /^\d{4}-\d{2}-\d{2}$/.test(p.as_of_date) &&
      p.sha256_of_source_csv.length === 64 &&
      p.count === 100;
    return { passed, message: `as_of=${p.as_of_date}, sha256 len=${p.sha256_of_source_csv.length}` };
  });

  runTest('Identifier columns do not consume each other', 'Mapping', () => {
    const both = detectColumnMapping(['Name', 'NSE Code', 'BSE Code']);
    const bseOnly = detectColumnMapping(['Name', 'BSE Code']);
    const nseOnly = detectColumnMapping(['Name', 'NSE Code']);
    const passed =
      both.ticker === 'NSE Code' &&
      both.bseCode === 'BSE Code' &&
      bseOnly.ticker === 'BSE Code' &&
      bseOnly.bseCode === 'BSE Code' &&
      nseOnly.ticker === 'NSE Code' &&
      nseOnly.bseCode === undefined;
    return {
      passed,
      message: `both=${JSON.stringify(both)}, bseOnly=${JSON.stringify(bseOnly)}`,
    };
  });

  runTest('Header order does not change mapping', 'Mapping', () => {
    const a = detectColumnMapping(['Name', 'NSE Code', 'BSE Code', 'Price to Earning']);
    const b = detectColumnMapping(['Price to Earning', 'BSE Code', 'NSE Code', 'Name']);
    const passed = JSON.stringify(a) === JSON.stringify(b);
    return { passed, message: passed ? 'identical' : `${JSON.stringify(a)} vs ${JSON.stringify(b)}` };
  });

  runTest('Exact aliases beat loose ones', 'Mapping', () => {
    const m = detectColumnMapping(['Name', 'Price to Earning', 'Price to book value']);
    const passed = m.peRatio === 'Price to Earning' && m.currentPrice === undefined;
    return { passed, message: JSON.stringify(m) };
  });

  runTest('Pinned scores for a known stock', 'Scoring', () => {
    // Fully specified inputs, so the expected score is arithmetic, not a clamp.
    // Valuation is judged against the loaded file's own sectors, and a stock
    // scored on its own has no yardstick, so it earns nothing there:
    // fq 30 + growth 25 + balance 10+10 + valuation 0 + governance 4+5 = 84
    const ev = evaluateStock(makeStock(), DEFAULT_SCREENING_CONFIG, APP);
    const passed = ev.score === 84 && ev.passed && ev.coveragePct === 100;
    return { passed, message: `score=${ev.score}, passed=${ev.passed}, coverage=${ev.coveragePct}` };
  });

  runTest('Sparse company is not scaled up', 'Scoring', () => {
    const sparse = makeStock({
      ticker: 'SPARSE', marketCap: null, salesGrowth: null, profitGrowth: null,
      roe: null, debtToEquity: null, interestCoverage: null, operatingCashFlow: null,
      promoterHolding: null, promoterPledge: null, peRatio: null, pbRatio: null,
      dividendYield: null,
    });
    const ev = evaluateStock(sparse, DEFAULT_SCREENING_CONFIG, APP);
    const passed = !ev.passed && ev.score <= 15 && ev.rejectionReasons.some((r) => r.includes('Insufficient Data'));
    return { passed, message: `score=${ev.score}; ${ev.rejectionReasons.join(', ')}` };
  });

  runTest('P/E and P/B ceilings enforced under the strict screen', 'Scoring', () => {
    const stock = makeStock({ peRatio: 1000, pbRatio: 1000 });
    // By default an expensive company is ranked low, not thrown away; the
    // strict screen re-applies the old ceilings as a filter.
    const relaxed = evaluateStock(stock, DEFAULT_SCREENING_CONFIG, APP);
    const ev = evaluateStock(stock, DEFAULT_SCREENING_CONFIG, { ...APP, strict_screen: true });
    const passed =
      !relaxed.rejectionReasons.includes('P/E above maximum') &&
      !ev.passed &&
      ev.rejectionReasons.includes('P/E above maximum') &&
      ev.rejectionReasons.includes('P/B above maximum');
    return {
      passed,
      message: `relaxed=[${relaxed.rejectionReasons.join(', ')}] strict=[${ev.rejectionReasons.join(', ')}]`,
    };
  });

  runTest('Financial companies use the financial model', 'Scoring', () => {
    const bare = evaluateStock(makeStock({ sector: 'Banking' }), DEFAULT_SCREENING_CONFIG, APP);
    const withMetrics = evaluateStock(
      makeStock({
        sector: 'Banking', returnOnAssets: 1.8, grossNpa: 2.1, netNpa: 0.5,
        capitalAdequacy: 16, operatingCashFlow: -900,
      }),
      DEFAULT_SCREENING_CONFIG,
      APP,
    );
    const passed =
      bare.scoringModel === 'financial' &&
      !bare.passed &&
      (bare.notScored ?? '').includes('missing bank metrics') &&
      withMetrics.notScored === null &&
      // A negative operating cash flow is ordinary for a growing loan book.
      withMetrics.redFlags.length === 0 &&
      withMetrics.score > 0;
    return {
      passed,
      message: `without metrics: ${bare.notScored ?? 'scored'}; with metrics: ${withMetrics.score}`,
    };
  });

  runTest('All three warning flags fire', 'Scoring', () => {
    const ev = evaluateStock(
      makeStock({ dividendYield: 0, marketCap: 400, promoterPledge: 5 }),
      DEFAULT_SCREENING_CONFIG,
      APP,
    );
    const want = ['Low Dividend Yield', 'Micro Cap', 'Promoter Pledged'];
    const missing = want.filter((w) => !ev.warningFlags.includes(w));
    return { passed: missing.length === 0, message: `flags=[${ev.warningFlags.join(', ')}]` };
  });

  runTest('Explanation is factual and non-empty', 'Scoring', () => {
    const ev = evaluateStock(makeStock(), DEFAULT_SCREENING_CONFIG, APP);
    const passed =
      ev.explanation.length > 40 &&
      ev.explanation.includes('Total fundamental score') &&
      ev.explanation.includes('ROCE');
    return { passed, message: ev.explanation.slice(0, 90) + '…' };
  });

  runTest('Watchlist sorts by score then ticker', 'Pipeline', () => {
    // promoterHolding 75 saturates governance where 60 does not, so MMM scores
    // highest and the remaining two tie and break alphabetically.
    const items = ['ZZZ', 'AAA', 'MMM'].map((t) =>
      evaluateStock(
        makeStock({ ticker: t, promoterHolding: t === 'MMM' ? 75 : 60 }),
        DEFAULT_SCREENING_CONFIG,
        APP,
      ),
    );
    const order = sortByScoreThenTicker(items).map((e) => e.stock.ticker);
    const passed = JSON.stringify(order) === JSON.stringify(['MMM', 'AAA', 'ZZZ']);
    return { passed, message: order.join(' > ') };
  });

  runTest('Deduplication by ticker, BSE code and name', 'Pipeline', () => {
    const stocks = [
      makeStock({ ticker: 'A', bseCode: '1', name: 'Alpha' }),
      makeStock({ ticker: 'A', bseCode: '9', name: 'Other' }),
      makeStock({ ticker: 'B', bseCode: '1', name: 'Beta' }),
      makeStock({ ticker: 'C', bseCode: '3', name: 'Alpha' }),
      makeStock({ ticker: 'D', bseCode: '4', name: 'Delta' }),
    ];
    const { unique, duplicatesRemoved } = dedupeStocks(stocks);
    const passed =
      duplicatesRemoved === 3 && JSON.stringify(unique.map((s) => s.ticker)) === JSON.stringify(['A', 'D']);
    return { passed, message: `kept=[${unique.map((s) => s.ticker).join(', ')}], removed=${duplicatesRemoved}` };
  });

  runTest('Custom filters change the outcome', 'Pipeline', () => {
    const stock = makeStock({ roce: 25 });
    const without = evaluateStock(stock, DEFAULT_SCREENING_CONFIG, APP);
    const withFilter = evaluateStock(stock, DEFAULT_SCREENING_CONFIG, {
      ...APP,
      custom_filters: [{ field: 'roce', operator: '>', value: '30' }],
    });
    const passed = without.passed && !withFilter.passed && withFilter.rejectionReasons.some((r) => r.includes('roce'));
    return { passed, message: `without=${without.passed}, with=${withFilter.passed}` };
  });

  runTest('Staleness threshold is honoured', 'Pipeline', () => {
    const rows = [{ Name: 'X', 'NSE Code': 'RELIANCE', 'Market Capitalization': '10000' }];
    const fortyDaysAgo = Date.now() - 40 * 86400000;
    const res = processScreenerPipeline(
      rows,
      { ...DEFAULT_APP_CONFIG, fundamentals_stale_after_days: 30 },
      DEFAULT_SCREENING_CONFIG,
      fortyDaysAgo,
    );
    const passed = res.inspectionReport.isStale && res.inspectionReport.fileAgeDays === 40;
    return { passed, message: `age=${res.inspectionReport.fileAgeDays}, stale=${res.inspectionReport.isStale}` };
  });

  runTest('52-week high needs 252 sessions', 'Technicals', () => {
    const series = (n: number) => Array.from({ length: n }, (_, i) => 100 + i * 0.5);
    const expectations: [number, boolean][] = [
      [20, false], [199, false], [200, false], [251, false], [252, true], [300, true],
    ];
    const bad = expectations.filter(
      ([n, want]) => computeTechnicalIndicators(series(n)).available.high52Week !== want,
    );
    return {
      passed: bad.length === 0,
      message: bad.length ? `wrong at n=${bad.map(([n]) => n).join(', ')}` : 'all six thresholds correct',
    };
  });

  runTest('Uploaded price history drives technical scores', 'Technicals', () => {
    const dates = businessDays(300);
    const lines = ['Date,Ticker,Close,Volume'];
    dates.forEach((d, i) => {
      lines.push(`${d},TEST,${100 + i * 0.5},${1000 + i}`);
      lines.push(`${d},${BENCHMARK_SYMBOL},${50 + i * 0.1},`);
    });
    const { history, skipped } = parsePriceHistoryCsv(lines.join('\n'));
    const tech = technicalsFromHistory(history, ['TEST']).TEST;
    const ev = evaluateStock(makeStock({ technicals: tech }), DEFAULT_SCREENING_CONFIG, {
      ...APP, enable_technical_confirmation: true,
    });
    const passed = skipped === 0 && tech.data_status === 'COMPLETE' && ev.technicalScore.score === 100;
    return { passed, message: `status=${tech.data_status}, score=${ev.technicalScore.score}, as of ${tech.as_of}` };
  });

  runTest('No price history is not a per-stock warning', 'Technicals', () => {
    const ev = evaluateStock(makeStock({ technicals: null }), DEFAULT_SCREENING_CONFIG, {
      ...APP, enable_technical_confirmation: true,
    });
    const passed =
      ev.technicalScore.score === null &&
      ev.technicalScore.breakdown[0] === 'No price history loaded' &&
      !ev.warningFlags.includes('Technical Data Missing');
    return { passed, message: `${ev.technicalScore.breakdown[0]}; flags=[${ev.warningFlags.join(', ')}]` };
  });

  runTest('Technical toggle disables scoring', 'Config', () => {
    const prices = Array.from({ length: 300 }, (_, i) => 100 + i * 0.5);
    const tech = computeTechnicalIndicators(prices);
    const on = evaluateStock(makeStock({ technicals: tech }), DEFAULT_SCREENING_CONFIG, {
      ...APP, enable_technical_confirmation: true,
    });
    const off = evaluateStock(makeStock({ technicals: tech }), DEFAULT_SCREENING_CONFIG, {
      ...APP, enable_technical_confirmation: false,
    });
    const passed = on.technicalScore.score !== null && off.technicalScore.score === null;
    return { passed, message: `on=${on.technicalScore.score}, off=${off.technicalScore.score}` };
  });

  runTest('CSV formula injection is neutralised', 'Security', () => {
    const cases: [string, string][] = [
      ['=cmd|', "'=cmd|"],
      ['+1+1', "'+1+1"],
      ['-500', "'-500"],
      ['@SUM(A1)', "'@SUM(A1)"],
      ['  =lead', "'  =lead"],
      ['\t@tab', "'\t@tab"],
      ['Normal', 'Normal'],
    ];
    const bad = cases.filter(([input, want]) => escapeCsvCell(input) !== want);
    return {
      passed: bad.length === 0,
      message: bad.length ? `failed on ${JSON.stringify(bad.map((b) => b[0]))}` : 'all seven cases guarded',
    };
  });

  return results;
}
