// src/components/Modals/BugDetailsDrawer.jsx - Deep Bug Inspector Drawer with Debounced Notes & Resolution Toggle
import React, { useState, useEffect } from "react";
import { useBugTracker } from "../../useBugTracker.jsx";
import { apiService } from "../../api.js";

export default function BugDetailsDrawer() {
  const {
    activeDrawerBug,
    setActiveDrawerBug,
    toggleResolveBug,
    updateBugSeverity,
    updateBugNotes,
    bugs,
  } = useBugTracker();

  const [remarks, setRemarks] = useState("");
  const [saveStatus, setSaveStatus] = useState("Synced");
  const [sourceContext, setSourceContext] = useState(null);
  const [isLoadingContext, setIsLoadingContext] = useState(false);
  const [sourceContextError, setSourceContextError] = useState("");

  // Keep local remarks in sync with activeDrawerBug or shared bugs array
  useEffect(() => {
    if (activeDrawerBug) {
      const current = bugs.find((b) => b.id === activeDrawerBug.id) || activeDrawerBug;
      setRemarks(current.engineerNotes || "");
      setSaveStatus("Synced");
    }
  }, [activeDrawerBug, bugs]);

  // Fetch rich surrounding source code context for active bug on demand
  useEffect(() => {
    if (!activeDrawerBug?.id) {
      setSourceContext(null);
      setSourceContextError("");
      return;
    }

    let isCancelled = false;
    setIsLoadingContext(true);
    setSourceContextError("");

    if (typeof apiService.getSourceContext !== "function") {
      setSourceContext(null);
      setSourceContextError("Source context is unavailable.");
      setIsLoadingContext(false);
      return;
    }

    apiService
      .getSourceContext(activeDrawerBug.id, 8)
      .then((res) => {
        if (!isCancelled) {
          if (res.live && res.data?.found && Array.isArray(res.data.lines) && res.data.lines.length > 0) {
            setSourceContext(res.data);
          } else {
            setSourceContext(null);
            setSourceContextError(res.error || res.data?.message || "Source context is unavailable.");
          }
          setIsLoadingContext(false);
        }
      })
      .catch(() => {
        if (!isCancelled) {
          setSourceContext(null);
          setSourceContextError("Source context is unavailable.");
          setIsLoadingContext(false);
        }
      });

    return () => {
      isCancelled = true;
    };
  }, [activeDrawerBug?.id]);

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

  const handleSeverityChange = (e) => {
    updateBugSeverity(currentBug.id, e.target.value);
  };

  // Determine snippet lines to display: prefer full source file context when available on disk,
  // otherwise fallback seamlessly to the persisted PostgreSQL code_snippet.
  const hasContextLines = sourceContext && Array.isArray(sourceContext.lines) && sourceContext.lines.length > 0;
  const displaySnippet = hasContextLines
    ? sourceContext.lines.map((l) => ({
        num: l.line_number,
        text: l.content,
        isErr: l.is_target,
      }))
    : currentBug.codeSnippet && currentBug.codeSnippet.length > 0
    ? currentBug.codeSnippet
    : currentBug.rawSnippet
    ? currentBug.rawSnippet.split("\n").map((t, idx) => ({
        num: currentBug.line + idx,
        text: t,
        isErr: idx === 0,
      }))
    : [
        {
          num: currentBug.line || 1,
          text: currentBug.wrong || currentBug.title || "Vulnerability finding",
          isErr: true,
        },
      ];

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
              {currentBug.bugType && (
                <span className="text-[10px] font-semibold bg-cyan-500/10 text-cyan-300 border border-cyan-500/20 px-2 py-0.5 rounded">
                  {currentBug.bugType}
                </span>
              )}
              <select
                value={currentBug.severity}
                onChange={handleSeverityChange}
                className={`text-[10px] font-bold px-2 py-0.5 rounded cursor-pointer border focus:outline-none transition-colors ${
                  currentBug.severity === "High"
                    ? "bg-red-500/20 text-red-400 border-red-500/40"
                    : currentBug.severity === "Medium"
                    ? "bg-amber-500/20 text-amber-400 border-amber-500/40"
                    : "bg-blue-500/20 text-blue-400 border-blue-500/40"
                }`}
                title="Change issue severity"
              >
                <option value="High" className="bg-[#131B2E] text-red-400">High</option>
                <option value="Medium" className="bg-[#131B2E] text-amber-400">Medium</option>
                <option value="Low" className="bg-[#131B2E] text-blue-400">Low</option>
              </select>
              {currentBug.confidence != null && (
                <span className="text-[10px] font-mono font-bold bg-purple-500/20 text-purple-300 border border-purple-500/30 px-2 py-0.5 rounded">
                  Confidence: {typeof currentBug.confidence === "number" ? `${Math.round(currentBug.confidence <= 1 ? currentBug.confidence * 100 : currentBug.confidence)}%` : currentBug.confidence}
                </span>
              )}
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
              {currentBug.file}:{currentBug.lineRange || currentBug.line}
              {currentBug.column != null ? `:${currentBug.column}` : ""}
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
                : "Issue is currently Open and prioritized for engineering remediation."}
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

        {/* Problem Explanations & LLM Findings */}
        <div className="space-y-3">
          <div className="bg-[#0B0F17]/80 border border-slate-800/80 rounded-xl p-3.5 space-y-1">
            <span className="text-[10px] font-bold text-red-400 uppercase tracking-wider block">
              What is wrong / Description
            </span>
            <p className="text-xs text-slate-300 leading-relaxed">
              {currentBug.wrong || currentBug.description || "Defect detected in source line."}
            </p>
          </div>

          {currentBug.reasoning && currentBug.reasoning !== currentBug.wrong && currentBug.reasoning !== currentBug.description && (
            <div className="bg-[#0B0F17]/80 border border-indigo-500/30 rounded-xl p-3.5 space-y-1">
              <span className="text-[10px] font-bold text-indigo-400 uppercase tracking-wider block">
                LLM Reasoning & Root Cause
              </span>
              <p className="text-xs text-slate-300 leading-relaxed">
                {currentBug.reasoning}
              </p>
            </div>
          )}

          {/* Expected vs Actual Behavior */}
          {(currentBug.expectedBehavior || currentBug.actualBehavior) && (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {currentBug.expectedBehavior && (
                <div className="bg-[#0B0F17]/80 border border-emerald-500/30 rounded-xl p-3 space-y-1">
                  <span className="text-[10px] font-bold text-emerald-400 uppercase tracking-wider block">
                    ✓ Expected Behavior
                  </span>
                  <p className="text-xs text-slate-300 leading-relaxed">
                    {currentBug.expectedBehavior}
                  </p>
                </div>
              )}
              {currentBug.actualBehavior && (
                <div className="bg-[#0B0F17]/80 border border-red-500/30 rounded-xl p-3 space-y-1">
                  <span className="text-[10px] font-bold text-red-400 uppercase tracking-wider block">
                    ✗ Actual Behavior
                  </span>
                  <p className="text-xs text-slate-300 leading-relaxed">
                    {currentBug.actualBehavior}
                  </p>
                </div>
              )}
            </div>
          )}

          {/* Flagged Evidence / Relevant Code */}
          {(currentBug.relevantCode || currentBug.evidence) && (
            <div className="bg-[#0B0F17]/80 border border-slate-800/80 rounded-xl p-3 space-y-1 font-mono text-xs">
              <span className="text-[10px] font-bold text-cyan-400 uppercase tracking-wider block font-sans">
                Flagged Evidence / Relevant Code
              </span>
              <div className="bg-[#080C14] text-red-300 p-2.5 rounded-lg border border-red-500/20 overflow-x-auto whitespace-pre">
                {currentBug.relevantCode || currentBug.evidence}
              </div>
            </div>
          )}

          {currentBug.matter && (
            <div className="bg-[#0B0F17]/80 border border-slate-800/80 rounded-xl p-3.5 space-y-1">
              <span className="text-[10px] font-bold text-amber-400 uppercase tracking-wider block">
                Why it matters (Security Impact)
              </span>
              <p className="text-xs text-slate-300 leading-relaxed">
                {currentBug.matter}
              </p>
            </div>
          )}
        </div>

        {/* Code Snippet with Line Highlight & Real Context */}
        <div className="space-y-1.5">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-300 block">
              Vulnerable Code Snippet
            </span>
            <span className="text-[10px] font-mono text-cyan-400 bg-cyan-500/10 px-2 py-0.5 rounded border border-cyan-500/20">
              {isLoadingContext
                ? "Loading Source Context..."
                : hasContextLines
                ? "Source File Context"
                : sourceContextError
                ? "Source Context Unavailable"
                : "Database Analysis Snippet"}
            </span>
          </div>

          <div className="bg-[#0B0F17] border border-slate-800 rounded-xl overflow-hidden font-mono text-xs">
            <div className="bg-[#0F1623] px-3.5 py-1.5 border-b border-slate-800 text-[11px] text-slate-400 flex items-center justify-between">
              <span className="truncate max-w-[70%]">{currentBug.file}</span>
              <span className="text-red-400 shrink-0">
                {currentBug.lineRange ? `Lines ${currentBug.lineRange}` : `Line ${currentBug.line}`}
              </span>
            </div>
            <div className="p-3 overflow-x-auto max-h-64 space-y-0.5">
              {displaySnippet.map((line, idx) => (
                <div
                  key={idx}
                  className={`flex items-center py-0.5 px-1 rounded transition-colors ${
                    line.isErr
                      ? "bg-red-500/20 text-red-300 font-semibold border-l-2 border-red-500 pl-2"
                      : "text-slate-400"
                  }`}
                >
                  <span className="w-10 text-slate-600 select-none text-[11px] shrink-0">
                    {line.isErr ? "▶ " : "  "}{line.num}
                  </span>
                  <span className="whitespace-pre">{line.text}</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Suggested Fix Code Diff */}
        {currentBug.suggestedFix && (
          <div className="space-y-1.5">
            <span className="text-xs font-semibold text-emerald-400 block">
              AI Suggested Code Patch / Fix
            </span>
            <div className="bg-[#0B0F17] border border-emerald-500/30 rounded-xl p-3 font-mono text-xs space-y-1 overflow-x-auto">
              {currentBug.suggestedFix.remove && (
                <div className="text-red-400 whitespace-pre bg-red-500/10 p-1 rounded">
                  - {currentBug.suggestedFix.remove}
                </div>
              )}
              {currentBug.suggestedFix.add && (
                <div className="text-emerald-400 whitespace-pre bg-emerald-500/10 p-1 rounded">
                  + {currentBug.suggestedFix.add}
                </div>
              )}
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
