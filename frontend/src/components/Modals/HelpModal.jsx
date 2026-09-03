// src/components/Modals/HelpModal.jsx - System Help & Documentation Modal
import React from "react";
import { useBugTracker } from "../../useBugTracker.jsx";

export default function HelpModal() {
  const { isHelpOpen, setIsHelpOpen } = useBugTracker();

  if (!isHelpOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-xs animate-fade-in">
      <div className="bg-[#131B2E] border border-slate-800 rounded-2xl max-w-2xl w-full p-6 space-y-5 shadow-2xl relative max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-800 pb-3 shrink-0">
          <div className="flex items-center space-x-3">
            <div className="p-2 bg-cyan-500/10 rounded-xl text-cyan-400 border border-cyan-500/20">
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </div>
            <div>
              <h3 className="text-base font-bold text-white">System Guide & Documentation</h3>
              <p className="text-xs text-slate-400">Everything you need to know about BugTracker AI</p>
            </div>
          </div>

          <button
            onClick={() => setIsHelpOpen(false)}
            className="text-slate-400 hover:text-white p-1 rounded-lg hover:bg-slate-800 transition-colors cursor-pointer"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Scrollable Content */}
        <div className="space-y-4 overflow-y-auto pr-2 text-xs text-slate-300 flex-1">
          {/* Section 1: Scanning */}
          <div className="bg-[#0B0F17] border border-slate-800/80 rounded-xl p-4 space-y-2">
            <h4 className="font-bold text-white text-sm flex items-center gap-2">
              <span className="text-cyan-400">1.</span> Repository Scanning (Tab 1)
            </h4>
            <p className="text-slate-400 leading-relaxed">
              Enter any public GitHub repository link (or choose from recent scan presets) and click <strong>"Analyze Repository"</strong>. Alternatively, drop a project <code>.ZIP</code> archive directly into the upload area. The system dispatches a request to <code>POST /api/v1/repositories/clone</code> or <code>POST /api/v1/repositories/upload</code>.
            </p>
          </div>

          {/* Section 2: AI Codebase Architecture */}
          <div className="bg-[#0B0F17] border border-slate-800/80 rounded-xl p-4 space-y-2">
            <h4 className="font-bold text-white text-sm flex items-center gap-2">
              <span className="text-cyan-400">2.</span> AI Architecture & File Inspection (Tab 2)
            </h4>
            <p className="text-slate-400 leading-relaxed">
              Reviews high-level system intent, auto-detected technology stacks, key subsystem components, and potential architectural risks from <code>GET /api/v1/repositories/:id/architecture</code>. Use the <strong>real-time search bar</strong> in Tab 2 to dynamically filter files by role, language, or risk status.
            </p>
          </div>

          {/* Section 3: Bug Management & Code Diffs */}
          <div className="bg-[#0B0F17] border border-slate-800/80 rounded-xl p-4 space-y-2">
            <h4 className="font-bold text-white text-sm flex items-center gap-2">
              <span className="text-cyan-400">3.</span> Bug Triage & Debounced Remarks (Tab 3)
            </h4>
            <p className="text-slate-400 leading-relaxed">
              Click any bug in the list to open the <strong>Bug Inspector Drawer</strong>. You can review vulnerable code lines, why the issue matters, and inspect suggested fix diffs.
            </p>
            <p className="text-slate-400 leading-relaxed">
              Engineer Remarks written into the textarea update the shared state immediately (so Tab 4 updates in real time) and dispatch a debounced request (500ms) to <code>PATCH /api/v1/candidate-issues/:id/notes</code>.
            </p>
          </div>

          {/* Section 4: Resolution & PDF Reports */}
          <div className="bg-[#0B0F17] border border-slate-800/80 rounded-xl p-4 space-y-2">
            <h4 className="font-bold text-white text-sm flex items-center gap-2">
              <span className="text-cyan-400">4.</span> Executive PDF & Multi-Format Audit Reports (Tab 4)
            </h4>
            <p className="text-slate-400 leading-relaxed">
              Tab 4 aggregates resolved vs open issue metrics, severity distribution, and engineer remarks from Tab 3. Click <strong>"Export PDF"</strong> (or CSV/JSON/MD/HTML) to generate server-side certified reports via <code>GET /api/v1/repositories/export/:id</code>, or use browser print.
            </p>
          </div>

          {/* Section 5: Live vs Demo Mode */}
          <div className="bg-[#0B0F17] border border-slate-800/80 rounded-xl p-4 space-y-2">
            <h4 className="font-bold text-white text-sm flex items-center gap-2">
              <span className="text-cyan-400">5.</span> FastAPI Integration & Live Database Persistence
            </h4>
            <p className="text-slate-400 leading-relaxed">
              All data fetching connects to your FastAPI backend on <code>http://localhost:8000/api/v1</code>. The header displays 🟢 <strong>Live data</strong> when connected to PostgreSQL.
            </p>
          </div>
        </div>

        {/* Footer */}
        <div className="flex justify-end pt-2 border-t border-slate-800 shrink-0">
          <button
            onClick={() => setIsHelpOpen(false)}
            className="bg-cyan-400 hover:bg-cyan-300 text-slate-950 font-bold px-5 py-2 rounded-lg text-xs transition-colors cursor-pointer"
          >
            Got it, close guide
          </button>
        </div>
      </div>
    </div>
  );
}
