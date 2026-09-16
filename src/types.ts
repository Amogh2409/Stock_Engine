/**
 * Shared types for the browser screening engine.
 *
 * These mirror the dictionaries produced by python/engine.py field-for-field so
 * the cross-engine parity test can compare them directly.
 */

export interface ScreenerRow {
  [key: string]: string | number | null | undefined;
}

/** Which indicators actually had enough history to be computed. */
export interface TechnicalAvailability {
  sma50: boolean;
  sma200: boolean;
  smaCross: boolean;
  relativeStrength6M: boolean;
  high52Week: boolean;
}

export interface TechnicalIndicators {
  currentPrice: number | null;
  sma50: number | null;
  sma200: number | null;
  isAboveSma50: boolean | null;
  isAboveSma200: boolean | null;
  isSma50Above200: boolean | null;
  /** % outperformance vs benchmark over the last 126 sessions. */
  relativeStrength6M: number | null;
  volumeRatio20D: number | null;
  /** (price - 52w high) / 52w high * 100. Null unless 252 sessions exist. */
  distFrom52WHighPct: number | null;
  volatility30D: number | null;
  /** Max over the last 252 valid sessions. Null with fewer than 252. */
  high52Week: number | null;
  /**
   * Chart indicators. Null means "not enough history", or "this price file
   * carries no highs and lows", never "zero". Availability is expressed by the
   * value itself, which is why `available` below still lists only the five
   * indicators the technical score is built from.
   */
  rsi14: number | null;
  macdLine: number | null;
  macdSignal: number | null;
  macdHistogram: number | null;
  adx14: number | null;
  diPlus14: number | null;
  diMinus14: number | null;
  atr14: number | null;
  atrPct: number | null;
  /** 0 is the lower Bollinger band, 100 the upper; outside runs past either. */
  bollingerPercentB: number | null;
  /** Net signed volume over 20 sessions, as a percentage of total volume. */
  obvPressure20D: number | null;
  roc1M: number | null;
  roc3M: number | null;
  roc6M: number | null;
  roc12M: number | null;
  /** Distance below the highest close in the loaded history. */
  drawdownFromPeakPct: number | null;
  relativeStrength3M: number | null;
  relativeStrength12M: number | null;
  source: string;
  as_of: string | null;
  history_rows: number;
  available: TechnicalAvailability;
  data_status: 'COMPLETE' | 'PARTIAL' | 'UNAVAILABLE';
}

/**
 * The four blocks behind a technical score. Null when there is no score to
 * break down -- technical confirmation off, no price history, or a history too
 * short to stand beside companies measured on every indicator.
 */
export interface TechnicalBlocks {
  trend: number;
  momentum: number;
  relStrength: number;
  volume: number;
}

export interface TechnicalScoreResult {
  /** Null when disabled or when no indicator is available. */
  score: number | null;
  maxScore: number;
  breakdown: string[];
  /** Availability warnings, merged into StockEvaluation.warningFlags. */
  warnings: string[];
  /** Per-block subtotals behind `score`, or null when there is no score. */
  blocks: TechnicalBlocks | null;
}

export interface CleanedStock {
  id: string;
  name: string;
  ticker: string;
  bseCode: string | null;
  sector: string;
  currentPrice: number | null;
  /** Rupee crore. */
  marketCap: number | null;
  salesGrowth: number | null;
  profitGrowth: number | null;
  roce: number | null;
  roe: number | null;
  debtToEquity: number | null;
  interestCoverage: number | null;
  /** Rupee crore. */
  operatingCashFlow: number | null;
  promoterHolding: number | null;
  promoterPledge: number | null;
  peRatio: number | null;
  pbRatio: number | null;
  dividendYield: number | null;
  /** Absolute revenue in rupee crore, when the export carries such a column. */
  sales: number | null;
  /** Optional; the direct test for negative net worth when an export carries it. */
  shareholdersEquity: number | null;
  /**
   * Financial-company metrics. Null for every company whose export lacks them,
   * which is what puts a bank into "not scored: missing bank metrics".
   */
  returnOnAssets: number | null;
  grossNpa: number | null;
  netNpa: number | null;
  capitalAdequacy: number | null;
  casa: number | null;
  /** Screener.in's "Financing Margin %", its nearest equivalent to NIM. */
  financingMargin: number | null;
  /**
   * Null when the run has no price history at all; an UNAVAILABLE record when
   * history was loaded but this ticker is not in it.
   */
  technicals: TechnicalIndicators | null;
  /**
   * Set when a dropped duplicate row reported different numbers from this one.
   * A hard red flag: with two disagreeing rows there is no way to tell which
   * describes the company.
   */
  duplicateConflict?: boolean;
  rawRow: ScreenerRow;
}

