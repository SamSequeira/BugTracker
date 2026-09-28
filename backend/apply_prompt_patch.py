"""
Replaces _build_compact_prompt() in semantic_pipeline.py with the improved
version and makes 'compact' the default prompt mode.

Usage (from the backend folder):
    python apply_prompt_patch.py app\\services\\llm_logic_reviewer\\semantic_pipeline.py

A backup is saved next to the file as semantic_pipeline.py.bak
"""
import shutil
import sys

NEW_FUNCTION = r'''def _build_compact_prompt(
    target: ExtractedFunction,
    context: ContextPackage,
) -> str:
    """
    Short prompt for small local models (SEMANTIC_PROMPT_MODE=compact).

    Design for a 3B model:
    - code first, short instructions, no long essay
    - target lines are numbered so start_line/end_line can be exact
    - the model first writes a short trace ("reasoning") and only then decides
    - a concrete checklist of common bug patterns (generic, not app-specific)
    - explicit "not a bug" rules to reduce false alarms
    - relevant_code must be ONE line copied exactly, so Component 7 can match it
    Output keys are identical to the full prompt, so the parser and
    validate_finding() work unchanged.
    """

    numbered = "\n".join(
        f"{number}: {line}"
        for number, line in enumerate(
            target.source.splitlines(),
            start=target.start_line,
        )
    )

    index = context.text.find(target.source)

    if index >= 0:
        other = context.text[index + len(target.source):].strip()
    else:
        other = context.text

    decorators = (
        "\n".join("@" + d for d in target.decorators)
        if target.decorators
        else "(none)"
    )

    other_block = (
        f"""
CONTEXT FROM THE SAME FILE (read it to understand the target; never report a bug that is only in this context):
{other}
"""
        if other
        else ""
    )

    return f"""You are a careful Python code reviewer. Decide if ONE function contains a real bug.

FILE: {target.file_path}
FUNCTION: {target.qualified_name}  (lines {target.start_line}-{target.end_line})
DECORATORS:
{decorators}

TARGET FUNCTION (each line starts with its line number and a colon; the number is NOT part of the code):
{numbered}
{other_block}
HOW TO REVIEW
1. From the function name and code, say in one sentence what it should do.
2. Trace it with a normal input, then with an empty, zero or missing input.
3. Compare the code against these common bug patterns:
- a sign, operator or comparison that does the opposite of what the function's purpose needs (adds where it should subtract, > instead of <, and instead of or)
- steps in the wrong order (for example limiting, slicing or paginating BEFORE filtering)
- division, len(), [0] or max()/min() on a value that can be 0 or empty, with no guard
- a mutable default argument (=[] or ={{}}) that the function changes or returns
- a shared module-level dict/list/cache that is read or filled here but never cleared or refreshed when the data changes
- a bare "except:" or an except block that hides the error and carries on as if it worked
- the wrong variable used or returned, a missing await, a resource not closed
4. Report a bug ONLY if you can point to one exact line of the TARGET FUNCTION and give a concrete input for which the result is wrong.

NOT A BUG (answer bug_found=false):
- code that already guards the case (an if/else, "or", max(1, x), a try/except that handles the error properly)
- style, naming, missing docs, missing features, missing tests, performance
- anything you cannot see in the code above; never invent fields, functions or behaviour
- normal framework code (dependency injection, generators that yield and then close, routers, app setup)

Reply with ONE JSON object and nothing else (no markdown, no code fences).
Use exactly these keys, in this order:
"reasoning": 2-3 short sentences: what the function should do, what the code does for a normal and for an empty/zero input, and your verdict. Write this first.
"bug_found": true or false
"bug_type": short category, or "" if no bug
"title": short title, or "" if no bug
"description": what is wrong, or "" if no bug
"file": "{target.file_path}"
"start_line": the line number shown before the first buggy line, or 0 if no bug
"end_line": the line number shown before the last buggy line, or 0 if no bug
"evidence": the ONE buggy line copied exactly from the code, without its line number, or "" if no bug
"expected_behavior": what should happen, or "" if no bug
"actual_behavior": what happens instead, or "" if no bug
"confidence": number from 0.0 to 1.0, or 0 if no bug
"relevant_code": the same ONE buggy line copied exactly, without its line number, or "" if no bug
""".strip()


'''

path = sys.argv[1] if len(sys.argv) > 1 else "app/services/llm_logic_reviewer/semantic_pipeline.py"

raw = open(path, "rb").read().decode("utf-8")
crlf = "\r\n" in raw
text = raw.replace("\r\n", "\n")

start_marker = "def _build_compact_prompt("
end_marker = "def build_detection_prompt("

if start_marker not in text or end_marker not in text:
    sys.exit("ERROR: could not find _build_compact_prompt / build_detection_prompt in this file. Nothing changed.")

start = text.index(start_marker)
end = text.index(end_marker)
if end < start:
    sys.exit("ERROR: unexpected function order. Nothing changed.")

shutil.copyfile(path, path + ".bak")

text = text[:start] + NEW_FUNCTION.rstrip("\n") + "\n\n\n" + text[end:]

old_default = 'os.getenv("SEMANTIC_PROMPT_MODE", "full")'
if old_default in text:
    text = text.replace(old_default, 'os.getenv("SEMANTIC_PROMPT_MODE", "compact")')
    print("Default prompt mode changed: full -> compact")
else:
    print("NOTE: default prompt mode line not found; set SEMANTIC_PROMPT_MODE=compact yourself.")

if crlf:
    text = text.replace("\n", "\r\n")

open(path, "wb").write(text.encode("utf-8"))
print("Done. Backup:", path + ".bak")
