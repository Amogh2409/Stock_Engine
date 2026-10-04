import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { MarketStructurePanel } from '../components/MarketStructurePanel';
import { SelectionReviewTable } from '../components/SelectionReviewTable';
import { computeMarketStructure, DEFAULT_APP_CONFIG, DEFAULT_SCREENING_CONFIG, generateSelectionReviewCsv,
  parseCsv, PriceSeries, processScreenerPipeline, selectionReview } from '../utils/screenerEngine';

function bars(n = 21): PriceSeries {
  return {
    dates: Array.from({ length: n }, (_, i) => `2020-01-${String(i + 1).padStart(2, '0')}`),
    closes: Array(n).fill(100), highs: Array(n).fill(110), lows: Array(n).fill(90),
    volumes: Array(n).fill(100), opens: Array(n).fill(100), closesUnadjusted: Array(n).fill(null),
  };
}

describe('Daily price and volume research', () => {
  it('compares the close with a hand-calculated prior profile, excluding the current bar and anchor', () => {
    const s = bars(3);
    s.closes = [100, 110, 150]; s.highs = [110, 120, 500]; s.lows = [90, 100, 100]; s.volumes = [100, 300, 1e9];
    const r = computeMarketStructure(s, null, null, 2, 3);
    expect(r.auctionContext).toMatchObject({ position: 'above value', referenceStart: '2020-01-01',
      referenceEnd: '2020-01-02', poc: 105, valueAreaLow: 100, valueAreaHigh: 120 });
    expect(computeMarketStructure(s, '2020-01-03', null, 2, 3).auctionContext).toEqual(r.auctionContext);
    for (const close of [100, 120]) {
      s.closes[2] = close;
      expect(computeMarketStructure(s, null, null, 2, 3).auctionContext.position).toBe('inside value');
    }
    s.lows[2] = 80; s.closes[2] = 99;
    expect(computeMarketStructure(s, null, null, 2, 3).auctionContext.position).toBe('below value');
    s.volumes[0] = null;
    const missing = computeMarketStructure(s, null, null, 2, 3);
    expect(missing.auctionContext.position).toBe('unavailable');
    expect(missing.anchoredVwap.value).not.toBeNull();
    expect(computeMarketStructure(bars(2)).auctionContext.position).toBe('unavailable');
  });
  it('matches hand-calculated VWAP, profile allocation, POC and contiguous value area', () => {
    const s = bars(2);
    s.closes[1] = 110; s.highs[1] = 120; s.lows[1] = 100; s.volumes[1] = 300;
    const r = computeMarketStructure(s, s.dates[0], null, 20, 3);
    expect(r.anchoredVwap.value).toBeCloseTo(107.5, 10);
    expect(r.volumeProfile.bins.map(b => b.volume)).toEqual([50, 200, 150]);
    expect(r.volumeProfile.poc).toBe(105);
    expect(r.volumeProfile.valueAreaLow).toBe(100);
    expect(r.volumeProfile.valueAreaHigh).toBe(120);
    expect(r.volumeProfile.totalVolume).toBe(400);
    expect(r.orderFlow.status).toBe('unavailable');
  });

  it.each([
    [89, 109, 95, 'sell-side', 'spring candidate'],
    [91, 111, 105, 'buy-side', 'upthrust candidate'],
    [89, 111, 100, 'both', 'ambiguous two-sided sweep'],
    [90, 110, 100, 'none', 'range — accumulation/distribution unresolved'],
    [95, 115, 112, 'none', 'markup candidate'],
    [85, 105, 88, 'none', 'markdown candidate'],
    [89, 109, 90, 'none', 'range — accumulation/distribution unresolved'],
  ])('classifies low=%s high=%s close=%s without using the current bar as a reference', (low, high, close, side, context) => {
    const s = bars(); s.lows[20] = Number(low); s.highs[20] = Number(high); s.closes[20] = Number(close);
    const r = computeMarketStructure(s);
    expect(r.sweep.side).toBe(side);
    expect(r.sweep.referenceLow).toBe(90);
    expect(r.sweep.referenceHigh).toBe(110);
    expect(r.wyckoff.context).toBe(context);
  });

  it('cannot see future prices or volumes after an explicit as-of date', () => {
    const s = bars(22);
    const before = computeMarketStructure(s, null, '2020-01-21');
    s.highs[21] = 9999; s.closes[21] = 9000; s.volumes[21] = 1e12;
    expect(computeMarketStructure(s, null, '2020-01-21')).toEqual(before);
  });

  it('refuses incomplete anchored volume without suppressing price-only context', () => {
    const s = bars(); s.volumes[10] = null;
    const r = computeMarketStructure(s);
    expect(r.anchoredVwap.value).toBeNull();
    expect(r.volumeProfile.poc).toBeNull();
    expect(r.sweep.side).toBe('none');
    expect(r.anchoredVwap.reason).toContain('no bars skipped');
    s.highs[20] = 80;
    expect(computeMarketStructure(s).sweep.side).toBeNull();
  });

  it('handles flat prices and anchors exactly without choosing future pivots', () => {
    const s = bars(); s.highs.fill(100); s.lows.fill(100);
    const r = computeMarketStructure(s, '2020-01-21');
    expect(r.anchoredVwap.value).toBe(100);
    expect(r.volumeProfile.bins).toEqual([{ low: 100, high: 100, volume: 100 }]);
    expect(computeMarketStructure(s, '2019-12-31').anchoredVwap.value).toBeNull();
    expect(computeMarketStructure(s, '2020-01-22').anchoredVwap.value).toBeNull();
    expect(computeMarketStructure(s, '2020-01-21', '2020-01-20').anchoredVwap.value).toBeNull();
  });

  it('rejects malformed dates, misaligned arrays and impossible parameters', () => {
    expect(computeMarketStructure(bars(), null, '2020-02-30').error).toBeTruthy();
    expect(computeMarketStructure(bars(), null, null, 0).error).toBeTruthy();
    expect(computeMarketStructure(bars(), null, null, 20, 1).error).toBeTruthy();
    const s = bars(); s.dates[1] = s.dates[0];
    expect(computeMarketStructure(s).error).toBeTruthy();
    const missing = bars(); missing.volumes.pop();
    expect(computeMarketStructure(missing).error).toBeTruthy();
  });

  it('conserves profile volume and resolves equal-volume POCs toward lower prices', () => {
    const r = computeMarketStructure(bars(), null, null, 20, 2);
    expect(r.volumeProfile.bins.map(b => b.volume)).toEqual([1000, 1000]);
    expect(r.volumeProfile.poc).toBe(95);
    expect(r.volumeProfile.bins.reduce((sum, b) => sum + b.volume, 0)).toBe(r.volumeProfile.totalVolume);
  });
});

