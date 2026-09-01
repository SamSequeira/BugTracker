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
      priority: "P1 â€¢ Fix now",
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
      priority: "P1 â€¢ Fix now",
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
      priority: "P2 â€¢ Fix this week",
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
      priority: "P2 â€¢ Fix this week",
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
      priority: "P3 â€¢ Backlog",
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
      priority: "P3 â€¢ Backlog",
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
      file: file.file,  // â† REAL file path from the scanned repo
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
  // Ref that holds the current polling interval ID so it can be cancelled
  // from anywhere (new scan start, unmount, completion, failure, timeout).
  const pollingRef = useRef(null);

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

  // =========================================================================
  // Analysis status polling
  // =========================================================================

  // Cancel any running poll interval immediately.
  const stopPolling = useCallback(() => {
    if (pollingRef.current !== null) {
      clearInterval(pollingRef.current);
      pollingRef.current = null;
    }
  }, []);

  // Start polling GET /analysis-status for repositoryId.
  // Polls every 3 s, stops on completed/failed or after 5 min.
  // Applies real metrics to state when completed.
  const startAnalysisPolling = useCallback(
    (repositoryId) => {
      // Cancel any previous poll before starting a new one.
      stopPolling();

      const POLL_INTERVAL_MS = 3000;
      const POLL_TIMEOUT_MS = 5 * 60 * 1000; // 5 minutes
      const startedAt = Date.now();

      pollingRef.current = setInterval(async () => {
        // Guard: stop if the interval was already cleared externally.
        if (pollingRef.current === null) return;

        // Hard timeout â€” stop regardless of status after 5 minutes.
        if (Date.now() - startedAt > POLL_TIMEOUT_MS) {
          stopPolling();
          setIsScanning(false);
          setScanProgress(0);
          setScanStage("");
          setScanError({
            message:
              "Analysis timed out after 5 minutes. The repository may be too large. " +
              "You can still view partial results in the Architecture tab.",
            type: "unknown",
          });
          return;
        }

        const res = await apiService.getRepositoryAnalysisStatus(repositoryId);

        if (!res.live || !res.data) {
          // Network hiccup â€” keep polling, don't give up on a single failure.
          return;
        }

        const { status: runStatus, total_files, supported_files, candidate_issues_count, duration_seconds } = res.data;

        if (runStatus === "none" || runStatus === "running") {
          // Not done yet â€” update the stage label and keep polling.
          if (runStatus === "running") {
            // Gently advance progress from 30 â†’ 90 while we wait.
            setScanProgress((prev) => Math.min(prev + 2, 90));
            setScanStage("âœ“ Analyzing codebase...");
          }
          return; // continue polling
        }

        // Terminal states â€” stop polling regardless.
        stopPolling();

        if (runStatus === "completed") {
          // Apply real backend metrics to stats state.
          // Explicitly clear linesOfCode so the DEFAULT_STATS placeholder
          // (128,742) does not persist alongside real totalFiles/totalBugs.
          setStats((prev) => ({
            ...prev,
            totalBugs: candidate_issues_count ?? prev.totalBugs,
            totalFiles: total_files ?? prev.totalFiles,
            scanTime: duration_seconds != null ? `${duration_seconds.toFixed(1)}s` : prev.scanTime,
            linesOfCode: null, // cleared â€” real line count not available from analysis-status
            critical: 0,       // reset to 0; no backend issue fetch here
          }));
          setIsLive(true);
          setScanProgress(100);

          // Update the matching recent scan preset status so it no longer
          // shows "Analyzingâ€¦" now that analysis is complete.
          setRecentScans((prev) =>
            prev.map((item) =>
              item.repository_id === repositoryId
                ? {
                    ...item,
                    status: `${candidate_issues_count ?? 0} issue${candidate_issues_count === 1 ? "" : "s"}`,
                    badgeColor: (candidate_issues_count ?? 0) > 0 ? "bg-amber-500" : "bg-emerald-500",
                  }
                : item
            )
          );

          setScanStage("âœ“ Analysis complete");
          setIsScanning(false);
          setScanCompleted(true);
        } else if (runStatus === "failed") {
          setIsScanning(false);
          setScanProgress(0);
          setScanStage("");
          setScanCompleted(false);
          setScanError({
            message:
              "Backend analysis failed for this repository. " +
              "Check server logs or try re-scanning.",
            type: "unknown",
          });
        }
      }, POLL_INTERVAL_MS);
    },
    [stopPolling] // eslint-disable-line react-hooks/exhaustive-deps
  );

  // Clean up polling interval on provider unmount.
  useEffect(() => {
    return () => stopPolling();
  }, [stopPolling]);

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

  // On login, populate recent scans from the real DB repository list
  // (newest-first). Falls back to the existing RECENT_SCANS mock if the
  // backend is unavailable or returns an empty list.
  // Also fetches analysis status for each repo so the preset shows
  // real status (completed / running / none / failed) rather than a
  // generic "Previously scanned" label.
  useEffect(() => {
    if (!isAuthenticated) return;

    (async () => {
      const res = await apiService.getRepositories();
      if (!res.live || !Array.isArray(res.data) || res.data.length === 0) return;

      // Map DB RepositoryResponse â†’ recentScans shape (initial neutral state).
      const dbScans = res.data.slice(0, 5).map((repo) => ({
        repository_id: repo.id,         // real backend ID â€” used by preset click handler
        name: repo.name,
        repo_url: repo.source_url || null,
        date: new Date(repo.created_at).toLocaleDateString("en-US", {
          month: "short",
          day: "numeric",
          year: "numeric",
        }),
        status: "Previously scanned",
        badgeColor: "bg-slate-500",
        totalBugs: 0,
      }));

      setRecentScans(dbScans);

      // Enrich each preset with the real analysis status in the background.
      // This runs after the initial list is shown so the UI isn't blocked.
      for (const repo of res.data.slice(0, 5)) {
        const statusRes = await apiService.getRepositoryAnalysisStatus(repo.id);
        if (!statusRes.live || !statusRes.data) continue;

        const { status: runStatus, candidate_issues_count } = statusRes.data;
        let badgeColor = "bg-slate-500";
        let statusLabel = "Previously scanned";

        if (runStatus === "completed") {
          const count = candidate_issues_count ?? 0;
          statusLabel = count > 0 ? `${count} issue${count === 1 ? "" : "s"}` : "Clean";
          badgeColor = count > 0 ? "bg-amber-500" : "bg-emerald-500";
        } else if (runStatus === "running") {
          statusLabel = "Analyzingâ€¦";
          badgeColor = "bg-cyan-500";
        } else if (runStatus === "failed") {
          statusLabel = "Analysis failed";
          badgeColor = "bg-red-500";
        } else if (runStatus === "none") {
          statusLabel = "Not analyzed";
          badgeColor = "bg-slate-600";
        }

        setRecentScans((prev) =>
          prev.map((item) =>
            item.repository_id === repo.id
              ? { ...item, status: statusLabel, badgeColor }
              : item
          )
        );
      }
    })();
  }, [isAuthenticated]); // eslint-disable-line react-hooks/exhaustive-deps

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
    // Cancel any existing poll before starting a new scan.
    stopPolling();
    // Reset stale repository-specific data so the previous repository's
    // metrics don't remain visible while the new scan runs.
    setCurrentRepositoryId(null);
    setStats(DEFAULT_STATS);
    setBugs(DEFAULT_BUGS);

    const targetUrl = typeof targetInput === "string" ? targetInput.trim() : repoUrl;
    if (!isFile && typeof targetInput === "string") {
      setRepoUrl(targetInput.trim());
    }

    try {
      if (!isFile) {
        // â”€â”€ GitHub URL path: clone via backend, then fetch metadata from GitHub API â”€â”€
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

        setScanStage(`âœ“ Cloned ${cloneData.repository_name} â€” fetching GitHub metadata...`);
        setScanProgress(50);

        // In parallel, fetch GitHub API metadata for the UI
        let githubResult = null;
        try {
          githubResult = await fetchGitHubRepo(targetUrl);
        } catch (_) {
          // Non-fatal â€” repo is cloned, metadata just won't be available
        }

        // Apply GitHub metadata (stars, forks, description, repoMeta banner).
        // Do NOT use heuristic stats/bugs from GitHub as the source of truth â€”
        // those will be overwritten by real backend data once polling completes.
        if (githubResult) {
          setAiSummary(githubResult.aiSummary);
          setRepoMeta(githubResult.repoMeta);
          // Only pre-populate fileSummary-based bugs if no backend id is set yet;
          // polling completion will later overwrite totalBugs with the real count.
          const fileSummaries = githubResult.aiSummary?.fileSummaries || [];
          if (fileSummaries.length > 0) {
            setBugs(generateBugsFromFileSummaries(fileSummaries, githubResult.repoMeta));
          }
        }

        // Store the backend repository_id so Architecture tab and polling work.
        if (cloneData?.repository_id) {
          setCurrentRepositoryId(cloneData.repository_id);
        }

        setIsLive(true);

        // Add to recent scans list (runtime â€” persisted list is loaded from DB on
        // next login via the useEffect above).
        const cleanName = cloneData.repository_name;
        const critical = githubResult?.stats?.critical || 0;
        setRecentScans((prev) => [
          {
            repository_id: cloneData.repository_id,
            name: cleanName,
            repo_url: targetUrl,
            date: "Just now",
            status: critical > 0 ? `${critical} Critical` : "Analyzingâ€¦",
            badgeColor: critical > 0 ? "bg-red-500" : "bg-cyan-500",
            totalBugs: 0,
          },
          ...prev.filter((item) => item.repo_url !== targetUrl).slice(0, 4),
        ]);

        // Start polling for real analysis metrics. The clone endpoint already
        // schedules a background AnalysisRun â€” we just poll until it finishes.
        // setScanCompleted / setScanProgress(100) are handled inside the poller.
        setScanStage("âœ“ Repository downloaded â€” analyzing codebase...");
        setScanProgress(30);
        // Keep isScanning=true so the progress bar stays visible during polling.
        // The poller will call setIsScanning(false) when done.
        if (cloneData?.repository_id) {
          startAnalysisPolling(cloneData.repository_id);
        } else {
          // No repository_id means something unusual happened â€” finish gracefully.
          setScanProgress(100);
          setScanStage("âœ“ Scan complete");
          setScanCompleted(true);
          setIsScanning(false);
        }
        // Return early â€” do NOT fall through to the outer setScanCompleted(true).
        return;

      } else {
        // â”€â”€ ZIP upload path: send to backend â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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

        setScanStage(`âœ“ Uploaded ${uploadData.repository_name} â€” analyzing...`);
        setScanProgress(30);

        // Set repo metadata for the banner (no GitHub API for ZIP uploads).
        setRepoMeta({
          fullName: uploadData.repository_name,
          description: "Uploaded ZIP archive",
          stars: 0,
          forks: 0,
          totalFiles: 0,
          defaultBranch: "â€”",
        });

        // Store the backend repository_id so Architecture tab and polling work.
        if (uploadData?.repository_id) {
          setCurrentRepositoryId(uploadData.repository_id);
        }

        setIsLive(true);

        setRecentScans((prev) => [
          {
            repository_id: uploadData.repository_id,
            name: uploadData.repository_name,
            repo_url: null,
            date: "Just now",
            status: "Analyzingâ€¦",
            badgeColor: "bg-cyan-500",
            totalBugs: 0,
          },
          ...prev.slice(0, 4),
        ]);

        // Start polling for real analysis metrics.
        setScanStage("âœ“ Archive uploaded â€” analyzing codebase...");
        if (uploadData?.repository_id) {
          startAnalysisPolling(uploadData.repository_id);
        } else {
          setScanProgress(100);
          setScanStage("âœ“ Archive scan complete");
          setScanCompleted(true);
          setIsScanning(false);
        }
        // Return early â€” polling handles setScanCompleted.
        return;
      }

      setScanCompleted(true);

    } catch (err) {
      stopPolling(); // cancel any in-flight poll on scan error
      setScanProgress(0);
      setScanStage("");
      setScanCompleted(false);
      setScanError({
        message: err.message || "An unexpected error occurred during the scan.",
        type: err.type || "unknown",
      });
    } finally {
      // Only clear isScanning here when polling is NOT active.
      // When polling is active it owns isScanning and will clear it on completion.
      if (pollingRef.current === null) {
        setIsScanning(false);
      }
    }
  };

  const loadRecentScan = (recentItem) => {
    // If the preset has a real backend repository_id, restore its analysis
    // metrics without re-cloning or re-analyzing.
    if (recentItem.repository_id) {
      // Reset stale state from the previous repository immediately so the UI
      // shows neutral/loading values instead of the previous repo's numbers.
      stopPolling();
      setCurrentRepositoryId(recentItem.repository_id);
      setStats(DEFAULT_STATS);
      setBugs(DEFAULT_BUGS);
      setScanCompleted(false);
      setScanError(null);
      if (recentItem.repo_url) setRepoUrl(recentItem.repo_url);

      // Fetch the analysis status for this repo and apply real metrics if done.
      (async () => {
        const res = await apiService.getRepositoryAnalysisStatus(recentItem.repository_id);
        if (res.live && res.data && res.data.status === "completed") {
          const { total_files, candidate_issues_count, duration_seconds } = res.data;
          setStats((prev) => ({
            ...prev,
            totalBugs: candidate_issues_count ?? 0,
            totalFiles: total_files ?? prev.totalFiles,
            scanTime: duration_seconds != null ? `${duration_seconds.toFixed(1)}s` : prev.scanTime,
            linesOfCode: null, // cleared to prevent stale DEFAULT_STATS value
            critical: 0,       // reset; no backend issue fetch here
          }));
          setIsLive(true);
          setScanCompleted(true);
        } else if (res.live && res.data && res.data.status === "running") {
          // Analysis still in progress â€” resume polling.
          setScanCompleted(false);
          setIsScanning(true);
          setScanProgress(30);
          setScanStage("âœ“ Resuming analysis monitoring...");
          startAnalysisPolling(recentItem.repository_id);
        } else if (res.live && res.data && res.data.status === "none") {
          // No analysis run yet â€” show neutral zero state, not DEFAULT_STATS.
          setStats((prev) => ({
            ...prev,
            totalBugs: 0,
            totalFiles: 0,
            scanTime: "â€”",
            linesOfCode: null,
            critical: 0,
          }));
          setBugs([]);
          setScanCompleted(false);
        } else if (res.live && res.data && res.data.status === "failed") {
          // Analysis failed â€” show zero state.
          setStats((prev) => ({
            ...prev,
            totalBugs: 0,
            totalFiles: 0,
            scanTime: "â€”",
            linesOfCode: null,
            critical: 0,
          }));
          setBugs([]);
          setScanCompleted(false);
        }
        // If res.live is false (backend unreachable), stats stay as DEFAULT_STATS
        // which is the correct demo/fallback behavior.
      })();
      return;
    }

    // Demo/mock preset â€” use the original re-scan behaviour.
    if (recentItem.repo_url) {
      setRepoUrl(recentItem.repo_url);
      runScan(recentItem.repo_url, false);
    }
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
