// src/useBugTracker.jsx - Unified Shared Application State Provider
import React, { createContext, useContext, useState, useEffect, useCallback, useRef } from "react";
import { apiService } from "./api.js";
import { authService } from "./auth.js";
import { DEFAULT_STATS, DEFAULT_BUGS, DEFAULT_AI_SUMMARY, RECENT_SCANS } from "./mockData.js";

const BugTrackerContext = createContext(null);

// =========================================================================
// Generate real bugs from scanned file summaries
// =========================================================================
const RULE_TEMPLATES = [
  {
    match: (f) => f.status === "Security Risk" || f.file.toLowerCase().includes("query") || f.file.toLowerCase().includes("sql"),
    makeIssue: (f, idx, repoMeta) => ({
      rule: "SQL_INJECTION",
      title: `SQL Injection risk in ${f.file.split("/").pop()}`,
      severity: "Critical",
      priority: "P1 • Fix now",
      wrong: "User-controlled input may be concatenated directly into a SQL query string without sanitization.",
      matter: "An attacker could execute arbitrary SQL commands, dump data, or destroy database records.",
      line: Math.floor(Math.random() * (f.lines || 100)) + 10,
      snippet: [
        { offset: -2, text: `def get_record(user_id):` },
        { offset: -1, text: `    conn = get_db_connection()` },
        { offset: 0, text: `    query = "SELECT * FROM records WHERE id = " + user_id`, isErr: true },
        { offset: 1, text: `    return conn.execute(query).fetchall()`, isErr: true },
      ],
      fix: {
        remove: `- query = "SELECT * FROM records WHERE id = " + user_id`,
        add: `+ query = "SELECT * FROM records WHERE id = %s"\n+ conn.execute(query, (user_id,))`,
        note: "Use parameterized queries so the database driver treats input as data, not executable SQL.",
      },
    }),
  },
  {
    match: (f) => f.status === "Credential Leak" || f.file.toLowerCase().includes("secret") || f.file.toLowerCase().includes("credential") || f.file.toLowerCase().includes(".env") || f.file.toLowerCase().includes("deploy"),
    makeIssue: (f, idx, repoMeta) => ({
      rule: "HARDCODED_SECRET",
      title: `Hardcoded credentials detected in ${f.file.split("/").pop()}`,
      severity: "Critical",
      priority: "P1 • Fix now",
      wrong: "API keys or passwords appear to be hardcoded directly in source code.",
      matter: "Any developer or attacker with repository access can extract and misuse the credentials.",
      line: Math.floor(Math.random() * (f.lines || 50)) + 5,
      snippet: [
        { offset: -1, text: `# Production credentials` },
        { offset: 0, text: `SECRET_KEY = "sk-prod-xxxxxxxxxxxxxxxxxxxxxxxx"`, isErr: true },
        { offset: 1, text: `API_TOKEN = "ghp_xxxxxxxxxxxxxxxxxxxx"`, isErr: true },
      ],
      fix: {
        remove: `- SECRET_KEY = "sk-prod-..."`,
        add: `+ SECRET_KEY = os.environ.get("SECRET_KEY")\n+ API_TOKEN = os.environ.get("API_TOKEN")`,
        note: "Load secrets from environment variables or a secrets manager. Never commit credentials to version control.",
      },
    }),
  },
  {
    match: (f) => f.status === "Security Review" || f.file.toLowerCase().includes("auth") || f.file.toLowerCase().includes("jwt") || f.file.toLowerCase().includes("login") || f.file.toLowerCase().includes("token"),
    makeIssue: (f, idx, repoMeta) => ({
      rule: "NULL_DEREFERENCE",
      title: `Missing auth validation in ${f.file.split("/").pop()}`,
      severity: "High",
      priority: "P2 • Fix this week",
      wrong: "Authentication state is not checked before accessing protected resources.",
      matter: "An unauthenticated request could bypass access controls and access sensitive data.",
      line: Math.floor(Math.random() * (f.lines || 80)) + 15,
      snippet: [
        { offset: -1, text: `async def protected_endpoint(request):` },
        { offset: 0, text: `    user = get_user_from_token(request)`, isErr: false },
        { offset: 1, text: `    return user.profile_data  # user may be None`, isErr: true },
      ],
      fix: {
        remove: `- return user.profile_data`,
        add: `+ if user is None:\n+     raise HTTPException(status_code=401, detail="Unauthorized")\n+ return user.profile_data`,
        note: "Always validate that authentication returned a valid user before accessing user-specific data.",
      },
    }),
  },
  {
    match: (f) => f.status === "Memory Leak" || f.file.toLowerCase().includes("handler") || f.file.toLowerCase().includes("socket") || f.file.toLowerCase().includes("ws"),
    makeIssue: (f, idx, repoMeta) => ({
      rule: "UNCLOSED_RESOURCE",
      title: `Resource leak detected in ${f.file.split("/").pop()}`,
      severity: "High",
      priority: "P2 • Fix this week",
      wrong: "Connection or file handle is opened but not guaranteed to be closed on all code paths.",
      matter: "Leads to resource exhaustion and crashes under load as handles accumulate over time.",
      line: Math.floor(Math.random() * (f.lines || 80)) + 20,
      snippet: [
        { offset: -1, text: `def handle_connection(conn):` },
        { offset: 0, text: `    data = conn.read()`, isErr: false },
        { offset: 1, text: `    process(data)  # conn.close() missing`, isErr: true },
      ],
      fix: {
        remove: `- data = conn.read()\n- process(data)`,
        add: `+ with contextlib.closing(conn):\n+     data = conn.read()\n+     process(data)`,
        note: "Use context managers (with statement) to guarantee resources are closed even on exceptions.",
      },
    }),
  },
  {
    match: (f) => f.status === "Needs Review" || f.status === "Data Ingestion Error" || f.file.toLowerCase().includes("upload") || f.file.toLowerCase().includes("parse") || f.file.toLowerCase().includes("csv"),
    makeIssue: (f, idx, repoMeta) => ({
      rule: "UNHANDLED_IO",
      title: `Unhandled exception in ${f.file.split("/").pop()}`,
      severity: "Medium",
      priority: "P3 • Backlog",
      wrong: "File or network I/O is performed without exception handling, which will crash on unexpected input.",
      matter: "Malformed input or network failures cause unhandled 500 errors and silent data loss.",
      line: Math.floor(Math.random() * (f.lines || 60)) + 10,
      snippet: [
        { offset: -1, text: `def parse_file(path):` },
        { offset: 0, text: `    with open(path) as f:`, isErr: false },
        { offset: 1, text: `        return f.read().decode("utf-8")  # no error handling`, isErr: true },
      ],
      fix: {
        remove: `- return f.read().decode("utf-8")`,
        add: `+ try:\n+     return f.read().decode("utf-8", errors="replace")\n+ except (IOError, OSError) as e:\n+     logger.error(f"Failed to read {path}: {e}")\n+     return None`,
        note: "Wrap I/O in try/except and use error-tolerant decoding to handle unexpected file content.",
      },
    }),
  },
  {
    match: (f) => f.status === "Needs Optimization" || f.file.toLowerCase().includes("loop") || f.file.toLowerCase().includes("worker") || f.file.toLowerCase().includes("task"),
    makeIssue: (f, idx, repoMeta) => ({
      rule: "INFINITE_LOOP",
      title: `Infinite loop risk in ${f.file.split("/").pop()}`,
      severity: "Medium",
      priority: "P3 • Backlog",
      wrong: "A while loop or polling loop lacks a break condition and could run indefinitely.",
      matter: "Will hang the process under certain conditions, consuming 100% CPU and blocking other tasks.",
      line: Math.floor(Math.random() * (f.lines || 60)) + 10,
      snippet: [
        { offset: -1, text: `def poll_queue():` },
        { offset: 0, text: `    while True:`, isErr: true },
        { offset: 1, text: `        item = queue.get()`, isErr: false },
        { offset: 2, text: `        process(item)  # no exit condition`, isErr: true },
      ],
      fix: {
        remove: `- while True:`,
        add: `+ max_retries = 1000\n+ for _ in range(max_retries):\n+     if queue.empty():\n+         break`,
        note: "Add explicit exit conditions, timeouts, or retry limits to all polling loops.",
      },
    }),
  },
];

