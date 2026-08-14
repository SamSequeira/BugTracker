import React, { useState, useEffect } from "react";

// ============================================================================
// 1. API CONFIGURATION & SERVICE LAYER
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
      return null; // Signals fallback to default mock data
    }
  },

  // Fetch Issues / Bugs List
  async getBugs() {
    try {
      const res = await fetch(`${API_BASE_URL}/bugs`);
      if (!res.ok) throw new Error();
      return await res.json();
    } catch (err) {
      return null; // Signals fallback to default mock data
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
// 2. DEFAULT FALLBACK DATA (USED WHEN BACKEND IS OFFLINE)
// ============================================================================
const DEFAULT_STATS = {
  totalBugs: 128,
  totalFiles: 2843,
  linesOfCode: 128742,
  critical: 8,
  high: 32,
  medium: 54,
  low: 34,
  severityBreakdown: { critical: 6.3, high: 25.0, medium: 42.2, low: 26.6 },
  priorityBreakdown: [
    { label: "P1 • Fix now", count: 18, pct: "14.1%", width: "14%", color: "bg-red-500" },
    { label: "P2 • Fix this week", count: 38, pct: "29.7%", width: "30%", color: "bg-amber-500" },
    { label: "P3 • Backlog", count: 46, pct: "35.9%", width: "36%", color: "bg-yellow-400" },
    { label: "P4 • Low urgency", count: 26, pct: "20.3%", width: "20%", color: "bg-blue-500" },
  ],
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
    similarCount: "3 similar",
    wrong: "User input is being inserted directly into a database query without sanitization. This lets an attacker run their own database commands.",
    matter: "An attacker could read, change, or delete data in your database.",
    codeSnippet: [
      { num: 114, text: "def getUserData(userId):", isErr: false },
      { num: 115, text: "    conn = getConnectbile()", isErr: false },
      { num: 116, text: "    cursor = conn.cursor()", isErr: false },
      { num: 117, text: '    query = "SELECT * FROM users WHERE id = " + userId', isErr: true },
      { num: 118, text: "    results = cursor.fetchall()", isErr: true },
      { num: 119, text: "    conn.close()", isErr: false },
      { num: 120, text: "    return results", isErr: false },
    ],
    suggestedFix: {
      remove: '- query = "SELECT * FROM users WHERE id = " + userId',
      add: '+ query = "SELECT * FROM users WHERE id = %s"\n+ cursor.execute(query, (userId,))',
      note: "Use parameterized queries to safely handle user input.",
    },
  },
  {
    id: "BUG-2026-0087",
    file: "scripts/deploy.sh",
    line: 42,
    title: "Hardcoded AWS credentials in deployment script",
    severity: "Critical",
    priority: "P1 • Fix now",
    status: "In Review",
    similarCount: "2 similar",
    wrong: "Plaintext AWS Secret Access Keys detected inside a version-controlled deployment script.",
    matter: "Public repository exposure could lead to immediate unauthorized cloud infrastructure takeovers.",
    codeSnippet: [
      { num: 40, text: "# Setup AWS environment credentials", isErr: false },
      { num: 41, text: 'export AWS_ACCESS_KEY_ID="AKIAIOSFODNN7EXAMPLE"', isErr: true },
      { num: 42, text: 'export AWS_SECRET_ACCESS_KEY="wJalrXUtnFEMI/K7MDENG..."', isErr: true },
      { num: 43, text: "aws s3 sync ./build s3://production-app-bucket", isErr: false },
    ],
    suggestedFix: {
      remove: '- export AWS_SECRET_ACCESS_KEY="wJalrXUtnFEMI..."',
      add: '+ export AWS_SECRET_ACCESS_KEY="${ENV_AWS_SECRET}"',
      note: "Inject credentials securely via CI/CD secrets manager.",
    },
  },
  {
    id: "BUG-2026-0076",
    file: "src/cart/checkout.py",
    line: 97,
    title: "Null pointer dereference on empty cart checkout",
    severity: "High",
    priority: "P2 • Fix this week",
    status: "Open",
    similarCount: "5 similar",
    wrong: "The checkout service processes cart items without verifying if the items collection is initialized.",
    matter: "Triggers unhandled 500 server crashes when users trigger simultaneous duplicate checkout requests.",
    codeSnippet: [
      { num: 95, text: "def process_order(cart):", isErr: false },
      { num: 96, text: "    items = cart.get_items()", isErr: false },
      { num: 97, text: "    total = sum([item.price for item in items])", isErr: true },
      { num: 98, text: "    return charge_card(cart.user, total)", isErr: false },
    ],
    suggestedFix: {
      remove: "- total = sum([item.price for item in items])",
      add: "+ if not items: raise EmptyCartException('No items in cart')\n+ total = sum([item.price for item in items])",
      note: "Validate non-empty collections before reduction operations.",
    },
  },
  {
    id: "BUG-2026-0063",
    file: "src/ws/handler.py",
    line: 214,
    title: "Memory leak in websocket connection handler",
    severity: "High",
    priority: "P2 • Fix this week",
    status: "Open",
    similarCount: "1 similar",
    wrong: "Closed websocket client sessions are not removed from the active global listeners map.",
    matter: "Causes progressive memory bloat leading to out-of-memory container termination under load.",
    codeSnippet: [
      { num: 212, text: "async def on_disconnect(websocket):", isErr: false },
      { num: 213, text: "    await websocket.close()", isErr: false },
      { num: 214, text: "    # Missing: active_connections.remove(websocket)", isErr: true },
    ],
    suggestedFix: {
      remove: "- # Missing connection cleanup",
      add: "+ active_connections.discard(websocket)",
      note: "Explicitly discard sockets from the active pool on disconnect.",
    },
  },
  {
    id: "BUG-2026-0059",
    file: "src/utils/csvParser.py",
    line: 66,
    title: "Unhandled exception when parsing malformed CSV upload",
    severity: "Medium",
    priority: "P3 • Backlog",
    status: "In Review",
    similarCount: "2 similar",
    wrong: "Non-UTF8 byte sequences in user-uploaded files raise unhandled UnicodeDecodeErrors.",
    matter: "Causes file ingestion worker jobs to hang without logging descriptive diagnostics.",
    codeSnippet: [
      { num: 64, text: "def parse_csv(file_stream):", isErr: false },
      { num: 65, text: "    reader = csv.reader(file_stream.read().decode('utf-8'))", isErr: true },
      { num: 66, text: "    return [row for row in reader]", isErr: false },
    ],
    suggestedFix: {
      remove: "- reader = csv.reader(file_stream.read().decode('utf-8'))",
      add: "+ content = file_stream.read().decode('utf-8', errors='replace')\n+ reader = csv.reader(content.splitlines())",
      note: "Sanitize byte streams with defensive encoding fallbacks.",
    },
  },
];

const DEFAULT_AI_SUMMARY = {
  intent: "Microservice-based asynchronous web platform managing user authentication, dynamic order processing, inventory ETL, and websocket notifications.",
  techStack: ["Python 3.11", "FastAPI", "PostgreSQL", "WebSockets", "Docker", "AWS S3"],
  healthAssessment: "The core architecture is modular and scalable. However, critical SQL sanitization in queryBuilder.py and AWS credential exposure in deploy.sh require immediate remediation.",
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
// 3. MAIN COMPONENT (WITH DYNAMIC SYNC & BACKEND CONNECTIVITY)
// ============================================================================
export default function BugTrackerApp() {
  const [activeTab, setActiveTab] = useState("dashboard"); // 'dashboard' | 'ai' | 'debug' | 'report'
  const [repoInput, setRepoInput] = useState("https://github.com/your-org/your-repo");
  const [isScanning, setIsScanning] = useState(false);
  const [scanProgress, setScanProgress] = useState(67);
  const [expandedBug, setExpandedBug] = useState("BUG-2026-0091");
  const [selectedSeverity, setSelectedSeverity] = useState("All");
  const [searchQuery, setSearchQuery] = useState("");

  // Dynamic States (Populated from API or Defaults)
  const [stats, setStats] = useState(DEFAULT_STATS);
  const [bugs, setBugs] = useState(DEFAULT_BUGS);
  const [aiSummary, setAiSummary] = useState(DEFAULT_AI_SUMMARY);

  // Initial Load from API
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

  // Handle Scan Submission
  const handleAnalyze = async (e) => {
    if (e) e.preventDefault();
    setIsScanning(true);
    setScanProgress(10);

    // Call backend API
    await apiService.startScan({ repo_url: repoInput });

    // Progress animation
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

  // Toggle Resolve Status (Syncs with API and UI)
  const handleToggleResolve = async (bugId) => {
    const target = bugs.find((b) => b.id === bugId);
    if (!target) return;
    const nextStatus = target.status === "Resolved" ? "Open" : "Resolved";

    // Optimistic UI Update
    setBugs((prev) =>
      prev.map((b) => (b.id === bugId ? { ...b, status: nextStatus } : b))
    );

    // Backend PATCH Call
    await apiService.toggleResolveBug(bugId, nextStatus);
  };

  // Filter calculations
  const filteredBugs = bugs.filter((bug) => {
    const matchSeverity = selectedSeverity === "All" || bug.severity === selectedSeverity;
    const matchSearch =
      searchQuery === "" ||
      bug.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
      bug.file.toLowerCase().includes(searchQuery.toLowerCase()) ||
      bug.id.toLowerCase().includes(searchQuery.toLowerCase());
    return matchSeverity && matchSearch;
  });

  const resolvedCount = bugs.filter((b) => b.status === "Resolved").length;
  const resolutionPercentage = Math.round((resolvedCount / (bugs.length || 1)) * 100);

  return (
    <div className="min-h-screen bg-[#0B0F17] text-slate-200 font-sans flex text-xs sm:text-sm">
      {/* ===================================================================== */}
      {/* 4-TAB FIXED SIDEBAR */}
      {/* ===================================================================== */}
      <aside className="w-16 bg-[#0F1623] border-r border-slate-800 flex flex-col items-center py-4 space-y-5 shrink-0 sticky top-0 h-screen z-30">
        <div className="p-2.5 bg-cyan-500/10 rounded-xl text-cyan-400 border border-cyan-500/20">
          <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"/></svg>
        </div>

        <nav className="flex flex-col space-y-2.5 w-full items-center pt-2">
          {/* TAB 1: DASHBOARD */}
          <button
            onClick={() => setActiveTab("dashboard")}
            title="Tab 1: Dashboard"
            className={`p-3 w-full flex justify-center transition-all ${
              activeTab === "dashboard"
                ? "bg-cyan-500/15 text-cyan-400 border-l-2 border-cyan-400"
                : "text-slate-400 hover:text-white"
            }`}
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z"/></svg>
          </button>

          {/* TAB 2: AI ANALYSIS */}
          <button
            onClick={() => setActiveTab("ai")}
            title="Tab 2: AI Codebase Intelligence"
            className={`p-3 w-full flex justify-center transition-all ${
              activeTab === "ai"
                ? "bg-cyan-500/15 text-cyan-400 border-l-2 border-cyan-400"
                : "text-slate-400 hover:text-white"
            }`}
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 3v4M3 5h4M6 17v4m-2-2h4m5-16l2.286 6.857L21 12l-5.714 2.143L13 21l-2.286-6.857L5 12l5.714-2.143L13 3z"/></svg>
          </button>

          {/* TAB 3: DEBUGGING */}
          <button
            onClick={() => setActiveTab("debug")}
            title="Tab 3: Debugging (By File & Line)"
            className={`p-3 w-full flex justify-center transition-all ${
              activeTab === "debug"
                ? "bg-cyan-500/15 text-cyan-400 border-l-2 border-cyan-400"
                : "text-slate-400 hover:text-white"
            }`}
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 4v1m6 11h2m-6 0h-2v4m0-11v3m0 0h.01M12 12h4.01M16 20h4M4 12h4m12 0a8 8 0 11-16 0 8 8 0 0116 0z"/></svg>
          </button>

          {/* TAB 4: REPORT */}
          <button
            onClick={() => setActiveTab("report")}
            title="Tab 4: Executive Report & Export"
            className={`p-3 w-full flex justify-center transition-all ${
              activeTab === "report"
                ? "bg-cyan-500/15 text-cyan-400 border-l-2 border-cyan-400"
                : "text-slate-400 hover:text-white"
            }`}
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/></svg>
          </button>
        </nav>

        <div className="mt-auto">
          <div className="w-8 h-8 rounded-full bg-cyan-900 text-cyan-200 flex items-center justify-center font-bold text-xs border border-cyan-600">
            AD
          </div>
        </div>
      </aside>

      {/* ===================================================================== */}
      {/* MAIN VIEWPORT */}
      {/* ===================================================================== */}
      <div className="flex-1 flex flex-col min-w-0 overflow-y-auto">
        {/* Persistent Top Header */}
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
          </div>
        </header>

        <main className="p-6 space-y-6 max-w-[1400px] mx-auto w-full">
          {/* ================================================================= */}
          {/* TAB 1: DASHBOARD */}
          {/* ================================================================= */}
          {activeTab === "dashboard" && (
            <div className="space-y-6">
              {/* Scan Box */}
              <div className="bg-[#131B2E] border border-slate-800 rounded-xl p-6 shadow-xl space-y-6">
                <div>
                  <h2 className="text-xl font-semibold text-white">Scan your repository in seconds</h2>
                  <p className="text-slate-400 text-xs mt-1">Paste a link or upload your code. We'll do the rest.</p>
                </div>

                <div className="bg-[#0B0F17] border border-slate-800 rounded-lg p-5 grid grid-cols-1 lg:grid-cols-12 gap-6 items-center">
                  <form onSubmit={handleAnalyze} className="lg:col-span-6 space-y-3">
                    <label className="text-xs text-slate-400 block font-medium">Paste GitHub repository link</label>
                    <input
                      type="text"
                      value={repoInput}
                      onChange={(e) => setRepoInput(e.target.value)}
                      className="w-full bg-[#131B2E] border border-slate-700 rounded-md px-3 py-2 text-xs text-white focus:outline-none focus:border-cyan-500 font-mono"
                    />
                    <button
                      type="submit"
                      disabled={isScanning}
                      className="w-full bg-cyan-400 hover:bg-cyan-300 text-slate-950 font-bold py-2 rounded-md text-xs transition-colors flex justify-center items-center gap-1.5"
                    >
                      {isScanning ? "Analyzing..." : "Analyze Repository →"}
                    </button>
                  </form>

                  <div className="hidden lg:flex lg:col-span-1 justify-center text-slate-500 text-xs font-bold">OR</div>

                  <div
                    onClick={() => handleAnalyze()}
                    className="lg:col-span-5 border-2 border-dashed border-slate-800 hover:border-cyan-500/40 rounded-lg p-6 text-center bg-[#0F1623]/50 cursor-pointer"
                  >
                    <p className="text-xs text-slate-300 font-medium">Drag & drop your .zip file here</p>
                    <span className="bg-slate-800 border border-slate-700 text-slate-200 text-xs px-3 py-1 rounded inline-block mt-2 font-medium">Choose ZIP File</span>
                  </div>
                </div>

                {/* Scanning Progress */}
                <div className="border-t border-slate-800/80 pt-4 space-y-2">
                  <div className="flex justify-between text-xs">
                    <span className="text-slate-300 font-medium">Analyzing {stats.totalFiles} files</span>
                    <span className="text-cyan-400 font-bold">{scanProgress}%</span>
                  </div>
                  <div className="w-full bg-slate-800 h-2 rounded-full overflow-hidden">
                    <div className="bg-cyan-400 h-full transition-all duration-300" style={{ width: `${scanProgress}%` }}></div>
                  </div>
                </div>
              </div>

              {/* 5 Metric KPI Cards */}
              <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
                <div className="bg-[#131B2E] border border-slate-800 p-4 rounded-xl">
                  <span className="text-slate-400 text-xs">Total Bugs</span>
                  <div className="text-2xl font-bold text-white mt-1">{stats.totalBugs}</div>
                  <span className="text-[10px] text-slate-500">Across {stats.totalFiles} files</span>
                </div>
                <div className="bg-[#131B2E] border border-slate-800 p-4 rounded-xl">
                  <span className="text-slate-400 text-xs">Critical</span>
                  <div className="text-2xl font-bold text-red-400 mt-1">{stats.critical}</div>
                  <span className="text-[10px] text-slate-500">Needs immediate attention</span>
                </div>
                <div className="bg-[#131B2E] border border-slate-800 p-4 rounded-xl">
                  <span className="text-slate-400 text-xs">High</span>
                  <div className="text-2xl font-bold text-amber-400 mt-1">{stats.high}</div>
                  <span className="text-[10px] text-slate-500">Should be fixed soon</span>
                </div>
                <div className="bg-[#131B2E] border border-slate-800 p-4 rounded-xl">
                  <span className="text-slate-400 text-xs">Medium</span>
                  <div className="text-2xl font-bold text-yellow-400 mt-1">{stats.medium}</div>
                  <span className="text-[10px] text-slate-500">Important but not urgent</span>
                </div>
                <div className="bg-[#131B2E] border border-slate-800 p-4 rounded-xl col-span-2 md:col-span-1">
                  <span className="text-slate-400 text-xs">Low</span>
                  <div className="text-2xl font-bold text-blue-400 mt-1">{stats.low}</div>
                  <span className="text-[10px] text-slate-500">Nice to fix</span>
                </div>
              </div>

              {/* Stacked Bars */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div className="bg-[#131B2E] border border-slate-800 p-5 rounded-xl space-y-4">
                  <h3 className="font-semibold text-white text-xs">Issues by Severity</h3>
                  <div className="h-6 w-full rounded-md overflow-hidden flex text-[10px] font-bold text-slate-900">
                    <div className="bg-red-500 flex items-center justify-center" style={{ width: `${stats.severityBreakdown.critical}%` }}>{stats.severityBreakdown.critical}%</div>
                    <div className="bg-amber-500 flex items-center justify-center" style={{ width: `${stats.severityBreakdown.high}%` }}>{stats.severityBreakdown.high}%</div>
                    <div className="bg-yellow-400 flex items-center justify-center" style={{ width: `${stats.severityBreakdown.medium}%` }}>{stats.severityBreakdown.medium}%</div>
                    <div className="bg-blue-500 flex items-center justify-center" style={{ width: `${stats.severityBreakdown.low}%` }}>{stats.severityBreakdown.low}%</div>
                  </div>
                </div>

                <div className="bg-[#131B2E] border border-slate-800 p-5 rounded-xl space-y-2.5">
                  <h3 className="font-semibold text-white text-xs">Priority Breakdown</h3>
                  {stats.priorityBreakdown.map((item, idx) => (
                    <div key={idx} className="flex items-center space-x-3 text-xs">
                      <span className="w-28 text-slate-400">{item.label}</span>
                      <div className="flex-1 bg-slate-800 h-2 rounded-full overflow-hidden">
                        <div className={`${item.color} h-full`} style={{ width: item.width }}></div>
                      </div>
                      <span className="text-slate-300 w-16 text-right font-mono">{item.count}</span>
                    </div>
                  ))}
                </div>
              </div>

              {/* Bug Table & Deep Inspector */}
              <div className="bg-[#131B2E] border border-slate-800 rounded-xl p-5 space-y-4">
                <div className="flex justify-between items-center flex-wrap gap-2">
                  <h3 className="font-semibold text-white text-sm">What to fix first (Top urgent issues)</h3>
                  <input
                    type="text"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    placeholder="Search by title or file..."
                    className="bg-[#0B0F17] border border-slate-700 rounded px-3 py-1 text-xs text-white"
                  />
                </div>

                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs min-w-[700px]">
                    <thead>
                      <tr className="border-b border-slate-800 text-slate-400">
                        <th className="py-2.5 px-3">#</th>
                        <th className="py-2.5 px-3">Bug ID</th>
                        <th className="py-2.5 px-3">Title</th>
                        <th className="py-2.5 px-3">Severity</th>
                        <th className="py-2.5 px-3">File & Line</th>
                        <th className="py-2.5 px-3">Status</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800/50">
                      {filteredBugs.map((bug, idx) => (
                        <React.Fragment key={bug.id}>
                          <tr
                            onClick={() => setExpandedBug(expandedBug === bug.id ? null : bug.id)}
                            className="hover:bg-slate-800/40 cursor-pointer transition-colors"
                          >
                            <td className="py-3 px-3 text-slate-500">{idx + 1}</td>
                            <td className="py-3 px-3 font-mono text-slate-300">{bug.id}</td>
                            <td className="py-3 px-3 font-medium text-white">{bug.title}</td>
                            <td className="py-3 px-3">
                              <span className={`px-2 py-0.5 rounded text-[10px] ${bug.severity === "Critical" ? "text-red-400 bg-red-500/10 border border-red-500/30" : "text-amber-400 bg-amber-500/10"}`}>
                                {bug.severity}
                              </span>
                            </td>
                            <td className="py-3 px-3 font-mono text-slate-400">{bug.file}:{bug.line}</td>
                            <td className="py-3 px-3">
                              <span className={`px-2 py-0.5 rounded text-[10px] border ${bug.status === "Resolved" ? "text-emerald-400 border-emerald-500/30" : "text-blue-400 border-blue-500/30"}`}>
                                {bug.status}
                              </span>
                            </td>
                          </tr>

                          {expandedBug === bug.id && (
                            <tr>
                              <td colSpan="6" className="p-4 bg-[#0B0F17] border-t border-slate-800 space-y-3">
                                <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                                  {/* Snippet */}
                                  <div className="bg-[#0F1623] border border-slate-800 p-3 rounded font-mono text-[11px]">
                                    {bug.codeSnippet.map((l) => (
                                      <div key={l.num} className={l.isErr ? "bg-red-500/20 text-red-300 pl-2 border-l-2 border-red-500" : "text-slate-500 pl-2"}>
                                        <span className="inline-block w-8 text-slate-600">{l.num}</span> {l.text}
                                      </div>
                                    ))}
                                  </div>

                                  {/* Fix */}
                                  <div className="space-y-2 text-xs">
                                    <p className="text-slate-300"><strong>What's wrong:</strong> {bug.wrong}</p>
                                    <div className="bg-[#0F1623] border border-slate-800 p-2.5 rounded font-mono text-[11px]">
                                      <div className="text-red-400">{bug.suggestedFix.remove}</div>
                                      <div className="text-emerald-400 whitespace-pre-line">{bug.suggestedFix.add}</div>
                                    </div>
                                  </div>
                                </div>

                                <button
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    handleToggleResolve(bug.id);
                                  }}
                                  className={`px-3 py-1.5 rounded text-xs font-semibold ${
                                    bug.status === "Resolved" ? "bg-emerald-600 text-white" : "bg-slate-800 border border-slate-700 text-slate-200"
                                  }`}
                                >
                                  {bug.status === "Resolved" ? "✓ Marked as Resolved" : "Mark as Resolved"}
                                </button>
                              </td>
                            </tr>
                          )}
                        </React.Fragment>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}

          {/* ================================================================= */}
          {/* TAB 2: AI CODEBASE ANALYSIS */}
          {/* ================================================================= */}
          {activeTab === "ai" && (
            <div className="space-y-6">
              <h2 className="text-xl font-bold text-white">✨ AI Codebase Intelligence</h2>
              <div className="bg-[#131B2E] border border-slate-800 rounded-xl p-5 space-y-3">
                <h3 className="font-bold text-white text-sm">Overall Purpose & Architecture</h3>
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
          {/* TAB 3: DEBUGGING (GROUPED BY FILE) */}
          {/* ================================================================= */}
          {activeTab === "debug" && (
            <div className="space-y-6">
              <h2 className="text-xl font-bold text-white">🐛 Debugging & Code Issue Inspector</h2>
              <div className="space-y-4">
                {filteredBugs.map((bug) => (
                  <div key={bug.id} className="bg-[#131B2E] border border-slate-800 rounded-xl p-4 space-y-3">
                    <div className="flex justify-between items-center">
                      <span className="font-mono text-xs font-bold text-cyan-400">{bug.file}:{bug.line}</span>
                      <span className="text-red-400 text-[10px] border border-red-500/30 px-2 py-0.5 rounded">{bug.severity}</span>
                    </div>
                    <h4 className={`text-xs font-semibold ${bug.status === "Resolved" ? "line-through text-slate-500" : "text-white"}`}>
                      {bug.title}
                    </h4>
                    <div className="bg-[#0B0F17] p-3 rounded font-mono text-[11px]">
                      {bug.codeSnippet.map((l) => (
                        <div key={l.num} className={l.isErr ? "bg-red-500/20 text-red-300 pl-2 border-l-2 border-red-500" : "text-slate-500 pl-2"}>
                          {l.num} {l.text}
                        </div>
                      ))}
                    </div>
                    <button
                      onClick={() => handleToggleResolve(bug.id)}
                      className={`px-3 py-1.5 rounded text-xs font-medium ${
                        bug.status === "Resolved" ? "bg-emerald-600 text-white" : "bg-slate-800 border border-slate-700 text-slate-200"
                      }`}
                    >
                      {bug.status === "Resolved" ? "✓ Resolved" : "Mark as Resolved"}
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* ================================================================= */}
          {/* TAB 4: REPORT */}
          {/* ================================================================= */}
          {activeTab === "report" && (
            <div className="space-y-6">
              <div className="flex justify-between items-center">
                <h2 className="text-xl font-bold text-white">📄 Code Resolution Audit Report</h2>
                <button onClick={() => window.print()} className="bg-cyan-400 text-slate-950 font-bold px-3 py-1.5 rounded text-xs">
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
                <table className="w-full text-left text-xs">
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
