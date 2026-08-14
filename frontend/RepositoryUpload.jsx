// RepositoryUpload.jsx - Standalone Landing / Scan Trigger Page Component

import React, { useState } from "react";
import { useBugTracker } from "./useBugTracker.js";

export default function RepositoryUpload({ onScanComplete }) {
  const { user, runScan, isScanning, scanProgress } = useBugTracker();
  const [activeTab, setActiveTab] = useState("github");
  const [repoUrl, setRepoUrl] = useState(user.repoUrl);

  const handleSubmit = (e) => {
    e.preventDefault();
    runScan(repoUrl);
    if (onScanComplete) {
      setTimeout(() => {
        onScanComplete();
      }, 1200);
    }
  };

  const handleNativeUpload = (e) => {
    const file = e.target.files[0];
    if (file) {
      runScan(file);
      if (onScanComplete) {
        setTimeout(() => {
          onScanComplete();
        }, 1200);
      }
    }
  };

  return (
    <div className="min-h-screen bg-[#0B0F17] text-slate-200 font-sans flex flex-col justify-between p-6">
      <input
        type="file"
        id="landing-zip-input"
        accept=".zip,.tar,.gz,.rar,.7z"
        className="hidden"
        onChange={handleNativeUpload}
      />

      {/* Header */}
      <header className="max-w-5xl mx-auto w-full flex items-center justify-between py-4 border-b border-slate-800">
        <div className="flex items-center space-x-3">
          <div className="p-2.5 bg-cyan-500/10 rounded-xl text-cyan-400 border border-cyan-500/20">
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
          </div>
          <div>
            <h1 className="font-bold text-white text-base">AI Bug Tracking System</h1>
            <p className="text-xs text-slate-400">Automated AST & NLP Code Security Analysis</p>
          </div>
        </div>
        <span className="text-xs text-slate-500 border border-slate-800 bg-[#0F1623] px-3 py-1 rounded-full">
          v1.2.0 Production Ready
        </span>
      </header>

      {/* Main Upload Box */}
      <main className="max-w-3xl mx-auto w-full my-auto py-10 space-y-8">
        <div className="text-center space-y-2">
          <h2 className="text-2xl font-bold text-white tracking-tight">
            Analyze Your Codebase in Seconds
          </h2>
          <p className="text-slate-400 text-xs sm:text-sm max-w-md mx-auto">
            Upload a zipped project or enter a public GitHub repository link to run automated security bug detection.
          </p>
        </div>

        {!isScanning ? (
          <div className="bg-[#131B2E] border border-slate-800 rounded-xl p-6 shadow-xl space-y-6">
            <div className="flex border-b border-slate-800 pb-3 space-x-6">
              <button
                onClick={() => setActiveTab("github")}
                className={`text-xs font-semibold pb-2 border-b-2 transition-colors ${
                  activeTab === "github"
                    ? "border-cyan-400 text-cyan-400"
                    : "border-transparent text-slate-400 hover:text-white"
                }`}
              >
                GitHub Repository
              </button>
              <button
                onClick={() => setActiveTab("zip")}
                className={`text-xs font-semibold pb-2 border-b-2 transition-colors ${
                  activeTab === "zip"
                    ? "border-cyan-400 text-cyan-400"
                    : "border-transparent text-slate-400 hover:text-white"
                }`}
              >
                Upload .ZIP Archive
              </button>
            </div>

            {activeTab === "github" ? (
              <form onSubmit={handleSubmit} className="space-y-4">
                <div>
                  <label className="text-xs text-slate-400 block mb-1 font-medium">
                    GitHub Repository Link
                  </label>
                  <input
                    type="url"
                    required
                    value={repoUrl}
                    onChange={(e) => setRepoUrl(e.target.value)}
                    placeholder="https://github.com/your-org/your-repo"
                    className="w-full bg-[#0B0F17] border border-slate-700 rounded-lg px-4 py-3 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-cyan-500 transition-colors font-mono"
                  />
                </div>
                <button
                  type="submit"
                  className="w-full bg-cyan-400 hover:bg-cyan-300 text-slate-950 font-bold py-3 rounded-lg text-xs transition-colors flex items-center justify-center gap-2 shadow-lg shadow-cyan-500/10"
                >
                  Analyze Repository &rarr;
                </button>
              </form>
            ) : (
              <div
                onClick={() => document.getElementById("landing-zip-input").click()}
                className="border-2 border-dashed border-slate-700 hover:border-cyan-500/50 bg-[#0B0F17]/50 rounded-lg p-10 flex flex-col items-center justify-center text-center cursor-pointer transition-colors"
              >
                <svg className="w-10 h-10 text-cyan-400 mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                </svg>
                <p className="text-xs font-semibold text-slate-200">
                  Drag and drop your project .ZIP file here
                </p>
                <span className="text-[11px] text-slate-500 my-1">or</span>
                <span className="bg-slate-800 border border-slate-700 text-slate-200 text-xs px-3 py-1.5 rounded-md font-medium">
                  Browse Files
                </span>
                <span className="text-[10px] text-slate-500 mt-3">Maximum supported size: 500MB</span>
              </div>
            )}

            <div className="flex items-center justify-between pt-2 text-[11px] text-slate-500 border-t border-slate-800/60">
              <span>Read-only mode: No changes are made to your repo.</span>
              <span>Supported: Python, JS, TS, Go, Java</span>
            </div>
          </div>
        ) : (
          <div className="bg-[#131B2E] border border-slate-800 rounded-xl p-8 space-y-6">
            <div className="flex items-center space-x-4">
              <div className="w-12 h-12 rounded-full border-2 border-cyan-500/30 border-t-cyan-400 animate-spin flex items-center justify-center shrink-0">
                <svg className="w-5 h-5 text-cyan-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                </svg>
              </div>
              <div>
                <h3 className="text-sm font-semibold text-white">Scanning your codebase...</h3>
                <p className="text-xs text-slate-400">Parsing AST trees and static vulnerabilities</p>
              </div>
            </div>

            <div className="space-y-2">
              <div className="flex justify-between text-xs">
                <span className="text-slate-300">Analysis Progress</span>
                <span className="text-cyan-400 font-bold">{scanProgress}%</span>
              </div>
              <div className="w-full bg-slate-800 h-2 rounded-full overflow-hidden">
                <div
                  className="bg-cyan-400 h-full transition-all duration-300"
                  style={{ width: `${scanProgress}%` }}
                ></div>
              </div>
            </div>
          </div>
        )}
      </main>

      <footer className="max-w-5xl mx-auto w-full text-center text-xs text-slate-600 border-t border-slate-800/60 pt-4">
        AI Bug Tracking & Prioritization System • Confidential & Internal Use
      </footer>
    </div>
  );
}
