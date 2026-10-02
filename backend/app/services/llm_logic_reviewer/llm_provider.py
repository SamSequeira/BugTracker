"""
LLM Provider abstraction for semantic bug detection.

Supported providers:
- Ollama
- Gemini
- Groq
- OpenAI

The semantic reviewer expects every provider to expose:

    generate(prompt) -> {
        "response": str,
        "error": optional str
    }

The provider layer is responsible only for communicating with the LLM.
It does NOT parse findings, validate evidence, deduplicate findings, or
persist database records.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import ollama

logger = logging.getLogger(__name__)


# ============================================================================
# BASE PROVIDER
# ============================================================================


class LLMProvider:
    """Abstract interface for semantic-review LLM providers."""

    def generate(
        self,
        prompt: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Generate an LLM response.

        Implementations must return:

            {
                "response": "<model output>"
            }

        or on failure:

            {
                "response": "",
                "error": "<error description>"
            }
        """

        raise NotImplementedError


# ============================================================================
# OLLAMA
# ============================================================================


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "").strip() or default)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, "").strip() or default)
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _resp_field(response: Any, name: str, default: Any = None) -> Any:
    """Read a field from an Ollama response (dict or response object)."""
    if isinstance(response, dict):
        return response.get(name, default)
    return getattr(response, name, default)


