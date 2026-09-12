/**
 * Cross-engine parity: TypeScript vs the Python inside the generated notebook.
 *
 * This suite is deliberately unforgiving. It fails when the notebook cannot be
 * produced, when Python or its dependencies are missing, when the subprocess
 * exits non-zero, when the JSON is invalid or incomplete, when a company is
 * absent, or when the two engines disagree on ANY compared field. There is no
 * fallback path and no hard-coded expected result standing in for a real run.
 */
import { beforeAll, describe, expect, it } from 'vitest';

import { NIFTY100_FALLBACK_SYMBOLS, NIFTY100_PROVENANCE } from '../data/nifty100Snapshot';
import { SAMPLE_SCREENER_CSV_STRING } from '../data/sampleScreenerData';
import { AppConfig, ScreeningConfig, StockEvaluation, WatchlistSnapshotEntry } from '../types';
import {
  BENCHMARK_SYMBOL,
  compareCodePoints,
  computeRankingChanges,
  CONFIG_LIMITS,
  DEFAULT_APP_CONFIG,
  DEFAULT_SCREENING_CONFIG,
  detectColumnMapping,
  escapeCsvCell,
  cleanNumeric,
  computeTechnicalIndicators,
  generateRankingChangesCsv,
  generateRejectedCsv,
  generateWatchlistCsv,
  normalizeHeader,
  parseCsv,
  parsePriceHistoryCsv,
  parseStrictDecimal,
  PipelineResult,
  PriceHistory,
  processScreenerPipeline,
  technicalsFromHistory,
  validateConfigDocument,
} from '../utils/screenerEngine';
import { businessDays } from './helpers/dates';
import { sampleUniverseSplit } from './helpers/sample';
import {
  MappingCase,
  ParityEvaluation,
  ParityPayload,
  readSampleCsvFromSource,
  runPythonParity,
  ScreenSpec,
  UnitCase,
} from './helpers/pythonBridge';

/** Screen every bundled company: custom mode, no symbol filter, no cutoffs. */
const APP_CONFIG: AppConfig = {
  universe_mode: 'custom',
  custom_symbols: [],
  custom_filters: [],
  top_n: 100,
  minimum_total_score: 0,
  fundamentals_stale_after_days: 30,
  enable_technical_confirmation: false,
  strict_screen: false,
};
const SCREENING_CONFIG: ScreeningConfig = { ...DEFAULT_SCREENING_CONFIG };

const EXPECTED_SAMPLE_ROWS = 31;

/**
 * Hand-built previous snapshot, arranged so the resulting delta set contains
 * every change type: AIAENG moves up, POLYCAB and SUNPHARMA move down,
 * CARBORUNIV holds its rank, FINEORG is new and GONE has left.
 */
const DELTA_PREVIOUS: WatchlistSnapshotEntry[] = [
  { ticker: 'POLYCAB', name: 'Polycab', rank: 1, score: 84.0, warningFlags: ['Micro Cap'] },
  { ticker: 'AIAENG', name: 'AIA Engineering', rank: 2, score: 89.0, warningFlags: [] },
  { ticker: 'SUNPHARMA', name: 'Sun Pharma', rank: 3, score: 80.0, warningFlags: [] },
  { ticker: 'CARBORUNIV', name: 'Carborundum', rank: 8, score: 80.2, warningFlags: [] },
  { ticker: 'GONE', name: 'Gone Ltd', rank: 5, score: 70.0, warningFlags: [] },
];

const UNIT_CASES: UnitCase[] = [
  { label: 'crore_1cr', value: '1 CRORE', unit: 'crore' },
  { label: 'crore_100lakh', value: '100 LAKH', unit: 'crore' },
  { label: 'crore_10lakh', value: '10 LAKH', unit: 'crore' },
  { label: 'crore_plain', value: '1,500.50', unit: 'crore' },
  { label: 'percent_pct', value: '15.5%', unit: 'percent' },
  { label: 'percent_monetary', value: '15 CR', unit: 'percent' },
  { label: 'percent_lakh', value: '15 LAKH', unit: 'percent' },
  { label: 'ratio_monetary', value: '1 CR', unit: 'ratio' },
  { label: 'ratio_percent', value: '0.5%', unit: 'ratio' },
  { label: 'ratio_plain', value: '0.42', unit: 'ratio' },
  { label: 'price_currency', value: '₹ 1,500', unit: 'price' },
  { label: 'price_monetary', value: '1500 CR', unit: 'price' },
  { label: 'garbage', value: '1500abc', unit: 'ratio' },
  { label: 'price_rs_words', value: 'Rs 1,500', unit: 'price' },
  { label: 'price_rs_dot', value: 'RS. 1,500', unit: 'price' },
  { label: 'price_inr', value: 'INR 1500', unit: 'price' },
  { label: 'price_rs_lower', value: 'rs 1500', unit: 'price' },
  { label: 'crore_rs_words', value: 'Rs 1,500 Cr', unit: 'crore' },
  { label: 'price_rsvp', value: 'RSVP', unit: 'price' },
];

