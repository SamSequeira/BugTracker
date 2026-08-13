#!/usr/bin/env python3
"""
Python parser using tree-sitter to generate normalized AST JSON.
"""

import json
from pathlib import Path
from tree_sitter import Language, Parser
import tree_sitter_python as tspython


def normalize_node(node, source_code):
    """Convert tree-sitter node to normalized schema."""
    return {
        "type": node.type,
        "start": {
            "line": node.start_point[0],
            "column": node.start_point[1],
            "byte": node.start_byte
        },
        "end": {
            "line": node.end_point[0],
            "column": node.end_point[1],
            "byte": node.end_byte
        },
        "text": source_code[node.start_byte:node.end_byte].decode('utf8'),
        "children": [normalize_node(child, source_code) for child in node.children]
    }


def parse_python_file(file_path, output_path):
    """Parse Python file and generate AST JSON."""
    # Initialize parser
    PY_LANGUAGE = Language(tspython.language(), "python")
    parser = Parser()
    parser.set_language(PY_LANGUAGE)
    
    # Read source file
    source_path = Path(file_path)
    with open(source_path, 'rb') as f:
        source_code = f.read()
    
    # Parse the code
    tree = parser.parse(source_code)
    
    # Normalize and convert to JSON
    ast_json = normalize_node(tree.root_node, source_code)
    
    # Write output
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(ast_json, f, indent=2, ensure_ascii=False)
    
    print(f"✓ Python AST generated: {output_file}")
    return ast_json


if __name__ == "__main__":
    parse_python_file("samples/sample.py", "output/sample_py_ast.json")
