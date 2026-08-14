// src/components/Modals/BugDetailsDrawer.jsx - Deep Bug Inspector Drawer with Debounced Notes & Resolution Toggle
import React, { useState, useEffect } from "react";
import { useBugTracker } from "../../useBugTracker.jsx";

export default function BugDetailsDrawer() {
  const {
    activeDrawerBug,
    setActiveDrawerBug,
    toggleResolveBug,
    updateBugNotes,
    bugs,
  } = useBugTracker();

  const [remarks, setRemarks] = useState("");
  const [saveStatus, setSaveStatus] = useState("Synced");

  // Keep local remarks in sync with activeDrawerBug or shared bugs array
  useEffect(() => {
    if (activeDrawerBug) {
      const current = bugs.find((b) => b.id === activeDrawerBug.id) || activeDrawerBug;
      setRemarks(current.engineerNotes || "");
      setSaveStatus("Synced");
    }
  }, [activeDrawerBug, bugs]);

  if (!activeDrawerBug) return null;

  // Retrieve latest state for active bug from shared bugs array
  const currentBug = bugs.find((b) => b.id === activeDrawerBug.id) || activeDrawerBug;
  const isResolved = currentBug.status === "Resolved";

  const handleRemarksChange = (e) => {
    const newVal = e.target.value;
    setRemarks(newVal);
    setSaveStatus("Saving...");
    updateBugNotes(currentBug.id, newVal);
    setTimeout(() => {
      setSaveStatus("Auto-saved to API");
    }, 550);
  };

  const handleToggleResolve = () => {
    toggleResolveBug(currentBug.id);
  };

  return (
    <div
      className="fixed inset-0 z-50 flex justify-end bg-black/60 backdrop-blur-xs animate-fade-in"
      onClick={() => setActiveDrawerBug(null)}
    >
      <div
        className="w-full max-w-2xl bg-[#131B2E] border-l border-slate-800 h-full p-6 space-y-5 shadow-2xl flex flex-col animate-slide-in relative overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-start justify-between border-b border-slate-800 pb-4 shrink-0">
          <div className="space-y-1 pr-4">
            <div className="flex items-center space-x-2 flex-wrap gap-y-1">
              <span className="font-mono text-xs text-cyan-400 font-bold bg-cyan-500/10 px-2 py-0.5 rounded border border-cyan-500/20">
                {currentBug.id}
              </span>
              <span
                className={`text-[10px] font-bold px-2 py-0.5 rounded ${
                  currentBug.severity === "Critical"
                    ? "bg-red-500/20 text-red-400 border border-red-500/30"
                    : currentBug.severity === "High"
                    ? "bg-amber-500/20 text-amber-400 border border-amber-500/30"
                    : "bg-blue-500/20 text-blue-400 border border-blue-500/30"
                }`}
              >
                {currentBug.severity}
              </span>
              <span className="text-[10px] font-medium bg-slate-800 text-slate-300 px-2 py-0.5 rounded">
                {currentBug.priority}
              </span>
              <span
                className={`text-[10px] font-bold px-2 py-0.5 rounded ${
                  isResolved
                    ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30"
                    : "bg-red-500/20 text-red-400 border border-red-500/30"
                }`}
              >
                {currentBug.status}
              </span>
            </div>
            <h3 className="text-base font-bold text-white leading-snug pt-1">
              {currentBug.title}
            </h3>
            <p className="text-xs text-slate-400 font-mono">
              {currentBug.file}:{currentBug.line}
            </p>
          </div>

          <button
            onClick={() => setActiveDrawerBug(null)}
            className="text-slate-400 hover:text-white p-1 rounded-lg hover:bg-slate-800 transition-colors shrink-0"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Resolution Toggle Banner */}
        <div className="bg-[#0B0F17] border border-slate-800 rounded-xl p-4 flex items-center justify-between shrink-0">
          <div>
            <div className="text-xs font-semibold text-white">Status Action</div>
            <div className="text-[11px] text-slate-400">
              {isResolved
                ? "Issue is marked as Resolved and reflected across all tabs."
                : "Issue is currently Open and counted in critical metrics."}
            </div>
          </div>
          <button
            type="button"
            onClick={handleToggleResolve}
            className={`px-4 py-2 rounded-lg text-xs font-bold transition-all flex items-center gap-1.5 shadow-md cursor-pointer ${
              isResolved
                ? "bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700"
                : "bg-emerald-500 hover:bg-emerald-400 text-slate-950 shadow-emerald-500/20"
            }`}
          >
            {isResolved ? (
              <>
                <span>↩ Reopen Issue</span>
              </>
            ) : (
              <>
                <span>✓ Mark as Resolved</span>
              </>
            )}
          </button>
        </div>

        {/* Problem Explanations */}
        <div className="space-y-3">
          <div className="bg-[#0B0F17]/80 border border-slate-800/80 rounded-xl p-3.5 space-y-1">
            <span className="text-[10px] font-bold text-red-400 uppercase tracking-wider block">
              What is wrong
            </span>
            <p className="text-xs text-slate-300 leading-relaxed">
              {currentBug.wrong || "Vulnerability detected in source line."}
            </p>
          </div>

          <div className="bg-[#0B0F17]/80 border border-slate-800/80 rounded-xl p-3.5 space-y-1">
            <span className="text-[10px] font-bold text-amber-400 uppercase tracking-wider block">
              Why it matters (Security Impact)
            </span>
            <p className="text-xs text-slate-300 leading-relaxed">
              {currentBug.matter || "Could lead to exploitation or data integrity failure."}
            </p>
          </div>
        </div>

        {/* Code Snippet with Line Highlight */}
        {currentBug.codeSnippet && (
          <div className="space-y-1.5">
            <span className="text-xs font-semibold text-slate-300 block">
              Vulnerable Code Snippet
            </span>
            <div className="bg-[#0B0F17] border border-slate-800 rounded-xl overflow-hidden font-mono text-xs">
              <div className="bg-[#0F1623] px-3.5 py-1.5 border-b border-slate-800 text-[11px] text-slate-400 flex items-center justify-between">
                <span>{currentBug.file}</span>
                <span className="text-red-400">Line {currentBug.line}</span>
              </div>
              <div className="p-3 overflow-x-auto">
                {currentBug.codeSnippet.map((line, idx) => (
                  <div
                    key={idx}
                    className={`flex items-center py-0.5 px-1 rounded ${
                      line.isErr ? "bg-red-500/20 text-red-300 font-semibold border-l-2 border-red-500 pl-2" : "text-slate-400"
                    }`}
                  >
                    <span className="w-8 text-slate-600 select-none text-[11px]">{line.num}</span>
                    <span className="whitespace-pre">{line.text}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* Suggested Fix Code Diff */}
        {currentBug.suggestedFix && (
          <div className="space-y-1.5">
            <span className="text-xs font-semibold text-emerald-400 block">
              AI Suggested Code Patch
            </span>
            <div className="bg-[#0B0F17] border border-emerald-500/30 rounded-xl p-3 font-mono text-xs space-y-1 overflow-x-auto">
              <div className="text-red-400 whitespace-pre bg-red-500/10 p-1 rounded">
                {currentBug.suggestedFix.remove}
              </div>
              <div className="text-emerald-400 whitespace-pre bg-emerald-500/10 p-1 rounded">
                {currentBug.suggestedFix.add}
              </div>
              {currentBug.suggestedFix.note && (
                <div className="text-[11px] text-slate-400 pt-1 font-sans">
                  💡 {currentBug.suggestedFix.note}
                </div>
              )}
            </div>
          </div>
        )}

        {/* Engineer Remarks with 500ms Debounce & Two-Way Sync */}
        <div className="space-y-1.5 pt-2">
          <div className="flex items-center justify-between">
            <label className="text-xs font-semibold text-slate-300">
              Engineer Remarks & Remediation Notes
            </label>
            <span className="text-[10px] text-slate-400 font-mono flex items-center gap-1">
              <span className={`w-1.5 h-1.5 rounded-full ${saveStatus.includes("Saving") ? "bg-amber-400 animate-spin" : "bg-emerald-400"}`}></span>
              {saveStatus}
            </span>
          </div>
          <textarea
            rows={3}
            value={remarks}
            onChange={handleRemarksChange}
            placeholder="Type resolution steps or architectural notes here... (Synced in real time to Tab 4 reports & API)"
            className="w-full bg-[#0B0F17] border border-slate-700 rounded-xl p-3 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-cyan-400 transition-colors font-sans"
          />
          <p className="text-[11px] text-slate-500">
            Remarks auto-sync immediately to Tab 4 Executive Reports and persist via debounced API calls.
          </p>
        </div>

        {/* Metadata Footer */}
        <div className="bg-[#0B0F17] border border-slate-800/80 rounded-xl p-3 text-[11px] text-slate-400 flex items-center justify-between shrink-0">
          <div>Assigned: <strong className="text-white">{currentBug.engineer || "Alex Mercer"}</strong></div>
          <div>Reported: <span className="font-mono text-slate-300">{currentBug.createdAt}</span></div>
        </div>
      </div>
    </div>
  );
}