const ESCAPE_CASES = [
  '=cmd|', '+1+1', '-500', '@SUM(A1:A2)',
  '  =leading', '\t@tabbed', ' -0.5', 'Normal text', 'Text, with comma',
];

const TECHNICAL_SIZES = [20, 199, 200, 251, 252, 300];

const MAPPING_CASES: MappingCase[] = [
  { label: 'nse_and_bse', headers: ['Name', 'NSE Code', 'BSE Code'] },
  { label: 'bse_only', headers: ['Name', 'BSE Code'] },
  { label: 'nse_only', headers: ['Name', 'NSE Code'] },
  { label: 'forward_order', headers: ['Name', 'NSE Code', 'BSE Code', 'Price to Earning'] },
  { label: 'reversed_order', headers: ['Price to Earning', 'BSE Code', 'NSE Code', 'Name'] },
  { label: 'pe_without_price', headers: ['Name', 'Price to Earning', 'Price to book value'] },
  {
    label: 'full_screener_export',
    headers: [
      'Name', 'NSE Code', 'BSE Code', 'Industry', 'Current Price',
      'Market Capitalization', 'Sales growth 3Years', 'Profit growth 3Years',
      'ROCE', 'Return on equity', 'Debt to equity', 'Interest Coverage',
      'Cash flow from operations', 'Promoter holding', 'Pledged percentage',
      'Price to Earning', 'Price to book value', 'Dividend yield',
    ],
  },
];

/** Park-Miller random walk: deterministic, exact in doubles, and irregular enough to be realistic. */
function randomWalk(seed: number, n: number, start: number): number[] {
  let state = seed;
  let price = start;
  const out: number[] = [];
  for (let i = 0; i < n; i += 1) {
    state = (state * 16807) % 2147483647;
    price *= 1 + (state / 2147483647 - 0.48) * 0.04;
    out.push(Math.round(price * 100) / 100);
  }
  return out;
}

const PRICE_DAYS = businessDays(300, '2025-06-02');

/**
 * One price-history file for both engines. It covers a full history, a recent
 * listing (partial indicators), a flat price (moving averages equal the price,
 * so comparisons depend on exact sums), a stock suspended on some sessions, a
 * benchmark with its own holidays, blank volumes and malformed rows.
 */
function buildPriceCsv(): string {
  const lines = ['Date,Ticker,Close,Volume'];
  const add = (ticker: string, closes: number[], days: string[], volume: (i: number) => string) =>
    days.forEach((d, i) => lines.push(`${d},${ticker},${closes[i]},${volume(i)}`));
  ['TCS', 'INFY', 'SUNPHARMA', 'AIAENG', 'POLYCAB', 'CARBORUNIV', 'FINEORG', 'ASTRAL'].forEach((t, k) =>
    add(t, randomWalk(1000 + k, 300, 100 + 50 * k), PRICE_DAYS, (i) =>
      i % 17 === 0 ? '' : String(100000 + ((i * 7919 + k) % 5000))),
  );
  add('KPITTECH', randomWalk(77, 180, 900), PRICE_DAYS.slice(-180), () => '5000');
  add('BEL', Array(300).fill(100.1), PRICE_DAYS, () => '1000');
  // Too short for any indicator, and a latest session with no volume.
  add('CLEAN', randomWalk(31, 30, 1400), PRICE_DAYS.slice(-30), () => '700');
  add('BIKAJI', randomWalk(62, 60, 800), PRICE_DAYS.slice(-60), (i) => (i === 59 ? '' : '900'));
  const suspended = PRICE_DAYS.filter((_, i) => i % 7 !== 3);
  add('LT', randomWalk(55, suspended.length, 3000), suspended, () => '');
  const benchDays = PRICE_DAYS.filter((_, i) => i % 11 !== 5);
  add(BENCHMARK_SYMBOL, randomWalk(99, benchDays.length, 24000), benchDays, () => '');
  lines.push(
    '2025-13-40x,TCS,1,1', '2025-02-30,TCS,1,1', `${PRICE_DAYS[0]},,5,5`, `${PRICE_DAYS[1]},INFY,n/a,5`, ',,,',
  );
  return `${lines.join('\n')}\n`;
}

const PRICE_CSV = buildPriceCsv();

/** Identical fundamentals, tickers whose code-point order differs from locale collation. */
const TIE_CSV = [
  'Name,NSE Code,Market Capitalization,Sales growth 3Years,Profit growth 3Years,ROCE,Return on equity,Debt to equity,Interest Coverage,Cash flow from operations,Promoter holding,Pledged percentage,Price to Earning,Price to book value,Dividend yield',
  ...['A_B', 'AB', 'A-B', 'A&B', 'AA', 'Z'].map(
    (ticker, i) => `Co ${i + 1},${ticker},5000,20%,20%,25%,25%,0.1,10,500,60%,0%,15,2,1%`,
  ),
].join('\n');

/**
 * Words pandas turns into blanks by default ("None", "NA", "N/A", "null"), a
 * sector that only Unicode case-folding would call financial, blank cells and
 * CRLF line endings.
 */