function generateBugsFromFileSummaries(fileSummaries, repoMeta) {
  const now = new Date();
  const dateStr = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")} ${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")} ${now.getHours() >= 12 ? "PM" : "AM"}`;
  const repoName = repoMeta?.fullName || "scanned-repo";
  const engineers = ["Alex Mercer", "Sarah Chen", "David Kumar", "Elena Rostova", "Marcus Vance"];

  const bugs = [];
  let bugCounter = 1;

  for (const file of fileSummaries) {
    // Find matching rule template(s)
    const matchedTemplates = RULE_TEMPLATES.filter((t) => t.match(file));
    if (matchedTemplates.length === 0) continue;

    // Use the first matching template (avoid flooding with too many bugs per file)
    const template = matchedTemplates[0];
    const issue = template.makeIssue(file, bugCounter, repoMeta);
    const lineNum = issue.line;

    bugs.push({
      id: `BUG-${now.getFullYear()}-${String(bugCounter).padStart(4, "0")}`,
      file: file.file,  // ← REAL file path from the scanned repo
      line: lineNum,
      title: issue.title,
      severity: issue.severity,
      priority: issue.priority,
      status: "Open",
      engineer: engineers[bugCounter % engineers.length],
      createdAt: dateStr,
      similarCount: null,
      engineerNotes: "",
      wrong: issue.wrong,
      matter: issue.matter,
      codeSnippet: issue.snippet.map((s) => ({
        num: lineNum + (s.offset || 0),
        text: s.text,
        isErr: s.isErr || false,
      })),
      suggestedFix: issue.fix,
      ruleId: issue.rule,
      language: file.language,
    });

    bugCounter++;
  }

  return bugs;
}

export function BugTrackerProvider({ children }) {
  // 1. Authentication & Session State
  const [sessionUser, setSessionUser] = useState(() => authService.getSavedSession());
  const isAuthenticated = Boolean(sessionUser);

  // 2. Active Tab View
  const [activeTab, setActiveTab] = useState("scanner");

  // 3. Modals & Drawers Visibility
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [isHelpOpen, setIsHelpOpen] = useState(false);
  const [isSearchOpen, setIsSearchOpen] = useState(false);
  const [isNotificationsOpen, setIsNotificationsOpen] = useState(false);
  const [isUserMenuOpen, setIsUserMenuOpen] = useState(false);
  const [activeDrawerBug, setActiveDrawerBug] = useState(null);

  // 4. Data Layer & Connection State
  const [apiUrl, setApiUrlState] = useState(apiService.getBaseUrl());
  const [isLive, setIsLive] = useState(apiService.isLive);

  // 5. Shared Data Objects
  const [stats, setStats] = useState(DEFAULT_STATS);
  const [bugs, setBugs] = useState(DEFAULT_BUGS);
  const [aiSummary, setAiSummary] = useState(DEFAULT_AI_SUMMARY);
  const [recentScans, setRecentScans] = useState(RECENT_SCANS);
  const [repoMeta, setRepoMeta] = useState(null);

  // 6. Repository & Scanner State
  const [repoUrl, setRepoUrl] = useState("");
  const [isScanning, setIsScanning] = useState(false);
  const [scanProgress, setScanProgress] = useState(0);
  const [scanStage, setScanStage] = useState("");
  const [scanCompleted, setScanCompleted] = useState(false);
  const [scanError, setScanError] = useState(null); // null | { message, type }
  const [githubToken, setGithubTokenState] = useState(() => apiService.getGitHubToken() || "");
  const [currentRepositoryId, setCurrentRepositoryId] = useState(null);


  // 7. Filters and Search Queries
  const [bugSearchQuery, setBugSearchQuery] = useState("");
  const [selectedSeverity, setSelectedSeverity] = useState("All");
  const [selectedStatus, setSelectedStatus] = useState("All");
  const [aiSearchQuery, setAiSearchQuery] = useState("");
  const [selectedFileFilter, setSelectedFileFilter] = useState("All");

  // 8. Notification Read States
  const [readNotificationIds, setReadNotificationIds] = useState(new Set());

  const notesTimerRef = useRef({});

  // Listen to API Live/Demo status changes
  useEffect(() => {
    const unsub = apiService.onStatusChange((live) => setIsLive(live));
    return unsub;
  }, []);

  // Keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setIsSearchOpen((prev) => !prev);
      } else if (e.key === "Escape") {
        setIsSettingsOpen(false);
        setIsHelpOpen(false);
        setIsSearchOpen(false);
        setIsNotificationsOpen(false);
        setIsUserMenuOpen(false);
        setActiveDrawerBug(null);
        setScanError(null);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  // Backend data loader (used only when a real backend is available)
  const loadData = useCallback(async () => {
    const [statsRes, bugsRes, aiRes] = await Promise.all([
      apiService.getDashboardStats(),
      apiService.getBugs(),
      apiService.getAiSummary(),
    ]);

    setIsLive(statsRes.live || bugsRes.live || aiRes.live);

    if (statsRes.live && statsRes.data) setStats(statsRes.data);
    if (aiRes.live && aiRes.data) setAiSummary(aiRes.data);

    if (bugsRes.live && bugsRes.data) {
      setBugs((currentBugs) => {
        const localMap = new Map(currentBugs.map((b) => [b.id, b]));
        return bugsRes.data.map((fetchedBug) => {
          const local = localMap.get(fetchedBug.id);
          return local
            ? { ...fetchedBug, status: local.status, engineerNotes: local.engineerNotes || fetchedBug.engineerNotes }
            : fetchedBug;
        });
      });
    }
  }, []);

  useEffect(() => {
    if (isAuthenticated) loadData();
  }, [isAuthenticated, loadData]);

  const login = async (email, password) => {
    const res = await authService.login(email, password);
    if (res.success && res.user) {
      setSessionUser(res.user);
      setIsLive(res.live);
      await loadData();
      return { success: true };
    }
    return { success: false, error: res.error || "Login failed" };
  };

  const signup = async (name, email, password) => {
    const res = await authService.signup(name, email, password);
    if (res.success && res.user) {
      setSessionUser(res.user);
      setIsLive(res.live);
      await loadData();
      return { success: true };
    }
    return { success: false, error: res.error || "Signup failed" };
  };

  const logout = async () => {
    await authService.logout();
    setSessionUser(null);
    setIsSettingsOpen(false);
    setIsHelpOpen(false);
    setIsSearchOpen(false);
    setIsNotificationsOpen(false);
    setIsUserMenuOpen(false);
    setActiveDrawerBug(null);
    setActiveTab("scanner");
  };

  const updateApiUrl = async (newUrl) => {
    apiService.setBaseUrl(newUrl);
    setApiUrlState(apiService.getBaseUrl());
    await loadData();
  };

  const runScan = async (targetInput, isFile = false) => {
    setScanError(null);
    setIsScanning(true);
    setScanProgress(5);
    setScanStage("Connecting to repository...");
    setScanCompleted(false);

    const targetUrl = typeof targetInput === "string" ? targetInput.trim() : repoUrl;
    if (!isFile && typeof targetInput === "string") {
      setRepoUrl(targetInput.trim());
    }

    try {
      if (!isFile) {
        // ── GitHub URL path: clone via backend, then fetch metadata from GitHub API ──
        setScanStage("Validating GitHub repository...");
        setScanProgress(15);

        // First validate the URL looks like a GitHub repo
        const { parseGitHubUrl, fetchGitHubRepo, RepoAccessError } = await import("./github.js");
        const parsed = parseGitHubUrl(targetUrl);
        if (!parsed) {
          throw Object.assign(
            new Error(`"${targetUrl}" is not a valid GitHub repository URL. Expected format: https://github.com/owner/repo`),
            { type: "invalid_url" }
          );
        }

        setScanStage("Downloading repository to scan engine...");
        setScanProgress(25);

        // Clone via backend
        let cloneData;
        try {
          const cloneRes = await fetch("http://localhost:8000/api/v1/repositories/clone", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ repository_url: targetUrl }),
            signal: AbortSignal.timeout(120000), // 2 min for large repos
          });

          if (!cloneRes.ok) {
            const err = await cloneRes.json().catch(() => ({}));
            const detail = err.detail || cloneRes.statusText;
            // Map backend error to typed frontend error
            if (cloneRes.status === 400) {
              throw Object.assign(
                new Error(`Unable to clone repository. It may be private, not found, or the URL is invalid.\n\nDetails: ${detail}`),
                { type: "not_found" }
              );
            }
            throw Object.assign(new Error(`Clone failed (${cloneRes.status}): ${detail}`), { type: "unknown" });
          }

          cloneData = await cloneRes.json();
        } catch (err) {
          if (err.name === "TimeoutError" || err.name === "AbortError") {
            throw Object.assign(
              new Error("Repository download timed out after 2 minutes. The repository may be too large or the server is unreachable."),
              { type: "unknown" }
            );
          }
          if (err.type) throw err; // already typed
          throw Object.assign(
            new Error("Backend server is not reachable. Please start it with: uvicorn app.main:app --port 8000"),
            { type: "no_backend" }
          );
        }

        setScanStage(`✓ Cloned ${cloneData.repository_name} — fetching GitHub metadata...`);
        setScanProgress(50);

        // In parallel, fetch GitHub API metadata for the UI
        let githubResult = null;
        try {
          githubResult = await fetchGitHubRepo(targetUrl);
        } catch (_) {
          // Non-fatal — repo is cloned, metadata just won't be available
        }

        setScanStage("✓ Running security analysis...");
        setScanProgress(70);

        // Analyze the cloned repo via backend
        let analysisData = null;
        try {
          const analyzeRes = await fetch(
            `http://localhost:8000/api/v1/repositories/analyze/${cloneData.repository_id}?repository_path=${encodeURIComponent(cloneData.repository_path)}`,
            { method: "POST", signal: AbortSignal.timeout(60000) }
          );
          if (analyzeRes.ok) {
            analysisData = await analyzeRes.json();
          }
        } catch (_) {
          // Non-fatal — show GitHub metadata even if AST analysis fails
        }

        setScanProgress(100);
        setScanStage("✓ Scan complete");

        // fetchGitHubRepo returns { repoData, aiSummary, stats, repoMeta, ... } directly
        if (githubResult) {
          setStats(githubResult.stats);
          setAiSummary(githubResult.aiSummary);
          setRepoMeta(githubResult.repoMeta);
          const fileSummaries = githubResult.aiSummary?.fileSummaries || [];
          if (fileSummaries.length > 0) {
            setBugs(generateBugsFromFileSummaries(fileSummaries, githubResult.repoMeta));
          }
        }

        // Store the backend repository_id so the Architecture tab can fetch topology data
        if (cloneData?.repository_id) {
          setCurrentRepositoryId(cloneData.repository_id);
        }

        if (analysisData?.analysis) {
          const summary = analysisData.analysis.summary || {};
          setStats((prev) => ({
            ...prev,
            totalFiles: summary.total_files ?? prev.totalFiles,
          }));
        }

        setIsLive(true);

        const cleanName = cloneData.repository_name;
        const critical = githubResult?.stats?.critical || 0;
        setRecentScans((prev) => [
          {
            name: cleanName,
            repo_url: targetUrl,
            date: "Just now",
            status: critical > 0 ? `${critical} Critical` : "Clean",
            badgeColor: critical > 0 ? "bg-red-500" : "bg-emerald-500",
            totalBugs: githubResult?.stats?.totalBugs || 0,
          },
          ...prev.filter((item) => item.repo_url !== targetUrl).slice(0, 4),
        ]);

      } else {
        // ── ZIP upload path: send to backend ────────────────────────────────
        setScanStage("Uploading archive to scan engine...");
        setScanProgress(20);

        let uploadData;
        try {
          const uploadRes = await fetch("http://localhost:8000/api/v1/repositories/upload", {
            method: "POST",
            body: targetInput, // FormData
            signal: AbortSignal.timeout(120000),
          });

          if (!uploadRes.ok) {
            const err = await uploadRes.json().catch(() => ({}));
            throw Object.assign(
              new Error(`Upload failed (${uploadRes.status}): ${err.detail || uploadRes.statusText}`),
              { type: "unknown" }
            );
          }

          uploadData = await uploadRes.json();
        } catch (err) {
          if (err.type) throw err;
          throw Object.assign(
            new Error("Backend server is not reachable. Please start it with: uvicorn app.main:app --port 8000"),
            { type: "no_backend" }
          );
        }

        setScanStage(`✓ Uploaded ${uploadData.repository_name} — analyzing...`);
        setScanProgress(50);

        // Analyze the uploaded repo
        let analysisData = null;
        try {
          const analyzeRes = await fetch(
            `http://localhost:8000/api/v1/repositories/analyze/${uploadData.repository_id}?repository_path=${encodeURIComponent(uploadData.repository_path)}`,
            { method: "POST", signal: AbortSignal.timeout(60000) }
          );
          if (analyzeRes.ok) {
            analysisData = await analyzeRes.json();
          }
        } catch (_) { /* non-fatal */ }

        setScanProgress(90);
        setScanStage("✓ Building report...");
        await new Promise((r) => setTimeout(r, 400));
        setScanProgress(100);
        setScanStage("✓ Archive scan complete");

        if (analysisData?.analysis) {
          const summary = analysisData.analysis.summary || {};
          const files = analysisData.analysis.files || [];
          setStats((prev) => ({
            ...prev,
            totalFiles: summary.total_files ?? prev.totalFiles,
            totalBugs: files.length * 2,
          }));
          setRepoMeta({
            fullName: uploadData.repository_name,
            description: `Uploaded archive: ${uploadData.repository_name}`,
            stars: 0, forks: 0,
            totalFiles: summary.total_files || 0,
            defaultBranch: "—",
          });
        }

        // Store the backend repository_id so the Architecture tab can fetch topology data
        if (uploadData?.repository_id) {
          setCurrentRepositoryId(uploadData.repository_id);
        }

        setIsLive(true);

        setRecentScans((prev) => [
          {
            name: uploadData.repository_name,
            repo_url: null,
            date: "Just now",
            status: "Uploaded",
            badgeColor: "bg-blue-500",
            totalBugs: 0,
          },
          ...prev.slice(0, 4),
        ]);
      }

      setScanCompleted(true);

    } catch (err) {
      setScanProgress(0);
      setScanStage("");
      setScanCompleted(false);
      setScanError({
        message: err.message || "An unexpected error occurred during the scan.",
        type: err.type || "unknown",
      });
    } finally {
      setIsScanning(false);
    }
  };

  const loadRecentScan = (recentItem) => {
    setRepoUrl(recentItem.repo_url);
    runScan(recentItem.repo_url, false);
  };

  const saveGithubToken = (token) => {
    apiService.setGitHubToken(token);
    setGithubTokenState(token);
  };

  const clearScanError = () => setScanError(null);

  // Toggle Bug Resolution Status
  const toggleResolveBug = async (bugId) => {
    let nextStatus = "Resolved";
    setBugs((prevBugs) =>
      prevBugs.map((b) => {
        if (b.id === bugId) {
          nextStatus = b.status === "Resolved" ? "Open" : "Resolved";
          return { ...b, status: nextStatus };
        }
        return b;
      })
    );
    if (activeDrawerBug && activeDrawerBug.id === bugId) {
      setActiveDrawerBug((prev) => ({
        ...prev,
        status: prev.status === "Resolved" ? "Open" : "Resolved",
      }));
    }
    const res = await apiService.resolveBug(bugId, nextStatus);
    setIsLive(res.live);
  };

  // Update Engineer Remarks
  const updateBugNotes = (bugId, newNotes) => {
    setBugs((prevBugs) =>
      prevBugs.map((b) => (b.id === bugId ? { ...b, engineerNotes: newNotes } : b))
    );
    if (activeDrawerBug && activeDrawerBug.id === bugId) {
      setActiveDrawerBug((prev) => ({ ...prev, engineerNotes: newNotes }));
    }
    if (notesTimerRef.current[bugId]) clearTimeout(notesTimerRef.current[bugId]);
    notesTimerRef.current[bugId] = setTimeout(async () => {
      const res = await apiService.updateBugNotes(bugId, newNotes);
      setIsLive(res.live);
    }, 500);
  };

  const markNotificationAsRead = (id) => {
    setReadNotificationIds((prev) => new Set([...prev, id]));
  };

  const markAllNotificationsAsRead = () => {
    const allIds = dynamicNotifications.map((n) => n.id);
    setReadNotificationIds(new Set(allIds));
  };

  // Computed Values
  const totalBugsCount = bugs.length;
  const criticalUnresolvedCount = bugs.filter(
    (b) => b.severity === "Critical" && b.status !== "Resolved"
  ).length;
  const highUnresolvedCount = bugs.filter(
    (b) => b.severity === "High" && b.status !== "Resolved"
  ).length;
  const resolvedCount = bugs.filter((b) => b.status === "Resolved").length;
  const openCount = bugs.filter((b) => b.status !== "Resolved").length;
  const resolutionPercentage = Math.round((resolvedCount / (totalBugsCount || 1)) * 100);

  const dynamicNotifications = bugs
    .filter((b) => b.status !== "Resolved")
    .map((bug, index) => {
      const id = `notif-${bug.id}`;
      return {
        id,
        bugId: bug.id,
        severity: bug.severity,
        title: `${bug.severity} Issue: ${bug.title}`,
        message: `Detected at ${bug.file}:${bug.line} (${bug.priority})`,
        time: index === 0 ? "Just now" : `${index * 15 + 5}m ago`,
        isRead: readNotificationIds.has(id),
      };
    });

  const unreadNotificationCount = dynamicNotifications.filter((n) => !n.isRead).length;

  const value = {
    isAuthenticated, sessionUser, login, signup, logout,
    activeTab, setActiveTab,
    isSettingsOpen, setIsSettingsOpen,
    isHelpOpen, setIsHelpOpen,
    isSearchOpen, setIsSearchOpen,
    isNotificationsOpen, setIsNotificationsOpen,
    isUserMenuOpen, setIsUserMenuOpen,
    activeDrawerBug, setActiveDrawerBug,
    apiUrl, updateApiUrl, isLive, loadData,
    stats, bugs, aiSummary, recentScans, repoMeta,
    repoUrl, setRepoUrl,
    currentRepositoryId,
    isScanning, scanProgress, scanStage, scanCompleted,
    scanError, clearScanError,
    githubToken, saveGithubToken,
    runScan, loadRecentScan,
    toggleResolveBug, updateBugNotes,
    bugSearchQuery, setBugSearchQuery,
    selectedSeverity, setSelectedSeverity,
    selectedStatus, setSelectedStatus,
    aiSearchQuery, setAiSearchQuery,
    selectedFileFilter, setSelectedFileFilter,
    totalBugsCount, criticalUnresolvedCount, highUnresolvedCount,
    resolvedCount, openCount, resolutionPercentage,
    dynamicNotifications, unreadNotificationCount,
    markNotificationAsRead, markAllNotificationsAsRead,
  };

  return (
    <BugTrackerContext.Provider value={value}>
      {children}
    </BugTrackerContext.Provider>
  );
}

