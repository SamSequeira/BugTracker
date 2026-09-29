// src/useBugTracker.jsx - Unified Shared Application State Provider
import React, { createContext, useContext, useState, useEffect, useCallback, useRef } from "react";
import { apiService } from "./api.js";
import { authService } from "./auth.js";
import { DEFAULT_STATS, DEFAULT_BUGS, DEFAULT_AI_SUMMARY, RECENT_SCANS } from "./mockData.js";
import { parseGitHubUrl, fetchGitHubRepo } from "./github.js";

const BugTrackerContext = createContext(null);

// // =========================================================================
// Convert real PostgreSQL CandidateIssue to UI Bug Object
// =========================================================================
function mapBackendCandidateIssueToUiBug(issue, index = 0) {
  const lineNum = issue.line_number || 1;
  const rawSev = (issue.verified_severity || issue.severity || "medium").toLowerCase();
  const normalizedSev = rawSev === "low" ? "Low" : rawSev === "high" || rawSev === "critical" ? "High" : "Medium";

  // Parse code snippet
  const rawSnippet = issue.code_snippet || issue.codeSnippet || "";
  let codeSnippet = [];
  if (rawSnippet && typeof rawSnippet === "string" && rawSnippet.trim()) {
    const rawLines = rawSnippet.split("\n");
    codeSnippet = rawLines.map((text, offset) => ({
      num: lineNum + offset,
      text: text,
      isErr: offset === 0,
    }));
  } else if (Array.isArray(issue.codeSnippet) && issue.codeSnippet.length > 0) {
    codeSnippet = issue.codeSnippet;
  } else if (issue.message || issue.title) {
    codeSnippet = [
      { num: lineNum, text: issue.message || issue.title, isErr: true },
    ];
  }

  // Priority mapping
  const rawPrio = (issue.verified_priority || issue.urgency || "p2").toLowerCase();
  const priorityLabel =
    rawPrio === "high" || rawPrio === "p1"
      ? "P1 • Fix now"
      : rawPrio === "low" || rawPrio === "p3" || rawPrio === "p4"
      ? "P3 • Backlog"
      : "P2 • Fix this week";

  const engineers = ["Alex Mercer", "Sarah Chen", "David Kumar", "Elena Rostova", "Marcus Vance"];

  const rawStatus = typeof issue.status === "string" ? issue.status : issue.status?.status || "open";
  const normalizedStatus = rawStatus.toLowerCase() === "resolved" ? "Resolved" : rawStatus.toLowerCase() === "in_review" || rawStatus.toLowerCase() === "in review" ? "In Review" : "Open";

  return {
    id: issue.id || `BUG-${index + 1}`,
    file: issue.file_path || issue.file || "unknown",
    line: lineNum,
    title: issue.title || issue.message || "Detected Issue",
    severity: normalizedSev,
    priority: priorityLabel,
    status: normalizedStatus,
    engineer: issue.engineer || engineers[index % engineers.length],
    createdAt: issue.created_at ? new Date(issue.created_at).toLocaleDateString() : "Recently",
    similarCount: issue.similar_count || null,
    engineerNotes: issue.engineer_notes || issue.verification_notes || issue.remarks || "",
    wrong: issue.description || issue.message || "Vulnerability or defect detected during static analysis.",
    matter: issue.security_impact || "Could lead to runtime failure or security compromise.",
    codeSnippet: codeSnippet,
    suggestedFix: issue.suggested_fix || null,
    ruleId: issue.rule_id || issue.ruleId || "",
    language: issue.language || "Unknown",
    rawIssue: issue,
  };
}

