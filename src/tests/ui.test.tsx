/**
 * UI regression tests for the defects that used to leave the app describing
 * data it was not actually showing.
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { useState } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import App from '../App';
import { clampTopN, ConfigPanel } from '../components/ConfigPanel';
import { ErrorBoundary } from '../components/ErrorBoundary';
import { DataInspectionView } from '../components/DataInspectionView';
import { Visualizations } from '../components/Visualizations';
import { WatchlistTable } from '../components/WatchlistTable';
import { AppConfig, CleanedStock, ScreeningConfig, StockEvaluation } from '../types';
import {
  BENCHMARK_SYMBOL,
  computeTechnicalIndicators,
  DEFAULT_APP_CONFIG,
  DEFAULT_SCREENING_CONFIG,
  emptyTechnicals,
  evaluateStock,
  inspectData,
  parseCsv,
} from '../utils/screenerEngine';
import { SAMPLE_SCREENER_CSV_STRING } from '../data/sampleScreenerData';
import { businessDays } from './helpers/dates';
import { sampleUniverseSplit } from './helpers/sample';

function fileFrom(name: string, content: string, type = 'text/csv'): File {
  return new File([content], name, { type, lastModified: Date.now() });
}

const SMALL_CSV = [
  'Name,NSE Code,Market Capitalization,Sales growth 3Years,Profit growth 3Years,ROCE,Return on equity,Debt to equity,Interest Coverage,Cash flow from operations,Promoter holding,Pledged percentage,Price to Earning,Price to book value,Dividend yield',
  'Uploaded Ltd,UPLOADED,5000,20%,20%,25%,25%,0.1,10,500,60%,0%,15,2,1%',
].join('\n');

/**
 * Same row, but on a ticker the pinned Nifty 100 holds, so the default universe
 * actually evaluates it and it reaches the watchlist.
 */
const PASSING_CSV = SMALL_CSV.replace('Uploaded Ltd,UPLOADED', 'Uploaded Ltd,SUNPHARMA');

describe('clampTopN', () => {
  it('accepts whole numbers inside 1-100', () => {
    expect(clampTopN('20')).toBe(20);
    expect(clampTopN('1')).toBe(1);
    expect(clampTopN('100')).toBe(100);
  });

  it('clamps out-of-range values instead of snapping to a default', () => {
    expect(clampTopN('0')).toBe(1);
    expect(clampTopN('-5')).toBe(1);
    expect(clampTopN('500')).toBe(100);
  });

  it('truncates fractions and falls back only for unparseable input', () => {
    expect(clampTopN('12.9')).toBe(12);
    expect(clampTopN('', 33)).toBe(33);
    expect(clampTopN('abc', 33)).toBe(33);
  });
});

