// src/components/Modals/SettingsModal.jsx - Backend URL & Connection Settings
import React, { useState } from "react";
import { useBugTracker } from "../../useBugTracker.jsx";
import { apiService } from "../../api.js";

export default function SettingsModal() {
  const { isSettingsOpen, setIsSettingsOpen, apiUrl, updateApiUrl, isLive, sessionUser } = useBugTracker();

  const [inputUrl, setInputUrl] = useState(apiUrl);
  const [testResult, setTestResult] = useState(null);
  const [isTesting, setIsTesting] = useState(false);
  const [saveMessage, setSaveMessage] = useState("");

  if (!isSettingsOpen) return null;

  const handleTestConnection = async () => {
    setIsTesting(true);
    setTestResult(null);
    setSaveMessage("");

    try {
      const res = await apiService.testConnection(inputUrl);
      if (res.success) {
        setTestResult({
          type: "success",
          message: `Backend reachable! (HTTP ${res.status || 200})`,
        });
      } else {
        setTestResult({
          type: "error",
          message: `Backend unreachable at this URL. ${res.error || "Connection timed out."}`,
        });
      }
    } catch (err) {
      setTestResult({
        type: "error",
        message: "Failed to connect to specified endpoint.",
      });
    } finally {
      setIsTesting(false);
    }
  };

  const handleSave = async (e) => {
    e.preventDefault();
    if (!inputUrl.trim()) return;

    await updateApiUrl(inputUrl.trim());
    setSaveMessage("Settings saved! Future requests will target this URL.");
    setTimeout(() => {
      setSaveMessage("");
      setIsSettingsOpen(false);
    }, 1200);
  };

  const handleResetDefault = () => {
    setInputUrl("http://localhost:8000/api");
    setTestResult(null);
    setSaveMessage("");
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-xs animate-fade-in">
      <div className="bg-[#131B2E] border border-slate-800 rounded-2xl max-w-lg w-full p-6 space-y-5 shadow-2xl relative">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-800 pb-3">
          <div className="flex items-center space-x-3">
            <div className="p-2 bg-cyan-500/10 rounded-xl text-cyan-400 border border-cyan-500/20">
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
              </svg>
            </div>
            <div>
              <h3 className="text-base font-bold text-white">Application Settings</h3>
              <p className="text-xs text-slate-400">Configure FastAPI backend target and runtime data mode</p>
            </div>
          </div>

          <button
            onClick={() => setIsSettingsOpen(false)}
            className="text-slate-400 hover:text-white p-1 rounded-lg hover:bg-slate-800 transition-colors"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Current Connection Status Pill */}
        <div className="bg-[#0B0F17] border border-slate-800 rounded-xl p-3.5 flex items-center justify-between">
          <div className="flex items-center space-x-2.5">
            <span className={`w-2.5 h-2.5 rounded-full ${isLive ? "bg-emerald-400 animate-pulse" : "bg-amber-400"}`}></span>
            <div>
              <div className="text-xs font-semibold text-white">
                {isLive ? "🟢 Live Data Mode Active" : "🟠 Demo Data Fallback Active"}
              </div>
              <div className="text-[11px] text-slate-400">
                {isLive
                  ? "Connected to active FastAPI server. Real requests in use."
                  : "Backend offline or unreachable. Using realistic local demo dataset with 4s timeout."}
              </div>
            </div>
          </div>
        </div>

        {/* Form */}
        <form onSubmit={handleSave} className="space-y-4">
          <div>
            <div className="flex items-center justify-between mb-1.5">
              <label className="text-xs font-semibold text-slate-300">
                FastAPI Backend Base URL
              </label>
              <button
                type="button"
                onClick={handleResetDefault}
                className="text-[11px] text-cyan-400 hover:underline"
              >
                Reset to Default
              </button>
            </div>
            <div className="flex gap-2">
              <input
                type="url"
                required
                value={inputUrl}
                onChange={(e) => {
                  setInputUrl(e.target.value);
                  setTestResult(null);
                }}
                placeholder="http://localhost:8000/api"
                className="flex-1 bg-[#0B0F17] border border-slate-700 rounded-lg px-3.5 py-2 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-cyan-400 font-mono transition-colors"
              />
              <button
                type="button"
                onClick={handleTestConnection}
                disabled={isTesting}
                className="bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 px-3 py-2 rounded-lg text-xs font-semibold transition-colors shrink-0 flex items-center gap-1.5 disabled:opacity-60"
              >
                {isTesting ? (
                  <div className="w-3.5 h-3.5 border-2 border-cyan-400 border-t-transparent rounded-full animate-spin"></div>
                ) : (
                  <span>Ping</span>
                )}
              </button>
            </div>
            <p className="text-[11px] text-slate-500 mt-1.5">
              Default: <code className="text-cyan-300">http://localhost:8000/api</code>. Applies immediately to subsequent API calls.
            </p>
          </div>

          {/* Test connection alert result */}
          {testResult && (
            <div
              className={`p-3 rounded-xl text-xs flex items-center gap-2 animate-fade-in ${
                testResult.type === "success"
                  ? "bg-emerald-500/10 text-emerald-300 border border-emerald-500/30"
                  : "bg-amber-500/10 text-amber-300 border border-amber-500/30"
              }`}
            >
              <span>{testResult.type === "success" ? "✓" : "⚠️"}</span>
              <span>{testResult.message}</span>
            </div>
          )}

          {saveMessage && (
            <div className="bg-cyan-500/10 text-cyan-300 border border-cyan-500/30 p-2.5 rounded-xl text-xs flex items-center gap-2 animate-fade-in">
              <span>✓</span>
              <span>{saveMessage}</span>
            </div>
          )}

          {/* User Session Info */}
          <div className="bg-[#0B0F17] border border-slate-800/80 rounded-xl p-3 text-xs space-y-1">
            <div className="text-slate-400 font-medium">Logged-in Engineer:</div>
            <div className="text-white font-mono">{sessionUser?.name} ({sessionUser?.email})</div>
          </div>

          {/* Buttons */}
          <div className="flex items-center justify-end space-x-2 pt-2 border-t border-slate-800">
            <button
              type="button"
              onClick={() => setIsSettingsOpen(false)}
              className="px-4 py-2 rounded-lg text-xs font-medium text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              className="bg-cyan-400 hover:bg-cyan-300 text-slate-950 font-bold px-4 py-2 rounded-lg text-xs transition-colors shadow-lg shadow-cyan-500/10"
            >
              Save Changes
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
