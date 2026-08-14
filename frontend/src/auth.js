// src/auth.js - Authentication State and Session Helper

import { apiService } from "./api.js";

const SESSION_KEY = "bugtracker_user_session";

export const authService = {
  // Retrieve saved session from sessionStorage
  getSavedSession() {
    try {
      const data = sessionStorage.getItem(SESSION_KEY);
      if (!data) return null;
      return JSON.parse(data);
    } catch (e) {
      sessionStorage.removeItem(SESSION_KEY);
      return null;
    }
  },

  // Save active user session
  saveSession(user) {
    if (user) {
      sessionStorage.setItem(SESSION_KEY, JSON.stringify(user));
    } else {
      sessionStorage.removeItem(SESSION_KEY);
    }
  },

  // Perform login
  async login(email, password) {
    const res = await apiService.login(email, password);
    if (res.success && res.user) {
      this.saveSession(res.user);
    }
    return res;
  },

  // Perform signup
  async signup(name, email, password) {
    const res = await apiService.signup(name, email, password);
    if (res.success && res.user) {
      this.saveSession(res.user);
    }
    return res;
  },

  // Perform logout
  async logout() {
    await apiService.logout();
    this.saveSession(null);
  },
};
