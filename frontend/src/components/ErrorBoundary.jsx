// src/components/ErrorBoundary.jsx - Global React Error Boundary
import React from "react";

export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null, errorInfo: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    console.error("ErrorBoundary caught an unhandled error:", error, errorInfo);
    this.setState({ errorInfo });
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="p-8 max-w-3xl mx-auto my-12 bg-[#131B2E] border border-red-500/30 rounded-2xl shadow-2xl space-y-4">
          <div className="flex items-center space-x-3">
            <span className="p-2 bg-red-500/20 text-red-400 rounded-xl text-lg">⚠️</span>
            <div>
              <h2 className="text-lg font-bold text-white">Something went wrong rendering this view</h2>
              <p className="text-xs text-slate-400">
                An unexpected interface error occurred. You can reload or reset your view below.
              </p>
            </div>
          </div>

          <div className="p-3 bg-[#0B0F17] rounded-xl border border-slate-800 text-xs font-mono text-red-300 overflow-x-auto">
            {this.state.error?.toString() || "Unknown error"}
          </div>

          <div className="flex items-center space-x-3 pt-2">
            <button
              onClick={() => {
                this.setState({ hasError: false, error: null });
                window.location.reload();
              }}
              className="px-4 py-2 bg-cyan-500 hover:bg-cyan-400 text-slate-950 font-bold rounded-xl text-xs transition-colors cursor-pointer"
            >
              ⟳ Reload Application
            </button>
            <button
              onClick={() => this.setState({ hasError: false, error: null })}
              className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 font-semibold rounded-xl text-xs transition-colors cursor-pointer"
            >
              Try Again
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
