// src/components/Auth/Signup.jsx - Signup Form with Input Validation & Backend Connect
import React, { useState } from "react";
import { useBugTracker } from "../../useBugTracker.jsx";

export default function Signup({ onSwitchToLogin }) {
  const { signup } = useBugTracker();

  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [errors, setErrors] = useState({});
  const [isLoading, setIsLoading] = useState(false);
  const [apiError, setApiError] = useState("");

  const validate = () => {
    const nextErrors = {};

    if (!fullName.trim()) {
      nextErrors.fullName = "Full name is required.";
    } else if (fullName.trim().length < 2) {
      nextErrors.fullName = "Name must be at least 2 characters.";
    }

    if (!email.trim()) {
      nextErrors.email = "Email is required.";
    } else {
      const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
      if (!emailRegex.test(email.trim())) {
        nextErrors.email = "Please enter a valid work email address.";
      }
    }

    if (!password) {
      nextErrors.password = "Password is required.";
    } else if (password.length < 6) {
      nextErrors.password = "Password must be at least 6 characters.";
    }

    if (!confirmPassword) {
      nextErrors.confirmPassword = "Please confirm your password.";
    } else if (password !== confirmPassword) {
      nextErrors.confirmPassword = "Passwords do not match.";
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
      const result = await signup(fullName.trim(), email.trim(), password);
      if (!result.success) {
        setApiError(result.error || "Failed to create account. Please try again.");
      }
    } catch (err) {
      setApiError("Backend unreachable. Initialized demo session.");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-bold text-white tracking-tight">Create your developer account</h2>
        <p className="text-xs text-slate-400 mt-1">
          Start scanning repositories and managing security bugs
        </p>
      </div>

      {apiError && (
        <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-3 text-xs text-red-300 flex items-start gap-2 animate-fade-in">
          <svg className="w-4 h-4 text-red-400 shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <div>
            <strong className="font-semibold text-red-200">Registration Alert: </strong>
            <span>{apiError}</span>
          </div>
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-3.5" noValidate>
        {/* Full Name */}
        <div>
          <label className="block text-xs font-semibold text-slate-300 mb-1">
            Full Name
          </label>
          <input
            type="text"
            id="signup-name"
            value={fullName}
            onChange={(e) => {
              setFullName(e.target.value);
              if (errors.fullName) setErrors((prev) => ({ ...prev, fullName: "" }));
            }}
            placeholder="e.g. Alex Mercer"
            className={`w-full bg-[#0B0F17] border rounded-lg px-3.5 py-2.5 text-xs text-white placeholder-slate-500 focus:outline-none transition-colors ${
              errors.fullName ? "border-red-500/80 focus:border-red-400" : "border-slate-700 focus:border-cyan-400"
            }`}
          />
          {errors.fullName && (
            <p className="text-[11px] text-red-400 mt-1 flex items-center gap-1">
              <span>⚠️</span> {errors.fullName}
            </p>
          )}
        </div>

        {/* Email Field */}
        <div>
          <label className="block text-xs font-semibold text-slate-300 mb-1">
            Work Email
          </label>
          <input
            type="email"
            id="signup-email"
            value={email}
            onChange={(e) => {
              setEmail(e.target.value);
              if (errors.email) setErrors((prev) => ({ ...prev, email: "" }));
            }}
            placeholder="alex.mercer@company.dev"
            className={`w-full bg-[#0B0F17] border rounded-lg px-3.5 py-2.5 text-xs text-white placeholder-slate-500 focus:outline-none transition-colors font-mono ${
              errors.email ? "border-red-500/80 focus:border-red-400" : "border-slate-700 focus:border-cyan-400"
            }`}
          />
          {errors.email && (
            <p className="text-[11px] text-red-400 mt-1 flex items-center gap-1">
              <span>⚠️</span> {errors.email}
            </p>
          )}
        </div>

        {/* Password Fields */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div>
            <label className="block text-xs font-semibold text-slate-300 mb-1">
              Password
            </label>
            <div className="relative">
              <input
                type={showPassword ? "text" : "password"}
                id="signup-password"
                value={password}
                onChange={(e) => {
                  setPassword(e.target.value);
                  if (errors.password) setErrors((prev) => ({ ...prev, password: "" }));
                }}
                placeholder="Min 6 chars"
                className={`w-full bg-[#0B0F17] border rounded-lg px-3.5 py-2.5 text-xs text-white placeholder-slate-500 focus:outline-none transition-colors font-mono pr-8 ${
                  errors.password ? "border-red-500/80 focus:border-red-400" : "border-slate-700 focus:border-cyan-400"
                }`}
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-2.5 top-2.5 text-slate-400 hover:text-white"
              >
                <span className="text-xs">{showPassword ? "🙈" : "👁️"}</span>
              </button>
            </div>
            {errors.password && (
              <p className="text-[10px] text-red-400 mt-1">
                ⚠️ {errors.password}
              </p>
            )}
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-300 mb-1">
              Confirm Password
            </label>
            <input
              type={showPassword ? "text" : "password"}
              id="signup-confirm-password"
              value={confirmPassword}
              onChange={(e) => {
                setConfirmPassword(e.target.value);
                if (errors.confirmPassword) setErrors((prev) => ({ ...prev, confirmPassword: "" }));
              }}
              placeholder="Re-enter password"
              className={`w-full bg-[#0B0F17] border rounded-lg px-3.5 py-2.5 text-xs text-white placeholder-slate-500 focus:outline-none transition-colors font-mono ${
                errors.confirmPassword ? "border-red-500/80 focus:border-red-400" : "border-slate-700 focus:border-cyan-400"
              }`}
            />
            {errors.confirmPassword && (
              <p className="text-[10px] text-red-400 mt-1">
                ⚠️ {errors.confirmPassword}
              </p>
            )}
          </div>
        </div>

        {/* Submit Button */}
        <button
          type="submit"
          id="btn-signup-submit"
          disabled={isLoading}
          className="w-full bg-cyan-400 hover:bg-cyan-300 text-slate-950 font-bold py-2.5 rounded-lg text-xs transition-all flex items-center justify-center gap-2 shadow-lg shadow-cyan-500/10 cursor-pointer disabled:opacity-60 mt-4"
        >
          {isLoading ? (
            <>
              <div className="w-4 h-4 border-2 border-slate-950 border-t-transparent rounded-full animate-spin"></div>
              <span>Creating account...</span>
            </>
          ) : (
            <span>Create Free Account →</span>
          )}
        </button>
      </form>

      {/* Switch to Sign In */}
      <div className="text-center pt-2 border-t border-slate-800/80">
        <p className="text-xs text-slate-400">
          Already have an account?{" "}
          <button
            type="button"
            onClick={onSwitchToLogin}
            className="text-cyan-400 hover:text-cyan-300 font-semibold transition-colors"
          >
            Sign in
          </button>
        </p>
      </div>
    </div>
  );
}
