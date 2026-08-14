// App.jsx - Main Application Entry Point with BugTrackerProvider

import React, { useState } from "react";
import { BugTrackerProvider, useBugTracker } from "./useBugTracker.js";
import BugTrackerDashboard from "./BugTrackerDashboard.jsx";

function MainContent() {
  const { isAuthenticated, login } = useBugTracker();
  const [usernameInput, setUsernameInput] = useState("SamSequeira");
  const [repoInput, setRepoInput] = useState("BugTracker");

  const handleLoginSubmit = (e) => {
    e.preventDefault();
    login(usernameInput, repoInput);
  };

  if (!isAuthenticated) {
    return (
      <div className="min-h-screen bg-[#0B0F17] flex flex-col justify-between p-6 max-w-5xl mx-auto text-slate-200">
        <header className="flex items-center justify-between py-4 border-b border-slate-800">
          <div className="flex items-center space-x-3">
            <div className="p-2.5 bg-cyan-500/10 rounded-xl text-cyan-400 border border-cyan-500/20">
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
            </div>
            <div>
              <h1 className="font-bold text-white text-base">AI Bug Tracking System</h1>
              <p className="text-[11px] text-slate-400">AST Analysis, Static Vulnerability Scanner & NLP Intelligence</p>
            </div>
          </div>
          <span className="text-xs text-slate-500 border border-slate-800 bg-[#0F1623] px-3 py-1 rounded-full">v1.2.0 Production Ready</span>
        </header>

        <main className="my-auto max-w-md w-full mx-auto py-10 space-y-6">
          <div className="text-center space-y-2">
            <h2 className="text-2xl font-bold text-white tracking-tight">Connect Your GitHub Account</h2>
            <p className="text-xs text-slate-400">Authenticate to scan repositories, inspect vulnerabilities, and generate audit reports.</p>
          </div>

          <div className="bg-[#131B2E] border border-slate-800 rounded-xl p-6 shadow-2xl space-y-5">
            <form onSubmit={handleLoginSubmit} className="space-y-4">
              <div>
                <label className="text-xs text-slate-400 block mb-1 font-medium">GitHub Username / Organization</label>
                <input
                  type="text"
                  required
                  value={usernameInput}
                  onChange={(e) => setUsernameInput(e.target.value)}
                  placeholder="e.g. SamSequeira"
                  className="w-full bg-[#0B0F17] border border-slate-700 rounded-lg px-3.5 py-2.5 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-cyan-500 font-mono"
                />
              </div>

              <div>
                <label className="text-xs text-slate-400 block mb-1 font-medium">Default Repository to Analyze</label>
                <input
                  type="text"
                  required
                  value={repoInput}
                  onChange={(e) => setRepoInput(e.target.value)}
                  placeholder="e.g. BugTracker"
                  className="w-full bg-[#0B0F17] border border-slate-700 rounded-lg px-3.5 py-2.5 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-cyan-500 font-mono"
                />
              </div>

              <button
                type="submit"
                className="w-full bg-cyan-400 hover:bg-cyan-300 text-slate-950 font-bold py-2.5 rounded-lg text-xs transition-colors flex items-center justify-center gap-2 shadow-lg shadow-cyan-500/10"
              >
                Sign in & Fetch Repository Files &rarr;
              </button>
            </form>
          </div>
        </main>

        <footer className="text-center text-xs text-slate-600 border-t border-slate-800/60 pt-4">
          AI Bug Tracking System • Confidential & Internal Use
        </footer>
      </div>
    );
  }

  return <BugTrackerDashboard />;
}

export default function App() {
  return (
    <BugTrackerProvider>
      <MainContent />
    </BugTrackerProvider>
  );
}