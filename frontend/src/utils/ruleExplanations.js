// frontend/src/utils/ruleExplanations.js
// Plain-English Human-Readable Explanations for Static Analysis Rules

export const RULE_EXPLANATIONS = {
  // Python Rules
  PY_DIV_001: {
    title: "Division by Zero",
    explanation:
      "This code performs a division where the divisor may be zero. Depending on the language and execution context, this can cause a runtime error, invalid numeric result, or unexpected program behavior.",
    technicalCategory: "Arithmetic Safety",
  },
  PY_RES_001: {
    title: "Potentially Unclosed Resource",
    explanation:
      "This code opens or acquires a resource, such as a file, stream, or connection, but the analyzer cannot confirm that it is properly closed. This may eventually cause resource leaks or resource exhaustion.",
    technicalCategory: "Resource Management",
  },
  PY_ASS_001: {
    title: "Assert Statement in Production Code",
    explanation:
      "This code relies on an assert statement for a runtime check. Assertions may be disabled in optimized execution environments, so important validation should not depend solely on them.",
    technicalCategory: "Defensive Programming",
  },
  PY_MUT_001: {
    title: "Mutable Default Argument",
    explanation:
      "This function uses a mutable object, such as a list or dictionary, as a default argument. The same object may be reused across multiple function calls, potentially causing unexpected shared state.",
    technicalCategory: "State Management",
  },
  PY_EXC_001: {
    title: "Problematic Exception Handling",
    explanation:
      "This code handles an exception in a potentially unsafe or overly broad way. Important errors may be hidden, making failures difficult to diagnose or allowing the program to continue in an unexpected state.",
    technicalCategory: "Error Handling",
  },

  // Java Rules
  JAVA_EQ_001: {
    title: "Incorrect String Comparison",
    explanation:
      "This code compares strings using == instead of comparing their actual contents. In Java, == may compare object references rather than the text inside the strings, which can cause incorrect program logic.",
    technicalCategory: "Logic Error",
  },
  JAVA_RES_001: {
    title: "Potentially Unclosed Resource",
    explanation:
      "This code acquires a resource but the analyzer cannot confirm that it is properly closed. This may lead to resource leaks or exhaustion over time.",
    technicalCategory: "Resource Management",
  },
  JAVA_EXC_001: {
    title: "Empty Catch Block",
    explanation:
      "This code catches an exception but does not handle it. The error may be silently ignored, making failures difficult to detect and potentially allowing the program to continue in an unexpected state.",
    technicalCategory: "Error Handling",
  },
  JAVA_DIV_001: {
    title: "Division by Zero",
    explanation:
      "This code performs a division where the divisor may be zero. This can cause a runtime exception or invalid behavior depending on the execution path.",
    technicalCategory: "Arithmetic Safety",
  },

  // JavaScript Rules
  JS_EQ_001: {
    title: "Loose Equality Comparison",
    explanation:
      "This code uses loose equality (==) instead of strict equality (===). Loose equality performs automatic type conversion, which can sometimes produce unexpected comparison results.",
    technicalCategory: "Logic Safety",
  },
  JS_AWA_001: {
    title: "Await Inside a Loop",
    explanation:
      "This code waits for each asynchronous operation to finish before starting the next one. If the operations are independent, this can unnecessarily slow down execution.",
    technicalCategory: "Performance",
  },
  JS_DIV_001: {
    title: "Division by Zero",
    explanation:
      "This code performs a division where the divisor may be zero. Depending on the values and execution context, this may produce invalid numeric results or unexpected program behavior.",
    technicalCategory: "Arithmetic Safety",
  },
};

/**
 * Format raw snake_case or hyphenated string into Title Case.
 */
function formatTitleCase(str) {
  if (!str) return "";
  return str
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase())
    .trim();
}

/**
 * Retrieve a human-readable explanation object for any given rule_id and issue_type.
 * Gracefully provides clear fallback for unknown or future rules without throwing errors.
 *
 * @param {string|null} ruleId - The static analysis rule identifier (e.g. "JAVA_EQ_001")
 * @param {string|null} issueType - Optional fallback issue type string (e.g. "string_reference_equality")
 * @returns {{ title: string, explanation: string, technicalCategory: string, technicalRuleId: string }}
 */
export function getRuleExplanation(ruleId, issueType = null) {
  const normRuleId = (ruleId || "").trim().toUpperCase();

  if (normRuleId && RULE_EXPLANATIONS[normRuleId]) {
    const entry = RULE_EXPLANATIONS[normRuleId];
    return {
      title: entry.title,
      explanation: entry.explanation,
      technicalCategory: entry.technicalCategory,
      technicalRuleId: normRuleId,
    };
  }

  // Graceful fallback for unknown/future rules
  const fallbackTitle = issueType ? formatTitleCase(issueType) : "Potential Code Issue";
  return {
    title: fallbackTitle || "Potential Code Issue",
    explanation:
      "This code was flagged by the static analyzer because it matches a potentially problematic code pattern. Review the code and available evidence to determine whether this is a real issue.",
    technicalCategory: "Static Analysis Finding",
    technicalRuleId: normRuleId || "UNKNOWN_RULE",
  };
}