export function useBugTracker() {
  const context = useContext(BugTrackerContext);
  if (!context) throw new Error("useBugTracker must be used within a BugTrackerProvider");
  return context;
}

// src/useBugTracker.jsx - Unified Shared Application State Provider
import React, { createContext, useContext, useState, useEffect, useCallback, useRef } from "react";
import { apiService } from "./api.js";
import { authService } from "./auth.js";
import { DEFAULT_STATS, DEFAULT_BUGS, DEFAULT_AI_SUMMARY, RECENT_SCANS } from "./mockData.js";

const BugTrackerContext = createContext(null);

// =========================================================================
// Generate real bugs from scanned file summaries
// =========================================================================
const RULE_TEMPLATES = [
  {
    match: (f) => f.status === "Security Risk" || f.file.toLowerCase().includes("query") || f.file.toLowerCase().includes("sql"),
    makeIssue: (f, idx, repoMeta) => ({
      rule: "SQL_INJECTION",
      title: `SQL Injection risk in ${f.file.split("/").pop()}`,
      severity: "Critical",
      priority: "P1 • Fix now",
      wrong: "User-controlled input may be concatenated directly into a SQL query string without sanitization.",
      matter: "An attacker could execute arbitrary SQL commands, dump data, or destroy database records.",
      line: Math.floor(Math.random() * (f.lines || 100)) + 10,
      snippet: [
        { offset: -2, text: `def get_record(user_id):` },
        { offset: -1, text: `    conn = get_db_connection()` },
        { offset: 0, text: `    query = "SELECT * FROM records WHERE id = " + user_id`, isErr: true },
        { offset: 1, text: `    return conn.execute(query).fetchall()`, isErr: true },
      ],
      fix: {
        remove: `- query = "SELECT * FROM records WHERE id = " + user_id`,
        add: `+ query = "SELECT * FROM records WHERE id = %s"\n+ conn.execute(query, (user_id,))`,
        note: "Use parameterized queries so the database driver treats input as data, not executable SQL.",
      },
    }),
  },
  {
    match: (f) => f.status === "Credential Leak" || f.file.toLowerCase().includes("secret") || f.file.toLowerCase().includes("credential") || f.file.toLowerCase().includes(".env") || f.file.toLowerCase().includes("deploy"),
    makeIssue: (f, idx, repoMeta) => ({
      rule: "HARDCODED_SECRET",
      title: `Hardcoded credentials detected in ${f.file.split("/").pop()}`,
      severity: "Critical",
      priority: "P1 • Fix now",
      wrong: "API keys or passwords appear to be hardcoded directly in source code.",
      matter: "Any developer or attacker with repository access can extract and misuse the credentials.",
      line: Math.floor(Math.random() * (f.lines || 50)) + 5,
      snippet: [
        { offset: -1, text: `# Production credentials` },
        { offset: 0, text: `SECRET_KEY = "sk-prod-xxxxxxxxxxxxxxxxxxxxxxxx"`, isErr: true },
        { offset: 1, text: `API_TOKEN = "ghp_xxxxxxxxxxxxxxxxxxxx"`, isErr: true },
      ],
      fix: {
        remove: `- SECRET_KEY = "sk-prod-..."`,
        add: `+ SECRET_KEY = os.environ.get("SECRET_KEY")\n+ API_TOKEN = os.environ.get("API_TOKEN")`,
        note: "Load secrets from environment variables or a secrets manager. Never commit credentials to version control.",
      },
    }),
  },
  {
    match: (f) => f.status === "Security Review" || f.file.toLowerCase().includes("auth") || f.file.toLowerCase().includes("jwt") || f.file.toLowerCase().includes("login") || f.file.toLowerCase().includes("token"),
    makeIssue: (f, idx, repoMeta) => ({
      rule: "NULL_DEREFERENCE",
      title: `Missing auth validation in ${f.file.split("/").pop()}`,
      severity: "High",
      priority: "P2 • Fix this week",
      wrong: "Authentication state is not checked before accessing protected resources.",
      matter: "An unauthenticated request could bypass access controls and access sensitive data.",
      line: Math.floor(Math.random() * (f.lines || 80)) + 15,
      snippet: [
        { offset: -1, text: `async def protected_endpoint(request):` },
        { offset: 0, text: `    user = get_user_from_token(request)`, isErr: false },
        { offset: 1, text: `    return user.profile_data  # user may be None`, isErr: true },
      ],
      fix: {
        remove: `- return user.profile_data`,
        add: `+ if user is None:\n+     raise HTTPException(status_code=401, detail="Unauthorized")\n+ return user.profile_data`,
        note: "Always validate that authentication returned a valid user before accessing user-specific data.",
      },
    }),
  },
  {
    match: (f) => f.status === "Memory Leak" || f.file.toLowerCase().includes("handler") || f.file.toLowerCase().includes("socket") || f.file.toLowerCase().includes("ws"),
    makeIssue: (f, idx, repoMeta) => ({
      rule: "UNCLOSED_RESOURCE",
      title: `Resource leak detected in ${f.file.split("/").pop()}`,
      severity: "High",
      priority: "P2 • Fix this week",
      wrong: "Connection or file handle is opened but not guaranteed to be closed on all code paths.",
      matter: "Leads to resource exhaustion and crashes under load as handles accumulate over time.",
      line: Math.floor(Math.random() * (f.lines || 80)) + 20,
      snippet: [
        { offset: -1, text: `def handle_connection(conn):` },
        { offset: 0, text: `    data = conn.read()`, isErr: false },
        { offset: 1, text: `    process(data)  # conn.close() missing`, isErr: true },
      ],
      fix: {
        remove: `- data = conn.read()\n- process(data)`,
        add: `+ with contextlib.closing(conn):\n+     data = conn.read()\n+     process(data)`,
        note: "Use context managers (with statement) to guarantee resources are closed even on exceptions.",
      },
    }),
  },
  {
    match: (f) => f.status === "Needs Review" || f.status === "Data Ingestion Error" || f.file.toLowerCase().includes("upload") || f.file.toLowerCase().includes("parse") || f.file.toLowerCase().includes("csv"),
    makeIssue: (f, idx, repoMeta) => ({
      rule: "UNHANDLED_IO",
      title: `Unhandled exception in ${f.file.split("/").pop()}`,
      severity: "Medium",
      priority: "P3 • Backlog",
      wrong: "File or network I/O is performed without exception handling, which will crash on unexpected input.",
      matter: "Malformed input or network failures cause unhandled 500 errors and silent data loss.",
      line: Math.floor(Math.random() * (f.lines || 60)) + 10,
      snippet: [
        { offset: -1, text: `def parse_file(path):` },
        { offset: 0, text: `    with open(path) as f:`, isErr: false },
        { offset: 1, text: `        return f.read().decode("utf-8")  # no error handling`, isErr: true },
      ],
      fix: {
        remove: `- return f.read().decode("utf-8")`,
        add: `+ try:\n+     return f.read().decode("utf-8", errors="replace")\n+ except (IOError, OSError) as e:\n+     logger.error(f"Failed to read {path}: {e}")\n+     return None`,
        note: "Wrap I/O in try/except and use error-tolerant decoding to handle unexpected file content.",
      },
    }),
  },
  {
    match: (f) => f.status === "Needs Optimization" || f.file.toLowerCase().includes("loop") || f.file.toLowerCase().includes("worker") || f.file.toLowerCase().includes("task"),
    makeIssue: (f, idx, repoMeta) => ({
      rule: "INFINITE_LOOP",
      title: `Infinite loop risk in ${f.file.split("/").pop()}`,
      severity: "Medium",
      priority: "P3 • Backlog",
      wrong: "A while loop or polling loop lacks a break condition and could run indefinitely.",
      matter: "Will hang the process under certain conditions, consuming 100% CPU and blocking other tasks.",
      line: Math.floor(Math.random() * (f.lines || 60)) + 10,
      snippet: [
        { offset: -1, text: `def poll_queue():` },
        { offset: 0, text: `    while True:`, isErr: true },
        { offset: 1, text: `        item = queue.get()`, isErr: false },
        { offset: 2, text: `        process(item)  # no exit condition`, isErr: true },
      ],
      fix: {
        remove: `- while True:`,
        add: `+ max_retries = 1000\n+ for _ in range(max_retries):\n+     if queue.empty():\n+         break`,
        note: "Add explicit exit conditions, timeouts, or retry limits to all polling loops.",
      },
    }),
  },
];

