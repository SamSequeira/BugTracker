// src/components/Layout/Sidebar.jsx - Fixed Left Navigation Bar
import React from "react";
import { useBugTracker } from "../../useBugTracker.jsx";

export default function Sidebar() {
  const {
    activeTab,
    setActiveTab,
    setIsSettingsOpen,
    setIsHelpOpen,
    setIsUserMenuOpen,
    sessionUser,
    highUnresolvedCount,
  } = useBugTracker();

  const name = sessionUser?.name || "Alex Mercer";
  const initials = sessionUser?.initials || name.substring(0, 2).toUpperCase();

  const navItems = [
    {
      id: "scanner",
      label: "Tab 1: Repository Scanner",
      icon: (
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z" />
        </svg>
      ),
    },
    {
      id: "ai",
      label: "Tab 2: AI Codebase Architecture",
      icon: (
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 3v4M3 5h4M6 17v4m-2-2h4m5-16l2.286 6.857L21 12l-5.714 2.143L13 21l-2.286-6.857L5 12l5.714-2.143L13 3z" />
        </svg>
      ),
    },
    {
      id: "bugs",
      label: "Tab 3: Bug Management & Inspector",
      icon: (
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 4v1m6 11h2m-6 0h-2v4m0-11v3m0 0h.01M12 12h4.01M16 20h4M4 12h4m12 0a8 8 0 11-16 0 8 8 0 0116 0z" />
        </svg>
      ),
      badge: highUnresolvedCount > 0 ? highUnresolvedCount : null,
    },
    {
      id: "reports",
      label: "Tab 4: Executive Audit & PDF Report",
      icon: (
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
        </svg>
      ),
    },
  ];

  return (
    <aside className="w-16 bg-[#0F1623] border-r border-slate-800 flex flex-col items-center py-4 space-y-4 shrink-0 sticky top-0 h-screen z-30 select-none">
      {/* Brand Logo */}
      <div
        onClick={() => setActiveTab("scanner")}
        title="BugTracker AI Home"
        className="p-2.5 bg-cyan-500/10 hover:bg-cyan-500/20 rounded-xl text-cyan-400 border border-cyan-500/20 shadow-lg shadow-cyan-500/10 cursor-pointer transition-all"
      >
        <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
        </svg>
      </div>

      {/* Navigation Tabs */}
      <nav className="flex flex-col space-y-2 w-full items-center pt-3 flex-1">
        {navItems.map((item) => {
          const isActive = activeTab === item.id;
          return (
            <button
              key={item.id}
              onClick={() => setActiveTab(item.id)}
              title={item.label}
              className={`p-3 w-full flex justify-center relative transition-all group ${
                isActive
                  ? "bg-cyan-500/15 text-cyan-400 border-l-3 border-cyan-400"
                  : "text-slate-400 hover:text-white hover:bg-slate-800/40"
              }`}
            >
              {item.icon}

              {/* Dynamic Issue Badge for Tab 3 */}
              {item.badge && !isActive && (
                <span className="absolute top-2 right-2 w-2 h-2 rounded-full bg-red-500 animate-pulse"></span>
              )}

              {/* Tooltip Hover Bubble */}
              <span className="absolute left-16 px-2.5 py-1 bg-slate-900 text-slate-100 text-xs font-semibold rounded-md shadow-xl border border-slate-700 whitespace-nowrap opacity-0 pointer-events-none group-hover:opacity-100 transition-opacity z-50">
                {item.label}
              </span>
            </button>
          );
        })}
      </nav>

      {/* Bottom Controls: Settings, Help, and Single User Avatar */}
      <div className="flex flex-col space-y-3 items-center pt-3 border-t border-slate-800/80 w-full">
        {/* Help Button */}
        <button
          onClick={() => setIsHelpOpen(true)}
          title="Help & Documentation"
          className="p-2 text-slate-400 hover:text-white hover:bg-slate-800 rounded-lg transition-colors group relative"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <span className="absolute left-16 px-2 py-1 bg-slate-900 text-slate-100 text-xs rounded-md shadow-xl border border-slate-700 whitespace-nowrap opacity-0 pointer-events-none group-hover:opacity-100 transition-opacity z-50">
            System Help
          </span>
        </button>

        {/* Settings Button */}
        <button
          onClick={() => setIsSettingsOpen(true)}
          title="Backend & Endpoint Settings"
          className="p-2 text-slate-400 hover:text-white hover:bg-slate-800 rounded-lg transition-colors group relative"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
          </svg>
          <span className="absolute left-16 px-2 py-1 bg-slate-900 text-slate-100 text-xs rounded-md shadow-xl border border-slate-700 whitespace-nowrap opacity-0 pointer-events-none group-hover:opacity-100 transition-opacity z-50">
            Settings & Backend URL
          </span>
        </button>

        {/* SINGLE AVATAR AT BOTTOM OF SIDEBAR ONLY */}
        <button
          onClick={() => setIsUserMenuOpen(true)}
          title={`User: ${name} (Click for Menu)`}
          className="w-8 h-8 rounded-full bg-gradient-to-tr from-cyan-600 to-blue-600 text-white flex items-center justify-center font-bold text-xs border border-cyan-400/50 hover:ring-2 hover:ring-cyan-400/40 transition-all cursor-pointer shadow-md"
        >
          {initials}
        </button>
      </div>
    </aside>
  );
}
