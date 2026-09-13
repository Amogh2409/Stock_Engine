/**
 * Browser screening engine.
 *
 * This file is the TypeScript half of a two-engine system; python/engine.py is
 * the other. Every scoring, parsing, sorting, CSV and delta rule below has a
 * one-to-one counterpart there, and src/tests/parity.test.ts asserts the two
 * agree exactly on all 31 bundled sample companies.
 *
 * Two conventions make that parity possible and MUST NOT be changed on one
 * side only:
 *   1. round1() -- one decimal, half-up, implemented as Math.round(x*10)/10,
 *      which is bit-identical to Python's floor(x*10 + 0.5)/10 on the same
 *      IEEE-754 double. Scores drive rank order, so a rounding difference is a
 *      ranking difference, not a display difference.
 *   2. Watchlists sort by score descending, then ticker ascending.
 */
import * as Papa from 'papaparse';

import {
  NIFTY100_FALLBACK_SYMBOLS,
  NIFTY100_PROVENANCE,
} from '../data/nifty100Snapshot';
import {
  AppConfig,
  CategoryScore,
  CleanedStock,
  ColumnProfile,
  DataInspectionReport,
  FilterOperator,
  RankingChange,
  RelativeStrengthBucket,
  ScreenerRow,
  ScreeningConfig,
  SectorMedian,
  SectorMedians,
  SectorRelativeStrength,
  StockEvaluation,
  TechnicalAvailability,
  TechnicalBlocks,
  TechnicalIndicators,
  TechnicalScoreResult,
  WatchlistSnapshotEntry,
} from '../types';

export { NIFTY100_FALLBACK_SYMBOLS, NIFTY100_PROVENANCE };

export const SCHEMA_VERSION = 'v6';

// ---------------------------------------------------------------------------
// Numeric helpers and canonical rounding
// ---------------------------------------------------------------------------

export function clamp(val: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, val));
}

/**
 * Canonical score rounding: one decimal place, half-up.
 * Counterpart of round1() in python/engine.py.
 */
export function round1(value: number): number;
export function round1(value: null | undefined): null;
export function round1(value: number | null | undefined): number | null;
export function round1(value: number | null | undefined): number | null {
  if (value === null || value === undefined) return null;
  return Math.round(value * 10) / 10;
}

/** Fixed-precision string used by every CSV writer in both engines. */
export function fmt1(value: number | null | undefined): string {
  const rounded = round1(value);
  return rounded === null ? '' : rounded.toFixed(1);
}

/**
 * Code-point string order, which is what Python's `<` uses. localeCompare is
 * locale-dependent collation ("A_B" sorts before "AB" under ICU, after it by
 * code point) and plain `<` compares UTF-16 units, so neither may be used to
 * order anything the Python engine also orders.
 */
export function compareCodePoints(a: string, b: string): number {
  const x = Array.from(a);
  const y = Array.from(b);
  const n = Math.min(x.length, y.length);
  for (let i = 0; i < n; i += 1) {
    const diff = (x[i].codePointAt(0) ?? 0) - (y[i].codePointAt(0) ?? 0);
    if (diff !== 0) return diff;
  }
  return x.length - y.length;
}

/** JSON.stringify, writing undefined as null (Python's None). Counterpart of _json_text(). */
export function jsonText(value: unknown): string {
  return JSON.stringify(value) ?? 'null';
}

/**
 * Strict scalar -> number. Counterpart of parse_strict_decimal().
 *
 * Finite numbers pass through. Strings must match NUMERIC_BODY_RE, the
 * ASCII-only decimal shape both engines pin, so hex (0x10), binary (0b101),
 * octal (0o17), underscore separators (1_0), Infinity/NaN and non-ASCII digits
 * are rejected identically -- Number() and Python's float() each accept some of
 * those and not others.
 */
export function parseStrictDecimal(val: unknown): number | null {
  if (typeof val === 'number') return Number.isFinite(val) ? val : null;
  if (typeof val !== 'string') return null;
  const text = val.trim();
  if (!NUMERIC_BODY_RE.test(text)) return null;
  const num = Number(text);
  return Number.isFinite(num) ? num : null;
}

// ---------------------------------------------------------------------------
// Unit-aware numeric parsing
// ---------------------------------------------------------------------------

/**
 * Declared unit of a source column. Screener.in exports monetary columns in
 * rupee crore, so "100 LAKH" must resolve to 1 crore -- not to 100.
 */
export type FieldUnit = 'crore' | 'percent' | 'ratio' | 'price' | 'plain';

const MONETARY_SUFFIX_RE = /(CRORES|CRORE|CRS|CR|LAKHS|LAKH|LACS|LAC)$/;
/**
 * The cleaned body must be a plain decimal. This deliberately rejects hex
 * (0x10), underscore separators (1_0), "inf" and "nan" -- all of which one
 * language's number parser accepts and the other's does not. Pinning the
 * accepted shape here is what keeps the two engines in agreement.
 */
const NUMERIC_BODY_RE = /^[+-]?(?:[0-9]+\.?[0-9]*|\.[0-9]+)(?:[eE][+-]?[0-9]+)?$/;
/**
 * JavaScript's \s (and String.prototype.trim) is exactly the WhiteSpace +
 * LineTerminator set; python/engine.py spells that set out as _WS_CHARS
 * because Python's own \s differs at the edges.
 */