/** Which scoring model produced a company's numbers. */
export type ScoringModel = 'general' | 'financial';

/** Median P/E and P/B for one bucket, with the sample size behind each. */
export interface SectorMedian {
  peRatio: number | null;
  pbRatio: number | null;
  peCount: number;
  pbCount: number;
}

/**
 * Valuation yardsticks derived from the loaded file itself: the fine Screener.in
 * industry, the coarse sector group, and the whole universe. A bucket is only
 * used when enough companies in it report the metric; see MIN_MEDIAN_SAMPLE.
 */
export interface SectorMedians {
  byIndustry: Record<string, SectorMedian>;
  byGroup: Record<string, SectorMedian>;
  universe: SectorMedian;
}

/** Median 6-month relative strength for one bucket, with its sample size. */
export interface RelativeStrengthBucket {
  value: number | null;
  count: number;
}

/**
 * Peer yardsticks for relative strength, bucketed exactly like SectorMedians:
 * the fine Screener.in industry, the coarse sector group, and the whole
 * universe. Only companies that actually have a 6-month figure feed a bucket.
 */
export interface SectorRelativeStrength {
  byIndustry: Record<string, RelativeStrengthBucket>;
  byGroup: Record<string, RelativeStrengthBucket>;
  universe: RelativeStrengthBucket;
}

export interface ScreeningConfig {
  minMarketCapCr: number;
  minSalesGrowthPct: number;
  minProfitGrowthPct: number;
  minRocePct: number;
  minRoePct: number;
  maxDebtToEquity: number;
  minInterestCoverage: number;
  requirePositiveOcf: boolean;
  minPromoterHoldingPct: number;
  maxPromoterPledgePct: number;
  minPeRatio: number;
  maxPeRatio: number;
  maxPbRatio: number;
  minDividendYieldPct: number;
  minimum_fundamental_coverage: number;
}

export type FilterOperator = '>' | '<' | '>=' | '<=' | '==' | '!=';

export interface CustomFilter {
  field: string;
  operator: FilterOperator;
  value: number | string;
}

export interface AppConfig {
  universe_mode: 'nifty100' | 'custom';
  custom_symbols: string[];
  custom_filters: CustomFilter[];
  top_n: number;
  minimum_total_score: number;
  fundamentals_stale_after_days: number;
  enable_technical_confirmation: boolean;
  /**
   * Share of the composite score the technical half carries, 0-100. The
   * fundamental half takes the remainder, so the two can never sum to anything
   * but 100.
   */
  technical_weight_pct: number;
  /**
   * Re-apply the old pass/fail hurdles as a filter over the ranked list. Off by
   * default, so every company surviving the hard red flags is scored and ranked.
   */
  strict_screen: boolean;
  /**
   * Annualised volatility the sized basket aims at, which decides how much of
   * the account is deployed. TSaM p.53 offers 12% ("a modest risk level") and
   * p.1048 offers "typically about 15%", then calls 15% aggressive in its own
   * example; 12% is a choice within that range, not a derivation.
   */
  target_volatility_pct: number;
  /** Most of the account any one position may take. Convention, per TSaM p.1040. */
  max_position_weight_pct: number;
  /** Most of the account any one sector group may take. Convention, per TSaM p.1040. */
  max_sector_weight_pct: number;
}

export interface CategoryScore {
  name: string;
  score: number;
  maxScore: number;
  percentage: number;
}

export interface CategoryScores {
  financialQuality: CategoryScore;
  growth: CategoryScore;
  balanceSheetSafety: CategoryScore;
  valuation: CategoryScore;
  governance: CategoryScore;
}

