/*
// src/components/Tabs/TabAiArchitecture.jsx - Tab 2: AI Codebase Architecture & Dynamic File Cards
import React, { useState, useMemo, useEffect, useCallback } from "react";
import { useBugTracker } from "../../useBugTracker.jsx";
import { apiService } from "../../api.js";

// ---------------------------------------------------------------------------
// Map a backend ArchitectureTopologyResponse → the shape the existing UI uses
// ---------------------------------------------------------------------------
function mapBackendToUiSummary(data) {
  // Tech stack: primary technologies shown prominently as badge strings
  const techStack = (data.primary_technologies || []).map((t) =>
    t.version ? `${t.name} ${t.version}` : t.name
  );

  // Main components
  const mainComponents = (data.components || []).map((c) => ({
    name: c.name,
    description: c.description || c.root_path || "",
  }));

  // Risks derived from health_assessment (single block → one risk item)
  const potentialRisks = data.summary?.health_assessment
    ? [{ title: "Health Assessment", severity: "Info", description: data.summary.health_assessment }]
    : [];

  // Recommendations: architecture_overview as a single item
  const recommendations = data.summary?.architecture_overview
    ? [data.summary.architecture_overview]
    : [];

  // File summaries from all components' source_files + uncategorized_files
  const allSourceFiles = [
    ...(data.components || []).flatMap((c) => c.source_files || []),
    ...(data.uncategorized_files || []),
  ];
  const fileSummaries = allSourceFiles.map((sf) => ({
    id: sf.id,
    file: sf.file_path || sf.file_name,
    role: sf.role || "Source File",
    intent: sf.intent || "",
    status: sf.is_supported ? "Clean" : "Documentation",
    statusColor: sf.is_supported
      ? "text-emerald-400 border-emerald-500/30 bg-emerald-500/10"
      : "text-slate-400 border-slate-600/30 bg-slate-500/10",
    lines: sf.line_count || 0,
    language: sf.language || "Unknown",
  }));

  return {
    intent: data.summary?.intent || "",
    techStack,
    architectureOverview: data.summary?.architecture_overview || "",
    healthAssessment: data.summary?.health_assessment || "",
    mainComponents,
    potentialRisks,
    recommendations,
    fileSummaries,
    // metadata for the status badge
    _totalTechnologies: data.total_technologies || 0,
    _totalPrimary: data.total_primary_technologies || 0,
    _totalComponents: data.total_components || 0,
    _totalFiles: data.total_source_files || 0,
    _parserVersion: data.summary?.parser_version || null,
  };
}

export default function TabAiArchitecture() {
  const {
    aiSummary,
    aiSearchQuery,
    setAiSearchQuery,
    selectedFileFilter,
    setSelectedFileFilter,
    setActiveTab,
    setActiveDrawerBug,
    bugs,
    currentRepositoryId,
  } = useBugTracker();

  const [selectedFileModal, setSelectedFileModal] = useState(null);

  // Backend architecture data state
  const [archData, setArchData] = useState(null);       // mapped UI summary from backend
  const [archLoading, setArchLoading] = useState(false);
  const [archError, setArchError] = useState(null);     // null | { message, status }

  // Fetch architecture for a known repository ID.
  const fetchArchitecture = useCallback(async (repoId) => {
    if (!repoId) return;
    setArchLoading(true);
    setArchError(null);
    const res = await apiService.getRepositoryArchitecture(repoId);
    setArchLoading(false);
    if (res.live && res.data) {
      setArchData(mapBackendToUiSummary(res.data));
    } else {
      setArchData(null);
      setArchError({ message: res.error || "Architecture data not yet available.", status: res.status });
    }
  }, []);

  useEffect(() => {
    // Always clear stale data before resolving the target repository,
    // so we never show a previous repository's architecture while loading.
    setArchData(null);
    setArchError(null);

    if (currentRepositoryId) {
      // Case 1: a repository was scanned through the frontend this session — use it directly.
      fetchArchitecture(currentRepositoryId);
    } else {
      // Case 2 (temporary fallback): no frontend scan yet.
      // Fetch the repository list and use the most recently created repository.
      // This covers repositories created/analyzed via Swagger or the backend directly.
      (async () => {
        const listRes = await apiService.getRepositories();
        const repos = listRes.data; // already guaranteed to be an array
        if (repos.length === 0) {
          // No repositories at all — stay on demo data.
          return;
        }
        // list_all() orders by created_at DESC, so index 0 is the latest.
        const latestId = repos[0].id;
        await fetchArchitecture(latestId);
      })();
    }
  }, [currentRepositoryId, fetchArchitecture]);

  // Use backend data when available; fall back to context aiSummary (mock/GitHub)
  const displaySummary = archData || aiSummary;

  // Dynamic filter for file cards
  const filteredFiles = useMemo(() => {
    const fileList = displaySummary?.fileSummaries || [];
    const query = aiSearchQuery.toLowerCase().trim();

    return fileList.filter((f) => {
      const matchesSearch =
        !query ||
        f.file.toLowerCase().includes(query) ||
        f.role.toLowerCase().includes(query) ||
        f.intent.toLowerCase().includes(query) ||
        f.language.toLowerCase().includes(query) ||
        f.status.toLowerCase().includes(query);

      const matchesCategory =
        selectedFileFilter === "All" ||
        (selectedFileFilter === "Risks" && f.status !== "Clean" && f.status !== "Documentation") ||
        (selectedFileFilter === "Clean" && f.status === "Clean") ||
        f.status === selectedFileFilter;

      return matchesSearch && matchesCategory;
    });
  }, [displaySummary, aiSearchQuery, selectedFileFilter]);

  const handleCardClick = (fileItem) => {
    // Check if there is an associated bug for this file
    const matchedBug = bugs.find((b) => fileItem.file.includes(b.file) || b.file.includes(fileItem.file));
    if (matchedBug) {
      setActiveTab("bugs");
      setActiveDrawerBug(matchedBug);
    } else {
      setSelectedFileModal(fileItem);
    }
  };

  return (
    <div className="space-y-6 animate-fade-in max-w-7xl mx-auto">
      {/* Header Overview Card * /}
      <div className="bg-[#131B2E] border border-slate-800 rounded-2xl p-6 sm:p-8 space-y-6 shadow-xl relative">
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 border-b border-slate-800/80 pb-5">
          <div>
            <span className="text-[11px] font-mono uppercase tracking-wider text-cyan-400 font-semibold bg-cyan-500/10 px-2.5 py-1 rounded-full border border-cyan-500/20">
              Tab 2 • Code Intelligence
            </span>
            <h2 className="text-xl sm:text-2xl font-bold text-white tracking-tight mt-2">
              AI Codebase Architecture & Topology
            </h2>
            <p className="text-xs text-slate-400 mt-1">
              Semantic NLP summary, detected technology stacks, subsystem boundaries, and file decomposition.
            </p>
          </div>

          <div className="flex items-center space-x-2 text-xs text-slate-400 bg-[#0B0F17] px-3 py-1.5 rounded-xl border border-slate-800">
            <span className="w-2 h-2 rounded-full bg-cyan-400 animate-pulse"></span>
            <span>{archData?._parserVersion || "AST Semantic Parser v2.4"}</span>
          </div>
        </div>

        {/* Loading state * /}
        {archLoading && (
          <div className="flex items-center gap-2 text-xs text-cyan-400 bg-cyan-500/5 border border-cyan-500/20 rounded-xl px-4 py-2.5">
            <span className="w-2 h-2 rounded-full bg-cyan-400 animate-pulse"></span>
            Loading architecture data for this repository…
          </div>
        )}

        {/* Error / no-analysis-yet state (only shown when a backend repo was resolved) * /}
        {!archLoading && archError && (
          <div className="text-xs text-amber-400 bg-amber-500/5 border border-amber-500/20 rounded-xl px-4 py-2.5">
            {archError.status === 404
              ? "No completed analysis found for this repository yet. Run a scan first."
              : archError.message}
          </div>
        )}

        {/* System Intent & Architecture Summary * /}
        <div className="space-y-4">
          <div>
            <h3 className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-1.5">
              Identified System Intent & Architecture
            </h3>
            <p className="text-xs sm:text-sm text-slate-200 leading-relaxed bg-[#0B0F17]/80 border border-slate-800 rounded-xl p-4">
              {displaySummary?.intent || "Enterprise microservice platform orchestrating authentication, checkout workflows, and WebSocket telemetry."}
            </p>
          </div>

          {/* Tech Stack Badges * /}
          <div>
            <h3 className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-2">
              Detected Technology Stack
            </h3>
            <div className="flex flex-wrap gap-2">
              {(displaySummary?.techStack || []).map((tech, idx) => (
                <span
                  key={idx}
                  className="bg-[#0B0F17] border border-cyan-500/30 text-cyan-300 font-mono text-xs px-3 py-1 rounded-lg flex items-center gap-1.5 shadow-xs"
                >
                  <span className="w-1.5 h-1.5 rounded-full bg-cyan-400"></span>
                  {tech}
                </span>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Main Subsystems & Architectural Risks Grid * /}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Main Subsystems * /}
        <div className="bg-[#131B2E] border border-slate-800 rounded-2xl p-6 space-y-4 shadow-lg">
          <h3 className="text-sm font-bold text-white flex items-center gap-2">
            <span>🧩</span> Main Architecture Components
          </h3>
          <div className="space-y-2.5">
            {(displaySummary?.mainComponents || []).map((comp, idx) => (
              <div
                key={idx}
                className="bg-[#0B0F17] border border-slate-800/80 rounded-xl p-3.5 space-y-1"
              >
                <div className="text-xs font-bold text-white flex items-center justify-between">
                  <span>{comp.name}</span>
                  <span className="text-[10px] font-mono text-slate-500">Core Subsystem</span>
                </div>
                <p className="text-xs text-slate-400">{comp.description}</p>
              </div>
            ))}
          </div>
        </div>

        {/* Potential Architectural Risks & Recommendations * /}
        <div className="bg-[#131B2E] border border-slate-800 rounded-2xl p-6 space-y-4 shadow-lg flex flex-col justify-between">
          <div className="space-y-4">
            <h3 className="text-sm font-bold text-white flex items-center gap-2">
              <span>⚠️</span> Potential Risks & Hotspots
            </h3>
            <div className="space-y-2.5">
              {(displaySummary?.potentialRisks || []).map((risk, idx) => (
                <div
                  key={idx}
                  className="bg-[#0B0F17] border border-red-500/20 rounded-xl p-3.5 space-y-1"
                >
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-red-300">{risk.title}</span>
                    <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-red-500/20 text-red-400 border border-red-500/30">
                      {risk.severity}
                    </span>
                  </div>
                  <p className="text-xs text-slate-400">{risk.description}</p>
                </div>
              ))}
            </div>
          </div>

          {/* Recommendations Banner * /}
          <div className="bg-[#0B0F17] border border-cyan-500/20 rounded-xl p-4 space-y-2 mt-4">
            <span className="text-[10px] font-bold text-cyan-400 uppercase tracking-wider block">
              💡 Primary AI Remediation Strategy
            </span>
            <ul className="text-xs text-slate-300 space-y-1.5 list-disc pl-4">
              {(displaySummary?.recommendations || []).slice(0, 3).map((rec, idx) => (
                <li key={idx}>{rec}</li>
              ))}
            </ul>
          </div>
        </div>
      </div>

      {/* File Decomposition & Dynamic Search / Filter Grid * /}
      <div className="bg-[#131B2E] border border-slate-800 rounded-2xl p-6 sm:p-8 space-y-6 shadow-xl">
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 border-b border-slate-800/80 pb-4">
          <div>
            <h3 className="text-base font-bold text-white">
              Decomposed Source File Cards ({filteredFiles.length})
            </h3>
            <p className="text-xs text-slate-400">
              Click any card to inspect full AST role, purpose, and associated security vulnerabilities.
            </p>
          </div>

          {/* Category Filter Chips * /}
          <div className="flex flex-wrap gap-1.5">
            {["All", "Risks", "Clean"].map((cat) => (
              <button
                key={cat}
                type="button"
                onClick={() => setSelectedFileFilter(cat)}
                className={`px-3 py-1 rounded-lg text-xs font-semibold transition-colors cursor-pointer ${
                  selectedFileFilter === cat
                    ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/30"
                    : "bg-[#0B0F17] text-slate-400 hover:text-white border border-slate-800"
                }`}
              >
                {cat}
              </button>
            ))}
          </div>
        </div>

        {/* Real-time Search Field * /}
        <div className="relative">
          <svg
            className="w-4 h-4 text-cyan-400 absolute left-3.5 top-3"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
          <input
            type="text"
            value={aiSearchQuery}
            onChange={(e) => setAiSearchQuery(e.target.value)}
            placeholder="Real-time filter by file name, intent, language, or risk status..."
            className="w-full bg-[#0B0F17] border border-slate-700 rounded-xl pl-10 pr-10 py-2.5 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-cyan-400 font-mono transition-colors"
          />
          {aiSearchQuery && (
            <button
              onClick={() => setAiSearchQuery("")}
              className="absolute right-3 top-2.5 text-slate-400 hover:text-white text-xs"
            >
              ✕
            </button>
          )}
        </div>

        {/* Grid of File Cards * /}
        {filteredFiles.length === 0 ? (
          <div className="text-center py-10 text-slate-400 space-y-1">
            <p>No file cards matched "{aiSearchQuery}"</p>
            <p className="text-[11px] text-slate-500">Try searching for "queryBuilder", "auth", "deploy", or clear filter.</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {filteredFiles.map((fileItem) => {
              const hasBug = bugs.some((b) => fileItem.file.includes(b.file) || b.file.includes(fileItem.file));
              return (
                <div
                  key={fileItem.id || fileItem.file}
                  onClick={() => handleCardClick(fileItem)}
                  className="bg-[#0B0F17] hover:bg-slate-800/80 border border-slate-800 hover:border-cyan-500/40 rounded-xl p-4.5 space-y-3 cursor-pointer transition-all flex flex-col justify-between group shadow-sm"
                >
                  <div className="space-y-2">
                    <div className="flex items-start justify-between gap-2">
                      <span className="font-mono text-xs font-bold text-white group-hover:text-cyan-300 transition-colors truncate">
                        {fileItem.file}
                      </span>
                      <span
                        className={`text-[10px] font-semibold px-2 py-0.5 rounded border shrink-0 ${fileItem.statusColor}`}
                      >
                        {fileItem.status}
                      </span>
                    </div>

                    <div className="space-y-1 text-xs">
                      <div>
                        <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Role</span>
                        <p className="text-slate-300 line-clamp-2 leading-relaxed">{fileItem.role}</p>
                      </div>
                      <div>
                        <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Intent</span>
                        <p className="text-slate-400 line-clamp-2 leading-relaxed">{fileItem.intent}</p>
                      </div>
                    </div>
                  </div>

                  <div className="pt-2 border-t border-slate-800/80 flex items-center justify-between text-[11px] text-slate-500">
                    <span className="font-mono bg-slate-900 px-2 py-0.5 rounded border border-slate-800 text-slate-400">
                      {fileItem.language} • {fileItem.lines} lines
                    </span>
                    <span className="text-cyan-400 group-hover:translate-x-0.5 transition-transform font-medium">
                      {hasBug ? "Inspect Bug →" : "View Info →"}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* File Info Modal if file doesn't have a direct bug * /}
      {selectedFileModal && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-xs animate-fade-in"
          onClick={() => setSelectedFileModal(null)}
        >
          <div
            className="bg-[#131B2E] border border-slate-800 rounded-2xl max-w-lg w-full p-6 space-y-4 shadow-2xl relative"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-start justify-between border-b border-slate-800 pb-3">
              <div>
                <h3 className="text-base font-bold text-white font-mono">{selectedFileModal.file}</h3>
                <span className="text-xs text-slate-400">{selectedFileModal.language} • {selectedFileModal.lines} lines</span>
              </div>
              <button
                onClick={() => setSelectedFileModal(null)}
                className="text-slate-400 hover:text-white p-1 rounded-lg hover:bg-slate-800"
              >
                ✕
              </button>
            </div>

            <div className="space-y-3 text-xs">
              <div className="bg-[#0B0F17] p-3 rounded-xl border border-slate-800">
                <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block mb-1">Architectural Role</span>
                <p className="text-slate-200">{selectedFileModal.role}</p>
              </div>
              <div className="bg-[#0B0F17] p-3 rounded-xl border border-slate-800">
                <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block mb-1">Functional Intent</span>
                <p className="text-slate-300">{selectedFileModal.intent}</p>
              </div>
              <div className="flex justify-between items-center bg-[#0B0F17] p-3 rounded-xl border border-slate-800">
                <span className="text-slate-400">Security Status:</span>
                <span className={`text-xs font-semibold px-2.5 py-0.5 rounded border ${selectedFileModal.statusColor}`}>
                  {selectedFileModal.status}
                </span>
              </div>
            </div>

            <div className="flex justify-end pt-2">
              <button
                onClick={() => setSelectedFileModal(null)}
                className="bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold px-4 py-2 rounded-lg"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
*/

