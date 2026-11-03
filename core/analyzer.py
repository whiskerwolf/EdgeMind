import sys

from core.static_check import static_checks
from core.runtime import check_runtime
from core.logic import check_logic
from core.quality import check_quality
from core.complexity import check_complexity
from core.smells import check_smells


ERROR_TYPES = {
    "SyntaxError",
    "IndentationError",
    "NameError",
    "IndexError",
    "ZeroDivisionError",
    "TypeError",
    "KeyError",
    "AttributeError",
    "Timeout Error",
    "LogicError",
    "FileError",
    "FileNotFoundError",
    "Runtime Error",
    "RuntimeError",
    "EdgeMindError",
    "CodeDoctorError",
    "ValueError",
    "ImportError",
    "ModuleNotFoundError",
    "AssertionError",
    "RecursionError",
    "TimeoutError",
}

WARNING_TYPES = {
    "UnusedImport",
    "UnusedVariable",
    "UnreachableCode",
    "LongFunction",
    "TooManyParameters",
    "DeepNesting",
    "MediumComplexity",
    "HighComplexity",
    "MagicNumber",
    "ExcessivePrint",
    "LongCondition",
    "EmptyFunction",
    "DuplicateCode",
    "NestedLoops",
}


def is_error(result):
    """Determine whether a diagnostic finding is an error rather than a warning."""
    if isinstance(result, dict):
        concept = result.get("concept")
        issue_type = result.get("type")
    else:
        concept = getattr(result, "concept", getattr(result, "source", None))
        issue_type = getattr(result, "type", None)

    return (
        concept == "Runtime Error Handling"
        or issue_type in ERROR_TYPES
    )


class AnalysisResultList(list):
    """List subclass that retains analysis execution metadata (e.g., static_only)."""
    def __init__(self, iterable=None, static_only=False):
        super().__init__(iterable or [])
        self.static_only = static_only


def deduplicate_results(results, static_only=False):
    """Remove exact duplicate findings without hiding distinct issues."""
    unique_results = []
    seen = set()

    for result in results:
        key = (
            result.get("type"),
            result.get("line", 0),
            result.get("message", ""),
        )

        if key not in seen:
            seen.add(key)
            unique_results.append(result)

    is_static = static_only or getattr(results, "static_only", False)
    return AnalysisResultList(unique_results, static_only=is_static)


def analyze_file(filename, static_only=False):
    try:
        with open(filename, "r", encoding="utf-8") as file:
            code = file.read()

        try:
            compile(code, filename, "exec")
        except SyntaxError as error:
            return AnalysisResultList([{
                "type": "SyntaxError",
                "line": error.lineno or 0,
                "message": error.msg,
                "why": "Python could not understand the code structure.",
                "fix": "Check the reported line for syntax mistakes.",
                "concept": "Python Syntax",
            }], static_only=static_only)

        results = AnalysisResultList([], static_only=static_only)

        # Static analysis
        results.extend(static_checks(code))

        # Logic analysis
        for item in check_logic(code):
            if isinstance(item, dict):
                results.append(item)
            else:
                results.append({
                    "type": getattr(item, "type", "LogicError"),
                    "line": getattr(item, "line", 0),
                    "message": getattr(item, "message", ""),
                    "why": getattr(item, "why", ""),
                    "fix": getattr(item, "fix", ""),
                    "concept": "Logic",
                })

        # Code quality
        results.extend(check_quality(code))

        # Complexity analysis
        results.extend(check_complexity(code))

        # Code smell detection
        results.extend(check_smells(code))

        # Runtime analysis (skipped if static_only is True)
        if not static_only:
            runtime_results = check_runtime(filename)

            for result in runtime_results:
                runtime_finding = {
                    "type": result.type,
                    "line": result.line,
                    "message": result.message,
                    "why": result.why,
                    "fix": result.fix,
                    "concept": "Runtime Error Handling",
                }

                # Avoid adding a generic runtime error if a more
                # specific diagnosis already exists for the same line.
                existing_diagnosis = any(
                    issue.get("type") == runtime_finding["type"]
                    and issue.get("line") == runtime_finding["line"]
                    and issue.get("concept") != "Runtime Error Handling"
                    for issue in results
                )

                if not existing_diagnosis:
                    results.append(runtime_finding)

        # Remove exact duplicate findings only.
        return deduplicate_results(results, static_only=static_only)

    except FileNotFoundError:
        return AnalysisResultList([{
            "type": "FileError",
            "line": 0,
            "message": f"File not found: {filename}",
            "why": "EdgeMind could not find the requested file.",
            "fix": "Check the file path.",
            "concept": "File Handling",
        }], static_only=static_only)

    except (OSError, UnicodeError) as error:
        return AnalysisResultList([{
            "type": "FileError",
            "line": 0,
            "message": str(error),
            "why": "EdgeMind could not read the requested file.",
            "fix": "Check the file path, permissions, and encoding.",
            "concept": "File Handling",
        }], static_only=static_only)

    except Exception as error:
        return AnalysisResultList([{
            "type": "EdgeMindError",
            "line": 0,
            "message": str(error),
            "why": "EdgeMind encountered an unexpected problem.",
            "fix": "Check the project files and analysis components.",
            "concept": "Error Handling",
        }], static_only=static_only)


