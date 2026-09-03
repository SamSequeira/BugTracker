// src/components/Tabs/TabRepositoryScanner.jsx - Tab 1: Repository Scanner & Overview Dashboard
import React, { useState } from "react";
import { useBugTracker } from "../../useBugTracker.jsx";

// Error type → human-readable label
const ERROR_LABELS = {
  private: "Private Repository",
  not_found: "Repository Not Found",
  invalid_token: "Invalid GitHub Token",
  rate_limited: "GitHub API Rate Limit",
  invalid_url: "Invalid URL",
  no_backend: "Backend Server Unavailable",
  unknown: "Scan Error",
};

export default function TabRepositoryScanner() {
  const {
    repoUrl,
    setRepoUrl,
    isScanning,
    scanProgress,
    scanStage,
    scanCompleted,
    scanError,
    clearScanError,
    githubToken,
    saveGithubToken,
    runScan,
    recentScans,
    loadRecentScan,
    stats,
    repoMeta,
    highUnresolvedCount,
    resolvedCount,
    resolutionPercentage,
    setActiveTab,
  } = useBugTracker();

  const [inputMode, setInputMode] = useState("github");
  const [selectedFile, setSelectedFile] = useState(null);
  const [isDragOver, setIsDragOver] = useState(false);
  const [tokenInput, setTokenInput] = useState(githubToken || "");
  const [showTokenField, setShowTokenField] = useState(false);
  const [tokenSaved, setTokenSaved] = useState(false);

  // Show token field automatically when hitting a private/not_found error
  const needsToken = scanError && (scanError.type === "private" || scanError.type === "not_found" || scanError.type === "invalid_token");

  const handleSaveToken = () => {
    saveGithubToken(tokenInput.trim());
    setTokenSaved(true);
    setTimeout(() => setTokenSaved(false), 2000);
    clearScanError();
  };

  const handleClearToken = () => {
    setTokenInput("");
    saveGithubToken("");
    setTokenSaved(false);
  };

  const handleScanSubmit = (e) => {
    e.preventDefault();
    if (inputMode === "github") {
      if (!repoUrl.trim()) return;
      runScan(repoUrl.trim(), false);
    } else {
      if (!selectedFile) return;
      const formData = new FormData();
      formData.append("file", selectedFile);
      runScan(formData, true);
    }
  };

  const handleFileChange = (e) => {
    const file = e.target.files?.[0];
    if (file) setSelectedFile(file);
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setIsDragOver(false);
    const file = e.dataTransfer.files?.[0];
    if (file) {
      setSelectedFile(file);
      setInputMode("zip");
    }
  };

  return (
    <div className="space-y-6 animate-fade-in max-w-7xl mx-auto">

      {/* ── Error Alert Banner ─────────────────────────────────────────────── */}
      {scanError && (
        <div className="bg-red-500/10 border border-red-500/40 rounded-2xl p-4 flex flex-col gap-3 shadow-lg animate-fade-in">
          <div className="flex items-start gap-4">
            <div className="p-2 bg-red-500/20 rounded-xl shrink-0">
              <svg className="w-5 h-5 text-red-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2"
                  d="M12 9v2m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
              </svg>
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-1">
                <span className="text-xs font-bold text-red-400 uppercase tracking-wider">
                  {ERROR_LABELS[scanError.type] || "Scan Error"}
                </span>
                {(scanError.type === "private" || scanError.type === "not_found") && (
                  <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-red-500/20 text-red-300 border border-red-500/30">
                    🔒 {scanError.type === "private" ? "Private" : "Not Found / Private"}
                  </span>
                )}
                {scanError.type === "rate_limited" && (
                  <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-amber-500/20 text-amber-300 border border-amber-500/30">
                    ⏱ Rate Limited
                  </span>
                )}
              </div>
              <p className="text-sm text-red-200 leading-relaxed">{scanError.message}</p>
              {scanError.type === "rate_limited" && (
                <p className="text-xs text-slate-400 mt-1.5">
                  GitHub allows 60 unauthenticated API requests per hour. Adding a Personal Access Token raises this to 5,000/hour.
                </p>
              )}
            </div>
            <button
              onClick={clearScanError}
              className="text-slate-400 hover:text-white p-1.5 rounded-lg hover:bg-slate-800 transition-colors shrink-0"
              title="Dismiss"
            >
              ✕
            </button>
          </div>

          {/* GitHub Token input — shown for private/not_found/rate_limited errors */}
          {(needsToken || scanError.type === "rate_limited") && (
            <div className="bg-[#0B0F17] border border-slate-700 rounded-xl p-4 space-y-3">
              <div className="flex items-center gap-2">
                <span className="text-xs font-bold text-slate-200">🔑 Add GitHub Personal Access Token</span>
                <span className="text-[10px] text-slate-500">to scan private repos or raise rate limits</span>
              </div>
              <p className="text-[11px] text-slate-400 leading-relaxed">
                Create a token at{" "}
                <a
                  href="https://github.com/settings/tokens/new?scopes=repo&description=BugTracker"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-cyan-400 hover:underline"
                >
                  github.com/settings/tokens
                </a>{" "}
                with the <code className="bg-slate-800 px-1 rounded text-cyan-300">repo</code> scope. Your token is stored in this browser session only — never sent to any server.
              </p>
              <div className="flex gap-2">
                <input
                  type="password"
                  value={tokenInput}
                  onChange={(e) => { setTokenInput(e.target.value); setTokenSaved(false); }}
                  placeholder="ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
                  className="flex-1 bg-[#131B2E] border border-slate-700 rounded-lg px-3 py-2 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-cyan-400 font-mono"
                />
                <button
                  type="button"
                  onClick={handleSaveToken}
                  disabled={!tokenInput.trim()}
                  className="bg-cyan-400 hover:bg-cyan-300 text-slate-950 font-bold px-4 py-2 rounded-lg text-xs transition-all disabled:opacity-50 shrink-0"
                >
                  {tokenSaved ? "✓ Saved" : "Save & Retry"}
                </button>
                {githubToken && (
                  <button
                    type="button"
                    onClick={handleClearToken}
                    className="bg-slate-700 hover:bg-slate-600 text-slate-200 font-bold px-3 py-2 rounded-lg text-xs transition-all shrink-0"
                    title="Clear token"
                  >
                    ✕
                  </button>
                )}
              </div>
              {tokenSaved && (
                <p className="text-[11px] text-emerald-400">
                  ✓ Token saved. Click "Analyze Repository" again to retry the scan.
                </p>
              )}
            </div>
          )}
        </div>
      )}

      {/* GitHub token active indicator (shown when no error but token is set) */}
      {githubToken && !scanError && (
        <div className="bg-emerald-500/10 border border-emerald-500/30 rounded-xl px-4 py-2 flex items-center justify-between animate-fade-in">
          <div className="flex items-center gap-2 text-xs text-emerald-300">
            <span>🔑</span>
            <span>GitHub token active — private repositories enabled</span>
          </div>
          <button
            type="button"
            onClick={() => { setShowTokenField(!showTokenField); }}
            className="text-[11px] text-slate-400 hover:text-white transition-colors"
          >
            {showTokenField ? "Hide" : "Change token"}
          </button>
        </div>
      )}

      {/* Inline token editor when clicking "Change token" */}
      {githubToken && !scanError && showTokenField && (
        <div className="bg-[#131B2E] border border-slate-700 rounded-xl p-4 space-y-3 animate-fade-in">
          <span className="text-xs font-bold text-slate-200">Update GitHub Token</span>
          <div className="flex gap-2">
            <input
              type="password"
              value={tokenInput}
              onChange={(e) => { setTokenInput(e.target.value); setTokenSaved(false); }}
              placeholder="ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
              className="flex-1 bg-[#0B0F17] border border-slate-700 rounded-lg px-3 py-2 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-cyan-400 font-mono"
            />
            <button
              type="button"
              onClick={handleSaveToken}
              disabled={!tokenInput.trim()}
              className="bg-cyan-400 hover:bg-cyan-300 text-slate-950 font-bold px-4 py-2 rounded-lg text-xs transition-all disabled:opacity-50"
            >
              {tokenSaved ? "✓ Saved" : "Update"}
            </button>
            <button
              type="button"
              onClick={handleClearToken}
              className="bg-slate-700 hover:bg-red-900/60 text-slate-200 font-bold px-3 py-2 rounded-lg text-xs transition-all"
            >
              Remove
            </button>
          </div>
        </div>
      )}

      {/* ── Repo Meta Banner (shown after successful scan) ─────────────────── */}
      {scanCompleted && repoMeta && !scanError && (
        <div className="bg-emerald-500/10 border border-emerald-500/30 rounded-2xl p-4 flex flex-wrap items-center gap-4 shadow-md animate-fade-in">
          <div className="p-2 bg-emerald-500/20 rounded-xl shrink-0">
            <svg className="w-5 h-5 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 13l4 4L19 7" />
            </svg>
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-bold text-emerald-300 font-mono">{repoMeta.fullName}</p>
            <p className="text-xs text-slate-400 truncate">{repoMeta.description || "No description"}</p>
          </div>
          <div className="flex flex-wrap gap-3 text-xs text-slate-300 font-mono shrink-0">
            <span>⭐ {(repoMeta.stars || 0).toLocaleString()}</span>
            <span>🍴 {repoMeta.forks || 0}</span>
            <span>📁 {repoMeta.totalFiles} files</span>
            <span>🌿 {repoMeta.defaultBranch}</span>
          </div>
        </div>
      )}

      {/* ── Top Scanner Card ───────────────────────────────────────────────── */}
      <div className="bg-[#131B2E] border border-slate-800 rounded-2xl p-6 sm:p-8 space-y-6 shadow-xl relative overflow-hidden">
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 border-b border-slate-800/80 pb-5">
          <div>
            <span className="text-[11px] font-mono uppercase tracking-wider text-cyan-400 font-semibold bg-cyan-500/10 px-2.5 py-1 rounded-full border border-cyan-500/20">
              Tab 1 • Codebase Scanner
            </span>
            <h2 className="text-xl sm:text-2xl font-bold text-white tracking-tight mt-2">
              Automated Code Security & AST Scanner
            </h2>
            <p className="text-xs text-slate-400 mt-1">
              Paste any <strong className="text-white">GitHub URL</strong> — public repos work instantly. Add a{" "}
              <button
                type="button"
                onClick={() => setShowTokenField(true)}
                className="text-cyan-400 hover:underline font-semibold"
              >
                GitHub token
              </button>{" "}
              to scan private repositories.
            </p>
          </div>

          <div className="bg-[#0B0F17] p-1 rounded-xl border border-slate-800 flex space-x-1 shrink-0">
            <button
              type="button"
              onClick={() => setInputMode("github")}
              className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-colors cursor-pointer ${inputMode === "github"
                ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/30"
                : "text-slate-400 hover:text-white"
                }`}
            >
              GitHub URL
            </button>
            <button
              type="button"
              onClick={() => setInputMode("zip")}
              className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-colors cursor-pointer ${inputMode === "zip"
                ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/30"
                : "text-slate-400 hover:text-white"
                }`}
            >
              ZIP Archive
            </button>
          </div>
        </div>

        {/* Scan Input Form */}
        <form onSubmit={handleScanSubmit} className="space-y-4">
          {inputMode === "github" ? (
            <div>
              <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                Target Repository URL
                <span className="ml-2 text-[10px] font-normal text-slate-500">(public repos only)</span>
              </label>
              <div className="flex flex-col sm:flex-row gap-3">
                <div className="relative flex-1">
                  <input
                    type="url"
                    required
                    value={repoUrl}
                    onChange={(e) => { setRepoUrl(e.target.value); clearScanError(); }}
                    placeholder="https://github.com/owner/repo"
                    className={`w-full bg-[#0B0F17] border rounded-xl px-4 py-3 text-xs sm:text-sm text-white placeholder-slate-500 focus:outline-none font-mono transition-colors ${scanError ? "border-red-500/50 focus:border-red-400" : "border-slate-700 focus:border-cyan-400"
                      }`}
                  />
                  {repoUrl && (
                    <a
                      href={repoUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="absolute right-3 top-3 text-[11px] text-cyan-400 hover:text-cyan-300 font-medium flex items-center gap-1 bg-[#131B2E] px-2 py-0.5 rounded border border-slate-700"
                    >
                      <span>Open</span><span>↗</span>
                    </a>
                  )}
                </div>

                <button
                  type="submit"
                  disabled={isScanning}
                  className="bg-cyan-400 hover:bg-cyan-300 text-slate-950 font-bold px-6 py-3 rounded-xl text-xs sm:text-sm transition-all flex items-center justify-center gap-2 shadow-lg shadow-cyan-500/10 cursor-pointer disabled:opacity-60 shrink-0"
                >
                  {isScanning ? (
                    <>
                      <div className="w-4 h-4 border-2 border-slate-950 border-t-transparent rounded-full animate-spin"></div>
                      <span>Scanning...</span>
                    </>
                  ) : (
                    <span>Analyze Repository →</span>
                  )}
                </button>
              </div>
            </div>
          ) : (
            <div>
              <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                Project ZIP Archive
                <span className="ml-2 text-[10px] font-normal text-slate-500">(requires backend on localhost:8000)</span>
              </label>
              <input
                type="file"
                id="zip-file-input"
                accept=".zip,.tar,.gz,.rar,.7z"
                className="hidden"
                onChange={handleFileChange}
              />
              <div
                onDrop={handleDrop}
                onDragOver={(e) => { e.preventDefault(); setIsDragOver(true); }}
                onDragLeave={() => setIsDragOver(false)}
                onClick={() => document.getElementById("zip-file-input").click()}
                className={`border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-all ${isDragOver
                  ? "border-cyan-400 bg-cyan-500/10"
                  : selectedFile
                    ? "border-emerald-500/50 bg-[#0B0F17]"
                    : "border-slate-700 hover:border-cyan-500/40 bg-[#0B0F17]/60"
                  }`}
              >
                {selectedFile ? (
                  <div className="space-y-2">
                    <div className="text-2xl">📦</div>
                    <div className="text-xs font-bold text-emerald-400 font-mono">
                      {selectedFile.name} ({(selectedFile.size / 1024 / 1024).toFixed(2)} MB)
                    </div>
                    <p className="text-[11px] text-slate-400">Click to replace or click Start Scan below</p>
                  </div>
                ) : (
                  <div className="space-y-2">
                    <svg className="w-8 h-8 text-cyan-400 mx-auto" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2"
                        d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                    </svg>
                    <p className="text-xs font-semibold text-white">
                      Drag & Drop .ZIP here, or <span className="text-cyan-400 underline">Browse Files</span>
                    </p>
                    <p className="text-[10px] text-slate-500">Supports Python, JavaScript, TypeScript, Go, Java</p>
                  </div>
                )}
              </div>

              {selectedFile && (
                <button
                  type="submit"
                  disabled={isScanning}
                  className="w-full mt-3 bg-cyan-400 hover:bg-cyan-300 text-slate-950 font-bold py-2.5 rounded-xl text-xs transition-all flex items-center justify-center gap-2 cursor-pointer shadow-lg shadow-cyan-500/10 disabled:opacity-60"
                >
                  {isScanning ? (
                    <>
                      <div className="w-4 h-4 border-2 border-slate-950 border-t-transparent rounded-full animate-spin"></div>
                      <span>Analyzing Archive...</span>
                    </>
                  ) : (
                    <span>Start Archive Scan →</span>
                  )}
                </button>
              )}
            </div>
          )}
        </form>

        {/* Scan Progress Bar */}
        {isScanning && (
          <div className="bg-[#0B0F17] border border-cyan-500/30 rounded-xl p-4 space-y-3 animate-fade-in">
            <div className="flex items-center justify-between text-xs">
              <div className="flex items-center space-x-2">
                <div className="w-3.5 h-3.5 border-2 border-cyan-400 border-t-transparent rounded-full animate-spin"></div>
                <span className="text-slate-200 font-medium font-mono">{scanStage}</span>
              </div>
              <span className="text-cyan-400 font-bold font-mono">{scanProgress}%</span>
            </div>
            <div className="w-full bg-slate-800 h-2 rounded-full overflow-hidden">
              <div
                className="bg-gradient-to-r from-cyan-500 to-blue-500 h-full transition-all duration-300"
                style={{ width: `${scanProgress}%` }}
              ></div>
            </div>
          </div>
        )}

        {/* Recent Scans */}
        <div className="pt-2">
          <div className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider mb-2.5 flex items-center gap-2">
            <span>⚡ Recent Repository Presets</span>
            <span className="text-[10px] text-slate-500 font-normal">(Click to re-scan)</span>
          </div>
          <div className="flex flex-wrap gap-2">
            {recentScans.map((item, idx) => (
              <button
                key={idx}
                type="button"
                onClick={() => loadRecentScan(item)}
                className="bg-[#0B0F17] hover:bg-slate-800 border border-slate-800 hover:border-slate-700 rounded-lg px-3 py-1.5 text-xs text-slate-300 hover:text-white flex items-center space-x-2 transition-colors cursor-pointer group"
              >
                <span className={`w-2 h-2 rounded-full ${item.badgeColor}`}></span>
                <span className="font-mono text-[11px]">{item.name}</span>
                <span className="text-[10px] text-slate-500 group-hover:text-cyan-400 font-sans">
                  • {item.status}
                </span>
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* ── KPI Stats Cards ────────────────────────────────────────────────── */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-[#131B2E] border border-slate-800 rounded-xl p-5 space-y-1 shadow-md">
          <div className="flex items-center justify-between text-xs text-slate-400">
            <span>Total Vulnerabilities</span>
            <span className="p-1.5 bg-blue-500/10 text-blue-400 rounded-lg">🐞</span>
          </div>
          <div className="text-2xl font-bold text-white font-mono">{stats.totalBugs ?? 0}</div>
          <div className="text-[11px] text-slate-400">
            Across <strong className="text-slate-200">{stats.totalFiles ?? 0}</strong> scanned source files
          </div>
        </div>

        <div className="bg-[#131B2E] border border-red-500/20 rounded-xl p-5 space-y-1 shadow-md">
          <div className="flex items-center justify-between text-xs text-slate-400">
            <span>Open High Priority Issues</span>
            <span className="p-1.5 bg-red-500/10 text-red-400 rounded-lg">🚨</span>
          </div>
          <div className="text-2xl font-bold text-red-400 font-mono">{stats.high ?? highUnresolvedCount}</div>
          <div className="text-[11px] text-red-300">Requires immediate P1 / P2 containment</div>
        </div>

        <div className="bg-[#131B2E] border border-emerald-500/20 rounded-xl p-5 space-y-1 shadow-md">
          <div className="flex items-center justify-between text-xs text-slate-400">
            <span>Resolved Vulnerabilities</span>
            <span className="p-1.5 bg-emerald-500/10 text-emerald-400 rounded-lg">✓</span>
          </div>
          <div className="text-2xl font-bold text-emerald-400 font-mono">{resolvedCount}</div>
          <div className="text-[11px] text-emerald-300">{resolutionPercentage}% resolution rate</div>
        </div>

        <div className="bg-[#131B2E] border border-slate-800 rounded-xl p-5 space-y-1 shadow-md">
          <div className="flex items-center justify-between text-xs text-slate-400">
            <span>AST Engine Speed</span>
            <span className="p-1.5 bg-cyan-500/10 text-cyan-400 rounded-lg">⚡</span>
          </div>
          <div className="text-2xl font-bold text-cyan-400 font-mono">{stats.scanTime || "—"}</div>
          <div className="text-[11px] text-slate-400">
            {stats.linesOfCode ? stats.linesOfCode.toLocaleString() : "—"} lines parsed
          </div>
        </div>
      </div>

      {/* ── Quick Nav Cards ────────────────────────────────────────────────── */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div
          onClick={() => setActiveTab("ai")}
          className="bg-[#131B2E] hover:bg-slate-800/80 border border-slate-800 hover:border-cyan-500/40 rounded-xl p-5 cursor-pointer transition-all group space-y-2"
        >
          <div className="flex items-center justify-between">
            <span className="text-xs font-mono text-cyan-400 font-semibold">Tab 2 →</span>
            <span className="text-slate-500 group-hover:text-cyan-400 transition-colors">✨</span>
          </div>
          <h3 className="text-sm font-bold text-white">AI Architecture & File Maps</h3>
          <p className="text-xs text-slate-400 leading-relaxed">
            Inspect detected stack, system intent, security risks, and filterable file summaries from the scanned repo.
          </p>
        </div>

        <div
          onClick={() => setActiveTab("bugs")}
          className="bg-[#131B2E] hover:bg-slate-800/80 border border-slate-800 hover:border-cyan-500/40 rounded-xl p-5 cursor-pointer transition-all group space-y-2"
        >
          <div className="flex items-center justify-between">
            <span className="text-xs font-mono text-cyan-400 font-semibold">Tab 3 →</span>
            <span className="text-slate-500 group-hover:text-cyan-400 transition-colors">🐞</span>
          </div>
          <h3 className="text-sm font-bold text-white">Bug Triage & Inspector</h3>
          <p className="text-xs text-slate-400 leading-relaxed">
            Filter issues by severity, review vulnerable code lines, inspect suggested fixes.
          </p>
        </div>

        <div
          onClick={() => setActiveTab("reports")}
          className="bg-[#131B2E] hover:bg-slate-800/80 border border-slate-800 hover:border-cyan-500/40 rounded-xl p-5 cursor-pointer transition-all group space-y-2"
        >
          <div className="flex items-center justify-between">
            <span className="text-xs font-mono text-cyan-400 font-semibold">Tab 4 →</span>
            <span className="text-slate-500 group-hover:text-cyan-400 transition-colors">📄</span>
          </div>
          <h3 className="text-sm font-bold text-white">Executive Audit & PDF Export</h3>
          <p className="text-xs text-slate-400 leading-relaxed">
            Review live audit metrics and generate clean PDF reports with one click.
          </p>
        </div>
      </div>
    </div>
  );
}
