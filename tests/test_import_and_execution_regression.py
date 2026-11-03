import os
import subprocess
import sys
import pytest

from core.analyzer import analyze_file, is_error
from core.runner import run_code, get_project_root, get_execution_env
from core.runtime import check_runtime
from core.smells import check_smells


def test_analyzing_project_test_files_has_no_modulenotfounderror():
    """Verify that EdgeMind can analyze its own test files without ModuleNotFoundError."""
    files_to_check = [
        "tests/test_integration.py",
        "tests/test_analyzer.py",
        "tests/test_null_adapter.py",
    ]
    for filepath in files_to_check:
        results = analyze_file(filepath)
        import_errors = [
            r for r in results
            if r.get("type") in {"ModuleNotFoundError", "ImportError"}
        ]
        assert not import_errors, f"Unexpected import error in {filepath}: {import_errors}"
        runtime_errors = [r for r in results if is_error(r)]
        assert not runtime_errors, f"Unexpected runtime errors in {filepath}: {runtime_errors}"


def test_check_runtime_resolves_project_packages():
    """Verify check_runtime executes test files and finds 'core' and 'adapters'."""
    assert check_runtime("tests/test_integration.py") == []
    assert check_runtime("tests/test_null_adapter.py") == []


def test_runner_run_code_executes_successfully():
    """Verify core/runner.py run_code correctly resolves the environment."""
    res_integration = run_code("tests/test_integration.py")
    assert res_integration["success"] is True
    assert res_integration["error"] == ""

    res_adapter = run_code("tests/test_null_adapter.py")
    assert res_adapter["success"] is True
    assert res_adapter["error"] == ""


def test_genuine_missing_dependency_is_diagnosed(tmp_path):
    """Verify genuinely missing imports are correctly flagged and diagnosed."""
    bad_file = tmp_path / "bad_import.py"
    bad_file.write_text("import completely_non_existent_package_xyz_987\n", encoding="utf-8")

    results = analyze_file(str(bad_file))
    mnf = [r for r in results if r.get("type") == "ModuleNotFoundError"]
    assert len(mnf) == 1, "Genuinely missing dependency must be reported as ModuleNotFoundError"
    assert is_error(mnf[0]), "ModuleNotFoundError must be classified as an error"
    assert "completely_non_existent_package_xyz_987" in mnf[0]["message"]
    assert mnf[0]["concept"] == "Runtime Error Handling"


def test_isolated_subproject_package_imports(tmp_path):
    """Verify target files within a separate project structure resolve their own packages."""
    project_dir = tmp_path / "my_project"
    project_dir.mkdir()
    (project_dir / "pyproject.toml").write_text("[project]\nname='my_project'\n", encoding="utf-8")

    pkg_dir = project_dir / "pkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text("", encoding="utf-8")
    (pkg_dir / "service.py").write_text("def get_value(): return 42\n", encoding="utf-8")

    script = pkg_dir / "main.py"
    script.write_text("from pkg.service import get_value\nres = get_value()\n", encoding="utf-8")

    results = analyze_file(str(script))
    errors = [r for r in results if is_error(r)]
    assert errors == [], f"Expected clean run for subproject, got errors: {errors}"


def test_magic_number_assert_exclusion():
    """Verify that numbers inside assert statements are not flagged as magic numbers."""
    code = """
def test_example():
    assert unused_imports[0]["line"] == 9
    assert duration < 0.01
    assert any(i["line"] == 8 for i in unreachable)
"""
    issues = check_smells(code)
    magic_numbers = [i for i in issues if i["type"] == "MagicNumber"]
    assert magic_numbers == [], f"Assert statements should not trigger magic numbers: {magic_numbers}"


def test_magic_number_still_detects_real_magic_numbers():
    """Verify that real magic numbers in calculations and conditions are still caught."""
    code = """
def calculate_tax(amount):
    if amount > 99.5:
        return amount * 1.18
    return amount
"""
    issues = check_smells(code)
    magic_numbers = [i for i in issues if i["type"] == "MagicNumber"]
    assert len(magic_numbers) >= 2
    detected_vals = [i["message"] for i in magic_numbers]
    assert any("99.5" in msg for msg in detected_vals)
    assert any("1.18" in msg for msg in detected_vals)


def test_cli_execution_with_test_file():
    """Verify running the analyzer CLI on a test file produces exit code 0 and PASS."""
    result = subprocess.run(
        [sys.executable, "-m", "core.analyzer", "tests/test_integration.py"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "Overall Result: PASS" in result.stdout
    assert "RUNTIME: PASS" in result.stdout
    assert "Errors: 0" in result.stdout
