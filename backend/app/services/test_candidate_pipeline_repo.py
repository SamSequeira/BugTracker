from app.services.ast_generator import ast_generator
from app.services.candidate_issue_service import candidate_issue_service


REPOSITORY_PATH = r"C:\Users\surpr\BugTracker_TestRepo"


print("=" * 60)
print(" COMPLETE CANDIDATE ISSUE PIPELINE TEST")
print("=" * 60)


# --------------------------------------------------
# STEP 1: AST GENERATION
# --------------------------------------------------

print("\n[1] Generating AST...")

ast_result = ast_generator.generate_ast_for_repository(
    REPOSITORY_PATH
)

print("AST generation completed.")

print("Total files:",
      ast_result["total_files"])

print("Supported files:",
      ast_result["supported_files"])

print("Languages:",
      ast_result["languages_detected"])


# --------------------------------------------------
# STEP 2: CANDIDATE ISSUE GENERATION
# --------------------------------------------------

print("\n[2] Generating Candidate Issues...")

result = candidate_issue_service.generate_from_repository(
    ast_result
)


# --------------------------------------------------
# STEP 3: DISPLAY RESULTS
# --------------------------------------------------

print("\n[3] RESULTS")

print("Total Candidate Issues:",
      len(result))


for index, issue in enumerate(result, start=1):

    print("\n----------------------------------------")
    print(f"Candidate Issue #{index}")

    if hasattr(issue, "model_dump"):
        data = issue.model_dump()

    elif hasattr(issue, "dict"):
        data = issue.dict()

    elif hasattr(issue, "to_dict"):
        data = issue.to_dict()

    else:
        data = issue

    print(data)


print("\n" + "=" * 60)
print(" PIPELINE TEST COMPLETED")
print("=" * 60)