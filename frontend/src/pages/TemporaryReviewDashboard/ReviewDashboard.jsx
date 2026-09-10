// frontend/src/pages/TemporaryReviewDashboard/ReviewDashboard.jsx
// Temporary Human Ground-Truth Review Web Dashboard with Independent PostgreSQL Code Snippet Display

import React, { useState, useEffect, useRef } from "react";
import {
  fetchReviewBatch,
  fetchCandidateIssue,
  fetchSourceContext,
  saveCandidateLabels,
  fetchDatasetStats,
} from "./reviewApi.js";
import { getRuleExplanation } from "../../utils/ruleExplanations.js";
import "./ReviewDashboard.css";

const SEVERITY_OPTIONS = [
  { id: "high", label: "High", color: "from-red-600 to-rose-700", border: "border-red-500", text: "text-red-400" },
  { id: "medium", label: "Medium", color: "from-amber-600 to-yellow-700", border: "border-amber-500", text: "text-amber-400" },
  { id: "low", label: "Low", color: "from-blue-600 to-teal-700", border: "border-blue-500", text: "text-blue-400" },
];

const PRIORITY_OPTIONS = [
  { id: "p1", label: "P1 — High / Blocker", color: "from-red-600 to-rose-700", border: "border-red-500", text: "text-red-400" },
  { id: "p2", label: "P2 — Medium / Normal", color: "from-amber-600 to-yellow-700", border: "border-amber-500", text: "text-amber-400" },
  { id: "p3", label: "P3 — Low / Backlog", color: "from-blue-600 to-slate-700", border: "border-blue-500", text: "text-blue-400" },
];

