"""
technology_detector.py
-----------------------
Deterministic technology stack detector for repositories.
Analyzes dependency manifests (requirements.txt, package.json, pom.xml,
build.gradle, Dockerfile, docker-compose.yml, etc.) and AST metrics.
"""

import json
import re
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.models.analysis_technology import AnalysisTechnology


# Directory names that should never be traversed for manifest detection
IGNORED_DIRS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    "site-packages",
    ".idea",
    ".vscode",
    "dist",
    "build",
    ".next",
    ".cache",
}

# Category Priority Ordering (Primary / Core stack technologies ranked first)
CATEGORY_PRIORITY: Dict[str, int] = {
    "Programming Language": 1,
    "Framework": 2,
    "Frontend": 3,
    "Database": 4,
    "Database/ORM": 5,
    "Infrastructure": 6,
    "Testing": 7,
    "Build Tool": 8,
    "State Management": 9,
    "Security/Auth": 10,
    "Cloud/SDK": 11,
    "Data/Analytics": 12,
    "Language/Tooling": 13,
    "Language/Runtime": 14,
    "Utility/Library": 15,
    "Library/Package": 16,
}

PRIMARY_CATEGORIES = {
    "Programming Language",
    "Framework",
    "Frontend",
    "Database",
    "Database/ORM",
    "Infrastructure",
    "Testing",
    "Build Tool",
    "State Management",
}


