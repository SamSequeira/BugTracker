// src/useBugTracker.jsx - Unified Shared Application State Provider
import React, { createContext, useContext, useState, useEffect, useCallback, useRef } from "react";
import { apiService } from "./api.js";
import { authService } from "./auth.js";
import { DEFAULT_STATS, DEFAULT_AI_SUMMARY, RECENT_SCANS } from "./mockData.js";
import { parseGitHubUrl, fetchGitHubRepo } from "./github.js";

const BugTrackerContext = createContext(null);

// // =========================================================================
// Convert real PostgreSQL CandidateIssue to UI Bug Object
// =========================================================================
function mapBackendCandidateIssueToUiBug(issue, index = 0) {
  const lineNum = issue.line_number || 1;
  const rawSev = (issue.severity || "medium").toLowerCase();
  const normalizedSev =
    rawSev === "critical" ? "Critical" :
    rawSev === "high" ? "High" :
    rawSev === "low" ? "Low" : "Medium";

  const rawPrio = (issue.urgency || issue.verified_priority || "p2").toLowerCase();
  const priorityLabel =
    rawPrio === "high" || rawPrio === "p1"
      ? "P1 • Fix now"
      : rawPrio === "low" || rawPrio === "p3" || rawPrio === "p4"
      ? "P3 • Backlog"
      : "P2 • Fix this week";

  const rawStatus = (issue.status || "open").toLowerCase();
  const normalizedStatus =
    rawStatus === "resolved" ? "Resolved" :
    rawStatus === "in progress" ? "In Progress" : "Open";

  // Parse code snippet from PostgreSQL candidate_issues.code_snippet
  const rawSnippet = issue.code_snippet || issue.codeSnippet || "";
  let codeSnippet = [];
  if (rawSnippet && typeof rawSnippet === "string" && rawSnippet.trim()) {
    codeSnippet = rawSnippet.split("\n").map((text, offset) => ({
      num: lineNum + offset,
      text,
      isErr: offset === 0,
    }));
  } else if (Array.isArray(issue.codeSnippet) && issue.codeSnippet.length > 0) {
    codeSnippet = issue.codeSnippet;
  } else {
    codeSnippet = [{ num: lineNum, text: issue.title || issue.message || "Issue detected", isErr: true }];
  }

  const engineers = ["Alex Mercer", "Sarah Chen", "David Kumar", "Elena Rostova", "Marcus Vance"];

  return {
    id: issue.id,
    file: issue.file_path || "unknown_file",   // ← critical: must match fileItem.file
    line: lineNum,
    title: issue.title || issue.message || `Issue in ${issue.file_path}`,
    severity: normalizedSev,
    priority: priorityLabel,
    status: normalizedStatus,
    engineer: engineers[index % engineers.length],
    createdAt: issue.created_at ? new Date(issue.created_at).toLocaleString() : "Recently detected",
    similarCount: null,
    engineerNotes: issue.engineer_notes || "",
    wrong: issue.description || issue.message || "",
    matter: issue.security_impact || issue.description || "Could lead to exploitation or data integrity failure.",
    codeSnippet,
    suggestedFix: issue.suggested_fix || null,
    ruleId: issue.rule_id || "",
    language: issue.language || "Unknown",
  };
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

  // 5. Shared Data Objects - initialized empty, populated strictly from DB/API
  const [stats, setStats] = useState(DEFAULT_STATS);
  const [bugs, setBugs] = useState([]);
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

  const stopPolling = useCallback(() => {
    if (pollingRef.current !== null) {
      clearInterval(pollingRef.current);
      pollingRef.current = null;
    }
  }, []);

  const startAnalysisPolling = useCallback(
    (repositoryId) => {
      stopPolling();

      const POLL_INTERVAL_MS = 2500;
      const POLL_TIMEOUT_MS = 5 * 60 * 1000;
      const startedAt = Date.now();

      pollingRef.current = setInterval(async () => {
        if (pollingRef.current === null) return;

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
          return;
        }

        const { status: runStatus, total_files, supported_files, candidate_issues_count, high_open_issues, duration_seconds } = res.data;

        if (runStatus === "none" || runStatus === "running") {
          if (runStatus === "running") {
            // Gently advance progress from 30 â†’ 90 while we wait.
            setScanProgress((prev) => Math.min(prev + 2, 90));
            setScanStage("✓ Analyzing codebase...");
          }
          return;
        }

        // Terminal states — stop polling regardless.
        stopPolling();

        if (runStatus === "completed") {
          setIsLive(true);
          setScanProgress(100);

          // Retrieve live candidate issues from PostgreSQL
          const bugsRes = await apiService.getBugs({ repository_id: repositoryId });
          let realBugs = [];
          if (bugsRes.live && Array.isArray(bugsRes.data)) {
            realBugs = bugsRes.data.map((b, idx) => mapBackendCandidateIssueToUiBug(b, idx));
            setBugs(realBugs);
          }

          setStats((prev) => ({
            ...prev,
            totalBugs: candidate_issues_count ?? realBugs.length,
            totalFiles: total_files ?? prev.totalFiles,
            scanTime: duration_seconds != null ? `${duration_seconds.toFixed(1)}s` : prev.scanTime,
            linesOfCode: null, // cleared — real line count not available from analysis-status
            critical: 0,       // reset to 0; no backend issue fetch here
            openHigh: high_open_issues ?? 0,
          }));
          setIsLive(true);
          setScanProgress(100);

          // Fetch real candidate issues for this repository and populate bugs state
          // so TabAiArchitecture can match file cards against real issue file paths.
          apiService.getBugs({ repository_id: repositoryId }).then((bugsRes) => {
            if (bugsRes.live && Array.isArray(bugsRes.data)) {
              setBugs(bugsRes.data.map((issue, idx) => mapBackendCandidateIssueToUiBug(issue, idx)));
            } else {
              setBugs([]);
            }
          });

          // Update the matching recent scan preset status so it no longer
          // shows "Analyzing…" now that analysis is complete.
          setRecentScans((prev) =>
            prev.map((item) =>
              item.repository_id === repositoryId
                ? {
                    ...item,
                    status: `${candidate_issues_count ?? realBugs.length} issue${(candidate_issues_count ?? realBugs.length) === 1 ? "" : "s"}`,
                    badgeColor: (candidate_issues_count ?? realBugs.length) > 0 ? "bg-amber-500" : "bg-emerald-500",
                  }
                : item
            )
          );

          setScanStage("✓ Analysis complete");
          setIsScanning(false);
          setScanCompleted(true);
        } else if (runStatus === "failed") {
          setIsScanning(false);
          setScanProgress(0);
          setScanStage("");
          setScanCompleted(false);
          setScanError({
            message:
              "Backend analysis failed for this repository. Check server logs or try re-scanning.",
            type: "unknown",
          });
        }
      }, POLL_INTERVAL_MS);
    },
    [stopPolling]
  );

  useEffect(() => {
    return () => stopPolling();
  }, [stopPolling]);

  // Backend data loader
  const loadData = useCallback(async () => {
    const [reposRes, bugsRes] = await Promise.all([
      apiService.getRepositories(),
      apiService.getBugs(),
    ]);

    setIsLive(reposRes.live || bugsRes.live);

    if (bugsRes.live && Array.isArray(bugsRes.data)) {
      const mapped = bugsRes.data.map((b, idx) => mapBackendCandidateIssueToUiBug(b, idx));
      setBugs(mapped);
      setStats((prev) => ({
        ...prev,
        totalBugs: mapped.length,
        high: mapped.filter((b) => b.severity === "High").length,
        medium: mapped.filter((b) => b.severity === "Medium").length,
        low: mapped.filter((b) => b.severity === "Low").length,
      }));
    }
  }, []);

  useEffect(() => {
    if (isAuthenticated) loadData();
  }, [isAuthenticated, loadData]);

  // On login, populate recent scans and default repository
  useEffect(() => {
    if (!isAuthenticated) return;

    (async () => {
      const res = await apiService.getRepositories();
      if (!res.live || !Array.isArray(res.data) || res.data.length === 0) return;

      const dbScans = res.data.slice(0, 5).map((repo) => ({
        repository_id: repo.id,
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

      // Default to latest repository if none selected yet
      if (!currentRepositoryId && res.data[0]) {
        const latestRepo = res.data[0];
        setCurrentRepositoryId(latestRepo.id);
        const bugsRes = await apiService.getBugs({ repository_id: latestRepo.id });
        if (bugsRes.live && Array.isArray(bugsRes.data) && bugsRes.data.length > 0) {
          const mapped = bugsRes.data.map((b, idx) => mapBackendCandidateIssueToUiBug(b, idx));
          setBugs(mapped);
        }
      }

      // Enrich presets with real analysis status in background
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
          statusLabel = "Analyzing…";
          badgeColor = "bg-cyan-500";
        } else if (runStatus === "failed") {
          statusLabel = "Analysis failed";
          badgeColor = "bg-red-500";
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
  }, [isAuthenticated]);

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
    stopPolling();
    setCurrentRepositoryId(null);
    setStats({
      ...DEFAULT_STATS,
      openHigh: 0,
    });
    setBugs([]);

    const targetUrl = typeof targetInput === "string" ? targetInput.trim() : repoUrl;
    if (!isFile && typeof targetInput === "string") {
      setRepoUrl(targetInput.trim());
    }

    try {
      if (!isFile) {
        setScanStage("Validating GitHub repository...");
        setScanProgress(15);

        const parsed = parseGitHubUrl(targetUrl);
        if (!parsed) {
          throw Object.assign(
            new Error(`"${targetUrl}" is not a valid GitHub repository URL. Expected format: https://github.com/owner/repo`),
            { type: "invalid_url" }
          );
        }

        setScanStage("Downloading repository to scan engine...");
        setScanProgress(25);

        let cloneData;
        try {
          const cloneRes = await fetch(`${apiService.getBaseUrl()}/repositories/clone`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ repository_url: targetUrl }),
            signal: AbortSignal.timeout(120000),
          });

          if (!cloneRes.ok) {
            const err = await cloneRes.json().catch(() => ({}));
            const detail = err.detail || cloneRes.statusText;
            if (cloneRes.status === 400) {
              throw Object.assign(
                new Error(`Unable to clone repository. It may be private or invalid.\nDetails: ${detail}`),
                { type: "not_found" }
              );
            }
            throw Object.assign(new Error(`Clone failed (${cloneRes.status}): ${detail}`), { type: "unknown" });
          }

          cloneData = await cloneRes.json();
        } catch (err) {
          if (err.name === "TimeoutError" || err.name === "AbortError") {
            throw Object.assign(
              new Error("Repository download timed out after 2 minutes."),
              { type: "unknown" }
            );
          }
          if (err.type) throw err;
          throw Object.assign(
            new Error("Backend server is not reachable. Please check if FastAPI is running on port 8000."),
            { type: "no_backend" }
          );
        }

        setScanStage(`✓ Cloned ${cloneData.repository_name} — fetching metadata...`);
        setScanProgress(50);

        let githubResult = null;
        try {
          githubResult = await fetchGitHubRepo(targetUrl);
        } catch (_) {
          // Non-fatal
        }

        if (githubResult) {
          setAiSummary(githubResult.aiSummary);
          setRepoMeta(githubResult.repoMeta);
        }

        if (cloneData?.repository_id) {
          setCurrentRepositoryId(cloneData.repository_id);
        }

        setIsLive(true);

        const cleanName = cloneData.repository_name;
        setRecentScans((prev) => [
          {
            repository_id: cloneData.repository_id,
            name: cleanName,
            repo_url: targetUrl,
            date: "Just now",
            status: "Analyzing…",
            badgeColor: "bg-cyan-500",
            totalBugs: 0,
          },
          ...prev.filter((item) => item.repo_url !== targetUrl).slice(0, 4),
        ]);

        setScanStage("✓ Repository downloaded — analyzing codebase AST...");
        setScanProgress(30);

        if (cloneData?.repository_id) {
          startAnalysisPolling(cloneData.repository_id);
        } else {
          setScanProgress(100);
          setScanStage("✓ Scan complete");
          setScanCompleted(true);
          setIsScanning(false);
        }
        return;

      } else {
        // ZIP upload path
        setScanStage("Uploading archive to scan engine...");
        setScanProgress(20);

        let uploadData;
        try {
          const uploadRes = await fetch(`${apiService.getBaseUrl()}/repositories/upload`, {
            method: "POST",
            body: targetInput,
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
            new Error("Backend server is not reachable. Please check if FastAPI is running on port 8000."),
            { type: "no_backend" }
          );
        }

        setScanStage(`✓ Uploaded ${uploadData.repository_name} — analyzing...`);
        setScanProgress(30);

        setRepoMeta({
          fullName: uploadData.repository_name,
          description: "Uploaded ZIP archive",
          stars: 0,
          forks: 0,
          totalFiles: 0,
          defaultBranch: "—",
        });

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
            status: "Analyzing…",
            badgeColor: "bg-cyan-500",
            totalBugs: 0,
          },
          ...prev.slice(0, 4),
        ]);

        setScanStage("✓ Archive uploaded — analyzing codebase AST...");
        if (uploadData?.repository_id) {
          startAnalysisPolling(uploadData.repository_id);
        } else {
          setScanProgress(100);
          setScanStage("✓ Archive scan complete");
          setScanCompleted(true);
          setIsScanning(false);
        }
        return;
      }

    } catch (err) {
      stopPolling();
      setScanProgress(0);
      setScanStage("");
      setScanCompleted(false);
      setScanError({
        message: err.message || "An unexpected error occurred during the scan.",
        type: err.type || "unknown",
      });
    } finally {
      if (pollingRef.current === null) {
        setIsScanning(false);
      }
    }
  };

  const loadRecentScan = (recentItem) => {
    if (recentItem.repository_id) {
      stopPolling();
      setCurrentRepositoryId(recentItem.repository_id);
      setStats(DEFAULT_STATS);
      setBugs([]);
      setScanCompleted(false);
      setScanError(null);
      if (recentItem.repo_url) setRepoUrl(recentItem.repo_url);

      (async () => {
        const res = await apiService.getRepositoryAnalysisStatus(recentItem.repository_id);
        if (res.live && res.data && res.data.status === "completed") {
          const { total_files, candidate_issues_count, high_open_issues, duration_seconds } = res.data;
          setStats((prev) => ({
            ...prev,
            totalBugs: candidate_issues_count ?? 0,
            totalFiles: total_files ?? prev.totalFiles,
            scanTime: duration_seconds != null ? `${duration_seconds.toFixed(1)}s` : prev.scanTime,
            linesOfCode: null, // cleared to prevent stale DEFAULT_STATS value
            critical: 0,
            openHigh: high_open_issues ?? 0,
          }));
          setIsLive(true);
          setScanCompleted(true);
          // Fetch real candidate issues so TabAiArchitecture can show "Inspect Bug" cards.
          const bugsRes = await apiService.getBugs({ repository_id: recentItem.repository_id });
          if (bugsRes.live && Array.isArray(bugsRes.data)) {
            setBugs(bugsRes.data.map((issue, idx) => mapBackendCandidateIssueToUiBug(issue, idx)));
          } else {
            setBugs([]);
          }
        } else if (res.live && res.data && res.data.status === "running") {
          // Analysis still in progress — resume polling.
          setScanCompleted(false);
          setIsScanning(true);
          setScanProgress(30);
          setScanStage("✓ Resuming analysis monitoring...");
          startAnalysisPolling(recentItem.repository_id);
        } else if (res.live && res.data && res.data.status === "none") {
          // No analysis run yet — show neutral zero state, not DEFAULT_STATS.
          setStats((prev) => ({
            ...prev,
            totalBugs: 0,
            totalFiles: 0,
            scanTime: "—",
            linesOfCode: null,
            critical: 0,
            openHigh: 0,
          }));
          setBugs([]);
          setScanCompleted(false);
        } else if (res.live && res.data && res.data.status === "failed") {
          // Analysis failed — show zero state.
          setStats((prev) => ({
            ...prev,
            totalBugs: 0,
            totalFiles: 0,
            scanTime: "—",
            linesOfCode: null,
            critical: 0,
            openHigh: 0,
          }));
          setBugs([]);
          setScanCompleted(false);
        }
        // If res.live is false (backend unreachable), stats stay as DEFAULT_STATS
        // which is the correct demo/fallback behavior.
      })();
      return;
    }

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

  // Toggle Bug Resolution Status - persists to PostgreSQL
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

  // Update Bug Severity - persists to PostgreSQL
  const updateBugSeverity = async (bugId, nextSeverity) => {
    const formattedSev =
      nextSeverity.toLowerCase() === "low"
        ? "Low"
        : nextSeverity.toLowerCase() === "medium"
        ? "Medium"
        : "High";

    setBugs((prevBugs) =>
      prevBugs.map((b) => (b.id === bugId ? { ...b, severity: formattedSev } : b))
    );
    if (activeDrawerBug && activeDrawerBug.id === bugId) {
      setActiveDrawerBug((prev) => ({ ...prev, severity: formattedSev }));
    }
    const res = await apiService.updateBugSeverity(bugId, formattedSev.toLowerCase());
    setIsLive(res.live);
  };

  // Update Engineer Remarks - persists to PostgreSQL with debounce
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
  const highUnresolvedCount = bugs.filter(
    (b) => b.severity === "High" && b.status !== "Resolved"
  ).length;
  const mediumUnresolvedCount = bugs.filter(
    (b) => b.severity === "Medium" && b.status !== "Resolved"
  ).length;
  const lowUnresolvedCount = bugs.filter(
    (b) => b.severity === "Low" && b.status !== "Resolved"
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
    toggleResolveBug, updateBugSeverity, updateBugNotes,
    bugSearchQuery, setBugSearchQuery,
    selectedSeverity, setSelectedSeverity,
    selectedStatus, setSelectedStatus,
    aiSearchQuery, setAiSearchQuery,
    selectedFileFilter, setSelectedFileFilter,
    totalBugsCount, highUnresolvedCount, mediumUnresolvedCount, lowUnresolvedCount,
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
