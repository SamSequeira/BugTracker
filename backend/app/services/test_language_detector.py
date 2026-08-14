from app.services.language_detector import detect_language

print(detect_language("test.py"))
print(detect_language("Main.java"))
print(detect_language("app.js"))
print(detect_language("README.md"))
print(detect_language("image.png"))