export default function ReviewDashboard() {
  // Batch & Navigation state
  const [items, setItems] = useState([]);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [jumpInput, setJumpInput] = useState("1");

  // Local verification states map: { [issueId]: { verified_severity, verified_priority, verification_notes, is_false_positive, status } }
  const [issueStatuses, setIssueStatuses] = useState({});

  // Active form state for current issue
  const [selectedSeverity, setSelectedSeverity] = useState("");
  const [selectedPriority, setSelectedPriority] = useState("");
  const [reviewerNotes, setReviewerNotes] = useState("");
  const [isSaving, setIsSaving] = useState(false);

  // False Positive Modal state
  const [showFpModal, setShowFpModal] = useState(false);
  const [fpExplanation, setFpExplanation] = useState("");

  // Optional Source Context state (non-blocking)
  const [showContext, setShowContext] = useState(false);
  const [contextData, setContextData] = useState(null);
  const [loadingContext, setLoadingContext] = useState(false);

  // Technical Evidence Accordion state
  const [showEvidence, setShowEvidence] = useState(false);

  // Blinded review toggle (default: true)
  const [blindedMode, setBlindedMode] = useState(true);

  // Dataset Statistics
  const [stats, setStats] = useState(null);

  // Notification Toast
  const [toast, setToast] = useState(null);

  const notesTextareaRef = useRef(null);

  const showToast = (message, type = "success") => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 3500);
  };

  // 1. Initial Load: Fetch 200-item review batch and dataset statistics
  useEffect(() => {
    let mounted = true;
    async function loadData() {
      try {
        setLoading(true);
        setError(null);

        const [batchItems, datasetStats] = await Promise.all([
          fetchReviewBatch(200, 42),
          fetchDatasetStats(),
        ]);

        if (!mounted) return;

        setItems(batchItems);
        setStats(datasetStats);

        // Map live status for each issue in the batch
        const statusMap = {};
        let firstUnreviewedIdx = 0;
        let foundFirstUnreviewed = false;

        for (let i = 0; i < batchItems.length; i++) {
          const itm = batchItems[i];
          let status = "UNREVIEWED";
          let sev = itm.verified_severity || "";
          let prio = itm.verified_priority || "";
          let notes = itm.verification_notes || "";
          let isFp = false;

          if (sev && prio) {
            status = "CONFIRMED";
          } else if (notes && notes.startsWith("[FALSE_POSITIVE]")) {
            status = "FALSE_POSITIVE";
            isFp = true;
          } else if (sev || prio) {
            status = "PARTIAL";
          } else {
            status = "UNREVIEWED";
            if (!foundFirstUnreviewed) {
              firstUnreviewedIdx = i;
              foundFirstUnreviewed = true;
            }
          }

          statusMap[itm.id] = {
            verified_severity: sev,
            verified_priority: prio,
            verification_notes: notes,
            is_false_positive: isFp,
            status,
          };
        }

        setIssueStatuses(statusMap);
        setCurrentIndex(firstUnreviewedIdx);
        setJumpInput(String(firstUnreviewedIdx + 1));
      } catch (err) {
        if (!mounted) return;
        setError(`Failed to initialize review batch: ${err.message}`);
      } finally {
        if (mounted) setLoading(false);
      }
    }

    loadData();
    return () => {
      mounted = false;
    };
  }, []);

  // Current active issue
  const currentItem = items[currentIndex] || null;
  const ruleInfo = currentItem
    ? getRuleExplanation(currentItem.rule_id, currentItem.issue_type)
    : null;

  // Compute presence of valid persisted code snippet
  const snippetRaw = currentItem?.code_snippet;
  const snippetTrimmed = typeof snippetRaw === "string" ? snippetRaw.trim() : "";
  const hasValidSnippet = snippetTrimmed.length > 0;

  // 2. Sync local form fields when active issue changes & auto-enrich if snippet missing
  useEffect(() => {
    if (!currentItem) return;

    // If candidate issue in batch is somehow missing code_snippet, fetch live single issue as compatibility fallback
    if (currentItem.code_snippet === undefined || currentItem.code_snippet === null) {
      fetchCandidateIssue(currentItem.id)
        .then((fullIssue) => {
          if (fullIssue && fullIssue.code_snippet !== undefined) {
            setItems((prevItems) =>
              prevItems.map((it, idx) =>
                idx === currentIndex ? { ...it, code_snippet: fullIssue.code_snippet } : it
              )
            );
          }
        })
        .catch(() => {
          // non-blocking
        });
    }

    const savedState = issueStatuses[currentItem.id];
    if (savedState) {
      setSelectedSeverity(savedState.verified_severity || "");
      setSelectedPriority(savedState.verified_priority || "");
      setReviewerNotes(
        savedState.verification_notes
          ? savedState.verification_notes.replace(/^\[FALSE_POSITIVE\]\s*/, "")
          : ""
      );
    } else {
      setSelectedSeverity("");
      setSelectedPriority("");
      setReviewerNotes("");
    }

    // Reset optional context and technical drawers on navigation
    setShowContext(false);
    setContextData(null);
    setShowEvidence(false);
    setJumpInput(String(currentIndex + 1));
  }, [currentIndex, currentItem, issueStatuses]);

  // 3. Load source context on demand (optional & non-blocking)
  const handleToggleContext = async () => {
    if (showContext) {
      setShowContext(false);
      return;
    }

    if (!currentItem) return;

    setShowContext(true);
    if (!contextData) {
      setLoadingContext(true);
      try {
        const res = await fetchSourceContext(currentItem.id, 15);
        setContextData(res);
      } catch (err) {
        setContextData({
          found: false,
          message: "The original repository file is not currently available on disk.",
          formatted_text: "[Notice] Source file not accessible on disk.",
          lines: [],
        });
      } finally {
        setLoadingContext(false);
      }
    }
  };

  // 4. Save Confirmation action
  const handleConfirmValid = async () => {
    if (!selectedSeverity || !selectedPriority) {
      showToast("Please select both Severity and Priority.", "error");
      return;
    }

    if (!reviewerNotes.trim()) {
      showToast("Reviewer notes are required to confirm an issue.", "error");
      if (notesTextareaRef.current) notesTextareaRef.current.focus();
      return;
    }

    if (!currentItem) return;

    setIsSaving(true);
    try {
      const payload = {
        verified_severity: selectedSeverity,
        verified_priority: selectedPriority,
        verification_notes: reviewerNotes.trim(),
        is_false_positive: false,
      };

      await saveCandidateLabels(currentItem.id, payload);

      setIssueStatuses((prev) => ({
        ...prev,
        [currentItem.id]: {
          verified_severity: selectedSeverity,
          verified_priority: selectedPriority,
          verification_notes: reviewerNotes.trim(),
          is_false_positive: false,
          status: "CONFIRMED",
        },
      }));

      const updatedStats = await fetchDatasetStats();
      if (updatedStats) setStats(updatedStats);

      showToast(`Saved Issue #${currentIndex + 1} as Confirmed Valid!`);

      if (currentIndex < items.length - 1) {
        setCurrentIndex(currentIndex + 1);
      }
    } catch (err) {
      showToast(err.message, "error");
    } finally {
      setIsSaving(false);
    }
  };

  // 5. Save False Positive action
  const handleConfirmFalsePositive = async () => {
    if (!fpExplanation.trim()) {
      showToast("Technical explanation is required for false positives.", "error");
      return;
    }

    if (!currentItem) return;

    setIsSaving(true);
    try {
      const payload = {
        is_false_positive: true,
        verified_severity: null,
        verified_priority: null,
        verification_notes: `[FALSE_POSITIVE] ${fpExplanation.trim()}`,
      };

      await saveCandidateLabels(currentItem.id, payload);

      setIssueStatuses((prev) => ({
        ...prev,
        [currentItem.id]: {
          verified_severity: null,
          verified_priority: null,
          verification_notes: `[FALSE_POSITIVE] ${fpExplanation.trim()}`,
          is_false_positive: true,
          status: "FALSE_POSITIVE",
        },
      }));

      setShowFpModal(false);
      setFpExplanation("");

      const updatedStats = await fetchDatasetStats();
      if (updatedStats) setStats(updatedStats);

      showToast(`Marked Issue #${currentIndex + 1} as False Positive.`);

      if (currentIndex < items.length - 1) {
        setCurrentIndex(currentIndex + 1);
      }
    } catch (err) {
      showToast(err.message, "error");
    } finally {
      setIsSaving(false);
    }
  };

  // 6. Skip & Navigation actions
  const handleSkip = () => {
    if (currentIndex < items.length - 1) {
      setCurrentIndex(currentIndex + 1);
      showToast(`Skipped Issue #${currentIndex + 1} (remains in queue).`, "info");
    } else {
      showToast("Reached the end of the review batch.", "info");
    }
  };

  const handlePrevious = () => {
    if (currentIndex > 0) {
      setCurrentIndex(currentIndex - 1);
    }
  };

  const handleJump = (e) => {
    e.preventDefault();
    const num = parseInt(jumpInput, 10);
    if (!isNaN(num) && num >= 1 && num <= items.length) {
      setCurrentIndex(num - 1);
    } else {
      showToast(`Enter an issue number between 1 and ${items.length}`, "error");
      setJumpInput(String(currentIndex + 1));
    }
  };

  // 7. Keyboard Shortcuts Handler
  useEffect(() => {
    const handleKeyDown = (e) => {
      const tag = e.target.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;

      if (e.key === "ArrowLeft") {
        e.preventDefault();
        handlePrevious();
      } else if (e.key === "ArrowRight") {
        e.preventDefault();
        if (currentIndex < items.length - 1) setCurrentIndex(currentIndex + 1);
      } else if (e.key.toLowerCase() === "s") {
        e.preventDefault();
        handleSkip();
      } else if (e.key.toLowerCase() === "v") {
        e.preventDefault();
        handleToggleContext();
      } else if (e.key.toLowerCase() === "f") {
        e.preventDefault();
        setShowFpModal(true);
      } else if (e.key.toLowerCase() === "c") {
        e.preventDefault();
        if (notesTextareaRef.current) notesTextareaRef.current.focus();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [currentIndex, items.length, showContext]);

  // Compute batch progress counts
  const totalBatch = items.length || 200;
  const statusValues = Object.values(issueStatuses);
  const confirmedCount = statusValues.filter((s) => s.status === "CONFIRMED").length;
  const falsePositiveCount = statusValues.filter((s) => s.status === "FALSE_POSITIVE").length;
  const reviewedCount = confirmedCount + falsePositiveCount;
  const remainingCount = Math.max(0, totalBatch - reviewedCount);
  const progressPct = totalBatch > 0 ? Math.round((reviewedCount / totalBatch) * 100) : 0;

  const currentStatus = currentItem ? issueStatuses[currentItem.id]?.status || "UNREVIEWED" : "UNREVIEWED";

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[600px] text-slate-300 space-y-4">
        <div className="w-12 h-12 border-4 border-cyan-500/30 border-t-cyan-400 rounded-full animate-spin"></div>
        <p className="text-sm font-mono tracking-wide text-cyan-300">
          Loading 200-Item Deterministic Review Batch...
        </p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-8 max-w-2xl mx-auto bg-red-950/40 border border-red-800 rounded-2xl text-red-200 mt-10">
        <h2 className="text-xl font-bold mb-2 flex items-center gap-2 text-red-400">
          <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
          Review System Error
        </h2>
        <p className="text-sm text-red-300/90">{error}</p>
        <button
          onClick={() => window.location.reload()}
          className="mt-4 px-4 py-2 bg-red-800/60 hover:bg-red-700 text-white rounded-lg text-sm transition-all"
        >
          Retry Connection
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-7xl mx-auto pb-16">
      {/* Toast Notification */}
      {toast && (
        <div
          className={`fixed bottom-6 right-6 z-50 px-5 py-3 rounded-xl shadow-2xl border text-sm font-semibold flex items-center gap-3 transition-all transform animate-bounce ${
            toast.type === "error"
              ? "bg-red-900/90 border-red-600 text-red-100"
              : toast.type === "info"
              ? "bg-cyan-950/90 border-cyan-600 text-cyan-100"
              : "bg-emerald-950/90 border-emerald-600 text-emerald-100"
          }`}
        >
          <span>{toast.message}</span>
        </div>
      )}

      {/* TOP HEADER */}
      <header className="bg-slate-900/80 backdrop-blur-md border border-slate-800 rounded-2xl p-5 shadow-xl relative overflow-hidden">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-xl sm:text-2xl font-black text-white tracking-tight flex items-center gap-2.5">
                <span className="p-1.5 bg-cyan-500/20 text-cyan-400 rounded-lg border border-cyan-500/30">
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" />
                  </svg>
                </span>
                BugTracker — Ground Truth Review
              </h1>
              <span className="px-2.5 py-1 bg-amber-500/15 border border-amber-500/30 text-amber-400 text-xs font-bold uppercase tracking-wider rounded-full flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full bg-amber-400 badge-pulse"></span>
                TEMPORARY DATASET REVIEW TOOL
              </span>
            </div>
            <p className="text-xs sm:text-sm text-slate-400 mt-1">
              Independent human labeling for static analysis candidate issues. Blinded mode active by default.
            </p>
          </div>

          {/* Blinded Mode Switch & Jump Box */}
          <div className="flex flex-wrap items-center gap-3">
            <button
              onClick={() => setBlindedMode(!blindedMode)}
              className={`px-3 py-1.5 rounded-lg border text-xs font-semibold flex items-center gap-2 transition-all ${
                blindedMode
                  ? "bg-cyan-950/60 border-cyan-700 text-cyan-300 hover:bg-cyan-900/60"
                  : "bg-slate-800 border-slate-700 text-slate-400 hover:text-white"
              }`}
              title="Suppress detector baseline predictions to eliminate anchoring bias"
            >
              <span className={`w-2 h-2 rounded-full ${blindedMode ? "bg-cyan-400" : "bg-slate-500"}`}></span>
              Blinded Review Mode: <span className="font-bold">{blindedMode ? "ON" : "OFF"}</span>
            </button>

            {/* Jump to Issue form */}
            <form onSubmit={handleJump} className="flex items-center gap-1.5">
              <span className="text-xs text-slate-400">Jump:</span>
              <input
                type="number"
                min="1"
                max={totalBatch}
                value={jumpInput}
                onChange={(e) => setJumpInput(e.target.value)}
                className="w-16 px-2 py-1 bg-slate-800 border border-slate-700 rounded-lg text-xs font-mono text-white text-center focus:border-cyan-500 outline-none"
              />
              <button
                type="submit"
                className="px-2.5 py-1 bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 text-xs font-semibold rounded-lg"
              >
                Go
              </button>
            </form>
          </div>
        </div>

        {/* PROGRESS METRICS BAR */}
        <div className="mt-5 pt-4 border-t border-slate-800/80 grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
          <div className="bg-slate-950/60 p-2.5 rounded-xl border border-slate-800 flex flex-col">
            <span className="text-slate-400 uppercase font-semibold text-[10px]">Reviewed Progress</span>
            <span className="text-base font-bold text-white font-mono mt-0.5">
              {reviewedCount} <span className="text-slate-500 text-xs font-normal">/ {totalBatch}</span> ({progressPct}%)
            </span>
          </div>

          <div className="bg-slate-950/60 p-2.5 rounded-xl border border-slate-800 flex flex-col">
            <span className="text-emerald-400 uppercase font-semibold text-[10px]">Confirmed Valid</span>
            <span className="text-base font-bold text-emerald-400 font-mono mt-0.5">{confirmedCount}</span>
          </div>

          <div className="bg-slate-950/60 p-2.5 rounded-xl border border-slate-800 flex flex-col">
            <span className="text-rose-400 uppercase font-semibold text-[10px]">False Positives</span>
            <span className="text-base font-bold text-rose-400 font-mono mt-0.5">{falsePositiveCount}</span>
          </div>

          <div className="bg-slate-950/60 p-2.5 rounded-xl border border-slate-800 flex flex-col">
            <span className="text-amber-400 uppercase font-semibold text-[10px]">Remaining Queue</span>
            <span className="text-base font-bold text-amber-400 font-mono mt-0.5">{remainingCount}</span>
          </div>
        </div>

        {/* Linear Progress Bar */}
        <div className="w-full bg-slate-950 rounded-full h-2 mt-3 overflow-hidden border border-slate-800 flex">
          <div
            className="bg-emerald-500 h-full transition-all duration-300"
            style={{ width: `${(confirmedCount / totalBatch) * 100}%` }}
            title={`Confirmed: ${confirmedCount}`}
          />
          <div
            className="bg-rose-500 h-full transition-all duration-300"
            style={{ width: `${(falsePositiveCount / totalBatch) * 100}%` }}
            title={`False Positives: ${falsePositiveCount}`}
          />
        </div>
      </header>

      {/* MAIN TWO-COLUMN WORKFLOW CONTAINER */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* LEFT / CENTER: CURRENT CANDIDATE ISSUE PANEL (8 COLS) */}
        <div className="lg:col-span-8 space-y-6">
          {currentItem ? (
            <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-6 shadow-2xl space-y-6">
              {/* Issue Card Top Bar */}
              <div className="flex flex-wrap items-center justify-between gap-3 pb-4 border-b border-slate-800">
                <div className="flex items-center gap-3">
                  <span className="px-3 py-1 bg-cyan-500/10 border border-cyan-500/30 text-cyan-400 font-mono text-sm font-bold rounded-lg">
                    Issue {currentIndex + 1} of {totalBatch}
                  </span>
                  <span className="text-xs text-slate-500 font-mono">ID: {currentItem.id.slice(0, 12)}...</span>
                </div>

                {/* Status Badge */}
                <div>
                  {currentStatus === "CONFIRMED" && (
                    <span className="px-3 py-1 bg-emerald-500/15 border border-emerald-500/40 text-emerald-400 text-xs font-bold uppercase rounded-lg flex items-center gap-1.5">
                      ✓ Confirmed Valid
                    </span>
                  )}
                  {currentStatus === "FALSE_POSITIVE" && (
                    <span className="px-3 py-1 bg-rose-500/15 border border-rose-500/40 text-rose-400 text-xs font-bold uppercase rounded-lg flex items-center gap-1.5">
                      ✗ False Positive
                    </span>
                  )}
                  {currentStatus === "PARTIAL" && (
                    <span className="px-3 py-1 bg-amber-500/15 border border-amber-500/40 text-amber-400 text-xs font-bold uppercase rounded-lg">
                      Partially Labeled
                    </span>
                  )}
                  {currentStatus === "UNREVIEWED" && (
                    <span className="px-3 py-1 bg-slate-800 border border-slate-700 text-slate-400 text-xs font-bold uppercase rounded-lg">
                      Unreviewed
                    </span>
                  )}
                </div>
              </div>

              {/* GOAL 1: PROMINENT HUMAN-READABLE ISSUE EXPLANATION */}
              <div className="p-5 bg-gradient-to-br from-slate-950 via-[#0C1220] to-[#0A101C] border border-cyan-500/30 rounded-2xl shadow-xl space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] uppercase font-black tracking-widest text-cyan-400 flex items-center gap-2">
                    <svg className="w-4 h-4 text-cyan-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                    ISSUE EXPLANATION
                  </span>
                  <span className="px-2.5 py-0.5 bg-cyan-500/10 border border-cyan-500/20 text-cyan-300 text-xs font-semibold rounded-full">
                    {ruleInfo?.technicalCategory || "Static Analysis"}
                  </span>
                </div>

                <h2 className="text-lg sm:text-xl font-black text-white tracking-tight">
                  {ruleInfo?.title || "Potential Code Issue"}
                </h2>

                <p className="text-sm text-slate-300 leading-relaxed">
                  {ruleInfo?.explanation || "This code was flagged by the static analyzer because it matches a potentially problematic pattern."}
                </p>

                {/* Secondary Technical Metadata Badges */}
                <div className="pt-2 border-t border-slate-800/80 flex flex-wrap items-center gap-3 text-xs text-slate-400 font-mono">
                  <span>
                    Technical Rule ID: <strong className="text-slate-300 bg-slate-800/80 px-2 py-0.5 rounded border border-slate-700 font-mono">{ruleInfo?.technicalRuleId || currentItem.rule_id}</strong>
                  </span>
                  {currentItem.issue_type && (
                    <span>
                      Pattern: <span className="text-slate-300">{currentItem.issue_type}</span>
                    </span>
                  )}
                </div>
              </div>

              {/* Repository & File Location Grid */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
                <div className="bg-slate-950/60 p-3 rounded-xl border border-slate-800">
                  <span className="text-slate-500 block uppercase font-semibold text-[10px]">Repository</span>
                  <span className="text-slate-200 font-semibold truncate block mt-0.5">
                    {currentItem.repository_name || "Unknown"}
                  </span>
                </div>

                <div className="bg-slate-950/60 p-3 rounded-xl border border-slate-800">
                  <span className="text-slate-500 block uppercase font-semibold text-[10px]">Language</span>
                  <span className="text-cyan-400 font-bold block mt-0.5">{currentItem.language || "N/A"}</span>
                </div>

                <div className="bg-slate-950/60 p-3 rounded-xl border border-slate-800 col-span-2">
                  <span className="text-slate-500 block uppercase font-semibold text-[10px]">File Location</span>
                  <div className="flex items-center justify-between text-slate-200 font-mono truncate mt-0.5">
                    <span className="truncate">{currentItem.file_path}</span>
                    <span className="text-cyan-400 font-bold ml-2 shrink-0">Line {currentItem.line_number || "N/A"}</span>
                  </div>
                </div>
              </div>

              {/* GOAL 2: ALWAYS SHOW THE STORED POSTGRESQL CODE SNIPPET (PRIMARY) */}
              <section className="flagged-code-section space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-black uppercase tracking-wider text-slate-300 flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full bg-cyan-400"></span>
                    FLAGGED CODE (Persisted PostgreSQL Record)
                  </span>
                  {hasValidSnippet && (
                    <button
                      onClick={() => {
                        navigator.clipboard.writeText(currentItem.code_snippet);
                        showToast("Code snippet copied to clipboard");
                      }}
                      className="text-xs text-cyan-400 hover:text-cyan-300 font-medium"
                    >
                      Copy Snippet
                    </button>
                  )}
                </div>
                <pre className="p-4 bg-[#050810] border border-slate-800 rounded-xl text-slate-100 review-code-editor text-sm overflow-x-auto shadow-inner leading-relaxed border-l-4 border-l-cyan-500 font-mono">
                  <code>
                    {hasValidSnippet
                      ? currentItem.code_snippet
                      : "No code snippet was persisted for this candidate issue."}
                  </code>
                </pre>
              </section>

              {/* GOAL 3: OPTIONAL SURROUNDING SOURCE CONTEXT SECTION */}
              <div className="space-y-3 pt-2">
                <div className="flex items-center gap-3">
                  <button
                    onClick={handleToggleContext}
                    className={`px-4 py-2.5 rounded-xl text-xs font-bold uppercase tracking-wider flex items-center gap-2 transition-all ${
                      showContext
                        ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 shadow-lg shadow-cyan-500/10"
                        : "bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700"
                    }`}
                  >
                    <svg className="w-4 h-4 text-cyan-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                    </svg>
                    {showContext ? "Hide Source Context [V]" : "View Full Source Context [V]"}
                  </button>

                  <button
                    onClick={() => setShowEvidence(!showEvidence)}
                    className="px-3.5 py-2.5 bg-slate-800/80 hover:bg-slate-700 text-slate-400 hover:text-slate-200 border border-slate-700/80 rounded-xl text-xs font-medium transition-all"
                  >
                    {showEvidence ? "Hide AST Evidence" : "Show Technical Details"}
                  </button>
                </div>

                {/* Optional Source Context Drawer */}
                {showContext && (
                  <div className="p-4 bg-[#050810] border border-cyan-500/30 rounded-xl shadow-2xl space-y-2">
                    <div className="flex items-center justify-between text-xs text-cyan-400 font-mono pb-2 border-b border-slate-800">
                      <span>Source Context (Surrounding Lines)</span>
                      {contextData?.total_lines && (
                        <span>
                          Lines {contextData.start_line}-{contextData.end_line} of {contextData.total_lines}
                        </span>
                      )}
                    </div>

                    {loadingContext ? (
                      <div className="py-6 text-center text-xs font-mono text-cyan-300">
                        Retrieving repository source context...
                      </div>
                    ) : contextData?.lines && contextData.lines.length > 0 ? (
                      <div className="review-code-editor text-xs font-mono overflow-x-auto max-h-96 space-y-0.5 py-1">
                        {contextData.lines.map((line) => (
                          <div
                            key={line.line_number}
                            className={`flex items-start px-2 py-0.5 rounded transition-colors ${
                              line.is_target ? "source-line-highlight" : "source-line-normal"
                            }`}
                          >
                            <span className="w-6 text-slate-500 font-bold select-none text-center">
                              {line.is_target ? ">" : " "}
                            </span>
                            <span className="w-12 text-slate-500 select-none text-right pr-3 font-mono">
                              {line.line_number}
                            </span>
                            <span className="text-slate-200 whitespace-pre-wrap flex-1">{line.content}</span>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <div className="p-4 bg-slate-950/90 border border-slate-800 rounded-xl text-xs space-y-1.5">
                        <span className="text-amber-400 font-bold block uppercase tracking-wider text-[11px]">
                          Source Context Unavailable
                        </span>
                        <p className="text-slate-300">
                          The original repository source file is not currently available on disk.
                        </p>
                        {hasValidSnippet && (
                          <p className="text-slate-400 text-[11px]">
                            The persisted candidate snippet above is still available for review.
                          </p>
                        )}
                      </div>
                    )}
                  </div>
                )}

                {/* Collapsible AST Evidence */}
                {showEvidence && (
                  <div className="p-4 bg-slate-950 border border-slate-800 rounded-xl text-xs font-mono space-y-2">
                    <span className="text-slate-400 font-bold block">AST Evidence (Static Analysis):</span>
                    <pre className="text-slate-300 overflow-x-auto max-h-60">
                      {JSON.stringify(currentItem.evidence || {}, null, 2)}
                    </pre>
                  </div>
                )}
              </div>

              {/* UNBLINDED REFERENCE CARD (Revealed only if Blinded Mode is OFF) */}
              {!blindedMode && (
                <div className="p-3.5 bg-slate-950/80 border border-slate-800 rounded-xl text-xs space-y-1">
                  <span className="text-[10px] uppercase font-bold text-slate-500 tracking-wider block">
                    Detector Baseline Prediction (Reference Only)
                  </span>
                  <div className="flex gap-4 font-mono text-slate-300">
                    <span>
                      Severity: <strong className="text-amber-400">{currentItem.detector_severity || currentItem.severity || "N/A"}</strong>
                    </span>
                    <span>
                      Urgency: <strong className="text-amber-400">{currentItem.detector_urgency || currentItem.urgency || "N/A"}</strong>
                    </span>
                  </div>
                </div>
              )}

              {/* REVIEW DECISION SECTION */}
              <div className="pt-6 border-t border-slate-800 space-y-6">
                <h3 className="text-sm font-bold uppercase tracking-wider text-cyan-400 flex items-center gap-2">
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                  </svg>
                  Human Ground-Truth Review Decision
                </h3>

                {/* 1. SEVERITY SELECTION */}
                <div className="space-y-2">
                  <label className="text-xs font-semibold text-slate-300 block">
                    1. Assign Ground-Truth Severity: <span className="text-red-400">*</span>
                  </label>
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5">
                    {SEVERITY_OPTIONS.map((opt) => {
                      const isSelected = selectedSeverity === opt.id;
                      return (
                        <button
                          key={opt.id}
                          type="button"
                          onClick={() => setSelectedSeverity(opt.id)}
                          className={`p-3 rounded-xl border font-bold text-xs uppercase tracking-wider transition-all flex items-center justify-center gap-2 ${
                            isSelected
                              ? `bg-gradient-to-r ${opt.color} text-white shadow-lg ${opt.border} ring-2 ring-white/20 scale-[1.02]`
                              : "bg-slate-950 hover:bg-slate-800/80 border-slate-800 text-slate-400"
                          }`}
                        >
                          {isSelected && <span>✓</span>}
                          {opt.label}
                        </button>
                      );
                    })}
                  </div>
                </div>

                {/* 2. PRIORITY SELECTION */}
                <div className="space-y-2">
                  <label className="text-xs font-semibold text-slate-300 block">
                    2. Assign Ground-Truth Priority: <span className="text-red-400">*</span>
                  </label>
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5">
                    {PRIORITY_OPTIONS.map((opt) => {
                      const isSelected = selectedPriority === opt.id;
                      return (
                        <button
                          key={opt.id}
                          type="button"
                          onClick={() => setSelectedPriority(opt.id)}
                          className={`p-3 rounded-xl border font-bold text-xs uppercase tracking-wider transition-all flex items-center justify-center gap-2 ${
                            isSelected
                              ? `bg-gradient-to-r ${opt.color} text-white shadow-lg ${opt.border} ring-2 ring-white/20 scale-[1.02]`
                              : "bg-slate-950 hover:bg-slate-800/80 border-slate-800 text-slate-400"
                          }`}
                        >
                          {isSelected && <span>✓</span>}
                          {opt.label}
                        </button>
                      );
                    })}
                  </div>
                </div>

                {/* 3. REVIEWER NOTES */}
                <div className="space-y-2">
                  <label className="text-xs font-semibold text-slate-300 block">
                    3. Reviewer Rationale Notes: <span className="text-red-400">*</span>
                  </label>
                  <textarea
                    ref={notesTextareaRef}
                    rows="3"
                    value={reviewerNotes}
                    onChange={(e) => setReviewerNotes(e.target.value)}
                    placeholder="Enter technical justification for why this severity and priority were assigned..."
                    className="w-full p-3.5 bg-slate-950 border border-slate-800 rounded-xl text-xs text-slate-200 placeholder-slate-600 focus:border-cyan-500 outline-none leading-relaxed"
                  />
                </div>

                {/* ACTION BUTTONS: CONFIRM, FALSE POSITIVE, SKIP */}
                <div className="flex flex-wrap items-center justify-between gap-3 pt-3">
                  <div className="flex items-center gap-3">
                    <button
                      type="button"
                      onClick={handleConfirmValid}
                      disabled={isSaving || !selectedSeverity || !selectedPriority || !reviewerNotes.trim()}
                      className={`px-5 py-3 rounded-xl font-bold text-xs uppercase tracking-wider flex items-center gap-2 shadow-lg transition-all ${
                        selectedSeverity && selectedPriority && reviewerNotes.trim() && !isSaving
                          ? "bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white shadow-emerald-900/30 cursor-pointer scale-[1.01]"
                          : "bg-slate-800 text-slate-500 border border-slate-700 cursor-not-allowed opacity-60"
                      }`}
                    >
                      {isSaving ? "Saving Decision..." : "✓ Confirm & Save [C]"}
                    </button>

                    <button
                      type="button"
                      onClick={() => setShowFpModal(true)}
                      className="px-4 py-3 bg-rose-950/50 hover:bg-rose-900/70 border border-rose-800/80 text-rose-300 hover:text-white rounded-xl font-bold text-xs uppercase tracking-wider transition-all"
                    >
                      ✗ Mark False Positive [F]
                    </button>
                  </div>

                  {/* Navigation controls */}
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={handlePrevious}
                      disabled={currentIndex === 0}
                      className="px-3.5 py-2.5 bg-slate-800 hover:bg-slate-700 disabled:opacity-40 disabled:hover:bg-slate-800 text-slate-200 rounded-xl text-xs font-semibold"
                    >
                      ← Previous
                    </button>
                    <button
                      type="button"
                      onClick={handleSkip}
                      className="px-3.5 py-2.5 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-xl text-xs font-semibold"
                    >
                      Skip [S]
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        if (currentIndex < items.length - 1) setCurrentIndex(currentIndex + 1);
                      }}
                      disabled={currentIndex === items.length - 1}
                      className="px-3.5 py-2.5 bg-slate-800 hover:bg-slate-700 disabled:opacity-40 disabled:hover:bg-slate-800 text-slate-200 rounded-xl text-xs font-semibold"
                    >
                      Next →
                    </button>
                  </div>
                </div>
              </div>
            </div>
          ) : (
            <div className="p-12 text-center text-slate-400 bg-slate-900/40 rounded-2xl border border-slate-800">
              No candidate issues in batch.
            </div>
          )}
        </div>

        {/* RIGHT: PROGRESS, CLASS BALANCE & 4X4 MATRIX (4 COLS) */}
        <aside className="lg:col-span-4 space-y-6">
          {/* Progress & Batch Scorecard */}
          <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-5 shadow-xl space-y-4">
            <h2 className="text-xs font-black uppercase tracking-wider text-slate-400 flex items-center justify-between">
              <span>Review Batch Summary</span>
              <span className="text-cyan-400 font-mono">{progressPct}%</span>
            </h2>

            <div className="space-y-2 text-xs">
              <div className="flex justify-between py-1 border-b border-slate-800">
                <span className="text-slate-400">Total Batch Size:</span>
                <strong className="text-white font-mono">{totalBatch}</strong>
              </div>
              <div className="flex justify-between py-1 border-b border-slate-800">
                <span className="text-emerald-400">Confirmed Valid:</span>
                <strong className="text-emerald-400 font-mono">{confirmedCount}</strong>
              </div>
              <div className="flex justify-between py-1 border-b border-slate-800">
                <span className="text-rose-400">False Positives:</span>
                <strong className="text-rose-400 font-mono">{falsePositiveCount}</strong>
              </div>
              <div className="flex justify-between py-1 border-b border-slate-800">
                <span className="text-amber-400">Unreviewed / Remaining:</span>
                <strong className="text-amber-400 font-mono">{remainingCount}</strong>
              </div>
            </div>
          </div>

          {/* Severity Class Distribution */}
          <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-5 shadow-xl space-y-3">
            <h2 className="text-xs font-black uppercase tracking-wider text-slate-400">
              Verified Severity Balance
            </h2>
            <div className="space-y-2">
              {SEVERITY_OPTIONS.map((sev) => {
                const count = stats?.severity_distribution?.[sev.id] || 0;
                const targetMet = count >= 30;
                return (
                  <div key={sev.id} className="flex items-center justify-between text-xs">
                    <span className={`font-semibold ${sev.text}`}>{sev.label}</span>
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-slate-300">{count}</span>
                      <span
                        className={`text-[10px] font-bold px-1.5 py-0.2 rounded ${
                          targetMet
                            ? "bg-emerald-500/20 text-emerald-400"
                            : "bg-slate-800 text-slate-400"
                        }`}
                      >
                        {targetMet ? "MET" : `${count}/30`}
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Priority Class Distribution */}
          <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-5 shadow-xl space-y-3">
            <h2 className="text-xs font-black uppercase tracking-wider text-slate-400">
              Verified Priority Balance
            </h2>
            <div className="space-y-2">
              {PRIORITY_OPTIONS.map((prio) => {
                const count = stats?.priority_distribution?.[prio.id] || 0;
                const targetMet = count >= 30;
                return (
                  <div key={prio.id} className="flex items-center justify-between text-xs">
                    <span className={`font-semibold ${prio.text}`}>{prio.label}</span>
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-slate-300">{count}</span>
                      <span
                        className={`text-[10px] font-bold px-1.5 py-0.2 rounded ${
                          targetMet
                            ? "bg-emerald-500/20 text-emerald-400"
                            : "bg-slate-800 text-slate-400"
                        }`}
                      >
                        {targetMet ? "MET" : `${count}/30`}
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* 4x4 Cross-Tab Matrix */}
          <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-5 shadow-xl space-y-3">
            <h2 className="text-xs font-black uppercase tracking-wider text-slate-400">
              Severity × Priority Matrix (4×4)
            </h2>
            <div className="overflow-x-auto">
              <table className="w-full text-center text-xs font-mono">
                <thead>
                  <tr className="text-slate-500 border-b border-slate-800">
                    <th className="pb-1.5 text-left text-[10px]">Sev \ Prio</th>
                    <th className="pb-1.5 text-[10px]">P1</th>
                    <th className="pb-1.5 text-[10px]">P2</th>
                    <th className="pb-1.5 text-[10px]">P3</th>
                    <th className="pb-1.5 text-[10px]">P4</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60">
                  {["critical", "high", "medium", "low"].map((s) => (
                    <tr key={s} className="hover:bg-slate-800/30">
                      <td className="py-1.5 text-left text-slate-400 capitalize font-sans text-xs">
                        {s}
                      </td>
                      {["p1", "p2", "p3", "p4"].map((p) => {
                        const cellVal = stats?.crosstab?.[`${s} + ${p}`] || 0;
                        return (
                          <td
                            key={p}
                            className={`py-1.5 ${
                              cellVal > 0 ? "text-cyan-400 font-bold bg-cyan-950/20" : "text-slate-600"
                            }`}
                          >
                            {cellVal}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Mini 200-Item Navigator Grid */}
          <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-5 shadow-xl space-y-3">
            <h2 className="text-xs font-black uppercase tracking-wider text-slate-400 flex items-center justify-between">
              <span>Batch Navigator (200)</span>
              <span className="text-[10px] text-slate-500">Click to Jump</span>
            </h2>
            <div className="grid grid-cols-10 gap-1.5 max-h-48 overflow-y-auto p-1 bg-slate-950/60 rounded-xl border border-slate-800/80">
              {items.map((itm, idx) => {
                const st = issueStatuses[itm.id]?.status || "UNREVIEWED";
                const isCurrent = idx === currentIndex;
                let bg = "bg-slate-800 text-slate-500 hover:bg-slate-700";
                if (st === "CONFIRMED") bg = "bg-emerald-600 text-white";
                else if (st === "FALSE_POSITIVE") bg = "bg-rose-600 text-white";
                else if (st === "PARTIAL") bg = "bg-amber-600 text-white";

                return (
                  <button
                    key={itm.id}
                    onClick={() => setCurrentIndex(idx)}
                    title={`#${idx + 1} - ${st}`}
                    className={`h-6 rounded text-[10px] font-mono font-bold flex items-center justify-center transition-all ${bg} ${
                      isCurrent ? "ring-2 ring-cyan-400 scale-110 z-10" : ""
                    }`}
                  >
                    {idx + 1}
                  </button>
                );
              })}
            </div>
          </div>
        </aside>
      </div>

      {/* FALSE POSITIVE MODAL */}
      {showFpModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm">
          <div className="bg-slate-900 border border-rose-800/80 rounded-2xl max-w-lg w-full p-6 shadow-2xl space-y-5 animate-in fade-in zoom-in duration-150">
            <div className="flex items-center gap-3 text-rose-400">
              <span className="p-2 bg-rose-500/20 rounded-xl border border-rose-500/30">
                <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                </svg>
              </span>
              <div>
                <h3 className="text-lg font-bold text-white">Mark as False Positive</h3>
                <p className="text-xs text-rose-300/80">
                  Candidate issue will be excluded from the ML training dataset.
                </p>
              </div>
            </div>

            <div className="space-y-2">
              <label className="text-xs font-semibold text-slate-300 block">
                Why is this finding a false positive? <span className="text-rose-400">*</span>
              </label>
              <textarea
                rows="4"
                value={fpExplanation}
                onChange={(e) => setFpExplanation(e.target.value)}
                placeholder="e.g. The variable is verified as non-zero by an upstream guard statement on line 42..."
                className="w-full p-3 bg-slate-950 border border-slate-800 rounded-xl text-xs text-slate-200 placeholder-slate-600 focus:border-rose-500 outline-none leading-relaxed"
                autoFocus
              />
            </div>

            <div className="flex justify-end items-center gap-3 pt-2">
              <button
                type="button"
                onClick={() => {
                  setShowFpModal(false);
                  setFpExplanation("");
                }}
                className="px-4 py-2.5 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-xl text-xs font-semibold"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleConfirmFalsePositive}
                disabled={!fpExplanation.trim() || isSaving}
                className={`px-5 py-2.5 rounded-xl font-bold text-xs uppercase tracking-wider text-white shadow-lg transition-all ${
                  fpExplanation.trim() && !isSaving
                    ? "bg-rose-600 hover:bg-rose-500 shadow-rose-900/40 cursor-pointer"
                    : "bg-slate-800 text-slate-500 cursor-not-allowed opacity-60"
                }`}
              >
                {isSaving ? "Saving..." : "Confirm False Positive"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