const CURRENCY_CHARS_RE = /[₹$€£,"'\s]/g;
/**
 * Rupee words written in front of a price ("Rs 1,500", "Rs. 1,500", "INR 1500").
 * Applied after the currency characters and spaces are stripped, so the text is
 * already upper-cased and closed up. Counterpart of _CURRENCY_PREFIX_RE.
 */
const CURRENCY_PREFIX_RE = /^(?:RS\.?|INR)/;

/**
 * Unit-aware parser. Counterpart of clean_numeric() in python/engine.py.
 *
 *   cleanNumeric('1 CRORE',  'crore')   ->  1
 *   cleanNumeric('100 LAKH', 'crore')   ->  1
 *   cleanNumeric('10 LAKH',  'crore')   ->  0.1
 *   cleanNumeric('15.5%',    'percent') ->  15.5
 *   cleanNumeric('15 CR',    'percent') ->  null  (monetary on a percentage)
 *   cleanNumeric('0.5%',     'ratio')   ->  null  (percent on a ratio)
 *
 * An unexpected suffix is a rejection, never a silent strip.
 */
export function cleanNumeric(value: unknown, unit: FieldUnit = 'plain'): number | null {
  if (value === null || value === undefined || value === '') return null;
  if (typeof value === 'boolean') return null;
  if (typeof value === 'number') {
    return Number.isFinite(value) ? value : null;
  }

  const text = String(value).toUpperCase().trim();
  if (text === '') return null;

  const hasPercent = text.includes('%');
  let body = text.replace(CURRENCY_CHARS_RE, '').replace(/%/g, '').replace(CURRENCY_PREFIX_RE, '');

  let multiplier = 1;
  const suffixMatch = MONETARY_SUFFIX_RE.exec(body);
  const hasMonetary = suffixMatch !== null;
  if (suffixMatch) {
    body = body.slice(0, suffixMatch.index);
    // 100 lakh == 1 crore
    multiplier = suffixMatch[1].startsWith('LA') ? 0.01 : 1;
  }

  if (unit === 'crore') {
    if (hasPercent) return null;
  } else if (unit === 'percent' || unit === 'ratio' || unit === 'price') {
    if (hasMonetary) return null;
    multiplier = 1;
    if ((unit === 'ratio' || unit === 'price') && hasPercent) return null;
  } else {
    multiplier = 1;
  }

  if (!NUMERIC_BODY_RE.test(body)) return null;
  const num = Number(body);
  if (Number.isNaN(num) || !Number.isFinite(num)) return null;
  return num * multiplier;
}

// ---------------------------------------------------------------------------
// Spreadsheet formula-injection guard
// ---------------------------------------------------------------------------

const DANGEROUS_LEAD = ['=', '+', '-', '@'];

/**
 * Neutralise formula injection in a *string* cell: if the first non-whitespace
 * character is = + - or @, prefix an apostrophe. Numbers pass through
 * untouched so genuine numeric columns stay numeric in the exported file.
 * Counterpart of escape_csv_cell() in python/engine.py.
 */
export function escapeCsvCell(value: unknown): string {
  if (value === null || value === undefined) return '';
  if (typeof value === 'number' || typeof value === 'bigint') return String(value);
  const text = String(value);
  const lead = text.replace(/^\s+/, '').charAt(0);
  return DANGEROUS_LEAD.includes(lead) ? `'${text}` : text;
}

/** RFC4180 minimal quoting, applied after the injection guard. */
function csvQuote(text: string): string {
  if (text.includes(',') || text.includes('"') || text.includes('\n') || text.includes('\r')) {
    return `"${text.replace(/"/g, '""')}"`;
  }
  return text;
}

function csvRow(cells: string[]): string {
  return cells.map(csvQuote).join(',');
}

/** Text cell: guard then quote. */
function textCell(value: unknown): string {
  return escapeCsvCell(value);
}

// ---------------------------------------------------------------------------
// Column resolution
// ---------------------------------------------------------------------------

const COLUMN_ALIASES: Record<string, string[]> = {
  name: ['name', 'company name', 'company'],
  sector: ['industry', 'sector', 'industry/sector'],
  currentPrice: ['current price', 'cmp', 'close price', 'market price', 'price'],
  marketCap: ['market capitalization', 'market cap', 'mcap', 'mar cap'],
  salesGrowth: ['sales growth 3years', 'sales growth', 'sales var 3yrs'],
  profitGrowth: ['profit growth 3years', 'profit growth', 'pat growth 3years', 'net profit growth'],
  roce: ['return on capital employed', 'roce'],
  roe: ['return on equity', 'roe'],
  debtToEquity: ['debt to equity', 'debt / equity', 'debt/equity ratio', 'd/e'],
  interestCoverage: ['interest coverage ratio', 'interest coverage', 'icr'],
  operatingCashFlow: [
    'cash flow from operations',
    'cash from operating activity',
    'operating cash flow',
    'cfo',
    'ocf',
  ],
  promoterHolding: ['promoter holding', 'promoter holding %'],
  promoterPledge: ['pledged percentage', 'promoter pledge', 'pledge %'],
  peRatio: ['price to earning', 'price to earnings', 'price/earnings', 'stock p/e', 'p/e ratio', 'p/e', 'pe ratio', 'pe'],
  pbRatio: ['price to book value', 'price to book', 'p/b ratio', 'p/b', 'pb ratio', 'pb'],
  dividendYield: ['dividend yield', 'div yield'],
  // Optional. Present only in exports that carry an absolute revenue column;
  // "Sales growth 3Years" is a percentage and is a different field.
  sales: ['sales', 'revenue', 'total revenue', 'total income'],
  // --- Financial-company metrics (banks, NBFCs). Optional everywhere else. ---
  // Screener.in spells these differently across screens, so each carries the
  // spellings seen in the wild; normalizeHeader() strips the trailing "%".
  returnOnAssets: ['return on assets', 'roa'],
  grossNpa: ['gross npa', 'gross npa percentage'],
  netNpa: ['net npa', 'net npa percentage'],
  capitalAdequacy: ['capital adequacy ratio', 'capital adequacy', 'car', 'crar'],
  casa: ['casa', 'casa ratio'],
  // Screener.in has no "net interest margin" ratio; "Financing Margin %" is
  // its nearest equivalent and is labelled as such wherever it is reported.
  financingMargin: ['financing margin', 'net interest margin', 'nim'],
};

const TICKER_PRIMARY_ALIASES = ['nse code', 'nse symbol', 'symbol', 'ticker', 'nse', 'code'];
const BSE_CODE_ALIASES = ['bse code', 'scrip code', 'bse id', 'bse'];

const EXACT_ONLY_ALIASES = new Set([
  'pe', 'pb', 'roe', 'roce', 'ocf', 'cfo', 'icr', 'd/e', 'p/e', 'p/b',
  'cmp', 'code', 'nse', 'bse', 'price', 'company', 'name',
  // 'sales' would otherwise partial-match "Sales growth 3Years"; 'car' would
  // match "Cars", 'nim'/'roa'/'casa' are short enough to collide by accident.
  'sales', 'roa', 'car', 'crar', 'casa', 'nim',
]);

export const FIELD_UNITS: Record<string, FieldUnit> = {
  currentPrice: 'price',
  marketCap: 'crore',
  operatingCashFlow: 'crore',
  salesGrowth: 'percent',
  profitGrowth: 'percent',
  roce: 'percent',
  roe: 'percent',
  promoterHolding: 'percent',
  promoterPledge: 'percent',
  dividendYield: 'percent',
  debtToEquity: 'ratio',
  interestCoverage: 'ratio',
  peRatio: 'ratio',
  pbRatio: 'ratio',
  sales: 'crore',
  returnOnAssets: 'percent',
  grossNpa: 'percent',
  netNpa: 'percent',
  capitalAdequacy: 'percent',
  casa: 'percent',
  financingMargin: 'percent',
};

const ZERO_WIDTH_RE = /[​-‍﻿]/g;
/** Spelled A-Za-z0-9_ to match _NON_WORD_RE in python/engine.py exactly. */
const NON_WORD_RE = /[^A-Za-z0-9_\s/]/g;
const WHITESPACE_RE = /\s+/g;

export function normalizeHeader(text: string): string {
  return String(text)
    .toLowerCase()
    .trim()
    .replace(ZERO_WIDTH_RE, '')
    .replace(NON_WORD_RE, '')
    .replace(WHITESPACE_RE, ' ')
    .trim();
}

function escapeRegExp(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

/** Best alias match as [kind, rank]; kind 0 = exact, 1 = word-boundary partial. */
function matchRank(normalizedHeader: string, aliases: string[]): [number, number] | null {
  let best: [number, number] | null = null;
  aliases.forEach((alias, rank) => {
    const aliasNorm = normalizeHeader(alias);
    if (!aliasNorm) return;
    let candidate: [number, number] | null = null;
    if (normalizedHeader === aliasNorm) {
      candidate = [0, rank];
    } else if (EXACT_ONLY_ALIASES.has(alias)) {
      return;
    } else if (new RegExp(`\\b${escapeRegExp(aliasNorm)}\\b`).test(normalizedHeader)) {
      candidate = [1, rank];
    }
    if (!candidate) return;
    if (!best || candidate[0] < best[0] || (candidate[0] === best[0] && candidate[1] < best[1])) {
      best = candidate;
    }
  });
  return best;
}

/**
 * Map canonical field names to actual CSV column names. Deterministic and
 * independent of column order. Counterpart of resolve_columns().
 *
 *   'NSE Code' + 'BSE Code' -> ticker=NSE Code, bseCode=BSE Code
 *   'BSE Code' only         -> ticker=BSE Code, bseCode=BSE Code (shared)
 *   'NSE Code' only         -> ticker=NSE Code, no bseCode
 */
export function detectColumnMapping(headers: string[]): Record<string, string> {
  const normalized = headers.map(normalizeHeader);
  const mapping: Record<string, string> = {};
  const claimed = new Set<number>();

  type Cand = { kind: number; rank: number; idx: number };
  const bseCands: Cand[] = [];
  const tickerCands: Cand[] = [];

  normalized.forEach((norm, idx) => {
    if (!norm) return;
    const bseHit = matchRank(norm, BSE_CODE_ALIASES);
    if (bseHit) bseCands.push({ kind: bseHit[0], rank: bseHit[1], idx });
    const tickHit = matchRank(norm, TICKER_PRIMARY_ALIASES);
    if (tickHit) tickerCands.push({ kind: tickHit[0], rank: tickHit[1], idx });
  });

  const byPriority = (a: Cand, b: Cand) =>
    a.kind - b.kind || a.rank - b.rank || a.idx - b.idx;

  const bseIdxs = new Set(bseCands.map((c) => c.idx));
  // A BSE column is never eligible as the primary ticker.
  const tickerPrimary = tickerCands.filter((c) => !bseIdxs.has(c.idx));

  if (bseCands.length) {
    const best = [...bseCands].sort(byPriority)[0];
    mapping.bseCode = headers[best.idx];
    claimed.add(best.idx);
  }
  if (tickerPrimary.length) {
    const best = [...tickerPrimary].sort(byPriority)[0];
    mapping.ticker = headers[best.idx];
    claimed.add(best.idx);
  } else if (mapping.bseCode) {
    // Only a BSE column exists: share it as the ticker fallback so both the
    // usable ticker and bseCode stay available for deduplication.
    mapping.ticker = mapping.bseCode;
  }

  const fieldOrder = Object.keys(COLUMN_ALIASES);
  for (const kindPass of [0, 1]) {
    const candidates: { rank: number; order: number; idx: number; field: string }[] = [];
    fieldOrder.forEach((field, order) => {
      if (mapping[field]) return;
      normalized.forEach((norm, idx) => {
        if (!norm || claimed.has(idx)) return;
        const hit = matchRank(norm, COLUMN_ALIASES[field]);
        if (!hit || hit[0] !== kindPass) return;
        candidates.push({ rank: hit[1], order, idx, field });
      });
    });
    candidates
      .sort((a, b) => a.rank - b.rank || a.order - b.order || a.idx - b.idx)
      .forEach(({ idx, field }) => {
        if (mapping[field] || claimed.has(idx)) return;
        mapping[field] = headers[idx];
        claimed.add(idx);
      });
  }

  return mapping;
}

/**
 * Parse a fundamentals CSV. Line endings are normalised and the delimiter is
 * pinned to a comma instead of sniffed, matching pandas.read_csv in
 * read_fundamentals_csv().
 */
export function parseCsv(csvString: string): ScreenerRow[] {
  const parsed = Papa.parse<ScreenerRow>(csvString.replace(/\r\n?/g, '\n'), {
    header: true,
    skipEmptyLines: true,
    dynamicTyping: false,
    delimiter: ',',
    newline: '\n',
  });
  return (parsed.data || []) as ScreenerRow[];
}

// ---------------------------------------------------------------------------
// Position sizing defaults
// ---------------------------------------------------------------------------
// Declared above DEFAULT_APP_CONFIG because that object needs them. The
// reasoning behind each, and what it does not rest on, is beside sizePositions()
// below and in knowledge/rulebook.md. Counterparts in python/engine.py.

/**
 * TSaM p.53 offers 12%, calling it "a modest risk level"; p.1048 offers
 * "typically about 15%" and then calls 15% aggressive in its own worked
 * example. Amogh chose 12% from that range. Recorded as a choice between two
 * figures the book gives, not as a derivation -- a later reader should see both
 * the range and that a human picked within it.
 */
export const DEFAULT_TARGET_VOLATILITY_PCT = 12.0;

/**
 * Convention, both of them. TSaM p.1040 warns that a portfolio concentrating on
 * fewer groups carries greater risk, which is the argument FOR having caps; it
 * names no level, so these two numbers are ours. They matter because the p.1032
 * risk ceiling is not a concentration limit: at a 6% stop it permits 83% of
 * capital in a single name, so without these a fully "compliant" portfolio
 * could hold three positions.
 */
export const DEFAULT_MAX_POSITION_WEIGHT_PCT = 10.0;
export const DEFAULT_MAX_SECTOR_WEIGHT_PCT = 25.0;

// ---------------------------------------------------------------------------
// Defaults
// ---------------------------------------------------------------------------

export const DEFAULT_APP_CONFIG: AppConfig = {
  universe_mode: 'nifty100',
  custom_symbols: [],
  custom_filters: [],
  top_n: 20,
  // PROVISIONAL, not a validated figure. Lowered from 65 so that widening the
  // quality and growth scales did not silently tighten the screen: the scales
  // moved every score down, so the threshold had to move with them or the
  // default would start rejecting companies that used to qualify. That
  // rescaling argument holds, but this particular number does not rest on
  // anything solid -- it was picked so the bundled sample passes the same 9 of
  // 11 companies it passed at 65, and that sample's figures are invented.
  // Recalibrate against a real Screener.in export, or when the composite score
  // takes over what this threshold gates.
  minimum_total_score: 50,
  fundamentals_stale_after_days: 30,
  enable_technical_confirmation: true,
  // Share of the composite the technical half carries; the fundamental half
  // takes the remainder, so one knob cannot produce weights that fail to sum to
  // 100. The split itself is untested against returns -- a backtest is what
  // would justify a number here.
  technical_weight_pct: 40,
  // Off by default: every company that survives the hard red flags is scored
  // and ranked. Turning this on re-applies the old pass/fail hurdles (minimum
  // ROCE, growth, leverage, valuation and so on) as a filter over that ranked
  // list, rather than as the only way to appear in it.
  strict_screen: false,
  // Position sizing. See the constants above for the sources: the target is a
  // choice between two figures TSaM offers (12% at p.53, "typically about 15%"
  // at p.1048), and the two caps are convention built on p.1040's warning about
  // concentration rather than on any level it states. The 5% per-position RISK
  // ceiling from p.1032 is deliberately NOT here: a setting that let a config
  // file exceed the book's hard limit would make the limit decorative.
  target_volatility_pct: DEFAULT_TARGET_VOLATILITY_PCT,
  max_position_weight_pct: DEFAULT_MAX_POSITION_WEIGHT_PCT,
  max_sector_weight_pct: DEFAULT_MAX_SECTOR_WEIGHT_PCT,
};

export const DEFAULT_SCREENING_CONFIG: ScreeningConfig = {
  minMarketCapCr: 1000,
  minSalesGrowthPct: 10.0,
  minProfitGrowthPct: 12.0,
  minRocePct: 15.0,
  minRoePct: 15.0,
  maxDebtToEquity: 1.0,
  minInterestCoverage: 3.0,
  requirePositiveOcf: true,
  minPromoterHoldingPct: 40.0,
  maxPromoterPledgePct: 10.0,
  minPeRatio: 5.0,
  maxPeRatio: 55.0,
  maxPbRatio: 12.0,
  minDividendYieldPct: 0.2,
  minimum_fundamental_coverage: 80.0,
};

export const ALLOWED_FILTER_FIELDS = [
  'marketCap', 'salesGrowth', 'profitGrowth', 'roce', 'roe', 'debtToEquity',
  'interestCoverage', 'operatingCashFlow', 'promoterHolding', 'promoterPledge',
  'peRatio', 'pbRatio', 'dividendYield',
] as const;

export const ALLOWED_FILTER_OPERATORS: FilterOperator[] = ['>', '<', '>=', '<=', '==', '!='];

/**
 * Sector/industry text marking a company as financial-sector. Screener.in has
 * many names for them ("Financial - Services", "Capital Markets", "Stock
 * Brokers", "Other Financial Services", ...) and the leverage and cash-flow
 * rules transfer to none of them. "financ" covers Finance/Financial/Financing/
 * Microfinance, "brok" covers broker/broking/brokerage, "insur" insurance and
 * insurers. "capital market" is spelled in full so "Capital Goods" is untouched.
 * Counterpart of FINANCIAL_SECTOR_TERMS in python/engine.py.
 */
export const FINANCIAL_SECTOR_TERMS = [
  'bank', 'financ', 'nbfc', 'insur', 'brok', 'capital market', 'asset management',
  'mutual fund', 'depositor', 'securities', 'stock exchange', 'wealth management',
  'lending',
];
const FINANCIAL_SECTOR_RE = new RegExp(FINANCIAL_SECTOR_TERMS.join('|'), 'i');

// --- Sector grouping -------------------------------------------------------
/**
 * Coarse groups, used when a Screener.in industry label is too thin to give a
 * meaningful median. Screener's labels are fine-grained ("FMCG - Food", "FMCG -
 * Household Products", "Metals - Non Ferrous"), so a 100-row export splits into
 * roughly 25 industries and most of them hold one or two companies.
 *
 * ORDER IS LOAD-BEARING. The first group with a matching term wins, so a group
 * is listed before any later one whose terms would also match it:
 *   "Cables - Power"      -> Industrials (cable), before Utilities (power)
 *   "Industrial Minerals" -> Metals & Mining (mineral), before Industrials
 *
 * Terms match at a word boundary and may be prefixes ("alumini" covers
 * aluminium and aluminum, "chemical" covers Chemicals). The leading boundary is
 * what stops "oil" matching "boiler" and "port" matching "airport". Every term
 * must stay plain lowercase letters and spaces -- no regex metacharacters --
 * because the two engines build this pattern without an escaping step.
 * Counterpart of SECTOR_GROUP_TERMS in python/engine.py.
 */
export const SECTOR_GROUP_FINANCIALS = 'Financials';
export const SECTOR_GROUP_TERMS: readonly (readonly [string, readonly string[]])[] = [
  ['Information Technology', ['computers', 'software', 'information technology',
    'it services', 'bpo']],
  ['Healthcare', ['pharma', 'healthcare', 'hospital', 'diagnostic', 'biotech',
    'medical', 'drug']],
  ['Automobile', ['automobile', 'auto component', 'auto ancillar', 'tyre',
    'two wheeler', 'commercial vehicle', 'passenger vehicle']],
  ['Metals & Mining', ['metal', 'steel', 'mining', 'mineral', 'zinc',
    'alumini', 'copper', 'ferrous']],
  ['Construction Materials', ['cement', 'tiles', 'ceramic', 'asbestos']],
  ['Chemicals', ['chemical', 'fertilis', 'fertiliz', 'paint', 'plastic', 'polymer']],
  ['Energy', ['oil', 'gas', 'petroleum', 'refiner', 'coal', 'energy']],
  ['Consumer Durables', ['consumer electronic', 'consumer durable', 'watches',
    'footwear', 'appliance', 'furniture', 'jewel']],
  ['FMCG', ['fmcg', 'beverage', 'tobacco', 'cigarette', 'personal product',
    'household product', 'sugar', 'dairy']],
  ['Consumer Services', ['retail', 'hotel', 'restaurant', 'travel', 'airline',
    'aviation', 'media', 'entertainment', 'education']],
  ['Telecommunication', ['telecom']],
  ['Realty', ['realty', 'real estate']],
  ['Industrials', ['capital goods', 'engineering', 'abrasive', 'defence',
    'infrastructure', 'cable', 'bearing', 'compressor',
    'industrial', 'logistic', 'port', 'trading', 'packaging',
    'construction', 'textile', 'paper']],
  ['Utilities', ['power', 'electric', 'utility', 'renewable']],
];
const SECTOR_GROUP_RES: [string, RegExp][] = SECTOR_GROUP_TERMS.map(
  ([name, terms]) => [name, new RegExp(`\\b(?:${terms.join('|')})`, 'i')],
);

/**
 * Coarse group for a Screener.in industry label, or null if nothing matches.
 *
 * Financials is decided by FINANCIAL_SECTOR_RE itself rather than by a separate
 * term list, so a company's group can never disagree with whether the engine
 * treats it as a financial company. Counterpart of sector_group().
 */
export function sectorGroup(sector: string | null | undefined): string | null {
  const text = sector || '';
  if (FINANCIAL_SECTOR_RE.test(text)) return SECTOR_GROUP_FINANCIALS;
  for (const [name, pattern] of SECTOR_GROUP_RES) {
    if (pattern.test(text)) return name;
  }
  return null;
}

// --- Valuation yardsticks from the loaded file -----------------------------
/**
 * Smallest bucket that may serve as a median. Below this the comparison says
 * more about the sample than about the company.
 */
export const MIN_MEDIAN_SAMPLE = 5;
const MEDIAN_COUNT_KEYS: Record<string, 'peCount' | 'pbCount'> = {
  peRatio: 'peCount',
  pbRatio: 'pbCount',
};
const MEDIAN_LABELS: Record<string, string> = { peRatio: 'P/E', pbRatio: 'P/B' };

/** Middle value, or the mean of the two middle ones. Null when empty. */
function median(values: readonly number[]): number | null {
  const ordered = [...values].sort((a, b) => a - b);
  const count = ordered.length;
  if (count === 0) return null;
  const mid = Math.floor(count / 2);
  if (count % 2 === 1) return ordered[mid];
  return (ordered[mid - 1] + ordered[mid]) / 2;
}

interface MedianEntries {
  pe: number[];
  pb: number[];
}

function medianBucket(entries: MedianEntries): SectorMedian {
  return {
    peRatio: median(entries.pe),
    pbRatio: median(entries.pb),
    peCount: entries.pe.length,
    pbCount: entries.pb.length,
  };
}

/**
 * P/E and P/B yardsticks for the loaded file: by industry, by group, overall.
 *
 * Only positive ratios feed a median. A negative P/E is a loss and a negative
 * P/B is negative net worth; neither is a cheap valuation, and both would drag
 * the yardstick the wrong way. Counterpart of sector_medians().
 */
export function sectorMedians(stocks: readonly CleanedStock[]): SectorMedians {
  const industries = new Map<string, MedianEntries>();
  const groups = new Map<string, MedianEntries>();
  const universe: MedianEntries = { pe: [], pb: [] };
  const bucketFor = (store: Map<string, MedianEntries>, key: string) => {
    let entry = store.get(key);
    if (!entry) {
      entry = { pe: [], pb: [] };
      store.set(key, entry);
    }
    return entry;
  };

  for (const stock of stocks) {
    const industry = (stock.sector || '').trim();
    const group = sectorGroup(industry);
    const { peRatio: pe, pbRatio: pb } = stock;
    const buckets: MedianEntries[] = [universe];
    if (industry) buckets.push(bucketFor(industries, industry));
    if (group) buckets.push(bucketFor(groups, group));
    for (const bucket of buckets) {
      if (pe !== null && pe > 0) bucket.pe.push(pe);
      if (pb !== null && pb > 0) bucket.pb.push(pb);
    }
  }

  const asRecord = (store: Map<string, MedianEntries>) => {
    const out: Record<string, SectorMedian> = {};
    for (const [name, entries] of store) out[name] = medianBucket(entries);
    return out;
  };
  return {
    byIndustry: asRecord(industries),
    byGroup: asRecord(groups),
    universe: medianBucket(universe),
  };
}

/**
 * [median, basis text] for one metric: industry, else group, else universe.
 *
 * A bucket is used only when at least MIN_MEDIAN_SAMPLE companies in it report
 * the metric. The basis text always names which bucket was used and why, so a
 * fallback can never be mistaken for a true sector comparison. Counterpart of
 * valuation_yardstick().
 */
export function valuationYardstick(
  medians: SectorMedians,
  sector: string | null | undefined,
  metric: 'peRatio' | 'pbRatio',
): [number | null, string] {
  const countKey = MEDIAN_COUNT_KEYS[metric];
  const industry = (sector || '').trim();
  const group = sectorGroup(industry);
  const industryBucket = ownEntry(medians.byIndustry, industry);
  const groupBucket = group === null ? undefined : ownEntry(medians.byGroup, group);

  const value = industryBucket ? industryBucket[metric] : null;
  const count = industryBucket ? industryBucket[countKey] : 0;
  if (value !== null && count >= MIN_MEDIAN_SAMPLE) {
    return [value, `${industry} median ${fmt1(value)} (n=${count})`];
  }

  const groupValue = groupBucket ? groupBucket[metric] : null;
  const groupCount = groupBucket ? groupBucket[countKey] : 0;
  if (groupValue !== null && groupCount >= MIN_MEDIAN_SAMPLE) {
    return [groupValue, `${group} group median ${fmt1(groupValue)} (industry n=${count})`];
  }

  const universeValue = medians.universe[metric];
  if (universeValue === null) {
    return [null, `no ${MEDIAN_LABELS[metric]} yardstick (the file has no positive ${MEDIAN_LABELS[metric]})`];
  }
  return [universeValue, `universe median ${fmt1(universeValue)} (group n=${groupCount})`];
}

// --- Sector-relative strength ----------------------------------------------
// Relative strength against a broad index quietly rewards being in a hot
// sector. A pharma company beating the Nifty while every pharma name beats it
// has demonstrated nothing about itself, and the 20-point relative-strength
// block cannot tell the two apart. Measuring the same return against its own
// peers asks the sharper question, so it is reported beside the benchmark
// figure rather than replacing it.
//
// It deliberately earns no points. That block already rests on convention
// rather than on any source (see knowledge/rulebook.md), and the backtest found
// the technical score does not rank forward returns, so adding a second
// unsourced scoring rule would be moving in the wrong direction.

/**
 * Median 6-month relative strength per industry, per group, and overall.
 *
 * A company feeds a bucket only when its own 6M figure is available, so a
 * recent listing never drags a peer median toward zero by being counted as if
 * it had returned nothing. Counterpart of sector_relative_strength().
 */
export function sectorRelativeStrength(
  stocks: readonly CleanedStock[],
  technicals: Record<string, TechnicalIndicators> | null,
): SectorRelativeStrength {
  const industries = new Map<string, number[]>();
  const groups = new Map<string, number[]>();
  const universe: number[] = [];
  const listFor = (store: Map<string, number[]>, key: string) => {
    let entry = store.get(key);
    if (!entry) {
      entry = [];
      store.set(key, entry);
    }
    return entry;
  };

  for (const stock of stocks) {
    const tech = technicals ? ownEntry(technicals, stock.ticker || '') : undefined;
    const value = tech ? tech.relativeStrength6M : null;
    if (value === null || value === undefined) continue;
    const industry = (stock.sector || '').trim();
    const group = sectorGroup(industry);
    universe.push(value);
    if (industry) listFor(industries, industry).push(value);
    if (group) listFor(groups, group).push(value);
  }

  const bucket = (values: number[]): RelativeStrengthBucket => ({
    value: median(values),
    count: values.length,
  });
  const asRecord = (store: Map<string, number[]>) => {
    const out: Record<string, RelativeStrengthBucket> = {};
    for (const [name, values] of store) out[name] = bucket(values);
    return out;
  };
  return { byIndustry: asRecord(industries), byGroup: asRecord(groups), universe: bucket(universe) };
}

/**
 * [median, basis text] for one company's peers: industry, else group, else
 * universe. The same MIN_MEDIAN_SAMPLE rule as valuationYardstick(), and the
 * same honesty about fallbacks: the basis always names the bucket actually
 * used, so a universe median can never be read as a true sector comparison.
 * Counterpart of relative_strength_yardstick().
 */
export function relativeStrengthYardstick(
  buckets: SectorRelativeStrength,
  sector: string | null | undefined,
): [number | null, string] {
  const industry = (sector || '').trim();
  const group = sectorGroup(industry);
  const industryBucket = ownEntry(buckets.byIndustry, industry);
  const groupBucket = group === null ? undefined : ownEntry(buckets.byGroup, group);

  const value = industryBucket ? industryBucket.value : null;
  const count = industryBucket ? industryBucket.count : 0;
  if (value !== null && count >= MIN_MEDIAN_SAMPLE) {
    return [value, `${industry} peers (n=${count})`];
  }

  const groupValue = groupBucket ? groupBucket.value : null;
  const groupCount = groupBucket ? groupBucket.count : 0;
  if (groupValue !== null && groupCount >= MIN_MEDIAN_SAMPLE) {
    return [groupValue, `${group} group (industry n=${count})`];
  }

  const universeValue = buckets.universe.value;
  if (universeValue === null) {
    return [null, 'no peer yardstick (no company in the file reports 6M relative strength)'];
  }
  return [universeValue, `whole universe (group n=${groupCount})`];
}

const FILTER_FIELD_SET = new Set<string>(ALLOWED_FILTER_FIELDS);
const FILTER_OP_SET = new Set<string>(ALLOWED_FILTER_OPERATORS);

/**
 * Validate a custom-filter list. Returns human-readable errors, never throws,
 * including for malformed entries from an imported config file. Counterpart of
 * validate_custom_filters().
 */
export function validateCustomFilters(filters: readonly unknown[] | undefined): string[] {
  const errors: string[] = [];
  for (const raw of filters || []) {
    if (raw === null || typeof raw !== 'object' || Array.isArray(raw)) {
      errors.push(`Invalid custom filter: ${jsonText(raw)}`);
      continue;
    }
    const { field, operator, value } = raw as Record<string, unknown>;
    if (typeof field !== 'string' || !FILTER_FIELD_SET.has(field)) {
      errors.push(`Invalid custom filter field: ${jsonText(field)}`);
    } else if (typeof operator !== 'string' || !FILTER_OP_SET.has(operator)) {
      errors.push(`Invalid custom filter operator: ${jsonText(operator)}`);
    } else if (parseStrictDecimal(value) === null) {
      errors.push(`Invalid numeric value in custom filter for ${field}: ${jsonText(value)}`);
    }
  }
  return errors;
}

/** Trim, upper-case and drop blank symbols. Counterpart of normalise_symbols(). */
export function normaliseSymbols(symbols: readonly unknown[] | undefined): string[] {
  return (symbols || []).map((s) => String(s).trim().toUpperCase()).filter(Boolean);
}

// ---------------------------------------------------------------------------
// Saved configuration (shared file format with python/engine.py)
// ---------------------------------------------------------------------------

/**
 * Documented range of every numeric setting. Counterpart of CONFIG_LIMITS in
 * python/engine.py (the parity suite asserts they are equal). The config panel
 * clamps its inputs to these bounds; imported files are validated against them.
 */
export const CONFIG_LIMITS: Record<string, { min: number; max: number }> = {
  top_n: { min: 1, max: 100 },
  minimum_total_score: { min: 0, max: 100 },
  technical_weight_pct: { min: 0, max: 100 },
  fundamentals_stale_after_days: { min: 1, max: 365 },
  minMarketCapCr: { min: 0, max: 100000 },
  minSalesGrowthPct: { min: -100, max: 100 },
  minProfitGrowthPct: { min: -100, max: 100 },
  minRocePct: { min: 0, max: 100 },
  minRoePct: { min: 0, max: 100 },
  maxDebtToEquity: { min: 0, max: 10 },
  minInterestCoverage: { min: 0, max: 100 },
  minPromoterHoldingPct: { min: 0, max: 100 },
  maxPromoterPledgePct: { min: 0, max: 100 },
  minPeRatio: { min: 0, max: 200 },
  maxPeRatio: { min: 0, max: 500 },
  maxPbRatio: { min: 0, max: 100 },
  minDividendYieldPct: { min: 0, max: 30 },
  minimum_fundamental_coverage: { min: 0, max: 100 },
  // Upper bounds are generous on purpose: 100 for either cap means "no cap",
  // which is a coherent thing to ask for, and 50 for the target covers the 18%
  // TSaM p.53 mentions some hedge funds run at with room to spare.
  target_volatility_pct: { min: 1, max: 50 },
  max_position_weight_pct: { min: 1, max: 100 },
  max_sector_weight_pct: { min: 1, max: 100 },
};
const WHOLE_NUMBER_SETTINGS = new Set(['top_n']);
const BOOLEAN_SETTINGS = new Set([
  'enable_technical_confirmation', 'requirePositiveOcf', 'strict_screen',
]);
const UNIVERSE_MODES = ['nifty100', 'custom'];
const CONFIG_SECTIONS = ['schema_version', 'app', 'screening'];
export const CONFIG_FILENAME = 'config.json';

/** The saved-configuration file both engines read: data-store/config/config.json. */
export interface ConfigDocument {
  schema_version: string;
  app: AppConfig;
  screening: ScreeningConfig;
}

function pickKeys<T extends object>(source: T, template: T): T {
  const out = {} as T;
  for (const key of Object.keys(template) as (keyof T)[]) out[key] = source[key];
  return out;
}

/** Counterpart of config_document(). */
export function buildConfigDocument(app: AppConfig, screening: ScreeningConfig): ConfigDocument {
  return {
    schema_version: SCHEMA_VERSION,
    app: pickKeys(app, DEFAULT_APP_CONFIG),
    screening: pickKeys(screening, DEFAULT_SCREENING_CONFIG),
  };
}

/** Why `value` is unacceptable for `key`, or null. Counterpart of _setting_error(). */
function settingError(section: string, key: string, value: unknown): string | null {
  const label = `${section}.${key}`;
  const limits = Object.prototype.hasOwnProperty.call(CONFIG_LIMITS, key) ? CONFIG_LIMITS[key] : undefined;
  if (limits) {
    if (typeof value !== 'number' || !Number.isFinite(value)) return `${label} must be a number`;
    if (WHOLE_NUMBER_SETTINGS.has(key) && !Number.isInteger(value)) return `${label} must be a whole number`;
    if (value < limits.min || value > limits.max) {
      return `${label} must be between ${limits.min} and ${limits.max}`;
    }
    return null;
  }
  if (BOOLEAN_SETTINGS.has(key)) {
    return typeof value === 'boolean' ? null : `${label} must be true or false`;
  }
  if (key === 'universe_mode') {
    return typeof value === 'string' && UNIVERSE_MODES.includes(value)
      ? null
      : `${label} must be one of: ${UNIVERSE_MODES.join(', ')}`;
  }
  if (key === 'custom_symbols') {
    return Array.isArray(value) && value.every((s) => typeof s === 'string')
      ? null
      : `${label} must be a list of symbols`;
  }
  if (key === 'custom_filters') {
    if (!Array.isArray(value)) return `${label} must be a list`;
    const problems = validateCustomFilters(value);
    return problems.length ? problems.join('; ') : null;
  }
  return `Unknown ${section} setting: ${key}`;
}

/**
 * Validate a saved configuration and merge it over the defaults. Counterpart
 * of validate_config_document(): every key is optional, but unknown sections
 * or keys, wrong types and out-of-range values are errors -- never silently
 * clamped.
 */
export function validateConfigDocument(document: unknown): {
  app: AppConfig;
  screening: ScreeningConfig;
  errors: string[];
} {
  const app: AppConfig = { ...DEFAULT_APP_CONFIG, custom_symbols: [], custom_filters: [] };
  const screening: ScreeningConfig = { ...DEFAULT_SCREENING_CONFIG };
  if (document === null || typeof document !== 'object' || Array.isArray(document)) {
    return { app, screening, errors: ['Configuration must be a JSON object'] };
  }
  const doc = document as Record<string, unknown>;
  // Keys are checked in code-point order: JavaScript lists integer-like keys
  // first whatever the file order, so file order cannot be shared with Python.
  const errors = Object.keys(doc)
    .sort(compareCodePoints)
    .filter((key) => !CONFIG_SECTIONS.includes(key))
    .map((key) => `Unknown configuration section: ${key}`);
  const version = 'schema_version' in doc ? doc.schema_version : SCHEMA_VERSION;
  if (version !== SCHEMA_VERSION) {
    errors.push(`Unsupported schema_version ${jsonText(version)} (expected ${SCHEMA_VERSION})`);
  }
  const sections: [string, Record<string, unknown>][] = [
    ['app', app as unknown as Record<string, unknown>],
    ['screening', screening as unknown as Record<string, unknown>],
  ];
  for (const [section, target] of sections) {
    const values = section in doc ? doc[section] : {};
    if (values === null || typeof values !== 'object' || Array.isArray(values)) {
      errors.push(`${section} must be an object`);
      continue;
    }
    const record = values as Record<string, unknown>;
    for (const key of Object.keys(record).sort(compareCodePoints)) {
      const value = record[key];
      if (!Object.prototype.hasOwnProperty.call(target, key)) {
        errors.push(`Unknown ${section} setting: ${key}`);
        continue;
      }
      const problem = settingError(section, key, value);
      if (problem) errors.push(problem);
      else if (key === 'custom_symbols') target[key] = normaliseSymbols(value as unknown[]);
      else if (key === 'custom_filters') target[key] = (value as object[]).map((f) => ({ ...f }));
      else target[key] = value;
    }
  }
  // A minimum P/E above the maximum rejects every company, so it is a config
  // error rather than a screen that quietly returns nothing.
  // A per-position cap above the per-group cap asks for something the sizing
  // pass cannot honour: the group cap is applied after the position cap, so the
  // larger number would silently never bind. Self-contradicting rather than
  // merely unusual, so it is an error, exactly like the P/E pair below.
  if (app.max_position_weight_pct > app.max_sector_weight_pct) {
    errors.push(
      `app.max_position_weight_pct (${app.max_position_weight_pct}) must not be above `
      + `app.max_sector_weight_pct (${app.max_sector_weight_pct})`,
    );
  }
  if (screening.minPeRatio > screening.maxPeRatio) {
    errors.push(
      `screening.minPeRatio (${screening.minPeRatio}) must not be above screening.maxPeRatio (${screening.maxPeRatio})`,
    );
  }
  return { app, screening, errors };
}

// ---------------------------------------------------------------------------
// Technical indicators and price history
// ---------------------------------------------------------------------------

export const SESSIONS_52_WEEK = 252;
export const SESSIONS_6_MONTH = 126;
/** Nifty 50, the relative-strength benchmark. Counterpart of BENCHMARK_SYMBOL. */
export const BENCHMARK_SYMBOL = '^NSEI';
/**
 * Open, High and Low were added so true range, ATR and ADX can be computed
 * honestly instead of being approximated from closes. Readers treat all three as
 * optional: a four-column Date,Ticker,Close,Volume file written by an earlier
 * version still loads, and the indicators that need a high and a low report
 * themselves unavailable on it rather than substituting the close.
 */
export const PRICE_HISTORY_COLUMNS = [
  'Date', 'Ticker', 'Open', 'High', 'Low', 'Close', 'Volume',
] as const;
const ISO_DATE_RE = /^[0-9]{4}-[0-9]{2}-[0-9]{2}$/;
const MONTH_DAYS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];

/**
 * YYYY-MM-DD naming a real Gregorian date. Counterpart of _is_real_date(); plain
 * arithmetic, because Date maps years 0-99 onto 1900-1999.
 */
function isRealDate(text: string): boolean {
  if (!ISO_DATE_RE.test(text)) return false;
  const year = Number(text.slice(0, 4));
  const month = Number(text.slice(5, 7));
  const day = Number(text.slice(8));
  if (month < 1 || month > 12) return false;
  const leap = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
  return day >= 1 && day <= MONTH_DAYS[month - 1] + (month === 2 && leap ? 1 : 0);
}
const TECHNICAL_KEYS: (keyof TechnicalAvailability)[] = [
  'sma50', 'sma200', 'smaCross', 'relativeStrength6M', 'high52Week',
];

export function emptyTechnicals(source = 'unavailable'): TechnicalIndicators {
  return {
    currentPrice: null,
    sma50: null,
    sma200: null,
    isAboveSma50: null,
    isAboveSma200: null,
    isSma50Above200: null,
    relativeStrength6M: null,
    volumeRatio20D: null,
    distFrom52WHighPct: null,
    volatility30D: null,
    high52Week: null,
    // Chart indicators. Null means "not enough history", or "this file has no
    // highs and lows", never "zero". See the helpers above for the minimum each
    // one needs.
    rsi14: null,
    macdLine: null,
    macdSignal: null,
    macdHistogram: null,
    adx14: null,
    diPlus14: null,
    diMinus14: null,
    atr14: null,
    atrPct: null,
    bollingerPercentB: null,
    obvPressure20D: null,
    roc1M: null,
    roc3M: null,
    roc6M: null,
    roc12M: null,
    drawdownFromPeakPct: null,
    relativeStrength3M: null,
    relativeStrength12M: null,
    source,
    as_of: null,
    history_rows: 0,
    available: {
      sma50: false, sma200: false, smaCross: false,
      relativeStrength6M: false, high52Week: false,
    },
    data_status: 'UNAVAILABLE',
  };
}

type MaybeNumber = number | null | undefined;

function finiteOrNaN(value: unknown): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : NaN;
}

