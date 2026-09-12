import { Download, Globe, Plus, RotateCcw, Shield, Sliders, Tag, Trash2, Upload } from 'lucide-react';
import React, { useState } from 'react';

import { NIFTY100_PROVENANCE } from '../data/nifty100Snapshot';
import { AppConfig, CustomFilter, FilterOperator, ScreeningConfig } from '../types';
import { downloadText } from '../utils/download';
import {
  ALLOWED_FILTER_FIELDS,
  ALLOWED_FILTER_OPERATORS,
  buildConfigDocument,
  CONFIG_FILENAME,
  CONFIG_LIMITS,
  DEFAULT_APP_CONFIG,
  DEFAULT_SCREENING_CONFIG,
  normaliseSymbols,
  validateConfigDocument,
  validateCustomFilters,
} from '../utils/screenerEngine';

interface ConfigPanelProps {
  appConfig: AppConfig;
  onAppConfigChange: (next: AppConfig) => void;
  screeningConfig: ScreeningConfig;
  onScreeningConfigChange: (next: ScreeningConfig) => void;
}

/** Presentation for each numeric threshold. Bounds come from CONFIG_LIMITS. */
interface NumericSpec {
  key: keyof ScreeningConfig;
  label: string;
  step: number;
  suffix?: string;
  help: string;
}

const SCREENING_SPECS: NumericSpec[] = [
  { key: 'minMarketCapCr', label: 'Min market cap', step: 100, suffix: '₹ Cr', help: 'Floor on size, in rupee crore.' },
  { key: 'minSalesGrowthPct', label: 'Min sales growth (3Y)', step: 0.5, suffix: '%', help: 'Three-year revenue CAGR floor.' },
  { key: 'minProfitGrowthPct', label: 'Min profit growth (3Y)', step: 0.5, suffix: '%', help: 'Three-year PAT CAGR floor.' },
  { key: 'minRocePct', label: 'Min ROCE', step: 0.5, suffix: '%', help: 'Return on capital employed floor.' },
  { key: 'minRoePct', label: 'Min ROE', step: 0.5, suffix: '%', help: 'Return on equity floor.' },
  { key: 'maxDebtToEquity', label: 'Max debt / equity', step: 0.05, suffix: 'x', help: 'Leverage ceiling. Skipped for financials, which are out of scope.' },
  { key: 'minInterestCoverage', label: 'Min interest coverage', step: 0.5, suffix: 'x', help: 'EBIT / interest floor.' },
  { key: 'minPromoterHoldingPct', label: 'Min promoter holding', step: 0.5, suffix: '%', help: 'Promoter skin-in-the-game floor.' },
  { key: 'maxPromoterPledgePct', label: 'Max promoter pledge', step: 0.5, suffix: '%', help: 'Pledged-shares ceiling.' },
  { key: 'minPeRatio', label: 'Min P/E', step: 0.5, help: 'Guards against negative or nonsense earnings multiples.' },
  { key: 'maxPeRatio', label: 'Max P/E', step: 1, help: 'Valuation ceiling on earnings.' },
  { key: 'maxPbRatio', label: 'Max P/B', step: 0.5, help: 'Valuation ceiling on book value.' },
  { key: 'minDividendYieldPct', label: 'Min dividend yield', step: 0.1, suffix: '%', help: 'Below this a "Low Dividend Yield" warning is flagged (not a rejection).' },
  { key: 'minimum_fundamental_coverage', label: 'Min fundamental coverage', step: 1, suffix: '%', help: 'Share of expected fields that must be present, else the row is rejected.' },
];

/**
 * A typed value clamped into [min, max], or null while the text is not a
 * number yet (empty, or a lone "-" on the way to a negative value).
 */
export function parseBounded(
  raw: string,
  limits: { min: number; max: number },
  wholeNumber = false,
): number | null {
  const text = raw.trim();
  if (text === '') return null;
  const parsed = Number(text);
  if (!Number.isFinite(parsed)) return null;
  const value = wholeNumber ? Math.trunc(parsed) : parsed;
  return Math.min(limits.max, Math.max(limits.min, value));
}

/** top_n must be a whole number in [1, 100]. */
export function clampTopN(raw: string | number, fallback = DEFAULT_APP_CONFIG.top_n): number {
  return parseBounded(String(raw), CONFIG_LIMITS.top_n, true) ?? fallback;
}

interface NumberFieldProps {
  id?: string;
  ariaLabel?: string;
  value: number;
  limits: { min: number; max: number };
  step: number;
  wholeNumber?: boolean;
  onCommit: (value: number) => void;
}