def print_report(filename, results=None, ai_reasoning=None, static_only=False):
    is_static = static_only or getattr(results, "static_only", False)
    if results is None:
        results = analyze_file(filename, static_only=is_static)
        is_static = is_static or getattr(results, "static_only", False)

    errors = [
        result for result in results
        if is_error(result)
    ]

    warnings = [
        result for result in results
        if result.get("type") in WARNING_TYPES
    ]

    other_issues = [
        result for result in results
        if not is_error(result) and result not in warnings
    ]

    total_errors = len(errors)
    total_warnings = len(warnings) + len(other_issues)

    score = 100 - (total_errors * 20) - (total_warnings * 5)
    score = max(0, min(100, score))

    if total_errors:
        status = "FAIL"
    elif total_warnings:
        status = "PASS WITH WARNINGS"
    else:
        status = "PASS"

    print("\n" + "=" * 55)
    print("                 EDGEMIND REPORT")
    print("=" * 55)

    print(f"File: {filename}")
    print(f"Overall Result: {status}")
    print(f"Score: {score}/100")
    print(f"Errors: {total_errors}")
    print(f"Warnings: {total_warnings}")

    print("\n" + "-" * 55)
    print("ANALYSIS SUMMARY")
    print("-" * 55)

    syntax_errors = [
        result for result in results
        if result.get("type") in {"SyntaxError", "IndentationError"}
    ]

    runtime_errors = [
        result for result in results
        if is_error(result)
        and result.get("type") not in {"SyntaxError", "IndentationError"}
    ]

    print("SYNTAX:", "FAIL" if syntax_errors else "PASS")
    if is_static:
        print("RUNTIME: SKIPPED")
    else:
        print("RUNTIME:", "FAIL" if runtime_errors else "PASS")

    print(
        "LOGIC:",
        "WARNING" if any(
            result.get("type") in {"LogicError", "Possible Logic Error"}
            for result in results
        ) else "PASS"
    )

    print(
        "QUALITY:",
        "WARNING" if any(
            result.get("type") in WARNING_TYPES
            for result in results
        ) else "PASS"
    )

    print(
        "COMPLEXITY:",
        "WARNING" if any(
            result.get("type") in {
                "MediumComplexity",
                "HighComplexity",
            }
            for result in results
        ) else "PASS"
    )

    if not results:
        print("\nNo issues detected. Your code looks good!")

    for result in results:
        issue_type = result.get("type", "Unknown")
        line = result.get("line", 0)
        message = result.get("message", "No description available.")
        why = result.get("why", "No explanation available.")
        fix = result.get("fix", "Review the code.")
        concept = result.get("concept", "General")

        category = (
            "ERROR" if is_error(result) else "WARNING"
        )

        print("\n" + "-" * 55)
        print(f"[{category}] {issue_type}")
        print(f"Line: {line}")
        print(f"Problem: {message}")
        print(f"Why: {why}")
        print(f"Fix: {fix}")
        print(f"Concept: {concept}")

        if line > 0:
            try:
                with open(filename, "r", encoding="utf-8") as file:
                    lines = file.readlines()

                if line <= len(lines):
                    print(f"Code: {lines[line - 1].rstrip()}")
            except (OSError, UnicodeError):
                pass

    if ai_reasoning:
        print("\n" + "-" * 55)
        print("AI REASONING")
        print("-" * 55)
        ai_status = ai_reasoning.get("status", "unknown")
        ai_provider = ai_reasoning.get("provider", "unknown")
        ai_summary = ai_reasoning.get("summary", "")
        ai_error = ai_reasoning.get("error")

        print(f"Status: {ai_status.upper()}")
        print(f"Provider: {ai_provider}")
        if ai_summary:
            print(f"Summary: {ai_summary}")
        if ai_error:
            print(f"Error: {ai_error}")

        ai_insights = ai_reasoning.get("insights", [])
        for insight in ai_insights:
            finding_type = insight.get("finding_type", "Finding")
            line = insight.get("line", 0)
            explanation = insight.get("explanation", "")
            fix = insight.get("suggested_fix", "")
            confidence = insight.get("confidence", "medium")

            print("\n" + "~" * 40)
            print(f"[AI INSIGHT] {finding_type} (Line {line}) [Confidence: {confidence}]")
            if explanation:
                print(f"Reasoning: {explanation}")
            if fix:
                print(f"Suggestion: {fix}")

    print("\n" + "=" * 55)