const NA_WORDS_CSV = [
  'Name,NSE Code,Industry,Market Capitalization,Sales growth 3Years,Profit growth 3Years,ROCE,Return on equity,Debt to equity,Interest Coverage,Cash flow from operations,Promoter holding,Pledged percentage,Price to Earning,Price to book value,Dividend yield',
  'None,NA,N/A,5000,20%,20%,25%,25%,0.1,10,500,60%,0%,15,2,1%',
  'null,NULL,nan,5000,20%,20%,25%,25%,0.1,10,500,60%,0%,15,2,1%',
  `Long S Co,LONGS,In${String.fromCharCode(0x17f)}urance,5000,20%,20%,25%,25%,0.1,10,500,60%,0%,15,2,1%`,
  'Blank Co,BLANK,,5000,,,,,,,,,,,,',
].join('\r\n');

/**
 * The Section 1 rules in one file: five identical passers (so top_n splits
 * them), a negative net worth, a Screener.in financial sector name, and a
 * rupee-prefixed price.
 */
const EDGE_CASE_CSV = [
  'Name,NSE Code,Industry,Current Price,Market Capitalization,Sales growth 3Years,Profit growth 3Years,ROCE,Return on equity,Debt to equity,Interest Coverage,Cash flow from operations,Promoter holding,Pledged percentage,Price to Earning,Price to book value,Dividend yield',
  ...['PASSA', 'PASSB', 'PASSC', 'PASSD', 'PASSE'].map(
    (t) => `${t} Ltd,${t},Computers - Software,"Rs 1,500",5000,20%,20%,25%,25%,0.1,10,500,60%,0%,15,2,1%`,
  ),
  'Negative Equity Ltd,NEGEQ,Pharmaceuticals,1200,5000,20%,20%,25%,25%,-3.5,10,500,60%,0%,15,2,1%',
  'Depository Ltd,FINSVC,Financial - Services,1480,30900,28%,34%,38%,29%,0,145,410,15%,0%,55,17,1.3%',
].join('\n');

const SCREENS: ScreenSpec[] = [
  {
    label: 'edge_cases',
    csv: EDGE_CASE_CSV,
    app_config: { ...APP_CONFIG, top_n: 2 },
    screening_config: { ...SCREENING_CONFIG },
  },
  {
    label: 'na_words_crlf',
    csv: NA_WORDS_CSV,
    app_config: { ...APP_CONFIG },
    screening_config: { ...SCREENING_CONFIG },
  },
  {
    label: 'price_history',
    csv: SAMPLE_SCREENER_CSV_STRING,
    app_config: { ...APP_CONFIG, enable_technical_confirmation: true },
    screening_config: { ...SCREENING_CONFIG },
    price_csv: PRICE_CSV,
  },
  {
    label: 'custom_filters',
    csv: SAMPLE_SCREENER_CSV_STRING,
    app_config: {
      ...APP_CONFIG,
      custom_filters: [
        { field: 'roce', operator: '>', value: '30' },
        { field: 'peRatio', operator: '<=', value: '40.5' },
        { field: 'debtToEquity', operator: '<', value: '0.1' },
        { field: 'marketCap', operator: '>=', value: '1e5' },
      ],
    },
    screening_config: { ...SCREENING_CONFIG },
  },
  {
    label: 'nifty100_defaults',
    csv: SAMPLE_SCREENER_CSV_STRING,
    app_config: { ...DEFAULT_APP_CONFIG },
    screening_config: { ...DEFAULT_SCREENING_CONFIG },
  },
  {
    label: 'nifty100_with_prices',
    csv: SAMPLE_SCREENER_CSV_STRING,
    app_config: { ...DEFAULT_APP_CONFIG, minimum_total_score: 0 },
    screening_config: { ...DEFAULT_SCREENING_CONFIG },
    price_csv: PRICE_CSV,
  },
  {
    // A non-empty custom list, written the way a person would: mixed case,
    // stray spaces, a blank entry and a symbol that is not in the file.
    label: 'custom_universe',
    csv: SAMPLE_SCREENER_CSV_STRING,
    app_config: {
      ...APP_CONFIG,
      custom_symbols: [' tcs ', 'infy', '', 'SUNPHARMA', 'NOT-IN-FILE'],
      enable_technical_confirmation: true,
    },
    screening_config: { ...SCREENING_CONFIG },
    price_csv: PRICE_CSV,
  },
  {
    label: 'ticker_ties',
    csv: TIE_CSV,
    app_config: { ...APP_CONFIG },
    screening_config: { ...SCREENING_CONFIG },
  },
] as unknown as ScreenSpec[];

const ch = (...codes: number[]) => String.fromCharCode(...codes);

const NUMBER_CASES = [
  30, 30.5, -2, 0, 1e-7, 1e-6, 1e16, 1e21, 123456.789, 0.1 + 0.2, 5e-324,
  1.7976931348623157e308, 123e-20, 0.000001234, 100, 1e15 + 0.5, -0.0001,
];

const STRICT_DECIMAL_CASES = [
  '12', ' 12.5 ', '1e3', '-0.5', '+7', '.5', '5.', '0x10', '0b101', '0o17', '1_0',
  'inf', 'Infinity', 'nan', 'NaN', ch(0x661, 0x662), '', ' ', '1e', 'e5', '--1', '1e400',
];

