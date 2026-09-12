import React from 'react';

/**
 * The closing line for one company, with the levels its technical score was
 * actually measured against drawn across it.
 *
 * The reference lines are the engine's own numbers, passed in rather than
 * recomputed here. That is deliberate. The score asks one question per level --
 * is the latest close above the trailing mean of the last 50 (or 200) valid
 * sessions -- and answers it once, at the last session. A rolling average drawn
 * as a curve would be a different quantity from the one that earned the points,
 * and computing it here would put a second implementation of the engine's
 * windowing in the UI, free to drift from the score it is meant to explain.
 *
 * So: one line for price, and a flat line for each level the score compared it
 * to. Where they cross is where the points were won or lost.
 */

const WIDTH = 600;
const HEIGHT = 180;
const PAD_X = 6;
const PAD_Y = 10;

interface Level {
  value: number;
  label: string;
  /** Stroke colour, matched to the tone the detail panel already uses. */
  colour: string;
  dash: string;
}

export interface PriceChartProps {
  closes: readonly number[];
  dates: readonly string[];
  sma50: number | null;
  sma200: number | null;
  high52Week: number | null;
  /** Trailing sessions to draw. The default is about one year of trading. */
  sessions?: number;
}

export const PriceChart: React.FC<PriceChartProps> = ({
  closes,
  dates,
  sma50,
  sma200,
  high52Week,
  sessions = 252,
}) => {
  // Only finite closes are plottable, and each must keep its own date.
  const usable: { close: number; date: string }[] = [];
  closes.forEach((close, i) => {
    if (Number.isFinite(close)) usable.push({ close, date: dates[i] ?? '' });
  });
  const window = usable.slice(-sessions);

  // A single point has no line to draw, and no span to scale against.
  if (window.length < 2) return null;

  const levels: Level[] = [];
  const addLevel = (value: number | null, label: string, colour: string, dash: string) => {
    if (value !== null && Number.isFinite(value)) levels.push({ value, label, colour, dash });
  };
  addLevel(sma50, '50 SMA', '#2563eb', '4 3');
  addLevel(sma200, '200 SMA', '#9333ea', '6 3');
  addLevel(high52Week, '52W high', '#059669', '2 3');

  // The scale has to cover the reference lines too, or a line above every close
  // in the window would be drawn outside the box and silently vanish.
  const values = window.map((p) => p.close).concat(levels.map((l) => l.value));
  const low = Math.min(...values);
  const high = Math.max(...values);
  // A perfectly flat series has no span to divide by; centre it instead.
  const span = high - low;
  const y = (value: number) =>
    span === 0 ? HEIGHT / 2 : PAD_Y + ((high - value) / span) * (HEIGHT - PAD_Y * 2);
  const x = (i: number) => PAD_X + (i / (window.length - 1)) * (WIDTH - PAD_X * 2);

  const points = window.map((p, i) => `${x(i).toFixed(2)},${y(p.close).toFixed(2)}`).join(' ');
  const first = window[0];
  const last = window[window.length - 1];
  const fell = last.close < first.close;

  return (
    <div data-testid="price-chart" className="space-y-1">
      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        className="w-full h-auto rounded bg-slate-50 border border-slate-100"
        role="img"
        aria-label={`Closing price over the last ${window.length} sessions`}
      >
        {levels.map((level) => (
          <line
            key={level.label}
            x1={PAD_X}
            x2={WIDTH - PAD_X}
            y1={y(level.value)}
            y2={y(level.value)}
            stroke={level.colour}
            strokeWidth={1}
            strokeDasharray={level.dash}
          />
        ))}
        <polyline
          points={points}
          fill="none"
          stroke={fell ? '#e11d48' : '#0f172a'}
          strokeWidth={1.5}
          strokeLinejoin="round"
          strokeLinecap="round"
        />
      </svg>

      <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1 text-[10px] text-slate-500">
        <span className="font-mono">
          {first.date || 'start'} to {last.date || 'latest'} · {window.length} sessions
        </span>
        <div className="flex flex-wrap items-center gap-2">
          {levels.map((level) => (
            <span key={level.label} className="inline-flex items-center gap-1">
              <span
                aria-hidden="true"
                className="inline-block w-3 border-t"
                style={{ borderColor: level.colour, borderTopStyle: 'dashed' }}
              />
              {level.label}
            </span>
          ))}
          {levels.length === 0 && <span>No level had enough history to draw</span>}
        </div>
      </div>
    </div>
  );
};