def generate_json_report(filename, results=None, indent=2, ai_reasoning=None, static_only=False):
    """Convenience wrapper to generate JSON report string."""
    from core.json_reporter import generate_json_report as _gen
    return _gen(filename, results=results, indent=indent, ai_reasoning=ai_reasoning, static_only=static_only)


def run_ai_reasoning(
    filename,
    findings,
    user_consent=False,
    adapter=None,
    code=None,
):
    """
    Run AI reasoning safely.
    Requires user_consent before source code is accessed or transmitted.
    """
    if code is None:
        try:
            with open(filename, "r", encoding="utf-8") as f:
                code = f.read()
        except (OSError, UnicodeError):
            code = ""

    if adapter is None:
        if not user_consent:
            sys.stderr.write(
                "EdgeMind: AI reasoning enabled without --share-source. Source code will not be transmitted.\n"
            )
            from adapters.null_adapter import NullAdapter
            adapter = NullAdapter(reason="Source-sharing consent not granted. Use --share-source to permit sending code.")
        else:
            from adapters.http_adapter import HttpAdapter
            http_adapter = HttpAdapter()
            if http_adapter.is_available():
                adapter = http_adapter
            else:
                sys.stderr.write(
                    "EdgeMind: AI reasoning enabled (--ai), but no API key found in EDGEMIND_AI_KEY, CODEDOCTOR_AI_KEY or GEMINI_API_KEY environment variables.\n"
                )
                from adapters.null_adapter import NullAdapter
                adapter = NullAdapter(reason="No API key found in EDGEMIND_AI_KEY, CODEDOCTOR_AI_KEY or GEMINI_API_KEY environment variables.")

    from core.ai_engine import AIEngine
    engine = AIEngine(adapter=adapter)
    response = engine.analyze(
        file_path=filename,
        code=code,
        findings=findings,
        user_consent=user_consent,
    )
    return response.to_dict()


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]

    # Help requested
    if "-h" in argv or "--help" in argv:
        print("Usage: python -m core.analyzer <python_file> [OPTIONS]")
        print("\nOptions:")
        print("  --json          Output structured report in JSON format")
        print("  --ai            Enable AI reasoning engine")
        print("  --share-source  Authorize sending bounded source code to external AI provider")
        print("  --static-only   Analyze code statically without executing runtime checks")
        print("  -h, --help      Show this help message and exit")
        sys.exit(0)

    if not argv:
        print("Usage: python -m core.analyzer <python_file> [--json] [--ai] [--share-source] [--static-only]")
        sys.exit(1)

    json_mode = "--json" in argv
    ai_mode = "--ai" in argv
    share_source = "--share-source" in argv
    static_only = "--static-only" in argv

    flag_set = {"--json", "--ai", "--share-source", "--static-only"}
    files = [arg for arg in argv if arg not in flag_set and not arg.startswith("-")]

    if not files:
        print("Usage: python -m core.analyzer <python_file> [--json] [--ai] [--share-source] [--static-only]")
        sys.exit(1)

    filename = files[0]
    results = analyze_file(filename, static_only=static_only)

    ai_reasoning = None
    if ai_mode:
        ai_reasoning = run_ai_reasoning(
            filename=filename,
            findings=results,
            user_consent=share_source,
        )

    if json_mode:
        from core.json_reporter import print_json_report
        print_json_report(
            filename,
            results=results,
            ai_reasoning=ai_reasoning,
            static_only=static_only,
        )
    else:
        print_report(
            filename,
            results=results,
            ai_reasoning=ai_reasoning,
            static_only=static_only,
        )


if __name__ == "__main__":
    main()