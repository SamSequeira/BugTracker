// useBugTracker.js - Unified React Context & Shared App State Provider

import React, { createContext, useContext, useState, useEffect, useCallback, useRef } from "react";
import { apiService } from "./api.js";
import { DEFAULT_STATS, DEFAULT_BUGS, DEFAULT_AI_SUMMARY, RECENT_SCANS, NOTIFICATIONS } from "./mockData.js";

const BugTrackerContext = createContext(null);

export function BugTrackerProvider({ children }) {
  // Auth & Workspace State
  const [isAuthenticated, setIsAuthenticated] = useState(true);
  const [user, setUser] = useState({
    username: "SamSequeira",
    repo: "BugTracker",
    repoUrl: "https://github.com/SamSequeira/BugTracker",
    avatar: "SS",
  });

  // UI Active Views & Navigation
  const [activeTab, setActiveTab] = useState("dashboard"); // 'dashboard' | 'ai' | 'debug' | 'report'
  const [scanInputTab, setScanInputTab] = useState("github");

  // Modals Visibility State
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [isHelpOpen, setIsHelpOpen] = useState(false);
  const [isSearchOpen, setIsSearchOpen] = useState(false);
  const [isNotificationsOpen, setIsNotificationsOpen] = useState(false);

  // Settings & Data Layer Connection State
  const [apiUrl, setApiUrlState] = useState(apiService.getBaseUrl());
  const [isLive, setIsLive] = useState(false);

  // Data Objects (Shared across all 4 Tabs)
  const [stats, setStats] = useState(DEFAULT_STATS);
  const [bugs, setBugs] = useState(DEFAULT_BUGS);
  const [aiSummary, setAiSummary] = useState(DEFAULT_AI_SUMMARY);
  const [recentScans, setRecentScans] = useState(RECENT_SCANS);
  const [notifications, setNotifications] = useState(NOTIFICATIONS);

  // Filters & Search
  const [searchQuery, setSearchQuery] = useState("");
  const [aiSearchQuery, setAiSearchQuery] = useState("");
  const [debugSeverity, setDebugSeverity] = useState("All");
  const [expandedBugId, setExpandedBugId] = useState("BUG-2026-0091");

  // Scan Execution State
  const [isScanning, setIsScanning] = useState(false);
  const [scanProgress, setScanProgress] = useState(67);
  const [selectedFileName, setSelectedFileName] = useState(null);

  // Debounce Map for Notes Auto-Save
  const notesTimerRef = useRef({});

  // 1. Initial Load & Background Refetch (Preserving local optimistic edits)
  const loadData = useCallback(async () => {
    const [statsRes, bugsRes, aiRes] = await Promise.all([
      apiService.getDashboardStats(),
      apiService.getBugs(),
      apiService.getAiSummary(),
    ]);

    setIsLive(statsRes.live || bugsRes.live || aiRes.live);

    if (statsRes.data) setStats(statsRes.data);
    if (aiRes.data) setAiSummary(aiRes.data);

    // Merge fetched bugs with unsaved local edits
    if (bugsRes.data) {
      setBugs((currentBugs) => {
        const editsMap = new Map(currentBugs.map((b) => [b.id, b]));
        return bugsRes.data.map((fetchedBug) => {
          const localEdit = editsMap.get(fetchedBug.id);
          if (localEdit) {
            return {
              ...fetchedBug,
              status: localEdit.status,
              engineerNotes: localEdit.engineerNotes,
            };
          }
          return fetchedBug;
        });
      });
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // Global Keyboard Shortcuts (Cmd/Ctrl+K for search, Esc to close modals)
  useEffect(() => {
    const handleKeyDown = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setIsSearchOpen((prev) => !prev);
      } else if (e.key === "Escape") {
        setIsSettingsOpen(false);
        setIsHelpOpen(false);
        setIsSearchOpen(false);
        setIsNotificationsOpen(false);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  // Update Settings API Base URL
  const updateApiUrl = (newUrl) => {
    apiService.setBaseUrl(newUrl);
    setApiUrlState(apiService.getBaseUrl());
    loadData();
  };

  // Sign In Handler
  const login = (username, repoName) => {
    const cleanUser = username.trim() || "SamSequeira";
    const cleanRepo = repoName.trim() || "BugTracker";
    const fullRepo = `${cleanUser}/${cleanRepo}`;
    const repoUrl = `https://github.com/${fullRepo}`;

    setUser({
      username: cleanUser,
      repo: cleanRepo,
      repoUrl: repoUrl,
      avatar: cleanUser.substring(0, 2).toUpperCase(),
    });
    setIsAuthenticated(true);
    setActiveTab("dashboard");
    runScan(repoUrl);
  };

  // Sign Out Handler
  const logout = () => {
    setIsAuthenticated(false);
    setActiveTab("dashboard");
    setIsSettingsOpen(false);
    setIsHelpOpen(false);
    setIsSearchOpen(false);
    setIsNotificationsOpen(false);
  };

  // Trigger Repository Scan Pipeline
  const runScan = async (inputSource) => {
    setIsScanning(true);
    setScanProgress(10);

    const isFile = typeof inputSource === "object";
    const payload = isFile ? inputSource : { repo_url: inputSource || user.repoUrl };

    if (!isFile && typeof inputSource === "string" && inputSource.includes("github.com")) {
      const parts = inputSource.replace("https://github.com/", "").split("/");
      if (parts.length >= 2) {
        setUser((prev) => ({
          ...prev,
          repoUrl: inputSource,
          username: parts[0],
          repo: parts[1],
        }));
      }
    }

    await apiService.startScan(payload, isFile);

    const interval = setInterval(() => {
      setScanProgress((prev) => {
        if (prev >= 100) {
          clearInterval(interval);
          setIsScanning(false);
          return 100;
        }
        return prev + 18;
      });
    }, 180);
  };

  // Toggle Bug Resolution Status (Optimistic + Backend Sync)
  const toggleResolveBug = async (bugId) => {
    let nextStatus = "Resolved";
    setBugs((prevBugs) =>
      prevBugs.map((bug) => {
        if (bug.id === bugId) {
          nextStatus = bug.status === "Resolved" ? "Open" : "Resolved";
          return { ...bug, status: nextStatus };
        }
        return bug;
      })
    );

    const res = await apiService.resolveBug(bugId, nextStatus);
    setIsLive(res.live);
  };

  // Update Engineer Remarks (Instant Local State Sync + 500ms Debounced API Save)
  const updateBugNotes = (bugId, newNote) => {
    // 1. Instant local state update so Tab 4 table updates immediately
    setBugs((prevBugs) =>
      prevBugs.map((b) => (b.id === bugId ? { ...b, engineerNotes: newNote } : b))
    );

    // 2. Debounced API dispatch
    if (notesTimerRef.current[bugId]) {
      clearTimeout(notesTimerRef.current[bugId]);
    }

    notesTimerRef.current[bugId] = setTimeout(async () => {
      const res = await apiService.updateBugNotes(bugId, newNote);
      setIsLive(res.live);
    }, 500);
  };

  // Computed Values
  const openCriticalCount = bugs.filter(
    (b) => b.severity === "Critical" && b.status !== "Resolved"
  ).length;

  const resolvedCount = bugs.filter((b) => b.status === "Resolved").length;
  const resolutionPercentage = Math.round(
    (resolvedCount / (bugs.length || 1)) * 100
  );

  const value = {
    isAuthenticated,
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
    login,
    logout,
    runScan,
    toggleResolveBug,
    updateBugNotes,
    openCriticalCount,
    resolvedCount,
    resolutionPercentage,
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
