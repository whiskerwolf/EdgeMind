import re


ERRORS = {
    "IndexError": {
        "message": "An index is outside the valid range.",
        "why": (
            "The program tried to access a sequence position "
            "that does not exist."
        ),
        "fix": (
            "Check the sequence length and verify the index. "
            "Remember that Python indexing starts at 0."
        ),
        "concept": "List Indexing",
    },

    "ZeroDivisionError": {
        "message": "A number was divided by zero.",
        "why": "The denominator evaluated to zero.",
        "fix": (
            "Check the denominator before division and handle "
            "zero according to your program's requirements."
        ),
        "concept": "Division and Error Handling",
    },

    "NameError": {
        "message": "A name could not be found.",
        "why": (
            "Python encountered a variable or name that was not "
            "defined in the current scope."
        ),
        "fix": (
            "Check the spelling, scope, and definition of the "
            "variable or function."
        ),
        "concept": "Variables and Scope",
    },

    "TypeError": {
        "message": "An operation received an incompatible type.",
        "why": (
            "The operation or function does not support the "
            "provided value types."
        ),
        "fix": (
            "Check the types of the values involved and convert "
            "them when appropriate."
        ),
        "concept": "Data Types",
    },

    "ValueError": {
        "message": "A value is unsuitable for the operation.",
        "why": (
            "The value has an acceptable type, but its content "
            "or format is not valid for the operation."
        ),
        "fix": (
            "Validate the input and check the format or range "
            "expected by the operation."
        ),
        "concept": "Input Validation",
    },

    "KeyError": {
        "message": "A dictionary key could not be found.",
        "why": (
            "The requested key is not present in the dictionary."
        ),
        "fix": (
            "Verify the key or use dict.get() when a missing "
            "key should have a default value."
        ),
        "concept": "Dictionary Keys",
    },

    "AttributeError": {
        "message": "An object does not provide the requested attribute.",
        "why": (
            "The attribute or method is unavailable on the object "
            "at the time it was accessed."
        ),
        "fix": (
            "Check the object's type, the attribute name, and "
            "whether the object has the expected value."
        ),
        "concept": "Objects and Methods",
    },

    "FileNotFoundError": {
        "message": "A requested file could not be found.",
        "why": (
            "The specified path does not identify an accessible file."
        ),
        "fix": (
            "Check the path, filename, working directory, "
            "and file existence."
        ),
        "concept": "File Handling",
    },

    "ImportError": {
        "message": "A requested import could not be completed.",
        "why": (
            "Python could not import the requested name or module."
        ),
        "fix": (
            "Check the module installation, import statement, "
            "and the name being imported."
        ),
        "concept": "Python Modules",
    },

    "ModuleNotFoundError": {
        "message": "Python could not find the requested module.",
        "why": (
            "The module may not be installed or may not be "
            "available on Python's module search path."
        ),
        "fix": (
            "Verify the module name and install the required "
            "package in the correct environment if necessary."
        ),
        "concept": "Python Modules",
    },

    "AssertionError": {
        "message": "An assertion condition evaluated to false.",
        "why": (
            "A condition that the program expected to be true "
            "was not satisfied."
        ),
        "fix": (
            "Check the asserted condition and determine why "
            "the actual value differs from the expected value."
        ),
        "concept": "Assertions and Testing",
    },

    "RecursionError": {
        "message": "The maximum recursion depth was exceeded.",
        "why": (
            "Recursive calls continued too deeply, often because "
            "a base case is missing or unreachable."
        ),
        "fix": (
            "Check the base case and ensure each recursive call "
            "moves toward it."
        ),
        "concept": "Recursion",
    },

    "IndentationError": {
        "message": "Python found an indentation problem.",
        "why": (
            "The indentation does not match the structure "
            "expected by Python."
        ),
        "fix": (
            "Check the indentation of the reported line and "
            "its surrounding code. Use consistent indentation."
        ),
        "concept": "Python Indentation",
    },

    "SyntaxError": {
        "message": "Python could not parse the code.",
        "why": (
            "The source code contains a syntax problem, such as "
            "an invalid expression or a missing delimiter."
        ),
        "fix": (
            "Inspect the reported line and nearby lines for "
            "missing brackets, colons, quotes, or invalid syntax."
        ),
        "concept": "Python Syntax",
    },

    "TimeoutError": {
        "message": "An operation exceeded its time limit.",
        "why": (
            "An operation did not complete within the permitted "
            "time, although the precise cause depends on context."
        ),
        "fix": (
            "Inspect the operation, input size, timeout setting, "
            "and whether the operation is blocked or unusually slow."
        ),
        "concept": "Execution and Timeouts",
    },
}


def diagnose(error):
    error_text = str(error).strip()

    if not error_text:
        return {
            "type": "UnknownError",
            "message": "No error details were provided.",
            "why": "EdgeMind received an empty error description.",
            "fix": "Provide an exception name or error message.",
            "concept": "Error Diagnosis",
        }

    # Inspect the final line of the traceback.
    last_line = error_text.splitlines()[-1].strip()

    match = re.match(
        r"^([A-Za-z_][A-Za-z0-9_]*)(?::\s*(.*))?$",
        last_line,
    )

    if match:
        error_type = match.group(1)
        original_message = (match.group(2) or "").strip()
    else:
        error_type = None
        original_message = last_line

    # Preserve the existing handling of unknown exceptions.
    if error_type not in ERRORS:
        return {
            "type": "Runtime Error",
            "message": "An error occurred during execution.",
            "why": error_text,
            "fix": (
                "Inspect the complete traceback and the code "
                "around the reported location."
            ),
            "concept": "Runtime Errors",
        }

    diagnosis = ERRORS[error_type]

    message = diagnosis["message"]
    why = diagnosis["why"]
    fix = diagnosis["fix"]
    concept = diagnosis["concept"]

    # Preserve the actual missing dictionary key.
    if error_type == "KeyError":
        key_match = re.search(
            r"""KeyError:\s*(['"])(.*?)\1\s*$""",
            error_text,
        )

        if key_match:
            key = key_match.group(2)
            message = f"The key '{key}' does not exist."
            why = (
                f"The dictionary lookup failed because the "
                f"requested key '{key}' was not found."
            )
            fix = (
                f"Check whether '{key}' exists before accessing it, "
                "or use dict.get() if a missing key is acceptable."
            )

        elif original_message:
            message = original_message

    # Preserve useful details for other errors when available.
    elif original_message:
        if error_type == "NameError":
            name_match = re.search(
                r"name ['\"](.+?)['\"] is not defined",
                original_message,
            )

            if name_match:
                name = name_match.group(1)
                message = f"Name '{name}' is not defined."
                why = (
                    f"Python cannot find '{name}' in the current "
                    "scope. It may be misspelled or undefined."
                )
                fix = (
                    f"Check the spelling of '{name}' and define "
                    "it before use."
                )
        else:
            message = original_message

    return {
        "type": error_type,
        "message": message,
        "why": why,
        "fix": fix,
        "concept": concept,
    }