describe('Rejected file uploads preserve displayed state', () => {
  beforeEach(() => {
    localStorage.clear();
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('leaves filename, sample status and results untouched when an XLSX is chosen', async () => {
    render(<App />);

    expect(screen.getByText(/File: bundled_sample\.csv/)).toBeTruthy();
    const watchlistTab = screen.getByRole('button', { name: /Watchlist \(top 20\)/ });
    const initialCount = within(watchlistTab).getByText(/^\d+$/).textContent;
    // The bundled sample must actually produce candidates, else this test
    // could pass by comparing "empty" to "empty".
    expect(Number(initialCount)).toBeGreaterThan(0);
    expect(screen.queryByRole('button', { name: /Reset sample/ })).toBeNull();

    const input = document.getElementById('screener-csv-file-input') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [fileFrom('books.xlsx', 'PKbinary')] } });

    await waitFor(() => {
      expect(screen.getByRole('alert').textContent).toMatch(/CSV-only/i);
    });

    // Nothing about the displayed dataset may have changed.
    expect(screen.getByText(/File: bundled_sample\.csv/)).toBeTruthy();
    // The notice names the rejected file, but the File: label must not.
    expect(screen.getByText(/File: bundled_sample\.csv/).textContent).not.toContain('books.xlsx');
    expect(screen.queryByRole('button', { name: /Reset sample/ })).toBeNull();
    expect(within(screen.getByRole('button', { name: /Watchlist \(top 20\)/ })).getByText(/^\d+$/).textContent)
      .toBe(initialCount);
    // The sample is illustrative data and must be labelled as such, never as a
    // dated export.
    expect(screen.getByText(/illustrative sample, figures are made up/)).toBeTruthy();
  });

  it('also rejects other unsupported extensions without touching state', async () => {
    render(<App />);
    const input = document.getElementById('screener-csv-file-input') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [fileFrom('data.json', '{}', 'application/json')] } });
    await waitFor(() => {
      expect(screen.getByRole('alert').textContent).toMatch(/was not loaded/);
    });
    expect(screen.getByText(/File: bundled_sample\.csv/)).toBeTruthy();
  });

  it('commits state only after a CSV is successfully read', async () => {
    render(<App />);
    const input = document.getElementById('screener-csv-file-input') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [fileFrom('my_export.csv', SMALL_CSV)] } });

    await waitFor(() => {
      expect(screen.getByText(/File: my_export\.csv/)).toBeTruthy();
    });
    expect(screen.getByRole('button', { name: /Reset sample/ })).toBeTruthy();
  });

  it('reports an empty CSV as an error and keeps the previous data', async () => {
    render(<App />);
    const input = document.getElementById('screener-csv-file-input') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [fileFrom('empty.csv', '   ')] } });
    await waitFor(() => {
      expect(screen.getByRole('alert').textContent).toMatch(/appears to be empty/);
    });
    expect(screen.getByText(/File: bundled_sample\.csv/)).toBeTruthy();
  });
});

describe('Snapshot persistence', () => {
  beforeEach(() => {
    localStorage.clear();
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  /** The sample is refused as a baseline, so these need a real upload first. */
  const uploadPassingCsv = () => {
    const input = document.getElementById('screener-csv-file-input') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [fileFrom('my_export.csv', PASSING_CSV)] } });
    return waitFor(() => expect(screen.getByText(/File: my_export\.csv/)).toBeTruthy());
  };

  it('reports a storage failure instead of throwing', async () => {
    render(<App />);
    await uploadPassingCsv();
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('quota', 'QuotaExceededError');
    });
    fireEvent.click(screen.getByRole('button', { name: /Save run/ }));
    await waitFor(() => {
      expect(screen.getByRole('alert').textContent).toMatch(/Browser storage is full/);
    });
  });

  it('persists only the minimal snapshot shape, never rawRow', async () => {
    render(<App />);
    await uploadPassingCsv();
    fireEvent.click(screen.getByRole('button', { name: /Save run/ }));
    await waitFor(() => {
      expect(localStorage.getItem('previousWatchlist')).toBeTruthy();
    });
    const stored = JSON.parse(localStorage.getItem('previousWatchlist') as string);
    expect(Array.isArray(stored.entries)).toBe(true);
    expect(stored.entries.length).toBeGreaterThan(0);
    for (const entry of stored.entries) {
      expect(Object.keys(entry).sort()).toEqual(['name', 'rank', 'score', 'ticker', 'warningFlags']);
      expect(JSON.stringify(entry)).not.toContain('rawRow');
    }
  });
});

