import asyncio

from app.services.repository_analysis_service import (
    repository_analysis_service
)


async def main():

    # CHANGE THIS TO A REAL CODE REPOSITORY/FOLDER
    repo_path = "."

    print("\n========================================")
    print(" CANDIDATE ISSUE PIPELINE TEST")
    print("========================================")

    try:

        result = await (
            repository_analysis_service
            .analyze_repository(repo_path)
        )

        print("\nRepository:")
        print(result["repository_path"])

        print("\nTotal Candidate Issues:")
        print(result["total_candidate_issues"])

        print("\nCandidate Issues:")

        for issue in result["candidate_issues"]:

            print("\n-----------------------------")

            print("Rule ID     :", issue["rule_id"])
            print("Issue Type  :", issue["issue_type"])
            print("File        :", issue["file_path"])
            print("Line        :", issue["line_number"])
            print("Code        :", issue["code_snippet"])
            print("Description :", issue["message"])
            print("Evidence    :", issue["evidence"])
            print("Severity    :", issue["severity"])

        print("\n========================================")
        print(" PIPELINE TEST COMPLETED")
        print("========================================")

    except Exception as e:

        print("\nPIPELINE ERROR:")
        print(type(e).__name__, ":", e)


if __name__ == "__main__":
    asyncio.run(main())