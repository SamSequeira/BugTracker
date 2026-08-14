// src/components/Layout/Header.jsx - Sticky Header Bar with Dynamic Stats & Actions
import React from "react";
import { useBugTracker } from "../../useBugTracker.jsx";

export default function Header() {
  const {
    criticalUnresolvedCount,
    isLive,
    setIsSearchOpen,
    setIsNotificationsOpen,
    unreadNotificationCount,
    setIsSettingsOpen,
    apiUrl,
  } = useBugTracker();

  const isMac = typeof navigator !== "undefined" && /(Mac|iPhone|iPod|iPad)/i.test(navigator.userAgent);

  return (
    <header className="h-14 bg-[#0F1623] border-b border-slate-800 px-4 sm:px-6 flex items-center justify-between sticky top-0 z-20 shrink-0">
      {/* Title & Technical Subtitle */}
      <div className="flex items-center space-x-3 truncate">
        <h1 className="font-semibold text-white text-sm sm:text-base tracking-tight truncate">
          AI Bug Tracking & Prioritization System
        </h1>
        <span className="text-[11px] text-slate-400 hidden xl:inline border-l border-slate-800 pl-3">
          Automated AST Analysis, NLP Classification & Triage
        </span>
      </div>

      {/* Right Actions & Status Badges */}
      <div className="flex items-center space-x-3">
        {/* Live Data / Demo Data Badge */}
        <button
          onClick={() => setIsSettingsOpen(true)}
          title={`Backend: ${apiUrl} (${isLive ? "Live API connected" : "Using local demo fallback dataset"})`}
          className={`text-[11px] font-medium px-2.5 py-1 rounded-full border flex items-center gap-1.5 transition-colors cursor-pointer ${
            isLive
              ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/30 hover:bg-emerald-500/20"
              : "bg-amber-500/10 text-amber-400 border-amber-500/30 hover:bg-amber-500/20"
          }`}
        >
          <span className={`w-1.5 h-1.5 rounded-full ${isLive ? "bg-emerald-400" : "bg-amber-400"}`}></span>
          <span>{isLive ? "Live data" : "Demo data"}</span>
        </button>

        {/* Dynamic Critical Issues Pill */}
        <span
          className={`border px-2.5 py-1 rounded-full text-xs font-semibold flex items-center gap-1.5 transition-all ${
            criticalUnresolvedCount > 0
              ? "bg-red-500/15 text-red-400 border-red-500/30 shadow-xs"
              : "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
          }`}
        >
          {criticalUnresolvedCount > 0 && (
            <span className="w-2 h-2 rounded-full bg-red-500 animate-pulse"></span>
          )}
          <span>{criticalUnresolvedCount} critical {criticalUnresolvedCount === 1 ? "issue" : "issues"}</span>
        </span>

        {/* Global Search Button */}
        <button
          onClick={() => setIsSearchOpen(true)}
          className="flex items-center space-x-2 bg-[#131B2E] hover:bg-slate-800 border border-slate-700/70 text-slate-300 hover:text-white px-2.5 py-1.5 rounded-lg text-xs transition-colors cursor-pointer"
          title="Search bugs, files, and commands"
        >
          <svg className="w-3.5 h-3.5 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
          <span className="hidden md:inline text-[11px] text-slate-400">Search</span>
          <kbd className="hidden sm:inline bg-[#0B0F17] border border-slate-700 text-slate-400 text-[10px] font-mono px-1.5 py-0.5 rounded">
            {isMac ? "⌘K" : "Ctrl+K"}
          </kbd>
        </button>

        {/* Notification Bell Button */}
        <button
          onClick={() => setIsNotificationsOpen(true)}
          className="relative p-2 text-slate-400 hover:text-white hover:bg-slate-800 rounded-lg transition-colors cursor-pointer"
          title="Open Notifications Drawer"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth="2"
              d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9"
            />
          </svg>
          {unreadNotificationCount > 0 && (
            <span className="absolute -top-0.5 -right-0.5 bg-cyan-400 text-slate-950 font-extrabold text-[10px] min-w-4 h-4 rounded-full flex items-center justify-center px-1 shadow-sm">
              {unreadNotificationCount}
            </span>
          )}
        </button>
      </div>
    </header>
  );
}
