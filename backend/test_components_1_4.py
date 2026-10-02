import asyncio
import sys
from pathlib import Path

from app.services.llm_logic_reviewer.reviewer import run_llm_logic_review


REPOSITORY_PATH = r"C:\Users\mayur\OneDrive\Desktop\miniwallet-buggy"
ANALYSIS_RUN_ID = "manual-component-test-001"


async def main():
    print("=" * 70)
    print("BUGTRACKER — COMPONENT 1-4 TEST")
    print("=" * 70)

    print(f"Repository : {REPOSITORY_PATH}")
    print(f"Analysis ID: {ANALYSIS_RUN_ID}")
    print()

    repository = Path(REPOSITORY_PATH)

    if not repository.exists():
        print("ERROR: Repository does not exist.")
        print(repository)
        sys.exit(1)

    if not repository.is_dir():
        print("ERROR: Repository path is not a directory.")
        sys.exit(1)

    print("Starting Component 1-4 pipeline...")
    print()

    result = await run_llm_logic_review(
        analysis_run_id=ANALYSIS_RUN_ID,
        repository_path=REPOSITORY_PATH,
        max_functions=22,
    )

    print()
    print("=" * 70)
    print("COMPONENT 1-4 — COMPLETE")
    print("=" * 70)

    for key, value in result.items():
        print(f"{key}: {value}")

    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())