from app.services.preprocessor import preprocess_code


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