describe('Price and volume research panel', () => {
  it('exposes missing data requirements without fabricated signals', () => {
    render(<MarketStructurePanel series={null} ticker="TEST" />);
    expect(screen.getByText(/Upload daily High, Low, Close and Volume/)).toBeTruthy();
    expect(screen.getByText('Order flow: unavailable.')).toBeTruthy();
  });

  it('updates the anchor and stops showing an old value when a date is invalid', () => {
    const s = bars(); s.closes[20] = 110; s.highs[20] = 120; s.lows[20] = 100;
    render(<MarketStructurePanel series={s} ticker="TEST" />);
    expect(screen.getByRole('img', { name: 'Estimated volume by price' })).toBeTruthy();
    fireEvent.change(screen.getByLabelText('Anchor date'), { target: { value: '2020-01-21' } });
    expect(screen.getByTestId('anchored-vwap').textContent).toContain('110.00');
    fireEvent.change(screen.getByLabelText('As-of date'), { target: { value: '2020-01-20' } });
    expect(screen.getByTestId('anchored-vwap').textContent).toBe('—');
    expect(within(screen.getByRole('region', { name: 'Price and volume research' }))
      .getAllByText(/Anchor must match/).length).toBeGreaterThan(0);
  });
});

const fundamentals = 'Name,NSE Code,Industry,Market Capitalization,Sales growth 3Years,Profit growth 3Years,ROCE,Return on equity,Debt to equity,Interest Coverage,Cash flow from operations,Promoter holding,Pledged percentage,Price to Earning,Price to book value,Dividend yield\n'
  + 'Alpha,AAA,IT,5000,20,20,25,25,0.1,10,500,60,0,15,2,1\n'
  + 'Beta,BBB,IT,5000,20,20,25,25,0.1,10,500,60,0,15,2,1';
const reviewApp = { ...DEFAULT_APP_CONFIG, universe_mode: 'custom' as const, custom_symbols: [],
  top_n: 1, minimum_total_score: 0, enable_technical_confirmation: false };
function markup() {
  const s = bars(); s.closes[20] = 112; s.highs[20] = 115; s.lows[20] = 95;
  return s;
}

