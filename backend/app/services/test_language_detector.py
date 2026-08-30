from app.services.language_detector import detect_language


print("========== LANGUAGE DETECTION TEST ==========")

test_files = [
    "test_python.py",
    "test_javascript.js",
    "TestJava.java",
    "notes.txt"
]

for filename in test_files:
    result = detect_language(filename)

    print(f"{filename:25} -> {result}")

print("=============================================")