export function BugTrackerProvider({ children }) {
  // 1. Authentication & Session State
  const [sessionUser, setSessionUser] = useState(null);
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
  const [currentRepositoryId, setCurrentRepositoryId] = useState(null);
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
  const pollingRef = useRef(null);

  // Listen to API Live/Demo status changes
  useEffect(() => {
    const unsub = apiService.onStatusChange((live) => {
      setIsLive(live);
      // Clear backend unavailable error when backend becomes available
      if (live) {
        setScanError((currentError) =>
          currentError?.type === "no_backend" ? null : currentError
        );
      }
    });
    return unsub;
  }, []);

  // Restore user session on mount
  useEffect(() => {
    let cancelled = false;

    const restoreSession = async () => {
      if (!apiService.getToken()) {
        authService.saveSession(null);
        return;
      }

      const res = await apiService.getCurrentUser();
      if (cancelled) return;
      if (res.success && res.user) {
        authService.saveSession(res.user);
        setSessionUser(res.user);
      } else {
        apiService.setToken(null);
        authService.saveSession(null);
      }
    };

    restoreSession();
    return () => { cancelled = true; };
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

  // Analysis status polling
  const stopPolling = useCallback(() => {
    if (pollingRef.current !== null) {
      clearInterval(pollingRef.current);
      pollingRef.current = null;
    }
  }, []);

  const startAnalysisPolling = useCallback(
    (repositoryId) => {
      stopPolling();

      const POLL_INTERVAL_MS = 2000;
      const POLL_TIMEOUT_MS = 10 * 60 * 1000;
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
              "Analysis timed out after 10 minutes. The repository may be too large.",
            type: "unknown",
          });
          return;
        }

        const res = await apiService.getRepositoryAnalysisStatus(repositoryId);

        if (!res.live || !res.data) {
          return;
        }

        const { status: runStatus, total_files, candidate_issues_count, high_open_issues, duration_seconds } = res.data;

        if (runStatus === "none" || runStatus === "running") {
          if (runStatus === "running") {
            setScanProgress((prev) => Math.min(prev + 4, 90));
            setScanStage("✓ Analyzing codebase AST & checking security rules...");
          }
          return;
        }

        // Terminal state
        stopPolling();

        if (runStatus === "completed") {
          setIsLive(true);
          setScanProgress(100);
          setScanStage("✓ Analysis complete!");
          setScanCompleted(true);
          setIsScanning(false);

          setStats((prev) => ({
            ...prev,
            totalBugs: candidate_issues_count ?? 0,
            totalFiles: total_files ?? prev.totalFiles,
            scanTime: duration_seconds != null ? `${duration_seconds.toFixed(1)}s` : prev.scanTime,
            critical: 0,
            openHigh: high_open_issues ?? 0,
          }));

          // Retrieve live candidate issues from PostgreSQL
          const bugsRes = await apiService.getBugs({ repository_id: repositoryId });
          if (bugsRes.live && Array.isArray(bugsRes.data)) {
            const realBugs = bugsRes.data.map((b, idx) => mapBackendCandidateIssueToUiBug(b, idx));
            setBugs(realBugs);
          }

          setRecentScans((prev) =>
            prev.map((item) =>
              item.repository_id === repositoryId
                ? {
                    ...item,
                    status: (candidate_issues_count ?? 0) > 0 ? `${candidate_issues_count} issues` : "Clean",
                    badgeColor: (candidate_issues_count ?? 0) > 0 ? "bg-amber-500" : "bg-emerald-500",
                    totalBugs: candidate_issues_count ?? 0,
                  }
                : item
            )
          );
        } else if (runStatus === "failed") {
          setIsScanning(false);
          setScanProgress(0);
          setScanStage("");
          setScanCompleted(false);
          setScanError({
            message: "Static analysis run failed for this repository.",
            type: "unknown",
          });
        }
      }, POLL_INTERVAL_MS);
    },
    [stopPolling]
  );

  // Backend data loader
  const loadData = useCallback(async () => {
    const [statsRes, bugsRes, aiRes] = await Promise.all([
      apiService.getDashboardStats(),
      apiService.getBugs(),
      apiService.getAiSummary(),
    ]);

    setIsLive(statsRes.live || bugsRes.live || aiRes.live);

    if (statsRes.live && statsRes.data) setStats(statsRes.data);
    if (aiRes.live && aiRes.data) setAiSummary(aiRes.data);

    if (bugsRes.live && bugsRes.data && Array.isArray(bugsRes.data)) {
      setBugs(bugsRes.data.map((b, idx) => mapBackendCandidateIssueToUiBug(b, idx)));
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
    setScanStage("Connecting to scan engine...");
    setScanCompleted(false);
    stopPolling();
    setCurrentRepositoryId(null);
    setStats({
      ...DEFAULT_STATS,
      openHigh: 0,
      critical: 0,
    });
    setBugs([]);
    setBugs([]);

    const targetUrl = typeof targetInput === "string" ? targetInput.trim() : repoUrl;
    if (!isFile && typeof targetInput === "string") {
      setRepoUrl(targetInput.trim());
    }

    try {
      if (!isFile) {
        setScanStage("Validating repository URL...");
        setScanProgress(15);

        const parsed = parseGitHubUrl(targetUrl);
        if (!parsed) {
          throw Object.assign(
            new Error(`"${targetUrl}" is not a valid repository URL. Expected format: https://github.com/owner/repo`),
            { type: "invalid_url" }
          );
        }

        setScanStage("Cloning repository into analyzer workspace...");
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

        setScanStage(`✓ Cloned ${cloneData.repository_name} — starting analysis...`);
        setScanProgress(40);

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
            linesOfCode: null,
            critical: 0,
            openHigh: high_open_issues ?? 0,
          }));
          setIsLive(true);
          setScanCompleted(true);
          const bugsRes = await apiService.getBugs({ repository_id: recentItem.repository_id });
          if (bugsRes.live && Array.isArray(bugsRes.data)) {
            setBugs(bugsRes.data.map((issue, idx) => mapBackendCandidateIssueToUiBug(issue, idx)));
          } else {
            setBugs([]);
          }
        } else if (res.live && res.data && res.data.status === "running") {
          setScanCompleted(false);
          setIsScanning(true);
          setScanProgress(30);
          setScanStage("✓ Resuming analysis monitoring...");
          startAnalysisPolling(recentItem.repository_id);
        }
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
    const res = await apiService.resolveBug(bugId, nextStatus.toLowerCase());
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