describe('Integrated selection review', () => {
  it('filters by prior value area and renders an evidence heatmap with unavailable tools explicit', () => {
    const result = processScreenerPipeline(parseCsv(fundamentals), reviewApp, DEFAULT_SCREENING_CONFIG, undefined,
      { AAA: markup(), BBB: bars() });
    const { unmount } = render(<SelectionReviewTable evaluations={result.evaluations} />);
    fireEvent.change(screen.getByLabelText('Selection review filter'), { target: { value: 'all' } });
    fireEvent.change(screen.getByLabelText('Auction context filter'), { target: { value: 'above value' } });
    expect(screen.getByText('Alpha')).toBeTruthy();
    expect(screen.queryByText('Beta')).toBeNull();
    fireEvent.change(screen.getByLabelText('Review display'), { target: { value: 'heatmap' } });
    expect(screen.getByRole('table', { name: 'Stock evidence heatmap' })).toBeTruthy();
    expect(screen.getByText('Gamma exposure · unavailable')).toBeTruthy();
    expect(screen.getByText('Market Profile / TPO · unavailable')).toBeTruthy();
    expect(generateSelectionReviewCsv(result.evaluations)).toContain('AuctionPosition,AuctionReferenceStart,AuctionReferenceEnd,PriorEstimatedPOC,PriorEstimatedVAL,PriorEstimatedVAH');
    // A lagging file's directional cells must not read like fresh confirmation.
    result.evaluations[0].selectionReview = { status: 'unavailable', reasons: ['Unaligned'] };
    unmount();
    render(<SelectionReviewTable evaluations={result.evaluations} />);
    fireEvent.change(screen.getByLabelText('Selection review filter'), { target: { value: 'unavailable' } });
    fireEvent.change(screen.getByLabelText('Review display'), { target: { value: 'heatmap' } });
    expect(screen.queryByText('markup candidate')).toBeNull();
    expect(screen.queryByText('above value', { selector: 'td' })).toBeNull();
  });
  it('reviews beyond top-N without changing existing admission or ranking', () => {
    const rows = parseCsv(fundamentals);
    const baseline = processScreenerPipeline(rows, reviewApp, DEFAULT_SCREENING_CONFIG);
    const result = processScreenerPipeline(rows, reviewApp, DEFAULT_SCREENING_CONFIG, undefined, { AAA: markup(), BBB: markup() });
    expect(result.evaluations.map(e => e.selectionReview.status)).toEqual(['candidate', 'candidate']);
    expect(result.passedBelowCutOff[0].stock.ticker).toBe('BBB');
    expect(result.watchlist.map(e => [e.stock.ticker, e.score, e.compositeScore]))
      .toEqual(baseline.watchlist.map(e => [e.stock.ticker, e.score, e.compositeScore]));
    expect(generateSelectionReviewCsv(result.evaluations)).toContain('BBB,Beta,yes');
  });

  it('refuses an unaligned price date and missing volume, while preserving failed screens', () => {
    const histories = { AAA: markup(), BBB: bars(20) };
    let result = processScreenerPipeline(parseCsv(fundamentals), reviewApp, DEFAULT_SCREENING_CONFIG, undefined, histories);
    expect(result.evaluations[1].selectionReview.status).toBe('unavailable');
    expect(result.evaluations[1].selectionReview.reasons[0]).toContain('latest screened session');
    const missing = markup(); missing.volumes[10] = null;
    result = processScreenerPipeline(parseCsv(fundamentals.replace('500,60,0,15', '500,60,99,15')),
      reviewApp, DEFAULT_SCREENING_CONFIG, undefined, { AAA: markup(), BBB: missing });
    expect(result.evaluations[0].selectionReview.status).toBe('excluded');
    expect(result.evaluations[1].selectionReview.status).toBe('unavailable');
  });

  it('does not call contradictory or unconfirmed patterns candidates', () => {
    const s = bars(); s.lows[20] = 89; s.highs[20] = 111; s.closes[20] = 105;
    expect(selectionReview(true, computeMarketStructure(s)).status).toBe('mixed');
    expect(selectionReview(false, computeMarketStructure(markup())).status).toBe('excluded');
    expect(selectionReview(true, null).status).toBe('unavailable');
  });

  it('shows all candidates, including those below top-N, and filters other statuses', () => {
    const result = processScreenerPipeline(parseCsv(fundamentals), reviewApp, DEFAULT_SCREENING_CONFIG, undefined,
      { AAA: markup(), BBB: markup() });
    render(<SelectionReviewTable evaluations={result.evaluations} />);
    expect(screen.getByText('Beta')).toBeTruthy();
    fireEvent.change(screen.getByLabelText('Selection review filter'), { target: { value: 'unavailable' } });
    expect(screen.getByText(/No companies in this view/)).toBeTruthy();
    expect(screen.queryByText('Beta')).toBeNull();
  });
});
