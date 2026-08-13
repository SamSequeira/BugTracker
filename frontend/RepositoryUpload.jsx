import React, { useState } from "react";
import {
  ShieldAlert,
  Upload,
  Github,
  FileArchive,
  Search,
  CheckCircle2,
  Clock,
  ChevronRight,
  Info,
  ArrowRight
} from "lucide-react";

export default function RepositoryUpload({ onScanComplete }) {
  const [activeTab, setActiveTab] = useState("github");
  const [repoUrl, setRepoUrl] = useState("");
  const [isScanning, setIsScanning] = useState(false);
  const [progress, setProgress] = useState(0);

  const handleStartScan = (e) => {
    e.preventDefault();
    setIsScanning(true);
    setProgress(15);

    // Simulate scanning progress before navigating to Dashboard
    const interval = setInterval(() => {
      setProgress((prev) => {
        if (prev >= 100) {
          clearInterval(interval);
          setTimeout(() => {
            onScanComplete(); // Triggers transition to Dashboard
          }, 500);
          return 100;
        }
        return prev + 25;
      });
    }, 600);
  };

  return (
    <div className="min-h-screen bg-[#0B0F17] text-slate-200 font-sans flex flex-col justify-between p-6">
      {/* Header */}
      <header className="max-w-5xl mx-auto w-full flex items-center justify-between py-4 border-b border-slate-800">
        <div className="flex items-center space-x-3">
          <div className="p-2 bg-cyan-500/10 rounded-lg text-cyan-400">
            <ShieldAlert className="w-6 h-6" />
          </div>
          <div>
            <h1 className="font-bold text-white text-base">AI Bug Tracking System</h1>
            <p className="text-xs text-slate-400">Automated AST & NLP Code Security Analysis</p>
          </div>
        </div>
        <span className="text-xs text-slate-500 border border-slate-800 bg-[#0F1623] px-3 py-1 rounded-full">
          v1.0.0 Frontend Demo
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
            {/* Input Selection Tabs */}
            <div className="flex border-b border-slate-800 pb-3 space-x-6">
              <button
                onClick={() => setActiveTab("github")}
                className={`text-xs font-semibold pb-2 border-b-2 transition-colors flex items-center gap-2 ${
                  activeTab === "github"
                    ? "border-cyan-400 text-cyan-400"
                    : "border-transparent text-slate-400 hover:text-white"
                }`}
              >
                <Github className="w-4 h-4" /> GitHub Repository
              </button>
              <button
                onClick={() => setActiveTab("zip")}
                className={`text-xs font-semibold pb-2 border-b-2 transition-colors flex items-center gap-2 ${
                  activeTab === "zip"
                    ? "border-cyan-400 text-cyan-400"
                    : "border-transparent text-slate-400 hover:text-white"
                }`}
              >
                <FileArchive className="w-4 h-4" /> Upload .ZIP Archive
              </button>
            </div>

            {/* Tab 1: GitHub Input Form */}
            {activeTab === "github" ? (
              <form onSubmit={handleStartScan} className="space-y-4">
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
                    className="w-full bg-[#0B0F17] border border-slate-700 rounded-lg px-4 py-3 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-cyan-500 transition-colors"
                  />
                </div>
                <button
                  type="submit"
                  className="w-full bg-cyan-400 hover:bg-cyan-300 text-slate-950 font-semibold py-3 rounded-lg text-xs transition-colors flex items-center justify-center gap-2 shadow-lg shadow-cyan-500/10"
                >
                  Analyze Repository <ArrowRight className="w-4 h-4" />
                </button>
              </form>
            ) : (
              /* Tab 2: Drag & Drop Box */
              <div
                onClick={handleStartScan}
                className="border-2 border-dashed border-slate-700 hover:border-cyan-500/50 bg-[#0B0F17]/50 rounded-lg p-10 flex flex-col items-center justify-center text-center cursor-pointer transition-colors"
              >
                <Upload className="w-10 h-10 text-cyan-400 mb-3" />
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
              <span className="flex items-center gap-1">
                <Info className="w-3.5 h-3.5 text-slate-400" /> Read-only mode: No changes are made to your repo.
              </span>
              <span>Supported: Python, JS, TS, Go, Java</span>
            </div>
          </div>
        ) : (
          /* Scanning Indicator State */
          <div className="bg-[#131B2E] border border-slate-800 rounded-xl p-8 space-y-6">
            <div className="flex items-center space-x-4">
              <div className="w-12 h-12 rounded-full border-2 border-cyan-500/30 border-t-cyan-400 animate-spin flex items-center justify-center shrink-0">
                <Search className="w-5 h-5 text-cyan-400" />
              </div>
              <div>
                <h3 className="text-sm font-semibold text-white">Scanning your codebase...</h3>
                <p className="text-xs text-slate-400">Parsing AST trees and static vulnerabilities</p>
              </div>
            </div>

            <div className="space-y-2">
              <div className="flex justify-between text-xs">
                <span className="text-slate-300">Analysis Progress</span>
                <span className="text-cyan-400 font-bold">{progress}%</span>
              </div>
              <div className="w-full bg-slate-800 h-2 rounded-full overflow-hidden">
                <div
                  className="bg-cyan-400 h-full transition-all duration-300"
                  style={{ width: `${progress}%` }}
                ></div>
              </div>
            </div>

            <ul className="text-xs space-y-2 text-slate-400 border-t border-slate-800 pt-4">
              <li className={`flex items-center gap-2 ${progress >= 25 ? "text-emerald-400" : "text-slate-500"}`}>
                <CheckCircle2 className="w-4 h-4" /> Reading source files...
              </li>
              <li className={`flex items-center gap-2 ${progress >= 50 ? "text-emerald-400" : "text-slate-500"}`}>
                <CheckCircle2 className="w-4 h-4" /> Running static analysis...
              </li>
              <li className={`flex items-center gap-2 ${progress >= 75 ? "text-cyan-400 animate-pulse" : "text-slate-500"}`}>
                <Clock className="w-4 h-4" /> Generating priority report...
              </li>
            </ul>
          </div>
        )}

        {/* Recent Scans Footer */}
        <div className="space-y-3">
          <h4 className="text-xs font-semibold text-slate-400">Recent Scans</h4>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
            {[
              { name: "payment-service", date: "May 18, 2026", bugs: "8 Critical" },
              { name: "user-dashboard", date: "May 15, 2026", bugs: "3 Critical" },
              { name: "inventory-api", date: "May 10, 2026", bugs: "Clean" },
            ].map((item, idx) => (
              <div
                key={idx}
                onClick={onScanComplete}
                className="bg-[#131B2E] hover:bg-slate-800/80 border border-slate-800 p-3 rounded-lg flex items-center justify-between cursor-pointer transition-colors"
              >
                <div>
                  <p className="text-xs font-medium text-slate-200">{item.name}</p>
                  <p className="text-[10px] text-slate-500">{item.date} • {item.bugs}</p>
                </div>
                <ChevronRight className="w-4 h-4 text-slate-500" />
              </div>
            ))}
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="max-w-5xl mx-auto w-full text-center text-xs text-slate-600 border-t border-slate-800/60 pt-4">
        AI Bug Tracking & Prioritization System • Confidential & Internal Use
      </footer>
    </div>
  );
}