const WHITESPACE_CASES = [
  `5${ch(0x1f)}`, `${ch(0xfeff)}5`, `${ch(0xa0)}5${ch(0x3000)}`, ' 5 ', `5${ch(0x85)}`,
  `${ch(0x2028)}5`, `${ch(0x1c)}5`,
];

const HEADER_CASES = [
  `Promoter${ch(0xa0)}holding ${ch(0xe9)}`, ` ROCE${ch(0x2003)}`, `Price${ch(0x1f)}to Earning`,
  `Market${ch(0x200b)}Cap`, 'Return  on\tequity',
];

const CONFIG_CASES: unknown[] = [
  {},
  { app: { top_n: 10, custom_symbols: [' tcs ', ''] }, screening: { minRocePct: 18 } },
  { app: { universe_mode: 'custom', enable_technical_confirmation: false } },
  { screening: { minSalesGrowthPct: -100, maxPeRatio: 500 } },
  { app: { top_n: 0 } },
  { app: { top_n: 2.5 } },
  { app: { paper_trading_only: true } },
  { screening: { minRocePct: '18' } },
  { screening: { minRocePct: true } },
  { screening: { requirePositiveOcf: 1 } },
  { screening: { minSalesGrowthPct: -100.5 } },
  { screening: { minPeRatio: 60, maxPeRatio: 55 } },
  { screening: { minPeRatio: 55, maxPeRatio: 55 } },
  { app: { custom_filters: [{ field: 'roce', operator: '>', value: '0b101' }] } },
  { app: { custom_filters: [null] } },
  {
    app: {
      custom_filters: [
        { field: null, operator: '>', value: 1 },
        { field: true, operator: '>', value: 1 },
        { field: 'roce', operator: '>', value: [1] },
        { field: 'roce', operator: 'exec', value: 1 },
        'roce > 1',
      ],
    },
  },
  { zzz: 1, 5: 2, app: { top_n: 5, b: 1, a: 2 } },
  { schema_version: 6 },
  { schema_version: 'v5' },
  { schema_version: null },
  { extra: {} },
  { app: null },
  [],
  null,
];

const PRICE_PARSE_CASES = [
  'Date,Ticker,Close\r\n2025-01-01,TCS,1\n2025-01-02,TCS,2\n',
  'Date,Ticker,Close\r2025-01-01,TCS,1\r2025-01-02,TCS,2\r',
  'Date\tTicker\tClose\n2025-01-01\tTCS\t1\n',
  'date;ticker;close\n2025-01-01;TCS;1\n',
  `${String.fromCharCode(0xfeff)}Date,Symbol,Close,Volume\n2025-02-29,TCS,1,\n2024-02-29,tcs,"1,5",7\n2024-02-28, TCS ,2,\n`,
  'Date,Ticker,Close\n"2025-01-01",TCS,"3"\n\n   \n',
  // The widened file, and one written before Open/High/Low existed. Both must
  // parse to the same key set in both engines, with the older file reporting
  // opens/highs/lows as absent rather than copying the close into them.
  'Date,Ticker,Open,High,Low,Close,Volume\n2025-01-01,TCS,99,105,98,104,1000\n2025-01-02,TCS,,,,102,\n',
  'Date,Ticker,Close,Volume\n2025-01-01,TCS,104,1000\n2025-01-02,TCS,102,\n',
  '',
];

/** Every compared field, as the Python driver reports it. */
function tsEvaluationFields(ev: StockEvaluation): Omit<ParityEvaluation, 'ticker'> {
  return {
    passed: ev.passed,
    score: ev.score,
    coverage: ev.coveragePct,
    reasons: ev.rejectionReasons,
    warningFlags: ev.warningFlags,
    categoryScores: {
      financialQuality: ev.categoryScores.financialQuality.score,
      growth: ev.categoryScores.growth.score,
      balanceSheetSafety: ev.categoryScores.balanceSheetSafety.score,
      valuation: ev.categoryScores.valuation.score,
      governance: ev.categoryScores.governance.score,
    },
    redFlags: ev.redFlags,
    notScored: ev.notScored,
    scoringModel: ev.scoringModel,
    scoreLines: ev.scoreLines,
    sectorGroup: ev.sectorGroup,
    techScore: ev.technicalScore.score,
    techBreakdown: ev.technicalScore.breakdown,
    dataStatus: ev.stock.technicals?.data_status ?? 'UNAVAILABLE',
    explanation: ev.explanation,
  };
}

