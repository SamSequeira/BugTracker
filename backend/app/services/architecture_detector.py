"""
architecture_detector.py
------------------------
Deterministic repository topology and architectural component detector.
Discovers logical architectural layers/components from directory structures
and file roles, and maps source files to their respective components.
"""

import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from app.models.architecture_component import ArchitectureComponent


# Layer Pattern Definitions: (pattern_keywords, component_name, component_type, description, default_role)
LAYER_DEFINITIONS = [
    (
        {"api", "routes", "routers", "controllers", "endpoints", "handlers", "rest", "graphql"},
        "API & Endpoints Layer",
        "api_layer",
        "Handles incoming HTTP/RPC requests, parameter validation, routing, and response serialization.",
        "API Request Handler / Controller",
    ),
    (
        {"services", "service", "core", "engine", "pipeline", "workers", "usecases", "domain", "managers", "jobs"},
        "Business Logic & Services",
        "service_layer",
        "Orchestrates business workflows, domain logic, pipeline execution, and service integrations.",
        "Business Service / Orchestrator",
    ),
    (
        {"models", "model", "repositories", "repository", "database", "db", "dao", "schemas", "entities", "alembic", "migrations"},
        "Data Persistence & Models",
        "persistence_layer",
        "Defines database schema entities, data validation schemas, and persistence repositories.",
        "Data Model / Persistence Accessor",
    ),
    (
        {"auth", "security", "guards", "middleware", "permissions"},
        "Authentication & Security",
        "security_layer",
        "Manages user authentication, authorization policies, session tokens, and cryptographic security.",
        "Security & Authentication Handler",
    ),
    (
        {"frontend", "components", "pages", "views", "ui", "templates", "styles", "layouts"},
        "User Interface & Presentation",
        "frontend_layer",
        "Renders frontend pages, interactive UI components, design elements, and client presentation.",
        "UI View / Component",
    ),
    (
        {"config", "docker", "deploy", "infrastructure", "infra", "ci", "scripts", "build"},
        "Infrastructure & Configuration",
        "infrastructure_layer",
        "Manages system configuration, environment settings, deployment containers, and automation.",
        "Infrastructure & Config Module",
    ),
    (
        {"utils", "util", "common", "helpers", "shared", "lib"},
        "Utilities & Shared Helpers",
        "utility_layer",
        "Provides cross-cutting helper functions, formatting routines, and shared library utilities.",
        "Utility / Helper Routine",
    ),
    (
        {"tests", "test", "spec", "specs", "__tests__"},
        "Automated Test Suite",
        "test_layer",
        "Contains automated unit tests, integration test fixtures, and regression test suites.",
        "Test Suite / Fixture",
    ),
]


class ArchitectureDetector:
    """Detects architectural components from repository file topology and assigns files to components."""

    def _normalize_path(self, path_str: str) -> str:
        """Normalize file path to forward slashes without leading/trailing slashes."""
        return path_str.replace("\\", "/").strip("/")

    def _classify_path(self, norm_path: str) -> Tuple[str, str, str, str, str]:
        """
        Classify a file path against known architectural layer patterns.
        Returns: (component_name, component_type, description, root_path_matched, default_role)
        """
        parts = [p.lower() for p in norm_path.split("/")]

        for keywords, name, c_type, desc, default_role in LAYER_DEFINITIONS:
            for idx, part in enumerate(parts[:-1]):  # check directories
                if part in keywords:
                    # Find root path of this component
                    root_path = "/".join(norm_path.split("/")[:idx + 1])
                    return name, c_type, desc, root_path, default_role

            # Also check filename if top level
            if len(parts) == 1 or parts[-1] in keywords:
                file_stem = Path(parts[-1]).stem
                if any(kw in file_stem for kw in keywords):
                    return name, c_type, desc, parts[0], default_role

        # Fallback for core/entrypoint files
        file_name = parts[-1] if parts else ""
        if file_name in ("main.py", "app.py", "index.js", "server.js", "index.ts", "server.ts", "Main.java"):
            return (
                "Core Application Entrypoint",
                "application_core",
                "Primary application bootstrap and initialization entrypoint.",
                "/",
                "Application Entrypoint",
            )

        return (
            "Application Module",
            "general_module",
            "General repository application modules and codebase files.",
            "/",
            "Application Source File",
        )

    def _infer_intent(self, file_path: str, role: str) -> str:
        """Deterministically infer high-level intent from filename and role."""
        p = Path(file_path)
        stem = p.stem.replace("_", " ").replace("-", " ")

        if "auth" in stem.lower() or "login" in stem.lower():
            return "Handles authentication, token verification, and credentials."
        elif "test" in stem.lower():
            return f"Executes verification and test cases for {stem}."
        elif "repo" in stem.lower() or "db" in stem.lower():
            return f"Encapsulates database operations and persistence for {stem}."
        elif "model" in stem.lower() or "schema" in stem.lower():
            return f"Defines data structures and entity schemas for {stem}."
        elif "service" in stem.lower():
            return f"Provides business logic workflows and processing for {stem}."
        elif "api" in stem.lower() or "router" in stem.lower():
            return f"Defines API endpoints and request routing for {stem}."
        elif "config" in stem.lower():
            return f"Manages configuration parameters and environment settings for {stem}."

        return f"Implements {stem} logic within the {role}."

    def detect_components(
        self,
        repo_path: str,
        analysis_run_id: str,
        files_data: List[Dict[str, Any]],
    ) -> Tuple[List[ArchitectureComponent], Dict[str, Dict[str, Any]]]:
        """
        Detect architectural components from file list and map files to components.

        Returns:
            Tuple of:
            1. List[ArchitectureComponent]: ORM instances ready for persistence.
            2. Dict[str, Dict[str, Any]]: Map of file_path -> {
                   "component_id": str,
                   "role": str,
                   "intent": str,
               }
        """
        detected_components: Dict[str, ArchitectureComponent] = {}
        file_mapping: Dict[str, Dict[str, Any]] = {}

        for f_data in files_data:
            fpath = f_data.get("file") or f_data.get("file_path") or ""
            if not fpath:
                continue

            # Strip repo_path prefix to get relative path for topology classification
            norm_path = self._normalize_path(fpath)
            if repo_path:
                norm_repo = self._normalize_path(repo_path)
                if norm_path.startswith(norm_repo):
                    norm_path = norm_path[len(norm_repo):].strip("/")

            c_name, c_type, c_desc, root_p, default_role = self._classify_path(norm_path)

            if c_name not in detected_components:
                component = ArchitectureComponent(
                    id=str(uuid.uuid4()),
                    analysis_run_id=analysis_run_id,
                    name=c_name,
                    description=c_desc,
                    component_type=c_type,
                    root_path=root_p,
                )
                detected_components[c_name] = component

            comp = detected_components[c_name]
            intent = self._infer_intent(fpath, default_role)

            file_mapping[fpath] = {
                "component_id": comp.id,
                "role": default_role,
                "intent": intent,
            }
            # Also index by relative/normalized paths for flexible matching
            file_mapping[norm_path] = file_mapping[fpath]
            file_mapping[Path(fpath).as_posix()] = file_mapping[fpath]

        components_list = list(detected_components.values())

        # Fallback if repository has no files or components detected
        if not components_list:
            fallback = ArchitectureComponent(
                id=str(uuid.uuid4()),
                analysis_run_id=analysis_run_id,
                name="Core Application Module",
                description="Primary application codebase and source modules.",
                component_type="application_core",
                root_path="/",
            )
            components_list.append(fallback)

        return components_list, file_mapping


architecture_detector = ArchitectureDetector()
