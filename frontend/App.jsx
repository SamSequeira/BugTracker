// src/App.jsx
import React, { useState } from "react";
import RepositoryUpload from "./upload/RepositoryUpload";
import BugTrackerDashboard from "./dashboard/BugTrackerDashboard";

export default function App() {
  const [currentPage, setCurrentPage] = useState("upload"); // 'upload' or 'dashboard'

  return (
    <div>
      {currentPage === "upload" ? (
        <RepositoryUpload onScanComplete={() => setCurrentPage("dashboard")} />
      ) : (
        <div>
          {/* Top banner allowing easy navigation back */}
          <div className="bg-[#0F1623] border-b border-slate-800 px-6 py-2 flex justify-between items-center text-xs text-slate-400">
            <span>Repository Context: <strong>your-repo (main)</strong></span>
            <button
              onClick={() => setCurrentPage("upload")}
              className="text-cyan-400 hover:underline flex items-center gap-1 font-medium"
            >
              &larr; Upload / Scan Another Repository
            </button>
          </div>

          <BugTrackerDashboard />
        </div>
      )}
    </div>
  );
}