function evaluationDifferences(tsEvaluations: StockEvaluation[], pyEvaluations: ParityEvaluation[]): string[] {
  const differences: string[] = [];
  if (tsEvaluations.length !== pyEvaluations.length) {
    differences.push(`count: ts=${tsEvaluations.length} py=${pyEvaluations.length}`);
  }
  const pyByTicker = new Map(pyEvaluations.map((e) => [e.ticker, e]));
  for (const ev of tsEvaluations) {
    const other = pyByTicker.get(ev.stock.ticker);
    if (!other) {
      differences.push(`${ev.stock.ticker}: absent from the Python result`);
      continue;
    }
    const ours = tsEvaluationFields(ev) as unknown as Record<string, unknown>;
    const theirs = other as unknown as Record<string, unknown>;
    for (const key of Object.keys(ours)) {
      if (JSON.stringify(ours[key]) !== JSON.stringify(theirs[key])) {
        differences.push(`${ev.stock.ticker}.${key}: ts=${JSON.stringify(ours[key])} py=${JSON.stringify(theirs[key])}`);
      }
    }
  }
  return differences;
}

let py: ParityPayload;
let ts: ReturnType<typeof processScreenerPipeline>;
let tsChanges: string;
const tsScreens: Record<string, { result: PipelineResult; history: PriceHistory | null; skipped: number | null }> = {};

beforeAll(() => {
  // If the sample literal and the imported constant ever diverge, both engines
  // would be fed different data and "parity" would be meaningless.
  expect(readSampleCsvFromSource()).toBe(SAMPLE_SCREENER_CSV_STRING);

  ts = processScreenerPipeline(parseCsv(SAMPLE_SCREENER_CSV_STRING), APP_CONFIG, SCREENING_CONFIG);
  const currentSnapshot: WatchlistSnapshotEntry[] = ts.watchlist.map((item, idx) => ({
    ticker: item.stock.ticker,
    name: item.stock.name,
    rank: item.rank ?? idx + 1,
    score: item.score,
    warningFlags: item.warningFlags,
  }));
  tsChanges = generateRankingChangesCsv(computeRankingChanges(currentSnapshot, DELTA_PREVIOUS));

  py = runPythonParity({
    csv: SAMPLE_SCREENER_CSV_STRING,
    app_config: APP_CONFIG as unknown as Record<string, unknown>,
    screening_config: SCREENING_CONFIG as unknown as Record<string, unknown>,
    expected_rows: EXPECTED_SAMPLE_ROWS,
    delta_fixture: {
      current: currentSnapshot as unknown as Record<string, unknown>[],
      previous: DELTA_PREVIOUS as unknown as Record<string, unknown>[],
    },
    unit_cases: UNIT_CASES,
    escape_cases: ESCAPE_CASES,
    technical_sizes: TECHNICAL_SIZES,
    mapping_cases: MAPPING_CASES,
    screens: SCREENS,
    number_cases: NUMBER_CASES,
    strict_decimal_cases: STRICT_DECIMAL_CASES,
    whitespace_cases: WHITESPACE_CASES,
    header_cases: HEADER_CASES,
    config_cases: CONFIG_CASES,
    price_parse_cases: PRICE_PARSE_CASES,
  });

  for (const spec of SCREENS) {
    const parsed = spec.price_csv === undefined ? null : parsePriceHistoryCsv(spec.price_csv);
    tsScreens[spec.label] = {
      result: processScreenerPipeline(
        parseCsv(spec.csv),
        spec.app_config as unknown as AppConfig,
        spec.screening_config as unknown as ScreeningConfig,
        undefined,
        parsed?.history ?? null,
      ),
      history: parsed?.history ?? null,
      skipped: parsed?.skipped ?? null,
    };
  }
});