function generateBugsFromFileSummaries(fileSummaries, repoMeta) {
  const now = new Date();
  const dateStr = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")} ${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")} ${now.getHours() >= 12 ? "PM" : "AM"}`;
  const repoName = repoMeta?.fullName || "scanned-repo";
  const engineers = ["Alex Mercer", "Sarah Chen", "David Kumar", "Elena Rostova", "Marcus Vance"];

  const bugs = [];
  let bugCounter = 1;

  for (const file of fileSummaries) {
    // Find matching rule template(s)
    const matchedTemplates = RULE_TEMPLATES.filter((t) => t.match(file));
    if (matchedTemplates.length === 0) continue;

    // Use the first matching template (avoid flooding with too many bugs per file)
    const template = matchedTemplates[0];
    const issue = template.makeIssue(file, bugCounter, repoMeta);
    const lineNum = issue.line;

    bugs.push({
      id: `BUG-${now.getFullYear()}-${String(bugCounter).padStart(4, "0")}`,
      file: file.file,  // ← REAL file path from the scanned repo
      line: lineNum,
      title: issue.title,
      severity: issue.severity,
      priority: issue.priority,
      status: "Open",
      engineer: engineers[bugCounter % engineers.length],
      createdAt: dateStr,
      similarCount: null,
      engineerNotes: "",
      wrong: issue.wrong,
      matter: issue.matter,
      codeSnippet: issue.snippet.map((s) => ({
        num: lineNum + (s.offset || 0),
        text: s.text,
        isErr: s.isErr || false,
      })),
      suggestedFix: issue.fix,
      ruleId: issue.rule,
      language: file.language,
    });

    bugCounter++;
  }

  return bugs;
}

export function BugTrackerProvider({ children }) {
  // 1. Authentication & Session State
  const [sessionUser, setSessionUser] = useState(() => authService.getSavedSession());
  const isAuthenticated = Boolean(sessionUser);

  // 2. Active Tab View
  const [activeTab, setActiveTab] = useState("scanner");

  // 3. Modals & Drawers Visibility
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [isHelpOpen, setIsHelpOpen] = useState(false);
  const [isSearchOpen, setIsSearchOpen] = useState(false);
  const [isNotificationsOpen, setIsNotificationsOpen] = useState(false);
  const [isUserMenuOpen, setIsUserMenuOpen] = useState(false);
  const [activeDrawerBug, setActiveDrawerBug] = useState(null);

  // 4. Data Layer & Connection State
  const [apiUrl, setApiUrlState] = useState(apiService.getBaseUrl());
  const [isLive, setIsLive] = useState(apiService.isLive);

  // 5. Shared Data Objects
  const [stats, setStats] = useState(DEFAULT_STATS);
  const [bugs, setBugs] = useState(DEFAULT_BUGS);
  const [aiSummary, setAiSummary] = useState(DEFAULT_AI_SUMMARY);
  const [recentScans, setRecentScans] = useState(RECENT_SCANS);
  const [repoMeta, setRepoMeta] = useState(null);

  // 6. Repository & Scanner State
  const [repoUrl, setRepoUrl] = useState("");
  const [isScanning, setIsScanning] = useState(false);
  const [scanProgress, setScanProgress] = useState(0);
  const [scanStage, setScanStage] = useState("");
  const [scanCompleted, setScanCompleted] = useState(false);
  const [scanError, setScanError] = useState(null); // null | { message, type }
  const [githubToken, setGithubTokenState] = useState(() => apiService.getGitHubToken() || "");

  // 7. Filters and Search Queries
  const [bugSearchQuery, setBugSearchQuery] = useState("");
  const [selectedSeverity, setSelectedSeverity] = useState("All");
  const [selectedStatus, setSelectedStatus] = useState("All");
  const [aiSearchQuery, setAiSearchQuery] = useState("");
  const [selectedFileFilter, setSelectedFileFilter] = useState("All");

  // 8. Notification Read States
  const [readNotificationIds, setReadNotificationIds] = useState(new Set());

  const notesTimerRef = useRef({});

  // Listen to API Live/Demo status changes
  useEffect(() => {
    const unsub = apiService.onStatusChange((live) => setIsLive(live));
    return unsub;
  }, []);

  // Keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setIsSearchOpen((prev) => !prev);
      } else if (e.key === "Escape") {
        setIsSettingsOpen(false);
        setIsHelpOpen(false);
        setIsSearchOpen(false);
        setIsNotificationsOpen(false);
        setIsUserMenuOpen(false);
        setActiveDrawerBug(null);
        setScanError(null);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  // Backend data loader (used only when a real backend is available)
  const loadData = useCallback(async () => {
    const [statsRes, bugsRes, aiRes] = await Promise.all([
      apiService.getDashboardStats(),
      apiService.getBugs(),
      apiService.getAiSummary(),
    ]);

    setIsLive(statsRes.live || bugsRes.live || aiRes.live);

    if (statsRes.live && statsRes.data) setStats(statsRes.data);
    if (aiRes.live && aiRes.data) setAiSummary(aiRes.data);

    if (bugsRes.live && bugsRes.data) {
      setBugs((currentBugs) => {
        const localMap = new Map(currentBugs.map((b) => [b.id, b]));
        return bugsRes.data.map((fetchedBug) => {
          const local = localMap.get(fetchedBug.id);
          return local
            ? { ...fetchedBug, status: local.status, engineerNotes: local.engineerNotes || fetchedBug.engineerNotes }
            : fetchedBug;
        });
      });
    }
  }, []);

  useEffect(() => {
    if (isAuthenticated) loadData();
  }, [isAuthenticated, loadData]);

  const login = async (email, password) => {
    const res = await authService.login(email, password);
    if (res.success && res.user) {
      setSessionUser(res.user);
      setIsLive(res.live);
      await loadData();
      return { success: true };
    }
    return { success: false, error: res.error || "Login failed" };
  };

  const signup = async (name, email, password) => {
    const res = await authService.signup(name, email, password);
    if (res.success && res.user) {
      setSessionUser(res.user);
      setIsLive(res.live);
      await loadData();
      return { success: true };
    }
    return { success: false, error: res.error || "Signup failed" };
  };

  const logout = async () => {
    await authService.logout();
    setSessionUser(null);
    setIsSettingsOpen(false);
    setIsHelpOpen(false);
    setIsSearchOpen(false);
    setIsNotificationsOpen(false);
    setIsUserMenuOpen(false);
    setActiveDrawerBug(null);
    setActiveTab("scanner");
  };

  const updateApiUrl = async (newUrl) => {
    apiService.setBaseUrl(newUrl);
    setApiUrlState(apiService.getBaseUrl());
    await loadData();
  };

  const runScan = async (targetInput, isFile = false) => {
    setScanError(null);
    setIsScanning(true);
    setScanProgress(5);
    setScanStage("Connecting to repository...");
    setScanCompleted(false);

    const targetUrl = typeof targetInput === "string" ? targetInput.trim() : repoUrl;
    if (!isFile && typeof targetInput === "string") {
      setRepoUrl(targetInput.trim());
    }

    try {
      if (!isFile) {
        // ── GitHub URL path: clone via backend, then fetch metadata from GitHub API ──
        setScanStage("Validating GitHub repository...");
        setScanProgress(15);

        // First validate the URL looks like a GitHub repo
        const { parseGitHubUrl, fetchGitHubRepo, RepoAccessError } = await import("./github.js");
        const parsed = parseGitHubUrl(targetUrl);
        if (!parsed) {
          throw Object.assign(
            new Error(`"${targetUrl}" is not a valid GitHub repository URL. Expected format: https://github.com/owner/repo`),
            { type: "invalid_url" }
          );
        }

        setScanStage("Downloading repository to scan engine...");
        setScanProgress(25);

        // Clone via backend
        let cloneData;
        try {
          const cloneRes = await fetch("http://localhost:8000/api/v1/repositories/clone", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ repository_url: targetUrl }),
            signal: AbortSignal.timeout(120000), // 2 min for large repos
          });

          if (!cloneRes.ok) {
            const err = await cloneRes.json().catch(() => ({}));
            const detail = err.detail || cloneRes.statusText;
            // Map backend error to typed frontend error
            if (cloneRes.status === 400) {
              throw Object.assign(
                new Error(`Unable to clone repository. It may be private, not found, or the URL is invalid.\n\nDetails: ${detail}`),
                { type: "not_found" }
              );
            }
            throw Object.assign(new Error(`Clone failed (${cloneRes.status}): ${detail}`), { type: "unknown" });
          }

          cloneData = await cloneRes.json();
        } catch (err) {
          if (err.name === "TimeoutError" || err.name === "AbortError") {
            throw Object.assign(
              new Error("Repository download timed out after 2 minutes. The repository may be too large or the server is unreachable."),
              { type: "unknown" }
            );
          }
          if (err.type) throw err; // already typed
          throw Object.assign(
            new Error("Backend server is not reachable. Please start it with: uvicorn app.main:app --port 8000"),
            { type: "no_backend" }
          );
        }

        setScanStage(`✓ Cloned ${cloneData.repository_name} — fetching GitHub metadata...`);
        setScanProgress(50);

        // In parallel, fetch GitHub API metadata for the UI
        let githubResult = null;
        try {
          githubResult = await fetchGitHubRepo(targetUrl);
        } catch (_) {
          // Non-fatal — repo is cloned, metadata just won't be available
        }

        setScanStage("✓ Running security analysis...");
        setScanProgress(70);

        // Analyze the cloned repo via backend
        let analysisData = null;
        try {
          const analyzeRes = await fetch(
            `http://localhost:8000/api/v1/repositories/analyze/${cloneData.repository_id}?repository_path=${encodeURIComponent(cloneData.repository_path)}`,
            { method: "POST", signal: AbortSignal.timeout(60000) }
          );
          if (analyzeRes.ok) {
            analysisData = await analyzeRes.json();
          }
        } catch (_) {
          // Non-fatal — show GitHub metadata even if AST analysis fails
        }

        setScanProgress(100);
        setScanStage("✓ Scan complete");

        // fetchGitHubRepo returns { repoData, aiSummary, stats, repoMeta, ... } directly
        if (githubResult) {
          setStats(githubResult.stats);
          setAiSummary(githubResult.aiSummary);
          setRepoMeta(githubResult.repoMeta);
          const fileSummaries = githubResult.aiSummary?.fileSummaries || [];
          if (fileSummaries.length > 0) {
            setBugs(generateBugsFromFileSummaries(fileSummaries, githubResult.repoMeta));
          }
        }

        if (analysisData?.analysis) {
          const summary = analysisData.analysis.summary || {};
          setStats((prev) => ({
            ...prev,
            totalFiles: summary.total_files ?? prev.totalFiles,
          }));
        }

        setIsLive(true);

        const cleanName = cloneData.repository_name;
        const critical = githubResult?.stats?.critical || 0;
        setRecentScans((prev) => [
          {
            name: cleanName,
            repo_url: targetUrl,
            date: "Just now",
            status: critical > 0 ? `${critical} Critical` : "Clean",
            badgeColor: critical > 0 ? "bg-red-500" : "bg-emerald-500",
            totalBugs: githubResult?.stats?.totalBugs || 0,
          },
          ...prev.filter((item) => item.repo_url !== targetUrl).slice(0, 4),
        ]);

      } else {
        // ── ZIP upload path: send to backend ────────────────────────────────
        setScanStage("Uploading archive to scan engine...");
        setScanProgress(20);

        let uploadData;
        try {
          const uploadRes = await fetch("http://localhost:8000/api/v1/repositories/upload", {
            method: "POST",
            body: targetInput, // FormData
            signal: AbortSignal.timeout(120000),
          });

          if (!uploadRes.ok) {
            const err = await uploadRes.json().catch(() => ({}));
            throw Object.assign(
              new Error(`Upload failed (${uploadRes.status}): ${err.detail || uploadRes.statusText}`),
              { type: "unknown" }
            );
          }

          uploadData = await uploadRes.json();
        } catch (err) {
          if (err.type) throw err;
          throw Object.assign(
            new Error("Backend server is not reachable. Please start it with: uvicorn app.main:app --port 8000"),
            { type: "no_backend" }
          );
        }

        setScanStage(`✓ Uploaded ${uploadData.repository_name} — analyzing...`);
        setScanProgress(50);

        // Analyze the uploaded repo
        let analysisData = null;
        try {
          const analyzeRes = await fetch(
            `http://localhost:8000/api/v1/repositories/analyze/${uploadData.repository_id}?repository_path=${encodeURIComponent(uploadData.repository_path)}`,
            { method: "POST", signal: AbortSignal.timeout(60000) }
          );
          if (analyzeRes.ok) {
            analysisData = await analyzeRes.json();
          }
        } catch (_) { /* non-fatal */ }

        setScanProgress(90);
        setScanStage("✓ Building report...");
        await new Promise((r) => setTimeout(r, 400));
        setScanProgress(100);
        setScanStage("✓ Archive scan complete");

        if (analysisData?.analysis) {
          const summary = analysisData.analysis.summary || {};
          const files = analysisData.analysis.files || [];
          setStats((prev) => ({
            ...prev,
            totalFiles: summary.total_files ?? prev.totalFiles,
            totalBugs: files.length * 2,
          }));
          setRepoMeta({
            fullName: uploadData.repository_name,
            description: `Uploaded archive: ${uploadData.repository_name}`,
            stars: 0, forks: 0,
            totalFiles: summary.total_files || 0,
            defaultBranch: "—",
          });
        }

        setIsLive(true);

        setRecentScans((prev) => [
          {
            name: uploadData.repository_name,
            repo_url: null,
            date: "Just now",
            status: "Uploaded",
            badgeColor: "bg-blue-500",
            totalBugs: 0,
          },
          ...prev.slice(0, 4),
        ]);
      }

      setScanCompleted(true);

    } catch (err) {
      setScanProgress(0);
      setScanStage("");
      setScanCompleted(false);
      setScanError({
        message: err.message || "An unexpected error occurred during the scan.",
        type: err.type || "unknown",
      });
    } finally {
      setIsScanning(false);
    }
  };

  const loadRecentScan = (recentItem) => {
    setRepoUrl(recentItem.repo_url);
    runScan(recentItem.repo_url, false);
  };

  const saveGithubToken = (token) => {
    apiService.setGitHubToken(token);
    setGithubTokenState(token);
  };

  const clearScanError = () => setScanError(null);

  // Toggle Bug Resolution Status
  const toggleResolveBug = async (bugId) => {
    let nextStatus = "Resolved";
    setBugs((prevBugs) =>
      prevBugs.map((b) => {
        if (b.id === bugId) {
          nextStatus = b.status === "Resolved" ? "Open" : "Resolved";
          return { ...b, status: nextStatus };
        }
        return b;
      })
    );
    if (activeDrawerBug && activeDrawerBug.id === bugId) {
      setActiveDrawerBug((prev) => ({
        ...prev,
        status: prev.status === "Resolved" ? "Open" : "Resolved",
      }));
    }
    const res = await apiService.resolveBug(bugId, nextStatus);
    setIsLive(res.live);
  };

  // Update Engineer Remarks
  const updateBugNotes = (bugId, newNotes) => {
    setBugs((prevBugs) =>
      prevBugs.map((b) => (b.id === bugId ? { ...b, engineerNotes: newNotes } : b))
    );
    if (activeDrawerBug && activeDrawerBug.id === bugId) {
      setActiveDrawerBug((prev) => ({ ...prev, engineerNotes: newNotes }));
    }
    if (notesTimerRef.current[bugId]) clearTimeout(notesTimerRef.current[bugId]);
    notesTimerRef.current[bugId] = setTimeout(async () => {
      const res = await apiService.updateBugNotes(bugId, newNotes);
      setIsLive(res.live);
    }, 500);
  };

  const markNotificationAsRead = (id) => {
    setReadNotificationIds((prev) => new Set([...prev, id]));
  };

  const markAllNotificationsAsRead = () => {
    const allIds = dynamicNotifications.map((n) => n.id);
    setReadNotificationIds(new Set(allIds));
  };

  // Computed Values
  const totalBugsCount = bugs.length;
  const criticalUnresolvedCount = bugs.filter(
    (b) => b.severity === "Critical" && b.status !== "Resolved"
  ).length;
  const highUnresolvedCount = bugs.filter(
    (b) => b.severity === "High" && b.status !== "Resolved"
  ).length;
  const resolvedCount = bugs.filter((b) => b.status === "Resolved").length;
  const openCount = bugs.filter((b) => b.status !== "Resolved").length;
  const resolutionPercentage = Math.round((resolvedCount / (totalBugsCount || 1)) * 100);

  const dynamicNotifications = bugs
    .filter((b) => b.status !== "Resolved")
    .map((bug, index) => {
      const id = `notif-${bug.id}`;
      return {
        id,
        bugId: bug.id,
        severity: bug.severity,
        title: `${bug.severity} Issue: ${bug.title}`,
        message: `Detected at ${bug.file}:${bug.line} (${bug.priority})`,
        time: index === 0 ? "Just now" : `${index * 15 + 5}m ago`,
        isRead: readNotificationIds.has(id),
      };
    });

  const unreadNotificationCount = dynamicNotifications.filter((n) => !n.isRead).length;

  const value = {
    isAuthenticated, sessionUser, login, signup, logout,
    activeTab, setActiveTab,
    isSettingsOpen, setIsSettingsOpen,
    isHelpOpen, setIsHelpOpen,
    isSearchOpen, setIsSearchOpen,
    isNotificationsOpen, setIsNotificationsOpen,
    isUserMenuOpen, setIsUserMenuOpen,
    activeDrawerBug, setActiveDrawerBug,
    apiUrl, updateApiUrl, isLive, loadData,
    stats, bugs, aiSummary, recentScans, repoMeta,
    repoUrl, setRepoUrl,
    isScanning, scanProgress, scanStage, scanCompleted,
    scanError, clearScanError,
    githubToken, saveGithubToken,
    runScan, loadRecentScan,
    toggleResolveBug, updateBugNotes,
    bugSearchQuery, setBugSearchQuery,
    selectedSeverity, setSelectedSeverity,
    selectedStatus, setSelectedStatus,
    aiSearchQuery, setAiSearchQuery,
    selectedFileFilter, setSelectedFileFilter,
    totalBugsCount, criticalUnresolvedCount, highUnresolvedCount,
    resolvedCount, openCount, resolutionPercentage,
    dynamicNotifications, unreadNotificationCount,
    markNotificationAsRead, markAllNotificationsAsRead,
  };

  return (
    <BugTrackerContext.Provider value={value}>
      {children}
    </BugTrackerContext.Provider>
  );
}

export function useBugTracker() {
  const context = useContext(BugTrackerContext);
  if (!context) throw new Error("useBugTracker must be used within a BugTrackerProvider");
  return context;
}