/** Right-align values to `length` entries so the latest sessions line up. */
function alignToEnd<T>(values: readonly T[], length: number, pad: T): T[] {
  const out = new Array<T>(length).fill(pad);
  const take = Math.min(length, values.length);
  for (let offset = 1; offset <= take; offset += 1) {
    out[length - offset] = values[values.length - offset];
  }
  return out;
}

/** Left-to-right sum divided by n. Counterpart of _sequential_mean(); see there for why. */
function sequentialMean(values: readonly number[]): number {
  let total = 0;
  for (const value of values) total += value;
  return total / values.length;
}

// --- Chart indicators ------------------------------------------------------
// Counterparts of the helpers in python/engine.py. Every one is a plain
// left-to-right loop so both engines produce bit-identical doubles, and every
// one returns null when its own minimum history is not met, or when a session
// it needs has no high or low. An unavailable indicator is never approximated.
export const ATR_ADX_PERIOD = 14;
/**
 * Five smoothing periods, which is long enough for Wilder's running average to
 * settle and short enough that one missing session does not disable the
 * indicator for a whole decade of history.
 */
const ATR_ADX_WINDOW = ATR_ADX_PERIOD * 5 + 1;
const RSI_PERIOD = 14;
const BOLLINGER_PERIOD = 20;
const BOLLINGER_DEVIATIONS = 2;
const OBV_LOOKBACK = 20;
export const SESSIONS_1_MONTH = 21;
export const SESSIONS_3_MONTH = 63;
export const SESSIONS_12_MONTH = 252;

/** EMA at each index from period-1 onwards. Counterpart of _ema_series(). */
function emaSeries(values: readonly number[], period: number): number[] {
  if (values.length < period) return [];
  let ema = sequentialMean(values.slice(0, period));
  const out = [ema];
  const weight = 2 / (period + 1);
  for (const value of values.slice(period)) {
    ema = value * weight + ema * (1 - weight);
    out.push(ema);
  }
  return out;
}

/** Wilder's running average. Counterpart of _wilder_average(). */
function wilderAverage(values: readonly number[], period: number): number {
  let average = sequentialMean(values.slice(0, period));
  for (const value of values.slice(period)) {
    average = (average * (period - 1) + value) / period;
  }
  return average;
}

/**
 * Wilder's RSI. Counterpart of _rsi(). A perfectly flat series has neither
 * gains nor losses, so its RSI is genuinely undefined; 50 is returned rather
 * than the 100 some libraries report, which would read as maximum strength for
 * a price that never moved.
 */
function rsi(prices: readonly number[], period = RSI_PERIOD): number | null {
  if (prices.length < period + 1) return null;
  const gains: number[] = [];
  const losses: number[] = [];
  for (let i = 1; i < prices.length; i += 1) {
    const change = prices[i] - prices[i - 1];
    gains.push(change > 0 ? change : 0);
    losses.push(change < 0 ? -change : 0);
  }
  const averageGain = wilderAverage(gains, period);
  const averageLoss = wilderAverage(losses, period);
  if (averageLoss === 0) return averageGain > 0 ? 100 : 50;
  return 100 - 100 / (1 + averageGain / averageLoss);
}

/** [line, signal, histogram] from the standard 12/26/9 EMAs. Counterpart of _macd(). */
function macd(prices: readonly number[], fast = 12, slow = 26, signal = 9): [number, number, number] | null {
  if (prices.length < slow + signal - 1) return null;
  const fastSeries = emaSeries(prices, fast);
  const slowSeries = emaSeries(prices, slow);
  if (!fastSeries.length || !slowSeries.length) return null;
  // fastSeries[i + offset] and slowSeries[i] describe the same session.
  const offset = slow - fast;
  const lineSeries: number[] = [];
  for (let i = 0; i < slowSeries.length; i += 1) {
    lineSeries.push(fastSeries[i + offset] - slowSeries[i]);
  }
  const signalSeries = emaSeries(lineSeries, signal);
  if (!signalSeries.length) return null;
  const line = lineSeries[lineSeries.length - 1];
  const signalValue = signalSeries[signalSeries.length - 1];
  return [line, signalValue, line - signalValue];
}

/** The tail ATR and ADX use, or null when a high or low is missing. */
function directionalWindow(
  highs: readonly number[],
  lows: readonly number[],
  closes: readonly number[],
  period: number,
): [number[], number[], number[]] | null {
  if (closes.length < period * 2 + 1) return null;
  const tail = Math.min(closes.length, ATR_ADX_WINDOW);
  const windowHighs = highs.slice(-tail);
  const windowLows = lows.slice(-tail);
  const windowCloses = closes.slice(-tail);
  for (let index = 0; index < tail; index += 1) {
    if (Number.isNaN(windowHighs[index]) || Number.isNaN(windowLows[index])) return null;
  }
  return [windowHighs, windowLows, windowCloses];
}

/** True range for every session after the first. Counterpart of _true_ranges(). */
function trueRanges(
  highs: readonly number[],
  lows: readonly number[],
  closes: readonly number[],
): number[] {
  const out: number[] = [];
  for (let i = 1; i < closes.length; i += 1) {
    const previousClose = closes[i - 1];
    out.push(Math.max(
      highs[i] - lows[i],
      Math.abs(highs[i] - previousClose),
      Math.abs(lows[i] - previousClose),
    ));
  }
  return out;
}

/** Wilder's ATR. Counterpart of _atr(). */
function atr(
  highs: readonly number[],
  lows: readonly number[],
  closes: readonly number[],
  period = ATR_ADX_PERIOD,
): number | null {
  const window = directionalWindow(highs, lows, closes, period);
  if (!window) return null;
  const ranges = trueRanges(window[0], window[1], window[2]);
  if (ranges.length < period) return null;
  return wilderAverage(ranges, period);
}

/**
 * [ADX, +DI, -DI] from Wilder's directional movement. Counterpart of _adx().
 * A series with no range at all (every high equal to its low, as a synthetic
 * flat fixture has) makes the directional indicators undefined rather than
 * zero, so null is returned.
 */
function adx(
  highs: readonly number[],
  lows: readonly number[],
  closes: readonly number[],
  period = ATR_ADX_PERIOD,
): [number, number, number] | null {
  const window = directionalWindow(highs, lows, closes, period);
  if (!window) return null;
  const [windowHighs, windowLows, windowCloses] = window;
  const ranges: number[] = [];
  const plusMoves: number[] = [];
  const minusMoves: number[] = [];
  for (let i = 1; i < windowCloses.length; i += 1) {
    const up = windowHighs[i] - windowHighs[i - 1];
    const down = windowLows[i - 1] - windowLows[i];
    plusMoves.push(up > down && up > 0 ? up : 0);
    minusMoves.push(down > up && down > 0 ? down : 0);
    const previousClose = windowCloses[i - 1];
    ranges.push(Math.max(
      windowHighs[i] - windowLows[i],
      Math.abs(windowHighs[i] - previousClose),
      Math.abs(windowLows[i] - previousClose),
    ));
  }
  if (ranges.length < period * 2) return null;
  let smoothedRange = sequentialMean(ranges.slice(0, period));
  let smoothedPlus = sequentialMean(plusMoves.slice(0, period));
  let smoothedMinus = sequentialMean(minusMoves.slice(0, period));
  const dxValues: number[] = [];
  let diPlus = 0;
  let diMinus = 0;
  for (let i = period; i < ranges.length; i += 1) {
    smoothedRange = (smoothedRange * (period - 1) + ranges[i]) / period;
    smoothedPlus = (smoothedPlus * (period - 1) + plusMoves[i]) / period;
    smoothedMinus = (smoothedMinus * (period - 1) + minusMoves[i]) / period;
    if (smoothedRange === 0) return null;
    diPlus = (100 * smoothedPlus) / smoothedRange;
    diMinus = (100 * smoothedMinus) / smoothedRange;
    const total = diPlus + diMinus;
    dxValues.push(total === 0 ? 0 : (100 * Math.abs(diPlus - diMinus)) / total);
  }
  if (dxValues.length < period) return null;
  return [wilderAverage(dxValues, period), diPlus, diMinus];
}

/**
 * Where the last close sits across the Bollinger bands, as a percentage: 0 is
 * the lower band and 100 the upper. Counterpart of _bollinger_percent_b().
 */
function bollingerPercentB(
  prices: readonly number[],
  period = BOLLINGER_PERIOD,
  deviations = BOLLINGER_DEVIATIONS,
): number | null {
  if (prices.length < period) return null;
  const window = prices.slice(-period);
  const mean = sequentialMean(window);
  let squares = 0;
  for (const value of window) {
    const deviation = value - mean;
    squares += deviation * deviation;
  }
  // Population standard deviation, which is what Bollinger bands use.
  const spread = Math.sqrt(squares / period) * deviations;
  if (spread === 0) return null;
  const lower = mean - spread;
  return ((prices[prices.length - 1] - lower) / (spread * 2)) * 100;
}

/**
 * Net signed volume over the lookback, as a percentage of its total.
 * Counterpart of _obv_pressure(): +100 means every session closed up.
 */
function obvPressure(
  prices: readonly number[],
  volumes: readonly number[],
  lookback = OBV_LOOKBACK,
): number | null {
  if (prices.length < lookback + 1) return null;
  const windowPrices = prices.slice(-(lookback + 1));
  const windowVolumes = volumes.slice(-(lookback + 1));
  let signed = 0;
  let gross = 0;
  for (let i = 1; i < windowPrices.length; i += 1) {
    const volume = windowVolumes[i];
    if (Number.isNaN(volume)) return null;
    gross += volume;
    if (windowPrices[i] > windowPrices[i - 1]) signed += volume;
    else if (windowPrices[i] < windowPrices[i - 1]) signed -= volume;
  }
  if (gross === 0) return null;
  return (signed / gross) * 100;
}

/** Percentage change over the given number of sessions. Counterpart of _rate_of_change(). */
function rateOfChange(prices: readonly number[], sessions: number): number | null {
  if (prices.length < sessions + 1) return null;
  const past = prices[prices.length - sessions - 1];
  if (past === 0) return null;
  return (prices[prices.length - 1] / past - 1) * 100;
}

/** How far below the highest close of the loaded history the last one sits. */
function drawdownFromPeak(prices: readonly number[], minimum = OBV_LOOKBACK): number | null {
  if (prices.length < minimum) return null;
  let peak = prices[0];
  for (const value of prices) if (value > peak) peak = value;
  if (peak <= 0) return null;
  return ((prices[prices.length - 1] - peak) / peak) * 100;
}

/** Percentage outperformance over sessions where both series traded. */
function relativeStrength(
  pairs: readonly (readonly [number, number])[],
  sessions: number,
): number | null {
  if (pairs.length < sessions) return null;
  const [pastStock, pastBench] = pairs[pairs.length - sessions];
  const [currentStock, currentBench] = pairs[pairs.length - 1];
  if (pastStock === 0 || pastBench === 0) return null;
  return ((currentStock - pastStock) / pastStock - (currentBench - pastBench) / pastBench) * 100;
}

/**
 * Compute indicators from position-aligned series. Counterpart of
 * compute_technical_indicators(): benchmark[i] and volumes[i] belong to the
 * session of prices[i] (null/NaN where absent), and series of different lengths
 * are aligned at their most recent end. A 200-session maximum is NOT a 52-week
 * high: with fewer than 252 valid sessions high52Week stays null and scores zero.
 */