describe('Cross-engine parity on all bundled sample companies', () => {
  it('both engines evaluated the same non-empty company set', () => {
    expect(ts.evaluations.length).toBe(EXPECTED_SAMPLE_ROWS);
    expect(py.evaluations.length).toBe(EXPECTED_SAMPLE_ROWS);

    const tsTickers = ts.evaluations.map((e) => e.stock.ticker).sort();
    const pyTickers = py.evaluations.map((e) => e.ticker).sort();
    expect(pyTickers).toEqual(tsTickers);
    expect(new Set(tsTickers).size).toBe(EXPECTED_SAMPLE_ROWS);
  });

  it('agrees exactly on ticker, pass/fail, score, coverage, reasons and warnings', () => {
    const pyByTicker = new Map(py.evaluations.map((e) => [e.ticker, e]));
    const differences: string[] = [];

    for (const evaluation of ts.evaluations) {
      const ticker = evaluation.stock.ticker;
      const other = pyByTicker.get(ticker);
      if (!other) {
        differences.push(`${ticker}: absent from the Python result`);
        continue;
      }
      if (evaluation.passed !== other.passed) {
        differences.push(`${ticker}.passed: ts=${evaluation.passed} py=${other.passed}`);
      }
      if (evaluation.score !== other.score) {
        differences.push(`${ticker}.score: ts=${evaluation.score} py=${other.score}`);
      }
      if (evaluation.coveragePct !== other.coverage) {
        differences.push(`${ticker}.coverage: ts=${evaluation.coveragePct} py=${other.coverage}`);
      }
      if (JSON.stringify(evaluation.rejectionReasons) !== JSON.stringify(other.reasons)) {
        differences.push(
          `${ticker}.reasons: ts=${JSON.stringify(evaluation.rejectionReasons)} py=${JSON.stringify(other.reasons)}`,
        );
      }
      if (JSON.stringify(evaluation.warningFlags) !== JSON.stringify(other.warningFlags)) {
        differences.push(
          `${ticker}.warnings: ts=${JSON.stringify(evaluation.warningFlags)} py=${JSON.stringify(other.warningFlags)}`,
        );
      }
      const tsCats = {
        financialQuality: evaluation.categoryScores.financialQuality.score,
        growth: evaluation.categoryScores.growth.score,
        balanceSheetSafety: evaluation.categoryScores.balanceSheetSafety.score,
        valuation: evaluation.categoryScores.valuation.score,
        governance: evaluation.categoryScores.governance.score,
      };
      if (JSON.stringify(tsCats) !== JSON.stringify(other.categoryScores)) {
        differences.push(
          `${ticker}.categoryScores: ts=${JSON.stringify(tsCats)} py=${JSON.stringify(other.categoryScores)}`,
        );
      }
    }

    expect(differences, `engines disagreed:\n${differences.join('\n')}`).toEqual([]);
  });

  it('agrees exactly on watchlist rank and ordering', () => {
    const tsOrder = ts.watchlist.map((item, idx) => ({
      ticker: item.stock.ticker,
      rank: item.rank ?? idx + 1,
      score: item.score,
    }));
    expect(py.watchlist).toEqual(tsOrder);

    // Ordering must be score desc, then ticker asc -- fully deterministic.
    for (let i = 1; i < tsOrder.length; i += 1) {
      const prev = tsOrder[i - 1];
      const curr = tsOrder[i];
      const ordered =
        prev.score > curr.score ||
        (prev.score === curr.score && compareCodePoints(prev.ticker, curr.ticker) < 0);
      expect(ordered, `rank ${i} out of order: ${prev.ticker}(${prev.score}) then ${curr.ticker}(${curr.score})`).toBe(true);
    }
    expect(tsOrder.map((r) => r.rank)).toEqual(tsOrder.map((_, i) => i + 1));
  });

  it('produces byte-identical watchlist and rejected CSVs', () => {
    expect(generateWatchlistCsv(ts.watchlist)).toBe(py.watchlist_csv);
    expect(generateRejectedCsv(ts.rejected)).toBe(py.rejected_csv);
  });

  it('produces byte-identical ranking-changes CSV from the same fixture', () => {
    expect(tsChanges).toBe(py.ranking_changes_csv);
    const header = tsChanges.split('\n')[0];
    expect(header).toBe(
      'Ticker,Name,ChangeType,PreviousRank,CurrentRank,RankDelta,PreviousScore,CurrentScore,ScoreDelta,NewWarnings',
    );
    // The fixture is built to exercise every change type.
    for (const type of ['NEW_ENTRY', 'RANK_UP', 'RANK_DOWN', 'REMOVED_ENTRY', 'STABLE']) {
      expect(tsChanges, `expected a ${type} row`).toContain(type);
    }
  });

  it('agrees on the deduplication count', () => {
    expect(py.duplicates_removed).toBe(ts.duplicatesCount);
  });
});

describe('Cross-engine parity on parsing and mapping', () => {
  it('agrees on unit-aware number parsing', () => {
    for (const testCase of UNIT_CASES) {
      const tsValue = cleanNumeric(testCase.value, testCase.unit);
      const pyValue = py.unit_parsing[testCase.label];
      const equal =
        tsValue === null || pyValue === null
          ? tsValue === pyValue
          : Math.abs(tsValue - (pyValue as number)) < 1e-12;
      expect(equal, `${testCase.label} ("${testCase.value}" as ${testCase.unit}): ts=${tsValue} py=${pyValue}`).toBe(true);
    }
    // Pin the documented crore contract explicitly.
    expect(py.unit_parsing.crore_1cr).toBe(1);
    expect(py.unit_parsing.crore_100lakh).toBe(1);
    expect(py.unit_parsing.crore_10lakh).toBeCloseTo(0.1, 12);
    expect(py.unit_parsing.percent_monetary).toBeNull();
    expect(py.unit_parsing.ratio_percent).toBeNull();
  });

  it('agrees on the CSV formula-injection guard', () => {
    for (const value of ESCAPE_CASES) {
      expect(py.csv_escapes[value], `escape of ${JSON.stringify(value)}`).toBe(escapeCsvCell(value));
    }
    expect(py.csv_escapes['=cmd|']).toBe("'=cmd|");
    expect(py.csv_escapes['  =leading']).toBe("'  =leading");
    expect(py.csv_escapes['Normal text']).toBe('Normal text');
  });

  it('agrees on 52-week-high availability at every threshold', () => {
    for (const n of TECHNICAL_SIZES) {
      const prices = Array.from({ length: n }, (_, i) => 100 + i * 0.5);
      const tsAvailable = computeTechnicalIndicators(prices).available.high52Week;
      expect(py.technical_availability[String(n)], `n=${n}`).toBe(tsAvailable);
      expect(tsAvailable, `n=${n} must be ${n >= 252}`).toBe(n >= 252);
    }
  });

  it('agrees on identifier-safe column resolution in every required case', () => {
    for (const testCase of MAPPING_CASES) {
      const tsMapping = detectColumnMapping(testCase.headers);
      expect(py.identifier_mappings[testCase.label], testCase.label).toEqual(tsMapping);
    }
    // The four required identifier outcomes, pinned.
    expect(py.identifier_mappings.nse_and_bse.ticker).toBe('NSE Code');
    expect(py.identifier_mappings.nse_and_bse.bseCode).toBe('BSE Code');
    expect(py.identifier_mappings.bse_only.ticker).toBe('BSE Code');
    expect(py.identifier_mappings.bse_only.bseCode).toBe('BSE Code');
    expect(py.identifier_mappings.nse_only.ticker).toBe('NSE Code');
    expect(py.identifier_mappings.nse_only.bseCode).toBeUndefined();
    // Header order must not change the outcome: same columns, opposite order.
    expect(py.identifier_mappings.reversed_order).toEqual(py.identifier_mappings.forward_order);
    expect(detectColumnMapping(['Price to Earning', 'BSE Code', 'NSE Code', 'Name'])).toEqual(
      detectColumnMapping(['Name', 'NSE Code', 'BSE Code', 'Price to Earning']),
    );
  });
});