describe('Rendered detail panels', () => {
  it('shows a non-empty research rationale', () => {
    const stock: CleanedStock = {
      id: 's', name: 'Alpha Ltd', ticker: 'ALPHA', bseCode: null, sector: 'IT',
      currentPrice: 100, marketCap: 10000, salesGrowth: 20, profitGrowth: 20,
      roce: 25, roe: 25, debtToEquity: 0, interestCoverage: 10,
      operatingCashFlow: 100, promoterHolding: 60, promoterPledge: 0,
      peRatio: 15, pbRatio: 2, dividendYield: 1,
      sales: null, returnOnAssets: null, grossNpa: null, netNpa: null,
      capitalAdequacy: null, casa: null, financingMargin: null,
      technicals: emptyTechnicals(), rawRow: {},
    };
    const ev = evaluateStock(stock, DEFAULT_SCREENING_CONFIG, {
      ...DEFAULT_APP_CONFIG, minimum_total_score: 0, enable_technical_confirmation: false,
    });
    const { container } = render(<WatchlistTable watchlist={[{ ...ev, rank: 1 }]} />);
    expect(ev.explanation.length).toBeGreaterThan(40);
    expect(container.textContent).toContain('Total fundamental score');
  });

  it('renders the inspection report with detected identifier columns', () => {
    const report = inspectData(
      parseCsv(SAMPLE_SCREENER_CSV_STRING),
      'sample.csv',
      DEFAULT_APP_CONFIG,
      Date.now(),
    );
    const { container } = render(<DataInspectionView report={report} />);
    expect(report.detectedTickerCol).toBe('NSE code');
    expect(report.detectedBseCodeCol).toBe('BSE code');
    // The bundled sample has percent-suffixed and bare-numeric columns.
    expect(container.textContent?.toLowerCase()).toContain('percentage');
    expect(container.textContent?.toLowerCase()).toContain('numeric');
  });
});

const BASE_STOCK: CleanedStock = {
  id: 'stock-0', name: 'Alpha Ltd', ticker: 'AAA', bseCode: null, sector: 'IT',
  currentPrice: 100, marketCap: 10000, salesGrowth: 20, profitGrowth: 20,
  roce: 25, roe: 25, debtToEquity: 0, interestCoverage: 10,
  operatingCashFlow: 100, promoterHolding: 60, promoterPledge: 0,
  peRatio: 15, pbRatio: 2, dividendYield: 1,
  sales: null, returnOnAssets: null, grossNpa: null, netNpa: null,
  capitalAdequacy: null, casa: null, financingMargin: null,
  technicals: null, rawRow: {},
};
const NO_CUTOFF = { ...DEFAULT_APP_CONFIG, minimum_total_score: 0 };

function ranked(overrides: Partial<CleanedStock>, rank: number): StockEvaluation {
  return { ...evaluateStock({ ...BASE_STOCK, ...overrides }, DEFAULT_SCREENING_CONFIG, NO_CUTOFF), rank };
}

describe('Watchlist detail describes only the data actually loaded', () => {
  it('drops a selection that is no longer listed, even when row ids collide', () => {
    const { rerender } = render(
      <WatchlistTable
        watchlist={[
          ranked({ id: 'stock-0', ticker: 'AAA', name: 'Alpha Ltd' }, 1),
          ranked({ id: 'stock-1', ticker: 'BBB', name: 'Beta Ltd' }, 2),
        ]}
      />,
    );
    fireEvent.click(screen.getAllByText('Beta Ltd')[0]);
    expect(within(screen.getByTestId('watchlist-detail')).getByText('Beta Ltd')).toBeTruthy();

    // A new upload: a different company now sits at Beta's old row id.
    rerender(<WatchlistTable watchlist={[ranked({ id: 'stock-1', ticker: 'CCC', name: 'Gamma Ltd' }, 1)]} />);
    const detail = within(screen.getByTestId('watchlist-detail'));
    expect(detail.getByText('Gamma Ltd')).toBeTruthy();
    expect(detail.queryByText('Beta Ltd')).toBeNull();
    expect(detail.getByText('#1')).toBeTruthy();
  });

  it('keeps following the same company when it is still listed', () => {
    const { rerender } = render(
      <WatchlistTable
        watchlist={[
          ranked({ id: 'stock-0', ticker: 'AAA', name: 'Alpha Ltd' }, 1),
          ranked({ id: 'stock-1', ticker: 'BBB', name: 'Beta Ltd' }, 2),
        ]}
      />,
    );
    fireEvent.click(screen.getAllByText('Beta Ltd')[0]);
    rerender(
      <WatchlistTable
        watchlist={[
          ranked({ id: 'stock-5', ticker: 'BBB', name: 'Beta Ltd' }, 1),
          ranked({ id: 'stock-6', ticker: 'DDD', name: 'Delta Ltd' }, 2),
        ]}
      />,
    );
    const detail = within(screen.getByTestId('watchlist-detail'));
    expect(detail.getByText('Beta Ltd')).toBeTruthy();
    expect(detail.getByText('#1')).toBeTruthy();
  });
});