export function computeTechnicalIndicators(
  prices: readonly MaybeNumber[],
  benchmark?: readonly MaybeNumber[] | null,
  volumes?: readonly MaybeNumber[] | null,
  source = 'injected',
  dates?: readonly string[] | null,
  highs?: readonly MaybeNumber[] | null,
  lows?: readonly MaybeNumber[] | null,
): TechnicalIndicators {
  const tech = emptyTechnicals(source);
  const closes = (prices || []).map(finiteOrNaN);
  const n = closes.length;
  const valid: number[] = [];
  closes.forEach((close, i) => {
    if (!Number.isNaN(close)) valid.push(i);
  });
  if (valid.length === 0) return tech;

  const series = valid.map((i) => closes[i]);
  const current = series[series.length - 1];
  tech.history_rows = series.length;
  tech.currentPrice = current;
  if (dates) tech.as_of = alignToEnd<string | null>(dates, n, null)[valid[valid.length - 1]];

  if (series.length >= 50) {
    tech.sma50 = sequentialMean(series.slice(-50));
    tech.isAboveSma50 = current > tech.sma50;
    tech.available.sma50 = true;
  }
  if (series.length >= 200) {
    const sma200 = sequentialMean(series.slice(-200));
    tech.sma200 = sma200;
    tech.isAboveSma200 = current > sma200;
    tech.available.sma200 = true;
    if (tech.sma50 !== null) {
      tech.isSma50Above200 = tech.sma50 > sma200;
      tech.available.smaCross = true;
    }
  }
  if (series.length >= SESSIONS_52_WEEK) {
    const high = Math.max(...series.slice(-SESSIONS_52_WEEK));
    tech.high52Week = high;
    if (high > 0) {
      tech.distFrom52WHighPct = ((current - high) / high) * 100;
      tech.available.high52Week = true;
    }
  }

  // Annualised volatility of up to the last 30 daily returns (needs 20).
  const returns: number[] = [];
  for (let i = Math.max(1, series.length - 30); i < series.length; i += 1) {
    if (series[i - 1] !== 0) returns.push(series[i] / series[i - 1] - 1);
  }
  if (returns.length >= 20) {
    const mean = sequentialMean(returns);
    let squares = 0;
    for (const value of returns) {
      const deviation = value - mean;
      squares += deviation * deviation;
    }
    tech.volatility30D = Math.sqrt(squares / (returns.length - 1)) * Math.sqrt(SESSIONS_52_WEEK) * 100;
  }

  // Latest session's volume against the mean of the last 20 sessions that
  // report volume, up to and including it; a blank latest volume gives no ratio.
  let alignedVolumes: number[] | null = null;
  if (volumes) {
    alignedVolumes = alignToEnd(volumes.map(finiteOrNaN), n, NaN);
    const last = valid[valid.length - 1];
    const latest = alignedVolumes[last];
    const window = alignedVolumes.slice(0, last + 1).filter((v) => !Number.isNaN(v)).slice(-20);
    if (!Number.isNaN(latest) && window.length >= 20) {
      const average = sequentialMean(window);
      if (average > 0) tech.volumeRatio20D = latest / average;
    }
  }

  if (benchmark) {
    const bench = alignToEnd(benchmark.map(finiteOrNaN), n, NaN);
    const pairs = valid
      .filter((i) => !Number.isNaN(bench[i]))
      .map((i) => [closes[i], bench[i]] as [number, number]);
    tech.relativeStrength3M = relativeStrength(pairs, SESSIONS_3_MONTH);
    tech.relativeStrength12M = relativeStrength(pairs, SESSIONS_12_MONTH);
    const sixMonth = relativeStrength(pairs, SESSIONS_6_MONTH);
    if (sixMonth !== null) {
      tech.relativeStrength6M = sixMonth;
      tech.available.relativeStrength6M = true;
    }
  }

  // --- Chart indicators, computed on the valid sessions only ---------------
  // Each is null when its own minimum history is not met, so a short series
  // reports "unavailable" per indicator instead of scoring a made-up zero.
  tech.rsi14 = rsi(series);
  const macdValues = macd(series);
  if (macdValues) {
    tech.macdLine = macdValues[0];
    tech.macdSignal = macdValues[1];
    tech.macdHistogram = macdValues[2];
  }
  tech.bollingerPercentB = bollingerPercentB(series);
  tech.roc1M = rateOfChange(series, SESSIONS_1_MONTH);
  tech.roc3M = rateOfChange(series, SESSIONS_3_MONTH);
  tech.roc6M = rateOfChange(series, SESSIONS_6_MONTH);
  tech.roc12M = rateOfChange(series, SESSIONS_12_MONTH);
  tech.drawdownFromPeakPct = drawdownFromPeak(series);
  if (alignedVolumes) {
    const volumeSeries = alignedVolumes;
    tech.obvPressure20D = obvPressure(series, valid.map((i) => volumeSeries[i]));
  }
  if (highs && lows) {
    const alignedHighs = alignToEnd(highs.map(finiteOrNaN), n, NaN);
    const alignedLows = alignToEnd(lows.map(finiteOrNaN), n, NaN);
    const sessionHighs = valid.map((i) => alignedHighs[i]);
    const sessionLows = valid.map((i) => alignedLows[i]);
    const averageRange = atr(sessionHighs, sessionLows, series);
    if (averageRange !== null) {
      tech.atr14 = averageRange;
      if (current !== 0) tech.atrPct = (averageRange / current) * 100;
    }
    const directional = adx(sessionHighs, sessionLows, series);
    if (directional) {
      tech.adx14 = directional[0];
      tech.diPlus14 = directional[1];
      tech.diMinus14 = directional[2];
    }
  }

  const availableCount = TECHNICAL_KEYS.filter((k) => tech.available[k]).length;
  tech.data_status =
    availableCount === TECHNICAL_KEYS.length ? 'COMPLETE' : availableCount > 0 ? 'PARTIAL' : 'UNAVAILABLE';
  return tech;
}

/**
 * Counterpart of calculate_technical_score(). A null `tech` means the run had
 * no price history at all -- a fact about the run, shown once, so it raises no
 * per-stock warning. An UNAVAILABLE record means history was loaded but this
 * stock is not in it, and that is flagged.
 */
/**
 * PROVISIONAL, not validated. These four blocks and the points inside them are
 * a starting hypothesis about what a medium-term long-only chart looks like.
 * Not one of them has been tested against forward returns; that is what the
 * backtest exists to find out. Do NOT tune them against the bundled sample,
 * whose figures are invented, and do not cite the split as evidence.
 *
 * Two rest on weaker ground than the others and should be first to go if the
 * backtest says the ranking is noise: RelStrength is benchmark-only until
 * sector-relative strength lands, so it measures "beat the Nifty" rather than
 * "beat your peers"; and Volume is the thinnest of the four, because a single
 * block deal moves OBV in an Indian large cap.
 * Counterpart of TECHNICAL_BLOCK_MAX in python/engine.py.
 */
export const TECHNICAL_BLOCK_MAX: Record<keyof TechnicalBlocks, number> = {
  trend: 40, momentum: 30, relStrength: 20, volume: 10,
};

/**
 * The four block names, derived from the caps above rather than written out a
 * second time. Two parallel lists of the same names can drift apart silently;
 * one cannot.
 */
const TECHNICAL_BLOCK_NAMES = Object.keys(TECHNICAL_BLOCK_MAX) as (keyof TechnicalBlocks)[];

/**
 * Direction of the RSI rule, stated as a decision rather than left in a number.
 * Rewarding a HIGH reading is a trend-continuation bet; rewarding a LOW one is
 * mean reversion. They are opposite systems and one threshold cannot serve
 * both. This engine is long-only over one to six months, so continuation is the
 * consistent choice. An extreme reading is exhaustion and raises a flag rather
 * than earning more.
 */
export const RSI_MOMENTUM_FLOOR = 50;
export const RSI_EXHAUSTION = 80;
/**
 * A MACD histogram closer to zero than this, as a percentage of price, is flat
 * rather than rising or falling. Without a band the sign of floating-point
 * residue decides fifteen points: a perfectly steady trend produces a histogram
 * of roughly -9e-16, because the signal line converges on the MACD line, and
 * that reads as "falling" under a bare `> 0`. Measured against price so the
 * band means the same for a 100-rupee stock and a 4000-rupee one.
 */
export const MACD_FLAT_BAND = 0.05;
/** Above this, conventionally, there is a trend at all -- whatever its direction. */
export const ADX_TRENDING = 25;
/**
 * Below this many sessions no technical score is produced. Scoring a company on
 * the two or three indicators a short history supports, beside companies
 * measured on all of them, compares numbers built from different amounts of
 * evidence. Such a company joins the fundamental-only list instead.
 */
export const SESSIONS_FOR_TECHNICAL_SCORE = 200;

/**
 * Technical score out of 100, in four blocks. Counterpart of
 * calculate_technical_score().
 *
 * Availability is handled one way throughout, and both alternatives are wrong.
 * Awarding zero for an indicator the history cannot support punishes a company
 * for a short listing or a four-column price file. Rescaling the earned points
 * up to 100 across whatever was available rewards missing data, inflating the
 * strong blocks of a company measured on two cheap indicators. So: score only
 * what is available, never rescale, and refuse to score below
 * SESSIONS_FOR_TECHNICAL_SCORE.
 *
 * Within one run every company is priced from the same file, so a file without
 * highs and lows costs every company its ADX points equally.
 */
export function calculateTechnicalScore(
  tech: TechnicalIndicators | null | undefined,
  isEnabled: boolean,
): TechnicalScoreResult {
  if (!isEnabled) {
    return {
      score: null, maxScore: 100, breakdown: ['Technical screening disabled'],
      warnings: [], blocks: null,
    };
  }
  if (!tech) {
    return {
      score: null, maxScore: 100, breakdown: ['No price history loaded'],
      warnings: [], blocks: null,
    };
  }
  const rows = tech.history_rows || 0;
  if (tech.data_status === 'UNAVAILABLE') {
    return {
      score: null,
      maxScore: 100,
      breakdown: [
        rows > 0
          ? `Only ${rows} sessions of price history; indicators need at least 50`
          : 'Technical data unavailable',
      ],
      warnings: ['Technical Data Missing'],
      blocks: null,
    };
  }
  if (rows < SESSIONS_FOR_TECHNICAL_SCORE) {
    // Enough for some indicators, not enough to stand beside companies
    // measured on all of them.
    return {
      score: null,
      maxScore: 100,
      breakdown: [`Only ${rows} sessions; a technical score needs ${SESSIONS_FOR_TECHNICAL_SCORE}`],
      warnings: ['Technical Data Missing'],
      blocks: null,
    };
  }

  const avail = tech.available;
  const breakdown: string[] = [];
  const warnings: string[] = [];
  const blocks: TechnicalBlocks = { trend: 0, momentum: 0, relStrength: 0, volume: 0 };
  const awardTo = (block: keyof TechnicalBlocks, points: number, text: string) => {
    blocks[block] += points;
    breakdown.push(`${text} (+${fmt1(points)})`);
  };

  // --- Trend, 40 -----------------------------------------------------------
  if (avail.sma200 && tech.isAboveSma200) awardTo('trend', 12, 'Price > 200 SMA');
  if (avail.sma50 && tech.isAboveSma50) awardTo('trend', 8, 'Price > 50 SMA');
  if (avail.smaCross && tech.isSma50Above200) awardTo('trend', 8, '50 SMA > 200 SMA');
  const adx = tech.adx14;
  if (adx === null) {
    breakdown.push('ADX unavailable, needs highs and lows (+0.0)');
  } else if (adx > ADX_TRENDING) {
    awardTo('trend', 4, `ADX ${fmt1(adx)}: trending`);
  } else {
    breakdown.push(`ADX ${fmt1(adx)}: no trend (+0.0)`);
  }
  if (avail.high52Week) {
    if (tech.distFrom52WHighPct !== null && tech.distFrom52WHighPct > -15) {
      awardTo('trend', 8, 'Within 15% of 52W high');
    }
  } else {
    breakdown.push(`52W high unavailable (needs ${SESSIONS_52_WEEK} sessions) (+0.0)`);
  }

  // --- Momentum, 30 --------------------------------------------------------
  // One measure per concept. RSI, MACD and the four rate-of-change windows are
  // all functions of the same close series, so paying for each would count one
  // move several times over and make momentum dominate whatever the headline
  // weights say. MACD carries direction, RSI carries extension; the ROC windows
  // stay computed and displayed but unscored for that reason.
  const hist = tech.macdHistogram;
  const price = tech.currentPrice;
  if (hist === null || price === null || price <= 0) {
    breakdown.push('MACD unavailable (+0.0)');
  } else {
    const histPct = (hist / price) * 100;
    if (histPct > MACD_FLAT_BAND) {
      awardTo('momentum', 15, 'MACD histogram rising');
    } else if (histPct < -MACD_FLAT_BAND) {
      breakdown.push('MACD histogram falling (+0.0)');
    } else {
      // A steady trend has direction but no acceleration, which is a real
      // reading rather than a missing one.
      breakdown.push('MACD histogram flat (+0.0)');
    }
  }
  const rsi = tech.rsi14;
  if (rsi === null) {
    breakdown.push('RSI unavailable (+0.0)');
  } else if (rsi > RSI_MOMENTUM_FLOOR) {
    awardTo('momentum', 15, `RSI ${fmt1(rsi)} above ${RSI_MOMENTUM_FLOOR}`);
  } else {
    breakdown.push(`RSI ${fmt1(rsi)} below ${RSI_MOMENTUM_FLOOR} (+0.0)`);
  }

  // --- Relative strength, 20 ----------------------------------------------
  const rsChecks: [number | null, number, string][] = [
    [tech.relativeStrength3M, 5, '3M'],
    [tech.relativeStrength6M, 10, '6M'],
    [tech.relativeStrength12M, 5, '12M'],
  ];
  for (const [value, points, label] of rsChecks) {
    if (value === null) breakdown.push(`${label} RS unavailable (+0.0)`);
    else if (value > 0) awardTo('relStrength', points, `Positive ${label} RS vs benchmark`);
    else breakdown.push(`Negative ${label} RS vs benchmark (+0.0)`);
  }

  // --- Volume, 10 ----------------------------------------------------------
  const ratio = tech.volumeRatio20D;
  if (ratio === null) {
    breakdown.push('Volume ratio unavailable (+0.0)');
  } else if (ratio > 1) {
    awardTo('volume', 5, `Volume ${fmt1(ratio)}x its 20-day average`);
  } else {
    breakdown.push(`Volume ${fmt1(ratio)}x its 20-day average (+0.0)`);
  }
  const obv = tech.obvPressure20D;
  if (obv === null) breakdown.push('OBV pressure unavailable (+0.0)');
  else if (obv > 0) awardTo('volume', 5, 'Buying pressure on volume');
  else breakdown.push('Selling pressure on volume (+0.0)');

  // --- Flags, never points -------------------------------------------------
  // Volatility has no direction. Paying for low volatility tilts the list
  // towards sleepy stocks and paying for high volatility towards lottery
  // tickets, and neither is defensible without evidence. So these describe.
  if (tech.atrPct !== null && tech.atrPct > 5) {
    warnings.push(`High Volatility (ATR ${fmt1(tech.atrPct)}% of price)`);
  }
  if (rsi !== null && rsi > RSI_EXHAUSTION) warnings.push(`Overbought (RSI ${fmt1(rsi)})`);
  if (tech.drawdownFromPeakPct !== null && tech.drawdownFromPeakPct < -25) {
    warnings.push(`Deep Drawdown (${fmt1(tech.drawdownFromPeakPct)}% from peak)`);
  }

  for (const key of TECHNICAL_BLOCK_NAMES) {
    blocks[key] = round1(clamp(blocks[key], 0, TECHNICAL_BLOCK_MAX[key]));
  }
  const score = clamp(
    blocks.trend + blocks.momentum + blocks.relStrength + blocks.volume, 0, 100,
  );

  if (tech.data_status !== 'COMPLETE') {
    const missing = TECHNICAL_KEYS.filter((k) => !avail[k]);
    warnings.push(`Technical Data Partial (${missing.join(', ')})`);
  }

  return { score: round1(score), maxScore: 100, breakdown, warnings, blocks };
}

/**
 * One ticker's sessions, sorted by date. opens/highs/lows are null on every
 * session of a file written before the OHLCV widening.
 */
export interface PriceSeries {
  dates: string[];
  closes: number[];
  volumes: (number | null)[];
  opens: (number | null)[];
  highs: (number | null)[];
  lows: (number | null)[];
}

/** Ticker -> sessions. The benchmark is stored under BENCHMARK_SYMBOL. */
export type PriceHistory = Record<string, PriceSeries>;

// ---------------------------------------------------------------------------
// Position sizing
// ---------------------------------------------------------------------------
// Equal-risk sizing, from TSaM Chapter 24 (p.1103, worked as Table 24.1 on
// p.1104) with its risk ceiling from Chapter 23 (p.1032). knowledge/rulebook.md
// carries the full citations and, more usefully, what each number does not rest
// on. Counterparts in python/engine.py.
//
// Why equal risk rather than anything cleverer: p.1054 states the condition
// plainly -- "unless you can select which trades are most likely to be better
// than another, equal risk is the most conservative approach". We have not
// demonstrated that we can select. The backtest measured the TECHNICAL score
// and found no ranking edge; the fundamental half has never been tested at all.
// Those are different findings and only the weaker one is ours -- no
// demonstrated selection ability, not a demonstrated absence of it -- but an
// untested half fails p.1054's condition exactly as an edgeless one does.
//
// Read the sourcing honestly. This sizing layer is the best-cited code in the
// system and it sits directly on a scoring layer that is roughly half
// convention. These citations lend that layer nothing. The argument runs the
// other way: equal risk is what the book prescribes precisely BECAUSE the
// selection underneath it is unproven.

/**
 * TSaM p.1032, principle 1: "No trade should ever risk more than 5% of the
 * invested capital." A ceiling on RISK, not on position size; the two are the
 * same number only when the stop sits 100% away. At a 6% stop this permits 83%
 * of capital in one name, so it is not a concentration limit and must not be
 * mistaken for one. Deliberately not configurable: a setting that let a config
 * file exceed the book's hard limit would make the limit decorative.
 */
export const MAX_RISK_PER_POSITION_PCT = 5.0;

/**
 * Convention. ATR as the basis for a stop is sourced -- TSaM p.852 describes ATR
 * as used to place stops -- but this multiple is not. 2.0 is inherited market
 * practice, exactly like the 50/200 pair and ADX 25, and should be read as
 * unjustified rather than as measured.
 */
export const STOP_ATR_MULTIPLE = 2.0;

/**
 * The portfolio return series needs enough overlapping sessions before its
 * standard deviation means anything. Below this the deployment fraction would
 * be noise wearing the clothes of a risk measurement, so it is not computed at
 * all.
 */
export const SESSIONS_FOR_PORTFOLIO_VOLATILITY = 60;

/** What one run's sizing pass concluded, for display beside the weights. */
export interface SizingSummary {
  measure: 'atrPct' | 'volatility30D' | null;
  targetVolatilityPct: number;
  portfolioVolatilityPct: number | null;
  deploymentPct: number | null;
  investedPct: number | null;
  basis: string;
}

/**
 * {date: simple return} for one ticker's parsed series. Counterpart of
 * _returns_by_date().
 *
 * The finite guards look redundant against PriceSeries, whose closes are typed
 * number[], but Python's parsed series can carry None and the two engines have
 * to skip the same sessions. A pair that cannot produce a return is skipped
 * rather than contributing a zero, for the same reason a missing indicator is
 * null and not 0: an absent measurement must not read as a measured flat day.
 */
function returnsByDate(entry: PriceSeries | undefined): Map<string, number> {
  const out = new Map<string, number>();
  if (!entry) return out;
  const dates = entry.dates || [];
  const closes = entry.closes || [];
  const n = Math.min(dates.length, closes.length);
  for (let i = 1; i < n; i += 1) {
    const previous = closes[i - 1];
    const current = closes[i];
    if (!Number.isFinite(previous) || !Number.isFinite(current) || previous === 0) continue;
    out.set(dates[i], current / previous - 1);
  }
  return out;
}

/**
 * [annualised volatility %, basis] of the weighted portfolio. Counterpart of
 * portfolio_volatility_pct().
 *
 * Built from the portfolio's OWN daily return series over the sessions where
 * every constituent traded, then one standard deviation of that series. This is
 * exactly sqrt(w' COV w) without ever forming a covariance matrix, and the
 * difference is not cosmetic: the matrix form is n*n products summed in an
 * order both engines would have to agree on, while a single return series is
 * one sequential sum, which is the discipline the rest of this file follows.
 *
 * It matters that this is the real thing rather than a weighted average of the
 * individual volatilities. Measured on 19 Nifty names, average pairwise
 * correlation was 0.24, the true portfolio volatility 13.0% and the
 * weighted-average approximation 22.8%. At a 12% target those imply 92.5% and
 * 52.7% of capital invested -- so the approximation would have parked nearly
 * half the account permanently while looking conservative.
 */
