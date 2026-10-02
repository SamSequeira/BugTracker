"""
Deterministic Evidence Builder.

Assembles multi-file context, call chains, and module-level state interactions
into structured EvidencePackets for semantic bug verification. Also sanitizes
all outgoing code chunks against accidental secret/credential leakage.
"""

import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from app.services.llm_logic_reviewer.repository_index import (
    FunctionIndexEntry,
    ModuleLevelStateEntry,
    RepositoryIndex,
)


@dataclass
class EvidenceItem:
    qualname: str
    file_path: str
    line: int
    snippet: str
    role: str  # "caller", "callee", "shared_state_writer", "shared_state_reader", "db_mutator"


@dataclass
class SharedStateItem:
    name: str
    file_path: str
    line: int
    init_value: str
    readers: List[str] = field(default_factory=list)
    writers: List[str] = field(default_factory=list)


@dataclass
class EvidencePacket:
    target_qualname: str
    target_file: str
    target_lines: Tuple[int, int]
    target_source: str
    callers: List[EvidenceItem] = field(default_factory=list)
    callees: List[EvidenceItem] = field(default_factory=list)
    shared_state: List[SharedStateItem] = field(default_factory=list)
    api_routes: List[str] = field(default_factory=list)
    is_complete: bool = True
    unresolved: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Secret Redaction
# ---------------------------------------------------------------------------

SECRET_PATTERNS = [
    # API key patterns (OpenAI, generic Bearer, AWS, GitHub)
    (r"\bsk-[a-zA-Z0-9_\-]{20,}\b", "sk-[REDACTED]"),
    (r"\bgh[pousr]-[a-zA-Z0-9]{20,}\b", "gh-[REDACTED]"),
    (r"\bAKIA[0-9A-Z]{16}\b", "AKIA[REDACTED]"),
    # Bearer token
    (r"Bearer\s+[A-Za-z0-9_\-\.]{15,}", "Bearer [REDACTED]"),
    # Key / password assignment patterns
    (r"""(?i)(api[_-]?key|secret|password|passwd|auth[_-]?token|access[_-]?token|private[_-]?key)\s*([:=])\s*['"][^'"]{4,}['"]""", r'\1\2"[REDACTED]"'),
    # Database connection URI credentials (postgres://user:pass@host)
    (r"(postgres(?:ql)?|mysql|mongodb(?:\\+srv)?):\/\/([^:]+):([^@]+)@", r"\1://\2:[REDACTED]@"),
]


def redact_secrets(text: str) -> str:
    """Sanitize strings by removing credentials, tokens, and private keys."""
    if not text:
        return text
    sanitized = text
    for pattern, repl in SECRET_PATTERNS:
        sanitized = re.sub(pattern, repl, sanitized)
    return sanitized


# ---------------------------------------------------------------------------
# Cross-File Evidence Assembly
# ---------------------------------------------------------------------------

