#!/usr/bin/env python3
"""
Comprehensive test suite for AST parsers.
Validates parser functionality, AST structure, and bug pattern detection.
"""

import json
import sys
from pathlib import Path
from typing import Dict, Any, List


class ASTTester:
    """Test AST generation and bug detection across all languages."""
    
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.errors = []
    
    def test_ast_files_exist(self):
        """Test 1: Verify all AST files were generated."""
        print("\n" + "="*70)
        print("TEST 1: AST File Generation")
        print("="*70)
        
        files = [
            "output/sample_py_ast.json",
            "output/sample_js_ast.json",
            "output/sample_java_ast.json"
        ]
        
        for file in files:
            if Path(file).exists():
                print(f"✓ {file} exists")
                self.passed += 1
            else:
                print(f"✗ {file} NOT FOUND")
                self.failed += 1
                self.errors.append(f"Missing file: {file}")
    
    def test_ast_structure(self):
        """Test 2: Validate AST structure and schema."""
        print("\n" + "="*70)
        print("TEST 2: AST Structure Validation")
        print("="*70)
        
        tests = [
            ("output/sample_py_ast.json", "python", "module", 6, "function_definition"),
            ("output/sample_js_ast.json", "javascript", "program", 6, "function_declaration"),
            ("output/sample_java_ast.json", "java", "program", 6, "method_declaration")
        ]
        
        for file, lang, expected_root, min_functions, func_type in tests:
            try:
                with open(file, 'r', encoding='utf-8') as f:
                    ast = json.load(f)
                
                # Check root type
                if ast['type'] == expected_root:
                    print(f"✓ {lang}: Root type is '{expected_root}'")
                    self.passed += 1
                else:
                    print(f"✗ {lang}: Expected root '{expected_root}', got '{ast['type']}'")
                    self.failed += 1
                    self.errors.append(f"{lang}: Invalid root type")
                
                # Check required fields
                required_fields = ['type', 'start', 'end', 'text', 'children']
                if all(field in ast for field in required_fields):
                    print(f"✓ {lang}: All required fields present")
                    self.passed += 1
                else:
                    missing = [f for f in required_fields if f not in ast]
                    print(f"✗ {lang}: Missing fields: {missing}")
                    self.failed += 1
                    self.errors.append(f"{lang}: Missing schema fields")
                
                # Check function count
                functions = self._find_nodes_by_type(ast, func_type)
                if len(functions) >= min_functions:
                    print(f"✓ {lang}: Found {len(functions)} functions/methods")
                    self.passed += 1
                else:
                    print(f"✗ {lang}: Expected at least {min_functions}, found {len(functions)}")
                    self.failed += 1
                    self.errors.append(f"{lang}: Insufficient functions parsed")
                    
            except Exception as e:
                print(f"✗ {lang}: Error loading AST - {e}")
                self.failed += 1
                self.errors.append(f"{lang}: {str(e)}")
    
    def test_bug_detection(self):
        """Test 3: Verify bug patterns are detectable."""
        print("\n" + "="*70)
        print("TEST 3: Bug Pattern Detection")
        print("="*70)
        
        tests = [
            ("output/sample_py_ast.json", "python", [
                ("Division by zero", "binary_operator", "/"),
                ("SQL injection", "string", "SELECT"),
            ]),
            ("output/sample_js_ast.json", "javascript", [
                ("Division by zero", "binary_expression", "/"),
                ("SQL injection", "template_string", "SELECT"),
            ]),
            ("output/sample_java_ast.json", "java", [
                ("Division by zero", "binary_expression", "/"),
                ("SQL injection", "string_literal", "SELECT"),
            ])
        ]
        
        for file, lang, patterns in tests:
            try:
                with open(file, 'r', encoding='utf-8') as f:
                    ast = json.load(f)
                
                for pattern_name, node_type, search_text in patterns:
                    nodes = self._find_nodes_by_type(ast, node_type)
                    found = any(search_text in node.get('text', '') for node in nodes)
                    
                    if found:
                        print(f"✓ {lang}: {pattern_name} pattern detectable")
                        self.passed += 1
                    else:
                        print(f"✗ {lang}: {pattern_name} pattern NOT found")
                        self.failed += 1
                        self.errors.append(f"{lang}: Missing {pattern_name} pattern")
                        
            except Exception as e:
                print(f"✗ {lang}: Error during bug detection - {e}")
                self.failed += 1
                self.errors.append(f"{lang}: {str(e)}")
    
    def test_position_tracking(self):
        """Test 4: Verify accurate position tracking."""
        print("\n" + "="*70)
        print("TEST 4: Position Tracking")
        print("="*70)
        
        files = [
            ("output/sample_py_ast.json", "python"),
            ("output/sample_js_ast.json", "javascript"),
            ("output/sample_java_ast.json", "java")
        ]
        
        for file, lang in files:
            try:
                with open(file, 'r', encoding='utf-8') as f:
                    ast = json.load(f)
                
                # Check position fields exist
                has_start = 'line' in ast['start'] and 'column' in ast['start'] and 'byte' in ast['start']
                has_end = 'line' in ast['end'] and 'column' in ast['end'] and 'byte' in ast['end']
                
                if has_start and has_end:
                    print(f"✓ {lang}: Position tracking (line/column/byte) present")
                    self.passed += 1
                else:
                    print(f"✗ {lang}: Position tracking incomplete")
                    self.failed += 1
                    self.errors.append(f"{lang}: Incomplete position data")
                
                # Verify positions are valid
                if ast['start']['line'] >= 0 and ast['end']['line'] > ast['start']['line']:
                    print(f"✓ {lang}: Position values are valid")
                    self.passed += 1
                else:
                    print(f"✗ {lang}: Invalid position values")
                    self.failed += 1
                    self.errors.append(f"{lang}: Invalid position values")
                    
            except Exception as e:
                print(f"✗ {lang}: Error checking positions - {e}")
                self.failed += 1
                self.errors.append(f"{lang}: {str(e)}")
    
    def _find_nodes_by_type(self, node: Dict[str, Any], node_type: str) -> List[Dict[str, Any]]:
        """Recursively find all nodes of a specific type."""
        matches = []
        if node.get('type') == node_type:
            matches.append(node)
        for child in node.get('children', []):
            matches.extend(self._find_nodes_by_type(child, node_type))
        return matches
    
    def print_summary(self):
        """Print test results summary."""
        print("\n" + "="*70)
        print("TEST SUMMARY")
        print("="*70)
        print(f"\nPassed: {self.passed}")
        print(f"Failed: {self.failed}")
        print(f"Total:  {self.passed + self.failed}")
        
        if self.failed > 0:
            print("\n❌ TESTS FAILED")
            print("\nErrors:")
            for error in self.errors:
                print(f"  - {error}")
            return False
        else:
            print("\n✅ ALL TESTS PASSED")
            print("\nAST parsers are working correctly:")
            print("  ✓ All AST files generated")
            print("  ✓ Schema structure validated")
            print("  ✓ Bug patterns detectable")
            print("  ✓ Position tracking accurate")
            return True


def main():
    """Run all AST parser tests."""
    print("="*70)
    print("AST PARSER TEST SUITE")
    print("="*70)
    print("\nValidating AST generation, structure, and bug detection")
    
    # Check if output directory exists
    if not Path("output").exists():
        print("\n❌ Error: output/ directory not found.")
        print("Run: python run_all_parsers.py")
        return False
    
    # Run all tests
    tester = ASTTester()
    tester.test_ast_files_exist()
    tester.test_ast_structure()
    tester.test_bug_detection()
    tester.test_position_tracking()
    
    # Print summary
    return tester.print_summary()


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
