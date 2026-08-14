// src/components/Auth/AuthScreen.jsx - Main Authentication Landing Screen
import React, { useState } from "react";
import Login from "./Login.jsx";
import Signup from "./Signup.jsx";
import ForgotPasswordModal from "./ForgotPasswordModal.jsx";

export default function AuthScreen() {
  const [authMode, setAuthMode] = useState("login"); // 'login' | 'signup'
  const [isForgotPasswordOpen, setIsForgotPasswordOpen] = useState(false);

  return (
    <div className="min-h-screen bg-[#0B0F17] text-slate-200 flex flex-col justify-between relative overflow-hidden">
      {/* Background Decorative Glow Gradients */}
      <div className="absolute top-0 left-1/4 w-96 h-96 bg-cyan-500/10 rounded-full blur-3xl pointer-events-none -translate-y-1/2"></div>
      <div className="absolute bottom-0 right-1/4 w-96 h-96 bg-blue-600/10 rounded-full blur-3xl pointer-events-none translate-y-1/2"></div>

      {/* Top Navbar Branding */}
      <header className="max-w-6xl mx-auto w-full px-6 py-5 flex items-center justify-between relative z-10">
        <div className="flex items-center space-x-3">
          <div className="p-2 bg-cyan-500/10 rounded-xl text-cyan-400 border border-cyan-500/20 shadow-lg shadow-cyan-500/10">
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
          </div>
          <div>
            <h1 className="font-bold text-white text-base tracking-tight flex items-center gap-2">
              BugTracker <span className="text-cyan-400 font-mono text-xs">AI</span>
            </h1>
            <span className="text-[11px] text-slate-400 hidden sm:inline">
              Automated Code Triage & Prioritization System
            </span>
          </div>
        </div>

        <div className="flex items-center space-x-3">
          <span className="bg-[#131B2E] border border-slate-800 text-slate-400 text-[11px] px-3 py-1 rounded-full flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-cyan-400 animate-pulse"></span>
            AST & NLP Ready
          </span>
        </div>
      </header>

      {/* Main Split Layout: Left Feature Highlights, Right Auth Card */}
      <main className="max-w-6xl mx-auto w-full px-6 py-8 grid grid-cols-1 lg:grid-cols-12 gap-8 items-center relative z-10 my-auto">
        {/* Left Column: Product Value & Architecture Preview */}
        <div className="lg:col-span-6 space-y-6 hidden lg:block">
          <div className="inline-flex items-center gap-2 bg-cyan-500/10 border border-cyan-500/20 text-cyan-400 px-3 py-1 rounded-full text-xs font-semibold">
            <span className="w-2 h-2 rounded-full bg-cyan-400"></span>
            Enterprise Code Security Intelligence
          </div>

          <h2 className="text-3xl xl:text-4xl font-extrabold text-white leading-tight tracking-tight">
            Stop Critical Vulnerabilities <br />
            <span className="text-transparent bg-clip-text bg-gradient-to-r from-cyan-400 to-blue-500">
              Before They Reach Production.
            </span>
          </h2>

          <p className="text-slate-400 text-xs sm:text-sm leading-relaxed max-w-lg">
            BugTracker parses complete abstract syntax trees (AST), classifies code semantics using NLP, and pinpoints exact file and line vulnerabilities with actionable auto-suggested fixes.
          </p>

          <div className="grid grid-cols-2 gap-4 pt-2">
            <div className="bg-[#131B2E]/80 border border-slate-800/80 rounded-xl p-4 space-y-1.5">
              <div className="text-cyan-400 font-bold text-sm flex items-center gap-1.5">
                <span>🛡️</span> Zero-Config Scanning
              </div>
              <p className="text-[11px] text-slate-400">
                Connect via GitHub URL or drag-and-drop .ZIP archives.
              </p>
            </div>

            <div className="bg-[#131B2E]/80 border border-slate-800/80 rounded-xl p-4 space-y-1.5">
              <div className="text-red-400 font-bold text-sm flex items-center gap-1.5">
                <span>⚡</span> AI Prioritization
              </div>
              <p className="text-[11px] text-slate-400">
                Rank issues from P1 (immediate fix) down to P4 backlogs.
              </p>
            </div>

            <div className="bg-[#131B2E]/80 border border-slate-800/80 rounded-xl p-4 space-y-1.5">
              <div className="text-amber-400 font-bold text-sm flex items-center gap-1.5">
                <span>✨</span> Code Diff Suggestions
              </div>
              <p className="text-[11px] text-slate-400">
                Direct suggested code diff removals & additions for every bug.
              </p>
            </div>

            <div className="bg-[#131B2E]/80 border border-slate-800/80 rounded-xl p-4 space-y-1.5">
              <div className="text-emerald-400 font-bold text-sm flex items-center gap-1.5">
                <span>📄</span> Executive PDF Reports
              </div>
              <p className="text-[11px] text-slate-400">
                One-click audit resolution summaries ready for export.
              </p>
            </div>
          </div>
        </div>

        {/* Right Column: Authentication Card */}
        <div className="lg:col-span-6 max-w-md w-full mx-auto">
          <div className="bg-[#131B2E] border border-slate-800 rounded-2xl p-6 sm:p-8 shadow-2xl shadow-black/60 relative">
            {/* Top Switcher Tabs */}
            <div className="flex border-b border-slate-800 pb-3 mb-6 space-x-6">
              <button
                type="button"
                onClick={() => setAuthMode("login")}
                className={`text-xs font-bold pb-2 border-b-2 transition-colors cursor-pointer ${
                  authMode === "login"
                    ? "border-cyan-400 text-cyan-400"
                    : "border-transparent text-slate-400 hover:text-white"
                }`}
              >
                Sign In
              </button>
              <button
                type="button"
                onClick={() => setAuthMode("signup")}
                className={`text-xs font-bold pb-2 border-b-2 transition-colors cursor-pointer ${
                  authMode === "signup"
                    ? "border-cyan-400 text-cyan-400"
                    : "border-transparent text-slate-400 hover:text-white"
                }`}
              >
                Create Account
              </button>
            </div>

            {authMode === "login" ? (
              <Login
                onSwitchToSignup={() => setAuthMode("signup")}
                onOpenForgotPassword={() => setIsForgotPasswordOpen(true)}
              />
            ) : (
              <Signup onSwitchToLogin={() => setAuthMode("login")} />
            )}
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="max-w-6xl mx-auto w-full px-6 py-4 border-t border-slate-800/80 flex flex-col sm:flex-row items-center justify-between text-xs text-slate-500 gap-2 relative z-10">
        <div>AI Bug Tracking & Prioritization System • Production Ready</div>
        <div className="flex items-center space-x-4">
          <span className="hover:text-slate-400 cursor-pointer">Security Policy</span>
          <span>•</span>
          <span className="hover:text-slate-400 cursor-pointer">FastAPI API Schema</span>
        </div>
      </footer>

      {/* Forgot Password Modal */}
      <ForgotPasswordModal
        isOpen={isForgotPasswordOpen}
        onClose={() => setIsForgotPasswordOpen(false)}
      />
    </div>
  );
}
