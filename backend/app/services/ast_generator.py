"""
AST Generator Service - Generates Abstract Syntax Trees for supported languages.
"""

import os
from pathlib import Path
from typing import Any, Dict, Optional
from tree_sitter import Language, Parser
import tree_sitter_python as tspython
import tree_sitter_javascript as tsjavascript
import tree_sitter_java as tsjava


class ASTGenerationError(Exception):
    """Raised when AST generation fails."""


class ASTGenerator:
    """Generates AST for Python, JavaScript, and Java code."""

    SUPPORTED_LANGUAGES = {
        "Python": [".py"],
        "JavaScript": [".js", ".jsx", ".mjs", ".cjs"],
        "Java": [".java"],
    }

    def __init__(self):
        """Initialize the AST generator with tree-sitter parsers."""
        self._parsers = {}
        self._init_parsers()

    def _init_parsers(self):
        try:
            # Create Tree-sitter language objects (handles tree-sitter >=0.22 and <0.22)
            try:
                py_language = Language(tspython.language())
            except TypeError:
                py_language = Language(tspython.language(), "python")

            try:
                java_language = Language(tsjava.language())
            except TypeError:
                java_language = Language(tsjava.language(), "java")

            try:
                js_language = Language(tsjavascript.language())
            except TypeError:
                js_language = Language(tsjavascript.language(), "javascript")

            # Create Python parser
            py_parser = Parser()
            if hasattr(py_parser, "set_language"):
                py_parser.set_language(py_language)
            else:
                py_parser.language = py_language

            # Create Java parser
            java_parser = Parser()
            if hasattr(java_parser, "set_language"):
                java_parser.set_language(java_language)
            else:
                java_parser.language = java_language

            # Create JavaScript parser
            js_parser = Parser()
            if hasattr(js_parser, "set_language"):
                js_parser.set_language(js_language)
            else:
                js_parser.language = js_language

            # Store parsers
            self._parsers["Python"] = py_parser
            self._parsers["Java"] = java_parser
            self._parsers["JavaScript"] = js_parser

        except Exception as e:
            raise ASTGenerationError(
                f"Failed to initialize parsers: {str(e)}"
            ) from e

    def detect_language(self, filename: str) -> Optional[str]:
        """Detect language from file extension."""
        extension = Path(filename).suffix.lower()
        for language, extensions in self.SUPPORTED_LANGUAGES.items():
            if extension in extensions:
                return language
        return None

    def _normalize_node(self, node, source_code: bytes) -> Dict[str, Any]:
        """Convert tree-sitter node to normalized schema."""
        try:
            text = source_code[node.start_byte:node.end_byte].decode('utf-8', errors='replace')
        except (UnicodeDecodeError, IndexError):
            text = ""

        return {
            "type": node.type,
            "start": {
                "line": node.start_point[0],
                "column": node.start_point[1],
                "byte": node.start_byte,
            },
            "end": {
                "line": node.end_point[0],
                "column": node.end_point[1],
                "byte": node.end_byte,
            },
            "text": text,
            "children": [self._normalize_node(child, source_code) for child in node.children],
        }

    def generate_ast(self, file_path: str, language: str) -> Dict[str, Any]:
        """
        Generate AST for a code file.
        
        Args:
            file_path: Path to the code file
            language: Programming language (Python, JavaScript, Java)
            
        Returns:
            Dict with AST data and metadata
        """
        if language not in self._parsers:
            raise ASTGenerationError(f"Language '{language}' is not supported")

        try:
            path_obj = Path(file_path)
            if not path_obj.exists():
                raise ASTGenerationError(f"File not found: {file_path}")

            # Read source file
            with open(path_obj, 'rb') as f:
                source_code = f.read()

            line_count = len(source_code.splitlines())

            # Parse the code
            parser = self._parsers[language]
            tree = parser.parse(source_code)

            # Normalize and convert to AST
            ast_json = self._normalize_node(tree.root_node, source_code)

            return {
                "success": True,
                "file": str(path_obj),
                "file_name": path_obj.name,
                "extension": path_obj.suffix,
                "language": language,
                "line_count": line_count,
                "is_supported": True,
                "ast": ast_json,
            }
        except (FileNotFoundError, OSError, ValueError) as e:
            path_obj = Path(file_path)
            return {
                "success": False,
                "file": str(path_obj),
                "file_name": path_obj.name if hasattr(path_obj, "name") else "",
                "extension": path_obj.suffix if hasattr(path_obj, "suffix") else "",
                "language": language,
                "line_count": 0,
                "is_supported": False,
                "error": str(e),
            }

    def generate_ast_for_repository(self, repo_path: str) -> Dict[str, Any]:
        """
        Scan a repository and generate ASTs for all supported code files.
        
        Args:
            repo_path: Path to the repository
            
        Returns:
            Dict with analysis results for all files
        """
        repo_path = Path(repo_path)
        if not repo_path.exists():
            raise ASTGenerationError(f"Repository path not found: {repo_path}")

        results = {
            "repository_path": str(repo_path),
            "files_analyzed": [],
            "languages_detected": {},
            "total_files": 0,
            "supported_files": 0,
        }

        ignore_dirs = {
            ".git", ".github", "node_modules", "build", "dist", ".gradle",
            "__pycache__", ".venv", "venv", ".idea", ".pytest_cache"
        }

        for root, dirs, files in os.walk(repo_path):
            dirs[:] = [d for d in dirs if d not in ignore_dirs]
            for file_name in files:
                results["total_files"] += 1
                language = self.detect_language(file_name)

                if language:
                    results["supported_files"] += 1
                    if language not in results["languages_detected"]:
                        results["languages_detected"][language] = 0
                    results["languages_detected"][language] += 1

                    full_path = os.path.join(root, file_name)
                    ast_result = self.generate_ast(full_path, language)
                    results["files_analyzed"].append(ast_result)

        return results


# Global singleton instance
ast_generator = ASTGenerator()
