// src/components/Modals/NotificationDrawer.jsx - Dynamic Notification Drawer
import React from "react";
import { useBugTracker } from "../../useBugTracker.jsx";

export default function NotificationDrawer() {
  const {
    isNotificationsOpen,
    setIsNotificationsOpen,
    dynamicNotifications,
    unreadNotificationCount,
    markNotificationAsRead,
    markAllNotificationsAsRead,
    setActiveTab,
    setActiveDrawerBug,
    bugs,
  } = useBugTracker();

  if (!isNotificationsOpen) return null;

  const handleNotificationClick = (notif) => {
    markNotificationAsRead(notif.id);
    const targetBug = bugs.find((b) => b.id === notif.bugId);
    if (targetBug) {
      setActiveTab("bugs");
      setActiveDrawerBug(targetBug);
    }
    setIsNotificationsOpen(false);
  };

  return (
    <div
      className="fixed inset-0 z-50 flex justify-end bg-black/60 backdrop-blur-xs animate-fade-in"
      onClick={() => setIsNotificationsOpen(false)}
    >
      <div
        className="w-full max-w-md bg-[#131B2E] border-l border-slate-800 h-full p-5 space-y-4 shadow-2xl flex flex-col animate-slide-in relative"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-800 pb-3 shrink-0">
          <div className="flex items-center space-x-2.5">
            <div className="p-2 bg-cyan-500/10 rounded-xl text-cyan-400 border border-cyan-500/20">
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth="2"
                  d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9"
                />
              </svg>
            </div>
            <div>
              <h3 className="text-sm font-bold text-white flex items-center gap-2">
                <span>Security Alerts</span>
                {unreadNotificationCount > 0 && (
                  <span className="bg-cyan-500/20 text-cyan-400 text-[10px] px-2 py-0.5 rounded-full border border-cyan-500/30">
                    {unreadNotificationCount} new
                  </span>
                )}
              </h3>
              <p className="text-xs text-slate-400">Live feed derived from active AST detection</p>
            </div>
          </div>

          <button
            onClick={() => setIsNotificationsOpen(false)}
            className="text-slate-400 hover:text-white p-1 rounded-lg hover:bg-slate-800 transition-colors"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Quick Actions */}
        <div className="flex items-center justify-between text-xs shrink-0">
          <span className="text-slate-400">{dynamicNotifications.length} active alerts</span>
          {dynamicNotifications.length > 0 && (
            <button
              onClick={markAllNotificationsAsRead}
              className="text-cyan-400 hover:text-cyan-300 transition-colors"
            >
              Mark all as read
            </button>
          )}
        </div>

        {/* Notifications List */}
        <div className="space-y-2.5 overflow-y-auto flex-1 pr-1">
          {dynamicNotifications.length === 0 ? (
            <div className="text-center py-12 text-slate-400 space-y-2">
              <div className="text-3xl">🎉</div>
              <p className="text-xs font-semibold text-white">All Clear! No Open Security Alerts</p>
              <p className="text-[11px] text-slate-500">Every detected vulnerability has been marked as resolved.</p>
            </div>
          ) : (
            dynamicNotifications.map((notif) => (
              <div
                key={notif.id}
                onClick={() => handleNotificationClick(notif)}
                className={`p-3.5 rounded-xl border transition-all cursor-pointer space-y-1.5 ${
                  notif.isRead
                    ? "bg-[#0B0F17]/60 border-slate-800/80 opacity-75 hover:opacity-100"
                    : "bg-[#0B0F17] border-cyan-500/30 hover:border-cyan-400"
                }`}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="flex items-center space-x-2">
                    <span
                      className={`w-2 h-2 rounded-full shrink-0 ${
                        notif.severity === "Critical" ? "bg-red-500 animate-pulse" : "bg-amber-400"
                      }`}
                    ></span>
                    <span className="text-xs font-semibold text-white leading-tight line-clamp-1">
                      {notif.title}
                    </span>
                  </div>
                  <span className="text-[10px] text-slate-500 shrink-0">{notif.time}</span>
                </div>
                <p className="text-[11px] text-slate-400 pl-4">{notif.message}</p>
                <div className="pl-4 flex items-center justify-between text-[10px]">
                  <span className="text-cyan-400 font-mono font-semibold hover:underline">
                    Inspect in Tab 3 →
                  </span>
                  <span className="text-slate-500 font-mono">{notif.bugId}</span>
                </div>
              </div>
            ))
          )}
        </div>

        {/* Footer */}
        <div className="pt-3 border-t border-slate-800 shrink-0 text-center">
          <button
            onClick={() => {
              setActiveTab("bugs");
              setIsNotificationsOpen(false);
            }}
            className="w-full bg-slate-800 hover:bg-slate-700 text-slate-200 py-2 rounded-lg text-xs font-semibold transition-colors"
          >
            View All Issues in Bug Tracker
          </button>
        </div>
      </div>
    </div>
  );
}
