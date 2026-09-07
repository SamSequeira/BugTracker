/*
// src/api.js - Central Data Access Layer for BugTracker
// Manages backend requests, 4s AbortController timeout, live/demo state, caching, and graceful fallbacks.

import { DEFAULT_STATS, DEFAULT_BUGS, DEFAULT_AI_SUMMARY } from "./mockData.js";
import { fetchGitHubRepo, parseGitHubUrl, RepoAccessError, setGitHubToken, getGitHubToken } from "./github.js";

const DEFAULT_API_URL = "http://localhost:8000/api/v1";
const TIMEOUT_MS = 4000;

class ApiService {
  constructor() {
    const savedBaseUrl = sessionStorage.getItem("bugtracker_api_url");
    this.baseUrl = savedBaseUrl === "http://localhost:8000/api"
      ? DEFAULT_API_URL
      : (savedBaseUrl || DEFAULT_API_URL);
    this.isLive = false;
    this.token = sessionStorage.getItem("bugtracker_auth_token") || null;
    this.cache = {};
    this.statusListeners = new Set();
  }

  // Register live/demo status change listener
  onStatusChange(listener) {
    this.statusListeners.add(listener);
    return () => this.statusListeners.delete(listener);
  }

  notifyStatus(live) {
    this.isLive = live;
    this.statusListeners.forEach((fn) => fn(live));
  }

  getBaseUrl() {
    return this.baseUrl;
  }

  setBaseUrl(url) {
    if (!url) return;
    this.baseUrl = url.trim().replace(/\/+$/, "");
    sessionStorage.setItem("bugtracker_api_url", this.baseUrl);
    this.cache = {}; // Invalidate cache when changing backend target
  }

  setToken(token) {
    this.token = token;
    if (token) {
      sessionStorage.setItem("bugtracker_auth_token", token);
    } else {
      sessionStorage.removeItem("bugtracker_auth_token");
    }
  }

  getToken() {
    return this.token || sessionStorage.getItem("bugtracker_auth_token");
  }

  // Core fetch wrapper with 4-second AbortController timeout
  async request(endpoint, options = {}, timeoutMs = TIMEOUT_MS) {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

    const headers = {
      ...(options.headers || {}),
    };

    // Attach auth token if available
    const token = this.getToken();
    if (token && !headers["Authorization"]) {
      headers["Authorization"] = `Bearer ${token}`;
    }

    // Default to JSON headers unless FormData is passed
    if (!(options.body instanceof FormData) && !headers["Content-Type"]) {
      headers["Content-Type"] = "application/json";
    }

    try {
      const response = await fetch(`${this.baseUrl}${endpoint}`, {
        ...options,
        headers,
        signal: controller.signal,
      });

      clearTimeout(timeoutId);

      if (!response.ok) {
        throw new Error(`HTTP Error ${response.status}: ${response.statusText}`);
      }

      this.notifyStatus(true);
      return await response.json();
    } catch (err) {
      clearTimeout(timeoutId);
      this.notifyStatus(false);
      throw err;
    }
  }

  // Set/get GitHub Personal Access Token for private repo scanning
  setGitHubToken(token) {
    setGitHubToken(token);
  }

  getGitHubToken() {
    return getGitHubToken();
  }

  // Quick test connection helper for Settings Modal
  async testConnection(url) {
    const targetUrl = (url || this.baseUrl).replace(/\/+$/, "");
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 3000);

    try {
      const res = await fetch(`${targetUrl}/dashboard-stats`, {
        signal: controller.signal,
      });
      clearTimeout(timeoutId);
      return { success: res.ok, status: res.status };
    } catch (err) {
      clearTimeout(timeoutId);
      return { success: false, error: err.message };
    }
  }

  // =========================================================================
  // 1. AUTHENTICATION ENDPOINTS (Backend-Ready with Realistic Fallback)
  // =========================================================================

  // POST /api/auth/login
  async login(email, password) {
    try {
      const res = await this.request("/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });
      const token = res.access_token || res.token || "demo-jwt-token-xyz";
      this.setToken(token);
      return {
        success: true,
        live: true,
        user: res.user || {
          id: "usr-live-01",
          name: res.name || email.split("@")[0],
          email: email,
          initials: (res.name || email).substring(0, 2).toUpperCase(),
          role: "Security Engineer",
        },
      };
    } catch (err) {
      throw err;
      // Graceful demo login fallback
      const token = "demo-session-token-" + Date.now();
      this.setToken(token);
      const namePart = email.split("@")[0].replace(/[^a-zA-Z0-9]/g, " ");
      const formattedName =
        namePart.charAt(0).toUpperCase() + namePart.slice(1) || "Alex Mercer";
      return {
        success: true,
        live: false,
        user: {
          id: "usr-demo-01",
          name: formattedName,
          email: email,
          initials: formattedName.substring(0, 2).toUpperCase(),
          role: "Lead Security Engineer",
        },
      };
    }
  }

  // POST /api/auth/signup
  async signup(name, email, password) {
    try {
      const res = await this.request("/auth/signup", {
        method: "POST",
        body: JSON.stringify({ name, email, password }),
      });
      const token = res.access_token || res.token || "demo-jwt-token-xyz";
      this.setToken(token);
      return {
        success: true,
        live: true,
        user: res.user || {
          id: "usr-live-" + Date.now(),
          name: name,
          email: email,
          initials: name.substring(0, 2).toUpperCase(),
          role: "Security Engineer",
        },
      };
    } catch (err) {
      const token = "demo-session-token-" + Date.now();
      this.setToken(token);
      return {
        success: true,
        live: false,
        user: {
          id: "usr-demo-" + Date.now(),
          name: name,
          email: email,
          initials: name.substring(0, 2).toUpperCase(),
          role: "Security Engineer",
        },
      };
    }
  }

  // GET /api/auth/me
  async getCurrentUser() {
    try {
      const res = await this.request("/auth/me");
      return { success: true, live: true, user: res };
    } catch (err) {
      return { success: false, live: false, user: null };
    }
  }

  // POST /api/auth/logout
  async logout() {
    try {
      await this.request("/auth/logout", { method: "POST" });
    } catch (err) {
      // Non-critical if offline
    } finally {
      this.setToken(null);
    }
  }

  // =========================================================================
  // 2. REPOSITORY & SCAN ENDPOINTS
  // =========================================================================

  // Scan a GitHub URL directly via the GitHub public API (no backend needed)
  // Returns { success, live, data: { aiSummary, stats } } or throws RepoAccessError
  async scanGitHubRepo(repoUrl) {
    // fetchGitHubRepo throws RepoAccessError for private/invalid repos — let it bubble up
    const result = await fetchGitHubRepo(repoUrl);
    return {
      success: true,
      live: true,
      data: {
        aiSummary: result.aiSummary,
        stats: result.stats,
        repoMeta: {
          name: result.repoData.name,
          fullName: result.repoData.full_name,
          description: result.repoData.description,
          stars: result.repoData.stargazers_count,
          forks: result.repoData.forks_count,
          openIssues: result.repoData.open_issues_count,
          defaultBranch: result.repoData.default_branch,
          pushedAt: result.repoData.pushed_at,
          languages: result.languages,
          totalFiles: result.totalFiles,
          owner: result.owner,
          repo: result.repo,
        },
      },
    };
  }

  // POST /api/scan (backend path — kept as fallback for ZIP uploads)
  async startScan(payload, isFile = false) {
    try {
      const options = isFile
        ? { method: "POST", body: payload }
        : {
          method: "POST",
          body: JSON.stringify(payload),
        };
      const data = await this.request("/scan", options);
      return { success: true, live: true, data };
    } catch (err) {
      console.warn("Backend /api/scan unreachable:", err.message);
      return {
        success: false,
        live: false,
        data: null,
      };
    }
  }

  // =========================================================================
  // 3. DASHBOARD STATS
  // =========================================================================

  // GET /api/dashboard-stats
  async getDashboardStats() {
    try {
      const data = await this.request("/dashboard-stats");
      this.cache["stats"] = data;
      return { live: true, data };
    } catch (err) {
      return { live: false, data: this.cache["stats"] || DEFAULT_STATS };
    }
  }

  // =========================================================================
  // 4. BUGS MANAGEMENT
  // =========================================================================

  // GET /api/bugs
  async getBugs() {
    try {
      const data = await this.request("/bugs");
      this.cache["bugs"] = data;
      return { live: true, data };
    } catch (err) {
      return { live: false, data: this.cache["bugs"] || DEFAULT_BUGS };
    }
  }

  // PATCH /api/bugs/{id}/resolve
  async resolveBug(bugId, nextStatus) {
    try {
      const data = await this.request(`/bugs/${bugId}/resolve`, {
        method: "PATCH",
        body: JSON.stringify({ status: nextStatus }),
      });
      return { live: true, data };
    } catch (err) {
      console.warn(`Local resolve applied for ${bugId} (Demo fallback)`);
      return { live: false, data: { id: bugId, status: nextStatus, optimistic: true } };
    }
  }

  // PATCH /api/bugs/{id}/notes
  async updateBugNotes(bugId, remarks) {
    try {
      const data = await this.request(`/bugs/${bugId}/notes`, {
        method: "PATCH",
        body: JSON.stringify({ remarks, engineerNotes: remarks }),
      });
      return { live: true, data };
    } catch (err) {
      console.warn(`Local remarks saved for ${bugId} (Demo fallback)`);
      return { live: false, data: { id: bugId, remarks, engineerNotes: remarks, optimistic: true } };
    }
  }

  // =========================================================================
  // 5. AI ARCHITECTURE SUMMARY
  // =========================================================================

  // GET /api/ai-summary
  async getAiSummary() {
    try {
      const data = await this.request("/ai-summary");
      this.cache["ai-summary"] = data;
      return { live: true, data };
    } catch (err) {
      return { live: false, data: this.cache["ai-summary"] || DEFAULT_AI_SUMMARY };
    }
  }

  // =========================================================================
  // 6. ARCHITECTURE & TOPOLOGY
  // =========================================================================

  // GET /api/v1/repositories/
  // Returns all repositories ordered newest-first: [{ id, name, created_at, ... }]
  // Used as a temporary fallback when currentRepositoryId is not yet set in state.
  async getRepositories() {
    try {
      const data = await this.request("/v1/repositories/");
      return { live: true, data: Array.isArray(data) ? data : [] };
    } catch (err) {
      return { live: false, data: [] };
    }
  }

  // GET /api/v1/repositories/{repositoryId}/architecture
  // Returns the persisted Architecture & Topology data for the latest completed
  // analysis run belonging to this specific repository. Never triggers analysis.
  async getRepositoryArchitecture(repositoryId) {
    if (!repositoryId) return { live: false, data: null, error: "No repository ID" };
    try {
      const data = await this.request(`/v1/repositories/${repositoryId}/architecture`);
      return { live: true, data };
    } catch (err) {
      const status = err.message?.match(/HTTP Error (\d+)/)?.[1];
      return { live: false, data: null, error: err.message, status: status ? parseInt(status) : null };
    }
  }
}

export const apiService = new ApiService();
*/