export function portfolioVolatilityPct(
  weights: Record<string, number>,
  history: PriceHistory | null | undefined,
): [number | null, string] {
  const store = history || {};
  const tickers = Object.keys(weights).sort(compareCodePoints);
  if (tickers.length === 0) return [null, 'no holdings to measure'];

  const perTicker = new Map<string, Map<string, number>>();
  for (const ticker of tickers) {
    const returns = returnsByDate(ownEntry(store, ticker));
    if (returns.size === 0) return [null, `${ticker} has no usable return series`];
    perTicker.set(ticker, returns);
  }

  let common: string[] | null = null;
  for (const ticker of tickers) {
    const returns = perTicker.get(ticker) as Map<string, number>;
    common = common === null
      ? [...returns.keys()]
      : common.filter((date) => returns.has(date));
  }
  const all = (common || []).slice().sort(compareCodePoints);
  if (all.length < SESSIONS_FOR_PORTFOLIO_VOLATILITY) {
    return [null, `only ${all.length} sessions common to all ${tickers.length} holdings, `
      + `needs ${SESSIONS_FOR_PORTFOLIO_VOLATILITY}`];
  }
  // Most recent year only. The price file starts at HISTORY_START (2015), so
  // the untrimmed intersection runs to about 2890 sessions, and a volatility
  // averaged over eleven years barely moves. That would quietly destroy the
  // point of the target: deployment is supposed to fall when volatility rises,
  // and an eleven-year mean cannot rise. It also mismatched every other measure
  // here -- ATR(14) and volatility30D are short-window -- so the deployment
  // fraction was being computed on a different timescale from the weights it
  // scaled. The window length is Convention: no book in this repo fixes one,
  // and 252 is chosen to match the annualisation everywhere else.
  const dates = all.slice(-SESSIONS_52_WEEK);

  const series: number[] = [];
  for (const date of dates) {
    let total = 0;
    for (const ticker of tickers) {
      total += weights[ticker] * (perTicker.get(ticker) as Map<string, number>).get(date)!;
    }
    series.push(total);
  }
  const mean = sequentialMean(series);
  let squares = 0;
  for (const value of series) {
    const deviation = value - mean;
    squares += deviation * deviation;
  }
  const variance = squares / (series.length - 1);
  const value = Math.sqrt(variance) * Math.sqrt(SESSIONS_52_WEEK) * 100;
  return [value, `${dates.length} sessions common to ${tickers.length} holdings`];
}

/** The four fields a sized position carries. */
export interface PositionSizing {
  positionWeightPct: number | null;
  stopPrice: number | null;
  stopDistancePct: number | null;
  sizingBasis: string;
}

/**
 * Equal-risk position sizes for the companies actually being bought.
 * Counterpart of size_positions().
 *
 * items is the ranked watchlist -- the names that would actually be purchased --
 * because a weight means nothing except relative to the rest of the basket. This
 * runs after ranking and after the top_n cut, which is also why it can never
 * influence a score: it does not exist until the selection is final.
 *
 * Four steps, in this order, because both engines must apply them identically:
 *
 *   1. Equal risk. Weight proportional to 1/volatility, normalised to sum to
 *      one, exactly as TSaM Table 24.1 (p.1104) works it -- "% of smallest" is
 *      min_vol/own_vol and "Scale" divides each by their total. ATR is the
 *      measure when available (p.1103 prefers it when high, low and close are
 *      present); annualised standard deviation is the book's own fallback when
 *      only closes are.
 *   2. Deployment. The volatility target scales the whole basket down until the
 *      portfolio's own volatility meets it. Long-only and unleveraged, so this
 *      can only ever reduce exposure and never raise it, which is also
 *      Kaufman's advice at p.1092: use these methods only to reduce leverage.
 *   3. Risk ceiling, TSaM p.1032 principle 1, applied per position.
 *   4. Concentration caps, per p.1040.
 *
 * Capped weight is NOT redistributed across the uncapped names; it stays in
 * cash. Redistribution needs iteration to converge, and an iteration count is
 * one more thing two engines would have to agree on exactly.
 *
 * Returns a Map rather than mutating, and the caller applies it to every view of
 * an evaluation. python/engine.py mutates the watchlist dicts, which are aliased
 * into its evaluations list, so the weights appear in both there; returning a
 * Map reproduces that deliberately instead of leaving the two engines disagreeing
 * about which lists carry weights.
 */
export function sizePositions(
  items: readonly StockEvaluation[],
  history: PriceHistory | null | undefined,
  appConfig: AppConfig,
): { summary: SizingSummary; sizing: Map<string, PositionSizing> } {
  const target = appConfig.target_volatility_pct;
  const maxPosition = appConfig.max_position_weight_pct;
  const maxSector = appConfig.max_sector_weight_pct;
  const sizing = new Map<string, PositionSizing>();
  const summary: SizingSummary = {
    measure: null,
    targetVolatilityPct: target,
    portfolioVolatilityPct: null,
    deploymentPct: null,
    investedPct: null,
    basis: '',
  };
  const unsized = (basis: string): PositionSizing => ({
    positionWeightPct: null, stopPrice: null, stopDistancePct: null, sizingBasis: basis,
  });
  if (items.length === 0) {
    summary.basis = 'no companies to size';
    return { summary, sizing };
  }

  const measureFor = (item: StockEvaluation, key: 'atrPct' | 'volatility30D'): number | null => {
    const value = item.stock.technicals ? item.stock.technicals[key] : null;
    if (value === null || value === undefined || !Number.isFinite(value)) return null;
    return value > 0 ? value : null;
  };

  // The measure is chosen once for the whole run, never per name. atrPct is a
  // daily range and volatility30D is annualised, so normalising a mixture of the
  // two would produce weights that describe nothing.
  let measureKey: 'atrPct' | 'volatility30D' = 'atrPct';
  let usable = items.filter((i) => measureFor(i, measureKey) !== null);
  if (usable.length === 0) {
    measureKey = 'volatility30D';
    usable = items.filter((i) => measureFor(i, measureKey) !== null);
  }
  if (usable.length === 0) {
    summary.basis = 'no company has a usable volatility measure';
    for (const item of items) sizing.set(item.stock.ticker, unsized('no volatility measure'));
    return { summary, sizing };
  }
  summary.measure = measureKey;

  // Step 1: Table 24.1, "% of smallest" then "Scale".
  const values = new Map<string, number>();
  for (const item of usable) values.set(item.stock.ticker, measureFor(item, measureKey) as number);
  const smallest = Math.min(...values.values());
  const raw = new Map<string, number>();
  for (const [ticker, value] of values) raw.set(ticker, smallest / value);
  let rawTotal = 0;
  for (const ticker of [...raw.keys()].sort(compareCodePoints)) rawTotal += raw.get(ticker) as number;
  const scale: Record<string, number> = {};
  for (const [ticker, value] of raw) scale[ticker] = value / rawTotal;

  // Step 2: deployment, measured on the equal-risk weights before any cap,
  // because the caps describe concentration and this describes total exposure.
  const [portfolioVol, portfolioBasis] = portfolioVolatilityPct(scale, history);
  if (portfolioVol === null || portfolioVol <= 0) {
    // No deployment fraction means no honest position size. Reporting the
    // relative weights alone would read as "invest all of this", which is a
    // claim about total exposure that nothing here has measured.
    summary.basis = `no position sizes: ${portfolioBasis}`;
    for (const item of usable) {
      sizing.set(item.stock.ticker, unsized(`portfolio volatility unavailable (${portfolioBasis})`));
    }
    return { summary, sizing };
  }
  const deployment = Math.min(1, target / portfolioVol);
  summary.portfolioVolatilityPct = round1(portfolioVol);
  summary.deploymentPct = round1(deployment * 100);
  summary.basis = portfolioBasis;

  const weights = new Map<string, number>();
  for (const item of usable) {
    const ticker = item.stock.ticker;
    let weight = scale[ticker] * deployment * 100;
    // Step 3: risk ceiling. weight% of capital losing stop% is weight*stop/100
    // of capital, so the cap binds at weight = 100 * MAX_RISK / stop.
    const atrPct = measureFor(item, 'atrPct');
    if (atrPct !== null) {
      const stopPct = STOP_ATR_MULTIPLE * atrPct;
      if (stopPct > 0) weight = Math.min(weight, (MAX_RISK_PER_POSITION_PCT * 100) / stopPct);
    }
    // Step 4a: per-position cap.
    weights.set(ticker, Math.min(weight, maxPosition));
  }

  // Step 4b: per-group cap. Members are scaled proportionally so the ordering
  // within a group is preserved; the shortfall stays in cash.
  const groups = new Map<string, string[]>();
  for (const item of usable) {
    const group = item.sectorGroup;
    if (!group) continue;
    const list = groups.get(group);
    if (list) list.push(item.stock.ticker);
    else groups.set(group, [item.stock.ticker]);
  }
  for (const group of [...groups.keys()].sort(compareCodePoints)) {
    const members = (groups.get(group) as string[]).slice().sort(compareCodePoints);
    let groupTotal = 0;
    for (const ticker of members) groupTotal += weights.get(ticker) as number;
    if (groupTotal > maxSector && groupTotal > 0) {
      const factor = maxSector / groupTotal;
      for (const ticker of members) weights.set(ticker, (weights.get(ticker) as number) * factor);
    }
  }

  let invested = 0;
  for (const item of usable) {
    const ticker = item.stock.ticker;
    const weight = weights.get(ticker) as number;
    invested += weight;
    const atrPct = measureFor(item, 'atrPct');
    if (atrPct === null) {
      // p.1032 principle 2 wants an exit known in advance, and without a high
      // and a low there is no ATR to place one against. Saying so is better than
      // inventing a percentage stop the books do not support.
      sizing.set(ticker, {
        positionWeightPct: round1(weight),
        stopPrice: null,
        stopDistancePct: null,
        sizingBasis: 'equal risk by annualised volatility; no ATR, so no stop',
      });
      continue;
    }
    const stopPct = STOP_ATR_MULTIPLE * atrPct;
    const price = item.stock.currentPrice;
    sizing.set(ticker, {
      positionWeightPct: round1(weight),
      stopPrice: price !== null && Number.isFinite(price) && price > 0
        ? round1(price * (1 - stopPct / 100))
        : null,
      stopDistancePct: round1(stopPct),
      sizingBasis: `equal risk by ATR, stop ${STOP_ATR_MULTIPLE}x ATR`,
    });
  }
  summary.investedPct = round1(invested);
  return { summary, sizing };
}

function ownEntry<T>(record: Record<string, T>, key: string): T | undefined {
  return Object.prototype.hasOwnProperty.call(record, key) ? record[key] : undefined;
}

/**
 * Parse Date,Ticker,Close[,Volume] text into per-ticker series. Counterpart of
 * parse_price_history_csv(): headers are case-insensitive ("Symbol" is accepted
 * for Ticker), rows with a malformed date, blank ticker or non-numeric close
 * are skipped and counted, and a later row for the same ticker and date wins.
 * Throws when a required column is missing.
 */
export function parsePriceHistoryCsv(text: string): { history: PriceHistory; skipped: number } {
  const body = text.charCodeAt(0) === 0xfeff ? text.slice(1) : text;
  // One rule for both engines: \r\n and a lone \r both end a line, and only
  // commas separate fields -- Papa would otherwise sniff both.
  const rows = (Papa.parse<string[]>(body.replace(/\r\n?/g, '\n'), {
    header: false,
    delimiter: ',',
    newline: '\n',
  }).data || []) as string[][];
  const names = (rows[0] || []).map((cell) => String(cell).trim().toLowerCase());
  const find = (...aliases: string[]): number | null => {
    for (const alias of aliases) {
      const index = names.indexOf(alias);
      if (index !== -1) return index;
    }
    return null;
  };
  const dateCol = find('date');
  const tickerCol = find('ticker', 'symbol');
  const closeCol = find('close');
  const volumeCol = find('volume');
  // Optional: a file written before the OHLCV widening has none of these, and
  // the indicators that need a high and a low then report unavailable.
  const openCol = find('open');
  const highCol = find('high');
  const lowCol = find('low');
  if (dateCol === null || tickerCol === null || closeCol === null) {
    throw new Error('Price history CSV needs Date, Ticker and Close columns (Volume is optional)');
  }

  type Point = [number, number | null, number | null, number | null, number | null];
  const pointsByTicker = new Map<string, Map<string, Point>>();
  let skipped = 0;
  for (const row of rows.slice(1)) {
    if (row.join('').trim() === '') continue;
    const cell = (index: number | null) => (index !== null && index < row.length ? String(row[index]) : '');
    const date = cell(dateCol).trim();
    const ticker = cell(tickerCol).trim().toUpperCase();
    const close = parseStrictDecimal(cell(closeCol));
    if (!isRealDate(date) || !ticker || close === null) {
      skipped += 1;
      continue;
    }
    if (!pointsByTicker.has(ticker)) pointsByTicker.set(ticker, new Map());
    pointsByTicker.get(ticker)!.set(date, [
      close,
      parseStrictDecimal(cell(volumeCol)),
      parseStrictDecimal(cell(openCol)),
      parseStrictDecimal(cell(highCol)),
      parseStrictDecimal(cell(lowCol)),
    ]);
  }

  const history: PriceHistory = {};
  for (const [ticker, points] of pointsByTicker) {
    const dates = [...points.keys()].sort(compareCodePoints);
    history[ticker] = {
      dates,
      closes: dates.map((d) => points.get(d)![0]),
      volumes: dates.map((d) => points.get(d)![1]),
      opens: dates.map((d) => points.get(d)![2]),
      highs: dates.map((d) => points.get(d)![3]),
      lows: dates.map((d) => points.get(d)![4]),
    };
  }
  return { history, skipped };
}

/**
 * Indicators for each ticker from a parsed price history. Counterpart of
 * technicals_from_history(): the benchmark is aligned to each stock's own
 * dates, so relative strength compares sessions where both actually traded.
 */
export function technicalsFromHistory(
  history: PriceHistory,
  tickers: readonly string[],
): Record<string, TechnicalIndicators> {
  const bench = ownEntry(history, BENCHMARK_SYMBOL);
  const benchByDate = bench ? new Map(bench.dates.map((d, i) => [d, bench.closes[i]])) : null;
  const out: Record<string, TechnicalIndicators> = {};
  for (const ticker of tickers) {
    const entry = ownEntry(history, ticker);
    if (!entry) {
      out[ticker] = emptyTechnicals('not in price history');
      continue;
    }
    const benchAligned = benchByDate ? entry.dates.map((d) => benchByDate.get(d) ?? null) : null;
    out[ticker] = computeTechnicalIndicators(
      entry.closes, benchAligned, entry.volumes, 'price history', entry.dates,
      entry.highs, entry.lows,
    );
  }
  return out;
}

/** Headline facts about a loaded price history, for status lines. */
export function describePriceHistory(history: PriceHistory): {
  tickers: number;
  asOf: string | null;
  hasBenchmark: boolean;
} {
  let asOf: string | null = null;
  let tickers = 0;
  for (const [ticker, series] of Object.entries(history)) {
    if (ticker !== BENCHMARK_SYMBOL) tickers += 1;
    const last = series.dates[series.dates.length - 1];
    if (last && (asOf === null || compareCodePoints(last, asOf) > 0)) asOf = last;
  }
  return { tickers, asOf, hasBenchmark: ownEntry(history, BENCHMARK_SYMBOL) !== undefined };
}

// ---------------------------------------------------------------------------
// Row parsing and deduplication
// ---------------------------------------------------------------------------

function textOf(row: ScreenerRow, col: string | undefined, fallback = ''): string {
  if (!col) return fallback;
  const raw = row[col];
  if (raw === null || raw === undefined) return fallback;
  const text = String(raw).trim();
  return text === '' ? fallback : text;
}

export function parseScreenerRows(
  rows: ScreenerRow[],
  mapping: Record<string, string>,
): CleanedStock[] {
  return rows.map((row, i) => {
    const num = (field: string) =>
      mapping[field] ? cleanNumeric(row[mapping[field]], FIELD_UNITS[field] || 'plain') : null;
    return {
      id: `stock-${i}`,
      name: textOf(row, mapping.name, 'Unknown'),
      ticker: textOf(row, mapping.ticker).toUpperCase(),
      bseCode: textOf(row, mapping.bseCode).toUpperCase() || null,
      sector: textOf(row, mapping.sector),
      currentPrice: num('currentPrice'),
      marketCap: num('marketCap'),
      salesGrowth: num('salesGrowth'),
      profitGrowth: num('profitGrowth'),
      roce: num('roce'),
      roe: num('roe'),
      debtToEquity: num('debtToEquity'),
      interestCoverage: num('interestCoverage'),
      operatingCashFlow: num('operatingCashFlow'),
      promoterHolding: num('promoterHolding'),
      promoterPledge: num('promoterPledge'),
      peRatio: num('peRatio'),
      pbRatio: num('pbRatio'),
      dividendYield: num('dividendYield'),
      sales: num('sales'),
      returnOnAssets: num('returnOnAssets'),
      grossNpa: num('grossNpa'),
      netNpa: num('netNpa'),
      capitalAdequacy: num('capitalAdequacy'),
      casa: num('casa'),
      financingMargin: num('financingMargin'),
      technicals: null,
      rawRow: row,
    };
  });
}

/**
 * Numeric fields compared between two rows for the same company. Any
 * disagreement means the export contradicts itself about that company.
 */
const DEDUPE_COMPARED_FIELDS = [
  'currentPrice', 'marketCap', 'salesGrowth', 'profitGrowth', 'roce', 'roe',
  'debtToEquity', 'interestCoverage', 'operatingCashFlow', 'promoterHolding',
  'promoterPledge', 'peRatio', 'pbRatio', 'dividendYield', 'sales',
  'returnOnAssets', 'grossNpa', 'netNpa', 'capitalAdequacy', 'casa',
  'financingMargin',
] as const;

/**
 * True when two rows for one company report different numbers. cleanNumeric()
 * never yields NaN, so plain inequality is safe. Counterpart of _rows_disagree().
 */
function rowsDisagree(first: CleanedStock, second: CleanedStock): boolean {
  const a = first as unknown as Record<string, unknown>;
  const b = second as unknown as Record<string, unknown>;
  for (const field of DEDUPE_COMPARED_FIELDS) {
    if (a[field] !== b[field]) return true;
  }
  return false;
}

/**
 * Counterpart of dedupe_stocks(): ticker, then BSE code, then normalised name.
 *
 * The first row seen survives. When a dropped duplicate reports different
 * numbers from the survivor, the survivor is marked duplicateConflict, which
 * hardRedFlags() turns into a rejection: with two disagreeing rows for one
 * company there is no way to tell which is real.
 */
export function dedupeStocks(stocks: CleanedStock[]): {
  unique: CleanedStock[];
  duplicatesRemoved: number;
} {
  const byTicker = new Map<string, CleanedStock>();
  const byBse = new Map<string, CleanedStock>();
  const byName = new Map<string, CleanedStock>();
  const unique: CleanedStock[] = [];
  let duplicatesRemoved = 0;

  for (const stock of stocks) {
    const ticker = (stock.ticker || '').toUpperCase();
    const bse = (stock.bseCode || '').toUpperCase();
    const rawName = stock.name || '';
    const nameKey = rawName.toUpperCase().replace(/[^A-Z0-9]/g, '');
    const isUnknown = !nameKey || rawName === 'Unknown';

    // Checked in the same order as before, so which rows count as duplicates
    // is unchanged; only the conflict marking is new.
    let existing: CleanedStock | undefined;
    if (ticker && byTicker.has(ticker)) existing = byTicker.get(ticker);
    else if (bse && byBse.has(bse)) existing = byBse.get(bse);
    else if (!isUnknown && byName.has(nameKey)) existing = byName.get(nameKey);

    if (existing !== undefined) {
      duplicatesRemoved += 1;
      if (rowsDisagree(existing, stock)) existing.duplicateConflict = true;
      continue;
    }
    if (ticker) byTicker.set(ticker, stock);
    if (bse) byBse.set(bse, stock);
    if (!isUnknown) byName.set(nameKey, stock);
    unique.push(stock);
  }
  return { unique, duplicatesRemoved };
}