describe('Cross-engine parity on the universe snapshot', () => {
  it('both engines carry the identical pinned symbol list', () => {
    expect(py.universe.count).toBe(100);
    expect(py.universe.symbols).toEqual([...NIFTY100_FALLBACK_SYMBOLS]);
    expect(new Set(py.universe.symbols).size).toBe(100);
  });

  it('both engines carry the identical provenance record', () => {
    expect(py.universe.provenance.source_url).toBe(NIFTY100_PROVENANCE.source_url);
    expect(py.universe.provenance.as_of_date).toBe(NIFTY100_PROVENANCE.as_of_date);
    expect(py.universe.provenance.retrieved_at_utc).toBe(NIFTY100_PROVENANCE.retrieved_at_utc);
    expect(py.universe.provenance.sha256_of_source_csv).toBe(NIFTY100_PROVENANCE.sha256_of_source_csv);
    expect(String(py.universe.provenance.sha256_of_source_csv)).toHaveLength(64);
  });
});

describe('Cross-engine parity on additional screens', () => {
  for (const spec of SCREENS) {
    describe(spec.label, () => {
      it('agrees on every evaluation field, including technicals and the rationale', () => {
        const differences = evaluationDifferences(tsScreens[spec.label].result.evaluations, py.screens[spec.label].evaluations);
        expect(differences, `engines disagreed:\n${differences.join('\n')}`).toEqual([]);
        expect(py.screens[spec.label].evaluations.length).toBeGreaterThan(0);
      });

      it('agrees on rank, ordering, counts and the exported CSVs', () => {
        const ours = tsScreens[spec.label].result;
        const theirs = py.screens[spec.label];
        expect(theirs.watchlist).toEqual(
          ours.watchlist.map((item, idx) => ({ ticker: item.stock.ticker, rank: item.rank ?? idx + 1, score: item.score })),
        );
        expect(theirs.passed_below_cutoff).toEqual(
          ours.passedBelowCutOff.map((item) => ({
            ticker: item.stock.ticker, rank: item.rank, score: item.score,
          })),
        );
        expect(theirs.duplicates_removed).toBe(ours.duplicatesCount);
        expect(theirs.outside_universe).toBe(ours.outsideUniverseCount);
        expect(theirs.price_rows_skipped).toBe(tsScreens[spec.label].skipped);
        expect(generateWatchlistCsv(ours.watchlist)).toBe(theirs.watchlist_csv);
        expect(generateWatchlistCsv(ours.passedBelowCutOff)).toBe(theirs.passed_below_csv);
        expect(generateRejectedCsv(ours.rejected)).toBe(theirs.rejected_csv);
      });
    });
  }

  it('computes bit-identical technical indicators from the same price file', () => {
    const { result, history } = tsScreens.price_history;
    const tickers = result.evaluations.map((e) => e.stock.ticker);
    const ours = JSON.parse(JSON.stringify(technicalsFromHistory(history as PriceHistory, tickers)));
    expect(py.screens.price_history.technicals).toEqual(ours);
  });

  it('exercises every technical situation it is meant to', () => {
    const byTicker = new Map(tsScreens.price_history.result.evaluations.map((e) => [e.stock.ticker, e]));
    expect(tsScreens.price_history.skipped).toBe(4);
    expect(byTicker.get('CLEAN')!.technicalScore.breakdown).toEqual([
      'Only 30 sessions of price history; indicators need at least 50',
    ]);
    expect(byTicker.get('BIKAJI')!.stock.technicals!.volumeRatio20D).toBeNull();
    const naWords = tsScreens.na_words_crlf.result.evaluations.map((e) => [e.stock.ticker, e.stock.name, e.stock.sector]);
    expect(naWords.slice(0, 2)).toEqual([['NA', 'None', 'N/A'], ['NULL', 'null', 'nan']]);
    expect(byTicker.get('TCS')!.stock.technicals!.data_status).toBe('COMPLETE');
    expect(byTicker.get('LT')!.stock.technicals!.data_status).toBe('COMPLETE');
    expect(byTicker.get('KPITTECH')!.stock.technicals!.data_status).toBe('PARTIAL');
    expect(byTicker.get('BEL')!.stock.technicals!.sma50).not.toBeNull();
    expect(byTicker.get('IDEA')!.warningFlags).toContain('Technical Data Missing');
    const noHistory = tsScreens.nifty100_defaults.result.evaluations;
    expect(noHistory.every((e) => e.technicalScore.breakdown[0] === 'No price history loaded')).toBe(true);
    expect(tsScreens.nifty100_defaults.result.outsideUniverseCount).toBe(sampleUniverseSplit().outside);
    expect(tsScreens.custom_filters.result.evaluations.some((e) => e.rejectionReasons.includes('roce <= 30'))).toBe(true);
  });

  it('agrees on the rules the edge-case screen exercises', () => {
    const ours = tsScreens.edge_cases.result;
    const byTicker = new Map(ours.evaluations.map((e) => [e.stock.ticker, e]));
    expect(byTicker.get('NEGEQ')!.redFlags).toEqual(['Negative net worth']);
    expect(byTicker.get('NEGEQ')!.rejectionReasons).not.toContain('High D/E');
    expect(byTicker.get('FINSVC')!.scoringModel).toBe('financial');
    expect(byTicker.get('FINSVC')!.notScored).toContain('missing bank metrics');
    expect(byTicker.get('PASSA')!.stock.currentPrice).toBe(1500);
    expect(ours.watchlist.map((e) => e.rank)).toEqual([1, 2]);
    expect(ours.passedBelowCutOff.map((e) => e.rank)).toEqual([3, 4, 5]);
  });

  it('applies a custom symbol list the same way in both engines', () => {
    const ours = tsScreens.custom_universe.result;
    // Normalised: " tcs " and "infy" match, the blank is dropped and the
    // symbol that is not in the file simply matches nothing.
    expect(ours.evaluations.map((e) => e.stock.ticker).sort()).toEqual(['INFY', 'SUNPHARMA', 'TCS']);
    expect(ours.outsideUniverseCount).toBe(sampleUniverseSplit().total - 3);
    expect(py.screens.custom_universe.evaluations.map((e) => e.ticker).sort())
      .toEqual(['INFY', 'SUNPHARMA', 'TCS']);
  });

  it('breaks score ties by code point, never by locale collation', () => {
    const order = tsScreens.ticker_ties.result.watchlist.map((e) => e.stock.ticker);
    expect(order).toEqual(['A&B', 'A-B', 'AA', 'AB', 'A_B', 'Z']);
    expect(py.screens.ticker_ties.watchlist.map((e) => e.ticker)).toEqual(order);
  });
});

