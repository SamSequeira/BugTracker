// frontend/src/pages/TemporaryReviewDashboard/reviewApi.js
// Temporary API client for Human Ground-Truth Dataset Review

const API_BASE = "http://localhost:8000";

/**
 * Fetch the deterministic review batch of 200 real candidate issues.
 */
export async function fetchReviewBatch(targetSize = 200, randomSeed = 42) {
  try {
    const response = await fetch(`${API_BASE}/candidate-issues/review/batch`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        target_size: targetSize,
        random_seed: randomSeed,
        max_per_rule_per_repo: 25,
      }),
    });

    if (!response.ok) {
      throw new Error(`Failed to load review batch (${response.status})`);
    }

    const data = await response.json();
    return data.items || [];
  } catch (err) {
    console.warn("API batch generation failed, falling back to static batch data:", err);
    // Fallback: fetch static batch file if available
    try {
      const staticRes = await fetch("/backend/data/review_batch_200.json");
      if (staticRes.ok) {
        const staticData = await staticRes.json();
        return staticData.items || [];
      }
    } catch {
      // ignore
    }
    throw err;
  }
}

/**
 * Fetch candidate issue details by ID (including latest verification status).
 */
export async function fetchCandidateIssue(issueId) {
  const response = await fetch(`${API_BASE}/candidate-issues/${issueId}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch issue ${issueId}: ${response.status}`);
  }
  return await response.json();
}

/**
 * Fetch surrounding source code context for a candidate issue.
 */
export async function fetchSourceContext(issueId, contextLines = 15) {
  try {
    const response = await fetch(
      `${API_BASE}/candidate-issues/${issueId}/context?context_lines=${contextLines}`
    );
    if (!response.ok) {
      return {
        found: false,
        message: `Source context unavailable (${response.status}).`,
        formatted_text: "[Notice] Source context unavailable for this repository snapshot.",
        lines: [],
      };
    }
    return await response.json();
  } catch (err) {
    return {
      found: false,
      message: `Source context error: ${err.message}`,
      formatted_text: "[Notice] Source context unavailable for this repository snapshot.",
      lines: [],
    };
  }
}

/**
 * Save human verification decision (Confirmed or False Positive).
 */
export async function saveCandidateLabels(issueId, payload) {
  const response = await fetch(`${API_BASE}/candidate-issues/${issueId}/labels`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const errText = await response.text();
    let detail = errText;
    try {
      const errJson = JSON.parse(errText);
      detail = errJson.detail || errText;
    } catch {
      // raw text
    }
    throw new Error(`Failed to save labels: ${detail}`);
  }

  return await response.json();
}

/**
 * Fetch global dataset progress and distribution stats.
 */
export async function fetchDatasetStats() {
  try {
    const response = await fetch(`${API_BASE}/candidate-issues/dataset/stats`);
    if (!response.ok) {
      throw new Error(`Status ${response.status}`);
    }
    return await response.json();
  } catch (err) {
    console.error("Failed to fetch dataset stats:", err);
    return null;
  }
}
