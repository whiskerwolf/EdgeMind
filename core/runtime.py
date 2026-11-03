import ast
import os
import re
import subprocess
import sys
from difflib import get_close_matches

from core.models import Diagnostic
from core.runner import (
    get_execution_env,
    execute_target_process,
    DEFAULT_TIMEOUT,
    DEFAULT_MAX_OUTPUT_BYTES,
)


def get_source_context(filename, line_number):
    """Read source code and return the relevant line."""
    try:
        with open(filename, "r", encoding="utf-8") as file:
            lines = file.readlines()

        source_line = (
            lines[line_number - 1].strip()
            if 1 <= line_number <= len(lines)
            else ""
        )
        return source_line, lines

    except (OSError, UnicodeError):
        return "", []


def find_similar_name(unknown_name, all_lines):
    """Suggest a likely variable-name correction."""
    try:
        tree = ast.parse("".join(all_lines))
    except (SyntaxError, ValueError):
        return None

    names = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.arg):
            names.add(node.arg)

    # Do not suggest the same name or unrelated identifiers.
    matches = get_close_matches(
        unknown_name,
        names - {unknown_name},
        n=1,
        cutoff=0.75,
    )

    return matches[0] if matches else None


def diagnose_error(error_type, message, source_line, all_lines):
    """Generate a source-aware explanation for a runtime error."""

    why = message
    fix = "Check the code at the reported line."
    concept = "Runtime Error Handling"

    if error_type == "ZeroDivisionError":
        why = "The program attempted to divide by zero."
        fix = (
            "Check the denominator before dividing. "
            "Handle zero when it is a possible input."
        )
        concept = "Division and Error Handling"

    elif error_type == "NameError":
        match = re.search(
            r"name '(.+?)' is not defined",
            message,
        )

        if match:
            name = match.group(1)
            suggestion = find_similar_name(name, all_lines)

            if suggestion:
                why = (
                    f"Python cannot find '{name}'. "
                    f"It may be a misspelling of '{suggestion}'."
                )
                fix = (
                    f"Replace '{name}' with '{suggestion}' if "
                    "that is the intended variable."
                )
            else:
                why = (
                    f"Python cannot find '{name}'. "
                    "It may be misspelled, undefined, or outside "
                    "the current scope."
                )
                fix = (
                    f"Check the spelling and scope of '{name}', "
                    "and define it before use."
                )
        else:
            why = "Python cannot find a name used by the program."
            fix = "Check variable names, definitions, and scope."

        concept = "Variables and Scope"

    elif error_type == "IndexError":
        why = "The index is outside the valid range of the sequence."
        fix = (
            "Check the sequence length and use a valid index. "
            "Remember that Python indexes start at zero."
        )
        concept = "List Indexing"

        try:
            tree = ast.parse(source_line)

            for node in ast.walk(tree):
                if not isinstance(node, ast.Subscript):
                    continue
                if not isinstance(node.value, ast.Name):
                    continue
                if not isinstance(node.slice, ast.Constant):
                    continue

                index = node.slice.value
                if not isinstance(index, int) or isinstance(index, bool):
                    continue

                variable = node.value.id

                for previous_line in reversed(all_lines):
                    try:
                        statements = ast.parse(previous_line).body
                    except SyntaxError:
                        continue

                    for statement in statements:
                        if not isinstance(statement, ast.Assign):
                            continue
                        if not any(
                            isinstance(target, ast.Name)
                            and target.id == variable
                            for target in statement.targets
                        ):
                            continue
                        if not isinstance(statement.value, ast.List):
                            continue

                        length = len(statement.value.elts)

                        if index >= length or index < -length:
                            why = (
                                f"List '{variable}' contains {length} "
                                f"elements, but index {index} is invalid."
                            )
                            fix = (
                                f"Use an index from {-length} to "
                                f"{length - 1}, or check the list length "
                                "before accessing an element."
                            )
                        break
                break

        except (SyntaxError, ValueError):
            pass

    elif error_type == "KeyError":
        match = re.search(
            r"KeyError:\s*(['\"])(.*?)\1",
            message,
        )

        if match:
            key = match.group(2)
            why = (
                f"The dictionary key '{key}' was not found. "
                "The dictionary may not contain that key."
            )
            fix = (
                f"Check whether '{key}' exists before accessing it, "
                "or use dict.get() if a missing key is acceptable."
            )
        else:
            why = "The requested dictionary key was not found."
            fix = "Check the available keys before accessing the dictionary."

        concept = "Dictionary Keys"

    elif error_type == "TypeError":
        why = (
            "The values or objects involved in this operation "
            "may have incompatible types."
        )
        fix = (
            "Inspect the operands and convert values to compatible "
            "types when appropriate."
        )
        concept = "Data Types"

    elif error_type == "AttributeError":
        why = (
            "The object does not provide the attribute or method "
            "used by the program."
        )
        fix = "Check the object's type, attribute name, and available methods."
        concept = "Objects and Methods"

    elif error_type == "ValueError":
        why = (
            "The operation received a value inappropriate for "
            "the requested conversion or operation."
        )
        fix = "Validate the value before using it."
        concept = "Values and Data Types"

    elif error_type == "ModuleNotFoundError":
        match = re.search(r"No module named ['\"](.+?)['\"]", message)
        mod_name = match.group(1) if match else "the requested module"
        why = (
            f"Python could not find the module '{mod_name}'. "
            "It may not be installed or is not available on Python's module search path."
        )
        fix = f"Verify the module name and ensure it is installed in your Python environment."
        concept = "Python Modules"

    elif error_type == "ImportError":
        why = "Python could not import the requested name or module."
        fix = "Check the module installation, import statement, and the name being imported."
        concept = "Python Modules"

    elif error_type == "FileNotFoundError":
        why = "The specified file could not be found at the requested path."
        fix = "Check the path, filename, working directory, and ensure the file exists."
        concept = "File Handling"

    return why, fix, concept


