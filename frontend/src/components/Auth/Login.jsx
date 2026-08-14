// src/components/Auth/Login.jsx - Polished Login Form with Validation & Demo Capabilities
import React, { useState } from "react";
import { useBugTracker } from "../../useBugTracker.jsx";

export default function Login({ onSwitchToSignup, onOpenForgotPassword }) {
  const { login } = useBugTracker();

  const [email, setEmail] = useState("alex.mercer@bugtracker.dev");
  const [password, setPassword] = useState("SecurePass2026!");
  const [showPassword, setShowPassword] = useState(false);
  const [errors, setErrors] = useState({});
  const [isLoading, setIsLoading] = useState(false);
  const [apiError, setApiError] = useState("");

  const validate = () => {
    const nextErrors = {};
    if (!email.trim()) {
      nextErrors.email = "Email is required.";
    } else {
      const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
      if (!emailRegex.test(email.trim())) {
        nextErrors.email = "Please enter a valid email address.";
      }
    }

    if (!password) {
      nextErrors.password = "Password is required.";
    } else if (password.length < 6) {
      nextErrors.password = "Password must be at least 6 characters.";
    }

    setErrors(nextErrors);
    return Object.keys(nextErrors).length === 0;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setApiError("");

    if (!validate()) return;

    setIsLoading(true);
    try {
      const result = await login(email.trim(), password);
      if (!result.success) {
        setApiError(result.error || "Invalid credentials. Please verify your email and password.");
      }
    } catch (err) {
      setApiError("Authentication service timed out. Loaded local demo workspace.");
    } finally {
      setIsLoading(false);
    }
  };

  const handleUseDemo = (demoEmail, demoRole) => {
    setEmail(demoEmail);
    setPassword("DemoSecurePass123!");
    setErrors({});
    setApiError("");
  };

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-bold text-white tracking-tight">Sign in to your account</h2>
        <p className="text-xs text-slate-400 mt-1">
          Access automated AST vulnerability detection and prioritization
        </p>
      </div>

      {apiError && (
        <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-3 text-xs text-red-300 flex items-start gap-2 animate-fade-in">
          <svg className="w-4 h-4 text-red-400 shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <div>
            <strong className="font-semibold text-red-200">Authentication Alert: </strong>
            <span>{apiError}</span>
          </div>
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-4" noValidate>
        {/* Email Field */}
        <div>
          <label className="block text-xs font-semibold text-slate-300 mb-1.5">
            Work Email
          </label>
          <div className="relative">
            <input
              type="email"
              id="login-email"
              value={email}
              onChange={(e) => {
                setEmail(e.target.value);
                if (errors.email) setErrors((prev) => ({ ...prev, email: "" }));
              }}
              placeholder="engineer@company.dev"
              className={`w-full bg-[#0B0F17] border rounded-lg pl-9 pr-3.5 py-2.5 text-xs text-white placeholder-slate-500 focus:outline-none transition-colors font-mono ${
                errors.email ? "border-red-500/80 focus:border-red-400" : "border-slate-700 focus:border-cyan-400"
              }`}
            />
            <svg
              className="w-4 h-4 text-slate-500 absolute left-3 top-3"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth="2"
                d="M16 12a4 4 0 10-8 0 4 4 0 008 0zm0 0v1.5a2.5 2.5 0 005 0V12a9 9 0 10-9 9m4.5-1.206a8.959 8.959 0 01-4.5 1.206"
              />
            </svg>
          </div>
          {errors.email && (
            <p className="text-[11px] text-red-400 mt-1.5 flex items-center gap-1">
              <span>⚠️</span> {errors.email}
            </p>
          )}
        </div>

        {/* Password Field */}
        <div>
          <div className="flex items-center justify-between mb-1.5">
            <label className="text-xs font-semibold text-slate-300">
              Password
            </label>
            <button
              type="button"
              onClick={onOpenForgotPassword}
              className="text-[11px] text-cyan-400 hover:text-cyan-300 transition-colors"
            >
              Forgot password?
            </button>
          </div>
          <div className="relative">
            <input
              type={showPassword ? "text" : "password"}
              id="login-password"
              value={password}
              onChange={(e) => {
                setPassword(e.target.value);
                if (errors.password) setErrors((prev) => ({ ...prev, password: "" }));
              }}
              placeholder="••••••••••••"
              className={`w-full bg-[#0B0F17] border rounded-lg pl-9 pr-10 py-2.5 text-xs text-white placeholder-slate-500 focus:outline-none transition-colors font-mono ${
                errors.password ? "border-red-500/80 focus:border-red-400" : "border-slate-700 focus:border-cyan-400"
              }`}
            />
            <svg
              className="w-4 h-4 text-slate-500 absolute left-3 top-3"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth="2"
                d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"
              />
            </svg>
            <button
              type="button"
              onClick={() => setShowPassword(!showPassword)}
              className="absolute right-3 top-2.5 text-slate-400 hover:text-white p-0.5 rounded transition-colors"
              title={showPassword ? "Hide password" : "Show password"}
            >
              {showPassword ? (
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l18 18" />
                </svg>
              ) : (
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                </svg>
              )}
            </button>
          </div>
          {errors.password && (
            <p className="text-[11px] text-red-400 mt-1.5 flex items-center gap-1">
              <span>⚠️</span> {errors.password}
            </p>
          )}
        </div>

        {/* Submit Button */}
        <button
          type="submit"
          id="btn-login-submit"
          disabled={isLoading}
          className="w-full bg-cyan-400 hover:bg-cyan-300 text-slate-950 font-bold py-2.5 rounded-lg text-xs transition-all flex items-center justify-center gap-2 shadow-lg shadow-cyan-500/10 cursor-pointer disabled:opacity-60"
        >
          {isLoading ? (
            <>
              <div className="w-4 h-4 border-2 border-slate-950 border-t-transparent rounded-full animate-spin"></div>
              <span>Signing in...</span>
            </>
          ) : (
            <span>Sign In to BugTracker →</span>
          )}
        </button>
      </form>

      {/* Switch to Sign Up */}
      <div className="text-center pt-2 border-t border-slate-800/80">
        <p className="text-xs text-slate-400">
          Don't have an account?{" "}
          <button
            type="button"
            onClick={onSwitchToSignup}
            className="text-cyan-400 hover:text-cyan-300 font-semibold transition-colors"
          >
            Create an account
          </button>
        </p>
      </div>

      {/* Quick Demo Pre-fills */}
      <div className="bg-[#0B0F17] border border-slate-800/80 rounded-xl p-3.5 space-y-2">
        <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider block">
          ⚡ One-Click Demo Profiles (Offline Ready)
        </span>
        <div className="grid grid-cols-2 gap-2">
          <button
            type="button"
            onClick={() => handleUseDemo("alex.mercer@bugtracker.dev", "Lead Engineer")}
            className="bg-[#131B2E] hover:bg-slate-800 border border-slate-700/60 rounded-lg p-2 text-left transition-colors"
          >
            <div className="text-xs font-semibold text-white">Alex Mercer</div>
            <div className="text-[10px] text-cyan-400 font-mono">Lead SecOps</div>
          </button>
          <button
            type="button"
            onClick={() => handleUseDemo("sarah.chen@cloudsec.io", "Cloud Security")}
            className="bg-[#131B2E] hover:bg-slate-800 border border-slate-700/60 rounded-lg p-2 text-left transition-colors"
          >
            <div className="text-xs font-semibold text-white">Sarah Chen</div>
            <div className="text-[10px] text-amber-400 font-mono">Cloud SecOps</div>
          </button>
        </div>
      </div>
    </div>
  );
}