/**
 * Number box whose text is yours while you edit: you can clear it or type "-"
 * on the way to a value. The setting changes whenever the text parses (clamped
 * to its range) and the box shows the committed value again when you leave it.
 */
function NumberField({ id, ariaLabel, value, limits, step, wholeNumber = false, onCommit }: NumberFieldProps) {
  const [draft, setDraft] = useState<string | null>(null);
  // What the box shows and what the setting holds can differ while typing, so
  // say so rather than silently applying a different number.
  const typed = draft === null || draft.trim() === '' ? null : Number(draft.trim());
  const adjusted =
    typed !== null && Number.isFinite(typed) && (typed < limits.min || typed > limits.max || (wholeNumber && !Number.isInteger(typed)));
  return (
    <>
      <input
        id={id}
        aria-label={ariaLabel}
        type="number"
        min={limits.min}
        max={limits.max}
        step={step}
        value={draft ?? String(value)}
        onChange={(e) => {
          setDraft(e.target.value);
          const parsed = parseBounded(e.target.value, limits, wholeNumber);
          if (parsed !== null) onCommit(parsed);
        }}
        onBlur={() => setDraft(null)}
        className="w-full px-2 py-1.5 border border-slate-200 rounded-lg text-xs font-mono"
      />
      {adjusted && (
        <p role="status" className="text-[11px] text-amber-700" data-testid={id ? `${id}-clamped` : undefined}>
          Allowed range is {limits.min} to {limits.max}
          {wholeNumber ? ', whole numbers only' : ''}; using <strong>{value}</strong>.
        </p>
      )}
    </>
  );
}

