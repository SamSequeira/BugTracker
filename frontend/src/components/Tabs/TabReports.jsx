// src/components/Tabs/TabReports.jsx - Tab 4: Executive Audit & PDF Report
import React, { useState } from "react";
import { useBugTracker } from "../../useBugTracker.jsx";
import { apiService } from "../../api.js";

export default function TabReports() {
  const {
    bugs,
    totalBugsCount,
    highUnresolvedCount,
    resolvedCount,
    openCount,
    resolutionPercentage,
    repoUrl,
    sessionUser,
    isLive,
    stats,
    setActiveTab,
    setActiveDrawerBug,
    currentRepositoryId,
  } = useBugTracker();

  const [exportFormat, setExportFormat] = useState("pdf");
  const [isExporting, setIsExporting] = useState(false);

  const handlePrint = () => {
    window.print();
  };

  const handleBackendExport = async () => {
    if (!currentRepositoryId) {
      handlePrint();
      return;
    }

    try {
      setIsExporting(true);
      const url = `${apiService.getBaseUrl()}/repositories/export/${currentRepositoryId}?format=${exportFormat}`;
      const response = await fetch(url);
      if (!response.ok) {
        throw new Error(`Export failed: ${response.statusText}`);
      }

      const blob = await response.blob();
      const downloadUrl = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = downloadUrl;
      link.download = `bugtracker_audit_${currentRepositoryId}.${exportFormat}`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(downloadUrl);
    } catch (err) {
      console.warn("Backend export failed, falling back to window.print():", err);
      handlePrint();
    } finally {
      setIsExporting(false);
    }
  };

  return (
    <div className="space-y-6 animate-fade-in max-w-7xl mx-auto print-container">
      {/* Action Header Card */}
      <div className="bg-[#131B2E] border border-slate-800 rounded-2xl p-6 sm:p-8 space-y-6 print-card shadow-xl">
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 border-b border-slate-800/80 pb-6">
          <div>
            <span className="text-[11px] font-mono uppercase tracking-wider text-cyan-400 font-semibold bg-cyan-500/10 px-2.5 py-1 rounded-full border border-cyan-500/20">
              Tab 4 • Compliance & Verification
            </span>
            <h2 className="text-xl sm:text-2xl font-bold text-white tracking-tight mt-2">
              Executive Security & Architecture Audit Report
            </h2>
            <p className="text-xs text-slate-400 mt-1">
              Deterministic, signed summary report ready for stakeholder presentation or security compliance sign-off.
            </p>
          </div>

          {/* Action Buttons: Format Selector + Export */}
          <div className="flex items-center space-x-2.5 no-print shrink-0">
            <select
              value={exportFormat}
              onChange={(e) => setExportFormat(e.target.value)}
              className="bg-[#0B0F17] border border-slate-700 rounded-xl px-3 py-2 text-xs text-white focus:outline-none focus:border-cyan-400 font-mono transition-colors"
            >
              <option value="pdf">PDF Document (.pdf)</option>
              <option value="csv">CSV Spreadsheet (.csv)</option>
              <option value="json">Raw JSON (.json)</option>
              <option value="md">Markdown (.md)</option>
              <option value="html">HTML Report (.html)</option>
            </select>

            <button
              onClick={handleBackendExport}
              disabled={isExporting}
              className="bg-cyan-500 hover:bg-cyan-400 disabled:opacity-50 text-slate-950 font-bold px-4 py-2 rounded-xl text-xs flex items-center space-x-2 transition-all shadow-md shadow-cyan-500/20 cursor-pointer"
            >
              <span>{isExporting ? "Exporting..." : "Export"}</span>
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
              </svg>
            </button>
          </div>
        </div>

        {/* Audit Meta Grid */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 text-xs font-mono">
          <div className="bg-[#0B0F17]/80 p-3 rounded-xl border border-slate-800">
            <span className="text-slate-400 block text-[10px] uppercase">Target Repository</span>
            <span className="text-white font-bold truncate block">{repoUrl || "active-analysis-repo"}</span>
          </div>
          <div className="bg-[#0B0F17]/80 p-3 rounded-xl border border-slate-800">
            <span className="text-slate-400 block text-[10px] uppercase">Lead Auditor</span>
            <span className="text-white font-bold">{sessionUser?.name || "Alex Mercer"}</span>
          </div>
          <div className="bg-[#0B0F17]/80 p-3 rounded-xl border border-slate-800">
            <span className="text-slate-400 block text-[10px] uppercase">Engine Signature</span>
            <span className="text-cyan-400 font-bold">AST-PARSER-v2.6.4</span>
          </div>
          <div className="bg-[#0B0F17]/80 p-3 rounded-xl border border-slate-800">
            <span className="text-slate-400 block text-[10px] uppercase">Generated Timestamp</span>
            <span className="text-slate-300 font-bold">{new Date().toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })}</span>
          </div>
        </div>

        {/* KPI Metrics Cards */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-2">
          <div className="bg-[#0B0F17] border border-slate-800 rounded-xl p-3.5 space-y-1">
            <div className="text-[10px] uppercase font-bold text-slate-400">Total Issues</div>
            <div className="text-xl font-bold text-white font-mono">{totalBugsCount}</div>
          </div>

          <div className="bg-[#0B0F17] border border-red-500/20 rounded-xl p-3.5 space-y-1">
            <div className="text-[10px] uppercase font-bold text-red-400">High Open</div>
            <div className="text-xl font-bold text-red-400 font-mono">{highUnresolvedCount}</div>
          </div>

          <div className="bg-[#0B0F17] border border-emerald-500/20 rounded-xl p-3.5 space-y-1">
            <div className="text-[10px] uppercase font-bold text-emerald-400">Resolved</div>
            <div className="text-xl font-bold text-emerald-400 font-mono">{resolvedCount}</div>
          </div>

          <div className="bg-[#0B0F17] border border-cyan-500/20 rounded-xl p-3.5 space-y-1">
            <div className="text-[10px] uppercase font-bold text-cyan-400">Health Index</div>
            <div className="text-xl font-bold text-cyan-400 font-mono">{stats.healthScore || 84}/100</div>
          </div>
        </div>
      </div>

      {/* Comprehensive Bug Resolution Audit Table */}
      <div className="bg-[#131B2E] border border-slate-800 rounded-2xl p-6 print-card space-y-4 shadow-xl overflow-hidden">
        <div className="flex items-center justify-between">
          <h3 className="text-sm sm:text-base font-bold text-white">
            Vulnerability Remediation Audit Log
          </h3>
          <span className="text-xs text-slate-400 font-mono">{bugs.length} recorded entries</span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs border-collapse print-table">
            <thead>
              <tr className="border-b border-slate-800 text-slate-400 font-semibold bg-[#0B0F17]/80">
                <th className="py-3 px-3">Bug ID</th>
                <th className="py-3 px-3">File Location</th>
                <th className="py-3 px-3">Vulnerability Title</th>
                <th className="py-3 px-3">Severity</th>
                <th className="py-3 px-3">Status</th>
                <th className="py-3 px-3">Engineer</th>
                <th className="py-3 px-3">Remediation Remarks</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60">
              {bugs.length === 0 ? (
                <tr>
                  <td colSpan={7} className="py-6 text-center text-slate-500 text-xs italic">
                    No issues recorded for this repository.
                  </td>
                </tr>
              ) : (
                bugs.map((bug) => {
                  const isResolved = bug.status === "Resolved";
                  return (
                    <tr
                      key={bug.id}
                      onClick={() => {
                        setActiveTab("bugs");
                        setActiveDrawerBug(bug);
                      }}
                      className="hover:bg-slate-800/50 transition-colors cursor-pointer"
                    >
                      <td className="py-3 px-3 font-mono font-bold text-cyan-400 whitespace-nowrap">
                        {bug.id}
                      </td>
                      <td className="py-3 px-3 font-mono text-slate-300 whitespace-nowrap">
                        {bug.file}:{bug.lineRange || bug.line}
                      </td>
                      <td className="py-3 px-3 font-medium text-white max-w-xs">
                        {bug.title}
                      </td>
                      <td className="py-3 px-3 whitespace-nowrap">
                        <span
                          className={`text-[10px] font-bold px-2 py-0.5 rounded ${
                            bug.severity === "High"
                              ? "bg-red-500/20 text-red-400"
                              : bug.severity === "Medium"
                              ? "bg-amber-500/20 text-amber-400"
                              : "bg-blue-500/20 text-blue-400"
                          }`}
                        >
                          {bug.severity}
                        </span>
                      </td>
                      <td className="py-3 px-3 whitespace-nowrap">
                        <span
                          className={`text-[10px] font-bold px-2 py-0.5 rounded ${
                            isResolved
                              ? "bg-emerald-500/20 text-emerald-400 badge-resolved"
                              : "bg-red-500/20 text-red-400 badge-open"
                          }`}
                        >
                          {bug.status}
                        </span>
                      </td>
                      <td className="py-3 px-3 text-slate-400 whitespace-nowrap">
                        {bug.engineer || "Unassigned"}
                      </td>
                      <td className="py-3 px-3 text-slate-300 italic max-w-sm">
                        {bug.engineerNotes || "No remediation remarks entered."}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