def check_runtime(filename, timeout=DEFAULT_TIMEOUT, max_output_bytes=DEFAULT_MAX_OUTPUT_BYTES):
    """Execute a Python file and diagnose runtime errors with process-tree cleanup and output bounds."""
    try:
        exec_result = execute_target_process(
            filename,
            timeout=timeout,
            max_output_bytes=max_output_bytes,
        )

        if exec_result.timed_out:
            return [
                Diagnostic(
                    type="Timeout Error",
                    severity="error",
                    line=0,
                    message="The program took too long to finish.",
                    why=(
                        "The program may contain an infinite loop "
                        "or a long-running operation."
                    ),
                    fix="Check loops, recursion, and operations that may not terminate.",
                    source="RuntimeDoctor",
                )
            ]

        if exec_result.returncode == 0:
            return []

        error = exec_result.stderr.strip()
        if not error:
            return []

        traceback_lines = re.findall(
            r'File ".*?", line (\d+)',
            error,
        )
        line_number = int(traceback_lines[-1]) if traceback_lines else 0

        error_lines = error.splitlines()
        non_notice_lines = [
            l for l in error_lines
            if not l.startswith("... [EdgeMind:") and not l.startswith("[EdgeMind:") and not l.startswith("... [CodeDoctor:") and not l.startswith("[CodeDoctor:") and l.strip()
        ]
        last_line = non_notice_lines[-1] if non_notice_lines else (error_lines[-1] if error_lines else "")

        if ": " in last_line:
            error_type, message = last_line.split(": ", 1)
        else:
            error_type, message = "Runtime Error", last_line

        abs_filename = os.path.abspath(filename)
        source_line, all_lines = get_source_context(abs_filename, line_number)

        why, fix, concept = diagnose_error(
            error_type,
            message,
            source_line,
            all_lines,
        )

        return [
            Diagnostic(
                type=error_type,
                severity="error",
                line=line_number,
                message=message,
                why=why,
                fix=fix,
                source="RuntimeDoctor",
            )
        ]

    except (OSError, UnicodeError) as error:
        return [
            Diagnostic(
                type="Runtime Error",
                severity="error",
                line=0,
                message=str(error),
                why="EdgeMind could not execute or read the program.",
                fix="Check the file path, encoding, and permissions.",
                source="RuntimeDoctor",
            )
        ]


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m core.runtime <python_file>")
        sys.exit(1)

    results = check_runtime(sys.argv[1])

    if not results:
        print("RuntimeDoctor: No runtime errors found.")

    for result in results:
        print(f"\n[{result.type}]")
        print(f"Line: {result.line}")
        print(f"Message: {result.message}")
        print(f"Why: {result.why}")
        print(f"Fix: {result.fix}")