describe('Technical panel', () => {
  it('says no price history is loaded instead of reporting NO / BEARISH', () => {
    render(<WatchlistTable watchlist={[ranked({}, 1)]} />);
    expect(screen.getByTestId('no-price-history')).toBeTruthy();
    const text = screen.getByTestId('watchlist-detail').textContent ?? '';
    expect(text).not.toMatch(/BEARISH/);
    expect(text).not.toMatch(/\bNO\b/);
    expect(text).toContain('No price history loaded');
  });

  it('shows a dash for each indicator without enough history', () => {
    const tech = computeTechnicalIndicators(Array.from({ length: 60 }, (_, i) => 100 + i));
    render(<WatchlistTable watchlist={[ranked({ technicals: tech }, 1)]} />);
    const cell = (label: string) => within(screen.getByText(label).parentElement as HTMLElement);
    expect(cell('Price vs 50 SMA:').getByText('Above')).toBeTruthy();
    expect(cell('Price vs 200 SMA:').getByText('—')).toBeTruthy();
    expect(cell('50 vs 200 SMA:').getByText('—')).toBeTruthy();
    expect(cell('From 52W high:').getByText('—')).toBeTruthy();
  });

  it('says how many sessions a too-short history has rather than claiming none', () => {
    const tech = computeTechnicalIndicators(Array.from({ length: 30 }, (_, i) => 100 + i));
    render(<WatchlistTable watchlist={[ranked({ technicals: tech }, 1)]} />);
    expect(screen.getByTestId('short-price-history').textContent).toMatch(/only 30 sessions/);
  });
});

function ConfigHarness() {
  const [app, setApp] = useState<AppConfig>({ ...DEFAULT_APP_CONFIG, universe_mode: 'custom' });
  const [screening, setScreening] = useState<ScreeningConfig>(DEFAULT_SCREENING_CONFIG);
  return (
    <>
      <ConfigPanel
        appConfig={app}
        onAppConfigChange={setApp}
        screeningConfig={screening}
        onScreeningConfigChange={setScreening}
      />
      <pre data-testid="config-state">{JSON.stringify({ app, screening })}</pre>
    </>
  );
}

const configState = () =>
  JSON.parse(screen.getByTestId('config-state').textContent as string) as { app: AppConfig; screening: ScreeningConfig };

describe('Config panel inputs', () => {
  it('lets you type a comma-separated symbol list one key at a time', () => {
    render(<ConfigHarness />);
    const input = screen.getByLabelText(/separated by commas or spaces/) as HTMLInputElement;
    for (const value of ['T', 'TC', 'TCS', 'TCS,', 'TCS, ', 'TCS, I', 'TCS, INFY']) {
      fireEvent.change(input, { target: { value } });
      expect(input.value).toBe(value);
    }
    expect(configState().app.custom_symbols).toEqual(['TCS', 'INFY']);
  });

  it('says when a typed value is outside the allowed range', () => {
    render(<ConfigHarness />);
    const input = screen.getByLabelText('Min market cap') as HTMLInputElement;
    fireEvent.change(input, { target: { value: '150000' } });
    expect(input.value).toBe('150000');
    expect(configState().screening.minMarketCapCr).toBe(100000);
    expect(screen.getByTestId('cfg-minMarketCapCr-clamped').textContent)
      .toMatch(/Allowed range is 0 to 100000; using 100000/);
    fireEvent.change(input, { target: { value: '5000' } });
    expect(screen.queryByTestId('cfg-minMarketCapCr-clamped')).toBeNull();
  });

  it('lets a number box be cleared and take a negative value', () => {
    render(<ConfigHarness />);
    const input = screen.getByLabelText('Min sales growth (3Y)') as HTMLInputElement;
    fireEvent.change(input, { target: { value: '' } });
    expect(input.value).toBe('');
    expect(configState().screening.minSalesGrowthPct).toBe(10);
    fireEvent.change(input, { target: { value: '-5' } });
    expect(configState().screening.minSalesGrowthPct).toBe(-5);
    fireEvent.change(input, { target: { value: '-500' } });
    expect(configState().screening.minSalesGrowthPct).toBe(-100);
    fireEvent.blur(input);
    expect(input.value).toBe('-100');
  });

  it('applies a valid config file and rejects an invalid one as a whole', async () => {
    render(<ConfigHarness />);
    const fileInput = screen.getByTestId('config-import-input');
    fireEvent.change(fileInput, {
      target: { files: [new File([JSON.stringify({ app: { top_n: 7 } })], 'good.json')] },
    });
    await waitFor(() => expect(configState().app.top_n).toBe(7));
    // Like the Python engine, a file describes a whole configuration: settings
    // it omits are at their defaults, so universe_mode is back to nifty100.
    const afterGood = configState();
    expect(afterGood.app.universe_mode).toBe('nifty100');
    expect(screen.getByRole('status').textContent).toMatch(/good\.json/);

    fireEvent.change(fileInput, {
      target: { files: [new File([JSON.stringify({ app: { top_n: 0, universe_mode: 'custom' } })], 'bad.json')] },
    });
    await waitFor(() => {
      expect(screen.getByRole('alert').textContent).toMatch(/not applied: app\.top_n must be between 1 and 100/);
    });
    expect(configState()).toEqual(afterGood);
  });
});

