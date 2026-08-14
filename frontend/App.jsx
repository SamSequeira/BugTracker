import React, { useState, useEffect } from "react";

// ============================================================================
// 1. API CONFIGURATION & SERVICE LAYER (Backend Ready)
// ============================================================================
const API_BASE_URL =
  (typeof process !== "undefined" && process.env?.REACT_APP_API_URL) ||
  (typeof import.meta !== "undefined" && import.meta.env?.VITE_API_URL) ||
  "http://localhost:8000/api";

const apiService = {
  // Trigger scan
  async startScan(payload, isFile = false) {
    try {
      const options = isFile
        ? { method: "POST", body: payload }
        : {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
          };
      const res = await fetch(`${API_BASE_URL}/scan`, options);
      if (!res.ok) throw new Error("Network response was not ok");
      return await res.json();
    } catch (err) {
      console.warn("Backend offline, using local simulation", err);
      return { status: "simulated", progress: 100 };
    }
  },

  // Fetch Dashboard Stats & KPIs
  async getDashboardStats() {
    try {
      const res = await fetch(`${API_BASE_URL}/dashboard-stats`);
      if (!res.ok) throw new Error();
      return await res.json();
    } catch (err) {
      return null;
    }
  },

  // Fetch Issues / Bugs List
  async getBugs() {
    try {
      const res = await fetch(`${API_BASE_URL}/bugs`);
      if (!res.ok) throw new Error();
      return await res.json();
    } catch (err) {
      return null;
    }
  },

  // Fetch AI Decomposition & Summaries
  async getAiSummary() {
    try {
      const res = await fetch(`${API_BASE_URL}/ai-summary`);
      if (!res.ok) throw new Error();
      return await res.json();
    } catch (err) {
      return null;
    }
  },

  // Toggle Bug Resolution
  async toggleResolveBug(bugId, nextStatus) {
    try {
      const res = await fetch(`${API_BASE_URL}/bugs/${bugId}/resolve`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: nextStatus }),
      });
      if (!res.ok) throw new Error();
      return await res.json();
    } catch (err) {
      return { success: true, localOnly: true };
    }
  },
};

// ============================================================================
// 2. DEFAULT FALLBACK DATA
// ============================================================================
const DEFAULT_STATS = {
  totalBugs: 128,
  totalFiles: 2843,
  linesOfCode: 128742,
  critical: 8,
  high: 32,
  medium: 54,
  low: 34,
};

