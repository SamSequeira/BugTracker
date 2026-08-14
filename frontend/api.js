// api.js - Central Data Access Layer with AbortController 4s timeout & silent fallback

import { DEFAULT_STATS, DEFAULT_BUGS, DEFAULT_AI_SUMMARY } from "./mockData.js";

const DEFAULT_API_URL = "http://localhost:8000/api";

class ApiService {
  constructor() {
    this.baseUrl = sessionStorage.getItem("bugtracker_api_url") || DEFAULT_API_URL;
    this.isLive = false;
    this.cache = {};
  }

  getBaseUrl() {
    return this.baseUrl;
  }

  setBaseUrl(url) {
    if (!url) return;
    this.baseUrl = url.trim().replace(/\/+$/, "");
    sessionStorage.setItem("bugtracker_api_url", this.baseUrl);
    this.cache = {}; // Clear endpoint cache on URL update
  }

  async fetchWithTimeout(endpoint, options = {}, timeoutMs = 4000) {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

    try {
      const response = await fetch(`${this.baseUrl}${endpoint}`, {
        ...options,
        signal: controller.signal,
      });
      clearTimeout(timeoutId);
      if (!response.ok) throw new Error(`HTTP Error ${response.status}`);
      this.isLive = true;
      return await response.json();
    } catch (err) {
      clearTimeout(timeoutId);
      this.isLive = false;
      throw err;
    }
  }

  // POST /api/scan
  async startScan(payload, isFile = false) {
    try {
      const options = isFile
        ? { method: "POST", body: payload }
        : {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
          };
      const data = await this.fetchWithTimeout("/scan", options);
      return { success: true, live: true, data };
    } catch (err) {
      console.warn("Backend /api/scan unreachable, utilizing fallback engine simulation:", err.message);
      return {
        success: true,
        live: false,
        data: { status: "simulated", progress: 100, message: "Scan completed via local fallback engine" },
      };
    }
  }

  // GET /api/dashboard-stats
  async getDashboardStats() {
    try {
      const data = await this.fetchWithTimeout("/dashboard-stats");
      this.cache["stats"] = data;
      return { live: true, data };
    } catch (err) {
      return { live: false, data: this.cache["stats"] || DEFAULT_STATS };
    }
  }

  // GET /api/bugs
  async getBugs() {
    try {
      const data = await this.fetchWithTimeout("/bugs");
      this.cache["bugs"] = data;
      return { live: true, data };
    } catch (err) {
      return { live: false, data: this.cache["bugs"] || DEFAULT_BUGS };
    }
  }

  // GET /api/ai-summary
  async getAiSummary() {
    try {
      const data = await this.fetchWithTimeout("/ai-summary");
      this.cache["ai-summary"] = data;
      return { live: true, data };
    } catch (err) {
      return { live: false, data: this.cache["ai-summary"] || DEFAULT_AI_SUMMARY };
    }
  }

  // PATCH /api/bugs/{id}/resolve
  async resolveBug(bugId, nextStatus) {
    try {
      const data = await this.fetchWithTimeout(`/bugs/${bugId}/resolve`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: nextStatus }),
      });
      return { live: true, data };
    } catch (err) {
      console.warn(`Optimistic local resolve applied for ${bugId}`);
      return { live: false, data: { bugId, status: nextStatus, optimistic: true } };
    }
  }

  // PATCH /api/bugs/{id}/notes
  async updateBugNotes(bugId, notes) {
    try {
      const data = await this.fetchWithTimeout(`/bugs/${bugId}/notes`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ engineerNotes: notes }),
      });
      return { live: true, data };
    } catch (err) {
      console.warn(`Optimistic local notes update for ${bugId}`);
      return { live: false, data: { bugId, engineerNotes: notes, optimistic: true } };
    }
  }
}

export const apiService = new ApiService();
