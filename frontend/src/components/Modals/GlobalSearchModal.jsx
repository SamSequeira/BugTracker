// src/components/Modals/GlobalSearchModal.jsx - Global Search across Bugs, Files, and Navigation
import React, { useState, useEffect, useRef } from "react";
import { useBugTracker } from "../../useBugTracker.jsx";

export default function GlobalSearchModal() {
  const {
    isSearchOpen,
    setIsSearchOpen,
    bugs,
    aiSummary,
    setActiveTab,
    setActiveDrawerBug,
    setAiSearchQuery,
    setBugSearchQuery,
  } = useBugTracker();

  const [query, setQuery] = useState("");
  const inputRef = useRef(null);

  useEffect(() => {
    if (isSearchOpen) {
      setTimeout(() => inputRef.current?.focus(), 50);
    } else {
      setQuery("");
    }
  }, [isSearchOpen]);

  if (!isSearchOpen) return null;

  const cleanQ = query.trim().toLowerCase();

  // 1. Navigation items
  const navMatches = [
    { title: "Tab 1: Repository Scanner", tab: "scanner", category: "Navigation" },
    { title: "Tab 2: AI Codebase Architecture", tab: "ai", category: "Navigation" },
    { title: "Tab 3: Bug Management & Inspector", tab: "bugs", category: "Navigation" },
    { title: "Tab 4: Executive Audit & PDF Report", tab: "reports", category: "Navigation" },
  ].filter((n) => !cleanQ || n.title.toLowerCase().includes(cleanQ));

  // 2. Bugs matches
  const bugMatches = bugs.filter((b) => {
    if (!cleanQ) return false;
    return (
      b.id.toLowerCase().includes(cleanQ) ||
      b.title.toLowerCase().includes(cleanQ) ||
      b.file.toLowerCase().includes(cleanQ) ||
      b.severity.toLowerCase().includes(cleanQ) ||
      b.status.toLowerCase().includes(cleanQ)
    );
  });

  // 3. File matches from AI architecture
  const fileMatches = (aiSummary?.fileSummaries || []).filter((f) => {
    if (!cleanQ) return false;
    return (
      f.file.toLowerCase().includes(cleanQ) ||
      f.role.toLowerCase().includes(cleanQ) ||
      f.intent.toLowerCase().includes(cleanQ) ||
      f.status.toLowerCase().includes(cleanQ)
    );
  });

  const handleSelectBug = (bug) => {
    setActiveTab("bugs");
    setActiveDrawerBug(bug);
    setIsSearchOpen(false);
  };

  const handleSelectFile = (fileItem) => {
    setActiveTab("ai");
    setAiSearchQuery(fileItem.file);
    setIsSearchOpen(false);
  };

  const handleSelectNav = (tabId) => {
    setActiveTab(tabId);
    setIsSearchOpen(false);
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center pt-20 p-4 bg-black/75 backdrop-blur-xs animate-fade-in"
      onClick={() => setIsSearchOpen(false)}
    >
      <div
        className="bg-[#131B2E] border border-slate-800 rounded-2xl max-w-xl w-full p-4 space-y-4 shadow-2xl relative"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Search Input */}
        <div className="relative">
          <svg
            className="w-5 h-5 text-cyan-400 absolute left-3.5 top-3"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Type to search bugs, files, architecture, or tabs..."
            className="w-full bg-[#0B0F17] border border-slate-700 rounded-xl pl-11 pr-10 py-3 text-xs sm:text-sm text-white placeholder-slate-500 focus:outline-none focus:border-cyan-400 transition-colors font-mono"
          />
          {query && (
            <button
              onClick={() => setQuery("")}
              className="absolute right-3 top-3 text-slate-400 hover:text-white"
            >
              ✕
            </button>
          )}
        </div>

        {/* Search Results List */}
        <div className="max-h-80 overflow-y-auto space-y-3 pr-1 text-xs">
          {/* Bugs Matches */}
          {bugMatches.length > 0 && (
            <div>
              <div className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider mb-2">
                Bugs & Security Issues ({bugMatches.length})
              </div>
              <div className="space-y-1.5">
                {bugMatches.map((bug) => (
                  <div
                    key={bug.id}
                    onClick={() => handleSelectBug(bug)}
                    className="p-2.5 bg-[#0B0F17] hover:bg-slate-800/80 border border-slate-800 rounded-lg cursor-pointer transition-colors flex items-center justify-between group"
                  >
                    <div className="space-y-0.5 truncate pr-2">
                      <div className="flex items-center space-x-2">
                        <span className="font-mono text-[10px] text-cyan-400 font-bold">{bug.id}</span>
                        <span className="text-white font-medium truncate">{bug.title}</span>
                      </div>
                      <div className="text-[11px] text-slate-400 font-mono">
                        {bug.file}:{bug.line}
                      </div>
                    </div>
                    <div className="flex items-center space-x-2 shrink-0">
                      <span
                        className={`text-[10px] px-2 py-0.5 rounded font-semibold ${
                          bug.severity === "Critical"
                            ? "bg-red-500/20 text-red-400"
                            : bug.severity === "High"
                            ? "bg-amber-500/20 text-amber-400"
                            : "bg-blue-500/20 text-blue-400"
                        }`}
                      >
                        {bug.severity}
                      </span>
                      <span className="text-slate-500 group-hover:text-cyan-400 transition-colors">→</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Files Matches */}
          {fileMatches.length > 0 && (
            <div>
              <div className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider mb-2">
                Codebase Files ({fileMatches.length})
              </div>
              <div className="space-y-1.5">
                {fileMatches.map((file) => (
                  <div
                    key={file.id}
                    onClick={() => handleSelectFile(file)}
                    className="p-2.5 bg-[#0B0F17] hover:bg-slate-800/80 border border-slate-800 rounded-lg cursor-pointer transition-colors flex items-center justify-between group"
                  >
                    <div className="space-y-0.5 truncate pr-2">
                      <div className="text-white font-mono font-medium truncate">{file.file}</div>
                      <div className="text-[11px] text-slate-400 truncate">{file.role}</div>
                    </div>
                    <div className="flex items-center space-x-2 shrink-0">
                      <span className="text-[10px] px-2 py-0.5 rounded font-mono bg-slate-800 text-slate-300">
                        {file.language}
                      </span>
                      <span className="text-slate-500 group-hover:text-cyan-400 transition-colors">→</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Navigation Matches */}
          {navMatches.length > 0 && (
            <div>
              <div className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider mb-2">
                Dashboard Views
              </div>
              <div className="space-y-1.5">
                {navMatches.map((nav) => (
                  <div
                    key={nav.tab}
                    onClick={() => handleSelectNav(nav.tab)}
                    className="p-2.5 bg-[#0B0F17] hover:bg-slate-800/80 border border-slate-800 rounded-lg cursor-pointer transition-colors flex items-center justify-between group"
                  >
                    <span className="text-slate-200 font-medium">{nav.title}</span>
                    <span className="text-slate-500 group-hover:text-cyan-400 text-xs">Jump →</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {cleanQ && bugMatches.length === 0 && fileMatches.length === 0 && navMatches.length === 0 && (
            <div className="text-center py-8 text-slate-400 space-y-1">
              <p>No results found matching "{query}"</p>
              <p className="text-[11px] text-slate-500">Try searching for "SQL", "queryBuilder", "auth", or "Critical"</p>
            </div>
          )}
        </div>

        {/* Footer info */}
        <div className="flex items-center justify-between text-[11px] text-slate-500 border-t border-slate-800 pt-2">
          <span>Press <kbd className="bg-slate-800 text-slate-300 px-1.5 py-0.5 rounded">ESC</kbd> to close</span>
          <span>Click any item to navigate</span>
        </div>
      </div>
    </div>
  );
}
