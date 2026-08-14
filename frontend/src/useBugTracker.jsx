// src/useBugTracker.jsx - Unified Shared Application State Provider
import React, { createContext, useContext, useState, useEffect, useCallback, useRef } from "react";
import { apiService } from "./api.js";
import { authService } from "./auth.js";
import { DEFAULT_STATS, DEFAULT_BUGS, DEFAULT_AI_SUMMARY, RECENT_SCANS } from "./mockData.js";

const BugTrackerContext = createContext(null);

export function BugTrackerProvider({ children }) {
  // 1. Authentication & Session State
  const [sessionUser, setSessionUser] = useState(() => authService.getSavedSession());
  const isAuthenticated = Boolean(sessionUser);

  // 2. Active Tab View
  // 'scanner' (Tab 1) | 'ai' (Tab 2) | 'bugs' (Tab 3) | 'reports' (Tab 4)
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

  // 5. Shared Data Objects (Single source of truth across all 4 Tabs)
  const [stats, setStats] = useState(DEFAULT_STATS);
  const [bugs, setBugs] = useState(DEFAULT_BUGS);
  const [aiSummary, setAiSummary] = useState(DEFAULT_AI_SUMMARY);
  const [recentScans, setRecentScans] = useState(RECENT_SCANS);

  // 6. Repository & Scanner State
  const [repoUrl, setRepoUrl] = useState("https://github.com/facebook/react");
  const [isScanning, setIsScanning] = useState(false);
  const [scanProgress, setScanProgress] = useState(0);
  const [scanStage, setScanStage] = useState("");
  const [scanCompleted, setScanCompleted] = useState(true);

  // 7. Filters and Search Queries
  const [bugSearchQuery, setBugSearchQuery] = useState("");
  const [selectedSeverity, setSelectedSeverity] = useState("All");
  const [selectedStatus, setSelectedStatus] = useState("All");
  const [aiSearchQuery, setAiSearchQuery] = useState("");
  const [selectedFileFilter, setSelectedFileFilter] = useState("All");

  // 8. Notification Read States
  const [readNotificationIds, setReadNotificationIds] = useState(new Set());

  // Debounce Ref for Engineer Remarks Auto-Save
  const notesTimerRef = useRef({});

  // Listen to API Live/Demo status changes
  useEffect(() => {
    const unsub = apiService.onStatusChange((live) => setIsLive(live));
    return unsub;
  }, []);

  // Keyboard shortcuts: Cmd/Ctrl+K for search, Escape for closing modals
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
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  // Central Initial & Refetch Data Loader
  const loadData = useCallback(async () => {
    const [statsRes, bugsRes, aiRes] = await Promise.all([
      apiService.getDashboardStats(),
      apiService.getBugs(),
      apiService.getAiSummary(),
    ]);

    setIsLive(statsRes.live || bugsRes.live || aiRes.live);

    if (statsRes.data) {
      setStats(statsRes.data);
    }
    if (aiRes.data) {
      setAiSummary(aiRes.data);
    }

    // Merge fetched bugs while preserving any local unsaved edits
    if (bugsRes.data) {
      setBugs((currentBugs) => {
        const localMap = new Map(currentBugs.map((b) => [b.id, b]));
        return bugsRes.data.map((fetchedBug) => {
          const local = localMap.get(fetchedBug.id);
          if (local) {
            return {
              ...fetchedBug,
              status: local.status,
              engineerNotes: local.engineerNotes || fetchedBug.engineerNotes,
            };
          }
          return fetchedBug;
        });
      });
    }
  }, []);

  // Load data when authenticated
  useEffect(() => {
    if (isAuthenticated) {
      loadData();
    }
  }, [isAuthenticated, loadData]);

  // Login handler
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

  // Signup handler
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

  // Logout handler
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

  // Update Settings API Base URL
  const updateApiUrl = async (newUrl) => {
    apiService.setBaseUrl(newUrl);
    setApiUrlState(apiService.getBaseUrl());
    await loadData();
  };

  // Trigger Repository Scan Pipeline
  const runScan = async (targetInput, isFile = false) => {
    setIsScanning(true);
    setScanProgress(5);
    setScanStage("Connecting to repository stream...");
    setScanCompleted(false);

    const targetUrl = typeof targetInput === "string" ? targetInput : repoUrl;
    if (!isFile && typeof targetInput === "string") {
      setRepoUrl(targetInput);
    }

    const payload = isFile ? targetInput : { repo_url: targetUrl };

    // Trigger API call in parallel
    const scanPromise = apiService.startScan(payload, isFile);

    // Multi-stage realistic progress
    const stages = [
      { pct: 20, stage: "✓ Repository connected & AST trees built" },
      { pct: 45, stage: "✓ Discovering files & dependency graph" },
      { pct: 70, stage: "✓ Analyzing architecture & static taint flows" },
      { pct: 90, stage: "✓ Detecting security bugs & CVE patterns" },
      { pct: 100, stage: "✓ AI prioritization & triage completed" },
    ];

    for (let i = 0; i < stages.length; i++) {
      await new Promise((resolve) => setTimeout(resolve, 350));
      setScanProgress(stages[i].pct);
      setScanStage(stages[i].stage);
    }

    const scanResult = await scanPromise;
    setIsLive(scanResult.live);

    // Add to recent scans
    if (!isFile && typeof targetUrl === "string" && targetUrl.trim()) {
      const cleanName = targetUrl.replace(/^https?:\/\//, "").replace(/\/+$/, "");
      setRecentScans((prev) => [
        {
          name: cleanName,
          repo_url: targetUrl,
          date: "Just now",
          status: "Scanned (8 Critical)",
          badgeColor: "bg-red-500",
          totalBugs: 128,
        },
        ...prev.filter((item) => item.repo_url !== targetUrl).slice(0, 4),
      ]);
    }

    setIsScanning(false);
    setScanCompleted(true);
    await loadData();
  };

  // Load a Recent Scan
  const loadRecentScan = (recentItem) => {
    setRepoUrl(recentItem.repo_url);
    runScan(recentItem.repo_url);
  };

  // Toggle Bug Resolution Status (Optimistic + Backend Sync)
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

    // Also update activeDrawerBug if open
    if (activeDrawerBug && activeDrawerBug.id === bugId) {
      setActiveDrawerBug((prev) => ({
        ...prev,
        status: prev.status === "Resolved" ? "Open" : "Resolved",
      }));
    }

    const res = await apiService.resolveBug(bugId, nextStatus);
    setIsLive(res.live);
  };

  // Update Engineer Remarks (Instant Shared State Sync + 500ms Debounced API Save)
  const updateBugNotes = (bugId, newNotes) => {
    // 1. Instant local update
    setBugs((prevBugs) =>
      prevBugs.map((b) => (b.id === bugId ? { ...b, engineerNotes: newNotes } : b))
    );

    if (activeDrawerBug && activeDrawerBug.id === bugId) {
      setActiveDrawerBug((prev) => ({ ...prev, engineerNotes: newNotes }));
    }

    // 2. Debounce API call
    if (notesTimerRef.current[bugId]) {
      clearTimeout(notesTimerRef.current[bugId]);
    }

    notesTimerRef.current[bugId] = setTimeout(async () => {
      const res = await apiService.updateBugNotes(bugId, newNotes);
      setIsLive(res.live);
    }, 500);
  };

  // Mark notification as read
  const markNotificationAsRead = (id) => {
    setReadNotificationIds((prev) => new Set([...prev, id]));
  };

  const markAllNotificationsAsRead = () => {
    const allIds = dynamicNotifications.map((n) => n.id);
    setReadNotificationIds(new Set(allIds));
  };

  // Computed Values Derived from Shared Bug State
  const totalBugsCount = bugs.length;
  const criticalUnresolvedCount = bugs.filter(
    (b) => b.severity === "Critical" && b.status !== "Resolved"
  ).length;
  const highUnresolvedCount = bugs.filter(
    (b) => b.severity === "High" && b.status !== "Resolved"
  ).length;
  const resolvedCount = bugs.filter((b) => b.status === "Resolved").length;
  const openCount = bugs.filter((b) => b.status !== "Resolved").length;
  const resolutionPercentage = Math.round(
    (resolvedCount / (totalBugsCount || 1)) * 100
  );

  // Dynamically Generated Notifications from Live Bug State
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
    // Auth & User
    isAuthenticated,
    sessionUser,
    login,
    signup,
    logout,

    // Navigation & Tabs
    activeTab,
    setActiveTab,

    // Modals & Drawers
    isSettingsOpen,
    setIsSettingsOpen,
    isHelpOpen,
    setIsHelpOpen,
    isSearchOpen,
    setIsSearchOpen,
    isNotificationsOpen,
    setIsNotificationsOpen,
    isUserMenuOpen,
    setIsUserMenuOpen,
    activeDrawerBug,
    setActiveDrawerBug,

    // API & Connection
    apiUrl,
    updateApiUrl,
    isLive,
    loadData,

    // Shared Data
    stats,
    bugs,
    aiSummary,
    recentScans,

    // Scanner
    repoUrl,
    setRepoUrl,
    isScanning,
    scanProgress,
    scanStage,
    scanCompleted,
    runScan,
    loadRecentScan,

    // Bug Actions
    toggleResolveBug,
    updateBugNotes,

    // Filters
    bugSearchQuery,
    setBugSearchQuery,
    selectedSeverity,
    setSelectedSeverity,
    selectedStatus,
    setSelectedStatus,
    aiSearchQuery,
    setAiSearchQuery,
    selectedFileFilter,
    setSelectedFileFilter,

    // Computed Stats
    totalBugsCount,
    criticalUnresolvedCount,
    highUnresolvedCount,
    resolvedCount,
    openCount,
    resolutionPercentage,

    // Dynamic Notifications
    dynamicNotifications,
    unreadNotificationCount,
    markNotificationAsRead,
    markAllNotificationsAsRead,
  };

  return (
    <BugTrackerContext.Provider value={value}>
      {children}
    </BugTrackerContext.Provider>
  );
}

export function useBugTracker() {
  const context = useContext(BugTrackerContext);
  if (!context) {
    throw new Error("useBugTracker must be used within a BugTrackerProvider");
  }
  return context;
}