describe('Error boundary', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  function Boom(): never {
    throw new Error('kaboom');
  }

  it('shows what failed instead of a blank page', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    render(
      <ErrorBoundary>
        <Boom />
      </ErrorBoundary>,
    );
    expect(screen.getByTestId('error-boundary').textContent).toMatch(/kaboom/);
  });

  it('offers to clear the saved run', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    const onReset = vi.fn();
    render(
      <ErrorBoundary onReset={onReset}>
        <Boom />
      </ErrorBoundary>,
    );
    fireEvent.click(screen.getByRole('button', { name: /Clear the saved run/ }));
    expect(onReset).toHaveBeenCalled();
  });
});

describe('A saved run with the wrong shape', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('is discarded instead of blanking the app', () => {
    localStorage.setItem('previousWatchlist', JSON.stringify({}));
    render(<App />);
    expect(screen.getByRole('button', { name: /Watchlist \(top 20\)/ })).toBeTruthy();
    expect(screen.queryByTestId('error-boundary')).toBeNull();
  });

  it('ignores entries that are not usable and treats the run as the first', () => {
    localStorage.setItem('previousWatchlist', JSON.stringify([{ ticker: 'TCS' }, 42]));
    render(<App />);
    fireEvent.click(screen.getByRole('button', { name: /Run deltas/ }));
    expect(screen.getByText(/No comparison snapshot yet/)).toBeTruthy();
  });
});