// ---------------------------------------------------------------------------
// Scoring
// ---------------------------------------------------------------------------

const COVERAGE_FIELDS_BASE = [
  'marketCap', 'salesGrowth', 'profitGrowth', 'roce', 'roe',
  'operatingCashFlow', 'peRatio', 'pbRatio', 'promoterHolding',
] as const;
const COVERAGE_FIELDS_NON_FINANCIAL = ['debtToEquity', 'interestCoverage'] as const;

// --- Financial-company metrics ---------------------------------------------
/**
 * Banks and NBFCs are scored on their own model rather than excluded, but only
 * when the export actually carries the metrics that model needs. Without them a
 * lender is reported as "not scored" rather than scored wrongly on ratios that
 * do not describe it.
 *
 * CASA and financing margin are deliberately NOT scored, only reported: an NBFC
 * has no CASA at all, so awarding points for it would penalise every NBFC for
 * being an NBFC. Counterpart of the same constants in python/engine.py.
 */
export const BANK_REQUIRED_FIELDS = [
  'returnOnAssets', 'grossNpa', 'netNpa', 'capitalAdequacy',
] as const;
export const BANK_OPTIONAL_FIELDS = ['casa', 'financingMargin'] as const;
export const BANK_FIELD_LABELS: Record<string, string> = {
  returnOnAssets: 'Return on assets',
  grossNpa: 'Gross NPA %',
  netNpa: 'Net NPA %',
  capitalAdequacy: 'Capital adequacy ratio',
  casa: 'CASA %',
  financingMargin: 'Financing margin %',
};

/**
 * Required financial-company metrics this row does not carry, in order.
 * Non-empty means the company cannot be scored on the financial model.
 * Counterpart of bank_metric_gaps().
 */
export function bankMetricGaps(stock: CleanedStock): string[] {
  const record = stock as unknown as Record<string, unknown>;
  return BANK_REQUIRED_FIELDS.filter(
    (field) => record[field] === null || record[field] === undefined,
  ).map((field) => BANK_FIELD_LABELS[field]);
}

/**
 * Reasons a company's numbers cannot be trusted, in a fixed order.
 *
 * A non-empty list rejects the company outright and stops it being scored.
 * These are not "unattractive" findings -- an expensive stock still gets a
 * score -- they are "this row is not usable as evidence". Counterpart of
 * hard_red_flags().
 */
export function hardRedFlags(
  stock: CleanedStock,
  config: ScreeningConfig,
  isFinancial: boolean,
  coverage: number,
): string[] {
  const flags: string[] = [];
  const {
    marketCap: mcap, promoterHolding: ph, promoterPledge: pp,
    pbRatio: pb, debtToEquity: de, operatingCashFlow: ocf, sales,
  } = stock;

  // 1. Negative net worth. P/B and D/E change sign, not magnitude, so a
  //    "cheap" P/B of -0.3 is insolvency rather than a bargain.
  if ((pb !== null && pb < 0) || (de !== null && de < 0)) flags.push('Negative net worth');
  // 2. Pledged promoter stake above the configured limit.
  if (pp !== null && pp > config.maxPromoterPledgePct) flags.push('High Promoter Pledge');
  // 3. Operating cash flow, for NON-FINANCIAL companies only. For a bank or
  //    NBFC a negative OCF is ordinary -- a growing loan book consumes cash --
  //    so applying this rule to lenders would reject the healthy ones.
  if (config.requirePositiveOcf && !isFinancial) {
    if (ocf === null) flags.push('OCF missing');
    else if (ocf <= 0) flags.push('Negative OCF');
  }
  // 4. Too little of the row is present to score it honestly.
  if (coverage < config.minimum_fundamental_coverage) {
    flags.push(`Insufficient Data (${fmt1(coverage)}%)`);
  }
  // 5. Revenue of zero or less: every growth rate and margin divides by it.
  //    Checked only when the export carries an absolute revenue column.
  if (sales !== null && sales <= 0) flags.push('Non-positive Sales');
  // 6. Impossible shareholding percentages mean the row itself is corrupt.
  if (ph !== null && (ph < 0 || ph > 100)) flags.push('Impossible Promoter Holding');
  if (pp !== null && (pp < 0 || pp > 100)) flags.push('Impossible Promoter Pledge');
  // 7. A company cannot be worth nothing and still be listed.
  if (mcap !== null && mcap <= 0) flags.push('Non-positive Market Cap');
  // 8. Internally contradictory: a promoter cannot pledge a stake it does not
  //    hold. This replaces a "P/B < 0 while book value > 0" check, which would
  //    need a book-value column the Screener.in export does not carry.
  if (pp !== null && pp > 0 && ph !== null && ph === 0) {
    flags.push('Pledge without promoter holding');
  }
  // 9. Two rows for the same company disagreed on their numbers, so there is
  //    no way to tell which one is real. Set by dedupeStocks().
  if (stock.duplicateConflict) flags.push('Conflicting duplicate rows');
  return flags;
}

/**
 * Coverage for a financial company counts the metrics its own model uses,
 * instead of the leverage and interest-cover columns that do not describe one.
 */
const COVERAGE_FIELDS_FINANCIAL: readonly string[] = [...BANK_REQUIRED_FIELDS];

/** The five sub-scores, capped 30/25/20/15/10. */
export interface ScoreParts {
  financialQuality: number;
  growth: number;
  balanceSheetSafety: number;
  valuation: number;
  governance: number;
}

const ZERO_PARTS: ScoreParts = {
  financialQuality: 0, growth: 0, balanceSheetSafety: 0, valuation: 0, governance: 0,
};

/** One scored line: "ROCE 25.0% (+15.0)". Counterpart of _award(). */
function award(label: string, value: number, unit: string, awarded: number): string {
  return `${label} ${fmt1(value)}${unit} (+${fmt1(awarded)})`;
}

/**
 * Sector-relative valuation, worth 10 for P/E and 5 for P/B.
 *
 * A ratio of half the yardstick earns full marks, the yardstick itself earns
 * half, and half again above it earns nothing. Judging against the sector is
 * the point: a P/E of 30 is dear for a bank and cheap for a fast-growing
 * software company. Counterpart of _valuation_points().
 */
function valuationPoints(
  stock: CleanedStock,
  medians: SectorMedians,
  lines: string[],
): number {
  let total = 0;
  const metrics: [('peRatio' | 'pbRatio'), string, number][] = [
    ['peRatio', 'P/E', 10],
    ['pbRatio', 'P/B', 5],
  ];
  for (const [metric, label, cap] of metrics) {
    const value = stock[metric];
    const [yardstick, basis] = valuationYardstick(medians, stock.sector, metric);
    if (value === null) {
      lines.push(`${label} missing, so no valuation points (+0.0)`);
      continue;
    }
    if (value <= 0) {
      lines.push(`${label} ${fmt1(value)} is not meaningful, so no valuation points (+0.0)`);
      continue;
    }
    if (yardstick === null || yardstick <= 0) {
      lines.push(`${label} ${fmt1(value)}: ${basis} (+0.0)`);
      continue;
    }
    const awarded = clamp(cap * (1.5 - value / yardstick), 0, cap);
    total += awarded;
    lines.push(`${label} ${fmt1(value)} vs ${basis} (+${fmt1(awarded)})`);
  }
  return total;
}

/** Growth, worth 25. Shared by both scoring models. Counterpart of _growth_points(). */
function growthPoints(stock: CleanedStock, lines: string[]): number {
  let total = 0;
  const metrics: [('salesGrowth' | 'profitGrowth'), string][] = [
    ['salesGrowth', 'Sales growth'],
    ['profitGrowth', 'Profit growth'],
  ];
  for (const [metric, label] of metrics) {
    const value = stock[metric];
    if (value === null) {
      lines.push(`${label} missing (+0.0)`);
    } else if (value <= 0) {
      lines.push(`${label} ${fmt1(value)}% (+0.0)`);
    } else {
      // Full marks at 30%, not 15%, for the same reason the quality scale was
      // widened: at 15% too much of the index scored full.
      const awarded = clamp((value / 30) * 12.5, 0, 12.5);
      total += awarded;
      lines.push(award(label, value, '%', awarded));
    }
  }
  return clamp(total, 0, 25);
}

/** Governance, worth 10. Shared by both models. Counterpart of _governance_points(). */
function governancePoints(stock: CleanedStock, lines: string[]): number {
  let total = 0;
  const ph = stock.promoterHolding;
  const pp = stock.promoterPledge;
  if (ph === null) {
    lines.push('Promoter holding missing (+0.0)');
  } else if (ph === 0) {
    // No promoter at all. ITC, L&T, HDFC Bank and ICICI Bank are professionally
    // managed, which is an ownership structure rather than a governance
    // failing, so it scores the neutral half of this component. A promoter who
    // has nearly sold out (holding 1%) is a different and genuinely worrying
    // thing, and still scores near zero below.
    total += 2.5;
    lines.push(`Promoter holding ${fmt1(ph)}%: no promoter, scored neutral (+2.5)`);
  } else if (ph < 0) {
    // Impossible as a percentage; hardRedFlags() rejects the row anyway.
    lines.push(award('Promoter holding', ph, '%', 0));
  } else {
    const awarded = clamp((ph / 75) * 5, 0, 5);
    total += awarded;
    lines.push(award('Promoter holding', ph, '%', awarded));
  }
  if (pp === null) {
    lines.push('Promoter pledge missing (+0.0)');
  } else if (pp === 0) {
    total += 5;
    lines.push('No promoter pledge (+5.0)');
  } else {
    const awarded = clamp(5 - pp, 0, 5);
    total += awarded;
    lines.push(award('Promoter pledge', pp, '%', awarded));
  }
  return clamp(total, 0, 10);
}

/**
 * Graded sub-scores for a non-financial company: 30/25/20/15/10.
 * Counterpart of score_general(). The sub-scores are built in the same source
 * order as the Python dict literal, so scoreLines come out identically.
 */
export function scoreGeneral(
  stock: CleanedStock,
  config: ScreeningConfig,
  medians: SectorMedians,
): { parts: ScoreParts; lines: string[] } {
  const lines: string[] = [];
  let quality = 0;
  const qualityMetrics: [('roce' | 'roe'), string][] = [['roce', 'ROCE'], ['roe', 'ROE']];
  for (const [metric, label] of qualityMetrics) {
    const value = stock[metric];
    if (value === null) {
      lines.push(`${label} missing (+0.0)`);
    } else if (value <= 0) {
      // Reported and genuinely zero or negative: worth no points, but a fact
      // about the company rather than a gap in the export.
      lines.push(award(label, value, '%', 0));
    } else {
      // Full marks at 40%, not 20%. At the old scale most of the Nifty 100
      // saturated -- a 58% ROCE tied a 20% one -- and a ranking cannot separate
      // companies on a factor where half the field scores full.
      const awarded = clamp((value / 40) * 15, 0, 15);
      quality += awarded;
      lines.push(award(label, value, '%', awarded));
    }
  }

  let safety = 0;
  const de = stock.debtToEquity;
  if (de === null) {
    lines.push('Debt/Equity missing (+0.0)');
  } else if (de < 0) {
    // Negative net worth. The company is red-flagged and can never reach the
    // watchlist, but it is still scored so the comparison can show why, and
    // negative equity is worth no safety points at all.
    lines.push(award('D/E', de, '', 0));
  } else {
    // Zero debt is the best possible case and earns the full ten.
    const awarded = clamp(10 - de * 5, 0, 10);
    safety += awarded;
    lines.push(award('D/E', de, '', awarded));
  }
  const icr = stock.interestCoverage;
  if (icr === null) {
    lines.push('Interest coverage missing (+0.0)');
  } else if (icr <= 0) {
    // No operating profit to cover interest at all: a real reported figure
    // that earns nothing.
    lines.push(award('Interest cover', icr, 'x', 0));
  } else {
    const awarded = clamp((icr / 5) * 10, 0, 10);
    safety += awarded;
    lines.push(award('Interest cover', icr, 'x', awarded));
  }

  return {
    parts: {
      financialQuality: clamp(quality, 0, 30),
      growth: growthPoints(stock, lines),
      balanceSheetSafety: clamp(safety, 0, 20),
      valuation: clamp(valuationPoints(stock, medians, lines), 0, 15),
      governance: governancePoints(stock, lines),
    },
    lines,
  };
}

/**
 * Graded sub-scores for a bank or NBFC, on the same 30/25/20/15/10 scale.
 *
 * Quality is return on assets and return on equity; safety is capital adequacy
 * and net NPA. A 1.5% return on assets is strong for a lender, capital adequacy
 * is scored above the 9% regulatory floor, and net NPA is scored down from a
 * clean book to 2%.
 *
 * CASA and financing margin are reported but score nothing -- an NBFC has no
 * CASA at all, so paying points for it would penalise every NBFC for being one.
 * Counterpart of score_financial().
 */
export function scoreFinancial(
  stock: CleanedStock,
  config: ScreeningConfig,
  medians: SectorMedians,
): { parts: ScoreParts; lines: string[] } {
  const lines: string[] = [];
  let quality = 0;
  const roa = stock.returnOnAssets;
  if (roa === null) {
    lines.push('Return on assets missing (+0.0)');
  } else if (roa <= 0) {
    lines.push(award('Return on assets', roa, '%', 0));
  } else {
    const awarded = clamp((roa / 1.5) * 15, 0, 15);
    quality += awarded;
    lines.push(award('Return on assets', roa, '%', awarded));
  }
  const roe = stock.roe;
  if (roe === null) {
    lines.push('ROE missing (+0.0)');
  } else if (roe <= 0) {
    lines.push(award('ROE', roe, '%', 0));
  } else {
    const awarded = clamp((roe / 20) * 15, 0, 15);
    quality += awarded;
    lines.push(award('ROE', roe, '%', awarded));
  }

  let safety = 0;
  const car = stock.capitalAdequacy;
  if (car !== null) {
    const awarded = clamp(((car - 9) / 7) * 10, 0, 10);
    safety += awarded;
    lines.push(award('Capital adequacy', car, '%', awarded));
  } else {
    lines.push('Capital adequacy missing (+0.0)');
  }
  const netNpa = stock.netNpa;
  if (netNpa !== null) {
    const awarded = clamp(((2 - netNpa) / 2) * 10, 0, 10);
    safety += awarded;
    lines.push(award('Net NPA', netNpa, '%', awarded));
  } else {
    lines.push('Net NPA missing (+0.0)');
  }

  // Reported, never scored.
  if (stock.grossNpa !== null) {
    lines.push(`Gross NPA ${fmt1(stock.grossNpa)}% (reported, not scored)`);
  }
  const reported: [('casa' | 'financingMargin'), string][] = [
    ['casa', 'CASA'],
    ['financingMargin', 'Financing margin'],
  ];
  for (const [field, label] of reported) {
    const value = stock[field];
    if (value !== null) lines.push(`${label} ${fmt1(value)}% (reported, not scored)`);
  }

  return {
    parts: {
      financialQuality: clamp(quality, 0, 30),
      growth: growthPoints(stock, lines),
      balanceSheetSafety: clamp(safety, 0, 20),
      valuation: clamp(valuationPoints(stock, medians, lines), 0, 15),
      governance: governancePoints(stock, lines),
    },
    lines,
  };
}

/**
 * The old pass/fail hurdles, applied only when strict_screen is on. These are
 * preferences, not data-integrity problems, so by default they cost points
 * rather than rejecting a company. Counterpart of strict_screen_failures().
 */
export function strictScreenFailures(
  stock: CleanedStock,
  config: ScreeningConfig,
  isFinancial: boolean,
): string[] {
  const reasons: string[] = [];
  const {
    marketCap: mcap, salesGrowth: sg, profitGrowth: pg, roce, roe,
    debtToEquity: de, interestCoverage: icr, peRatio: pe, pbRatio: pb,
    promoterHolding: ph,
  } = stock;

  if (mcap === null) reasons.push('Market Cap missing');
  else if (mcap < config.minMarketCapCr) reasons.push('Low Market Cap');
  if (sg === null) reasons.push('Sales Growth missing');
  else if (sg < config.minSalesGrowthPct) reasons.push('Low Sales Growth');
  if (pg === null) reasons.push('Profit Growth missing');
  else if (pg < config.minProfitGrowthPct) reasons.push('Low Profit Growth');
  if (roce === null) reasons.push('ROCE missing');
  else if (roce < config.minRocePct) reasons.push('Low ROCE');
  if (roe === null) reasons.push('ROE missing');
  else if (roe < config.minRoePct) reasons.push('Low ROE');
  if (!isFinancial) {
    if (de === null) reasons.push('Debt/Equity missing');
    else if (de > config.maxDebtToEquity) reasons.push('High D/E');
    if (icr === null) reasons.push('Interest Coverage missing');
    else if (icr < config.minInterestCoverage) reasons.push('Low Interest Coverage');
  }
  if (pe === null) {
    reasons.push('P/E Ratio missing');
  } else {
    if (pe < config.minPeRatio) reasons.push('P/E below minimum');
    if (pe > config.maxPeRatio) reasons.push('P/E above maximum');
  }
  if (pb === null) reasons.push('P/B Ratio missing');
  else if (pb > config.maxPbRatio) reasons.push('P/B above maximum');
  if (ph === null) reasons.push('Promoter Holding missing');
  else if (ph < config.minPromoterHoldingPct) reasons.push('Low Promoter Holding');
  return reasons;
}

function category(name: string, score: number, maxScore: number): CategoryScore {
  return {
    name,
    score: round1(score),
    maxScore,
    percentage: round1((score / maxScore) * 100),
  };
}

/** Factual rationale from real factor contributions. Counterpart of build_explanation(). */
export function buildExplanation(
  stock: CleanedStock,
  total: number,
  parts: { fq: number; growth: number; balance: number; valuation: number; governance: number },
  reasons: string[],
  warningFlags: string[],
): string {
  const contributions: [string, number, number][] = [
    ['financial quality', parts.fq, 30],
    ['growth', parts.growth, 25],
    ['balance-sheet safety', parts.balance, 20],
    ['valuation', parts.valuation, 15],
    ['governance', parts.governance, 10],
  ];
  const ranked = [...contributions].sort((a, b) => {
    const ratio = b[1] / b[2] - a[1] / a[2];
    return ratio !== 0 ? ratio : compareCodePoints(a[0], b[0]);
  });
  const strongest = ranked[0];
  const weakest = ranked[ranked.length - 1];

  const out: string[] = [];
  out.push(`Total fundamental score ${fmt1(total)}/100.`);
  out.push(
    `Strongest factor: ${strongest[0]} at ${fmt1(strongest[1])}/${strongest[2]}; ` +
      `weakest: ${weakest[0]} at ${fmt1(weakest[1])}/${weakest[2]}.`,
  );
  const metrics: string[] = [];
  ([
    ['ROCE', 'roce', '%'],
    ['ROE', 'roe', '%'],
    ['D/E', 'debtToEquity', ''],
    ['P/E', 'peRatio', ''],
    ['promoter holding', 'promoterHolding', '%'],
  ] as [string, keyof CleanedStock, string][]).forEach(([label, key, suffix]) => {
    const value = stock[key];
    if (typeof value === 'number') metrics.push(`${label} ${fmt1(value)}${suffix}`);
  });
  if (metrics.length) out.push(`Key inputs: ${metrics.join(', ')}.`);
  out.push(reasons.length ? `Rejected because: ${reasons.join('; ')}.` : 'Passed every configured screening rule.');
  if (warningFlags.length) out.push(`Warnings: ${warningFlags.join(', ')}.`);
  return out.join(' ');
}

