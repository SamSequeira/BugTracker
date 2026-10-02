import sys, os, asyncio, uuid
from pathlib import Path
sys.path.insert(0, ".")

for line in Path(".env").read_text().splitlines():
    if "=" in line and not line.startswith("#"):
        key, val = line.split("=", 1)
        os.environ[key.strip()] = val.strip()

print("=" * 100)
print("COMPLETE END-TO-END SEMANTIC PIPELINE TEST")
print("=" * 100)
print()

test_repo = Path("test_e2e_repo")
files = list(test_repo.rglob("*.py"))
print(f"Test repository: {test_repo.absolute()}")
print(f"Python files: {len(files)}")
for f in files:
    print(f"  - {f.relative_to(test_repo)}")
print()

print("Testing Ollama provider...")
from app.services.llm_logic_reviewer.llm_provider import create_llm_provider
provider = create_llm_provider()
print(f"Provider: {type(provider).__name__}")

test_prompt = "Analyze: def divide(a,b): return a/b. Return JSON."
result = provider.generate(test_prompt)
if result.get("response"):
    print(f"Ollama working: {len(result['response'])} chars")
elif result.get("error"):
    print(f"Ollama error: {result['error']}")
print()

print("Running semantic pipeline...")
async def test():
    from app.services.llm_logic_reviewer.reviewer import run_llm_logic_review
    run_id = str(uuid.uuid4())
    metrics = await run_llm_logic_review(run_id, str(test_repo.absolute()))
    return metrics

metrics = asyncio.run(test())
print()
print("RESULTS:")
for key, val in metrics.items():
    print(f"  {key}: {val}")
print()
print("TEST COMPLETE")