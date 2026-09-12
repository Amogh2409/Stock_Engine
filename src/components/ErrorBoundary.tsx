import { AlertTriangle } from 'lucide-react';
import React from 'react';

interface ErrorBoundaryProps {
  children: React.ReactNode;
  /** Clears whatever persisted state could be causing the crash. */
  onReset?: () => void;
}

interface ErrorBoundaryState {
  error: Error | null;
}

/**
 * Catches a render failure and shows what happened, so one bad value — a
 * corrupt saved run, an unexpected row — cannot leave the page blank with the
 * real error only in the console.
 */
export class ErrorBoundary extends React.Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error('The screener failed to render:', error, info.componentStack);
  }

  render() {
    const { error } = this.state;
    if (!error) return this.props.children;
    return (
      <div
        role="alert"
        data-testid="error-boundary"
        className="min-h-screen bg-slate-50 flex items-center justify-center p-6"
      >
        <div className="max-w-lg bg-white border border-rose-200 rounded-xl p-6 space-y-3">
          <h1 className="text-base font-bold text-rose-900 flex items-center gap-2">
            <AlertTriangle className="w-5 h-5 text-rose-600" />
            The screener could not display this
          </h1>
          <p className="text-xs text-slate-600">
            Nothing was lost: your CSV files are untouched and this page holds no other state.
            The most common cause is a saved comparison run left over from an older version.
          </p>
          <p className="text-xs font-mono bg-slate-50 border border-slate-200 rounded-lg p-2 text-slate-700">
            {error.message || String(error)}
          </p>
          <div className="flex flex-wrap gap-2">
            {this.props.onReset && (
              <button
                onClick={() => {
                  this.props.onReset?.();
                  this.setState({ error: null });
                }}
                className="px-3 py-1.5 bg-rose-600 hover:bg-rose-700 text-white text-xs font-semibold rounded-lg"
              >
                Clear the saved run and retry
              </button>
            )}
            <button
              onClick={() => this.setState({ error: null })}
              className="px-3 py-1.5 bg-white border border-slate-200 hover:bg-slate-50 text-slate-700 text-xs font-semibold rounded-lg"
            >
              Try again
            </button>
          </div>
        </div>
      </div>
    );
  }
}
