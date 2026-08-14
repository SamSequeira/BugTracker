# AI Bug Tracking & Prioritization System — Frontend UI/UX

This directory contains the multi-page frontend UI for the **AI Bug Tracking & Prioritization System**. It provides a real-time, dark-themed interactive experience spanning a dedicated repository upload interface and an analytical security dashboard.

---

## 📁 Repository Structure

```text
BugTracker/
├── backend/                      # FastAPI backend service (Python)
└── frontend/                     # UI components & pages
    ├── App.jsx                   # Main application component & routing
    ├── BugTrackerDashboard.jsx   # Page 2: Interactive bug dashboard
    ├── RepositoryUpload.jsx      # Page 1: Standalone upload & scan page
    ├── index.html                # Standalone browser entry point
    └── README.md                 # Frontend documentation
🛠️ Tech Stack & Dependencies
UI Framework: React 18

Styling: Tailwind CSS (Custom Dark Palette #0B0F17)

Icons: Lucide React / Lucide Web Icons

State Management: React Hooks (useState, useEffect)

🚀 Page Features & UI Components
Page 1: Repository Upload Page (RepositoryUpload.jsx)
Dedicated Entry Point: Standalone landing screen for starting a repository scan.

Dual Upload Options: GitHub repository URL input field or drag-and-drop .ZIP archive box (up to 500MB).

Scan Status Tracker: Simulated scanning progress bar and status checks before redirecting to the main dashboard.

Recent Scans Access: Quick-selection list for previously scanned projects.

Page 2: Bug Tracker Dashboard (BugTrackerDashboard.jsx)
1. Header & Navigation Shell
System Title & Branding: Displays the engine capabilities (AST, Static Analysis, NLP & Similarity Search).

Live Threat Badge: Pulsing indicator showing real-time critical bug counts (8 critical issues).

Header Actions: Global search, unread notification counter (3), and user profile avatar (AD).

Sidebar Menu: Icon navigation for switching between Code Analysis, Bug Tracking, Analytics, Git Branches, and Settings.

2. Repository Scanner & Engine
Dual Input Modes: Analyze code via a public GitHub Repository link or drag-and-drop a .ZIP archive (up to 500MB).

Live Pipeline Tracker: Real-time progress bar (67% completion) with step-by-step indicators (Reading code, Detecting languages, Checking for problems, Preparing report).

Recent Scans History: Clickable quick-access pills showing recent repository scans, execution dates, and primary status tags.

3. Key Metrics (KPI Summary Cards)
Overview metrics summarizing repository code health:

Total Bugs: 128 across 2,843 scanned files.

Critical (P1): 8 immediate security/system risks.

High (P2): 32 major vulnerabilities needing fix within the week.

Medium (P3): 54 backlog functional/performance issues.

Low (P4): 34 code quality or non-urgent warnings.

4. Visual Analytics & Priority Breakdown
Issues by Severity: Color-coded distribution bar detailing Critical (6.3%), High (25.0%), Medium (42.2%), and Low (26.6%) ratios.

Priority SLA Breakdown: Categorizes issue resolution targets:

P1 • Fix now (18 issues / 14.1%)

P2 • Fix this week (38 issues / 29.7%)

P3 • Backlog (46 issues / 35.9%)

P4 • Low urgency (26 issues / 20.3%)

5. Filterable Bug Table & AI Code Inspector
Search & Severity Badges: Live search bar by title or file name with severity quick-filters (All, Critical, High, Medium, Low).

Detailed Issue Table: Lists Bug ID, Title, Severity, Priority, File & Line Number, Status (Open / In Review), and Similar Duplicate counts.

Expandable Code Inspector Drawer (Click any row):

Code Snippet Viewer: Highlighted syntax viewer marking vulnerable lines in red.

AI Analysis: Explains What's wrong and Why it matters.

Suggested Fix Diff Box: Git-style diff box showing exact lines to remove (-) and replacement fix code (+).

Quick Actions: Mark as Resolved, Ignore this issue, and Copy code location.

6. Accordions & Context Footer
Category Drawers: Expandable accordion panels for Recently Found Issues and Repeated/Similar Issues.

Status Footer: Persistent bar showing active repository (your-repo), visibility (Public), active branch (main), total files (2,843), total LOC (128,742), and scan timestamp.
