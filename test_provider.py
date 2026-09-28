import sys
sys.path.insert(0, "backend")

from app.core.config import settings
from app.services.llm_logic_reviewer.llm_provider import create_llm_provider

print("[Testing OllamaProvider creation...]")
p = create_llm_provider()
print(f"Provider type: {type(p).__name__}")

print("[Testing generation...]")
result = p.generate("What is 2+2?")
response_text = result.get("response", "")
print(f"Response length: {len(response_text)} chars")
if response_text:
    print(f"Sample: {response_text[:150]}")