describe('Saving a run', () => {
  beforeEach(() => {
    localStorage.clear();
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  const uploadPassingCsv = () => {
    const input = document.getElementById('screener-csv-file-input') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [fileFrom('my_export.csv', PASSING_CSV)] } });
    return waitFor(() => expect(screen.getByText(/File: my_export\.csv/)).toBeTruthy());
  };

  it('refuses to save the illustrative sample', async () => {
    render(<App />);
    fireEvent.click(screen.getByRole('button', { name: /Save run/ }));
    await waitFor(() => {
      expect(screen.getByRole('alert').textContent).toMatch(/illustrative data, so it cannot be saved/);
    });
    expect(localStorage.getItem('previousWatchlist')).toBeNull();
  });

  it('refuses to save an empty watchlist', async () => {
    render(<App />);
    const input = document.getElementById('screener-csv-file-input') as HTMLInputElement;
    // The row is evaluated (its ticker is in the index) but fails the screen,
    // so there is no watchlist to save.
    const failing = PASSING_CSV.replace('25%,25%', '1%,1%');
    fireEvent.change(input, { target: { files: [fileFrom('poor.csv', failing)] } });
    await waitFor(() => expect(screen.getByText(/File: poor\.csv/)).toBeTruthy());
    fireEvent.click(screen.getByRole('button', { name: /Save run/ }));
    await waitFor(() => {
      expect(screen.getByRole('alert').textContent).toMatch(/no watchlist to save/);
    });
    expect(localStorage.getItem('previousWatchlist')).toBeNull();
  });

  it('records the date, file name and settings, and shows them in Run deltas', async () => {
    render(<App />);
    await uploadPassingCsv();
    fireEvent.click(screen.getByRole('button', { name: /Save run/ }));
    await waitFor(() => expect(localStorage.getItem('previousWatchlist')).toBeTruthy());
    const saved = JSON.parse(localStorage.getItem('previousWatchlist') as string);
    expect(saved.fileName).toBe('my_export.csv');
    expect(saved.savedAt).toMatch(/^\d{4}-\d{2}-\d{2}T/);
    expect(saved.appConfig.top_n).toBe(DEFAULT_APP_CONFIG.top_n);
    expect(saved.screeningConfig.minRocePct).toBe(DEFAULT_SCREENING_CONFIG.minRocePct);
    expect(saved.entries.length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole('button', { name: /Run deltas/ }));
    const details = screen.getByTestId('saved-run-details').textContent ?? '';
    expect(details).toMatch(/my_export\.csv/);
    expect(details).toMatch(/top 20/);
  });

  it('asks before replacing an existing baseline and keeps it on cancel', async () => {
    render(<App />);
    await uploadPassingCsv();
    fireEvent.click(screen.getByRole('button', { name: /Save run/ }));
    await waitFor(() => expect(localStorage.getItem('previousWatchlist')).toBeTruthy());
    const first = localStorage.getItem('previousWatchlist');

    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false);
    fireEvent.click(screen.getByRole('button', { name: /Save run/ }));
    expect(confirmSpy).toHaveBeenCalledWith(expect.stringMatching(/Replace the saved run/));
    expect(localStorage.getItem('previousWatchlist')).toBe(first);

    confirmSpy.mockReturnValue(true);
    fireEvent.click(screen.getByRole('button', { name: /Save run/ }));
    await waitFor(() => {
      expect(screen.getByRole('status').textContent).toMatch(/Saved .* as the comparison baseline/);
    });
  });
});

describe('Uploading a price file whose tickers do not match', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('reports that nothing matched and names the .NS / .BO suffix', async () => {
    render(<App />);
    const days = businessDays(60);
    const csv = ['Date,Ticker,Close', ...days.map((d, i) => `${d},SUNPHARMA.NS,${100 + i}`)].join('\n');
    const input = document.getElementById('price-history-file-input') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [fileFrom('yahoo.csv', csv)] } });
    await waitFor(() => {
      expect(screen.getByRole('alert').textContent).toMatch(/none of them match the .* screened tickers/);
    });
    expect(screen.getByRole('alert').textContent).toMatch(/\.NS or \.BO suffix removed/);
    expect(screen.getByText(/none loaded/)).toBeTruthy();
  });

  it('reports how many of the screened tickers matched when some do', async () => {
    render(<App />);
    const days = businessDays(60);
    const csv = ['Date,Ticker,Close', ...days.map((d, i) => `${d},SUNPHARMA,${100 + i}`)].join('\n');
    const input = document.getElementById('price-history-file-input') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [fileFrom('prices.csv', csv)] } });
    await waitFor(() => {
      expect(screen.getByRole('status').textContent).toMatch(/1 of the \d+ screened tickers matched/);
    });
  });
});