# Category & Canonical Name Mappings
TECH_KNOWLEDGE_BASE: Dict[str, Tuple[str, str]] = {
    # Python Frameworks & Libs
    "fastapi": ("FastAPI", "Framework"),
    "django": ("Django", "Framework"),
    "flask": ("Flask", "Framework"),
    "starlette": ("Starlette", "Framework"),
    "tornado": ("Tornado", "Framework"),
    "pyramid": ("Pyramid", "Framework"),
    "uvicorn": ("Uvicorn", "Infrastructure"),
    "gunicorn": ("Gunicorn", "Infrastructure"),
    "celery": ("Celery", "Infrastructure"),
    "sqlalchemy": ("SQLAlchemy", "Database/ORM"),
    "alembic": ("Alembic", "Database/ORM"),
    "psycopg2": ("Psycopg2 (PostgreSQL)", "Database/ORM"),
    "psycopg2-binary": ("Psycopg2 (PostgreSQL)", "Database/ORM"),
    "asyncpg": ("Asyncpg (PostgreSQL)", "Database/ORM"),
    "aiomysql": ("AioMySQL", "Database/ORM"),
    "aiosqlite": ("AioSQLite", "Database/ORM"),
    "pymongo": ("PyMongo", "Database/ORM"),
    "motor": ("Motor (MongoDB)", "Database/ORM"),
    "redis": ("Redis", "Database"),
    "chromadb": ("ChromaDB", "Database"),
    "tortoise-orm": ("Tortoise-ORM", "Database/ORM"),
    "peewee": ("Peewee", "Database/ORM"),
    "pydantic": ("Pydantic", "Utility/Library"),
    "pydantic-settings": ("Pydantic Settings", "Utility/Library"),
    "pydantic_core": ("Pydantic Core", "Utility/Library"),
    "pytest": ("Pytest", "Testing"),
    "pytest-asyncio": ("Pytest AsyncIO", "Testing"),
    "unittest": ("Unittest", "Testing"),
    "pyjwt": ("PyJWT", "Security/Auth"),
    "pwdlib": ("Pwdlib", "Security/Auth"),
    "passlib": ("Passlib", "Security/Auth"),
    "cryptography": ("Cryptography", "Security/Auth"),
    "bcrypt": ("Bcrypt", "Security/Auth"),
    "python-jose": ("Python-Jose", "Security/Auth"),
    "email-validator": ("Email Validator", "Utility/Library"),
    "tree-sitter": ("Tree-Sitter", "Utility/Library"),
    "tree-sitter-python": ("Tree-Sitter Python", "Utility/Library"),
    "tree-sitter-javascript": ("Tree-Sitter JavaScript", "Utility/Library"),
    "tree-sitter-java": ("Tree-Sitter Java", "Utility/Library"),
    "boto3": ("Boto3 (AWS SDK)", "Cloud/SDK"),
    "botocore": ("Botocore", "Cloud/SDK"),
    "python-dotenv": ("Python Dotenv", "Utility/Library"),
    "requests": ("Requests", "Utility/Library"),
    "httpx": ("HTTPX", "Utility/Library"),
    "aiohttp": ("AioHTTP", "Utility/Library"),
    "pandas": ("Pandas", "Data/Analytics"),
    "numpy": ("NumPy", "Data/Analytics"),
    "sentence-transformers": ("Sentence Transformers", "Data/Analytics"),
    "transformers": ("Hugging Face Transformers", "Data/Analytics"),
    "torch": ("PyTorch", "Data/Analytics"),
    "onnxruntime": ("ONNX Runtime", "Data/Analytics"),

    # JavaScript / TypeScript Ecosystem
    "react": ("React", "Frontend"),
    "react-dom": ("React DOM", "Frontend"),
    "vue": ("Vue.js", "Frontend"),
    "angular": ("Angular", "Frontend"),
    "@angular/core": ("Angular", "Frontend"),
    "next": ("Next.js", "Framework"),
    "nuxt": ("Nuxt.js", "Framework"),
    "svelte": ("Svelte", "Frontend"),
    "express": ("Express.js", "Framework"),
    "nestjs": ("NestJS", "Framework"),
    "@nestjs/core": ("NestJS", "Framework"),
    "fastify": ("Fastify", "Framework"),
    "koa": ("Koa", "Framework"),
    "redux": ("Redux", "State Management"),
    "@reduxjs/toolkit": ("Redux Toolkit", "State Management"),
    "zustand": ("Zustand", "State Management"),
    "mobx": ("MobX", "State Management"),
    "tailwindcss": ("Tailwind CSS", "Frontend"),
    "bootstrap": ("Bootstrap", "Frontend"),
    "@mui/material": ("Material-UI", "Frontend"),
    "antd": ("Ant Design", "Frontend"),
    "lucide-react": ("Lucide Icons", "Frontend"),
    "prisma": ("Prisma", "Database/ORM"),
    "@prisma/client": ("Prisma Client", "Database/ORM"),
    "typeorm": ("TypeORM", "Database/ORM"),
    "mongoose": ("Mongoose", "Database/ORM"),
    "sequelize": ("Sequelize", "Database/ORM"),
    "drizzle-orm": ("Drizzle ORM", "Database/ORM"),
    "pg": ("node-postgres", "Database/ORM"),
    "mysql2": ("MySQL2", "Database/ORM"),
    "axios": ("Axios", "Utility/Library"),
    "typescript": ("TypeScript", "Programming Language"),
    "vite": ("Vite", "Build Tool"),
    "webpack": ("Webpack", "Build Tool"),
    "jest": ("Jest", "Testing"),
    "vitest": ("Vitest", "Testing"),
    "cypress": ("Cypress", "Testing"),
    "playwright": ("Playwright", "Testing"),
    "jsonwebtoken": ("JSON Web Token", "Security/Auth"),

    # Java Ecosystem
    "spring-boot": ("Spring Boot", "Framework"),
    "spring-boot-starter-web": ("Spring Boot Web", "Framework"),
    "spring-boot-starter-data-jpa": ("Spring Data JPA", "Database/ORM"),
    "spring-boot-starter-security": ("Spring Security", "Security/Auth"),
    "hibernate-core": ("Hibernate", "Database/ORM"),
    "junit-jupiter": ("JUnit 5", "Testing"),
    "junit": ("JUnit", "Testing"),
    "mockito-core": ("Mockito", "Testing"),
    "lombok": ("Lombok", "Utility/Library"),
    "jackson-databind": ("Jackson", "Utility/Library"),

    # Infrastructure & Databases
    "docker": ("Docker", "Infrastructure"),
    "docker-compose": ("Docker Compose", "Infrastructure"),
    "docker compose": ("Docker Compose", "Infrastructure"),
    "kubernetes": ("Kubernetes", "Infrastructure"),
    "nginx": ("Nginx", "Infrastructure"),
    "postgresql": ("PostgreSQL", "Database"),
    "postgres": ("PostgreSQL", "Database"),
    "mysql": ("MySQL", "Database"),
    "mongodb": ("MongoDB", "Database"),
    "sqlite": ("SQLite", "Database"),
    "sqlite3": ("SQLite", "Database"),
    "elasticsearch": ("Elasticsearch", "Database"),
    "rabbitmq": ("RabbitMQ", "Infrastructure"),
}