export const ConfigPanel: React.FC<ConfigPanelProps> = ({
  appConfig,
  onAppConfigChange,
  screeningConfig,
  onScreeningConfigChange,
}) => {
  const [draftFilter, setDraftFilter] = useState<{ field: string; operator: FilterOperator; value: string }>({
    field: ALLOWED_FILTER_FIELDS[0],
    operator: '>',
    value: '',
  });
  const [filterError, setFilterError] = useState<string | null>(null);
  const [symbolsDraft, setSymbolsDraft] = useState<string | null>(null);
  const [fileNotice, setFileNotice] = useState<{ kind: 'error' | 'info'; message: string } | null>(null);

  const setApp = <K extends keyof AppConfig>(key: K, value: AppConfig[K]) =>
    onAppConfigChange({ ...appConfig, [key]: value });

  const setScreening = (key: keyof ScreeningConfig, value: number | boolean) =>
    onScreeningConfigChange({ ...screeningConfig, [key]: value } as ScreeningConfig);

  const addFilter = () => {
    const candidate: CustomFilter = {
      field: draftFilter.field,
      operator: draftFilter.operator,
      value: draftFilter.value,
    };
    const errors = validateCustomFilters([candidate]);
    if (errors.length) {
      setFilterError(errors[0]);
      return;
    }
    setFilterError(null);
    setApp('custom_filters', [...appConfig.custom_filters, candidate]);
    setDraftFilter({ ...draftFilter, value: '' });
  };

  const removeFilter = (index: number) =>
    setApp('custom_filters', appConfig.custom_filters.filter((_, i) => i !== index));

  const exportConfig = () =>
    downloadText(
      `${JSON.stringify(buildConfigDocument(appConfig, screeningConfig), null, 2)}\n`,
      CONFIG_FILENAME,
      'application/json',
    );

  const importConfig = (event: React.ChangeEvent<HTMLInputElement>) => {
    const input = event.target;
    const file = input.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onerror = () => {
      input.value = '';
      setFileNotice({ kind: 'error', message: `Could not read "${file.name}".` });
    };
    reader.onload = () => {
      input.value = '';
      const raw = String(reader.result ?? '');
      const text = raw.charCodeAt(0) === 0xfeff ? raw.slice(1) : raw;
      let parsed: unknown;
      try {
        parsed = JSON.parse(text);
      } catch (error) {
        setFileNotice({
          kind: 'error',
          message: `"${file.name}" is not valid JSON (${error instanceof Error ? error.message : String(error)}).`,
        });
        return;
      }
      const { app, screening, errors } = validateConfigDocument(parsed);
      if (errors.length) {
        // All-or-nothing: a file that asks for something invalid changes nothing.
        setFileNotice({ kind: 'error', message: `"${file.name}" was not applied: ${errors.join('; ')}.` });
        return;
      }
      onAppConfigChange(app);
      onScreeningConfigChange(screening);
      setFilterError(null);
      setFileNotice({
        kind: 'info',
        message:
          `Applied "${file.name}". Settings it does not mention are at their defaults, ` +
          'exactly as the Python engine reads the same file.',
      });
    };
    reader.readAsText(file);
  };

  return (
    <div className="space-y-6" id="config-panel-container">
      <div className="p-4 bg-blue-50/70 border border-blue-100 rounded-xl flex flex-col md:flex-row md:items-start justify-between gap-4">
        <div>
          <h3 className="text-sm font-semibold text-blue-900 flex items-center gap-1.5">
            <Sliders className="w-4 h-4 text-blue-600" />
            Screening parameters
          </h3>
          <p className="text-xs text-blue-700 mt-1 max-w-2xl leading-relaxed">
            Every threshold is editable here and clamped to its documented range. Custom filters use
            a fixed list of fields and operators; nothing you type is ever executed as code.{' '}
            <strong>Export</strong> saves these settings as <code>{CONFIG_FILENAME}</code>: put it in{' '}
            <code>data-store/config/</code> (or pass <code>--config</code>) and the Python engine
            screens with exactly the same settings.
          </p>
        </div>
        <div className="flex flex-wrap gap-2 flex-shrink-0">
          <button
            onClick={exportConfig}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-white text-xs font-semibold text-slate-700 border border-slate-200 rounded-lg hover:bg-slate-50"
          >
            <Download className="w-3.5 h-3.5 text-blue-600" />
            Export {CONFIG_FILENAME}
          </button>
          <label
            htmlFor="config-import-input"
            className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-white text-xs font-semibold text-slate-700 border border-slate-200 rounded-lg hover:bg-slate-50 cursor-pointer focus-within:ring-2 focus-within:ring-blue-500"
          >
            <Upload className="w-3.5 h-3.5 text-blue-600" />
            Import
            {/* sr-only, not hidden: a display:none input cannot be tabbed to. */}
            <input
              type="file"
              id="config-import-input"
              accept=".json,application/json"
              onChange={importConfig}
              className="sr-only"
              data-testid="config-import-input"
            />
          </label>
          <button
            onClick={() => {
              onAppConfigChange(DEFAULT_APP_CONFIG);
              onScreeningConfigChange(DEFAULT_SCREENING_CONFIG);
              setFilterError(null);
              setFileNotice(null);
            }}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-white text-xs font-semibold text-slate-700 border border-slate-200 rounded-lg hover:bg-slate-50"
          >
            <RotateCcw className="w-3.5 h-3.5 text-slate-500" />
            Reset defaults
          </button>
        </div>
      </div>

      {fileNotice && (
        <p
          role={fileNotice.kind === 'error' ? 'alert' : 'status'}
          className={`text-xs rounded-lg px-3 py-2 border ${
            fileNotice.kind === 'error'
              ? 'text-rose-700 bg-rose-50 border-rose-200'
              : 'text-emerald-800 bg-emerald-50 border-emerald-200'
          }`}
        >
          {fileNotice.message}
        </p>
      )}

      {/* Universe */}
      <div className="bg-white border border-slate-200 rounded-xl p-5 space-y-4">
        <h4 className="text-xs font-semibold uppercase tracking-wider flex items-center gap-1.5">
          <Globe className="w-4 h-4 text-blue-600" />
          1. Universe
        </h4>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <label
            className={`p-4 rounded-xl border-2 cursor-pointer transition-all ${
              appConfig.universe_mode === 'nifty100' ? 'border-blue-600 bg-blue-50/40' : 'border-slate-200 hover:border-slate-300'
            }`}
          >
            <div className="flex items-center justify-between mb-2">
              <span className="font-bold text-sm">Nifty 100</span>
              <input
                type="radio"
                name="universe_mode"
                checked={appConfig.universe_mode === 'nifty100'}
                onChange={() => setApp('universe_mode', 'nifty100')}
              />
            </div>
            <p className="text-xs text-slate-500">
              Restricts screening to the pinned Nifty 100 snapshot — <strong>cached, as of{' '}
              {NIFTY100_PROVENANCE.as_of_date}</strong>. Not a live feed; the index is rebalanced
              periodically. The notebook refreshes it from NSE when the network is available.
            </p>
            <span className="text-[11px] font-mono text-blue-700 mt-2 block">
              {NIFTY100_PROVENANCE.count} symbols · sha256 {NIFTY100_PROVENANCE.sha256_of_source_csv.slice(0, 12)}…
            </span>
          </label>

          <label
            className={`p-4 rounded-xl border-2 cursor-pointer transition-all ${
              appConfig.universe_mode === 'custom' ? 'border-blue-600 bg-blue-50/40' : 'border-slate-200 hover:border-slate-300'
            }`}
          >
            <div className="flex items-center justify-between mb-2">
              <span className="font-bold text-sm">Custom universe</span>
              <input
                type="radio"
                name="universe_mode"
                checked={appConfig.universe_mode === 'custom'}
                onChange={() => setApp('universe_mode', 'custom')}
              />
            </div>
            <p className="text-xs text-slate-500">
              Screen a specific list of NSE symbols, or leave the list empty to screen every row in
              the uploaded export.
            </p>
          </label>
        </div>

        {appConfig.universe_mode === 'custom' && (
          <div className="p-3 bg-slate-50 rounded-xl border border-slate-200 space-y-2">
            <label className="text-xs font-semibold flex items-center gap-1" htmlFor="custom-symbols">
              <Tag className="w-3.5 h-3.5 text-blue-600" />
              NSE symbols (separated by commas or spaces)
            </label>
            <input
              id="custom-symbols"
              type="text"
              value={symbolsDraft ?? appConfig.custom_symbols.join(', ')}
              onChange={(e) => {
                // Keep exactly what was typed so a trailing comma or space
                // survives until the next symbol is entered.
                setSymbolsDraft(e.target.value);
                setApp('custom_symbols', normaliseSymbols(e.target.value.split(/[\s,]+/)));
              }}
              onBlur={() => setSymbolsDraft(null)}
              placeholder="Leave empty to screen every row, or e.g. TCS, INFY, TITAN"
              className="w-full px-3 py-2 bg-white border border-slate-200 rounded-lg text-xs font-mono"
            />
            <p className="text-[11px] text-slate-500">
              Active: {appConfig.custom_symbols.length > 0 ? appConfig.custom_symbols.join(', ') : 'all rows in export'}
            </p>
          </div>
        )}

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 pt-2">
          <div>
            <label className="text-xs text-slate-600 block mb-1" htmlFor="cfg-top-n">
              Watchlist size (top N) <span className="text-slate-400">1–100</span>
            </label>
            <NumberField
              id="cfg-top-n"
              value={appConfig.top_n}
              limits={CONFIG_LIMITS.top_n}
              step={1}
              wholeNumber
              onCommit={(v) => setApp('top_n', v)}
            />
          </div>
          <div>
            <label className="text-xs text-slate-600 block mb-1" htmlFor="cfg-min-score">
              Min total score <span className="text-slate-400">0–100</span>
            </label>
            <NumberField
              id="cfg-min-score"
              value={appConfig.minimum_total_score}
              limits={CONFIG_LIMITS.minimum_total_score}
              step={1}
              onCommit={(v) => setApp('minimum_total_score', v)}
            />
          </div>
          <div>
            <label className="text-xs text-slate-600 block mb-1" htmlFor="cfg-stale">
              Stale after (days) <span className="text-slate-400">1–365</span>
            </label>
            <NumberField
              id="cfg-stale"
              value={appConfig.fundamentals_stale_after_days}
              limits={CONFIG_LIMITS.fundamentals_stale_after_days}
              step={1}
              onCommit={(v) => setApp('fundamentals_stale_after_days', v)}
            />
          </div>
        </div>

        <div className="flex flex-col gap-2 pt-2 text-xs">
          <label className="inline-flex items-start gap-2 cursor-pointer">
            <input
              type="checkbox"
              className="mt-0.5"
              checked={appConfig.enable_technical_confirmation}
              onChange={(e) => setApp('enable_technical_confirmation', e.target.checked)}
            />
            <span>
              <span className="font-medium">Technical confirmation scoring (separate 0–100)</span>
              <span className="block text-[11px] text-slate-500">
                Needs daily price history: use <strong>Upload prices</strong> in the header. The
                Python engine downloads it itself and saves the same file under{' '}
                <code>data-store/market_data/</code>.
              </span>
            </span>
          </label>
          <label className="inline-flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={screeningConfig.requirePositiveOcf}
              onChange={(e) => setScreening('requirePositiveOcf', e.target.checked)}
            />
            <span className="font-medium">Require positive operating cash flow</span>
          </label>
        </div>
      </div>

      {/* Thresholds */}
      <div className="bg-white border border-slate-200 rounded-xl p-5 space-y-4">
        <h4 className="text-xs font-semibold uppercase tracking-wider flex items-center gap-1.5">
          <Shield className="w-4 h-4 text-blue-600" />
          2. Fundamental thresholds
        </h4>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {SCREENING_SPECS.map((spec) => {
            const value = screeningConfig[spec.key] as number;
            const limits = CONFIG_LIMITS[spec.key];
            const inputId = `cfg-${String(spec.key)}`;
            return (
              <div key={String(spec.key)} className="p-3 border border-slate-200 rounded-xl space-y-2">
                <label className="text-[11px] font-semibold uppercase tracking-wider block" htmlFor={inputId}>
                  {spec.label}
                </label>
                <div className="flex items-center gap-2">
                  <NumberField
                    id={inputId}
                    value={value}
                    limits={limits}
                    step={spec.step}
                    onCommit={(v) => setScreening(spec.key, v)}
                  />
                  {spec.suffix && <span className="text-[11px] text-slate-500 font-mono">{spec.suffix}</span>}
                </div>
                <input
                  type="range"
                  aria-label={`${spec.label} slider`}
                  min={limits.min}
                  max={limits.max}
                  step={spec.step}
                  value={value}
                  onChange={(e) => {
                    const parsed = parseBounded(e.target.value, limits);
                    if (parsed !== null) setScreening(spec.key, parsed);
                  }}
                  className="w-full accent-blue-600"
                />
                <p className="text-[11px] text-slate-500 leading-snug">{spec.help}</p>
                <p className="text-[10px] text-slate-400 font-mono">
                  range {limits.min} – {limits.max}
                </p>
              </div>
            );
          })}
        </div>
      </div>

      {/* Custom filters */}
      <div className="bg-white border border-slate-200 rounded-xl p-5 space-y-4">
        <h4 className="text-xs font-semibold uppercase tracking-wider flex items-center gap-1.5">
          <Plus className="w-4 h-4 text-blue-600" />
          3. Custom filters
        </h4>
        <p className="text-xs text-slate-500 max-w-2xl leading-relaxed">
          Additional numeric hurdles. The field and operator come from fixed dropdowns and the value
          must be a plain decimal number, so a filter can only ever be a numeric comparison — free
          text is never evaluated as an expression.
        </p>

        <div className="flex flex-wrap items-end gap-2">
          <div>
            <label className="text-[11px] text-slate-600 block mb-1" htmlFor="filter-field">Field</label>
            <select
              id="filter-field"
              value={draftFilter.field}
              onChange={(e) => setDraftFilter({ ...draftFilter, field: e.target.value })}
              className="px-2 py-1.5 border border-slate-200 rounded-lg text-xs font-mono bg-white"
            >
              {ALLOWED_FILTER_FIELDS.map((field) => (
                <option key={field} value={field}>{field}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-[11px] text-slate-600 block mb-1" htmlFor="filter-op">Operator</label>
            <select
              id="filter-op"
              value={draftFilter.operator}
              onChange={(e) => setDraftFilter({ ...draftFilter, operator: e.target.value as FilterOperator })}
              className="px-2 py-1.5 border border-slate-200 rounded-lg text-xs font-mono bg-white"
            >
              {ALLOWED_FILTER_OPERATORS.map((op) => (
                <option key={op} value={op}>{op}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-[11px] text-slate-600 block mb-1" htmlFor="filter-value">Value</label>
            <input
              id="filter-value"
              type="text"
              inputMode="decimal"
              value={draftFilter.value}
              onChange={(e) => setDraftFilter({ ...draftFilter, value: e.target.value })}
              placeholder="e.g. 25"
              className="px-2 py-1.5 border border-slate-200 rounded-lg text-xs font-mono w-28"
            />
          </div>
          <button
            onClick={addFilter}
            className="inline-flex items-center gap-1 px-3 py-1.5 bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold rounded-lg"
          >
            <Plus className="w-3.5 h-3.5" />
            Add filter
          </button>
        </div>

        {filterError && (
          <p role="alert" className="text-xs text-rose-700 bg-rose-50 border border-rose-200 rounded-lg px-3 py-2">
            {filterError}
          </p>
        )}

        {appConfig.custom_filters.length === 0 ? (
          <p className="text-xs text-slate-400">No custom filters active.</p>
        ) : (
          <ul className="space-y-1">
            {appConfig.custom_filters.map((filter, index) => (
              <li
                key={`${filter.field}-${filter.operator}-${filter.value}-${index}`}
                className="flex items-center justify-between text-xs font-mono bg-slate-50 border border-slate-200 rounded-lg px-3 py-2"
              >
                <span>{filter.field} {filter.operator} {String(filter.value)}</span>
                <button
                  onClick={() => removeFilter(index)}
                  className="text-rose-600 hover:text-rose-700"
                  aria-label={`Remove filter ${filter.field} ${filter.operator} ${String(filter.value)}`}
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
};
