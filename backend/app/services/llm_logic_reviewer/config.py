"""
Config for the local-LLM logic review pipeline.
All values overridable via backend/.env — same pattern as app/core/config.py.
"""

import os


def _optional(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


OLLAMA_HOST: str = _optional("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL: str = _optional("OLLAMA_MODEL", "qwen2.5-coder:3b-instruct-q4_K_M")

# How long to wait for one function's review before giving up on it (seconds).
# Kept generous since a 4GB-VRAM card will spill layers to CPU.
OLLAMA_TIMEOUT_SECONDS: float = float(_optional("OLLAMA_TIMEOUT_SECONDS", "90"))

# Skip functions shorter than this many lines — not enough logic to review,
# and keeps noise/cost down.
LLM_MIN_FUNCTION_LINES: int = int(_optional("LLM_MIN_FUNCTION_LINES", "2"))

# Hard cap on characters of function source sent per call, to keep prompts
# small and fast even for one unusually huge function.
LLM_MAX_FUNCTION_CHARS: int = int(_optional("LLM_MAX_FUNCTION_CHARS", "4000"))

# If a single function call fails/times out this many times in a row,
# stop retrying it and move on (never crash the whole repo scan).
LLM_MAX_RETRIES_PER_FUNCTION: int = int(_optional("LLM_MAX_RETRIES_PER_FUNCTION", "1"))

# ---------------------------------------------------------------------------
# Semantic pipeline (OpenAI-backed strong reasoner)
# ---------------------------------------------------------------------------

# OpenAI API key — read from environment only, NEVER hardcoded or logged.
OPENAI_API_KEY: str = _optional("OPENAI_API_KEY", "")

# Strong OpenAI model used as final semantic reasoner after Qwen investigation.
# gpt-4o-mini is fast, cheap, and strong enough for this task.
SEMANTIC_STRONG_MODEL: str = _optional("SEMANTIC_STRONG_MODEL", "gpt-4o-mini")

# Minimum confidence (0-1) required to emit a semantic finding.
# Conservative: 0.75 means we need strong evidence before creating an issue.
SEMANTIC_MIN_CONFIDENCE: float = float(_optional("SEMANTIC_MIN_CONFIDENCE", "0.75"))

# Minimum candidate score (from deterministic risk scorer) to send function to LLM.
# Functions below this threshold are skipped entirely to conserve LLM calls.
SEMANTIC_CANDIDATE_SCORE_THRESHOLD: int = int(_optional("SEMANTIC_CANDIDATE_SCORE_THRESHOLD", "3"))

# When true, emit detailed per-function diagnostic logs for the semantic pipeline.
# Set SEMANTIC_DEBUG=true in .env for diagnosis. Never logs secrets.
SEMANTIC_DEBUG: bool = _optional("SEMANTIC_DEBUG", "false").lower() in ("true", "1", "yes")

# Maximum chars of context to send to OpenAI per call (keeps cost bounded).
SEMANTIC_MAX_OPENAI_CONTEXT_CHARS: int = int(_optional("SEMANTIC_MAX_OPENAI_CONTEXT_CHARS", "8000"))
