from core.analyzer import analyze_file, print_report, is_error


def test_missing_file():
    results = analyze_file("missing_file.py")

    assert any(
        issue["type"] == "FileError"
        for issue in results
    )


def test_syntax_error(tmp_path):
    file = tmp_path / "broken.py"
    file.write_text("def broken(\n", encoding="utf-8")

    results = analyze_file(str(file))

    assert any(
        issue["type"] == "SyntaxError"
        for issue in results
    )


def test_duplicate_calculation(tmp_path):
    file = tmp_path / "duplicate.py"

    file.write_text(
        "price = 100\n"
        "quantity = 5\n"
        "total = price * quantity\n"
        "amount = price * quantity\n",
        encoding="utf-8"
    )

    results = analyze_file(str(file))

    assert any(
        issue["type"] == "DuplicateCode"
        for issue in results
    )


def test_clean_file(tmp_path):
    file = tmp_path / "clean.py"

    file.write_text(
        "def add(a, b):\n"
        "    return a + b\n",
        encoding="utf-8"
    )

    results = analyze_file(str(file))

    assert results == []


def test_findings_have_required_fields(tmp_path):
    file = tmp_path / "example.py"

    file.write_text(
        "price = 100\n"
        "quantity = 5\n"
        "total = price * quantity\n"
        "amount = price * quantity\n",
        encoding="utf-8"
    )

    results = analyze_file(str(file))

    for issue in results:
        assert "type" in issue
        assert "line" in issue
        assert "message" in issue
        assert "why" in issue
        assert "fix" in issue
        assert "concept" in issue


def test_name_error_typo_suggestion():
    result = analyze_file("tests/name_error_demo.py")

    errors = [
        item for item in result
        if item.get("type") == "NameError"
    ]

    assert errors
    assert "student_name" in errors[0]["message"]


def test_runtime_file_not_found_error_classified_as_error(tmp_path, capsys):
    file = tmp_path / "missing_file_runtime.py"
    file.write_text(
        'with open("non_existent_file_xyz_123.txt", "r") as f:\n'
        '    print(f.read())\n',
        encoding="utf-8"
    )

    results = analyze_file(str(file))
    fnf_issues = [i for i in results if i.get("type") == "FileNotFoundError"]
    assert len(fnf_issues) == 1
    assert is_error(fnf_issues[0])

    print_report(str(file))
    captured = capsys.readouterr().out
    assert "[ERROR] FileNotFoundError" in captured
    assert "Overall Result: FAIL" in captured
    assert "RUNTIME: FAIL" in captured
    assert "Errors: 1" in captured
    assert "Warnings: 0" in captured


def test_runtime_error_classified_as_error(tmp_path, capsys):
    file = tmp_path / "runtime_error.py"
    file.write_text('raise RuntimeError("operation failed")\n', encoding="utf-8")

    results = analyze_file(str(file))
    re_issues = [i for i in results if i.get("type") == "RuntimeError"]
    assert len(re_issues) == 1
    assert is_error(re_issues[0])

    print_report(str(file))
    captured = capsys.readouterr().out
    assert "[ERROR] RuntimeError" in captured
    assert "Overall Result: FAIL" in captured
    assert "RUNTIME: FAIL" in captured


def test_custom_runtime_exception_classified_as_error(tmp_path, capsys):
    file = tmp_path / "custom_error.py"
    file.write_text(
        "class CustomFailure(Exception):\n"
        "    pass\n\n"
        "raise CustomFailure('critical issue')\n",
        encoding="utf-8"
    )

    results = analyze_file(str(file))
    custom_issues = [i for i in results if i.get("type") == "CustomFailure"]
    assert len(custom_issues) == 1
    assert is_error(custom_issues[0])

    print_report(str(file))
    captured = capsys.readouterr().out
    assert "[ERROR] CustomFailure" in captured
    assert "Overall Result: FAIL" in captured
    assert "RUNTIME: FAIL" in captured


def test_code_quality_warnings_remain_warnings(tmp_path, capsys):
    file = tmp_path / "quality_warning.py"
    file.write_text(
        "import math\n"
        "def compute():\n"
        "    unused_var = 42\n"
        "    return 10\n",
        encoding="utf-8"
    )

    results = analyze_file(str(file))
    assert results
    for issue in results:
        assert not is_error(issue)

    print_report(str(file))
    captured = capsys.readouterr().out
    assert "[WARNING]" in captured
    assert "[ERROR]" not in captured
    assert "Overall Result: PASS WITH WARNINGS" in captured
    assert "RUNTIME: PASS" in captured
    assert "Errors: 0" in captured


def test_standard_runtime_errors_classified_as_errors():
    error_types_to_verify = [
        "IndexError",
        "ZeroDivisionError",
        "NameError",
        "ValueError",
        "KeyError",
        "FileNotFoundError",
        "ModuleNotFoundError",
        "Runtime Error",
        "Timeout Error",
        "TypeError",
        "AttributeError",
        "ImportError",
        "AssertionError",
        "RecursionError",
    ]
    for error_type in error_types_to_verify:
        finding = {
            "type": error_type,
            "line": 1,
            "message": "test",
            "concept": "Runtime Error Handling",
        }
        assert is_error(finding), f"{error_type} with runtime concept should be classified as an error"
        finding_no_concept = {
            "type": error_type,
            "line": 1,
            "message": "test",
            "concept": "General",
        }
        assert is_error(finding_no_concept), f"{error_type} in ERROR_TYPES should be classified as an error"