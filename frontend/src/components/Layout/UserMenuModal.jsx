// src/components/Layout/UserMenuModal.jsx - User Profile & Sign Out Menu Modal
import React from "react";
import { useBugTracker } from "../../useBugTracker.jsx";

export default function UserMenuModal({ isOpen, onClose }) {
  const { sessionUser, logout, apiUrl, isLive } = useBugTracker();

  if (!isOpen) return null;

  const handleSignOut = async () => {
    onClose();
    await logout();
  };

  const name = sessionUser?.name || "Alex Mercer";
  const email = sessionUser?.email || "alex.mercer@bugtracker.dev";
  const initials = sessionUser?.initials || name.substring(0, 2).toUpperCase();
  const role = sessionUser?.role || "Lead Security Engineer";

  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center sm:justify-start p-4 sm:p-6 sm:pl-20 bg-black/60 backdrop-blur-xs animate-fade-in">
      <div
        className="bg-[#131B2E] border border-slate-800 rounded-2xl w-full max-w-sm p-5 space-y-4 shadow-2xl relative"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between">
          <div className="flex items-center space-x-3">
            <div className="w-11 h-11 rounded-full bg-gradient-to-tr from-cyan-600 to-blue-600 text-white font-bold text-sm flex items-center justify-center border-2 border-cyan-400/40 shadow-lg shadow-cyan-500/10">
              {initials}
            </div>
            <div>
              <h3 className="text-sm font-bold text-white leading-tight">{name}</h3>
              <p className="text-[11px] text-slate-400 font-mono mt-0.5">{email}</p>
            </div>
          </div>

          <button
            onClick={onClose}
            className="text-slate-400 hover:text-white p-1 rounded-lg hover:bg-slate-800 transition-colors"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="bg-[#0B0F17] border border-slate-800/80 rounded-xl p-3 space-y-2 text-xs">
          <div className="flex justify-between items-center">
            <span className="text-slate-400">Security Role:</span>
            <span className="text-cyan-400 font-semibold bg-cyan-500/10 px-2 py-0.5 rounded border border-cyan-500/20">
              {role}
            </span>
          </div>
          <div className="flex justify-between items-center">
            <span className="text-slate-400">Backend Connection:</span>
            <span className={`font-mono text-[10px] flex items-center gap-1 ${isLive ? "text-emerald-400" : "text-amber-400"}`}>
              <span className={`w-1.5 h-1.5 rounded-full ${isLive ? "bg-emerald-400" : "bg-amber-400"}`}></span>
              {isLive ? "Live API Connected" : "Local Demo Session"}
            </span>
          </div>
          <div className="flex justify-between items-center truncate">
            <span className="text-slate-400">API Endpoint:</span>
            <span className="font-mono text-[10px] text-slate-300 truncate max-w-[170px]" title={apiUrl}>
              {apiUrl}
            </span>
          </div>
        </div>

        <div className="pt-2 border-t border-slate-800 flex justify-between gap-2">
          <button
            type="button"
            onClick={onClose}
            className="flex-1 bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold py-2 rounded-lg transition-colors"
          >
            Close Menu
          </button>
          <button
            type="button"
            onClick={handleSignOut}
            className="flex-1 bg-red-500/20 hover:bg-red-500/30 border border-red-500/30 text-red-300 hover:text-red-200 text-xs font-bold py-2 rounded-lg transition-colors flex items-center justify-center gap-1.5"
          >
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
            </svg>
            <span>Sign Out</span>
          </button>
        </div>
      </div>
    </div>
  );
}
