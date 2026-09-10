// src/api.js - Central Data Access Layer for BugTracker
// Manages backend requests, AbortController timeout, live/demo state, and caching.

import { DEFAULT_STATS, DEFAULT_AI_SUMMARY } from "./mockData.js";
import { fetchGitHubRepo, setGitHubToken, getGitHubToken } from "./github.js";

const DEFAULT_API_URL = "http://localhost:8000/api/v1";
const TIMEOUT_MS = 6000;

class ApiService {
  constructor() {
    this.baseUrl = sessionStorage.getItem("bugtracker_api_url") || DEFAULT_API_URL;
    // Normalize legacy /api URL to /api/v1 if saved in sessionStorage
    if (this.baseUrl.endsWith("/api")) {
      this.baseUrl = this.baseUrl + "/v1";
    }
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
    let cleanUrl = url.trim().replace(/\/+$/, "");
    if (cleanUrl.endsWith("/api")) {
      cleanUrl += "/v1";
    }
    this.baseUrl = cleanUrl;
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

  // Core fetch wrapper with AbortController timeout
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
        const errorText = await response.text().catch(() => "");
        let detail = response.statusText;
        try {
          const jsonErr = JSON.parse(errorText);
          detail = jsonErr.detail || detail;
        } catch {
          if (errorText) detail = errorText;
        }
        throw Object.assign(new Error(`HTTP Error ${response.status}: ${detail}`), {
          status: response.status,
          detail,
        });
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
      const res = await fetch(`${targetUrl}/repositories/`, {
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
  // 1. AUTHENTICATION ENDPOINTS
  // =========================================================================

  // POST /api/v1/auth/login
  async login(email, password) {
    try {
      const res = await this.request("/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });
      const token = res.access_token;
      this.setToken(token);
      return {
        success: true,
        live: true,
        user: res.user || {
          id: "usr-live-01",
          name: email.split("@")[0],
          email: email,
          initials: email.substring(0, 2).toUpperCase(),
          role: "Security Engineer",
        },
      };
    } catch (err) {
      const isHttp = Boolean(err.status);
      const detail = err.detail || (err.status === 401 ? "Invalid email or password." : err.message);
      return {
        success: false,
        live: isHttp,
        error: detail,
        user: null,
      };
    }
  }

  // POST /api/v1/auth/signup
  async signup(name, email, password) {
    try {
      await this.request("/auth/signup", {
        method: "POST",
        body: JSON.stringify({ name, email, password }),
      });
      // After signup, automatically log in
      return await this.login(email, password);
    } catch (err) {
      const isHttp = Boolean(err.status);
      const detail = err.detail || (err.status === 400 ? "Email already registered." : err.message);
      return {
        success: false,
        live: isHttp,
        error: detail,
        user: null,
      };
    }
  }

  // GET /api/v1/auth/me
  async getCurrentUser() {
    try {
      const res = await this.request("/auth/me");
      return { success: true, live: true, user: res };
    } catch (err) {
      return { success: false, live: false, user: null };
    }
  }

  // POST /api/v1/auth/logout
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

  // Scan a GitHub URL directly via GitHub public API for client metadata
  async scanGitHubRepo(repoUrl) {
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

  // GET /api/v1/repositories/
  async getRepositories() {
    try {
      const data = await this.request("/repositories/");
      return { live: true, data: Array.isArray(data) ? data : [] };
    } catch (err) {
      return { live: false, data: [] };
    }
  }

  // GET /api/v1/repositories/{repositoryId}/architecture
  async getRepositoryArchitecture(repositoryId) {
    if (!repositoryId) return { live: false, data: null, error: "No repository ID" };
    try {
      const data = await this.request(`/repositories/${repositoryId}/architecture`);
      return { live: true, data };
    } catch (err) {
      const status = err.message?.match(/HTTP Error (\d+)/)?.[1];
      return { live: false, data: null, error: err.message, status: status ? parseInt(status) : null };
    }
  }

  // GET /api/v1/repositories/{repositoryId}/analysis-status
  async getRepositoryAnalysisStatus(repositoryId) {
    if (!repositoryId) return { live: false, data: null, error: "No repository ID" };
    try {
      const data = await this.request(`/repositories/${repositoryId}/analysis-status`);
      return { live: true, data };
    } catch (err) {
      const httpStatus = err.message?.match(/HTTP Error (\d+)/)?.[1];
      return {
        live: false,
        data: null,
        error: err.message,
        status: httpStatus ? parseInt(httpStatus) : null,
      };
    }
  }

  // =========================================================================
  // 3. CANDIDATE ISSUES & BUGS MANAGEMENT
  // =========================================================================

  // GET /api/v1/candidate-issues
  async getBugs(params = {}) {
    try {
      const query = new URLSearchParams();
      if (params.repository_id) query.append("repository_id", params.repository_id);
      if (params.analysis_run_id) query.append("analysis_run_id", params.analysis_run_id);
      if (params.severity && params.severity !== "All") query.append("severity", params.severity.toLowerCase());
      if (params.verification_status && params.verification_status !== "all") {
        query.append("verification_status", params.verification_status);
      }
      query.append("limit", params.limit || "500");

      const queryString = query.toString();
      const endpoint = `/candidate-issues${queryString ? `?${queryString}` : ""}`;
      const data = await this.request(endpoint);

      const items = data.items || [];
      this.cache["bugs"] = items;
      return { live: true, data: items, total: data.total || items.length };
    } catch (err) {
      return { live: false, data: this.cache["bugs"] || [], total: (this.cache["bugs"] || []).length, error: err.message };
    }
  }

  // PATCH /api/v1/candidate-issues/{id}/status
  async resolveBug(bugId, nextStatus) {
    try {
      const data = await this.request(`/candidate-issues/${bugId}/status`, {
        method: "PATCH",
        body: JSON.stringify({ status: nextStatus }),
      });
      return { live: true, data };
    } catch (err) {
      console.warn(`Local resolve applied for ${bugId} (Demo fallback)`);
      return { live: false, data: { id: bugId, status: nextStatus, optimistic: true } };
    }
  }

  // PATCH /api/v1/candidate-issues/{id}/severity
  async updateBugSeverity(bugId, nextSeverity) {
    try {
      const data = await this.request(`/candidate-issues/${bugId}/severity`, {
        method: "PATCH",
        body: JSON.stringify({ severity: nextSeverity }),
      });
      return { live: true, data };
    } catch (err) {
      console.warn(`Local severity update for ${bugId}: ${err.message}`);
      return { live: false, data: { id: bugId, severity: nextSeverity, optimistic: true } };
    }
  }

  // PATCH /api/v1/candidate-issues/{id}/notes
  async updateBugNotes(bugId, remarks) {
    try {
      const data = await this.request(`/candidate-issues/${bugId}/notes`, {
        method: "PATCH",
        body: JSON.stringify({ remarks, engineerNotes: remarks }),
      });
      return { live: true, data };
    } catch (err) {
      console.warn(`Local remarks saved for ${bugId} (Demo fallback)`);
      return { live: false, data: { id: bugId, remarks, engineerNotes: remarks, optimistic: true } };
    }
  }

  // PATCH /api/v1/candidate-issues/{id}/labels
  async saveCandidateLabels(issueId, payload) {
    return await this.request(`/candidate-issues/${issueId}/labels`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
  }

  // GET /api/v1/candidate-issues/{id}/context
  async getSourceContext(issueId, contextLines = 8) {
    if (!issueId) return { found: false, lines: [] };
    try {
      const data = await this.request(`/candidate-issues/${issueId}/context?context_lines=${contextLines}`);
      return data;
    } catch (err) {
      return { found: false, lines: [], error: err.message };
    }
  }

  // GET /api/v1/candidate-issues/dataset/stats
  async getDatasetStats() {
    try {
      const data = await this.request("/candidate-issues/dataset/stats");
      return { live: true, data };
    } catch (err) {
      return { live: false, data: null };
    }
  }

  // POST /api/v1/candidate-issues/review/batch
  async getReviewBatch(targetSize = 200, randomSeed = 42) {
    return await this.request("/candidate-issues/review/batch", {
      method: "POST",
      body: JSON.stringify({
        target_size: targetSize,
        random_seed: randomSeed,
        max_per_rule_per_repo: 25,
      }),
    });
  }

  // =========================================================================
  // 4. AI ARCHITECTURE & DASHBOARD STATS
  // =========================================================================

  // GET /api/v1/dashboard-stats
  async getDashboardStats() {
    try {
      const statsRes = await this.getDatasetStats();
      if (statsRes.live && statsRes.data) {
        return { live: true, data: statsRes.data };
      }
      return { live: false, data: DEFAULT_STATS };
    } catch (err) {
      return { live: false, data: this.cache["stats"] || DEFAULT_STATS };
    }
  }
}

export const apiService = new ApiService();