describe('Cross-engine parity on price-file parsing', () => {
  it('parses every file identically: line endings, delimiters, BOM, quotes and bad dates', () => {
    PRICE_PARSE_CASES.forEach((text, i) => {
      let ours: unknown;
      try {
        const { history, skipped } = parsePriceHistoryCsv(text);
        ours = { error: false, history, skipped };
      } catch {
        ours = { error: true };
      }
      expect(py.price_parse_results[i], JSON.stringify(text)).toEqual(JSON.parse(JSON.stringify(ours)));
    });
    expect(py.price_parse_results.filter((r) => r.error)).toHaveLength(3);
  });
});

describe('Cross-engine parity on number and text shapes', () => {
  it('writes numbers into text identically', () => {
    expect(py.number_text).toEqual(NUMBER_CASES.map((n) => String(n)));
  });

  it('accepts exactly the same strict decimals', () => {
    expect(py.strict_decimals).toEqual(STRICT_DECIMAL_CASES.map(parseStrictDecimal));
  });

  it('treats exactly the same characters as whitespace', () => {
    expect(py.whitespace_numbers).toEqual(WHITESPACE_CASES.map((s) => cleanNumeric(s, 'ratio')));
    expect(py.trimmed).toEqual(WHITESPACE_CASES.map((s) => s.trim()));
    expect(py.headers).toEqual(HEADER_CASES.map(normalizeHeader));
  });
});

describe('Cross-engine parity on saved configuration', () => {
  it('uses identical setting ranges', () => {
    expect(py.config_limits).toEqual(
      Object.fromEntries(Object.entries(CONFIG_LIMITS).map(([key, v]) => [key, [v.min, v.max]])),
    );
  });

  it('accepts, rejects and merges every document identically', () => {
    CONFIG_CASES.forEach((doc, i) => {
      const ours = validateConfigDocument(doc);
      const theirs = py.config_results[i];
      expect(theirs.valid, JSON.stringify(doc)).toBe(ours.errors.length === 0);
      expect(theirs.errors, JSON.stringify(doc)).toEqual(ours.errors);
      if (theirs.valid) {
        expect(theirs.app, JSON.stringify(doc)).toEqual(ours.app);
        expect(theirs.screening, JSON.stringify(doc)).toEqual(ours.screening);
      }
    });
    expect(py.config_results.filter((r) => r.valid)).toHaveLength(5);
  });
});
