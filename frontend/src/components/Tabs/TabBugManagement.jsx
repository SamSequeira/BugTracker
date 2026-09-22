// src/components/Tabs/TabBugManagement.jsx - Tab 3: Bug Management & Deep Inspector
import React, { useMemo } from "react";
import { useBugTracker } from "../../useBugTracker.jsx";

export default function TabBugManagement() {
  const {
    bugs,
    bugSearchQuery,
    setBugSearchQuery,
    selectedSeverity,
    setSelectedSeverity,
    selectedStatus,
    setSelectedStatus,
    setActiveDrawerBug,
    toggleResolveBug,
  } = useBugTracker();

  // Dynamic filter for bug issues
  const filteredBugs = useMemo(() => {
    const query = bugSearchQuery.toLowerCase().trim();

    return bugs.filter((bug) => {
      const matchesSearch =
        !query ||
        bug.id.toLowerCase().includes(query) ||
        bug.title.toLowerCase().includes(query) ||
        bug.file.toLowerCase().includes(query) ||
        bug.engineer?.toLowerCase().includes(query) ||
        bug.engineerNotes?.toLowerCase().includes(query);

      const matchesSeverity =
        selectedSeverity === "All" || bug.severity === selectedSeverity;

      const matchesStatus =
        selectedStatus === "All" || bug.status === selectedStatus;

      return matchesSearch && matchesSeverity && matchesStatus;
    });
  }, [bugs, bugSearchQuery, selectedSeverity, selectedStatus]);

  return (
    <div className="space-y-6 animate-fade-in max-w-7xl mx-auto">
      {/* Top Filter and Controls Card */}
      <div className="bg-[#131B2E] border border-slate-800 rounded-2xl p-6 sm:p-8 space-y-5 shadow-xl">
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 border-b border-slate-800/80 pb-5">
          <div>
            <span className="text-[11px] font-mono uppercase tracking-wider text-cyan-400 font-semibold bg-cyan-500/10 px-2.5 py-1 rounded-full border border-cyan-500/20">
              Tab 3 • Issue Triage
            </span>
            <h2 className="text-xl sm:text-2xl font-bold text-white tracking-tight mt-2">
              Bug Management & Vulnerability Inspector
            </h2>
            <p className="text-xs text-slate-400 mt-1">
              Filter by AST severity tiers, inspect vulnerable lines, test suggested diff fixes, and update debounced remarks.
            </p>
          </div>

          <span className="text-xs text-slate-400 font-mono bg-[#0B0F17] px-3 py-1.5 rounded-xl border border-slate-800">
            Showing <strong className="text-cyan-400">{filteredBugs.length}</strong> of {bugs.length} issues
          </span>
        </div>

        {/* Filters Bar: Search + Severity + Status */}
        <div className="grid grid-cols-1 sm:grid-cols-12 gap-3">
          {/* Search Input */}
          <div className="sm:col-span-6 relative">
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
              value={bugSearchQuery}
              onChange={(e) => setBugSearchQuery(e.target.value)}
              placeholder="Search by bug ID, title, file name, or engineer..."
              className="w-full bg-[#0B0F17] border border-slate-700 rounded-xl pl-10 pr-10 py-2.5 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-cyan-400 font-mono transition-colors"
            />
            {bugSearchQuery && (
              <button
                onClick={() => setBugSearchQuery("")}
                className="absolute right-3 top-2.5 text-slate-400 hover:text-white text-xs"
              >
                ✕
              </button>
            )}
          </div>

          {/* Severity Dropdown */}
          <div className="sm:col-span-3">
            <select
              value={selectedSeverity}
              onChange={(e) => setSelectedSeverity(e.target.value)}
              className="w-full bg-[#0B0F17] border border-slate-700 rounded-xl px-3 py-2.5 text-xs text-white focus:outline-none focus:border-cyan-400 transition-colors"
            >
              <option value="All">All Severities</option>
              <option value="High">High Only</option>
              <option value="Medium">Medium Only</option>
              <option value="Low">Low Only</option>
            </select>
          </div>

          {/* Status Dropdown */}
          <div className="sm:col-span-3">
            <select
              value={selectedStatus}
              onChange={(e) => setSelectedStatus(e.target.value)}
              className="w-full bg-[#0B0F17] border border-slate-700 rounded-xl px-3 py-2.5 text-xs text-white focus:outline-none focus:border-cyan-400 transition-colors"
            >
              <option value="All">All Statuses</option>
              <option value="Open">Open Issues</option>
              <option value="In Progress">In Progress</option>
              <option value="Resolved">Resolved Issues</option>
            </select>
          </div>
        </div>
      </div>

      {/* Bugs List Grid / Table View */}
      <div className="space-y-3">
        {filteredBugs.length === 0 ? (
          <div className="bg-[#131B2E] border border-slate-800 rounded-2xl p-12 text-center text-slate-400 space-y-2">
            <div className="text-3xl">🔍</div>
            <p className="text-sm font-semibold text-white">No vulnerabilities found matching your filters</p>
            <p className="text-xs text-slate-500">
              Try resetting your search query or changing severity and status filters.
            </p>
          </div>
        ) : (
          filteredBugs.map((bug) => {
            const isResolved = bug.status === "Resolved";
            return (
              <div
                key={bug.id}
                onClick={() => setActiveDrawerBug(bug)}
                className={`bg-[#131B2E] hover:bg-slate-800/90 border rounded-2xl p-5 transition-all cursor-pointer shadow-md space-y-3 group ${
                  isResolved
                    ? "border-slate-800/80 opacity-80"
                    : bug.severity === "High"
                    ? "border-red-500/30 hover:border-red-500/60"
                    : bug.severity === "Medium"
                    ? "border-amber-500/30 hover:border-amber-500/60"
                    : "border-slate-800 hover:border-cyan-500/40"
                }`}
              >
                {/* Top Row: ID, Badges, and Action Button */}
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                  <div className="flex items-center space-x-2.5 flex-wrap gap-y-1">
                    <span className="font-mono text-xs text-cyan-400 font-bold bg-cyan-500/10 px-2.5 py-0.5 rounded border border-cyan-500/20">
                      {bug.id}
                    </span>
                    <span
                      className={`text-[10px] font-bold px-2 py-0.5 rounded ${
                        bug.severity === "High"
                          ? "bg-red-500/20 text-red-400 border border-red-500/30"
                          : bug.severity === "Medium"
                          ? "bg-amber-500/20 text-amber-400 border border-amber-500/30"
                          : "bg-blue-500/20 text-blue-400 border border-blue-500/30"
                      }`}
                    >
                      {bug.severity}
                    </span>
                    <span className="text-[10px] font-medium bg-[#0B0F17] text-slate-300 px-2 py-0.5 rounded border border-slate-800">
                      {bug.priority}
                    </span>
                    <span
                      className={`text-[10px] font-bold px-2 py-0.5 rounded ${
                        isResolved
                          ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30"
                          : "bg-red-500/20 text-red-400 border border-red-500/30"
                      }`}
                    >
                      {bug.status}
                    </span>
                    {bug.similarCount && (
                      <span className="text-[10px] text-slate-500 bg-slate-800 px-2 py-0.5 rounded">
                        {bug.similarCount}
                      </span>
                    )}
                  </div>

                  {/* Inline Toggle Resolve Button */}
                  <div
                    onClick={(e) => e.stopPropagation()}
                    className="flex items-center space-x-2 shrink-0"
                  >
                    <button
                      type="button"
                      onClick={() => toggleResolveBug(bug.id)}
                      className={`text-xs font-bold px-3 py-1.5 rounded-lg transition-colors cursor-pointer flex items-center gap-1.5 ${
                        isResolved
                          ? "bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700"
                          : "bg-emerald-500/20 hover:bg-emerald-500/30 text-emerald-300 border border-emerald-500/30"
                      }`}
                    >
                      {isResolved ? "↩ Reopen" : "✓ Resolve"}
                    </button>
                    <button
                      type="button"
                      onClick={() => setActiveDrawerBug(bug)}
                      className="bg-[#0B0F17] hover:bg-slate-800 text-cyan-400 border border-slate-700 px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors"
                    >
                      Inspector &rarr;
                    </button>
                  </div>
                </div>

                {/* Bug Title & File Line */}
                <div className="space-y-1">
                  <h3 className="text-sm sm:text-base font-bold text-white group-hover:text-cyan-300 transition-colors">
                    {bug.title}
                  </h3>
                  <div className="flex items-center space-x-3 text-xs text-slate-400 font-mono">
                    <span className="text-slate-300">{bug.file}</span>
                    <span>:</span>
                    <span className="text-red-400">Line {bug.line}</span>
                    <span className="text-slate-600">•</span>
                    <span className="text-slate-500 font-sans">Assigned: {bug.engineer}</span>
                  </div>
                </div>

                {/* Problem snippet preview */}
                <p className="text-xs text-slate-300 line-clamp-2 leading-relaxed bg-[#0B0F17]/60 p-2.5 rounded-xl border border-slate-800/80">
                  {bug.wrong || "Vulnerability identified in parsed syntax tree."}
                </p>

                {/* Engineer remarks preview if any */}
                {bug.engineerNotes && (
                  <div className="text-[11px] text-cyan-300/90 flex items-center gap-1.5 bg-cyan-500/5 px-2.5 py-1.5 rounded-lg border border-cyan-500/10">
                    <span className="font-semibold text-cyan-400">Remediation Note:</span>
                    <span className="truncate">{bug.engineerNotes}</span>
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
// src/components/Tabs/TabBugManagement.jsx - Tab 3: Bug Management & Deep Inspector
import React, { useMemo } from "react";
import { useBugTracker } from "../../useBugTracker.jsx";

export default function TabBugManagement() {
  const {
    bugs,
    bugSearchQuery,
    setBugSearchQuery,
    selectedSeverity,
    setSelectedSeverity,
    selectedStatus,
    setSelectedStatus,
    setActiveDrawerBug,
    toggleResolveBug,
  } = useBugTracker();

  // Dynamic filter for bug issues
  const filteredBugs = useMemo(() => {
    const query = (bugSearchQuery || "").toLowerCase().trim();

    return (bugs || []).filter((bug) => {
      if (!bug) return false;
      const bugId = String(bug.id || "").toLowerCase();
      const bugTitle = String(bug.title || "").toLowerCase();
      const bugFile = String(bug.file || "").toLowerCase();
      const bugEngineer = String(bug.engineer || "").toLowerCase();
      const bugNotes = String(bug.engineerNotes || "").toLowerCase();

      const matchesSearch =
        !query ||
        bugId.includes(query) ||
        bugTitle.includes(query) ||
        bugFile.includes(query) ||
        bugEngineer.includes(query) ||
        bugNotes.includes(query);

      const matchesSeverity =
        !selectedSeverity || selectedSeverity === "All" || bug.severity === selectedSeverity;

      const matchesStatus =
        !selectedStatus || selectedStatus === "All" || bug.status === selectedStatus;

      return matchesSearch && matchesSeverity && matchesStatus;
    });
  }, [bugs, bugSearchQuery, selectedSeverity, selectedStatus]);

  return (
    <div className="space-y-6 animate-fade-in max-w-7xl mx-auto">
      {/* Top Filter and Controls Card */}
      <div className="bg-[#131B2E] border border-slate-800 rounded-2xl p-6 sm:p-8 space-y-5 shadow-xl">
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 border-b border-slate-800/80 pb-5">
          <div>
            <span className="text-[11px] font-mono uppercase tracking-wider text-cyan-400 font-semibold bg-cyan-500/10 px-2.5 py-1 rounded-full border border-cyan-500/20">
              Tab 3 • Issue Triage
            </span>
            <h2 className="text-xl sm:text-2xl font-bold text-white tracking-tight mt-2">
              Bug Management & Vulnerability Inspector
            </h2>
            <p className="text-xs text-slate-400 mt-1">
              Filter by AST severity tiers, inspect vulnerable lines, test suggested diff fixes, and update debounced remarks.
            </p>
          </div>

          <span className="text-xs text-slate-400 font-mono bg-[#0B0F17] px-3 py-1.5 rounded-xl border border-slate-800">
            Showing <strong className="text-cyan-400">{filteredBugs.length}</strong> of {bugs.length} issues
          </span>
        </div>

        {/* Filters Bar: Search + Severity + Status */}
        <div className="grid grid-cols-1 sm:grid-cols-12 gap-3">
          {/* Search Input */}
          <div className="sm:col-span-6 relative">
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
              value={bugSearchQuery}
              onChange={(e) => setBugSearchQuery(e.target.value)}
              placeholder="Search by bug ID, title, file name, or engineer..."
              className="w-full bg-[#0B0F17] border border-slate-700 rounded-xl pl-10 pr-10 py-2.5 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-cyan-400 font-mono transition-colors"
            />
            {bugSearchQuery && (
              <button
                onClick={() => setBugSearchQuery("")}
                className="absolute right-3 top-2.5 text-slate-400 hover:text-white text-xs"
              >
                ✕
              </button>
            )}
          </div>

          {/* Severity Dropdown */}
          <div className="sm:col-span-3">
            <select
              value={selectedSeverity}
              onChange={(e) => setSelectedSeverity(e.target.value)}
              className="w-full bg-[#0B0F17] border border-slate-700 rounded-xl px-3 py-2.5 text-xs text-white focus:outline-none focus:border-cyan-400 transition-colors"
            >
              <option value="All">All Severities</option>
              <option value="High">High Only</option>
              <option value="Medium">Medium Only</option>
              <option value="Low">Low Only</option>
            </select>
          </div>

          {/* Status Dropdown */}
          <div className="sm:col-span-3">
            <select
              value={selectedStatus}
              onChange={(e) => setSelectedStatus(e.target.value)}
              className="w-full bg-[#0B0F17] border border-slate-700 rounded-xl px-3 py-2.5 text-xs text-white focus:outline-none focus:border-cyan-400 transition-colors"
            >
              <option value="All">All Statuses</option>
              <option value="Open">Open Issues</option>
              <option value="In Progress">In Progress</option>
              <option value="Resolved">Resolved Issues</option>
            </select>
          </div>
        </div>
      </div>

      {/* Bugs List Grid / Table View */}
      <div className="space-y-3">
        {filteredBugs.length === 0 ? (
          <div className="bg-[#131B2E] border border-slate-800 rounded-2xl p-12 text-center text-slate-400 space-y-2">
            <div className="text-3xl">🔍</div>
            <p className="text-sm font-semibold text-white">No vulnerabilities found matching your filters</p>
            <p className="text-xs text-slate-500">
              Try resetting your search query or changing severity and status filters.
            </p>
          </div>
        ) : (
          filteredBugs.map((bug) => {
            const isResolved = bug.status === "Resolved";
            return (
              <div
                key={bug.id}
                onClick={() => setActiveDrawerBug(bug)}
                className={`bg-[#131B2E] hover:bg-slate-800/90 border rounded-2xl p-5 transition-all cursor-pointer shadow-md space-y-3 group ${
                  isResolved
                    ? "border-slate-800/80 opacity-80"
                    : bug.severity === "High"
                    ? "border-red-500/30 hover:border-red-500/60"
                    : bug.severity === "Medium"
                    ? "border-amber-500/30 hover:border-amber-500/60"
                    : "border-slate-800 hover:border-cyan-500/40"
                }`}
              >
                {/* Top Row: ID, Badges, and Action Button */}
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                  <div className="flex items-center space-x-2.5 flex-wrap gap-y-1">
                    <span className="font-mono text-xs text-cyan-400 font-bold bg-cyan-500/10 px-2.5 py-0.5 rounded border border-cyan-500/20">
                      {bug.id}
                    </span>
                    <span
                      className={`text-[10px] font-bold px-2 py-0.5 rounded ${
                        bug.severity === "High"
                          ? "bg-red-500/20 text-red-400 border border-red-500/30"
                          : bug.severity === "Medium"
                          ? "bg-amber-500/20 text-amber-400 border border-amber-500/30"
                          : "bg-blue-500/20 text-blue-400 border border-blue-500/30"
                      }`}
                    >
                      {bug.severity}
                    </span>
                    <span className="text-[10px] font-medium bg-[#0B0F17] text-slate-300 px-2 py-0.5 rounded border border-slate-800">
                      {bug.priority}
                    </span>
                    <span
                      className={`text-[10px] font-bold px-2 py-0.5 rounded ${
                        isResolved
                          ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30"
                          : "bg-red-500/20 text-red-400 border border-red-500/30"
                      }`}
                    >
                      {bug.status}
                    </span>
                    {bug.similarCount && (
                      <span className="text-[10px] text-slate-500 bg-slate-800 px-2 py-0.5 rounded">
                        {bug.similarCount}
                      </span>
                    )}
                  </div>

                  {/* Inline Toggle Resolve Button */}
                  <div
                    onClick={(e) => e.stopPropagation()}
                    className="flex items-center space-x-2 shrink-0"
                  >
                    <button
                      type="button"
                      onClick={() => toggleResolveBug(bug.id)}
                      className={`text-xs font-bold px-3 py-1.5 rounded-lg transition-colors cursor-pointer flex items-center gap-1.5 ${
                        isResolved
                          ? "bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700"
                          : "bg-emerald-500/20 hover:bg-emerald-500/30 text-emerald-300 border border-emerald-500/30"
                      }`}
                    >
                      {isResolved ? "↩ Reopen" : "✓ Resolve"}
                    </button>
                    <button
                      type="button"
                      onClick={() => setActiveDrawerBug(bug)}
                      className="bg-[#0B0F17] hover:bg-slate-800 text-cyan-400 border border-slate-700 px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors"
                    >
                      Inspector &rarr;
                    </button>
                  </div>
                </div>

                {/* Bug Title & File Line */}
                <div className="space-y-1">
                  <h3 className="text-sm sm:text-base font-bold text-white group-hover:text-cyan-300 transition-colors">
                    {bug.title}
                  </h3>
                  <div className="flex items-center space-x-3 text-xs text-slate-400 font-mono">
                    <span className="text-slate-300">{bug.file}</span>
                    <span>:</span>
                    <span className="text-red-400">Line {bug.line}</span>
                    <span className="text-slate-600">•</span>
                    <span className="text-slate-500 font-sans">Assigned: {bug.engineer}</span>
                  </div>
                </div>

                {/* Problem snippet preview */}
                <p className="text-xs text-slate-300 line-clamp-2 leading-relaxed bg-[#0B0F17]/60 p-2.5 rounded-xl border border-slate-800/80">
                  {bug.wrong || "Vulnerability identified in parsed syntax tree."}
                </p>

                {/* Engineer remarks preview if any */}
                {bug.engineerNotes && (
                  <div className="text-[11px] text-cyan-300/90 flex items-center gap-1.5 bg-cyan-500/5 px-2.5 py-1.5 rounded-lg border border-cyan-500/10">
                    <span className="font-semibold text-cyan-400">Remediation Note:</span>
                    <span className="truncate">{bug.engineerNotes}</span>
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