// src/api.js - Central Data Access Layer for BugTracker
// Manages backend requests, 4s AbortController timeout, live/demo state, caching, and graceful fallbacks.

import { DEFAULT_STATS, DEFAULT_BUGS, DEFAULT_AI_SUMMARY } from "./mockData.js";
import { fetchGitHubRepo, parseGitHubUrl, RepoAccessError, setGitHubToken, getGitHubToken } from "./github.js";

const DEFAULT_API_URL = "http://localhost:8000/api/v1";
const TIMEOUT_MS = 4000;

class ApiService {
  constructor() {
    const savedBaseUrl = sessionStorage.getItem("bugtracker_api_url");
    this.baseUrl = savedBaseUrl === "http://localhost:8000/api"
      ? DEFAULT_API_URL
      : (savedBaseUrl || DEFAULT_API_URL);
    this.isLive = false;
    this.token = sessionStorage.getItem("bugtracker_auth_token") || null;
    this.cache = {};
    this.statusListeners = new Set();
  }

  // Register live/demo status change listener
  onStatusChange(listener) {
    this.statusListeners.add(listener);
    return () => this.statusListeners.delete(listener);
  }

  notifyStatus(live) {
    this.isLive = live;
    this.statusListeners.forEach((fn) => fn(live));
  }

