"""
Regression Suite: Java Declared-Type Resolution & Shadowing
============================================================
Validates FN-3, W04, and Phase 5.7 hierarchical scoping in JAVA_EQ_001.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent.parent.parent.parent.resolve()))

from app.services.static_analyzer.rules.java_string_equality import JavaStringEquality
from app.services.static_analyzer.tests.harness import (
    RuleTestRunner, module, block, node, leaf, ident, java_binop,
)


def run_tests() -> bool:
    rule = JavaStringEquality()
    r = RuleTestRunner("Regression â€” Java Declared-Type Resolution")

    # --- 1. FIELD STRING DATA SHADOWED BY LOCAL INT DATA (MUST NOT FLAG) ---
    field_data = node("field_declaration", "String data;", 2, children=[
        node("type_identifier", "String", 2),
        node("variable_declarator", "data", 2, children=[ident("data", 2)])
    ])
    local_data = node("local_variable_declaration", "int data = 5;", 4, children=[
        node("integral_type", "int", 4),
        node("variable_declarator", "data = 5", 4, children=[ident("data", 4)])
    ])
    local_other = node("local_variable_declaration", "int other = 6;", 5, children=[
        node("integral_type", "int", 5),
        node("variable_declarator", "other = 6", 5, children=[ident("other", 5)])
    ])
    cmp_local = java_binop(ident("data", 6), "==", ident("other", 6), 6)
    meth_test = node("method_declaration", "void test() {...}", 3, children=[
        node("void_type", "void", 3), ident("test", 3), node("formal_parameters", "()", 3),
        block(local_data, local_other, cmp_local)
    ])
    class_test = node("class_declaration", "class Test {...}", 1, children=[
        leaf("class", "class", 1), ident("Test", 1), block(field_data, meth_test)
    ])
    r.must_not_flag("field String data shadowed by local int data -> must NOT flag", rule, module(class_test), "Test.java")

    # --- 2. FIELD STRING VALUE SHADOWED BY PARAMETER INT VALUE (MUST NOT FLAG) ---
    param_val = node("formal_parameter", "int value", 3, children=[node("integral_type", "int", 3), ident("value", 3)])
    param_oth = node("formal_parameter", "int other", 3, children=[node("integral_type", "int", 3), ident("other", 3)])
    cmp_param = java_binop(ident("value", 4), "==", ident("other", 4), 4)
    meth_val = node("method_declaration", "void test(int value, int other) {...}", 3, children=[
        node("void_type", "void", 3), ident("test", 3),
        node("formal_parameters", "(int value, int other)", 3, children=[param_val, param_oth]),
        block(cmp_param)
    ])
    class_val = node("class_declaration", "class Test {...}", 1, children=[
        leaf("class", "class", 1), ident("Test", 1), block(field_data, meth_val)
    ])
    r.must_not_flag("field String shadowed by parameter int -> must NOT flag", rule, module(class_val), "Test.java")

    # --- 3. PARAMETER STRING VS PARAMETER STRING (MUST FLAG) ---
    param_s1 = node("formal_parameter", "String a", 3, children=[node("type_identifier", "String", 3), ident("a", 3)])
    param_s2 = node("formal_parameter", "String b", 3, children=[node("type_identifier", "String", 3), ident("b", 3)])
    cmp_strings = java_binop(ident("a", 4), "==", ident("b", 4), 4)
    meth_strings = node("method_declaration", "void test(String a, String b) {...}", 3, children=[
        node("void_type", "void", 3), ident("test", 3),
        node("formal_parameters", "(String a, String b)", 3, children=[param_s1, param_s2]),
        block(cmp_strings)
    ])
    r.must_flag("parameter String a == parameter String b -> FLAGGED", rule, module(meth_strings), "Test.java")

    # --- 4. SIBLING METHOD ISOLATION ---
    param_da = node("formal_parameter", "String data", 2, children=[node("type_identifier", "String", 2), ident("data", 2)])
    param_oa = node("formal_parameter", "String other", 2, children=[node("type_identifier", "String", 2), ident("other", 2)])
    meth_a = node("method_declaration", "void a(String data, String other) {...}", 2, children=[
        node("void_type", "void", 2), ident("a", 2),
        node("formal_parameters", "(String data, String other)", 2, children=[param_da, param_oa]),
        block(java_binop(ident("data", 3), "==", ident("other", 3), 3))
    ])
    param_db = node("formal_parameter", "int data", 5, children=[node("integral_type", "int", 5), ident("data", 5)])
    param_ob = node("formal_parameter", "int other", 5, children=[node("integral_type", "int", 5), ident("other", 5)])
    meth_b = node("method_declaration", "void b(int data, int other) {...}", 5, children=[
        node("void_type", "void", 5), ident("b", 5),
        node("formal_parameters", "(int data, int other)", 5, children=[param_db, param_ob]),
        block(java_binop(ident("data", 6), "==", ident("other", 6), 6))
    ])
    sibling_class = node("class_declaration", "class Sibling", 1, children=[block(meth_a, meth_b)])
    issues_sibling = list(rule.analyze(module(sibling_class), "Test.java", []))
    if len(issues_sibling) == 1 and issues_sibling[0].line_number == 4:
        r._passes += 1
        print("  OK   [sibling       ] String in a() flagged, int in sibling b() NOT flagged")
    else:
        r._failures.append(f"  FAIL [sibling       ] sibling isolation failed, got {len(issues_sibling)} issues")

    # --- 5. JAVA.LANG.STRING FULLY QUALIFIED & TYPE BOUNDARIES ---
    decl_fq_str = node("local_variable_declaration", "java.lang.String val;", 2, children=[
        node("scoped_type_identifier", "java.lang.String", 2),
        node("variable_declarator", "val", 2, children=[ident("val", 2)])
    ])
    r.must_flag("java.lang.String val == other -> FLAGGED", rule, module(decl_fq_str, java_binop(ident("val", 4), "==", ident("other", 4), 4)), "Test.java")

    # Object, CharSequence, arrays, generics
    decl_obj = node("local_variable_declaration", "Object o1, o2;", 2, children=[
        node("type_identifier", "Object", 2),
        node("variable_declarator", "o1", 2, children=[ident("o1", 2)]),
        node("variable_declarator", "o2", 2, children=[ident("o2", 2)])
    ])
    r.must_not_flag("Object o1 == o2 -> Object reference identity check -> NOT flagged", rule, module(decl_obj, java_binop(ident("o1", 4), "==", ident("o2", 4), 4)), "Test.java")

    decl_arr = node("local_variable_declaration", "String[] arr1, arr2;", 2, children=[
        node("array_type", "String[]", 2, children=[node("type_identifier", "String", 2), node("dimensions", "[]", 2)]),
        node("variable_declarator", "arr1", 2, children=[ident("arr1", 2)]),
        node("variable_declarator", "arr2", 2, children=[ident("arr2", 2)])
    ])
    r.must_not_flag("String[] arr1 == arr2 -> array reference -> NOT flagged", rule, module(decl_arr, java_binop(ident("arr1", 4), "==", ident("arr2", 4), 4)), "Test.java")

    return r.run()


if __name__ == "__main__":
    ok = run_tests()
    sys.exit(0 if ok else 1)

"""
Regression Suite: Java Declared-Type Resolution & Shadowing
============================================================
Validates hierarchical scoping in JAVA_EQ_001.
"""
