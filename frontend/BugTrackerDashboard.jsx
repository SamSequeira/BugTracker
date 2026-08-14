// BugTrackerDashboard.jsx - Main Dashboard Component with Shared State, Modals & Live/Demo Fallback

import React, { useState } from "react";
import { useBugTracker } from "./useBugTracker.js";
import { apiService } from "./api.js";

export default function BugTrackerDashboard() {
  const {
    user,
    activeTab,
    setActiveTab,
    scanInputTab,
    setScanInputTab,
    isSettingsOpen,
    setIsSettingsOpen,
    isHelpOpen,
    setIsHelpOpen,
    isSearchOpen,
    setIsSearchOpen,
    isNotificationsOpen,
    setIsNotificationsOpen,
    apiUrl,
    updateApiUrl,
    isLive,
    stats,
    bugs,
    aiSummary,
    recentScans,
    notifications,
    searchQuery,
    setSearchQuery,
    aiSearchQuery,
    setAiSearchQuery,
    debugSeverity,
    setDebugSeverity,
    expandedBugId,
    setExpandedBugId,
    isScanning,
    scanProgress,
    selectedFileName,
    setSelectedFileName,
    logout,
    runScan,
    toggleResolveBug,
    updateBugNotes,
    openCriticalCount,
    resolvedCount,
    resolutionPercentage,
  } = useBugTracker();

  // Local state for GitHub URL input field in Tab 1
  const [localRepoInput, setLocalRepoInput] = useState(user.repoUrl);
  // Settings modal editable URL
  const [settingsUrlInput, setSettingsUrlInput] = useState(apiUrl);
  const [testConnStatus, setTestConnStatus] = useState(null);

  // File Upload Dialog Handler
  const handleNativeFileSelect = (e) => {
    const file = e.target.files[0];
    if (file) {
      const sizeMb = (file.size / (1024 * 1024)).toFixed(2);
      setSelectedFileName(`${file.name} (${sizeMb} MB)`);
      runScan(file);
    }
  };

  const handleFileDrop = (e) => {
    e.preventDefault();
    const file = e.dataTransfer.files[0];
    if (file) {
      const sizeMb = (file.size / (1024 * 1024)).toFixed(2);
      setSelectedFileName(`${file.name} (${sizeMb} MB)`);
      runScan(file);
    }
  };

  const handleTestConnection = async () => {
    setTestConnStatus("testing");
    apiService.setBaseUrl(settingsUrlInput);
    const res = await apiService.getDashboardStats();
    if (res.live) {
      setTestConnStatus("success");
    } else {
      setTestConnStatus("failed");
    }
  };

  const handleSaveSettings = (e) => {
    e.preventDefault();
    updateApiUrl(settingsUrlInput);
    setIsSettingsOpen(false);
  };

  // Filtered Tab 2 File Cards
  const filteredFileCards = aiSummary.fileSummaries.filter((f) => {
    if (!aiSearchQuery) return true;
    const q = aiSearchQuery.toLowerCase();
    return (
      f.file.toLowerCase().includes(q) ||
      f.role.toLowerCase().includes(q) ||
      f.intent.toLowerCase().includes(q) ||
      f.status.toLowerCase().includes(q)
    );
  });

  // Filtered Tab 3 Bugs Table
  const filteredBugs = bugs.filter((bug) => {
    const matchSeverity = debugSeverity === "All" || bug.severity === debugSeverity;
    const matchSearch =
      searchQuery === "" ||
      bug.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
      bug.file.toLowerCase().includes(searchQuery.toLowerCase()) ||
      bug.id.toLowerCase().includes(searchQuery.toLowerCase());
    return matchSeverity && matchSearch;
  });

  // Global Search Filter Results
  const globalSearchBugs = searchQuery
    ? bugs.filter(
        (b) =>
          b.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
          b.file.toLowerCase().includes(searchQuery.toLowerCase()) ||
          b.id.toLowerCase().includes(searchQuery.toLowerCase())
      )
    : [];

  return (
    <div className="min-h-screen bg-[#0B0F17] text-slate-200 font-sans flex text-xs sm:text-sm">
      {/* Hidden Native File Input */}
      <input
        type="file"
        id="hidden-file-input"
        accept=".zip,.tar,.gz,.rar,.7z"
        className="hidden"
        onChange={handleNativeFileSelect}
      />

      {/* ===================================================================== */}
      {/* LEFT SIDEBAR (ONE AVATAR ONLY AT BOTTOM)                              */}
      {/* ===================================================================== */}
      <aside className="no-print w-16 bg-[#0F1623] border-r border-slate-800 flex flex-col items-center py-4 space-y-5 shrink-0 sticky top-0 h-screen z-30">
        <div className="p-2.5 bg-cyan-500/10 rounded-xl text-cyan-400 border border-cyan-500/20">
          <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
        </div>

        {/* 4 Core Navigation Tabs */}
        <nav className="flex flex-col space-y-2.5 w-full items-center pt-2">
          <button
            onClick={() => setActiveTab("dashboard")}
            title="Tab 1: Dashboard (Repository Scanner)"
            className={`p-3 w-full flex justify-center transition-all ${
              activeTab === "dashboard"
                ? "bg-cyan-500/15 text-cyan-400 border-l-2 border-cyan-400"
                : "text-slate-400 hover:text-white"
            }`}
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z" />
            </svg>
          </button>

          <button
            onClick={() => setActiveTab("ai")}
            title="Tab 2: AI Codebase Intelligence"
            className={`p-3 w-full flex justify-center transition-all ${
              activeTab === "ai"
                ? "bg-cyan-500/15 text-cyan-400 border-l-2 border-cyan-400"
                : "text-slate-400 hover:text-white"
            }`}
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 3v4M3 5h4M6 17v4m-2-2h4m5-16l2.286 6.857L21 12l-5.714 2.143L13 21l-2.286-6.857L5 12l5.714-2.143L13 3z" />
            </svg>
          </button>

          <button
            onClick={() => setActiveTab("debug")}
            title="Tab 3: Debugging & Issue Inspector"
            className={`p-3 w-full flex justify-center transition-all ${
              activeTab === "debug"
                ? "bg-cyan-500/15 text-cyan-400 border-l-2 border-cyan-400"
                : "text-slate-400 hover:text-white"
            }`}
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 4v1m6 11h2m-6 0h-2v4m0-11v3m0 0h.01M12 12h4.01M16 20h4M4 12h4m12 0a8 8 0 11-16 0 8 8 0 0116 0z" />
            </svg>
          </button>

          <button
            onClick={() => setActiveTab("report")}
            title="Tab 4: Executive Audit Report"
            className={`p-3 w-full flex justify-center transition-all ${
              activeTab === "report"
                ? "bg-cyan-500/15 text-cyan-400 border-l-2 border-cyan-400"
                : "text-slate-400 hover:text-white"
            }`}
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
          </button>
        </nav>

        {/* Sidebar Actions & Profile at Bottom */}
        <div className="mt-auto flex flex-col space-y-3 items-center pt-4 border-t border-slate-800/80 w-full">
          <button
            onClick={() => {
              setSettingsUrlInput(apiUrl);
              setTestConnStatus(null);
              setIsSettingsOpen(true);
            }}
            title="Settings & API Backend URL"
            className="p-2 text-slate-400 hover:text-cyan-400 transition-colors"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
            </svg>
          </button>

          <button
            onClick={() => setIsHelpOpen(true)}
            title="Help & Shortcuts"
            className="p-2 text-slate-400 hover:text-cyan-400 transition-colors"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </button>

          <button
            onClick={logout}
            title="Sign Out to Auth Screen"
            className="p-2 text-slate-500 hover:text-red-400 transition-colors"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
            </svg>
          </button>

          {/* SINGLE PROFILE AVATAR AT BOTTOM */}
          <div className="w-8 h-8 rounded-full bg-cyan-950 border border-cyan-500/40 text-cyan-300 flex items-center justify-center font-bold text-xs">
            {user.avatar}
          </div>
        </div>
      </aside>

      {/* ===================================================================== */}
      {/* MAIN VIEWPORT                                                         */}
      {/* ===================================================================== */}
      <div className="flex-1 flex flex-col min-w-0 overflow-y-auto">
        {/* Header */}
        <header className="no-print h-14 bg-[#0F1623] border-b border-slate-800 px-6 flex items-center justify-between sticky top-0 z-20">
          <div className="flex items-center space-x-3">
            <h1 className="font-semibold text-white text-base">AI Bug Tracking & Prioritization System</h1>
            <span className="text-[11px] text-slate-400 hidden xl:inline">
              AST & Static Vulnerability Scanner • Connected to GitHub
            </span>
          </div>

          <div className="flex items-center space-x-4">
            {/* LIVE / DEMO DATA INDICATOR BADGE */}
            <span
              title={isLive ? "Connected to live FastAPI backend" : "Backend unreachable - operating with local fallback dataset"}
              className={`px-2.5 py-1 rounded-full text-xs font-mono border flex items-center gap-1.5 cursor-pointer ${
                isLive
                  ? "bg-emerald-500/15 text-emerald-400 border-emerald-500/30"
                  : "bg-amber-500/15 text-amber-400 border-amber-500/30"
              }`}
              onClick={() => setIsSettingsOpen(true)}
            >
              <span className={`w-2 h-2 rounded-full ${isLive ? "bg-emerald-400 animate-pulse" : "bg-amber-400"}`}></span>
              {isLive ? "Live Data" : "Demo Data"}
            </span>

            {/* COMPUTED CRITICAL ISSUES PILL */}
            <span className="bg-red-500/15 text-red-400 border border-red-500/30 px-2.5 py-1 rounded-full text-xs font-medium flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-red-500 animate-pulse"></span>
              {openCriticalCount} critical issues
            </span>

            {/* SEARCH ICON (Cmd+K) */}
            <button
              onClick={() => setIsSearchOpen(true)}
              title="Global Search (Cmd/Ctrl+K)"
              className="p-1.5 text-slate-400 hover:text-white transition-colors"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
              </svg>
            </button>

            {/* NOTIFICATION BELL */}
            <div className="relative">
              <button
                onClick={() => setIsNotificationsOpen((prev) => !prev)}
                title="Notifications"
                className="p-1.5 text-slate-400 hover:text-white transition-colors block"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
                </svg>
                {notifications.length > 0 && (
                  <span className="absolute -top-1 -right-1 bg-cyan-400 text-slate-950 font-bold text-[10px] w-4 h-4 rounded-full flex items-center justify-center">
                    {notifications.length}
                  </span>
                )}
              </button>
            </div>

            <span className="text-xs text-slate-400 font-mono hidden sm:inline">@{user.username}</span>
          </div>
        </header>

        <main className="p-6 space-y-6 max-w-[1400px] mx-auto w-full">
          {/* ===================================================================== */}
          {/* TAB 1: DASHBOARD (REPOSITORY SCANNER & DUAL INPUT)                    */}
          {/* ===================================================================== */}
          {activeTab === "dashboard" && (
            <div className="space-y-6">
              <div className="bg-[#131B2E] border border-slate-800 rounded-xl p-6 shadow-xl space-y-6">
                <div>
                  <h2 className="text-xl font-semibold text-white">Scan your repository in seconds</h2>
                  <p className="text-slate-400 text-xs mt-1">Paste a link or upload your code. We'll do the rest.</p>
                </div>

                <div className="bg-[#0B0F17] border border-slate-800 rounded-lg p-5 grid grid-cols-1 lg:grid-cols-12 gap-6 items-center">
                  {/* LEFT INPUT: GITHUB OR ZIP SWITCHER */}
                  <div className="lg:col-span-6 space-y-4">
                    <div className="flex space-x-4 border-b border-slate-800 pb-2">
                      <button
                        onClick={() => setScanInputTab("github")}
                        className={`text-xs font-medium pb-2 border-b-2 transition-colors ${
                          scanInputTab === "github"
                            ? "border-cyan-400 text-cyan-400"
                            : "border-transparent text-slate-400 hover:text-white"
                        }`}
                      >
                        GitHub Repository
                      </button>
                      <button
                        onClick={() => setScanInputTab("zip")}
                        className={`text-xs font-medium pb-2 border-b-2 transition-colors ${
                          scanInputTab === "zip"
                            ? "border-cyan-400 text-cyan-400"
                            : "border-transparent text-slate-400 hover:text-white"
                        }`}
                      >
                        Upload .zip File
                      </button>
                    </div>

                    {/* GITHUB INPUT FORM */}
                    {scanInputTab === "github" ? (
                      <form
                        onSubmit={(e) => {
                          e.preventDefault();
                          runScan(localRepoInput);
                        }}
                        className="space-y-3"
                      >
                        <label className="text-xs text-slate-400 block font-medium">Paste your GitHub repository link</label>
                        <div className="flex items-center space-x-2">
                          <input
                            type="url"
                            value={localRepoInput}
                            onChange={(e) => setLocalRepoInput(e.target.value)}
                            placeholder="https://github.com/org/repo"
                            className="w-full bg-[#131B2E] border border-slate-700 rounded-md px-3 py-2 text-xs text-white focus:outline-none focus:border-cyan-500 font-mono"
                          />
                          <button
                            type="button"
                            onClick={() => localRepoInput && window.open(localRepoInput, "_blank")}
                            title="Open in GitHub in a new tab"
                            className="bg-slate-800 hover:bg-slate-700 border border-slate-700 text-cyan-400 px-3 py-2 rounded-md text-xs font-medium shrink-0 flex items-center gap-1 transition-colors"
                          >
                            Open ↗
                          </button>
                        </div>
                        <button
                          type="submit"
                          disabled={isScanning}
                          className="w-full bg-cyan-400 hover:bg-cyan-300 text-slate-950 font-bold py-2.5 rounded-md text-xs transition-colors flex items-center justify-center gap-1.5 shadow-lg shadow-cyan-500/10"
                        >
                          {isScanning ? "Analyzing Codebase..." : "Analyze Repository →"}
                        </button>
                      </form>
                    ) : (
                      /* ZIP FILE INPUT FORM */
                      <div className="space-y-3">
                        <label className="text-xs text-slate-400 block font-medium">Upload local project archive (.zip)</label>
                        <button
                          type="button"
                          onClick={() => document.getElementById("hidden-file-input").click()}
                          className="w-full bg-slate-800 hover:bg-slate-700 border border-slate-700 text-white font-medium py-2.5 rounded text-xs flex items-center justify-center gap-2 transition-colors"
                        >
                          Choose ZIP File from Disk...
                        </button>
                        {selectedFileName && (
                          <div className="text-[11px] text-cyan-400 font-mono">
                            ✓ Uploaded: <strong>{selectedFileName}</strong>
                          </div>
                        )}
                      </div>
                    )}

                    <p className="text-[11px] text-slate-500 flex items-center gap-1.5">
                      <svg className="w-3.5 h-3.5 text-cyan-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                      </svg>
                      We only read public code. No changes are made.
                    </p>
                  </div>

                  <div className="hidden lg:flex lg:col-span-1 justify-center text-slate-500 text-xs font-bold">OR</div>

                  {/* DRAG & DROP ZIP BOX */}
                  <div
                    onClick={() => document.getElementById("hidden-file-input").click()}
                    onDragOver={(e) => e.preventDefault()}
                    onDrop={handleFileDrop}
                    className="lg:col-span-5 border-2 border-dashed border-slate-800 hover:border-cyan-500/40 rounded-lg p-6 text-center bg-[#0F1623]/50 cursor-pointer transition-all space-y-2"
                  >
                    <svg className="w-8 h-8 text-slate-400 mx-auto" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                    </svg>
                    <p className="text-xs text-slate-300 font-medium">Drag & drop your .zip file here</p>
                    <span className="text-slate-500 text-[10px] block">or click anywhere inside this box</span>
                    <button type="button" className="bg-slate-800 border border-slate-700 text-slate-200 text-xs px-3 py-1.5 rounded-md font-medium">Choose ZIP File</button>
                    <span className="text-[10px] text-slate-500 block mt-1">Max file size: 500MB</span>
                  </div>
                </div>

                {/* SCANNING PROGRESS PIPELINE */}
                <div className="border-t border-slate-800/80 pt-4 space-y-3">
                  <div className="flex justify-between text-xs">
                    <span className="text-slate-300 font-medium">
                      Analyzing {stats.totalFiles} files from {user.username}/{user.repo}
                    </span>
                    <span className="text-cyan-400 font-bold">{scanProgress}%</span>
                  </div>
                  <div className="w-full bg-slate-800 h-2 rounded-full overflow-hidden">
                    <div className="bg-cyan-400 h-full transition-all duration-300" style={{ width: `${scanProgress}%` }}></div>
                  </div>

                  <ul className="text-xs space-y-1 text-slate-400 grid grid-cols-2 sm:grid-cols-4 gap-2 pt-1">
                    <li className={`flex items-center gap-1.5 ${scanProgress >= 25 ? "text-emerald-400" : "text-slate-500"}`}>
                      ✓ Reading code...
                    </li>
                    <li className={`flex items-center gap-1.5 ${scanProgress >= 50 ? "text-emerald-400" : "text-slate-500"}`}>
                      ✓ Detecting languages...
                    </li>
                    <li className={`flex items-center gap-1.5 ${scanProgress >= 75 ? "text-cyan-400 animate-pulse" : "text-slate-500"}`}>
                      ● Checking for problems...
                    </li>
                    <li className={`flex items-center gap-1.5 ${scanProgress >= 100 ? "text-emerald-400" : "text-slate-500"}`}>
                      ○ Report ready
                    </li>
                  </ul>
                </div>

                {/* RECENT SCANS HISTORY CHIPS */}
                <div className="pt-3 border-t border-slate-800/60">
                  <div className="flex items-center justify-between mb-3">
                    <span className="text-xs font-semibold text-slate-400">Recent Repository Scans</span>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {recentScans.map((item, idx) => (
                      <button
                        key={idx}
                        onClick={() => {
                          setLocalRepoInput(item.repo_url);
                          runScan(item.repo_url);
                        }}
                        className="bg-[#0B0F17] hover:bg-slate-800 border border-slate-800 px-3 py-1.5 rounded-lg flex items-center space-x-2 text-xs cursor-pointer transition-colors"
                      >
                        <span className={`w-2 h-2 rounded-full ${item.badgeColor}`}></span>
                        <span className="text-slate-200 font-medium">{item.name}</span>
                        <span className="text-slate-500 text-[10px]">{item.date}</span>
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* ===================================================================== */}
          {/* TAB 2: AI CODEBASE ANALYSIS (DETAILED ARCHITECTURE & PER-FILE CARDS)  */}
          {/* ===================================================================== */}
          {activeTab === "ai" && (
            <div className="space-y-6">
              <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 border-b border-slate-800 pb-4">
                <div>
                  <h2 className="text-xl font-bold text-white flex items-center gap-2">
                    <span className="text-cyan-400">✨</span> AI Codebase Intelligence & Module Decomposition
                  </h2>
                  <p className="text-xs text-slate-400 mt-0.5">Automated AST & NLP comprehension of project architecture, domain logic, and per-page purpose.</p>
                </div>
                <span className="text-xs bg-cyan-500/10 text-cyan-400 border border-cyan-500/30 px-3 py-1 rounded-md font-mono">
                  AST + Tree-Sitter NLP Engine
                </span>
              </div>

              {/* Scope Brief Card */}
              <div className="bg-[#131B2E] border border-slate-800 rounded-xl p-5 space-y-4 shadow-xl">
                <h3 className="font-bold text-white text-sm sm:text-base">Executive Architecture & Scope Brief</h3>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs">
                  <div className="bg-[#0B0F17] border border-slate-800 p-3.5 rounded-lg space-y-1.5">
                    <span class="text-slate-500 uppercase font-bold text-[10px]">Business Domain & Purpose</span>
                    <p className="text-slate-300">{aiSummary.intent}</p>
                  </div>
                  <div className="bg-[#0B0F17] border border-slate-800 p-3.5 rounded-lg space-y-1.5">
                    <span className="text-slate-500 uppercase font-bold text-[10px]">Detected Tech Stack</span>
                    <div className="flex flex-wrap gap-1.5 pt-1">
                      {aiSummary.techStack.map((tech) => (
                        <span key={tech} className="bg-slate-800 text-cyan-300 px-2 py-0.5 rounded text-[10px] font-mono border border-slate-700">
                          {tech}
                        </span>
                      ))}
                    </div>
                  </div>
                  <div className="bg-[#0B0F17] border border-slate-800 p-3.5 rounded-lg space-y-1.5">
                    <span className="text-slate-500 uppercase font-bold text-[10px]">Executive Assessment</span>
                    <p className="text-slate-300">{aiSummary.healthAssessment}</p>
                  </div>
                </div>
              </div>

              {/* Per-File Cards Filter Input */}
              <div className="flex items-center justify-between flex-wrap gap-3">
                <h3 className="font-semibold text-white text-sm">📁 Per-File & Per-Page Functional Decomposition ({filteredFileCards.length} modules)</h3>
                <div className="relative w-64">
                  <input
                    type="text"
                    value={aiSearchQuery}
                    onChange={(e) => setAiSearchQuery(e.target.value)}
                    placeholder="Filter modules by name or intent..."
                    className="bg-[#0B0F17] border border-slate-700 rounded-md px-3 py-1.5 text-xs text-white placeholder-slate-500 w-full focus:outline-none focus:border-cyan-500 font-mono"
                  />
                </div>
              </div>

              {/* 8+ Per-File Cards Grid */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {filteredFileCards.map((card) => (
                  <div key={card.id} className="bg-[#131B2E] border border-slate-800 rounded-xl p-4 space-y-2.5 shadow-lg">
                    <div className="flex justify-between items-start">
                      <span className="font-mono text-xs font-bold text-cyan-300">{card.file}</span>
                      <span className={`text-[10px] px-2 py-0.5 rounded border font-bold ${card.statusColor}`}>{card.status}</span>
                    </div>
                    <p className="text-xs text-slate-300">{card.role}</p>
                    <div className="bg-[#0B0F17] border border-slate-800 p-2.5 rounded text-[11px] text-slate-400">
                      <strong className="text-slate-200">Business Intent:</strong> {card.intent}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* ===================================================================== */}
          {/* TAB 3: DEBUGGING & ISSUE INSPECTOR (5 BUGS, EXPANDABLE & SYNCED)     */}
          {/* ===================================================================== */}
          {activeTab === "debug" && (
            <div className="space-y-4">
              <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                <h3 className="font-semibold text-white text-sm">
                  What to fix first <span className="text-slate-400 font-normal">(Top urgent repository bugs)</span>
                </h3>
                <div className="relative w-64">
                  <input
                    type="text"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    placeholder="Search by title or file name..."
                    className="bg-[#0B0F17] border border-slate-700 rounded-md pl-4 pr-3 py-1.5 text-xs text-white placeholder-slate-500 w-full focus:outline-none focus:border-cyan-500 font-mono"
                  />
                </div>
              </div>

              {/* Severity Filter Chips */}
              <div className="flex flex-wrap gap-2 text-xs">
                {["All", "Critical", "High", "Medium", "Low"].map((sev) => {
                  const isActive = debugSeverity === sev;
                  const count = sev === "All" ? bugs.length : bugs.filter((b) => b.severity === sev).length;
                  return (
                    <button
                      key={sev}
                      onClick={() => setDebugSeverity(sev)}
                      className={`px-3 py-1 rounded-md transition-colors font-medium ${
                        isActive
                          ? "bg-cyan-500/20 text-cyan-400 border border-cyan-500/40"
                          : "bg-slate-800/60 text-slate-400 hover:bg-slate-800"
                      }`}
                    >
                      {sev} ({count})
                    </button>
                  );
                })}
              </div>

              {/* Bugs Table */}
              <div className="overflow-x-auto bg-[#131B2E] border border-slate-800 rounded-xl p-3 shadow-lg">
                <table className="w-full text-left text-xs min-w-[800px]">
                  <thead>
                    <tr className="border-b border-slate-800 text-slate-400">
                      <th className="py-2.5 px-3 w-8">#</th>
                      <th className="py-2.5 px-3 w-32">Bug ID</th>
                      <th className="py-2.5 px-3">Title</th>
                      <th className="py-2.5 px-3 w-24">Severity</th>
                      <th className="py-2.5 px-3 w-32">Priority</th>
                      <th className="py-2.5 px-3 w-48">File & Line</th>
                      <th className="py-2.5 px-3 w-24">Status</th>
                      <th className="py-2.5 px-3 w-24">Similar</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/50">
                    {filteredBugs.map((bug, idx) => {
                      const isExpanded = expandedBugId === bug.id;
                      const isResolved = bug.status === "Resolved";

                      return (
                        <React.Fragment key={bug.id}>
                          <tr
                            onClick={() => setExpandedBugId(isExpanded ? null : bug.id)}
                            className="hover:bg-slate-800/40 cursor-pointer transition-colors bg-slate-800/20"
                          >
                            <td className="py-3 px-3 text-slate-500">{idx + 1}</td>
                            <td className="py-3 px-3 font-mono text-slate-300">{bug.id}</td>
                            <td className={`py-3 px-3 font-medium ${isResolved ? "line-through text-slate-500" : "text-white"}`}>
                              {bug.title}
                            </td>
                            <td className="py-3 px-3">
                              <span
                                className={`px-2 py-0.5 rounded text-[11px] font-medium ${
                                  bug.severity === "Critical"
                                    ? "bg-red-500/10 text-red-400 border border-red-500/30"
                                    : bug.severity === "High"
                                    ? "bg-amber-500/10 text-amber-400 border border-amber-500/30"
                                    : "bg-yellow-500/10 text-yellow-400 border border-yellow-500/30"
                                }`}
                              >
                                {bug.severity}
                              </span>
                            </td>
                            <td className="py-3 px-3 font-medium text-red-400">{bug.priority}</td>
                            <td className="py-3 px-3 font-mono text-slate-400">
                              {bug.file}:{bug.line}
                            </td>
                            <td className="py-3 px-3">
                              <span
                                className={`px-2 py-0.5 rounded text-[10px] border ${
                                  isResolved
                                    ? "text-emerald-300 border-emerald-500/40 bg-emerald-500/20"
                                    : bug.status === "Open"
                                    ? "text-emerald-400 border-emerald-500/30 bg-emerald-500/10"
                                    : "text-blue-400 border-blue-500/30 bg-blue-500/10"
                                }`}
                              >
                                {bug.status}
                              </span>
                            </td>
                            <td className="py-3 px-3 text-slate-400 flex items-center justify-between">
                              <span>{bug.similarCount}</span>
                              <span className="text-xs">{isExpanded ? "⌃" : "⌄"}</span>
                            </td>
                          </tr>

                          {/* EXPANDABLE INSPECTOR DRAWER */}
                          {isExpanded && (
                            <tr>
                              <td colSpan="8" className="p-4 bg-[#0B0F17] border-t border-slate-800">
                                <div className="space-y-4">
                                  <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                                    {/* Code Snippet */}
                                    <div className="bg-[#0F1623] border border-slate-800 rounded-lg p-3 font-mono text-[11px] leading-relaxed">
                                      <div className="text-slate-500 mb-2 flex items-center justify-between">
                                        <span>Code snippet &mdash; {bug.file}:{bug.line}</span>
                                        <button
                                          onClick={() => navigator.clipboard.writeText(`${bug.file}:${bug.line}`)}
                                          className="text-cyan-400 hover:underline text-[10px]"
                                        >
                                          📋 Copy location
                                        </button>
                                      </div>
                                      <div className="space-y-1">
                                        {bug.codeSnippet.map((line) => (
                                          <div
                                            key={line.num}
                                            className={
                                              line.isErr
                                                ? "bg-red-500/20 border-l-2 border-red-500 text-red-200 pl-2 py-0.5"
                                                : "text-slate-500 pl-2"
                                            }
                                          >
                                            <span className="inline-block w-8 text-slate-600 select-none">{line.num}</span>
                                            <span>{line.text}</span>
                                          </div>
                                        ))}
                                      </div>
                                    </div>

                                    {/* AI Fix Explanation & Diff Box */}
                                    <div className="space-y-3 text-xs">
                                      <div>
                                        <h5 className="font-semibold text-slate-300 mb-0.5">What's wrong</h5>
                                        <p className="text-slate-400">{bug.wrong}</p>
                                      </div>
                                      <div>
                                        <h5 className="font-semibold text-slate-300 mb-0.5">Why it matters</h5>
                                        <p className="text-slate-400">{bug.matter}</p>
                                      </div>
                                      <div className="bg-[#0F1623] border border-slate-800 p-2.5 rounded">
                                        <h5 className="font-semibold text-slate-200 mb-1">Suggested Fix</h5>
                                        <div className="font-mono text-[11px] bg-[#0B0F17] p-2 rounded border border-slate-800">
                                          <div className="text-red-400">{bug.suggestedFix.remove}</div>
                                          <div className="text-emerald-400 whitespace-pre-line">{bug.suggestedFix.add}</div>
                                        </div>
                                      </div>
                                    </div>
                                  </div>

                                  {/* REMARKS TEXTAREA (DEBOUNCED AUTO-SAVE) */}
                                  <div className="bg-[#0F1623] border border-slate-800 rounded-lg p-3 space-y-1">
                                    <label className="text-xs text-cyan-400 font-semibold flex items-center justify-between">
                                      <span>📝 Software Engineer Remarks & PM Status Note</span>
                                      <span className="text-[10px] text-slate-500 font-normal">Real-time sync to Tab 4 Report & PDF</span>
                                    </label>
                                    <textarea
                                      rows="2"
                                      value={bug.engineerNotes || ""}
                                      onChange={(e) => updateBugNotes(bug.id, e.target.value)}
                                      placeholder="Type engineering remarks or status updates..."
                                      className="w-full bg-[#0B0F17] border border-slate-700 rounded p-2 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-cyan-500 font-sans"
                                    />
                                  </div>

                                  {/* RESOLVE BUTTON */}
                                  <button
                                    onClick={() => toggleResolveBug(bug.id)}
                                    className={`px-4 py-2 rounded text-xs font-semibold transition-colors ${
                                      isResolved
                                        ? "bg-emerald-600 text-white shadow-lg shadow-emerald-600/20"
                                        : "bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700"
                                    }`}
                                  >
                                    {isResolved ? "✓ Marked as Resolved" : "Mark as Resolved"}
                                  </button>
                                </div>
                              </td>
                            </tr>
                          )}
                        </React.Fragment>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* ===================================================================== */}
          {/* TAB 4: REPORT (AI SUMMARY & REAL-TIME ENGINEER NOTES & PRINT)          */}
          {/* ===================================================================== */}
          {activeTab === "report" && (
            <div className="space-y-6">
              <div className="flex justify-between items-center border-b border-slate-800 pb-3">
                <div>
                  <h2 className="text-xl font-bold text-white flex items-center gap-2">
                    <span>📄</span> Code Resolution & PM Client Audit Report
                  </h2>
                  <p className="text-xs text-slate-400 mt-0.5">Includes AI Spark Architecture summary and live software engineer remarks.</p>
                </div>
                <button
                  onClick={() => window.print()}
                  className="no-print bg-cyan-400 hover:bg-cyan-300 text-slate-950 font-bold px-4 py-2 rounded-lg text-xs flex items-center gap-1.5 shadow-lg shadow-cyan-500/10"
                >
                  🖨️ Download Report (PDF)
                </button>
              </div>

              {/* Progress Summary Card */}
              <div className="bg-[#131B2E] border border-slate-800 p-4 rounded-xl flex items-center justify-between">
                <div>
                  <span className="text-xs text-slate-400">Total Resolution Progress</span>
                  <div className="text-sm font-bold text-white mt-0.5">
                    {resolvedCount} of {bugs.length} issues fixed ({resolutionPercentage}%)
                  </div>
                </div>
                <div className="w-48 bg-slate-800 h-2.5 rounded-full overflow-hidden">
                  <div className="bg-cyan-400 h-full transition-all duration-300" style={{ width: `${resolutionPercentage}%` }}></div>
                </div>
              </div>

              {/* AI SPARK SUMMARY */}
              <div className="bg-[#131B2E] border border-slate-800 rounded-xl p-5 space-y-3 shadow-xl">
                <div className="flex items-center space-x-2">
                  <span className="text-cyan-400 text-base">✨</span>
                  <h3 className="font-bold text-white text-sm">AI Codebase Intelligence Summary</h3>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs">
                  <div className="bg-[#0B0F17] p-3 rounded border border-slate-800">
                    <span className="text-slate-500 uppercase text-[10px] font-bold">Scope & Purpose</span>
                    <p className="text-slate-300 mt-1">{aiSummary.intent}</p>
                  </div>
                  <div className="bg-[#0B0F17] p-3 rounded border border-slate-800">
                    <span className="text-slate-500 uppercase text-[10px] font-bold">Detected Tech Stack</span>
                    <div className="flex flex-wrap gap-1 mt-1">
                      {aiSummary.techStack.map((tech) => (
                        <span key={tech} className="bg-slate-800 text-cyan-300 text-[10px] font-mono px-1.5 py-0.5 rounded border border-slate-700">
                          {tech}
                        </span>
                      ))}
                    </div>
                  </div>
                  <div className="bg-[#0B0F17] p-3 rounded border border-slate-800">
                    <span className="text-slate-500 uppercase text-[10px] font-bold">Executive Assessment</span>
                    <p className="text-slate-300 mt-1">{aiSummary.healthAssessment}</p>
                  </div>
                </div>
              </div>

              {/* AUDIT TABLE WITH LIVE REMARKS */}
              <div className="bg-[#131B2E] border border-slate-800 rounded-xl overflow-hidden print-card shadow-lg">
                <table className="w-full text-left text-xs min-w-[750px]">
                  <thead className="bg-[#0F1623] text-slate-400 border-b border-slate-800">
                    <tr>
                      <th className="p-3 w-10">#</th>
                      <th className="p-3 w-44">File & Line</th>
                      <th className="p-3 w-56">Issue Description</th>
                      <th className="p-3 w-20">Severity</th>
                      <th className="p-3 w-28">Fix Status</th>
                      <th className="p-3">Software Engineer Remarks / Client Notes</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/50">
                    {bugs.map((bug, idx) => (
                      <tr key={bug.id} className="hover:bg-slate-800/30">
                        <td className="p-3 text-slate-500">{idx + 1}</td>
                        <td className="p-3 font-mono text-cyan-300">
                          {bug.file}:{bug.line}
                        </td>
                        <td className="p-3 text-white font-medium">{bug.title}</td>
                        <td className="p-3">
                          <span
                            className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                              bug.severity === "Critical"
                                ? "text-red-400 bg-red-500/10 border border-red-500/30"
                                : "text-amber-400 bg-amber-500/10"
                            }`}
                          >
                            {bug.severity}
                          </span>
                        </td>
                        <td className="p-3">
                          <span
                            className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                              bug.status === "Resolved"
                                ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40"
                                : "bg-red-500/10 text-red-400 border border-red-500/30"
                            }`}
                          >
                            {bug.status === "Resolved" ? "✓ Fixed" : "Open"}
                          </span>
                        </td>
                        <td className="p-3 text-slate-300 font-sans italic bg-[#0B0F17]/40">
                          {bug.engineerNotes ? `"${bug.engineerNotes}"` : <span className="text-slate-600 not-italic">No note added yet</span>}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </main>

        {/* Footer */}
        <footer className="no-print bg-[#0F1623] border-t border-slate-800 p-4 px-6 flex flex-col md:flex-row items-center justify-between text-xs text-slate-400 space-y-3 md:space-y-0 mt-auto">
          <div className="flex items-center space-x-4 flex-wrap gap-y-2">
            <a href={user.repoUrl} target="_blank" rel="noreferrer" className="font-semibold text-white hover:text-cyan-400 flex items-center gap-1.5">
              <span>{user.username}/{user.repo}</span>
              <span className="bg-slate-800 text-[10px] px-1.5 py-0.5 rounded text-slate-400 border border-slate-700">Public ↗</span>
            </a>
            <span>Files scanned: <strong className="text-slate-200">{stats.totalFiles}</strong></span>
            <span>Total LOC: <strong className="text-slate-200">{stats.linesOfCode?.toLocaleString()}</strong></span>
          </div>

          <button
            onClick={() => {
              setActiveTab("dashboard");
              window.scrollTo({ top: 0, behavior: "smooth" });
            }}
            className="bg-cyan-400 hover:bg-cyan-300 text-slate-950 font-bold px-4 py-1.5 rounded-md text-xs shrink-0"
          >
            Scan another repository ↑
          </button>
        </footer>
      </div>

      {/* ===================================================================== */}
      {/* SETTINGS MODAL                                                        */}
      {/* ===================================================================== */}
      {isSettingsOpen && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-[#131B2E] border border-slate-800 rounded-xl max-w-md w-full p-6 space-y-5 shadow-2xl">
            <div className="flex justify-between items-center border-b border-slate-800 pb-3">
              <h3 className="font-bold text-white text-base">Backend API Settings</h3>
              <button onClick={() => setIsSettingsOpen(false)} className="text-slate-400 hover:text-white">✕</button>
            </div>
            <form onSubmit={handleSaveSettings} className="space-y-4">
              <div>
                <label className="text-xs text-slate-300 block mb-1 font-medium">FastAPI Server Base Endpoint URL</label>
                <input
                  type="url"
                  value={settingsUrlInput}
                  onChange={(e) => setSettingsUrlInput(e.target.value)}
                  required
                  placeholder="http://localhost:8000/api"
                  className="w-full bg-[#0B0F17] border border-slate-700 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:border-cyan-500 font-mono"
                />
                <p className="text-[11px] text-slate-500 mt-1">Changes take effect immediately across all tabs & end-to-end calls.</p>
              </div>

              {testConnStatus && (
                <div className={`p-2.5 rounded text-xs border ${
                  testConnStatus === "testing"
                    ? "bg-slate-800 text-slate-300 border-slate-700"
                    : testConnStatus === "success"
                    ? "bg-emerald-500/20 text-emerald-300 border-emerald-500/40"
                    : "bg-amber-500/20 text-amber-300 border-amber-500/40"
                }`}>
                  {testConnStatus === "testing" && "Testing endpoint connection..."}
                  {testConnStatus === "success" && "✓ Backend server connected successfully! Live data mode active."}
                  {testConnStatus === "failed" && "⚠️ Backend server unreachable. Demo fallback mode will be used."}
                </div>
              )}

              <div className="flex justify-end space-x-3 pt-2">
                <button
                  type="button"
                  onClick={handleTestConnection}
                  className="bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 px-3 py-2 rounded-lg text-xs"
                >
                  Test Connection
                </button>
                <button
                  type="submit"
                  className="bg-cyan-400 hover:bg-cyan-300 text-slate-950 font-bold px-4 py-2 rounded-lg text-xs"
                >
                  Save Endpoint
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ===================================================================== */}
      {/* HELP & SHORTCUTS MODAL                                                */}
      {/* ===================================================================== */}
      {isHelpOpen && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-[#131B2E] border border-slate-800 rounded-xl max-w-lg w-full p-6 space-y-4 shadow-2xl">
            <div className="flex justify-between items-center border-b border-slate-800 pb-3">
              <h3 className="font-bold text-white text-base">Keyboard Shortcuts & Usage Guide</h3>
              <button onClick={() => setIsHelpOpen(false)} className="text-slate-400 hover:text-white">✕</button>
            </div>
            <div className="space-y-3 text-xs">
              <div className="bg-[#0B0F17] p-3 rounded-lg border border-slate-800 space-y-2">
                <span className="text-cyan-400 font-bold">Global Shortcuts</span>
                <div className="flex justify-between items-center text-slate-300">
                  <span>Open Search Modal</span>
                  <kbd className="bg-slate-800 border border-slate-700 px-2 py-0.5 rounded text-[10px] font-mono">Cmd/Ctrl + K</kbd>
                </div>
                <div className="flex justify-between items-center text-slate-300">
                  <span>Close Active Modal</span>
                  <kbd className="bg-slate-800 border border-slate-700 px-2 py-0.5 rounded text-[10px] font-mono">Esc</kbd>
                </div>
              </div>
              <div className="bg-[#0B0F17] p-3 rounded-lg border border-slate-800 space-y-1.5">
                <span className="text-cyan-400 font-bold">Feature Highlights</span>
                <p className="text-slate-300">• Shared App State: Resolving bugs in Tab 3 updates Tab 4 instantly.</p>
                <p className="text-slate-300">• Auto-Save Notes: Editing engineer remarks auto-saves with debounced timer.</p>
                <p className="text-slate-300">• Live & Fallback: Automatic silent fallback to demo data if FastAPI is offline.</p>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ===================================================================== */}
      {/* GLOBAL SEARCH MODAL (Cmd+K)                                           */}
      {/* ===================================================================== */}
      {isSearchOpen && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-start justify-center pt-20 p-4">
          <div className="bg-[#131B2E] border border-slate-800 rounded-xl max-w-xl w-full p-4 space-y-3 shadow-2xl">
            <div className="flex items-center space-x-2 border-b border-slate-800 pb-3">
              <svg className="w-5 h-5 text-cyan-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
              </svg>
              <input
                type="text"
                autoFocus
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search bugs by ID, title, or file location..."
                className="w-full bg-transparent text-sm text-white placeholder-slate-500 focus:outline-none font-mono"
              />
              <button onClick={() => setIsSearchOpen(false)} className="text-slate-400 hover:text-white text-xs bg-slate-800 px-2 py-1 rounded">Esc</button>
            </div>

            <div className="max-h-80 overflow-y-auto space-y-2">
              {globalSearchBugs.length > 0 ? (
                globalSearchBugs.map((b) => (
                  <div
                    key={b.id}
                    onClick={() => {
                      setExpandedBugId(b.id);
                      setActiveTab("debug");
                      setIsSearchOpen(false);
                    }}
                    className="bg-[#0B0F17] hover:bg-slate-800 p-3 rounded-lg border border-slate-800 cursor-pointer flex justify-between items-center transition-colors"
                  >
                    <div>
                      <span className="font-mono text-xs text-cyan-400 font-bold">{b.id} &mdash; {b.file}:{b.line}</span>
                      <p className="text-xs text-white font-medium">{b.title}</p>
                    </div>
                    <span className="text-[10px] bg-red-500/10 text-red-400 border border-red-500/30 px-2 py-0.5 rounded font-bold">{b.severity}</span>
                  </div>
                ))
              ) : searchQuery ? (
                <div className="p-4 text-center text-slate-500 text-xs">No matching issues found for "{searchQuery}"</div>
              ) : (
                <div className="p-4 text-center text-slate-500 text-xs">Type a keyword to search across all bugs and code files...</div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ===================================================================== */}
      {/* NOTIFICATION DRAWER                                                   */}
      {/* ===================================================================== */}
      {isNotificationsOpen && (
        <div className="absolute right-6 top-16 w-80 bg-[#131B2E] border border-slate-800 rounded-xl p-4 space-y-3 shadow-2xl z-40">
          <div className="flex justify-between items-center border-b border-slate-800 pb-2">
            <h4 className="font-bold text-white text-xs">Critical Issue Alerts</h4>
            <button onClick={() => setIsNotificationsOpen(false)} className="text-slate-400 hover:text-white text-xs">✕</button>
          </div>
          <div className="space-y-2">
            {notifications.map((n) => (
              <div
                key={n.id}
                onClick={() => {
                  setExpandedBugId(n.bugId);
                  setActiveTab("debug");
                  setIsNotificationsOpen(false);
                }}
                className="bg-[#0B0F17] hover:bg-slate-800 p-2.5 rounded-lg border border-slate-800 text-xs space-y-1 cursor-pointer transition-colors"
              >
                <div className="flex justify-between text-cyan-400 font-bold">
                  <span>{n.title}</span>
                  <span className="text-slate-500 text-[10px] font-normal">{n.time}</span>
                </div>
                <p className="text-slate-300 text-[11px]">{n.message}</p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}