import { CheckCircle2, Play, ShieldCheck, Timer, XCircle } from 'lucide-react';
import React, { useState } from 'react';
import { TestResult } from '../types';
import { runAllValidations } from '../utils/testRunner';

export const TestsRunner: React.FC = () => {
  const [testResults, setTestResults] = useState<TestResult[]>(() => runAllValidations());
  const [isRunning, setIsRunning] = useState(false);

  const handleRunTests = () => {
    setIsRunning(true);
    setTimeout(() => {
      const results = runAllValidations();
      setTestResults(results);
      setIsRunning(false);
    }, 250);
  };

  const allPassed = testResults.every((t) => t.passed);
  const totalExecutionTime = testResults.reduce((acc, t) => acc + t.executionTimeMs, 0).toFixed(2);

  return (
    <div className="space-y-6" id="tests-runner-container">
      {/* Header & Trigger */}
      <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-xs flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <ShieldCheck className="w-5 h-5 text-emerald-600" />
            <h3 className="text-sm font-semibold text-slate-900">
              Deterministic Verification & Automated Unit Tests
            </h3>
          </div>
          <p className="text-xs text-slate-500 mt-1 max-w-xl leading-relaxed">
            Runs the engine's own invariants in your browser: unit-aware parsing, rounding, identifier
            mapping, pinned scores, deduplication, custom filters, price-history technicals and CSV
            formula-injection guards. The automated test suite asserts every one of them.
          </p>
        </div>

        <button
          onClick={handleRunTests}
          disabled={isRunning}
          className="inline-flex items-center gap-1.5 px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-semibold rounded-lg transition-colors shadow-xs flex-shrink-0 disabled:opacity-50"
        >
          <Play className="w-3.5 h-3.5" />
          {isRunning ? 'Running Tests...' : 'Re-Run All Tests'}
        </button>
      </div>

      {/* Summary Status Banner */}
      <div
        className={`p-4 rounded-xl border flex items-center justify-between ${
          allPassed ? 'bg-emerald-50/70 border-emerald-200 text-emerald-900' : 'bg-rose-50 border-rose-200 text-rose-900'
        }`}
      >
        <div className="flex items-center gap-3">
          {allPassed ? (
            <CheckCircle2 className="w-6 h-6 text-emerald-600 flex-shrink-0" />
          ) : (
            <XCircle className="w-6 h-6 text-rose-600 flex-shrink-0" />
          )}
          <div>
            <div className="text-sm font-bold">
              {allPassed ? 'All Quantitative Invariants Passed' : 'Validation Failures Detected'}
            </div>
            <div className="text-xs text-slate-600 mt-0.5">
              {testResults.filter((t) => t.passed).length} of {testResults.length} test scenarios verified successfully.
            </div>
          </div>
        </div>

        <div className="flex items-center gap-1.5 text-xs text-slate-500 font-mono bg-white px-3 py-1.5 rounded-lg border border-slate-200">
          <Timer className="w-3.5 h-3.5" />
          {totalExecutionTime} ms
        </div>
      </div>

      {/* Tests Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {testResults.map((test, idx) => (
          <div
            key={idx}
            className="bg-white border border-slate-200 rounded-xl p-4 shadow-xs flex flex-col justify-between space-y-2"
          >
            <div>
              <div className="flex items-center justify-between">
                <span className="text-[10px] font-mono uppercase tracking-wider text-slate-400">
                  {test.category}
                </span>
                <span className="text-[10px] font-mono text-slate-400">{test.executionTimeMs}ms</span>
              </div>
              <h4 className="text-sm font-semibold text-slate-900 mt-1 flex items-center gap-1.5">
                {test.passed ? (
                  <CheckCircle2 className="w-4 h-4 text-emerald-600 flex-shrink-0" />
                ) : (
                  <XCircle className="w-4 h-4 text-rose-600 flex-shrink-0" />
                )}
                {test.name}
              </h4>
              <p className="text-xs text-slate-600 mt-2 leading-relaxed font-sans">{test.message}</p>
            </div>

            <div className="pt-2 border-t border-slate-100 flex items-center justify-between text-[11px]">
              <span className="text-slate-400">Deterministic check #{idx + 1}</span>
              <span
                className={`font-semibold px-2 py-0.5 rounded ${
                  test.passed ? 'bg-emerald-50 text-emerald-700' : 'bg-rose-50 text-rose-700'
                }`}
              >
                {test.passed ? 'PASS' : 'FAIL'}
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
