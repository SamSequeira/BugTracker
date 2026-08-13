#!/usr/bin/env python3
"""
Convenience script to run all parsers and generate AST JSON files.
"""

import sys
from pathlib import Path

# Add scripts directory to path
sys.path.insert(0, str(Path(__file__).parent / "scripts"))

from parse_python import parse_python_file
from parse_javascript import parse_javascript_file
from parse_java import parse_java_file


def main():
    """Run all parsers."""
    print("=" * 60)
    print("Running all parsers...")
    print("=" * 60)
    
    try:
        # Parse Python
        print("\n[1/3] Parsing Python...")
        parse_python_file("samples/sample.py", "output/sample_py_ast.json")
        
        # Parse JavaScript
        print("\n[2/3] Parsing JavaScript...")
        parse_javascript_file("samples/sample.js", "output/sample_js_ast.json")
        
        # Parse Java
        print("\n[3/3] Parsing Java...")
        parse_java_file("samples/sample.java", "output/sample_java_ast.json")
        
        print("\n" + "=" * 60)
        print("✓ All parsers completed successfully!")
        print("=" * 60)
        print("\nGenerated files:")
        print("  - output/sample_py_ast.json")
        print("  - output/sample_js_ast.json")
        print("  - output/sample_java_ast.json")
        
    except Exception as e:
        print(f"\n✗ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