def build_cross_file_evidence(
    func_qualname: str,
    repo_index: RepositoryIndex,
    max_snippet_chars: int = 1500,
) -> EvidencePacket:
    """
    Assemble cross-file context (callers, callees, shared state readers/writers)
    into a structured EvidencePacket.
    """
    target_fn = repo_index.functions_by_qualname.get(func_qualname)
    if not target_fn:
        # Fallback by name lookup
        target_fn = repo_index.find_function(func_qualname.split("::")[-1])

    if not target_fn:
        return EvidencePacket(
            target_qualname=func_qualname,
            target_file="",
            target_lines=(0, 0),
            target_source="",
            is_complete=False,
            unresolved=[func_qualname],
        )

    # 1. Callers
    callers: List[EvidenceItem] = []
    caller_entries = repo_index.find_callers_by_qualname(target_fn.qualname)
    if not caller_entries:
        caller_entries = repo_index.find_callers(target_fn.name)

    for c in caller_entries:
        if c.qualname == target_fn.qualname:
            continue
        callers.append(
            EvidenceItem(
                qualname=c.qualname,
                file_path=c.file_path,
                line=c.start_line,
                snippet=redact_secrets(c.code_snippet[:max_snippet_chars]),
                role="caller",
            )
        )

    # 2. Callees
    callees: List[EvidenceItem] = []
    callee_entries = repo_index.find_callees_by_qualname(target_fn.qualname)
    if not callee_entries:
        callee_entries = repo_index.find_callees(target_fn.name)

    for c in callee_entries:
        if c.qualname == target_fn.qualname:
            continue
        callees.append(
            EvidenceItem(
                qualname=c.qualname,
                file_path=c.file_path,
                line=c.start_line,
                snippet=redact_secrets(c.code_snippet[:max_snippet_chars]),
                role="callee",
            )
        )

    # 3. Module-level shared state
    shared_state: List[SharedStateItem] = []
    file_state = repo_index.get_module_level_state(target_fn.file_path)
    for s in file_state:
        shared_state.append(
            SharedStateItem(
                name=s.name,
                file_path=s.file_path,
                line=s.line,
                init_value=s.init_value,
                readers=list(s.readers),
                writers=list(s.writers),
            )
        )

    # Also scan for state variables referenced across all files if relevant
    for fp, s_list in repo_index.module_level_state.items():
        if fp == target_fn.file_path.replace("\\", "/"):
            continue
        for s in s_list:
            if s.name in target_fn.code_snippet:
                shared_state.append(
                    SharedStateItem(
                        name=s.name,
                        file_path=s.file_path,
                        line=s.line,
                        init_value=s.init_value,
                        readers=list(s.readers),
                        writers=list(s.writers),
                    )
                )

    # 4. API routes
    api_routes: List[str] = list(target_fn.api_references)
    for c in callers:
        fn = repo_index.functions_by_qualname.get(c.qualname)
        if fn and fn.api_references:
            api_routes.extend(fn.api_references)

    return EvidencePacket(
        target_qualname=target_fn.qualname,
        target_file=target_fn.file_path,
        target_lines=(target_fn.start_line, target_fn.end_line),
        target_source=redact_secrets(target_fn.code_snippet),
        callers=callers[:5],
        callees=callees[:5],
        shared_state=shared_state,
        api_routes=list(set(api_routes))[:5],
        is_complete=True,
    )


def build_cache_chain(
    cache_var_name: str,
    file_path: str,
    repo_index: RepositoryIndex,
) -> dict:
    """
    Assembles evidence for cache-staleness / invalidation analysis:
    - Identifies functions reading the cache
    - Identifies functions writing to the cache
    - Identifies database-mutating functions in the same domain that fail to invalidate the cache
    """
    readers = repo_index.find_shared_state_readers(cache_var_name, file_path=file_path)
    writers = repo_index.find_shared_state_writers(cache_var_name, file_path=file_path)

    # Find DB mutating functions in repository
    db_mutators = []
    for fn in repo_index.functions_by_qualname.values():
        if fn.db_model_references or any(db_kw in fn.code_snippet.lower() for db_kw in ("db.commit", "db.delete", "db.add")):
            db_mutators.append(fn)

    return {
        "cache_variable": cache_var_name,
        "file_path": file_path,
        "readers": [r.qualname for r in readers],
        "writers": [w.qualname for w in writers],
        "potential_uninvalidated_mutators": [m.qualname for m in db_mutators if m.qualname not in [w.qualname for w in writers]][:5],
    }


def build_mutation_chain(
    db_mutating_func_qualname: str,
    repo_index: RepositoryIndex,
) -> dict:
    """
    Trace: DB write -> shared state -> stale reads
    """
    fn = repo_index.functions_by_qualname.get(db_mutating_func_qualname)
    if not fn:
        return {}

    # Check if this mutator invalidates any cache
    invalidated_caches = []
    for fp, states in repo_index.module_level_state.items():
        for state in states:
            if state.name in fn.code_snippet:
                invalidated_caches.append(state.name)

    return {
        "mutator_qualname": db_mutating_func_qualname,
        "file_path": fn.file_path,
        "invalidated_caches": invalidated_caches,
        "all_repo_caches": [s.name for states in repo_index.module_level_state.values() for s in states],
    }