// src/components/Tabs/TabAiArchitecture.jsx - Tab 2: AI Codebase Architecture & Dynamic File Cards
import React, { useState, useMemo } from "react";
import { useBugTracker } from "../../useBugTracker.jsx";

export default function TabAiArchitecture() {
  const {
    aiSummary,
    aiSearchQuery,
    setAiSearchQuery,
    selectedFileFilter,
    setSelectedFileFilter,
    setActiveTab,
    setActiveDrawerBug,
    bugs,
  } = useBugTracker();

  const [selectedFileModal, setSelectedFileModal] = useState(null);

  // Dynamic filter for file cards
  const filteredFiles = useMemo(() => {
    const fileList = aiSummary?.fileSummaries || [];
    const query = aiSearchQuery.toLowerCase().trim();

    return fileList.filter((f) => {
      const matchesSearch =
        !query ||
        f.file.toLowerCase().includes(query) ||
        f.role.toLowerCase().includes(query) ||
        f.intent.toLowerCase().includes(query) ||
        f.language.toLowerCase().includes(query) ||
        f.status.toLowerCase().includes(query);

      const matchesCategory =
        selectedFileFilter === "All" ||
        (selectedFileFilter === "Risks" && f.status !== "Clean" && f.status !== "Documentation") ||
        (selectedFileFilter === "Clean" && f.status === "Clean") ||
        f.status === selectedFileFilter;

      return matchesSearch && matchesCategory;
    });
  }, [aiSummary, aiSearchQuery, selectedFileFilter]);

  const handleCardClick = (fileItem) => {
    // Check if there is an associated bug for this file
    const matchedBug = bugs.find((b) => fileItem.file.includes(b.file) || b.file.includes(fileItem.file));
    if (matchedBug) {
      setActiveTab("bugs");
      setActiveDrawerBug(matchedBug);
    } else {
      setSelectedFileModal(fileItem);
    }
  };

  return (
    <div className="space-y-6 animate-fade-in max-w-7xl mx-auto">
      {/* Header Overview Card */}
      <div className="bg-[#131B2E] border border-slate-800 rounded-2xl p-6 sm:p-8 space-y-6 shadow-xl relative">
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 border-b border-slate-800/80 pb-5">
          <div>
            <span className="text-[11px] font-mono uppercase tracking-wider text-cyan-400 font-semibold bg-cyan-500/10 px-2.5 py-1 rounded-full border border-cyan-500/20">
              Tab 2 • Code Intelligence
            </span>
            <h2 className="text-xl sm:text-2xl font-bold text-white tracking-tight mt-2">
              AI Codebase Architecture & Topology
            </h2>
            <p className="text-xs text-slate-400 mt-1">
              Semantic NLP summary, detected technology stacks, subsystem boundaries, and file decomposition.
            </p>
          </div>

          <div className="flex items-center space-x-2 text-xs text-slate-400 bg-[#0B0F17] px-3 py-1.5 rounded-xl border border-slate-800">
            <span className="w-2 h-2 rounded-full bg-cyan-400 animate-pulse"></span>
            <span>AST Semantic Parser v2.4</span>
          </div>
        </div>

        {/* System Intent & Architecture Summary */}
        <div className="space-y-4">
          <div>
            <h3 className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-1.5">
              Identified System Intent & Architecture
            </h3>
            <p className="text-xs sm:text-sm text-slate-200 leading-relaxed bg-[#0B0F17]/80 border border-slate-800 rounded-xl p-4">
              {aiSummary.intent || "Enterprise microservice platform orchestrating authentication, checkout workflows, and WebSocket telemetry."}
            </p>
          </div>

          {/* Tech Stack Badges */}
          <div>
            <h3 className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-2">
              Detected Technology Stack
            </h3>
            <div className="flex flex-wrap gap-2">
              {(aiSummary.techStack || []).map((tech, idx) => (
                <span
                  key={idx}
                  className="bg-[#0B0F17] border border-cyan-500/30 text-cyan-300 font-mono text-xs px-3 py-1 rounded-lg flex items-center gap-1.5 shadow-xs"
                >
                  <span className="w-1.5 h-1.5 rounded-full bg-cyan-400"></span>
                  {tech}
                </span>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Main Subsystems & Architectural Risks Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Main Subsystems */}
        <div className="bg-[#131B2E] border border-slate-800 rounded-2xl p-6 space-y-4 shadow-lg">
          <h3 className="text-sm font-bold text-white flex items-center gap-2">
            <span>🧩</span> Main Architecture Components
          </h3>
          <div className="space-y-2.5">
            {(aiSummary.mainComponents || []).map((comp, idx) => (
              <div
                key={idx}
                className="bg-[#0B0F17] border border-slate-800/80 rounded-xl p-3.5 space-y-1"
              >
                <div className="text-xs font-bold text-white flex items-center justify-between">
                  <span>{comp.name}</span>
                  <span className="text-[10px] font-mono text-slate-500">Core Subsystem</span>
                </div>
                <p className="text-xs text-slate-400">{comp.description}</p>
              </div>
            ))}
          </div>
        </div>

        {/* Potential Architectural Risks & Recommendations */}
        <div className="bg-[#131B2E] border border-slate-800 rounded-2xl p-6 space-y-4 shadow-lg flex flex-col justify-between">
          <div className="space-y-4">
            <h3 className="text-sm font-bold text-white flex items-center gap-2">
              <span>⚠️</span> Potential Risks & Hotspots
            </h3>
            <div className="space-y-2.5">
              {(aiSummary.potentialRisks || []).map((risk, idx) => (
                <div
                  key={idx}
                  className="bg-[#0B0F17] border border-red-500/20 rounded-xl p-3.5 space-y-1"
                >
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-red-300">{risk.title}</span>
                    <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-red-500/20 text-red-400 border border-red-500/30">
                      {risk.severity}
                    </span>
                  </div>
                  <p className="text-xs text-slate-400">{risk.description}</p>
                </div>
              ))}
            </div>
          </div>

          {/* Recommendations Banner */}
          <div className="bg-[#0B0F17] border border-cyan-500/20 rounded-xl p-4 space-y-2 mt-4">
            <span className="text-[10px] font-bold text-cyan-400 uppercase tracking-wider block">
              💡 Primary AI Remediation Strategy
            </span>
            <ul className="text-xs text-slate-300 space-y-1.5 list-disc pl-4">
              {(aiSummary.recommendations || []).slice(0, 3).map((rec, idx) => (
                <li key={idx}>{rec}</li>
              ))}
            </ul>
          </div>
        </div>
      </div>

      {/* File Decomposition & Dynamic Search / Filter Grid */}
      <div className="bg-[#131B2E] border border-slate-800 rounded-2xl p-6 sm:p-8 space-y-6 shadow-xl">
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 border-b border-slate-800/80 pb-4">
          <div>
            <h3 className="text-base font-bold text-white">
              Decomposed Source File Cards ({filteredFiles.length})
            </h3>
            <p className="text-xs text-slate-400">
              Click any card to inspect full AST role, purpose, and associated security vulnerabilities.
            </p>
          </div>

          {/* Category Filter Chips */}
          <div className="flex flex-wrap gap-1.5">
            {["All", "Risks", "Clean"].map((cat) => (
              <button
                key={cat}
                type="button"
                onClick={() => setSelectedFileFilter(cat)}
                className={`px-3 py-1 rounded-lg text-xs font-semibold transition-colors cursor-pointer ${
                  selectedFileFilter === cat
                    ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/30"
                    : "bg-[#0B0F17] text-slate-400 hover:text-white border border-slate-800"
                }`}
              >
                {cat}
              </button>
            ))}
          </div>
        </div>

        {/* Real-time Search Field */}
        <div className="relative">
          <svg
            className="w-4 h-4 text-cyan-400 absolute left-3.5 top-3"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
          <input
            type="text"
            value={aiSearchQuery}
            onChange={(e) => setAiSearchQuery(e.target.value)}
            placeholder="Real-time filter by file name, intent, language, or risk status..."
            className="w-full bg-[#0B0F17] border border-slate-700 rounded-xl pl-10 pr-10 py-2.5 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-cyan-400 font-mono transition-colors"
          />
          {aiSearchQuery && (
            <button
              onClick={() => setAiSearchQuery("")}
              className="absolute right-3 top-2.5 text-slate-400 hover:text-white text-xs"
            >
              ✕
            </button>
          )}
        </div>

        {/* Grid of File Cards */}
        {filteredFiles.length === 0 ? (
          <div className="text-center py-10 text-slate-400 space-y-1">
            <p>No file cards matched "{aiSearchQuery}"</p>
            <p className="text-[11px] text-slate-500">Try searching for "queryBuilder", "auth", "deploy", or clear filter.</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {filteredFiles.map((fileItem) => {
              const hasBug = bugs.some((b) => fileItem.file.includes(b.file) || b.file.includes(fileItem.file));
              return (
                <div
                  key={fileItem.id || fileItem.file}
                  onClick={() => handleCardClick(fileItem)}
                  className="bg-[#0B0F17] hover:bg-slate-800/80 border border-slate-800 hover:border-cyan-500/40 rounded-xl p-4.5 space-y-3 cursor-pointer transition-all flex flex-col justify-between group shadow-sm"
                >
                  <div className="space-y-2">
                    <div className="flex items-start justify-between gap-2">
                      <span className="font-mono text-xs font-bold text-white group-hover:text-cyan-300 transition-colors truncate">
                        {fileItem.file}
                      </span>
                      <span
                        className={`text-[10px] font-semibold px-2 py-0.5 rounded border shrink-0 ${fileItem.statusColor}`}
                      >
                        {fileItem.status}
                      </span>
                    </div>

                    <div className="space-y-1 text-xs">
                      <div>
                        <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Role</span>
                        <p className="text-slate-300 line-clamp-2 leading-relaxed">{fileItem.role}</p>
                      </div>
                      <div>
                        <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Intent</span>
                        <p className="text-slate-400 line-clamp-2 leading-relaxed">{fileItem.intent}</p>
                      </div>
                    </div>
                  </div>

                  <div className="pt-2 border-t border-slate-800/80 flex items-center justify-between text-[11px] text-slate-500">
                    <span className="font-mono bg-slate-900 px-2 py-0.5 rounded border border-slate-800 text-slate-400">
                      {fileItem.language} • {fileItem.lines} lines
                    </span>
                    <span className="text-cyan-400 group-hover:translate-x-0.5 transition-transform font-medium">
                      {hasBug ? "Inspect Bug →" : "View Info →"}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* File Info Modal if file doesn't have a direct bug */}
      {selectedFileModal && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-xs animate-fade-in"
          onClick={() => setSelectedFileModal(null)}
        >
          <div
            className="bg-[#131B2E] border border-slate-800 rounded-2xl max-w-lg w-full p-6 space-y-4 shadow-2xl relative"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-start justify-between border-b border-slate-800 pb-3">
              <div>
                <h3 className="text-base font-bold text-white font-mono">{selectedFileModal.file}</h3>
                <span className="text-xs text-slate-400">{selectedFileModal.language} • {selectedFileModal.lines} lines</span>
              </div>
              <button
                onClick={() => setSelectedFileModal(null)}
                className="text-slate-400 hover:text-white p-1 rounded-lg hover:bg-slate-800"
              >
                ✕
              </button>
            </div>

            <div className="space-y-3 text-xs">
              <div className="bg-[#0B0F17] p-3 rounded-xl border border-slate-800">
                <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block mb-1">Architectural Role</span>
                <p className="text-slate-200">{selectedFileModal.role}</p>
              </div>
              <div className="bg-[#0B0F17] p-3 rounded-xl border border-slate-800">
                <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block mb-1">Functional Intent</span>
                <p className="text-slate-300">{selectedFileModal.intent}</p>
              </div>
              <div className="flex justify-between items-center bg-[#0B0F17] p-3 rounded-xl border border-slate-800">
                <span className="text-slate-400">Security Status:</span>
                <span className={`text-xs font-semibold px-2.5 py-0.5 rounded border ${selectedFileModal.statusColor}`}>
                  {selectedFileModal.status}
                </span>
              </div>
            </div>

            <div className="flex justify-end pt-2">
              <button
                onClick={() => setSelectedFileModal(null)}
                className="bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold px-4 py-2 rounded-lg"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