export interface StockEvaluation {
  stock: CleanedStock;
  passed: boolean;
  rejectionReasons: string[];
  warningFlags: string[];
  /** 0-100, one decimal, half-up. Identical to the Python engine's value. */
  score: number;
  /** Share of expected fundamental fields present, one decimal. */
  coveragePct: number;
  /**
   * Rules that make the company's numbers untrustworthy. Non-empty means it was
   * rejected outright and never scored.
   */
  redFlags: string[];
  /**
   * Non-null when the company could not be scored at all -- a financial company
   * whose export lacks the metrics the financial model needs.
   */
  notScored: string | null;
  /** Which model produced the sub-scores. */
  scoringModel: ScoringModel;
  /** One line per awarded point, in the order the points were awarded. */
  scoreLines: string[];
  /** Coarse sector group, or null when the industry label matches none. */
  sectorGroup: string | null;
  /** 1-based rank within the sorted, truncated watchlist. */
  rank?: number;
  /**
   * Fundamental and technical halves combined, and what the ranking sorts on.
   * Equal to `score` when there is no technical score to combine.
   */
  compositeScore: number;
  /** How the composite was arrived at, for display beside it. */
  compositeBasis: string;
  /** Descriptive band over the composite. A label, not a prediction. */
  verdict: string;
  /**
   * 6-month relative strength minus the median of this company's sector peers.
   * Null when the company has no 6M figure, or when no peer bucket qualified.
   *
   * Diagnostic only: it earns no points, and it is computed after scoring so
   * that it cannot reach one. Beating a broad index says little when the whole
   * sector is beating it; this says whether the company beat its own peers.
   */
  sectorRelativeStrength6M: number | null;
  /** Which peer bucket the comparison used, or why there was none. */
  sectorRelativeStrengthBasis: string;
  /**
   * Share of total capital this position should take, or null when it was not
   * sized. Only the watchlist is sized -- a weight is a share of a basket, so a
   * company below the cut-off has no weight rather than a weight of zero.
   *
   * Equal risk by volatility, per TSaM p.1103 and Table 24.1 at p.1104, scaled
   * to a portfolio volatility target and then capped. Null also when the
   * portfolio's volatility could not be measured: relative weights on their own
   * would read as "invest all of this", a claim about total exposure that
   * nothing has measured.
   */
  positionWeightPct: number | null;
  /** Stop level set in advance, per TSaM p.1032 principle 2. Null without an ATR. */
  stopPrice: number | null;
  /** How far the stop sits below the price, as a percentage. */
  stopDistancePct: number | null;
  /** Which measure sized this position, or why it could not be sized. */
  sizingBasis: string;
  technicalScore: TechnicalScoreResult;
  categoryScores: CategoryScores;
  /** Factual rationale built from real factor contributions. Never empty. */
  explanation: string;
}

export type RankingChangeType =
  | 'NEW_ENTRY'
  | 'RANK_UP'
  | 'RANK_DOWN'
  | 'REMOVED_ENTRY'
  | 'STABLE';

/**
 * Canonical delta record. Field names match the exported CSV headers and the
 * Python engine exactly. RankDelta = previousRank - currentRank, so a positive
 * value means the stock moved up. Deltas are null where an entry or removal
 * makes the comparison undefined.
 */
export interface RankingChange {
  ticker: string;
  name: string;
  changeType: RankingChangeType;
  previousRank: number | null;
  currentRank: number | null;
  rankDelta: number | null;
  previousScore: number | null;
  currentScore: number | null;
  scoreDelta: number | null;
  newWarnings: string[];
}

/** Minimal persisted snapshot. Deliberately excludes rawRow. */
export interface WatchlistSnapshotEntry {
  ticker: string;
  name: string;
  rank: number;
  score: number;
  warningFlags: string[];
}

export interface ColumnProfile {
  name: string;
  mappedField: string | null;
  detectedType: 'numeric' | 'percentage' | 'currency' | 'text';
  nonNullCount: number;
  nullCount: number;
  nullPercentage: number;
  sampleValues: string[];
  needsConversion: boolean;
}

export interface DataInspectionReport {
  filename: string;
  totalRows: number;
  totalColumns: number;
  duplicateRows: number;
  columns: ColumnProfile[];
  detectedTickerCol: string | null;
  detectedNameCol: string | null;
  detectedBseCodeCol: string | null;
  missingFields: string[];
  fileAgeDays: number | null;
  fileModifiedDate: string;
  /** Date the data describes (YYYY-MM-DD), or null when nothing says. */
  dataDate: string | null;
  /** Where dataDate came from, so staleness can be labelled honestly. */
  dateSource: 'data date' | 'file name' | 'file timestamp' | null;
  isStale: boolean;
  configErrors: string[];
}

export interface TestResult {
  name: string;
  category: string;
  passed: boolean;
  message: string;
  executionTimeMs: number;
}