  getBaseUrl() {
    return this.baseUrl;
  }

  setBaseUrl(url) {
    if (!url) return;
    this.baseUrl = url.trim().replace(/\/+$/, "");
    sessionStorage.setItem("bugtracker_api_url", this.baseUrl);
    this.cache = {}; // Invalidate cache when changing backend target
  }

  setToken(token) {
    this.token = token;
    if (token) {
      sessionStorage.setItem("bugtracker_auth_token", token);
    } else {
      sessionStorage.removeItem("bugtracker_auth_token");
    }
  }

  getToken() {
    return this.token || sessionStorage.getItem("bugtracker_auth_token");
  }

  // Core fetch wrapper with 4-second AbortController timeout
  async request(endpoint, options = {}, timeoutMs = TIMEOUT_MS) {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

    const headers = {
      ...(options.headers || {}),
    };

    // Attach auth token if available
    const token = this.getToken();
    if (token && !headers["Authorization"]) {
      headers["Authorization"] = `Bearer ${token}`;
    }

    // Default to JSON headers unless FormData is passed
    if (!(options.body instanceof FormData) && !headers["Content-Type"]) {
      headers["Content-Type"] = "application/json";
    }

    try {
      const response = await fetch(`${this.baseUrl}${endpoint}`, {
        ...options,
        headers,
        signal: controller.signal,
      });

      clearTimeout(timeoutId);

      if (!response.ok) {
        throw new Error(`HTTP Error ${response.status}: ${response.statusText}`);
      }

      this.notifyStatus(true);
      return await response.json();
    } catch (err) {
      clearTimeout(timeoutId);
      this.notifyStatus(false);
      throw err;
    }
  }

