import { AlertTriangle, CheckCircle, Database, FileText, Layers } from 'lucide-react';
import React from 'react';
import { DataInspectionReport } from '../types';

interface DataInspectionViewProps {
  report: DataInspectionReport;
  /**
   * Companies removed by the engine's deduplication (same ticker, BSE code or
   * normalised name). The status bar reports this same number; report.duplicateRows
   * counts something narrower, rows identical in every column.
   */
  duplicateCompanies?: number;
}

export const DataInspectionView: React.FC<DataInspectionViewProps> = ({
  report,
  duplicateCompanies,
}) => {
  return (
    <div className="space-y-6" id="data-inspection-container">
      {/* Top Level Metrics Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-xs">
          <div className="flex items-center justify-between text-slate-500 mb-1">
            <span className="text-xs font-medium uppercase tracking-wider">Total Companies</span>
            <Database className="w-4 h-4 text-blue-600" />
          </div>
          <div className="text-2xl font-bold text-slate-900 font-mono">{report.totalRows}</div>
          <span className="text-[11px] text-slate-400">Rows in CSV</span>
        </div>

        <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-xs">
          <div className="flex items-center justify-between text-slate-500 mb-1">
            <span className="text-xs font-medium uppercase tracking-wider">Total Columns</span>
            <Layers className="w-4 h-4 text-emerald-600" />
          </div>
          <div className="text-2xl font-bold text-slate-900 font-mono">{report.totalColumns}</div>
          <span className="text-[11px] text-slate-400">Exported Attributes</span>
        </div>

        <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-xs">
          <div className="flex items-center justify-between text-slate-500 mb-1">
            <span className="text-xs font-medium uppercase tracking-wider">Duplicate companies</span>
            <AlertTriangle
              className={`w-4 h-4 ${(duplicateCompanies ?? 0) > 0 ? 'text-amber-500' : 'text-slate-400'}`}
            />
          </div>
          <div className="text-2xl font-bold text-slate-900 font-mono" data-testid="duplicate-companies">
            {duplicateCompanies ?? 0}
          </div>
          <span className="text-[11px] text-slate-400">
            Removed by ticker, BSE code or name — the same count the status bar shows.
            <br />
            {report.duplicateRows} {report.duplicateRows === 1 ? 'row is' : 'rows are'} identical in
            every column.
          </span>
        </div>

        <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-xs">
          <div className="flex items-center justify-between text-slate-500 mb-1">
            <span className="text-xs font-medium uppercase tracking-wider">Primary Identifiers</span>
            <FileText className="w-4 h-4 text-purple-600" />
          </div>
          <div className="text-sm font-semibold text-slate-900 truncate">
            {report.detectedTickerCol || 'NSE/BSE code'}
          </div>
          <span className="text-[11px] text-slate-400">Name: {report.detectedNameCol || 'Name'}</span>
        </div>
      </div>

      {/* Missing Crucial Fields Warning Banner */}
      {report.configErrors && report.configErrors.length > 0 && (
        <div className="p-4 bg-red-50 border border-red-200 rounded-xl flex items-start gap-3 mb-4">
          <AlertTriangle className="w-5 h-5 text-red-600 flex-shrink-0 mt-0.5" />
          <div>
            <h4 className="text-xs font-semibold text-red-900">
              Invalid Custom Filters Detected
            </h4>
            <p className="text-xs text-red-700 mt-0.5">
              The screener halted because of invalid custom filters: {report.configErrors.join(', ')}.
            </p>
          </div>
        </div>
      )}

      {report.missingFields.length > 0 && (
        <div className="p-4 bg-amber-50 border border-amber-200 rounded-xl flex items-start gap-3">
          <AlertTriangle className="w-5 h-5 text-amber-600 flex-shrink-0 mt-0.5" />
          <div>
            <h4 className="text-xs font-semibold text-amber-900">
              Crucial Screener Factors Missing from Export
            </h4>
            <p className="text-xs text-amber-700 mt-0.5">
              The following critical parameters could not be detected: {report.missingFields.join(', ')}.
              A missing field earns no points for its factor and counts against coverage; nothing is
              filled in or estimated.
            </p>
          </div>
        </div>
      )}

      {/* Detailed Columns Inspection Table */}
      <div className="bg-white border border-slate-200 rounded-xl overflow-hidden shadow-xs">
        <div className="px-5 py-4 border-b border-slate-100 bg-slate-50/50 flex justify-between items-center">
          <div>
            <h3 className="text-sm font-semibold text-slate-900">Export Column Audit & Conversion Preview</h3>
            <p className="text-xs text-slate-500 mt-0.5">
              Identifies data types, missing value percentages, and formatting patterns needing numeric conversion.
            </p>
          </div>
          <span className="text-xs text-slate-500 font-medium">
            {report.columns.filter((c) => c.needsConversion).length} columns need conversion
          </span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs text-slate-700">
            <thead className="bg-slate-50 text-slate-500 font-medium border-b border-slate-100 uppercase tracking-wider text-[11px]">
              <tr>
                <th className="py-3 px-4">CSV Column Name</th>
                <th className="py-3 px-3">Mapped Factor</th>
                <th className="py-3 px-3">Detected Type</th>
                <th className="py-3 px-3 text-right">Missing Count (%)</th>
                <th className="py-3 px-3 text-center">Conversion</th>
                <th className="py-3 px-4">Raw Sample Values</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 font-mono text-[12px]">
              {report.columns.map((col, idx) => (
                <tr key={idx} className="hover:bg-slate-50/60 transition-colors">
                  <td className="py-2.5 px-4 font-sans font-semibold text-slate-900">
                    {col.name}
                  </td>
                  <td className="py-2.5 px-3">
                    {col.mappedField ? (
                      <span className="inline-flex items-center gap-1 font-sans text-xs text-blue-700 bg-blue-50 px-2 py-0.5 rounded border border-blue-100">
                        <CheckCircle className="w-3 h-3 text-blue-600" />
                        {col.mappedField}
                      </span>
                    ) : (
                      <span className="font-sans text-xs text-slate-400 italic">Unmapped</span>
                    )}
                  </td>
                  <td className="py-2.5 px-3 capitalize font-sans text-slate-600">
                    <span className="px-2 py-0.5 bg-slate-100 rounded text-[11px]">
                      {col.detectedType}
                    </span>
                  </td>
                  <td className="py-2.5 px-3 text-right">
                    <span className={col.nullCount > 0 ? 'text-amber-600 font-medium' : 'text-slate-500'}>
                      {col.nullCount} ({col.nullPercentage}%)
                    </span>
                  </td>
                  <td className="py-2.5 px-3 text-center font-sans">
                    {col.needsConversion ? (
                      <span className="text-[11px] font-medium text-amber-700 bg-amber-50 px-2 py-0.5 rounded border border-amber-200">
                        Stripped %, ₹, Cr
                      </span>
                    ) : (
                      <span className="text-[11px] text-slate-400">Direct float/text</span>
                    )}
                  </td>
                  <td className="py-2.5 px-4 text-slate-500 truncate max-w-xs font-mono text-[11px]">
                    {col.sampleValues.slice(0, 3).join(', ')}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
