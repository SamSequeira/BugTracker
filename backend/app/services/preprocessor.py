import io
import tokenize


def preprocess_code(code: str, language: str) -> str:
    """
    Preprocess source code before AST generation.
    """

    language = language.lower()

    if language == "python":
        return preprocess_python(code)

    elif language == "java":
        return preprocess_java(code)

    elif language == "javascript":
        return preprocess_javascript(code)

    else:
        raise ValueError(f"Unsupported language: {language}")


def preprocess_python(code: str) -> str:
    """
    Preprocess Python code by:
    - Removing comments
    - Removing unnecessary trailing whitespace
    - Preserving strings
    - Preserving indentation
    - Preserving line structure for AST analysis
    """

    try:
        tokens = tokenize.generate_tokens(
            io.StringIO(code).readline
        )

        processed_tokens = []

        for token in tokens:

            # Remove comments
            if token.type == tokenize.COMMENT:
                # Replace comment with spaces temporarily
                # so line positions are preserved
                token = tokenize.TokenInfo(
                    token.type,
                    " " * len(token.string),
                    token.start,
                    token.end,
                    token.line
                )

            processed_tokens.append(token)

        processed_code = tokenize.untokenize(processed_tokens)

        # Remove unnecessary trailing spaces from every line
        lines = processed_code.splitlines()

        cleaned_lines = [
            line.rstrip()
            for line in lines
        ]

        return "\n".join(cleaned_lines)

    except tokenize.TokenError:
        # If tokenization fails, return the original code
        return code

def preprocess_java(code: str) -> str:
    """
    Remove Java comments while preserving strings,
    character literals, and code structure.
    """

    result = []
    i = 0
    length = len(code)

    in_string = False
    in_char = False
    in_single_comment = False
    in_multi_comment = False
    escape = False

    while i < length:
        char = code[i]

        # Single-line comment
        if in_single_comment:
            if char == "\n":
                in_single_comment = False
                result.append("\n")
            i += 1
            continue

        # Multi-line comment
        if in_multi_comment:
            if char == "*" and i + 1 < length and code[i + 1] == "/":
                in_multi_comment = False
                i += 2
            else:
                # Preserve newlines so line numbers remain useful
                if char == "\n":
                    result.append("\n")
                i += 1
            continue

        # Inside a string
        if in_string:
            result.append(char)

            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False

            i += 1
            continue

        # Inside a character literal
        if in_char:
            result.append(char)

            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == "'":
                in_char = False

            i += 1
            continue

        # Start of string
        if char == '"':
            in_string = True
            result.append(char)
            i += 1
            continue

        # Start of character literal
        if char == "'":
            in_char = True
            result.append(char)
            i += 1
            continue

        # Start of single-line comment
        if char == "/" and i + 1 < length and code[i + 1] == "/":
            in_single_comment = True
            i += 2
            continue

        # Start of multi-line comment
        if char == "/" and i + 1 < length and code[i + 1] == "*":
            in_multi_comment = True
            i += 2
            continue

        result.append(char)
        i += 1

    return "".join(result)

def preprocess_javascript(code: str) -> str:
    """Preprocess JavaScript source code.

    Removes:
    - Single-line comments (//)
    - Multi-line comments (/* ... */)
    - Excessive blank lines
    - Trailing whitespace

    Preserves:
    - Strings
    - Template literals
    - URLs inside strings
    - Code indentation
    """

    result = []
    i = 0
    n = len(code)

    # Track whether we are inside a string/template literal
    in_string = False
    string_char = None

    while i < n:
        char = code[i]

        # --------------------------------------------------
        # Inside a string or template literal
        # --------------------------------------------------
        if in_string:
            result.append(char)

            # Handle escaped characters
            if char == "\\" and i + 1 < n:
                i += 1
                result.append(code[i])

            # End of string/template
            elif char == string_char:
                in_string = False
                string_char = None

            i += 1
            continue

        # --------------------------------------------------
        # Start of string / template literal
        # --------------------------------------------------
        if char in ('"', "'", "`"):
            in_string = True
            string_char = char
            result.append(char)
            i += 1
            continue

        # --------------------------------------------------
        # Single-line comment //
        # --------------------------------------------------
        if char == "/" and i + 1 < n and code[i + 1] == "/":
            i += 2

            # Skip until end of line
            while i < n and code[i] != "\n":
                i += 1

            # Preserve newline
            if i < n:
                result.append("\n")
                i += 1

            continue

        # --------------------------------------------------
        # Multi-line comment /* ... */
        # --------------------------------------------------
        if char == "/" and i + 1 < n and code[i + 1] == "*":
            i += 2

            # Preserve newlines inside comment so that
            # source line numbers are not completely changed
            while i < n:
                if code[i] == "*" and i + 1 < n and code[i + 1] == "/":
                    i += 2
                    break

                if code[i] == "\n":
                    result.append("\n")

                i += 1

            continue

        # Normal character
        result.append(char)
        i += 1

    # ------------------------------------------------------
    # Clean trailing whitespace and excessive blank lines
    # ------------------------------------------------------

    processed_code = "".join(result)

    lines = processed_code.splitlines()

    cleaned_lines = []
    previous_blank = False

    for line in lines:
        line = line.rstrip()

        if line.strip() == "":
            if previous_blank:
                continue

            previous_blank = True
            cleaned_lines.append("")
        else:
            previous_blank = False
            cleaned_lines.append(line)

    return "\n".join(cleaned_lines).strip()