const DEFAULT_BUGS = [
  {
    id: "BUG-2026-0091",
    file: "src/db/queryBuilder.py",
    line: 118,
    title: "SQL Injection vulnerability in user query builder",
    severity: "Critical",
    priority: "P1 • Fix now",
    status: "Open",
    wrong: "User input is being inserted directly into a database query without sanitization. This lets an attacker run their own database commands.",
    matter: "An attacker could read, change, or delete data in your database.",
    snippet: [
      { num: 114, text: "def getUserData(userId):", isErr: false },
      { num: 115, text: "    conn = getConnectbile()", isErr: false },
      { num: 116, text: "    cursor = conn.cursor()", isErr: false },
      { num: 117, text: '    query = "SELECT * FROM users WHERE id = " + userId', isErr: true },
      { num: 118, text: "    results = cursor.fetchall()", isErr: true },
      { num: 119, text: "    conn.close()", isErr: false },
      { num: 120, text: "    return results", isErr: false },
    ],
    fixRemove: '- query = "SELECT * FROM users WHERE id = " + userId',
    fixAdd: '+ query = "SELECT * FROM users WHERE id = %s"\n+ cursor.execute(query, (userId,))',
  },
  {
    id: "BUG-2026-0087",
    file: "scripts/deploy.sh",
    line: 42,
    title: "Hardcoded AWS credentials in deployment script",
    severity: "Critical",
    priority: "P1 • Fix now",
    status: "In Review",
    wrong: "Plaintext AWS Secret Access Keys detected inside version-controlled deployment script.",
    matter: "Public exposure could lead to complete cloud infrastructure hijacking.",
    snippet: [
      { num: 40, text: "# Setup AWS environment credentials", isErr: false },
      { num: 41, text: 'export AWS_ACCESS_KEY_ID="AKIAIOSFODNN7EXAMPLE"', isErr: true },
      { num: 42, text: 'export AWS_SECRET_ACCESS_KEY="wJalrXUtnFEMI/K7MDENG..."', isErr: true },
      { num: 43, text: "aws s3 sync ./build s3://production-bucket", isErr: false },
    ],
    fixRemove: '- export AWS_SECRET_ACCESS_KEY="wJalrXUtnFEMI..."',
    fixAdd: '+ export AWS_SECRET_ACCESS_KEY="${ENV_AWS_SECRET}"',
  },
  {
    id: "BUG-2026-0076",
    file: "src/cart/checkout.py",
    line: 97,
    title: "Null pointer dereference on empty cart checkout",
    severity: "High",
    priority: "P2 • Fix this week",
    status: "Open",
    wrong: "Checkout handler does not check if the cart items list is initialized.",
    matter: "Triggers unhandled 500 crashes during rapid checkout requests.",
    snippet: [
      { num: 95, text: "def process_order(cart):", isErr: false },
      { num: 96, text: "    items = cart.get_items()", isErr: false },
      { num: 97, text: "    total = sum([item.price for item in items])", isErr: true },
      { num: 98, text: "    return charge_card(cart.user, total)", isErr: false },
    ],
    fixRemove: "- total = sum([item.price for item in items])",
    fixAdd: "+ if not items: raise EmptyCartException('No items in cart')\n+ total = sum([item.price for item in items])",
  },
  {
    id: "BUG-2026-0063",
    file: "src/ws/handler.py",
    line: 214,
    title: "Memory leak in websocket connection handler",
    severity: "High",
    priority: "P2 • Fix this week",
    status: "Open",
    wrong: "Closed client connections are not removed from active subscriber sets.",
    matter: "Leads to unbounded memory growth and worker crash under heavy load.",
    snippet: [
      { num: 212, text: "async def on_disconnect(websocket):", isErr: false },
      { num: 213, text: "    await websocket.close()", isErr: false },
      { num: 214, text: "    # Missing: active_connections.remove(websocket)", isErr: true },
    ],
    fixRemove: "- # Missing connection cleanup",
    fixAdd: "+ active_connections.discard(websocket)",
  },
  {
    id: "BUG-2026-0059",
    file: "src/utils/csvParser.py",
    line: 66,
    title: "Unhandled exception when parsing malformed CSV upload",
    severity: "Medium",
    priority: "P3 • Backlog",
    status: "In Review",
    wrong: "Non-UTF8 byte sequences in user-uploaded files raise unhandled UnicodeDecodeErrors.",
    matter: "Causes file ingestion worker jobs to hang without logging descriptive diagnostics.",
    snippet: [
      { num: 64, text: "def parse_csv(file_stream):", isErr: false },
      { num: 65, text: "    reader = csv.reader(file_stream.read().decode('utf-8'))", isErr: true },
      { num: 66, text: "    return [row for row in reader]", isErr: false },
    ],
    fixRemove: "- reader = csv.reader(file_stream.read().decode('utf-8'))",
    fixAdd: "+ content = file_stream.read().decode('utf-8', errors='replace')\n+ reader = csv.reader(content.splitlines())",
  },
];

const DEFAULT_AI_SUMMARY = {
  intent:
    "Microservice-based asynchronous web platform managing user authentication, dynamic order processing, inventory ETL, and websocket notifications.",
  techStack: ["Python 3.11", "FastAPI", "PostgreSQL", "WebSockets", "Docker", "AWS S3"],
  fileSummaries: [
    {
      file: "src/db/queryBuilder.py",
      role: "Database abstraction layer and dynamic SQL query generator.",
      intent: "Constructs parameterized SQL queries for user authentication and records retrieval.",
      status: "Security Risk",
      statusColor: "text-red-400 border-red-500/30 bg-red-500/10",
    },
    {
      file: "scripts/deploy.sh",
      role: "Continuous deployment and AWS S3/CloudFront build pipeline sync.",
      intent: "Automates packaging and deploying static frontend bundles to cloud infrastructure.",
      status: "Credential Leak",
      statusColor: "text-red-400 border-red-500/30 bg-red-500/10",
    },
    {
      file: "src/cart/checkout.py",
      role: "Shopping cart lifecycle and payment gateway processing controller.",
      intent: "Calculates cart item subtotals, tax rates, and coordinates checkout billing API calls.",
      status: "Null Safety Issue",
      statusColor: "text-amber-400 border-amber-500/30 bg-amber-500/10",
    },
    {
      file: "src/ws/handler.py",
      role: "Real-time bidirectional WebSocket event broadcaster and socket pool.",
      intent: "Maintains live client notification connections and broadcasts order status telemetry.",
      status: "Memory Leak",
      statusColor: "text-amber-400 border-amber-500/30 bg-amber-500/10",
    },
  ],
};

