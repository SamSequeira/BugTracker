from app.services.preprocessor import preprocess_code, preprocess_javascript


python_code = '''
# Normal comment

x = 10  # Inline comment

text = "# This is inside a string"

url = "https://example.com"

def hello():
    # Comment inside function
    print("Hello")
'''


processed_code = preprocess_code(python_code, "Python")


print("========== ORIGINAL CODE ==========")
print(python_code)

print("========== PROCESSED CODE ==========")
print(processed_code)

import ast

try:
    ast.parse(processed_code)
    print("========== AST TEST ==========")
    print("Valid Python syntax: YES")
except SyntaxError as e:
    print("Valid Python syntax: NO")
    print(e)
javascript_code = """
// Normal comment

function hello() {

    // Comment inside function
    console.log("Hello");

}

/* Multi-line
   comment
   here */

const text = "// This is NOT a comment";

const url = "https://example.com";

const template = `Hello // this is not a comment`;

let x = 10;      // Inline comment

let y = 20;

console.log(x + y);
"""

processed = preprocess_javascript(javascript_code)

print("========== JAVASCRIPT ORIGINAL ==========")
print(javascript_code)

print("========== JAVASCRIPT PROCESSED ==========")
print(processed)