describe('Counts and labels agree between tabs', () => {
  it('shows the engine duplicate count in the Data schema tab', () => {
    const duplicated = [SMALL_CSV, SMALL_CSV.split('\n')[1].replace('Uploaded Ltd', 'Same Ticker Ltd')].join('\n');
    render(<App />);
    const input = document.getElementById('screener-csv-file-input') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [fileFrom('dupes.csv', duplicated)] } });
    return waitFor(() => {
      expect(screen.getByText(/1 duplicates removed/)).toBeTruthy();
      fireEvent.click(screen.getByRole('button', { name: /Data schema/ }));
      expect(screen.getByTestId('duplicate-companies').textContent).toBe('1');
    });
  });

  it('prefers the latest close over the export price, and says which date it is', () => {
    const days = businessDays(60);
    const tech = computeTechnicalIndicators(
      days.map((_, i) => 200 + i),
      null,
      null,
      'price history',
      days,
    );
    render(<WatchlistTable watchlist={[ranked({ currentPrice: 100, technicals: tech }, 1)]} />);
    expect(screen.getByText(`₹${(200 + 59).toLocaleString('en-IN')}`)).toBeTruthy();
    expect(screen.getAllByText(days[days.length - 1]).length).toBeGreaterThan(0);
  });

  it('falls back to the export price, labelled, with no price history', () => {
    render(<WatchlistTable watchlist={[ranked({ currentPrice: 100 }, 1)]} />);
    expect(screen.getByText('₹100')).toBeTruthy();
    expect(screen.getByText('export')).toBeTruthy();
  });
});

describe('Charts with nothing to chart', () => {
  it('explains why instead of rendering nothing', () => {
    const { container } = render(<Visualizations allEvaluations={[]} />);
    expect(container.textContent).toMatch(/No companies were evaluated/);
  });

  it('says the 70+ tile counts rejected companies too', () => {
    const { container } = render(<Visualizations allEvaluations={[ranked({}, 1)]} />);
    expect(container.textContent).toMatch(/including rejected/);
  });
});

describe('Keyboard access to the file inputs', () => {
  it('keeps every file input in the tab order', () => {
    render(<App />);
    for (const id of ['screener-csv-file-input', 'price-history-file-input']) {
      const input = document.getElementById(id) as HTMLInputElement;
      expect(input.className, id).not.toMatch(/\bhidden\b/);
      input.focus();
      expect(document.activeElement, id).toBe(input);
    }
  });

  it('keeps the config import input in the tab order', () => {
    render(<ConfigHarness />);
    const input = screen.getByTestId('config-import-input') as HTMLInputElement;
    expect(input.className).not.toMatch(/\bhidden\b/);
    input.focus();
    expect(document.activeElement).toBe(input);
  });
});

describe('App universe and price history', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('says how many sample rows are outside the Nifty 100 and can screen them all', () => {
    render(<App />);
    const { total, inIndex, outside } = sampleUniverseSplit();
    expect(screen.getByText(new RegExp(`${inIndex} evaluated, ${outside} outside the Nifty 100`))).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: /Screen all rows/ }));
    expect(screen.getByText(new RegExp(`${total} evaluated`))).toBeTruthy();
    expect(screen.queryByRole('button', { name: /Screen all rows/ })).toBeNull();
  });

  it('uses an uploaded price history for technical scores', async () => {
    render(<App />);
    const days = businessDays(300);
    const csv = [
      'Date,Ticker,Close,Volume',
      ...days.map((d, i) => `${d},SUNPHARMA,${100 + i * 0.5},1000`),
      ...days.map((d, i) => `${d},${BENCHMARK_SYMBOL},${50 + i * 0.1},`),
    ].join('\n');
    const input = document.getElementById('price-history-file-input') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [fileFrom('prices.csv', csv)] } });
    await waitFor(() => expect(screen.getByText(/1 ticker, as of/)).toBeTruthy());
    // Every company is ranked now, so the top of the list is not the one this
    // file prices. Select the stock the upload actually covers before reading
    // its technical score.
    fireEvent.click(screen.getAllByText('Sun Pharmaceutical Industries Ltd.')[0]);
    expect(within(screen.getByTestId('watchlist-detail')).getByText('100')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: /Clear price history/ }));
    expect(screen.getByTestId('no-price-history')).toBeTruthy();
  });

  it('rejects a price file without the required columns', async () => {
    render(<App />);
    const input = document.getElementById('price-history-file-input') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [fileFrom('prices.csv', 'Date,Close\n2025-01-01,1\n')] } });
    await waitFor(() => {
      expect(screen.getByRole('alert').textContent).toMatch(/needs Date, Ticker and Close/);
    });
    expect(screen.getByText(/none loaded/)).toBeTruthy();
  });
});