// ============================================================================
// 3. MAIN COMPONENT
// ============================================================================
export default function App() {
  const [activeTab, setActiveTab] = useState("dashboard"); // 'dashboard' | 'ai' | 'debug' | 'report'
  const [scanInputTab, setScanInputTab] = useState("github"); // 'github' | 'zip'
  const [repoInput, setRepoInput] = useState("https://github.com/your-org/your-repo");
  const [isScanning, setIsScanning] = useState(false);
  const [scanProgress, setScanProgress] = useState(67);
  const [expandedBug, setExpandedBug] = useState("BUG-2026-0091");

  // Dynamic States
  const [stats, setStats] = useState(DEFAULT_STATS);
  const [bugs, setBugs] = useState(DEFAULT_BUGS);
  const [aiSummary, setAiSummary] = useState(DEFAULT_AI_SUMMARY);

  // Initial Load from Backend (falls back gracefully)
  useEffect(() => {
    async function loadData() {
      const [apiStats, apiBugs, apiAi] = await Promise.all([
        apiService.getDashboardStats(),
        apiService.getBugs(),
        apiService.getAiSummary(),
      ]);
      if (apiStats) setStats(apiStats);
      if (apiBugs) setBugs(apiBugs);
      if (apiAi) setAiSummary(apiAi);
    }
    loadData();
  }, []);

  // Handle Scan Trigger
  const handleAnalyze = async (e) => {
    if (e) e.preventDefault();
    setIsScanning(true);
    setScanProgress(10);

    await apiService.startScan({ repo_url: repoInput });

    const interval = setInterval(() => {
      setScanProgress((prev) => {
        if (prev >= 100) {
          clearInterval(interval);
          setIsScanning(false);
          return 100;
        }
        return prev + 15;
      });
    }, 200);
  };

  // Toggle Bug Resolution
  const handleToggleResolve = async (bugId) => {
    const target = bugs.find((b) => b.id === bugId);
    if (!target) return;
    const nextStatus = target.status === "Resolved" ? "Open" : "Resolved";

    setBugs((prev) =>
      prev.map((b) => (b.id === bugId ? { ...b, status: nextStatus } : b))
    );

    await apiService.toggleResolveBug(bugId, nextStatus);
  };

  const resolvedCount = bugs.filter((b) => b.status === "Resolved").length;
  const resolutionPercentage = Math.round((resolvedCount / (bugs.length || 1)) * 100);

  return (
    <div className="min-h-screen bg-[#0B0F17] text-slate-200 font-sans flex text-xs sm:text-sm">
      {/* ===================================================================== */}
      {/* 4-TAB FIXED LEFT SIDEBAR                                              */}
      {/* ===================================================================== */}
      <aside className="w-16 bg-[#0F1623] border-r border-slate-800 flex flex-col items-center py-4 space-y-5 shrink-0 sticky top-0 h-screen z-30">
        <div className="p-2.5 bg-cyan-500/10 rounded-xl text-cyan-400 border border-cyan-500/20">
          <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
        </div>

        <button className="p-1.5 text-slate-500 hover:text-slate-300 transition-colors">
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 5l7 7-7 7M5 5l7 7-7 7" />
          </svg>
        </button>

        <nav className="flex flex-col space-y-2.5 w-full items-center pt-2">
          {/* Tab 1: Dashboard */}
          <button
            onClick={() => setActiveTab("dashboard")}
            title="Tab 1: Dashboard"
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

          {/* Tab 2: AI Analysis */}
          <button
            onClick={() => setActiveTab("ai")}
            title="Tab 2: AI Codebase Analysis"
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

          {/* Tab 3: Debugging */}
          <button
            onClick={() => setActiveTab("debug")}
            title="Tab 3: Debugging (By File & Line)"
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

          {/* Tab 4: Report */}
          <button
            onClick={() => setActiveTab("report")}
            title="Tab 4: Executive Report & Export"
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

        <div className="mt-auto flex flex-col space-y-3.5 items-center pt-4 border-t border-slate-800/80 w-full">
          <button title="Settings" className="p-2 text-slate-500 hover:text-slate-300 transition-colors">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
            </svg>
          </button>
          <div className="w-8 h-8 rounded-full bg-cyan-900 text-cyan-200 flex items-center justify-center font-bold text-xs border border-cyan-600">
            AD
          </div>
        </div>
      </aside>

      {/* ===================================================================== */}
      {/* MAIN VIEWPORT                                                         */}
      {/* ===================================================================== */}
      <div className="flex-1 flex flex-col min-w-0 overflow-y-auto">
        {/* Top Header */}
        <header className="h-14 bg-[#0F1623] border-b border-slate-800 px-6 flex items-center justify-between sticky top-0 z-20">
          <div className="flex items-center space-x-3">
            <h1 className="font-semibold text-white text-base">AI Bug Tracking & Prioritization System</h1>
            <span className="text-[11px] text-slate-400 hidden xl:inline">
              Smart Repository Analysis using AST, Static Analysis, NLP & Similarity Search
            </span>
          </div>

          <div className="flex items-center space-x-4">
            <span className="bg-red-500/15 text-red-400 border border-red-500/30 px-2.5 py-1 rounded-full text-xs font-medium flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-red-500 animate-pulse"></span>
              {stats.critical} critical issues
            </span>
            <svg className="w-4 h-4 text-slate-400 hover:text-white cursor-pointer" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
            <div className="relative cursor-pointer">
              <svg className="w-4 h-4 text-slate-400 hover:text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
              </svg>
              <span className="absolute -top-1.5 -right-1.5 bg-cyan-500 text-slate-950 font-bold text-[10px] w-3.5 h-3.5 rounded-full flex items-center justify-center">
                3
              </span>
            </div>
            <div className="w-7 h-7 rounded-full bg-cyan-900 text-cyan-200 flex items-center justify-center font-semibold text-xs border border-cyan-600">
              AD
            </div>
          </div>
        </header>

        <main className="p-6 space-y-6 max-w-[1400px] mx-auto w-full">
          {/* ================================================================= */}
          {/* TAB 1: DASHBOARD (SHOWS ONLY IMAGE 2 SPECIFICATION)               */}
          {/* ================================================================= */}
          {activeTab === "dashboard" && (
            <div className="space-y-6">
              {/* Repository Scanner Main Box */}
              <div className="bg-[#131B2E] border border-slate-800 rounded-xl p-6 shadow-xl space-y-6">
                <div>
                  <h2 className="text-xl font-semibold text-white">Scan your repository in seconds</h2>
                  <p className="text-slate-400 text-xs mt-1">Paste a link or upload your code. We'll do the rest.</p>
                </div>

                <div className="bg-[#0B0F17] border border-slate-800 rounded-lg p-5 grid grid-cols-1 lg:grid-cols-12 gap-6 items-center">
                  <div className="lg:col-span-6 space-y-4">
                    <div className="flex space-x-4 border-b border-slate-800 pb-2">
                      <button
                        onClick={() => setScanInputTab("github")}
                        className={`text-xs font-medium pb-2 border-b-2 transition-colors flex items-center gap-1.5 ${
                          scanInputTab === "github"
                            ? "border-cyan-400 text-cyan-400"
                            : "border-transparent text-slate-400 hover:text-white"
                        }`}
                      >
                        GitHub Repository
                      </button>
                      <button
                        onClick={() => setScanInputTab("zip")}
                        className={`text-xs font-medium pb-2 border-b-2 transition-colors flex items-center gap-1.5 ${
                          scanInputTab === "zip"
                            ? "border-cyan-400 text-cyan-400"
                            : "border-transparent text-slate-400 hover:text-white"
                        }`}
                      >
                        Upload .zip File
                      </button>
                    </div>

                    {scanInputTab === "github" ? (
                      <form onSubmit={handleAnalyze} className="space-y-3">
                        <label className="text-xs text-slate-400 block font-medium">Paste your GitHub repository link</label>
                        <input
                          type="text"
                          value={repoInput}
                          onChange={(e) => setRepoInput(e.target.value)}
                          className="w-full bg-[#131B2E] border border-slate-700 rounded-md px-3 py-2 text-xs text-white focus:outline-none focus:border-cyan-500 font-mono"
                        />
                        <button
                          type="submit"
                          disabled={isScanning}
                          className="w-full bg-cyan-400 hover:bg-cyan-300 text-slate-950 font-bold py-2 rounded-md text-xs transition-colors flex justify-center items-center gap-1.5 shadow-lg shadow-cyan-500/10"
                        >
                          {isScanning ? "Analyzing..." : "Analyze Repository →"}
                        </button>
                      </form>
                    ) : (
                      <div className="space-y-3">
                        <label className="text-xs text-slate-400 block font-medium">Upload local project archive</label>
                        <button
                          onClick={() => handleAnalyze()}
                          className="w-full bg-slate-800 hover:bg-slate-700 border border-slate-700 text-white font-medium py-2 rounded text-xs"
                        >
                          Choose ZIP File from Disk
                        </button>
                      </div>
                    )}

                    <p className="text-[11px] text-slate-500 flex items-center gap-1.5">
                      <svg className="w-3.5 h-3.5 text-cyan-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                      </svg>
                      We only read public code. No changes are made.
                    </p>
                  </div>

                  <div className="hidden lg:flex lg:col-span-1 justify-center items-center">
                    <span className="text-xs text-slate-500 font-semibold bg-slate-900 border border-slate-800 px-2.5 py-1 rounded-full">OR</span>
                  </div>

                  <div
                    onClick={() => handleAnalyze()}
                    className="lg:col-span-5 border-2 border-dashed border-slate-800 hover:border-cyan-500/40 rounded-lg p-6 flex flex-col items-center justify-center text-center bg-[#0F1623]/50 cursor-pointer transition-all"
                  >
                    <svg className="w-8 h-8 text-slate-400 mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                    </svg>
                    <p className="text-xs text-slate-300 font-medium">Drag and drop your .zip file here</p>
                    <span className="text-slate-500 text-[10px] my-1">or</span>
                    <button className="bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 text-xs px-3 py-1.5 rounded-md font-medium">Choose ZIP File</button>
                    <span className="text-[10px] text-slate-500 mt-2">Max file size: 500MB</span>
                  </div>
                </div>

                {/* Progress Pipeline */}
                <div className="mt-6 border-t border-slate-800/80 pt-6 grid grid-cols-1 md:grid-cols-12 gap-6 items-center">
                  <div className="md:col-span-5 flex items-center space-x-4">
                    <div className="w-12 h-12 rounded-full border-2 border-cyan-500/30 border-t-cyan-400 animate-spin flex items-center justify-center shrink-0">
                      <svg className="w-5 h-5 text-cyan-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                      </svg>
                    </div>
                    <div>
                      <p className="text-sm font-semibold text-white">Scanning your codebase...</p>
                      <ul className="text-xs space-y-1 text-slate-400 mt-1">
                        <li className="flex items-center gap-1.5 text-emerald-400 font-medium">✓ Reading your code...</li>
                        <li className="flex items-center gap-1.5 text-emerald-400 font-medium">✓ Detecting languages...</li>
                        <li className="flex items-center gap-1.5 text-cyan-400 font-medium animate-pulse">● Checking for problems...</li>
                        <li className="flex items-center gap-1.5 text-slate-500">○ Preparing report...</li>
                      </ul>
                    </div>
                  </div>

                  <div className="md:col-span-7 space-y-2">
                    <div className="flex justify-between text-xs">
                      <span className="text-slate-300 font-medium">Analyzing {stats.totalFiles} files</span>
                      <span className="text-cyan-400 font-bold">{scanProgress}%</span>
                    </div>
                    <div className="w-full bg-slate-800 h-2 rounded-full overflow-hidden">
                      <div className="bg-cyan-400 h-full transition-all duration-300" style={{ width: `${scanProgress}%` }}></div>
                    </div>
                    <p className="text-[11px] text-slate-500">This usually takes 1–3 minutes depending on the size of your code.</p>
                  </div>
                </div>

                {/* Recent Scans Row */}
                <div className="mt-6 pt-4 border-t border-slate-800/60">
                  <div className="flex items-center justify-between mb-3">
                    <span className="text-xs font-semibold text-slate-400">Recent Scans</span>
                    <button onClick={() => setActiveTab("debug")} className="text-xs text-cyan-400 hover:underline">
                      View all history &rarr;
                    </button>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {[
                      { name: "your-repo", color: "bg-red-500", date: "May 21, 2026 10:42 AM" },
                      { name: "payment-service", color: "bg-amber-500", date: "May 18, 2026 04:22 PM" },
                      { name: "user-dashboard", color: "bg-yellow-500", date: "May 15, 2026 11:03 AM" },
                      { name: "inventory-api", color: "bg-blue-500", date: "May 10, 2026 09:17 AM" },
                      { name: "blog-website", color: "bg-blue-500", date: "May 8, 2026 02:50 PM" },
                    ].map((item, idx) => (
                      <div
                        key={idx}
                        onClick={() => setActiveTab("debug")}
                        className="bg-[#0B0F17] hover:bg-slate-800 border border-slate-800 px-3 py-1.5 rounded-lg flex items-center space-x-2 text-xs cursor-pointer transition-colors"
                      >
                        <span className={`w-2 h-2 rounded-full ${item.color}`}></span>
                        <span className="text-slate-200 font-medium">{item.name}</span>
                        <span className="text-slate-500 text-[10px]">{item.date}</span>
                        <span className="text-slate-500 text-[10px]">&rsaquo;</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* ================================================================= */}
          {/* TAB 2: AI CODEBASE ANALYSIS                                       */}
          {/* ================================================================= */}
          {activeTab === "ai" && (
            <div className="space-y-6">
              <h2 className="text-xl font-bold text-white flex items-center gap-2">
                <span className="text-cyan-400">✨</span> AI Codebase Intelligence & Intent
              </h2>
              <div className="bg-[#131B2E] border border-slate-800 rounded-xl p-5 space-y-3">
                <h3 className="font-bold text-white text-sm">Overall Repository Purpose</h3>
                <p className="text-xs text-slate-300 leading-relaxed">{aiSummary.intent}</p>
                <div className="flex gap-2 flex-wrap pt-2">
                  {aiSummary.techStack.map((tech) => (
                    <span key={tech} className="bg-[#0B0F17] text-cyan-300 font-mono text-[10px] px-2 py-0.5 rounded border border-slate-800">
                      {tech}
                    </span>
                  ))}
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {aiSummary.fileSummaries.map((f, idx) => (
                  <div key={idx} className="bg-[#131B2E] border border-slate-800 rounded-xl p-4 space-y-2">
                    <div className="flex justify-between items-center">
                      <span className="font-mono text-xs font-bold text-white">{f.file}</span>
                      <span className={`text-[10px] px-2 py-0.5 rounded border font-medium ${f.statusColor}`}>{f.status}</span>
                    </div>
                    <p className="text-xs text-slate-300">{f.role}</p>
                    <p className="text-[11px] text-slate-400"><strong>Intent:</strong> {f.intent}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* ================================================================= */}
          {/* TAB 3: DEBUGGING (GROUPED BY FILE & LINE)                          */}
          {/* ================================================================= */}
          {activeTab === "debug" && (
            <div className="space-y-6">
              <div className="flex justify-between items-center flex-wrap gap-2">
                <h2 className="text-xl font-bold text-white flex items-center gap-2">
                  <span className="text-red-400">🐛</span> Debugging & Issue Inspector
                </h2>
              </div>

              <div className="space-y-4">
                {bugs.map((bug) => {
                  const isExpanded = expandedBug === bug.id;
                  const isResolved = bug.status === "Resolved";

                  return (
                    <div key={bug.id} className="bg-[#131B2E] border border-slate-800 rounded-xl overflow-hidden">
                      <div
                        onClick={() => setExpandedBug(isExpanded ? null : bug.id)}
                        className="bg-[#0F1623] px-4 py-3 flex items-center justify-between cursor-pointer hover:bg-slate-800/40"
                      >
                        <div className="flex items-center space-x-3">
                          <span className="font-mono text-xs font-bold text-cyan-400">{bug.file}:{bug.line}</span>
                          <span className={`text-xs font-semibold ${isResolved ? "line-through text-slate-500" : "text-white"}`}>
                            {bug.title}
                          </span>
                        </div>
                        <div className="flex items-center space-x-2">
                          <span className="text-red-400 bg-red-500/10 border border-red-500/30 px-2 py-0.5 rounded text-[10px]">
                            {bug.severity}
                          </span>
                          <span className={`text-[10px] px-2 py-0.5 rounded border ${isResolved ? "text-emerald-400 border-emerald-500/30" : "text-blue-400 border-blue-500/30"}`}>
                            {bug.status}
                          </span>
                        </div>
                      </div>

                      {isExpanded && (
                        <div className="p-4 bg-[#0B0F17] space-y-4 border-t border-slate-800">
                          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                            {/* Code snippet */}
                            <div className="bg-[#0F1623] border border-slate-800 rounded p-3 font-mono text-[11px]">
                              {bug.snippet.map((line) => (
                                <div key={line.num} className={line.isErr ? "bg-red-500/20 text-red-300 pl-2 border-l-2 border-red-500" : "text-slate-500 pl-2"}>
                                  <span className="inline-block w-8 text-slate-600 select-none">{line.num}</span> {line.text}
                                </div>
                              ))}
                            </div>

                            {/* Fix Diff */}
                            <div className="space-y-3 text-xs">
                              <div>
                                <h5 className="font-semibold text-slate-300">What's wrong</h5>
                                <p className="text-slate-400">{bug.wrong}</p>
                              </div>
                              <div className="bg-[#0F1623] border border-slate-800 p-2.5 rounded">
                                <h5 className="font-semibold text-slate-200 mb-1">Suggested Fix</h5>
                                <div className="font-mono text-[11px] bg-[#0B0F17] p-2 rounded">
                                  <div className="text-red-400">{bug.fixRemove}</div>
                                  <div className="text-emerald-400 whitespace-pre-line">{bug.fixAdd}</div>
                                </div>
                              </div>
                            </div>
                          </div>

                          <button
                            onClick={() => handleToggleResolve(bug.id)}
                            className={`px-3 py-1.5 rounded text-xs font-semibold ${
                              isResolved ? "bg-emerald-600 text-white" : "bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700"
                            }`}
                          >
                            {isResolved ? "✓ Marked as Resolved" : "Mark as Resolved"}
                          </button>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* ================================================================= */}
          {/* TAB 4: REPORT                                                     */}
          {/* ================================================================= */}
          {activeTab === "report" && (
            <div className="space-y-6">
              <div className="flex justify-between items-center">
                <h2 className="text-xl font-bold text-white flex items-center gap-2">
                  <span>📄</span> Code Resolution Audit Report
                </h2>
                <button onClick={() => window.print()} className="bg-cyan-400 hover:bg-cyan-300 text-slate-950 font-bold px-3.5 py-1.5 rounded text-xs">
                  Download Report (PDF)
                </button>
              </div>

              <div className="bg-[#131B2E] border border-slate-800 p-4 rounded-xl">
                <span className="text-xs text-slate-400">Resolution Status</span>
                <div className="text-sm font-bold text-white mt-1">
                  {resolvedCount} of {bugs.length} issues fixed ({resolutionPercentage}%)
                </div>
              </div>

              <div className="bg-[#131B2E] border border-slate-800 rounded-xl overflow-hidden">
                <table className="w-full text-left text-xs min-w-[700px]">
                  <thead className="bg-[#0F1623] text-slate-400 border-b border-slate-800">
                    <tr>
                      <th className="p-3">File</th>
                      <th className="p-3">Line</th>
                      <th className="p-3">Issue</th>
                      <th className="p-3">Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/50">
                    {bugs.map((bug) => (
                      <tr key={bug.id} className="hover:bg-slate-800/30">
                        <td className="p-3 font-mono text-cyan-300">{bug.file}</td>
                        <td className="p-3">:{bug.line}</td>
                        <td className="p-3 text-white">{bug.title}</td>
                        <td className="p-3">
                          <span className={`px-2 py-0.5 rounded text-[10px] ${bug.status === "Resolved" ? "bg-emerald-500/20 text-emerald-300" : "bg-red-500/10 text-red-400"}`}>
                            {bug.status === "Resolved" ? "✓ Fixed" : "Open"}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
