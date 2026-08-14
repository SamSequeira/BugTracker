// src/components/Tabs/TabReports.jsx - Tab 4: Executive Audit & PDF Report
import React from "react";
import { useBugTracker } from "../../useBugTracker.jsx";

export default function TabReports() {
  const {
    bugs,
    totalBugsCount,
    criticalUnresolvedCount,
    resolvedCount,
    openCount,
    resolutionPercentage,
    repoUrl,
    sessionUser,
    isLive,
    stats,
    setActiveTab,
    setActiveDrawerBug,
  } = useBugTracker();

  const handlePrint = () => {
    window.print();
  };

  const currentDate = new Date().toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });

  return (
    <div className="space-y-6 animate-fade-in max-w-7xl mx-auto print-container">
      {/* Top Banner & Print Trigger (Hidden during print) */}
      <div className="bg-[#131B2E] border border-slate-800 rounded-2xl p-6 sm:p-8 space-y-6 shadow-xl no-print">
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 border-b border-slate-800/80 pb-5">
          <div>
            <span className="text-[11px] font-mono uppercase tracking-wider text-cyan-400 font-semibold bg-cyan-500/10 px-2.5 py-1 rounded-full border border-cyan-500/20">
              Tab 4 • Compliance & Reports
            </span>
            <h2 className="text-xl sm:text-2xl font-bold text-white tracking-tight mt-2">
              Executive Security & Remediation Audit Report
            </h2>
            <p className="text-xs text-slate-400 mt-1">
              Synchronized in real time with Tab 3 triage actions, debounced remarks, and bug resolution states.
            </p>
          </div>

          {/* Download Report PDF Button */}
          <button
            type="button"
            onClick={handlePrint}
            className="bg-cyan-400 hover:bg-cyan-300 text-slate-950 font-bold px-5 py-3 rounded-xl text-xs sm:text-sm transition-all flex items-center gap-2 shadow-lg shadow-cyan-500/10 cursor-pointer shrink-0"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth="2"
                d="M17 17h2a2 2 0 002-2v-4a2 2 0 00-2-2H5a2 2 0 00-2 2v4a2 2 0 002 2h2m2 4h6a2 2 0 002-2v-4a2 2 0 00-2-2H9a2 2 0 00-2 2v4a2 2 0 002 2zm8-12V5a2 2 0 00-2-2H9a2 2 0 00-2 2v4h10z"
              />
            </svg>
            <span>Download Report (PDF)</span>
          </button>
        </div>

        {/* Resolution Progress Bar Card */}
        <div className="bg-[#0B0F17] border border-slate-800 rounded-xl p-5 space-y-3">
          <div className="flex justify-between items-center text-xs">
            <span className="font-semibold text-white">Remediation Progress</span>
            <span className="font-mono text-cyan-400 font-bold">{resolutionPercentage}% Resolved</span>
          </div>
          <div className="w-full bg-slate-800 h-2.5 rounded-full overflow-hidden">
            <div
              className="bg-gradient-to-r from-cyan-500 to-emerald-400 h-full transition-all duration-500"
              style={{ width: `${resolutionPercentage}%` }}
            ></div>
          </div>
          <div className="flex justify-between items-center text-[11px] text-slate-400 pt-1">
            <span>
              <strong className="text-emerald-400">{resolvedCount}</strong> of {totalBugsCount} issues mitigated
            </span>
            <span>
              <strong className="text-red-400">{openCount}</strong> issues pending resolution
            </span>
          </div>
        </div>
      </div>

      {/* Printable Report Header (Formatted specifically for Print & Screen) */}
      <div className="bg-[#131B2E] border border-slate-800 rounded-2xl p-6 print-card space-y-4 shadow-lg">
        <div className="border-b border-slate-800/80 pb-4 flex flex-col sm:flex-row justify-between sm:items-center gap-2">
          <div>
            <h1 className="text-xl font-bold text-white tracking-tight">
              BugTracker AI • Security Audit Summary
            </h1>
            <p className="text-xs text-slate-400 font-mono mt-0.5">
              Target Repository: <strong className="text-slate-200">{repoUrl}</strong>
            </p>
          </div>

          <div className="text-left sm:text-right text-xs text-slate-400 font-mono space-y-0.5">
            <div>Generated: <span className="text-slate-200">{currentDate}</span></div>
            <div>Auditor: <span className="text-slate-200">{sessionUser?.name || "Alex Mercer"}</span></div>
            <div className="text-[11px] text-cyan-400 font-semibold">{isLive ? "Live API Verified" : "Demo Data Audit"}</div>
          </div>
        </div>

        {/* KPI Metrics Cards */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-2">
          <div className="bg-[#0B0F17] border border-slate-800 rounded-xl p-3.5 space-y-1">
            <div className="text-[10px] uppercase font-bold text-slate-400">Total Issues</div>
            <div className="text-xl font-bold text-white font-mono">{totalBugsCount}</div>
          </div>

          <div className="bg-[#0B0F17] border border-red-500/20 rounded-xl p-3.5 space-y-1">
            <div className="text-[10px] uppercase font-bold text-red-400">Critical Open</div>
            <div className="text-xl font-bold text-red-400 font-mono">{criticalUnresolvedCount}</div>
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
              {bugs.map((bug) => {
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
                      {bug.file}:{bug.line}
                    </td>
                    <td className="py-3 px-3 font-medium text-white max-w-xs">
                      {bug.title}
                    </td>
                    <td className="py-3 px-3 whitespace-nowrap">
                      <span
                        className={`text-[10px] font-bold px-2 py-0.5 rounded ${
                          bug.severity === "Critical"
                            ? "bg-red-500/20 text-red-400"
                            : bug.severity === "High"
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
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