/**
 * Screen and score one stock. Counterpart of ScreeningEngine.evaluate().
 *
 * Three outcomes, decided in this order:
 *   not scored -- a financial company whose export lacks the metrics the
 *                 financial model needs. Saying so is honest; scoring it on
 *                 ratios that do not describe a lender is not.
 *   rejected   -- a hard red flag fired: the numbers cannot be trusted, so
 *                 there is nothing worth scoring.
 *   scored     -- graded sub-scores, each awarded point carrying its own line.
 *
 * The old pass/fail hurdles are preferences rather than data-integrity
 * problems, so they cost points instead of rejecting, and only reject when
 * strict_screen is on.
 *
 * medians comes from sectorMedians() over the whole loaded file and is what
 * makes valuation sector-relative. Evaluating a stock on its own, with no
 * medians, therefore scores no valuation points and says so in its score lines.
 */
/**
 * DESCRIPTIVE LABELS, NOT MEASURED CUT-OFFS. These numbers were chosen to
 * spread the current scoring scale so a long list can be read quickly. Nothing
 * tests that a "Strong" goes on to outperform a "Good", and until a backtest
 * says otherwise they carry no predictive claim at all. Do not cite them as
 * evidence, and do not tune them against the bundled sample -- its figures are
 * invented.
 */
const VERDICT_BANDS: readonly (readonly [number, string])[] = [
  [70, 'Strong'], [60, 'Good'], [45, 'Average'],
];
const VERDICT_WEAK = 'Weak';
const VERDICT_RED_FLAG = 'Red flag';
const VERDICT_NOT_SCORED = 'Not scored';

/**
 * The fundamental and technical halves combined, with text describing how.
 * Counterpart of combine_scores().
 *
 * A null technical score means confirmation is off, the run had no price
 * history at all, or this company is not in the price file. The composite is
 * then the fundamental score alone rather than the fundamental score diluted
 * towards zero -- a gap in the price file is a fact about the file, not
 * evidence against the company. Such companies are ranked separately by
 * processScreenerPipeline, because a composite without a technical half is not
 * on the same scale as one with it.
 */
export function combineScores(
  fundamental: number,
  technical: number | null,
  technicalWeightPct: number,
): { composite: number; basis: string } {
  if (technical === null) return { composite: round1(fundamental), basis: 'fundamental only' };
  const weight = clamp(technicalWeightPct, 0, 100) / 100;
  const composite = fundamental * (1 - weight) + technical * weight;
  return {
    composite: round1(composite),
    basis: `fundamentals ${round1((1 - weight) * 100)}% + technicals ${round1(weight * 100)}%`,
  };
}

/**
 * A descriptive band over the composite. Counterpart of verdict_for().
 *
 * These are labels for reading a long list quickly. They are NOT predictions
 * and are not validated against returns: the cut-offs were chosen to spread the
 * current scale, and nothing yet tests that a "Strong" outperforms a "Good".
 */
export function verdictFor(
  composite: number,
  redFlags: readonly string[],
  notScored: string | null,
): string {
  if (notScored) return VERDICT_NOT_SCORED;
  if (redFlags.length) return VERDICT_RED_FLAG;
  for (const [threshold, label] of VERDICT_BANDS) {
    if (composite >= threshold) return label;
  }
  return VERDICT_WEAK;
}

export function evaluateStock(
  stock: CleanedStock,
  config: ScreeningConfig,
  appConfig: AppConfig,
  medians: SectorMedians = sectorMedians([]),
): StockEvaluation {
  const reasons: string[] = [];
  const warningFlags: string[] = [];

  const isFinancial = FINANCIAL_SECTOR_RE.test(stock.sector || '');

  for (const filter of appConfig.custom_filters || []) {
    const value = (stock as unknown as Record<string, number | null>)[filter.field];
    const limit = parseStrictDecimal(filter.value);
    if (limit === null) {
      reasons.push(`Invalid numeric value in custom filter for ${filter.field}: ${jsonText(filter.value)}`);
      continue;
    }
    if (typeof value !== 'number' || value === null) {
      reasons.push(`Missing value for ${filter.field}`);
      continue;
    }
    const ok =
      filter.operator === '>' ? value > limit
      : filter.operator === '<' ? value < limit
      : filter.operator === '>=' ? value >= limit
      : filter.operator === '<=' ? value <= limit
      : filter.operator === '==' ? value === limit
      : value !== limit;
    if (!ok) {
      const inverse: Record<FilterOperator, string> = {
        '>': '<=', '<': '>=', '>=': '<', '<=': '>', '==': '!=', '!=': '==',
      };
      // `${limit}` is String(limit); Python reproduces it with js_number_to_string().
      reasons.push(`${filter.field} ${inverse[filter.operator]} ${limit}`);
    }
  }

  const { marketCap: mcap, promoterPledge: pp, dividendYield: div } = stock;

  // Coverage counts the fields the company's own model actually uses.
  const fields: string[] = [...COVERAGE_FIELDS_BASE];
  fields.push(...(isFinancial ? COVERAGE_FIELDS_FINANCIAL : COVERAGE_FIELDS_NON_FINANCIAL));
  const available = fields.filter(
    (f) => (stock as unknown as Record<string, unknown>)[f] !== null,
  ).length;
  const coverage = (available / fields.length) * 100;

  const gaps = isFinancial ? bankMetricGaps(stock) : [];
  // Reported before coverage, so a bank whose export simply lacks the bank
  // columns is told exactly which ones are missing rather than being dismissed
  // as an incomplete row.
  const notScored = gaps.length ? `Not scored: missing bank metrics (${gaps.join(', ')})` : null;
  const redFlags = notScored ? [] : hardRedFlags(stock, config, isFinancial, coverage);

  let parts: ScoreParts;
  let scoreLines: string[];
  if (notScored) {
    reasons.push(notScored);
    warningFlags.push('Missing Bank Metrics');
    parts = { ...ZERO_PARTS };
    scoreLines = [];
  } else if (redFlags.length) {
    // Scored anyway, so a comparison across the whole index can show what the
    // fundamentals look like beside the flag that disqualifies them: "Vedanta
    // scores 58 but its promoters have pledged" is worth more than a bare 0.0.
    // The flags stay in reasons, so the company still never reaches the
    // watchlist.
    reasons.push(...redFlags);
    const flagged = (isFinancial ? scoreFinancial : scoreGeneral)(stock, config, medians);
    parts = flagged.parts;
    scoreLines = flagged.lines;
  } else {
    const scored = (isFinancial ? scoreFinancial : scoreGeneral)(stock, config, medians);
    parts = scored.parts;
    scoreLines = scored.lines;
    if (appConfig.strict_screen) {
      reasons.push(...strictScreenFailures(stock, config, isFinancial));
    }
  }

  const fq = parts.financialQuality;
  const growth = parts.growth;
  const balance = parts.balanceSheetSafety;
  const valuation = parts.valuation;
  const governance = parts.governance;
  const total = clamp(fq + growth + balance + valuation + governance, 0, 100);

  const wasScored = notScored === null && redFlags.length === 0;
  if (wasScored && total < appConfig.minimum_total_score) {
    reasons.push(`Low Total Score: ${fmt1(total)}`);
  }

  if (div !== null && div < config.minDividendYieldPct) warningFlags.push('Low Dividend Yield');
  if (mcap !== null && mcap < 500) warningFlags.push('Micro Cap');
  if (pp !== null && pp > 0) warningFlags.push('Promoter Pledged');

  const technicalScore = calculateTechnicalScore(
    stock.technicals,
    appConfig.enable_technical_confirmation,
  );
  // Technical availability warnings belong in the displayed flag set, not a
  // separate list nobody reads.
  warningFlags.push(...technicalScore.warnings);

  // The composite is what the ranking sorts on. minimum_total_score still gates
  // the fundamental total: moving that gate onto the composite would be a second
  // recalibration with nothing to calibrate it against.
  const combined = combineScores(total, technicalScore.score, appConfig.technical_weight_pct);
  const verdict = verdictFor(combined.composite, redFlags, notScored);

  return {
    stock,
    passed: reasons.length === 0,
    rejectionReasons: reasons,
    warningFlags,
    score: round1(total),
    compositeScore: combined.composite,
    compositeBasis: combined.basis,
    verdict,
    // Filled in by the pipeline, the only place that sees every company at
    // once. Scoring one stock cannot know its peers, so the default says so
    // plainly rather than implying a comparison that never happened.
    sectorRelativeStrength6M: null,
    sectorRelativeStrengthBasis: 'not compared',
    // Also filled in by the pipeline, and for the same reason: a position
    // weight is a share of a basket, so it cannot exist until the basket does.
    // Only the watchlist is sized, so a company below the cut-off keeps these
    // defaults, and 'not sized' says that rather than implying a weight of zero
    // was calculated for it.
    positionWeightPct: null,
    stopPrice: null,
    stopDistancePct: null,
    sizingBasis: 'not sized',
    coveragePct: round1(coverage),
    redFlags,
    notScored,
    scoringModel: isFinancial ? 'financial' : 'general',
    scoreLines,
    sectorGroup: sectorGroup(stock.sector),
    technicalScore,
    categoryScores: {
      financialQuality: category('Financial', fq, 30),
      growth: category('Growth', growth, 25),
      balanceSheetSafety: category('Safety', balance, 20),
      valuation: category('Valuation', valuation, 15),
      governance: category('Governance', governance, 10),
    },
    explanation: buildExplanation(stock, total, { fq, growth, balance, valuation, governance }, reasons, warningFlags),
  };
}

// ---------------------------------------------------------------------------
// Data inspection
// ---------------------------------------------------------------------------

/** Column headers that carry the date the data describes. */
const FUNDAMENTALS_DATE_ALIASES = ['date', 'as on', 'as of', 'as at', 'report date', 'data date'];
const FILENAME_DATE_RE = /([0-9]{4}-[0-9]{2}-[0-9]{2})/;

export type FundamentalsDateSource = 'data date' | 'file name' | 'file timestamp';