class OllamaProvider(LLMProvider):
    """
    Local Ollama provider.

    Settings (all optional, read from environment variables):

        OLLAMA_NUM_CTX      context window in tokens        (default 8192)
        OLLAMA_TEMPERATURE  sampling temperature            (default 0)
        OLLAMA_NUM_PREDICT  max tokens the model may write  (default 900)
        OLLAMA_JSON_MODE    force valid JSON output         (default true)
        OLLAMA_SEED         fixed seed for repeatable runs  (default 0)
        OLLAMA_KEEP_ALIVE   keep the model loaded           (default 30m)

    Why these matter: with no options Ollama uses a 4096-token context and
    a non-zero temperature. Prompts longer than the context are silently
    cut, and the model's answers vary from run to run.
    """

    def __init__(
        self,
        host: str,
        model: str,
        timeout: float,
    ) -> None:
        self.host = host
        self.model = model
        self.timeout = timeout

        self.num_ctx = _env_int("OLLAMA_NUM_CTX", 8192)
        self.temperature = _env_float("OLLAMA_TEMPERATURE", 0.0)
        self.num_predict = _env_int("OLLAMA_NUM_PREDICT", 900)
        self.json_mode = _env_bool("OLLAMA_JSON_MODE", True)
        self.seed = _env_int("OLLAMA_SEED", 0)
        self.keep_alive = os.getenv("OLLAMA_KEEP_ALIVE", "30m").strip() or "30m"

        # Filled after every call so runners/tests can inspect real token use.
        self.last_meta: dict[str, Any] = {}

        self.client = ollama.Client(
            host=host,
            timeout=timeout,
        )

        logger.info(
            "Ollama provider initialized: model=%s host=%s timeout=%s "
            "num_ctx=%s temperature=%s num_predict=%s json_mode=%s seed=%s",
            self.model,
            self.host,
            self.timeout,
            self.num_ctx,
            self.temperature,
            self.num_predict,
            self.json_mode,
            self.seed,
        )

    def _build_call_kwargs(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        """Provider defaults first; anything the caller passes wins."""
        call_kwargs = dict(kwargs)

        options: dict[str, Any] = {
            "num_ctx": self.num_ctx,
            "temperature": self.temperature,
            "num_predict": self.num_predict,
            "seed": self.seed,
        }

        caller_options = call_kwargs.pop("options", None)
        if caller_options:
            try:
                options.update(dict(caller_options))
            except (TypeError, ValueError):
                pass

        call_kwargs["options"] = options

        if self.json_mode:
            call_kwargs.setdefault("format", "json")

        call_kwargs.setdefault("keep_alive", self.keep_alive)

        return call_kwargs

    def generate(
        self,
        prompt: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Send one prompt to Ollama.

        No JSON parsing is performed here. The semantic pipeline owns
        response parsing because different providers can return slightly
        different response representations.

        The returned dict has an extra "meta" key with the real token
        counts, so prompt truncation is visible instead of silent.
        """

        if not isinstance(prompt, str) or not prompt.strip():
            return {
                "response": "",
                "error": "Prompt is empty.",
            }

        try:
            call_kwargs = self._build_call_kwargs(kwargs)

            response = self.client.generate(
                model=self.model,
                prompt=prompt,
                **call_kwargs,
            )

            content = _resp_field(response, "response", "")

            if content is None:
                content = ""

            content = str(content)

            used_ctx = call_kwargs["options"].get("num_ctx")
            max_out = call_kwargs["options"].get("num_predict")
            prompt_tokens = _resp_field(response, "prompt_eval_count", None)
            output_tokens = _resp_field(response, "eval_count", None)
            done_reason = _resp_field(response, "done_reason", None)

            meta = {
                "prompt_chars": len(prompt),
                "prompt_tokens": prompt_tokens,
                "output_tokens": output_tokens,
                "num_ctx": used_ctx,
                "num_predict": max_out,
                "done_reason": done_reason,
                "prompt_truncated": False,
                "output_cut_off": False,
            }

            if (
                isinstance(prompt_tokens, int)
                and isinstance(used_ctx, int)
                and prompt_tokens >= int(used_ctx * 0.98)
            ):
                meta["prompt_truncated"] = True
                logger.warning(
                    "Ollama prompt used %s of %s context tokens: the start "
                    "of the prompt was probably cut. Raise OLLAMA_NUM_CTX "
                    "or shorten the prompt.",
                    prompt_tokens,
                    used_ctx,
                )

            if done_reason == "length" or (
                isinstance(output_tokens, int)
                and isinstance(max_out, int)
                and max_out > 0
                and output_tokens >= max_out
            ):
                meta["output_cut_off"] = True
                logger.warning(
                    "Ollama answer hit the OLLAMA_NUM_PREDICT limit (%s): "
                    "the JSON is probably incomplete.",
                    max_out,
                )

            self.last_meta = meta

            if not content.strip():
                return {
                    "response": "",
                    "error": "Ollama returned an empty response.",
                    "meta": meta,
                }

            return {
                "response": content,
                "meta": meta,
            }

        except Exception as exc:
            error_message = str(exc)

            logger.error(
                "Ollama generation failed: %s",
                error_message,
            )

            return {
                "response": "",
                "error": error_message,
            }


# ============================================================================
# OPENAI
# ============================================================================


class OpenAIProvider(LLMProvider):
    """OpenAI API provider."""

    def __init__(
        self,
        api_key: str,
        model: str,
        timeout: float = 60,
    ) -> None:
        if not api_key:
            raise ValueError(
                "OPENAI_API_KEY is required for OpenAI provider."
            )

        try:
            from openai import OpenAI
        except ImportError as exc:
            raise ImportError(
                "openai package required for OpenAI provider. "
                "Install it with: pip install openai"
            ) from exc

        self.model = model
        self.timeout = timeout

        self.client = OpenAI(
            api_key=api_key,
            timeout=timeout,
        )

        logger.info(
            "OpenAI provider initialized: model=%s",
            self.model,
        )

    def generate(
        self,
        prompt: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        if not isinstance(prompt, str) or not prompt.strip():
            return {
                "response": "",
                "error": "Prompt is empty.",
            }

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a precise code analysis expert. "
                            "Return exactly one valid JSON object."
                        ),
                    },
                    {
                        "role": "user",
                        "content": prompt,
                    },
                ],
                temperature=0.0,
                response_format={
                    "type": "json_object",
                },
                **kwargs,
            )

            content = response.choices[0].message.content or ""

            if not content.strip():
                return {
                    "response": "",
                    "error": "OpenAI returned an empty response.",
                }

            return {
                "response": content,
            }

        except Exception as exc:
            error_message = str(exc)

            logger.error(
                "OpenAI generation failed: %s",
                error_message,
            )

            return {
                "response": "",
                "error": error_message,
            }


# ============================================================================
# GEMINI
# ============================================================================


class GeminiProvider(LLMProvider):
    """Google Gemini API provider."""

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-2.0-flash",
        fallback_models: list[str] | None = None,
        timeout: float = 60,
    ) -> None:
        if not api_key:
            raise ValueError(
                "GEMINI_API_KEY is required for Gemini provider."
            )

        try:
            from google import genai
        except ImportError as exc:
            raise ImportError(
                "google-genai package required. "
                "Install it with: pip install google-genai"
            ) from exc

        self.client = genai.Client(
            api_key=api_key,
        )

        self.primary_model = model
        self.fallback_models = fallback_models or []
        self.timeout = timeout

        self.all_models = [
            self.primary_model,
            *self.fallback_models,
        ]

        logger.info(
            "Gemini provider initialized: models=%s",
            self.all_models,
        )

    def generate(
        self,
        prompt: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        if not isinstance(prompt, str) or not prompt.strip():
            return {
                "response": "",
                "error": "Prompt is empty.",
            }

        attempted_models: list[str] = []
        last_error: Exception | None = None

        for model_name in self.all_models:
            attempted_models.append(model_name)

            try:
                logger.info(
                    "Gemini model attempt: %s",
                    model_name,
                )

                response = self.client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    **kwargs,
                )

                content = getattr(
                    response,
                    "text",
                    None,
                )

                if content is None:
                    content = ""

                content = str(content)

                if not content.strip():
                    raise RuntimeError(
                        f"Gemini model '{model_name}' returned "
                        "an empty response."
                    )

                logger.info(
                    "Gemini generation successful using: %s",
                    model_name,
                )

                return {
                    "response": content,
                }

            except Exception as exc:
                last_error = exc
                error_message = str(exc)

                logger.warning(
                    "Gemini model '%s' failed: %s",
                    model_name,
                    error_message,
                )

                # Only continue to another Gemini model for errors that
                # plausibly indicate temporary availability or model
                # availability problems.
                if not _is_temporary_provider_error(
                    error_message
                ):
                    return {
                        "response": "",
                        "error": error_message,
                    }

        attempted = ", ".join(attempted_models)

        return {
            "response": "",
            "error": (
                f"All Gemini models failed. "
                f"Attempted: {attempted}. "
                f"Last error: {last_error}"
            ),
        }


# ============================================================================
# GROQ
# ============================================================================


class GroqProvider(LLMProvider):
    """Groq API provider."""

    def __init__(
        self,
        api_key: str,
        model: str = "llama-3.3-70b-versatile",
        timeout: float = 60,
    ) -> None:
        if not api_key:
            raise ValueError(
                "GROQ_API_KEY is required for Groq provider."
            )

        try:
            from groq import Groq
        except ImportError as exc:
            raise ImportError(
                "groq package required. "
                "Install it with: pip install groq"
            ) from exc

        self.model = model
        self.timeout = timeout

        self.client = Groq(
            api_key=api_key,
        )

        logger.info(
            "Groq provider initialized: model=%s",
            self.model,
        )

    def generate(
        self,
        prompt: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        if not isinstance(prompt, str) or not prompt.strip():
            return {
                "response": "",
                "error": "Prompt is empty.",
            }

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a precise code analysis expert. "
                            "Return exactly one valid JSON object."
                        ),
                    },
                    {
                        "role": "user",
                        "content": prompt,
                    },
                ],
                temperature=0.0,
                max_completion_tokens=750,
                timeout=self.timeout,
                **kwargs,
            )

            content = response.choices[0].message.content or ""

            if not content.strip():
                return {
                    "response": "",
                    "error": "Groq returned an empty response.",
                }

            return {
                "response": content,
            }

        except Exception as exc:
            error_message = str(exc)

            logger.error(
                "Groq generation failed: %s",
                error_message,
            )

            return {
                "response": "",
                "error": error_message,
            }


# ============================================================================
# ERROR CLASSIFICATION
# ============================================================================


def _is_temporary_provider_error(
    error_message: str,
) -> bool:
    """
    Determine whether an error is reasonable to retry/fail over.

    This is intentionally conservative.

    Authentication and malformed-request errors should NOT cause arbitrary
    provider switching.
    """

    error = error_message.lower()

    temporary_patterns = (
        "503",
        "service unavailable",
        "unavailable",
        "429",
        "resource_exhausted",
        "rate limit",
        "rate_limit",
        "quota",
        "timeout",
        "timed out",
        "connection",
        "connection reset",
        "connection refused",
        "disconnected",
        "high demand",
        "overloaded",
        "temporarily unavailable",
        "502",
        "504",
    )

    return any(
        pattern in error
        for pattern in temporary_patterns
    )


# ============================================================================
# PROVIDER FACTORY
# ============================================================================


def create_llm_provider(
    provider_type: str | None = None,
) -> LLMProvider:
    """
    Create the configured LLM provider.

    Environment variables:

    LLM_PROVIDER
        ollama | gemini | groq | openai

    LLM_FAILOVER_PROVIDER
        Optional secondary provider.

    Ollama:
        OLLAMA_HOST
        OLLAMA_MODEL
        OLLAMA_TIMEOUT_SECONDS

    Gemini:
        GEMINI_API_KEY
        GEMINI_MODEL
        GEMINI_TIMEOUT_SECONDS

    Groq:
        GROQ_API_KEY
        GROQ_MODEL
        GROQ_TIMEOUT_SECONDS

    OpenAI:
        OPENAI_API_KEY
        OPENAI_MODEL
        OPENAI_TIMEOUT_SECONDS
    """

    # Auto-load the project .env so provider settings are always available
    # regardless of whether the caller has already loaded dotenv.
    try:
        from dotenv import load_dotenv as _load_dotenv
        import pathlib as _pathlib
        _env_file = _pathlib.Path(__file__).resolve().parents[4] / ".env"
        if _env_file.is_file():
            _load_dotenv(_env_file, override=False)
    except Exception:
        pass

    primary_type = (
        provider_type
        or os.getenv(
            "LLM_PROVIDER",
            "ollama",
        )
    ).strip().lower()

    failover_type = os.getenv(
        "LLM_FAILOVER_PROVIDER",
        "",
    ).strip().lower()

    primary_provider = _create_single_provider(
        primary_type
    )

    if (
        failover_type
        and failover_type != primary_type
    ):
        try:
            failover_provider = _create_single_provider(
                failover_type
            )

            logger.info(
                "LLM failover configured: %s -> %s",
                primary_type,
                failover_type,
            )

            return FailoverProvider(
                primary=primary_provider,
                failover=failover_provider,
                primary_name=primary_type,
                failover_name=failover_type,
            )

        except Exception as exc:
            # A broken optional failover must not prevent the configured
            # primary provider from operating.
            logger.warning(
                "Could not initialize failover provider '%s': %s",
                failover_type,
                exc,
            )

    return primary_provider


def _create_single_provider(
    provider_type: str,
) -> LLMProvider:
    """
    Create exactly one provider.

    No failover logic belongs here.
    """

    provider_type = provider_type.strip().lower()

    # ------------------------------------------------------------------------
    # OLLAMA
    # ------------------------------------------------------------------------

    if provider_type == "ollama":
        host = os.getenv(
            "OLLAMA_HOST",
            "http://localhost:11434",
        ).strip()

        model = os.getenv(
            "OLLAMA_MODEL",
            "qwen2.5-coder:3b-instruct-q4_K_M",
        ).strip()

        timeout = float(
            os.getenv(
                "OLLAMA_TIMEOUT_SECONDS",
                "120",
            )
        )

        if not host:
            raise ValueError(
                "OLLAMA_HOST cannot be empty."
            )

        if not model:
            raise ValueError(
                "OLLAMA_MODEL cannot be empty."
            )

        logger.info(
            "Creating Ollama provider: model=%s host=%s",
            model,
            host,
        )

        return OllamaProvider(
            host=host,
            model=model,
            timeout=timeout,
        )

    # ------------------------------------------------------------------------
    # GEMINI
    # ------------------------------------------------------------------------

    if provider_type == "gemini":
        api_key = os.getenv(
            "GEMINI_API_KEY"
        )

        if not api_key:
            raise ValueError(
                "GEMINI_API_KEY environment variable "
                "is required for Gemini provider."
            )

        model = os.getenv(
            "GEMINI_MODEL",
            "gemini-2.0-flash",
        ).strip()

        timeout = float(
            os.getenv(
                "GEMINI_TIMEOUT_SECONDS",
                "60",
            )
        )

        logger.info(
            "Creating Gemini provider: model=%s",
            model,
        )

        return GeminiProvider(
            api_key=api_key,
            model=model,
            fallback_models=[],
            timeout=timeout,
        )

    # ------------------------------------------------------------------------
    # GROQ
    # ------------------------------------------------------------------------

    if provider_type == "groq":
        api_key = os.getenv(
            "GROQ_API_KEY"
        )

        if not api_key:
            raise ValueError(
                "GROQ_API_KEY environment variable "
                "is required for Groq provider."
            )

        model = os.getenv(
            "GROQ_MODEL",
            "llama-3.3-70b-versatile",
        ).strip()

        timeout = float(
            os.getenv(
                "GROQ_TIMEOUT_SECONDS",
                "60",
            )
        )

        logger.info(
            "Creating Groq provider: model=%s",
            model,
        )

        return GroqProvider(
            api_key=api_key,
            model=model,
            timeout=timeout,
        )

    # ------------------------------------------------------------------------
    # OPENAI
    # ------------------------------------------------------------------------

    if provider_type == "openai":
        api_key = os.getenv(
            "OPENAI_API_KEY"
        )

        if not api_key:
            raise ValueError(
                "OPENAI_API_KEY environment variable "
                "is required for OpenAI provider."
            )

        model = os.getenv(
            "OPENAI_MODEL",
            "gpt-4o-mini",
        ).strip()

        timeout = float(
            os.getenv(
                "OPENAI_TIMEOUT_SECONDS",
                "60",
            )
        )

        logger.info(
            "Creating OpenAI provider: model=%s",
            model,
        )

        return OpenAIProvider(
            api_key=api_key,
            model=model,
            timeout=timeout,
        )

    raise ValueError(
        f"Unknown LLM provider: {provider_type}. "
        "Supported providers: ollama, gemini, groq, openai."
    )


# ============================================================================
# FAILOVER PROVIDER
# ============================================================================


class FailoverProvider(LLMProvider):
    """
    Primary -> secondary provider failover.

    The secondary provider is used only when the primary provider fails
    without returning usable response content and the error appears temporary.
    """

    def __init__(
        self,
        primary: LLMProvider,
        failover: LLMProvider,
        primary_name: str,
        failover_name: str,
    ) -> None:
        self.primary = primary
        self.failover = failover
        self.primary_name = primary_name
        self.failover_name = failover_name

    def generate(
        self,
        prompt: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        # --------------------------------------------------------------------
        # Primary
        # --------------------------------------------------------------------

        primary_result = self.primary.generate(
            prompt,
            **kwargs,
        )

        primary_response = primary_result.get(
            "response",
            "",
        )

        if isinstance(
            primary_response,
            str
        ) and primary_response.strip():
            return primary_result

        primary_error = str(
            primary_result.get(
                "error",
                "Unknown primary-provider error.",
            )
        )

        # --------------------------------------------------------------------
        # Decide whether failover is justified
        # --------------------------------------------------------------------

        if not _is_temporary_provider_error(
            primary_error
        ):
            logger.error(
                "Primary provider '%s' failed with "
                "non-temporary error: %s",
                self.primary_name,
                primary_error,
            )

            return primary_result

        # --------------------------------------------------------------------
        # Secondary
        # --------------------------------------------------------------------

        logger.warning(
            "Primary provider '%s' failed temporarily. "
            "Trying failover provider '%s'.",
            self.primary_name,
            self.failover_name,
        )

        failover_result = self.failover.generate(
            prompt,
            **kwargs,
        )

        failover_response = failover_result.get(
            "response",
            "",
        )

        if isinstance(
            failover_response,
            str
        ) and failover_response.strip():
            logger.info(
                "Failover provider '%s' succeeded.",
                self.failover_name,
            )

            return failover_result

        failover_error = str(
            failover_result.get(
                "error",
                "Unknown failover-provider error.",
            )
        )

        logger.error(
            "Both providers failed. "
            "Primary=%s; Failover=%s",
            primary_error[:200],
            failover_error[:200],
        )

        return {
            "response": "",
            "error": (
                f"Primary provider '{self.primary_name}' failed: "
                f"{primary_error}; "
                f"Failover provider '{self.failover_name}' failed: "
                f"{failover_error}"
            ),
        }


# ============================================================================
# SECRET REDACTION
# ============================================================================


def redact_secrets(
    text: str,
) -> str:
    """
    Lightweight redaction helper.

    This function is intentionally independent of the provider calls.
    """

    import re

    if not isinstance(text, str):
        return text

    # API keys
    text = re.sub(
        r"(api[\-_]?key|apikey)"
        r"[\s:=]+"
        r"['\"]?"
        r"([a-zA-Z0-9_\-]{20,})"
        r"['\"]?",
        r"\1=<REDACTED>",
        text,
        flags=re.IGNORECASE,
    )

    # Bearer tokens
    text = re.sub(
        r"bearer\s+"
        r"([a-zA-Z0-9_\-\.]{20,})",
        r"bearer <REDACTED>",
        text,
        flags=re.IGNORECASE,
    )

    # AWS access keys
    text = re.sub(
        r"(AKIA[A-Z0-9]{16})",
        r"<REDACTED_AWS_KEY>",
        text,
    )

    # AWS secret keys
    text = re.sub(
        r"(aws[\-_]?secret[\-_]?access[\-_]?key)"
        r"[\s:=]+"
        r"['\"]?"
        r"([a-zA-Z0-9/+=]{40})"
        r"['\"]?",
        r"\1=<REDACTED>",
        text,
        flags=re.IGNORECASE,
    )

    # Passwords
    text = re.sub(
        r"(password|passwd|pwd)"
        r"[\s:=]+"
        r"['\"]?"
        r"([^\s'\"]{8,})"
        r"['\"]?",
        r"\1=<REDACTED>",
        text,
        flags=re.IGNORECASE,
    )

    # Generic tokens
    text = re.sub(
        r"(token)"
        r"[\s:=]+"
        r"['\"]?"
        r"([a-zA-Z0-9_\-\.]{20,})"
        r"['\"]?",
        r"\1=<REDACTED>",
        text,
        flags=re.IGNORECASE,
    )

    # PEM private keys
    text = re.sub(
        r"-----BEGIN [A-Z ]+PRIVATE KEY-----"
        r".*?"
        r"-----END [A-Z ]+PRIVATE KEY-----",
        "-----BEGIN PRIVATE KEY-----"
        "<REDACTED>"
        "-----END PRIVATE KEY-----",
        text,
        flags=re.DOTALL,
    )

    return text