  // Set/get GitHub Personal Access Token for private repo scanning
  setGitHubToken(token) {
    setGitHubToken(token);
  }

  getGitHubToken() {
    return getGitHubToken();
  }

  // Quick test connection helper for Settings Modal
  async testConnection(url) {
    const targetUrl = (url || this.baseUrl).replace(/\/+$/, "");
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 3000);

    try {
      const res = await fetch(`${targetUrl}/dashboard-stats`, {
        signal: controller.signal,
      });
      clearTimeout(timeoutId);
      return { success: res.ok, status: res.status };
    } catch (err) {
      clearTimeout(timeoutId);
      return { success: false, error: err.message };
    }
  }

  // =========================================================================
  // 1. AUTHENTICATION ENDPOINTS (Backend-Ready with Realistic Fallback)
  // =========================================================================

  // POST /api/auth/login
  async login(email, password) {
    try {
      const res = await this.request("/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });
      const token = res.access_token || res.token || "demo-jwt-token-xyz";
      this.setToken(token);
      return {
        success: true,
        live: true,
        user: res.user || {
          id: "usr-live-01",
          name: res.name || email.split("@")[0],
          email: email,
          initials: (res.name || email).substring(0, 2).toUpperCase(),
          role: "Security Engineer",
        },
      };
    } catch (err) {
      throw err;
      // Graceful demo login fallback
      throw err;
      const token = "demo-session-token-" + Date.now();
      this.setToken(token);
      const namePart = email.split("@")[0].replace(/[^a-zA-Z0-9]/g, " ");
      const formattedName =
        namePart.charAt(0).toUpperCase() + namePart.slice(1) || "Alex Mercer";
      return {
        success: true,
        live: false,
        user: {
          id: "usr-demo-01",
          name: formattedName,
          email: email,
          initials: formattedName.substring(0, 2).toUpperCase(),
          role: "Lead Security Engineer",
        },
      };
    }
  }

  // POST /api/auth/signup
  async signup(name, email, password) {
    try {
      const res = await this.request("/auth/signup", {
        method: "POST",
        body: JSON.stringify({ name, email, password }),
      });
      const token = res.access_token || res.token || "demo-jwt-token-xyz";
      this.setToken(token);
      return {
        success: true,
        live: true,
        user: res.user || {
          id: "usr-live-" + Date.now(),
          name: name,
          email: email,
          initials: name.substring(0, 2).toUpperCase(),
          role: "Security Engineer",
        },
      };
    } catch (err) {
      throw err;
      const token = "demo-session-token-" + Date.now();
      this.setToken(token);
      return {
        success: true,
        live: false,
        user: {
          id: "usr-demo-" + Date.now(),
          name: name,
          email: email,
          initials: name.substring(0, 2).toUpperCase(),
          role: "Security Engineer",
        },
      };
    }
  }

  // GET /api/auth/me
  async getCurrentUser() {
    try {
      const res = await this.request("/auth/me");
      return { success: true, live: true, user: res };
    } catch (err) {
      return { success: false, live: false, user: null };
    }
  }

  // POST /api/auth/logout
  async logout() {
    try {
      await this.request("/auth/logout", { method: "POST" });
    } catch (err) {
      // Non-critical if offline
    } finally {
      this.setToken(null);
    }
  }

  // =========================================================================
  // 2. REPOSITORY & SCAN ENDPOINTS
  // =========================================================================

  // Scan a GitHub URL directly via the GitHub public API (no backend needed)
  // Returns { success, live, data: { aiSummary, stats } } or throws RepoAccessError
  async scanGitHubRepo(repoUrl) {
    // fetchGitHubRepo throws RepoAccessError for private/invalid repos — let it bubble up
    const result = await fetchGitHubRepo(repoUrl);
    return {
      success: true,
      live: true,
      data: {
        aiSummary: result.aiSummary,
        stats: result.stats,
        repoMeta: {
          name: result.repoData.name,
          fullName: result.repoData.full_name,
          description: result.repoData.description,
          stars: result.repoData.stargazers_count,
          forks: result.repoData.forks_count,
          openIssues: result.repoData.open_issues_count,
          defaultBranch: result.repoData.default_branch,
          pushedAt: result.repoData.pushed_at,
          languages: result.languages,
          totalFiles: result.totalFiles,
          owner: result.owner,
          repo: result.repo,
        },
      },
    };
  }

  // POST /api/scan (backend path — kept as fallback for ZIP uploads)
  async startScan(payload, isFile = false) {
    try {
      const options = isFile
        ? { method: "POST", body: payload }
        : {
          method: "POST",
          body: JSON.stringify(payload),
        };
      const data = await this.request("/scan", options);
      return { success: true, live: true, data };
    } catch (err) {
      console.warn("Backend /api/scan unreachable:", err.message);
      return {
        success: false,
        live: false,
        data: null,
      };
    }
  }

  // =========================================================================
  // 3. DASHBOARD STATS
  // =========================================================================

  // GET /api/dashboard-stats
  async getDashboardStats() {
    try {
      const data = await this.request("/dashboard-stats");
      this.cache["stats"] = data;
      return { live: true, data };
    } catch (err) {
      return { live: false, data: this.cache["stats"] || DEFAULT_STATS };
    }
  }

  // =========================================================================
  // 4. BUGS MANAGEMENT
  // =========================================================================

  // GET /api/bugs
  async getBugs() {
    try {
      const data = await this.request("/bugs");
      this.cache["bugs"] = data;
      return { live: true, data };
    } catch (err) {
      return { live: false, data: this.cache["bugs"] || DEFAULT_BUGS };
    }
  }

  // PATCH /api/bugs/{id}/resolve
  async resolveBug(bugId, nextStatus) {
    try {
      const data = await this.request(`/bugs/${bugId}/resolve`, {
        method: "PATCH",
        body: JSON.stringify({ status: nextStatus }),
      });
      return { live: true, data };
    } catch (err) {
      console.warn(`Local resolve applied for ${bugId} (Demo fallback)`);
      return { live: false, data: { id: bugId, status: nextStatus, optimistic: true } };
    }
  }

  // PATCH /api/bugs/{id}/notes
  async updateBugNotes(bugId, remarks) {
    try {
      const data = await this.request(`/bugs/${bugId}/notes`, {
        method: "PATCH",
        body: JSON.stringify({ remarks, engineerNotes: remarks }),
      });
      return { live: true, data };
    } catch (err) {
      console.warn(`Local remarks saved for ${bugId} (Demo fallback)`);
      return { live: false, data: { id: bugId, remarks, engineerNotes: remarks, optimistic: true } };
    }
  }

  // =========================================================================
  // 5. AI ARCHITECTURE SUMMARY
  // =========================================================================

  // GET /api/ai-summary
  async getAiSummary() {
    try {
      const data = await this.request("/ai-summary");
      this.cache["ai-summary"] = data;
      return { live: true, data };
    } catch (err) {
      return { live: false, data: this.cache["ai-summary"] || DEFAULT_AI_SUMMARY };
    }
  }
}

export const apiService = new ApiService();
