from app.services.ast_generator import ast_generator


REPOSITORY_PATH = r"C:\Users\surpr\BugTracker_TestRepo"


print("=" * 50)
print(" AST GENERATION TEST")
print("=" * 50)

result = ast_generator.generate_ast_for_repository(
    REPOSITORY_PATH
)

print("\nRepository:")
print(result["repository_path"])

print("\nTotal files:")
print(result["total_files"])

print("\nSupported files:")
print(result["supported_files"])

print("\nLanguages detected:")
print(result["languages_detected"])

print("\nFiles analyzed:")

for file_result in result["files_analyzed"]:

    print("\n--------------------------------")
    print("File:", file_result["file"])
    print("Language:", file_result["language"])
    print("Success:", file_result["success"])

    if file_result["success"]:
        print("AST generated: YES")
    else:
        print("Error:", file_result.get("error"))

print("\n" + "=" * 50)