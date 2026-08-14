import React, { useState } from "react";

export default function App() {
  // Navigation State: 'dashboard' | 'ai' | 'debug' | 'report'
  const [activeTab, setActiveTab] = useState("dashboard");
  const [dashboardSubView, setDashboardSubView] = useState("scanner"); // 'scanner' | 'overview'
  const [expandedBug, setExpandedBug] = useState("BUG-2026-0091");
  const [scanProgress, setScanProgress] = useState(67);

  // Synced Bug List (Changes here update both Debugging and Report tabs)
  const [bugs, setBugs] = useState([
    {
      id: "BUG-2026-0091",
      file: "src/db/queryBuilder.py",
      line: 118,
      title: "SQL Injection vulnerability in user query builder",
      severity: "Critical",
      priority: "P1 • Fix now",
      status: "Open",
      wrong: "User input is concatenated directly into SQL query without parameterization.",
      matter: "An attacker could read, change, or delete sensitive records in your database.",
      snippet: [
        { num: 114, text: "def getUserData(userId):", isErr: false },
        { num: 115, text: "    conn = getConnectbile()", isErr: false },
        { num: 116, text: "    cursor = conn.cursor()", isErr: false },
        { num: 117, text: '    query = "SELECT * FROM users WHERE id = " + userId', isErr: true },
        { num: 118, text: "    results = cursor.fetchall()", isErr: true },
        { num: 119, text: "    conn.close()", isErr: false },
        { num: 120, text: "    return results", isErr: false }
      ],
      fixRemove: '- query = "SELECT * FROM users WHERE id = " + userId',
      fixAdd: '+ query = "SELECT * FROM users WHERE id = %s"\n+ cursor.execute(query, (userId,))'
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
        { num: 43, text: "aws s3 sync ./build s3://production-bucket", isErr: false }
      ],
      fixRemove: '- export AWS_SECRET_ACCESS_KEY="wJalrXUtnFEMI..."',
      fixAdd: '+ export AWS_SECRET_ACCESS_KEY="${ENV_AWS_SECRET}"'
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
        { num: 98, text: "    return charge_card(cart.user, total)", isErr: false }
      ],
      fixRemove: "- total = sum([item.price for item in items])",
      fixAdd: "+ if not items: raise EmptyCartException('No items in cart')\n+ total = sum([item.price for item in items])"
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
        { num: 214, text: "    # Missing: active_connections.remove(websocket)", isErr: true }
      ],
      fixRemove: "- # Missing connection cleanup",
      fixAdd: "+ active_connections.discard(websocket)"
    }
  ]);

  // Per-File AI Decomposition Data (Tab 2)
  const fileSummaries = [
    {
      file: "src/db/queryBuilder.py",
      role: "Database abstraction layer and dynamic SQL query generator.",
      intent: "Constructs SQL queries for user authentication and records retrieval.",
      status: "Security Risk",
      statusColor: "text-red-400 border-red-500/30 bg-red-500/10"
    },
    {
      file: "scripts/deploy.sh",
      role: "Continuous deployment and AWS S3/CloudFront build pipeline sync.",
      intent: "Automates packaging and deploying static frontend bundles to cloud infrastructure.",
      status: "Credential Leak",
      statusColor: "text-red-400 border-red-500/30 bg-red-500/10"
    },
    {
      file: "src/cart/checkout.py",
      role: "Shopping cart lifecycle and payment gateway processing controller.",
      intent: "Calculates cart item subtotals, tax rates, and coordinates checkout billing API calls.",
      status: "Null Safety Issue",
      statusColor: "text-amber-400 border-amber-500/30 bg-amber-500/10"
    },
    {
      file: "src/ws/handler.py",
      role: "Real-time bidirectional WebSocket event broadcaster and socket pool.",
      intent: "Maintains live client notification connections and broadcasts order status telemetry.",
      status: "Memory Leak",
      statusColor: "text-amber-400 border-amber-500/30 bg-amber-500/10"
    }
  ];

  const toggleResolve = (id) => {
    setBugs(prev =>
      prev.map(b => (b.id === id ? { ...b, status: b.status === "Resolved" ? "Open" : "Resolved" } : b))
    );
  };

  return (
    <div className="min-h-screen bg-[#0B0F17] text-slate-200 font-sans flex text-xs sm:text-sm">
      {/* 4-TAB SIDEBAR */}
      <aside className="w-16 bg-[#0F1623] border-r border-slate-800 flex flex-col items-center py-5 space-y-6 shrink-0 sticky top-0 h-screen z-30">
        <div className="p-2.5 bg-cyan-500/10 rounded-xl text-cyan-400 border border-cyan-500/20">
          <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"/></svg>
        </div>

        <nav className="flex flex-col space-y-3 w-full items-center pt-2">
          {/* Tab 1: Dashboard */}
          <button
            onClick={() => setActiveTab("dashboard")}
            title="Dashboard"
            className={`p-3 w-full flex justify-center transition-all ${
              activeTab === "dashboard" ? "bg-cyan-500/15 text-cyan-400 border-l-2 border-cyan-400" : "text-slate-400 hover:text-white"
            }`}
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z"/></svg>
          </button>

          {/* Tab 2: AI Analysis */}
          <button
            onClick={() => setActiveTab("ai")}
            title="AI Codebase Analysis"
            className={`p-3 w-full flex justify-center transition-all ${
              activeTab === "ai" ? "bg-cyan-500/15 text-cyan-400 border-l-2 border-cyan-400" : "text-slate-400 hover:text-white"
            }`}
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 3v4M3 5h4M6 17v4m-2-2h4m5-16l2.286 6.857L21 12l-5.714 2.143L13 21l-2.286-6.857L5 12l5.714-2.143L13 3z"/></svg>
          </button>

          {/* Tab 3: Debugging */}
          <button
            onClick={() => setActiveTab("debug")}
            title="Debugging (By File & Line)"
            className={`p-3 w-full flex justify-center transition-all ${
              activeTab === "debug" ? "bg-cyan-500/15 text-cyan-400 border-l-2 border-cyan-400" : "text-slate-400 hover:text-white"
            }`}
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 4v1m6 11h2m-6 0h-2v4m0-11v3m0 0h.01M12 12h4.01M16 20h4M4 12h4m12 0a8 8 0 11-16 0 8 8 0 0116 0z"/></svg>
          </button>

          {/* Tab 4: Report */}
          <button
            onClick={() => setActiveTab("report")}
            title="Consolidated Report"
            className={`p-3 w-full flex justify-center transition-all ${
              activeTab === "report" ? "bg-cyan-500/15 text-cyan-400 border-l-2 border-cyan-400" : "text-slate-400 hover:text-white"
            }`}
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/></svg>
          </button>
        </nav>

        <div className="mt-auto">
          <div className="w-8 h-8 rounded-full bg-cyan-800 text-cyan-200 flex items-center justify-center font-bold text-xs">
            AD
          </div>
        </div>
      </aside>

      {/* MAIN VIEWPORT */}
      <div className="flex-1 flex flex-col min-w-0 overflow-y-auto">
        {/* Header */}
        <header className="h-14 bg-[#0F1623] border-b border-slate-800 px-6 flex items-center justify-between sticky top-0 z-20">
          <div className="flex items-center space-x-3">
            <h1 className="font-semibold text-white text-base">AI Bug Tracking & Prioritization System</h1>
            <span className="text-[11px] text-slate-400 hidden xl:inline">AST, Static Analysis, NLP & Similarity Search</span>
          </div>
          <div className="flex items-center space-x-4">
            <span className="bg-red-500/15 text-red-400 border border-red-500/30 px-2.5 py-1 rounded-full text-xs font-medium">
              8 critical issues
            </span>
          </div>
        </header>

        <main className="p-6 space-y-6 max-w-[1400px] mx-auto w-full">

          {/* ========================================================================= */}
          {/* TAB 1: DASHBOARD                                                          */}
          {/* ========================================================================= */}
          {activeTab === "dashboard" && (
            <div className="space-y-6">
              <div className="flex space-x-2 bg-[#0F1623] p-1 rounded-lg border border-slate-800 w-fit">
                <button
                  onClick={() => setDashboardSubView("scanner")}
                  className={`px-3 py-1.5 rounded-md text-xs font-medium ${
                    dashboardSubView === "scanner" ? "bg-cyan-500 text-slate-950 font-bold" : "text-slate-400"
                  }`}
                >
                  1. Repository Scanner
                </button>
                <button
                  onClick={() => setDashboardSubView("overview")}
                  className={`px-3 py-1.5 rounded-md text-xs font-medium ${
                    dashboardSubView === "overview" ? "bg-cyan-500 text-slate-950 font-bold" : "text-slate-400"
                  }`}
                >
                  2. Security & KPI Overview
                </button>
              </div>

              {dashboardSubView === "scanner" ? (
                <div className="bg-[#131B2E] border border-slate-800 rounded-xl p-6 shadow-xl space-y-6">
                  <h2 className="text-xl font-semibold text-white">Scan your repository in seconds</h2>
                  <div className="bg-[#0B0F17] border border-slate-800 rounded-lg p-5 grid grid-cols-1 lg:grid-cols-12 gap-6 items-center">
                    <div className="lg:col-span-6 space-y-3">
                      <label className="text-xs text-slate-400 block font-medium">Paste GitHub repository link</label>
                      <input
                        type="text"
                        defaultValue="https://github.com/your-org/your-repo"
                        className="w-full bg-[#131B2E] border border-slate-700 rounded-md px-3 py-2 text-xs text-white focus:outline-none focus:border-cyan-500 font-mono"
                      />
                      <button
                        onClick={() => setDashboardSubView("overview")}
                        className="w-full bg-cyan-400 hover:bg-cyan-300 text-slate-950 font-semibold py-2 rounded-md text-xs transition-colors"
                      >
                        Analyze Repository &rarr;
                      </button>
                    </div>

                    <div className="hidden lg:flex lg:col-span-1 justify-center text-slate-500 text-xs font-bold">OR</div>

                    <div
                      onClick={() => setDashboardSubView("overview")}
                      className="lg:col-span-5 border-2 border-dashed border-slate-800 hover:border-cyan-500/40 rounded-lg p-6 text-center bg-[#0F1623]/50 cursor-pointer"
                    >
                      <p className="text-xs text-slate-300 font-medium">Drag & drop your .zip file here</p>
                      <span className="bg-slate-800 border border-slate-700 text-slate-200 text-xs px-3 py-1 rounded inline-block mt-2">Choose ZIP File</span>
                    </div>
                  </div>

                  {/* Progress */}
                  <div className="border-t border-slate-800 pt-4 space-y-2">
                    <div className="flex justify-between text-xs">
                      <span className="text-slate-300">Analyzing 1,842 files</span>
                      <span className="text-cyan-400 font-bold">{scanProgress}%</span>
                    </div>
                    <div className="w-full bg-slate-800 h-2 rounded-full overflow-hidden">
                      <div className="bg-cyan-400 h-full" style={{ width: `${scanProgress}%` }}></div>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="space-y-6">
                  {/* KPI Cards */}
                  <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
                    <div className="bg-[#131B2E] border border-slate-800 p-4 rounded-xl">
                      <span className="text-slate-400 text-xs">Total Bugs</span>
                      <div className="text-2xl font-bold text-white mt-1">128</div>
                    </div>
                    <div className="bg-[#131B2E] border border-slate-800 p-4 rounded-xl">
                      <span className="text-slate-400 text-xs">Critical</span>
                      <div className="text-2xl font-bold text-red-400 mt-1">8</div>
                    </div>
                    <div className="bg-[#131B2E] border border-slate-800 p-4 rounded-xl">
                      <span className="text-slate-400 text-xs">High</span>
                      <div className="text-2xl font-bold text-amber-400 mt-1">32</div>
                    </div>
                    <div className="bg-[#131B2E] border border-slate-800 p-4 rounded-xl">
                      <span className="text-slate-400 text-xs">Medium</span>
                      <div className="text-2xl font-bold text-yellow-400 mt-1">54</div>
                    </div>
                    <div className="bg-[#131B2E] border border-slate-800 p-4 rounded-xl">
                      <span className="text-slate-400 text-xs">Low</span>
                      <div className="text-2xl font-bold text-blue-400 mt-1">34</div>
                    </div>
                  </div>

                  {/* Severity Breakdown Bar */}
                  <div className="bg-[#131B2E] border border-slate-800 p-5 rounded-xl space-y-3">
                    <h3 className="font-semibold text-white text-xs">Issues by Severity</h3>
                    <div className="h-6 w-full rounded-md overflow-hidden flex text-[10px] font-bold text-slate-900">
                      <div className="bg-red-500 w-[6.3%] flex items-center justify-center">6%</div>
                      <div className="bg-amber-500 w-[25%] flex items-center justify-center">25%</div>
                      <div className="bg-yellow-400 w-[42%] flex items-center justify-center">42%</div>
                      <div className="bg-blue-500 w-[27%] flex items-center justify-center">27%</div>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* ========================================================================= */}
          {/* TAB 2: AI CODEBASE ANALYSIS                                               */}
          {/* ========================================================================= */}
          {activeTab === "ai" && (
            <div className="space-y-6">
              <div className="border-b border-slate-800 pb-3">
                <h2 className="text-xl font-bold text-white">✨ AI Codebase Intelligence</h2>
                <p className="text-xs text-slate-400 mt-0.5">Automated functional breakdown explaining repository intent and per-file responsibilities.</p>
              </div>

              <div className="bg-[#131B2E] border border-slate-800 rounded-xl p-5 space-y-3">
                <h3 className="font-bold text-white text-sm">Overall Repository Summary</h3>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs">
                  <div className="bg-[#0B0F17] p-3 rounded border border-slate-800">
                    <span className="text-slate-500 uppercase text-[10px] font-bold">Intent</span>
                    <p className="text-slate-300 mt-1">Microservice backend handling auth, orders, and real-time alerts.</p>
                  </div>
                  <div className="bg-[#0B0F17] p-3 rounded border border-slate-800">
                    <span className="text-slate-500 uppercase text-[10px] font-bold">Stack</span>
                    <p className="text-cyan-300 font-mono mt-1">FastAPI, Python 3.11, PostgreSQL, Docker, AWS S3</p>
                  </div>
                  <div className="bg-[#0B0F17] p-3 rounded border border-slate-800">
                    <span className="text-slate-500 uppercase text-[10px] font-bold">Health Assessment</span>
                    <p className="text-slate-300 mt-1">Well structured, but requires fixing SQL injection and hardcoded keys.</p>
                  </div>
                </div>
              </div>

              {/* Per-File Summary Cards */}
              <div className="space-y-3">
                <h3 className="font-semibold text-white text-xs">Per-File Functional Decomposition</h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {fileSummaries.map((f, idx) => (
                    <div key={idx} className="bg-[#131B2E] border border-slate-800 rounded-xl p-4 space-y-2">
                      <div className="flex justify-between items-center">
                        <span className="font-mono text-xs font-bold text-white">{f.file}</span>
                        <span className={`text-[10px] px-2 py-0.5 rounded border font-medium ${f.statusColor}`}>{f.status}</span>
                      </div>
                      <p className="text-xs text-slate-300">{f.role}</p>
                      <div className="bg-[#0B0F17] p-2 rounded text-[11px] text-slate-400">
                        <strong className="text-slate-200">Intent: </strong>{f.intent}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* ========================================================================= */}
          {/* TAB 3: DEBUGGING (GROUPED BY FILE & LINE)                                 */}
          {/* ========================================================================= */}
          {activeTab === "debug" && (
            <div className="space-y-6">
              <div className="border-b border-slate-800 pb-3">
                <h2 className="text-xl font-bold text-white">🐛 Debugging & Issue Inspector</h2>
                <p className="text-xs text-slate-400 mt-0.5">Issues grouped by file name with highlighted line numbers and fixes.</p>
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
                            onClick={() => toggleResolve(bug.id)}
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

          {/* ========================================================================= */}
          {/* TAB 4: REPORT (WITH PRINT / PDF EXPORT)                                   */}
          {/* ========================================================================= */}
          {activeTab === "report" && (
            <div className="space-y-6">
              <div className="flex justify-between items-center border-b border-slate-800 pb-3">
                <div>
                  <h2 className="text-xl font-bold text-white">📄 Code Resolution Audit Report</h2>
                  <p className="text-xs text-slate-400 mt-0.5">Consolidated list of all issues with real-time fix status.</p>
                </div>
                <button
                  onClick={() => window.print()}
                  className="bg-cyan-400 hover:bg-cyan-300 text-slate-950 font-bold px-4 py-2 rounded-lg text-xs"
                >
                  Download Report (PDF)
                </button>
              </div>

              <div className="bg-[#131B2E] border border-slate-800 rounded-xl overflow-hidden">
                <table className="w-full text-left text-xs min-w-[700px]">
                  <thead>
                    <tr className="border-b border-slate-800 text-slate-400 bg-[#0F1623]">
                      <th className="py-3 px-4">#</th>
                      <th className="py-3 px-4">File Path</th>
                      <th className="py-3 px-4">Line</th>
                      <th className="py-3 px-4">Issue Description</th>
                      <th className="py-3 px-4">Severity</th>
                      <th className="py-3 px-4">Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/50">
                    {bugs.map((bug, idx) => (
                      <tr key={bug.id} className="hover:bg-slate-800/30">
                        <td className="py-3 px-4 text-slate-500">{idx + 1}</td>
                        <td className="py-3 px-4 font-mono text-cyan-300">{bug.file}</td>
                        <td className="py-3 px-4 font-mono text-slate-300">:{bug.line}</td>
                        <td className="py-3 px-4 text-white">{bug.title}</td>
                        <td className="py-3 px-4 text-red-400 font-bold">{bug.severity}</td>
                        <td className="py-3 px-4">
                          <span className={`px-2 py-0.5 rounded text-[10px] font-semibold ${bug.status === "Resolved" ? "bg-emerald-500/20 text-emerald-300" : "bg-red-500/10 text-red-400"}`}>
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
