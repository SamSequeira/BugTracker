/*
// src/App.jsx - Main Application Container & Route Guard
import React from "react";
import { BugTrackerProvider, useBugTracker } from "./useBugTracker.jsx";
import AuthScreen from "./components/Auth/AuthScreen.jsx";
import Sidebar from "./components/Layout/Sidebar.jsx";
import Header from "./components/Layout/Header.jsx";
import UserMenuModal from "./components/Layout/UserMenuModal.jsx";
import TabRepositoryScanner from "./components/Tabs/TabRepositoryScanner.jsx";
import TabAiArchitecture from "./components/Tabs/TabAiArchitecture.jsx";
import TabBugManagement from "./components/Tabs/TabBugManagement.jsx";
import TabReports from "./components/Tabs/TabReports.jsx";
import SettingsModal from "./components/Modals/SettingsModal.jsx";
import HelpModal from "./components/Modals/HelpModal.jsx";
import GlobalSearchModal from "./components/Modals/GlobalSearchModal.jsx";
import NotificationDrawer from "./components/Modals/NotificationDrawer.jsx";
import BugDetailsDrawer from "./components/Modals/BugDetailsDrawer.jsx";

function AppContent() {
  const { isAuthenticated, activeTab, isUserMenuOpen, setIsUserMenuOpen } = useBugTracker();

  // 1. Unauthenticated State: Show Login / Signup Screen
  if (!isAuthenticated) {
    return <AuthScreen />;
  }

  // 2. Authenticated Protected Dashboard
  return (
    <div className="flex min-h-screen bg-[#0B0F17] text-slate-200 antialiased font-sans select-text">
      {/* Fixed Left Navigation Bar * /}
      <Sidebar />

      {/* Main App Container * /}
      <div className="flex-1 flex flex-col min-w-0 overflow-x-hidden">
        {/* Sticky Header * /}
        <Header />

        {/* Dynamic Viewport Content * /}
        <main className="flex-1 p-4 sm:p-6 lg:p-8 overflow-y-auto">
          {activeTab === "scanner" && <TabRepositoryScanner />}
          {activeTab === "ai" && <TabAiArchitecture />}
          {activeTab === "bugs" && <TabBugManagement />}
          {activeTab === "reports" && <TabReports />}
        </main>
      </div>

      {/* Global Application Modals & Drawers * /}
      <SettingsModal />
      <HelpModal />
      <GlobalSearchModal />
      <NotificationDrawer />
      <BugDetailsDrawer />
      <UserMenuModal
        isOpen={isUserMenuOpen}
        onClose={() => setIsUserMenuOpen(false)}
      />
    </div>
  );
}

export default function App() {
  return (
    <BugTrackerProvider>
      <AppContent />
    </BugTrackerProvider>
  );
}
*/

// src/App.jsx - Main Application Container & Route Guard
import React from "react";
import { BugTrackerProvider, useBugTracker } from "./useBugTracker.jsx";
import AuthScreen from "./components/Auth/AuthScreen.jsx";
import Sidebar from "./components/Layout/Sidebar.jsx";
import Header from "./components/Layout/Header.jsx";
import UserMenuModal from "./components/Layout/UserMenuModal.jsx";
import TabRepositoryScanner from "./components/Tabs/TabRepositoryScanner.jsx";
import TabAiArchitecture from "./components/Tabs/TabAiArchitecture.jsx";
import TabBugManagement from "./components/Tabs/TabBugManagement.jsx";
import TabReports from "./components/Tabs/TabReports.jsx";
import ReviewDashboard from "./pages/TemporaryReviewDashboard/ReviewDashboard.jsx";
import SettingsModal from "./components/Modals/SettingsModal.jsx";
import HelpModal from "./components/Modals/HelpModal.jsx";
import GlobalSearchModal from "./components/Modals/GlobalSearchModal.jsx";
import NotificationDrawer from "./components/Modals/NotificationDrawer.jsx";
import BugDetailsDrawer from "./components/Modals/BugDetailsDrawer.jsx";

function AppContent() {
  const { isAuthenticated, activeTab, setActiveTab, isUserMenuOpen, setIsUserMenuOpen } = useBugTracker();

  // Allow direct standalone access to temporary review tool via URL (/review or #review)
  const isDirectReviewRoute = window.location.pathname === "/review" || window.location.hash === "#review" || window.location.hash === "#/review";

  React.useEffect(() => {
    if (isDirectReviewRoute && activeTab !== "review") {
      setActiveTab("review");
    }
  }, [isDirectReviewRoute, activeTab, setActiveTab]);

  // 1. Direct Review Route (bypass auth for temporary review tool convenience)
  if (isDirectReviewRoute || activeTab === "review") {
    return (
      <div className="flex min-h-screen bg-[#0B0F17] text-slate-200 antialiased font-sans select-text">
        <Sidebar />
        <div className="flex-1 flex flex-col min-w-0 overflow-x-hidden">
          <Header />
          <main className="flex-1 p-4 sm:p-6 lg:p-8 overflow-y-auto">
            <ReviewDashboard />
          </main>
        </div>
        <SettingsModal />
        <HelpModal />
        <GlobalSearchModal />
        <NotificationDrawer />
        <BugDetailsDrawer />
        <UserMenuModal
          isOpen={isUserMenuOpen}
          onClose={() => setIsUserMenuOpen(false)}
        />
      </div>
    );
  }

  // 2. Unauthenticated State: Show Login / Signup Screen
  if (!isAuthenticated) {
    return <AuthScreen />;
  }

  // 3. Authenticated Protected Dashboard
  return (
    <div className="flex min-h-screen bg-[#0B0F17] text-slate-200 antialiased font-sans select-text">
      {/* Fixed Left Navigation Bar */}
      <Sidebar />

      {/* Main App Container */}
      <div className="flex-1 flex flex-col min-w-0 overflow-x-hidden">
        {/* Sticky Header */}
        <Header />

        {/* Dynamic Viewport Content */}
        <main className="flex-1 p-4 sm:p-6 lg:p-8 overflow-y-auto">
          {activeTab === "scanner" && <TabRepositoryScanner />}
          {activeTab === "ai" && <TabAiArchitecture />}
          {activeTab === "bugs" && <TabBugManagement />}
          {activeTab === "reports" && <TabReports />}
          {activeTab === "review" && <ReviewDashboard />}
        </main>
      </div>

      {/* Global Application Modals & Drawers */}
      <SettingsModal />
      <HelpModal />
      <GlobalSearchModal />
      <NotificationDrawer />
      <BugDetailsDrawer />
      <UserMenuModal
        isOpen={isUserMenuOpen}
        onClose={() => setIsUserMenuOpen(false)}
      />
    </div>
  );
}

export default function App() {
  return (
    <BugTrackerProvider>
      <AppContent />
    </BugTrackerProvider>
  );
}