/** Local date as YYYY-MM-DD. */
function isoDate(when: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${when.getFullYear()}-${pad(when.getMonth() + 1)}-${pad(when.getDate())}`;
}

/** Whole days from a YYYY-MM-DD date to today, both taken as local midnights. */
function daysSince(date: string): number {
  const [year, month, day] = date.split('-').map(Number);
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  return Math.round((today - new Date(year, month - 1, day).getTime()) / 86400000);
}

/**
 * The date the fundamentals describe and where that date came from, in order:
 * a date column inside the export ("Date", "As on", ...), an ISO date in the
 * file name, then the file's timestamp. Copying an old export resets its
 * timestamp, so the timestamp is the last resort and is always reported.
 * Counterpart of fundamentals_as_of() in python/engine.py.
 */
export function fundamentalsAsOf(
  rows: ScreenerRow[],
  fileName: string,
  lastModifiedTimestamp?: number,
): { date: string | null; source: FundamentalsDateSource | null } {
  const headers = rows.length > 0 ? Object.keys(rows[0]) : [];
  for (const header of headers) {
    if (FUNDAMENTALS_DATE_ALIASES.includes(normalizeHeader(header))) {
      const dates = rows
        .map((row) => String(row[header] ?? '').trim())
        .filter(isRealDate)
        .sort(compareCodePoints);
      if (dates.length > 0) return { date: dates[dates.length - 1], source: 'data date' };
    }
  }
  const match = FILENAME_DATE_RE.exec(fileName || '');
  if (match && isRealDate(match[1])) return { date: match[1], source: 'file name' };
  if (typeof lastModifiedTimestamp === 'number') {
    return { date: isoDate(new Date(lastModifiedTimestamp)), source: 'file timestamp' };
  }
  return { date: null, source: null };
}

const INSPECTED_FIELDS = [
  'name', 'ticker', 'bseCode', 'sector', 'currentPrice', 'marketCap',
  'salesGrowth', 'profitGrowth', 'roce', 'roe', 'debtToEquity',
  'interestCoverage', 'operatingCashFlow', 'promoterHolding', 'promoterPledge',
  'peRatio', 'pbRatio', 'dividendYield',
];

export function inspectData(
  rows: ScreenerRow[],
  filename: string,
  appConfig: AppConfig,
  lastModifiedTimestamp?: number,
): DataInspectionReport {
  const headers = rows.length > 0 ? Object.keys(rows[0]) : [];
  const mapping = detectColumnMapping(headers);
  const missingFields = INSPECTED_FIELDS.filter((f) => !mapping[f]);

  const asOf = fundamentalsAsOf(rows, filename, lastModifiedTimestamp);
  const fileAgeDays = asOf.date === null ? null : daysSince(asOf.date);
  const isStale = fileAgeDays !== null && fileAgeDays > appConfig.fundamentals_stale_after_days;
  const modDateStr = asOf.date ?? 'Not provided';

  const seen = new Set<string>();
  let duplicateRows = 0;
  for (const row of rows) {
    const canonical = JSON.stringify(row, Object.keys(row).sort());
    if (seen.has(canonical)) duplicateRows += 1;
    else seen.add(canonical);
  }

  const columns: ColumnProfile[] = headers.map((header) => {
    let mappedField: string | null = null;
    for (const [field, col] of Object.entries(mapping)) {
      if (col === header) { mappedField = field; break; }
    }
    let nonNullCount = 0;
    const sampleValues: string[] = [];
    let hasCurrency = false;
    let hasPercentage = false;
    let hasNumeric = false;
    let needsConversion = false;

    for (const row of rows) {
      const val = row[header];
      if (val === undefined || val === null || val === '') continue;
      nonNullCount += 1;
      const text = String(val).trim();
      if (sampleValues.length < 3) sampleValues.push(text);
      if (typeof val === 'number') { hasNumeric = true; continue; }
      const lower = text.toLowerCase();
      if (/[₹$€£]/.test(text) || /crore|\bcr\b|\blakh\b/.test(lower)) hasCurrency = true;
      else if (text.includes('%')) hasPercentage = true;
      if (/[₹$€£%,\s]|crore|\bcr\b|\blakh\b/.test(lower)) needsConversion = true;
      const cleaned = lower.replace(/[₹$€£%,\s]|crore|\bcr\b|\blakh\b/g, '');
      if (cleaned !== '' && !Number.isNaN(Number(cleaned))) hasNumeric = true;
    }

    const detectedType: ColumnProfile['detectedType'] = hasCurrency
      ? 'currency'
      : hasPercentage
      ? 'percentage'
      : hasNumeric
      ? 'numeric'
      : 'text';

    const nullCount = rows.length - nonNullCount;
    return {
      name: header,
      mappedField,
      detectedType,
      nonNullCount,
      nullCount,
      nullPercentage: rows.length > 0 ? round1((nullCount / rows.length) * 100) : 0,
      sampleValues,
      needsConversion: detectedType === 'text' ? false : needsConversion,
    };
  });

  return {
    filename,
    totalRows: rows.length,
    totalColumns: headers.length,
    duplicateRows,
    columns,
    detectedTickerCol: mapping.ticker || null,
    detectedNameCol: mapping.name || null,
    detectedBseCodeCol: mapping.bseCode || null,
    missingFields,
    fileAgeDays,
    fileModifiedDate: modDateStr,
    dataDate: asOf.date,
    dateSource: asOf.source,
    isStale,
    configErrors: validateCustomFilters(appConfig.custom_filters),
  };
}

// ---------------------------------------------------------------------------
// Pipeline
// ---------------------------------------------------------------------------

export interface PipelineResult {
  evaluations: StockEvaluation[];
  watchlist: StockEvaluation[];
  rejected: StockEvaluation[];
  inspectionReport: DataInspectionReport;
  duplicatesCount: number;
  /** Unique rows dropped because their ticker is not in the active universe. */
  outsideUniverseCount: number;
  /** Passed every rule but ranks below top_n; ranked, never dropped. */
  passedBelowCutOff: StockEvaluation[];
  /**
   * Passed every rule, but this run priced other companies and not these, so
   * their composite has no technical half. Ranked among themselves rather than
   * mixed into a list built on a different scale. Empty when no company in the
   * run has a technical score, because then every composite is comparable.
   */
  fundamentalOnly: StockEvaluation[];
  /**
   * What the sizing pass concluded for this run: which volatility measure it
   * used, the portfolio's own volatility, and how much of the account that put
   * to work. Null figures mean it could not be measured, never that it measured
   * zero.
   */
  sizing: SizingSummary;
}

/** Canonical watchlist ordering: score descending, then ticker ascending. */
export function sortByScoreThenTicker(items: StockEvaluation[]): StockEvaluation[] {
  // "Score" here is the composite, which is what the ranking is built on; it
  // equals the fundamental score whenever there is no technical half to fold in.
  return [...items].sort(
    (a, b) => b.compositeScore - a.compositeScore || compareCodePoints(a.stock.ticker, b.stock.ticker),
  );
}

/**
 * Run the full screen. Counterpart of ScreeningEngine.prepare() + screen().
 * priceHistory is a parsed price-history CSV, or null/undefined when the run
 * has none -- technical confirmation then reports "No price history loaded"
 * once instead of flagging every stock.
 */
export function processScreenerPipeline(
  rows: ScreenerRow[],
  appConfig: AppConfig,
  screeningConfig: ScreeningConfig,
  lastModifiedTimestamp?: number,
  priceHistory?: PriceHistory | null,
  fileName?: string,
): PipelineResult {
  const inspectionReport = inspectData(rows, fileName ?? 'screener.csv', appConfig, lastModifiedTimestamp);
  if (inspectionReport.configErrors.length > 0) {
    return {
      evaluations: [], watchlist: [], rejected: [], passedBelowCutOff: [],
      fundamentalOnly: [],
      sizing: {
        measure: null,
        targetVolatilityPct: appConfig.target_volatility_pct,
        portfolioVolatilityPct: null,
        deploymentPct: null,
        investedPct: null,
        basis: 'configuration is invalid, nothing was screened',
      },
      inspectionReport, duplicatesCount: 0, outsideUniverseCount: 0,
    };
  }

  const headers = rows.length > 0 ? Object.keys(rows[0]) : [];
  const mapping = detectColumnMapping(headers);
  const parsed = parseScreenerRows(rows, mapping);
  const { unique, duplicatesRemoved } = dedupeStocks(parsed);

  const allowed = new Set(
    appConfig.universe_mode === 'nifty100'
      ? NIFTY100_FALLBACK_SYMBOLS
      : normaliseSymbols(appConfig.custom_symbols),
  );
  let universe = allowed.size > 0 ? unique.filter((s) => allowed.has(s.ticker.toUpperCase())) : unique;
  const outsideUniverseCount = unique.length - universe.length;

  // Hoisted so the sector-relative pass below can take the same (stocks,
  // technicals) pair the Python engine does. Attaching them to the stock is a
  // convenience of this engine only, and letting the two drift apart in shape
  // is exactly what the parity suite cannot catch: it compares outputs.
  let technicals: Record<string, TechnicalIndicators> | null = null;
  if (priceHistory) {
    const loaded = technicalsFromHistory(priceHistory, universe.map((s) => s.ticker));
    technicals = loaded;
    universe = universe.map((s) => ({ ...s, technicals: loaded[s.ticker] }));
  }

  // One set of yardsticks for the whole run, computed from the companies
  // actually being screened, so valuation is judged against this file's sectors
  // rather than a hard-coded notion of "expensive".
  const medians = sectorMedians(universe);
  // Sector-relative strength is cross-sectional: no company can be placed
  // against its peers until every peer has been measured. So it is attached
  // after scoring, which is also the reason it can never influence a score --
  // it does not exist until the scores are final.
  const rsBuckets = sectorRelativeStrength(universe, technicals);
  const evaluations = universe
    .map((s) => evaluateStock(s, screeningConfig, appConfig, medians))
    .map((ev) => {
      const own = ev.stock.technicals?.relativeStrength6M ?? null;
      const [peer, basis] = relativeStrengthYardstick(rsBuckets, ev.stock.sector);
      if (own === null) {
        return { ...ev, sectorRelativeStrengthBasis: '6M relative strength unavailable' };
      }
      if (peer === null) return { ...ev, sectorRelativeStrengthBasis: basis };
      return { ...ev, sectorRelativeStrength6M: round1(own - peer), sectorRelativeStrengthBasis: basis };
    });

  // Every passing stock is ranked, then the list is split at top_n: the ones
  // below the cut-off are reported separately rather than dropped.
  // A composite built without a technical half is not on the same scale as one
  // built with it. At the default weights, a company with fundamentals 90 and no
  // price data scores 90, while an identical company whose technicals scored 50
  // gets 0.6*90 + 0.4*50 = 74 -- so being absent from the price file would be
  // worth sixteen points, and worth most to recent listings, illiquid names and
  // whatever the download was rate-limited out of. Those companies are ranked in
  // a list of their own rather than competing on a scale they never faced.
  //
  // When NO company has a technical score -- confirmation switched off, or a run
  // with no price history at all -- every composite is fundamental only, which is
  // one consistent scale, so the split does not apply.
  const allPassed = evaluations.filter((e) => e.passed);
  const technicalInPlay = evaluations.some((e) => e.technicalScore.score !== null);
  const rankable = technicalInPlay
    ? allPassed.filter((e) => e.technicalScore.score !== null)
    : allPassed;
  const fundamentalOnly = technicalInPlay
    ? sortByScoreThenTicker(allPassed.filter((e) => e.technicalScore.score === null))
      .map((item, idx) => ({ ...item, rank: idx + 1 }))
    : [];
  const passed = sortByScoreThenTicker(rankable)
    .map((item, idx) => ({ ...item, rank: idx + 1 }));
  const cutOff = appConfig.top_n > 0 ? appConfig.top_n : passed.length;
  const watchlist = passed.slice(0, cutOff);
  const passedBelowCutOff = passed.slice(cutOff);

  const rejected = sortByScoreThenTicker(evaluations.filter((e) => !e.passed));

  // Position sizing is cross-sectional like the block above, but it runs later
  // still, because a weight is a share of a basket and the basket is not decided
  // until the cut-off is applied. Only the watchlist is sized: a company below
  // the cut-off is not being bought, so it has no weight rather than a weight of
  // zero. Nothing here can reach a score -- the scores were final before this.
  const { summary: sizing, sizing: sizingByTicker } = sizePositions(watchlist, priceHistory, appConfig);
  // Applied to every view, not just the watchlist. python/engine.py mutates the
  // watchlist dicts and those same objects are aliased into its evaluations
  // list, so the weights appear in both there. These arrays are independent
  // copies made by .map(), so without this the two engines would disagree about
  // which lists carry weights -- and the parity driver reads them off
  // evaluations.
  const withSizing = (item: StockEvaluation): StockEvaluation => {
    const fields = sizingByTicker.get(item.stock.ticker);
    return fields ? { ...item, ...fields } : item;
  };

  return {
    evaluations: evaluations.map(withSizing),
    watchlist: watchlist.map(withSizing),
    passedBelowCutOff,
    fundamentalOnly,
    rejected: rejected.map(withSizing),
    inspectionReport,
    sizing,
    duplicatesCount: duplicatesRemoved, outsideUniverseCount,
  };
}

// ---------------------------------------------------------------------------
// Delta tracking
// ---------------------------------------------------------------------------

export const RANKING_CHANGE_COLUMNS = [
  'Ticker', 'Name', 'ChangeType', 'PreviousRank', 'CurrentRank', 'RankDelta',
  'PreviousScore', 'CurrentScore', 'ScoreDelta', 'NewWarnings',
] as const;

/**
 * Snapshot entries usable for delta tracking; malformed ones are dropped. A
 * hand-edited or half-written saved run must never blank the app.
 * Counterpart of valid_snapshot_entries() in python/engine.py.
 */
export function validSnapshotEntries(data: unknown): WatchlistSnapshotEntry[] {
  if (!Array.isArray(data)) return [];
  const entries: WatchlistSnapshotEntry[] = [];
  for (const raw of data) {
    if (raw === null || typeof raw !== 'object' || Array.isArray(raw)) continue;
    const { ticker, name, rank, score, warningFlags } = raw as Record<string, unknown>;
    if (typeof ticker !== 'string' || ticker === '') continue;
    if (typeof rank !== 'number' || !Number.isFinite(rank)) continue;
    if (typeof score !== 'number' || !Number.isFinite(score)) continue;
    entries.push({
      ticker,
      name: typeof name === 'string' ? name : ticker,
      rank,
      score,
      warningFlags: Array.isArray(warningFlags)
        ? warningFlags.filter((flag): flag is string => typeof flag === 'string')
        : [],
    });
  }
  return entries;
}

/** Browser storage key holding the saved run the next run is compared against. */
export const SAVED_RUN_KEY = 'previousWatchlist';

/** What "Save run" stores: the watchlist plus what produced it. */
export interface SavedRun {
  savedAt: string | null;
  fileName: string | null;
  appConfig: AppConfig | null;
  screeningConfig: ScreeningConfig | null;
  entries: WatchlistSnapshotEntry[];
}

/**
 * Read a saved run: the object form, or the bare array older versions stored.
 * Null when nothing usable is in it, so a bad value is discarded rather than
 * thrown at the delta code.
 */
export function parseSavedRun(data: unknown): SavedRun | null {
  const blank = { savedAt: null, fileName: null, appConfig: null, screeningConfig: null };
  if (Array.isArray(data)) {
    const entries = validSnapshotEntries(data);
    return entries.length > 0 ? { ...blank, entries } : null;
  }
  if (data === null || typeof data !== 'object') return null;
  const record = data as Record<string, unknown>;
  const entries = validSnapshotEntries(record.entries);
  if (entries.length === 0) return null;
  return {
    savedAt: typeof record.savedAt === 'string' ? record.savedAt : null,
    fileName: typeof record.fileName === 'string' ? record.fileName : null,
    appConfig: (record.appConfig as AppConfig | undefined) ?? null,
    screeningConfig: (record.screeningConfig as ScreeningConfig | undefined) ?? null,
    entries,
  };
}

/** Reduce a watchlist to the persisted snapshot shape (no rawRow). */
export function toSnapshot(watchlist: StockEvaluation[]): WatchlistSnapshotEntry[] {
  return watchlist.map((item, idx) => ({
    ticker: item.stock.ticker,
    name: item.stock.name,
    rank: item.rank ?? idx + 1,
    score: item.score,
    warningFlags: item.warningFlags,
  }));
}

/**
 * Canonical delta computation. Counterpart of compute_ranking_changes().
 * RankDelta = previousRank - currentRank (positive means moved up); null where
 * an entry or removal makes the comparison undefined.
 */
export function computeRankingChanges(
  current: WatchlistSnapshotEntry[],
  previous: WatchlistSnapshotEntry[] | null,
): RankingChange[] {
  const prevMap = new Map<string, WatchlistSnapshotEntry>();
  for (const item of previous || []) prevMap.set(item.ticker, item);

  const changes: RankingChange[] = [];
  const seen = new Set<string>();

  for (const item of [...current].sort((a, b) => a.rank - b.rank)) {
    seen.add(item.ticker);
    const prev = prevMap.get(item.ticker);
    if (!prev) {
      changes.push({
        ticker: item.ticker,
        name: item.name || item.ticker,
        changeType: 'NEW_ENTRY',
        previousRank: null,
        currentRank: item.rank,
        rankDelta: null,
        previousScore: null,
        currentScore: item.score,
        scoreDelta: null,
        newWarnings: [...item.warningFlags],
      });
      continue;
    }
    const prevWarnings = new Set(prev.warningFlags);
    changes.push({
      ticker: item.ticker,
      name: item.name || item.ticker,
      changeType:
        item.rank < prev.rank ? 'RANK_UP' : item.rank > prev.rank ? 'RANK_DOWN' : 'STABLE',
      previousRank: prev.rank,
      currentRank: item.rank,
      rankDelta: prev.rank - item.rank,
      previousScore: prev.score,
      currentScore: item.score,
      scoreDelta: round1(item.score - prev.score),
      newWarnings: item.warningFlags.filter((w) => !prevWarnings.has(w)),
    });
  }

  const removed = [...prevMap.values()]
    .filter((p) => !seen.has(p.ticker))
    .sort((a, b) => a.rank - b.rank);
  for (const prev of removed) {
    changes.push({
      ticker: prev.ticker,
      name: prev.name || prev.ticker,
      changeType: 'REMOVED_ENTRY',
      previousRank: prev.rank,
      currentRank: null,
      rankDelta: null,
      previousScore: prev.score,
      currentScore: null,
      scoreDelta: null,
      newWarnings: [],
    });
  }
  return changes;
}

/** Columns that hold numbers and must stay numeric in the export. */
const DELTA_NUMERIC_COLUMNS = new Set([
  'PreviousRank', 'CurrentRank', 'RankDelta', 'PreviousScore', 'CurrentScore', 'ScoreDelta',
]);

function deltaCell(column: string, change: RankingChange): string {
  switch (column) {
    case 'Ticker': return change.ticker;
    case 'Name': return change.name;
    case 'ChangeType': return change.changeType;
    case 'PreviousRank': return change.previousRank === null ? '' : String(change.previousRank);
    case 'CurrentRank': return change.currentRank === null ? '' : String(change.currentRank);
    case 'RankDelta': return change.rankDelta === null ? '' : String(change.rankDelta);
    case 'PreviousScore': return fmt1(change.previousScore);
    case 'CurrentScore': return fmt1(change.currentScore);
    case 'ScoreDelta': return fmt1(change.scoreDelta);
    case 'NewWarnings': return change.newWarnings.join(', ');
    default: return '';
  }
}

/** Byte-identical to ranking_changes_to_csv() in python/engine.py. */
export function generateRankingChangesCsv(changes: RankingChange[]): string {
  const lines = [csvRow([...RANKING_CHANGE_COLUMNS])];
  for (const change of changes) {
    lines.push(
      csvRow(
        RANKING_CHANGE_COLUMNS.map((col) => {
          const cell = deltaCell(col, change);
          // Numeric columns are written as numbers; a negative delta must not
          // become text just because it starts with a minus sign.
          return DELTA_NUMERIC_COLUMNS.has(col) ? cell : textCell(cell);
        }),
      ),
    );
  }
  return `${lines.join('\n')}\n`;
}

export const WATCHLIST_CSV_COLUMNS = [
  'Rank', 'Ticker', 'Name', 'Sector', 'CurrentPrice', 'MarketCapCr', 'Score',
  'TechScore', 'Composite', 'Verdict', 'Coverage', 'FinancialQuality',
  'Growth', 'BalanceSheet', 'Valuation', 'Governance',
  // The four blocks behind TechScore. Blank rather than zero when the company
  // has no technical score at all: an empty cell says "not measured", a zero
  // would say "measured and found wanting".
  'Trend', 'Momentum', 'Volume', 'RelStrength',
  // Position sizing. Blank rather than zero when a company could not be sized,
  // for the same reason the block columns are: an empty cell reads as "not
  // measured", a zero reads as "measured and found to be nothing".
  'WeightPct', 'StopPrice', 'StopDistancePct', 'SizingBasis',
  'WarningFlags',
] as const;

/**
 * One technical block subtotal, blank when the company has no score to break
 * down. Counterpart of _block() in python/engine.py.
 */
function blockCell(item: StockEvaluation, name: keyof TechnicalBlocks): string {
  const blocks = item.technicalScore.blocks;
  return blocks === null ? '' : fmt1(blocks[name]);
}

export const REJECTED_CSV_COLUMNS = [
  'Ticker', 'Name', 'Sector', 'Score', 'Coverage', 'RejectionReasons', 'WarningFlags',
] as const;

/** Byte-identical to watchlist_to_csv() in python/engine.py. */
export function generateWatchlistCsv(rows: StockEvaluation[]): string {
  const lines = [csvRow([...WATCHLIST_CSV_COLUMNS])];
  rows.forEach((item, idx) => {
    const c = item.categoryScores;
    lines.push(csvRow([
      String(item.rank ?? idx + 1),
      textCell(item.stock.ticker),
      textCell(item.stock.name),
      textCell(item.stock.sector),
      fmt1(item.stock.currentPrice),
      fmt1(item.stock.marketCap),
      fmt1(item.score),
      item.technicalScore.score === null ? '' : fmt1(item.technicalScore.score),
      fmt1(item.compositeScore),
      textCell(item.verdict),
      fmt1(item.coveragePct),
      fmt1(c.financialQuality.score),
      fmt1(c.growth.score),
      fmt1(c.balanceSheetSafety.score),
      fmt1(c.valuation.score),
      fmt1(c.governance.score),
      blockCell(item, 'trend'),
      blockCell(item, 'momentum'),
      blockCell(item, 'volume'),
      blockCell(item, 'relStrength'),
      item.positionWeightPct === null ? '' : fmt1(item.positionWeightPct),
      item.stopPrice === null ? '' : fmt1(item.stopPrice),
      item.stopDistancePct === null ? '' : fmt1(item.stopDistancePct),
      textCell(item.sizingBasis),
      textCell(item.warningFlags.join(', ')),
    ]));
  });
  return `${lines.join('\n')}\n`;
}

/** Byte-identical to rejected_to_csv() in python/engine.py. */
export function generateRejectedCsv(rows: StockEvaluation[]): string {
  const lines = [csvRow([...REJECTED_CSV_COLUMNS])];
  for (const item of rows) {
    lines.push(csvRow([
      textCell(item.stock.ticker),
      textCell(item.stock.name),
      textCell(item.stock.sector),
      fmt1(item.score),
      fmt1(item.coveragePct),
      textCell(item.rejectionReasons.join('; ')),
      textCell(item.warningFlags.join(', ')),
    ]));
  }
  return `${lines.join('\n')}\n`;
}

// ---------------------------------------------------------------------------
// HTML report
// ---------------------------------------------------------------------------

/** Escape every user-derived string before it reaches the DOM or a report. */
export function escapeHtml(unsafe: unknown): string {
  return String(unsafe ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

export function generateHtmlReport(
  watchlist: StockEvaluation[],
  belowCutOff: StockEvaluation[],
  rejected: StockEvaluation[],
  report: DataInspectionReport,
  appConfig: AppConfig,
  /**
   * Passed, but unpriced by this run, so ranked on a different scale. Defaulted
   * so existing callers keep working; appended rather than inserted so their
   * positional arguments keep meaning what they meant.
   */
  fundamentalOnly: StockEvaluation[] = [],
  /**
   * What the sizing pass concluded. Appended with a default for the same reason
   * fundamentalOnly was: existing callers pass five or six positional arguments
   * and must keep meaning what they meant. Null renders the report exactly as
   * before, which is honest -- nothing is claimed about exposure.
   */
  sizing: SizingSummary | null = null,
): string {
  const candidateRows = (items: StockEvaluation[]) =>
    items
      .map(
        (item, idx) => `
    <tr>
      <td>${item.rank ?? idx + 1}</td>
      <td>${escapeHtml(item.stock.ticker)}</td>
      <td>${escapeHtml(item.stock.name)}</td>
      <td>${escapeHtml(item.stock.sector)}</td>
      <td class="score">${escapeHtml(fmt1(item.score))}</td>
      <td>${escapeHtml(item.technicalScore.score === null ? 'N/A' : fmt1(item.technicalScore.score))}</td>
      <td>${item.positionWeightPct === null ? '&mdash;' : `${escapeHtml(fmt1(item.positionWeightPct))}%`}</td>
      <td>${item.stopPrice === null ? '&mdash;' : escapeHtml(fmt1(item.stopPrice))}</td>
      <td class="warning">${escapeHtml(item.warningFlags.join(', '))}</td>
    </tr>
    <tr class="rationale"><td colspan="9">${escapeHtml(item.explanation)}</td></tr>`,
      )
      .join('');
  const rows = candidateRows(watchlist);

  const rejectedRows = rejected
    .slice(0, 50)
    .map(
      (item) => `
    <tr>
      <td>${escapeHtml(item.stock.ticker)}</td>
      <td>${escapeHtml(fmt1(item.score))}</td>
      <td class="warning">${escapeHtml(item.rejectionReasons.join('; '))}</td>
    </tr>`,
    )
    .join('');

  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Indian Stock Screening Report</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; line-height: 1.6; color: #333; max-width: 1200px; margin: 0 auto; padding: 20px; }
    h1, h2 { color: #1e3a8a; }
    table { width: 100%; border-collapse: collapse; margin-bottom: 30px; font-size: 14px; }
    th, td { padding: 10px; border-bottom: 1px solid #e2e8f0; text-align: left; }
    th { background-color: #f8fafc; font-weight: 600; color: #475569; }
    .score { font-weight: bold; color: #059669; }
    .warning { color: #dc2626; font-size: 12px; }
    .rationale td { font-size: 12px; color: #475569; background: #f8fafc; }
    .header-box { background: #f0f9ff; border: 1px solid #bae6fd; padding: 20px; border-radius: 8px; margin-bottom: 30px; }
  </style>
</head>
<body>
  <div class="header-box">
    <h1>Indian Equity Screening Report</h1>
    <p><strong>Generated:</strong> ${escapeHtml(new Date().toISOString())}</p>
    <p><strong>Universe mode:</strong> ${escapeHtml(appConfig.universe_mode)}</p>
    <p><strong>Universe snapshot:</strong> cached, as of ${escapeHtml(NIFTY100_PROVENANCE.as_of_date)}</p>
    <p><strong>Rows scanned:</strong> ${report.totalRows}</p>
    <p><strong>Candidates passed:</strong> ${watchlist.length + belowCutOff.length}</p>
    ${sizing === null ? '' : (sizing.deploymentPct === null || sizing.investedPct === null
      ? `<p><strong>Position sizing:</strong> none &mdash; ${escapeHtml(sizing.basis)}.
    Relative weights alone would read as &quot;invest all of this&quot;, a claim about total
    exposure that nothing in this run measured, so no weight is shown.</p>`
      : `<p><strong>Position sizing:</strong> ${escapeHtml(fmt1(sizing.investedPct))}% invested,
    <strong>${escapeHtml(fmt1(round1(100 - sizing.investedPct)))}% held in cash</strong>.
    Portfolio volatility ${escapeHtml(fmt1(sizing.portfolioVolatilityPct))}% against a
    ${escapeHtml(fmt1(sizing.targetVolatilityPct))}% target, which permitted
    ${escapeHtml(fmt1(sizing.deploymentPct))}% before the per-position and sector caps.</p>
    <p>The cash is the volatility target doing its job, not a shortfall: fewer holdings, or
    more correlated ones, raise portfolio volatility and lower how much is put to work.
    Stops are ${escapeHtml(fmt1(round1(STOP_ATR_MULTIPLE)))}x ATR, set in advance; that
    multiple is ours and matches no figure in the sources, so it is not a protection the
    books endorse.</p>`)}
  </div>
  <h2>Top candidates (top ${appConfig.top_n})</h2>
  <table>
    <tr><th>Rank</th><th>Ticker</th><th>Name</th><th>Sector</th><th>Score</th><th>Tech</th><th>Weight</th><th>Stop</th><th>Warnings</th></tr>${rows}
  </table>
  ${belowCutOff.length === 0 ? '' : `<h2>Passed, below the top ${appConfig.top_n}</h2>
  <table>
    <tr><th>Rank</th><th>Ticker</th><th>Name</th><th>Sector</th><th>Score</th><th>Tech</th><th>Weight</th><th>Stop</th><th>Warnings</th></tr>${candidateRows(belowCutOff)}
  </table>`}
  ${fundamentalOnly.length === 0 ? '' : `<h2>Passed, but this run could not price them</h2>
  <p>Ranked separately: with no technical half, their composite is not on the same
  scale as the list above, and mixing the two would reward absence from the price file.</p>
  <table>
    <tr><th>Rank</th><th>Ticker</th><th>Name</th><th>Sector</th><th>Score</th><th>Tech</th><th>Weight</th><th>Stop</th><th>Warnings</th></tr>${candidateRows(fundamentalOnly)}
  </table>`}
  <h2>Rejected sample (first 50)</h2>
  <table>
    <tr><th>Ticker</th><th>Score</th><th>Rejection reasons</th></tr>${rejectedRows}
  </table>
</body>
</html>`;
}