class TechnologyDetector:
    """Detects technologies and frameworks present in a code repository."""

    def _clean_version(self, raw_ver: str) -> Optional[str]:
        """Strip comparison operators, carets, and tildes to yield a clean version."""
        if not raw_ver:
            return None
        cleaned = re.sub(r"^[=><^~!\s]+", "", raw_ver.strip())
        cleaned = cleaned.split(",")[0].strip()  # Take the primary version if comma-separated
        return cleaned if cleaned else None

    def _parse_requirements_txt(self, path: Path) -> List[Dict[str, Any]]:
        """Parse Python requirements.txt file."""
        findings = []
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
            for line in content.splitlines():
                line = line.strip()
                if not line or line.startswith("#") or line.startswith("-"):
                    continue
                match = re.match(r"^([a-zA-Z0-9_\-\.]+)(?:([=><^~!]+.*))?", line)
                if match:
                    pkg_name = match.group(1).lower()
                    raw_version = match.group(2)
                    version = self._clean_version(raw_version) if raw_version else None
                    findings.append({
                        "raw_name": pkg_name,
                        "version": version,
                        "source": "requirements.txt",
                    })
        except Exception:
            pass
        return findings

    def _parse_pyproject_toml(self, path: Path) -> List[Dict[str, Any]]:
        """Parse dependencies from pyproject.toml."""
        findings = []
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
            # Simple line parser for dependencies section
            in_deps = False
            for line in content.splitlines():
                line = line.strip()
                if re.match(r"^\[.*dependencies.*\]", line, re.IGNORECASE):
                    in_deps = True
                    continue
                elif line.startswith("["):
                    in_deps = False

                if in_deps and "=" in line:
                    parts = line.split("=", 1)
                    pkg = parts[0].strip().strip('"').strip("'").lower()
                    ver_part = parts[1].strip().strip('"').strip("'")
                    ver = self._clean_version(ver_part)
                    findings.append({
                        "raw_name": pkg,
                        "version": ver,
                        "source": "pyproject.toml",
                    })
                elif in_deps and line.startswith('"') or line.startswith("'"):
                    # PEP 621 style dependencies list
                    dep_str = line.strip(',"\'')
                    match = re.match(r"^([a-zA-Z0-9_\-\.]+)(?:([=><^~!]+.*))?", dep_str)
                    if match:
                        findings.append({
                            "raw_name": match.group(1).lower(),
                            "version": self._clean_version(match.group(2)) if match.group(2) else None,
                            "source": "pyproject.toml",
                        })
        except Exception:
            pass
        return findings

    def _parse_package_json(self, path: Path) -> List[Dict[str, Any]]:
        """Parse dependencies from package.json."""
        findings = []
        try:
            data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
            all_deps = {}
            if "dependencies" in data and isinstance(data["dependencies"], dict):
                all_deps.update(data["dependencies"])
            if "devDependencies" in data and isinstance(data["devDependencies"], dict):
                all_deps.update(data["devDependencies"])

            for pkg, raw_ver in all_deps.items():
                findings.append({
                    "raw_name": pkg.lower(),
                    "version": self._clean_version(str(raw_ver)),
                    "source": "package.json",
                })
        except Exception:
            pass
        return findings

    def _parse_pom_xml(self, path: Path) -> List[Dict[str, Any]]:
        """Parse dependencies from Maven pom.xml."""
        findings = []
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
            dep_pattern = re.compile(
                r"<dependency>.*?<artifactId>(.*?)</artifactId>.*?(?:<version>(.*?)</version>.*?)?</dependency>",
                re.DOTALL | re.IGNORECASE,
            )
            for match in dep_pattern.finditer(content):
                artifact_id = match.group(1).strip().lower()
                version = self._clean_version(match.group(2)) if match.group(2) else None
                findings.append({
                    "raw_name": artifact_id,
                    "version": version,
                    "source": "pom.xml",
                })
        except Exception:
            pass
        return findings

    def _parse_dockerfile(self, path: Path) -> List[Dict[str, Any]]:
        """Parse Dockerfile base images and runtime technologies."""
        findings = [{"raw_name": "docker", "version": None, "source": "Dockerfile"}]
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
            for line in content.splitlines():
                line = line.strip()
                if line.upper().startswith("FROM "):
                    parts = line.split()[1].split(":")
                    image_name = parts[0].lower()
                    image_tag = parts[1] if len(parts) > 1 else None
                    clean_tag = image_tag.split("-")[0] if image_tag else None

                    if "python" in image_name:
                        findings.append({"raw_name": "python", "version": clean_tag, "source": "Dockerfile"})
                    elif "node" in image_name:
                        findings.append({"raw_name": "node.js", "version": clean_tag, "source": "Dockerfile"})
                    elif "openjdk" in image_name or "java" in image_name:
                        findings.append({"raw_name": "java", "version": clean_tag, "source": "Dockerfile"})
                    elif "postgres" in image_name:
                        findings.append({"raw_name": "postgresql", "version": clean_tag, "source": "Dockerfile"})
                    elif "redis" in image_name:
                        findings.append({"raw_name": "redis", "version": clean_tag, "source": "Dockerfile"})
                    elif "nginx" in image_name:
                        findings.append({"raw_name": "nginx", "version": clean_tag, "source": "Dockerfile"})
        except Exception:
            pass
        return findings

    def _parse_docker_compose(self, path: Path) -> List[Dict[str, Any]]:
        """Parse docker-compose.yml services and images."""
        findings = [{"raw_name": "docker compose", "version": None, "source": path.name}]
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
            for line in content.splitlines():
                line = line.strip()
                if line.startswith("image:"):
                    parts = line.split(":", 1)[1].strip().split(":")
                    image = parts[0].lower()
                    tag = parts[1] if len(parts) > 1 else None
                    clean_tag = tag.split("-")[0] if tag else None

                    if "postgres" in image:
                        findings.append({"raw_name": "postgresql", "version": clean_tag, "source": path.name})
                    elif "redis" in image:
                        findings.append({"raw_name": "redis", "version": clean_tag, "source": path.name})
                    elif "mongo" in image:
                        findings.append({"raw_name": "mongodb", "version": clean_tag, "source": path.name})
                    elif "mysql" in image or "mariadb" in image:
                        findings.append({"raw_name": "mysql", "version": clean_tag, "source": path.name})
                    elif "nginx" in image:
                        findings.append({"raw_name": "nginx", "version": clean_tag, "source": path.name})
                    elif "rabbitmq" in image:
                        findings.append({"raw_name": "rabbitmq", "version": clean_tag, "source": path.name})
                    elif "elasticsearch" in image:
                        findings.append({"raw_name": "elasticsearch", "version": clean_tag, "source": path.name})
        except Exception:
            pass
        return findings

    def detect_technologies(
        self,
        repo_path: str,
        analysis_run_id: str,
        ast_result: Optional[Dict[str, Any]] = None,
    ) -> List[AnalysisTechnology]:
        """
        Scan repository directory and AST summary to extract all technologies.
        Returns deduplicated List of AnalysisTechnology ORM objects.
        """
        root = Path(repo_path)
        detected_map: Dict[str, Dict[str, Any]] = {}

        if not root.exists():
            return []

        # 1. Scan for manifest files
        for p in root.rglob("*"):
            if not p.is_file():
                continue
            if any(part in IGNORED_DIRS for part in p.parts):
                continue
            name = p.name.lower()

            raw_findings = []
            if name == "requirements.txt":
                raw_findings = self._parse_requirements_txt(p)
            elif name == "pyproject.toml":
                raw_findings = self._parse_pyproject_toml(p)
            elif name == "package.json":
                raw_findings = self._parse_package_json(p)
            elif name == "pom.xml":
                raw_findings = self._parse_pom_xml(p)
            elif name == "dockerfile" or name.startswith("dockerfile."):
                raw_findings = self._parse_dockerfile(p)
            elif name in ("docker-compose.yml", "docker-compose.yaml"):
                raw_findings = self._parse_docker_compose(p)

            for item in raw_findings:
                raw_key = item["raw_name"]
                if raw_key in TECH_KNOWLEDGE_BASE:
                    canonical_name, category = TECH_KNOWLEDGE_BASE[raw_key]
                elif raw_key in ("docker", "docker compose", "postgresql", "redis", "mongodb", "mysql", "nginx", "rabbitmq", "elasticsearch", "python", "node.js", "java"):
                    canonical_name = raw_key.title()
                    category = "Infrastructure" if raw_key in ("docker", "docker compose", "nginx") else ("Database" if raw_key in ("postgresql", "redis", "mongodb", "mysql", "elasticsearch") else "Language/Runtime")
                else:
                    canonical_name = raw_key.replace("-", " ").replace("_", " ").title()
                    category = "Library/Package"

                unique_key = canonical_name.lower()
                if unique_key not in detected_map or (item["version"] and not detected_map[unique_key].get("version")):
                    detected_map[unique_key] = {
                        "name": canonical_name,
                        "category": category,
                        "version": item.get("version"),
                        "detection_source": item.get("source"),
                    }

        # 2. Add language runtimes from AST scan if not present
        if ast_result and "languages_detected" in ast_result:
            for lang, count in ast_result["languages_detected"].items():
                if count > 0:
                    lang_key = lang.lower()
                    if lang_key not in detected_map:
                        detected_map[lang_key] = {
                            "name": lang,
                            "category": "Programming Language",
                            "version": None,
                            "detection_source": "AST Code Analysis",
                        }

        # 3. Sort technologies deterministically by category priority and name
        sorted_items = sorted(
            detected_map.values(),
            key=lambda x: (
                CATEGORY_PRIORITY.get(x["category"], 99),
                x["name"].lower(),
            ),
        )

        # 4. Instantiate ORM objects
        orm_technologies: List[AnalysisTechnology] = []
        for item in sorted_items:
            orm_technologies.append(
                AnalysisTechnology(
                    id=str(uuid.uuid4()),
                    analysis_run_id=analysis_run_id,
                    name=item["name"],
                    category=item["category"],
                    version=item["version"],
                    detection_source=item["detection_source"],
                )
            )

        return orm_technologies


technology_detector = TechnologyDetector()
