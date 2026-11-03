import pytest
from core.smells import check_smells
from core.logic import check_logic
from core.analyzer import analyze_file, is_error


# 1. Dictionary numeric values not flagged as magic numbers
def test_dict_numeric_values_not_flagged_as_magic_numbers():
    code = 'student = {"name": "Alex", "age": 20, "score": 95}'
    issues = check_smells(code)
    magic_issues = [i for i in issues if i["type"] == "MagicNumber"]
    assert not magic_issues, f"Dictionary data should not be flagged as magic numbers: {magic_issues}"


# 2. Ordinary function-call arguments not flagged as magic numbers
def test_ordinary_function_call_arguments_not_flagged():
    code = 'calculate_sum(10, 20)'
    issues = check_smells(code)
    magic_issues = [i for i in issues if i["type"] == "MagicNumber"]
    assert not magic_issues, f"Top-level function arguments should not be magic numbers: {magic_issues}"

    code_print = 'print(calculate_sum(10, 20))'
    issues_print = check_smells(code_print)
    magic_print = [i for i in issues_print if i["type"] == "MagicNumber"]
    assert not magic_print, f"Print call arguments should not be magic numbers: {magic_print}"


# 3. Genuine magic numbers in calculations remain detected
def test_genuine_magic_numbers_in_calculations_detected():
    code = """
def calculate_tax(amount):
    if amount > 99.5:
        return amount * 1.18
    return amount
"""
    issues = check_smells(code)
    magic = [i for i in issues if i["type"] == "MagicNumber"]
    assert len(magic) >= 2, f"Expected 99.5 and 1.18 to be detected: {magic}"
    messages = [i["message"] for i in magic]
    assert any("99.5" in m for m in messages), "Threshold 99.5 should be flagged"
    assert any("1.18" in m for m in messages), "Multiplier 1.18 should be flagged"


# 4. Average-pattern detection under multiple function names
@pytest.mark.parametrize("fn_name", ["average", "calculate_average", "compute_avg", "find_average"])
def test_average_pattern_multiple_function_names(fn_name):
    code = f"""
def {fn_name}(a, b):
    return a + b / 2
"""
    warnings = check_logic(code)
    assert any(
        w.type == "Possible Logic Error" and "average" in w.message.lower()
        for w in warnings
    ), f"Expected logic warning for {fn_name}"


# 5. Average-like expression in an assignment
def test_average_expression_in_assignment():
    # Module-level assignment
    code_mod = "avg = a + b / 2"
    warnings_mod = check_logic(code_mod)
    assert any(
        w.type == "Possible Logic Error" and "average" in w.message.lower()
        for w in warnings_mod
    ), "Expected warning for module-level avg assignment"

    # Inside function assignment
    code_fn = """
def compute_scores(a, b):
    average = a + b / 2
    return average
"""
    warnings_fn = check_logic(code_fn)
    assert any(
        w.type == "Possible Logic Error" and "average" in w.message.lower()
        for w in warnings_fn
    ), "Expected warning for function-level average assignment"


# 6. Likely inclusive-sum boundary issue
def test_likely_inclusive_sum_boundary_issue():
    code = """
def calculate_sum(n):
    total = 0
    for i in range(1, n):
        total += i
    return total
"""
    warnings = check_logic(code)
    off_by_one = [w for w in warnings if "off-by-one" in w.message.lower()]
    assert len(off_by_one) == 1, f"Expected off-by-one warning for range(1, n), got {warnings}"
    assert "range(1, n)" in off_by_one[0].message
    assert "n + 1" in off_by_one[0].fix


# 7. Intentional exclusive range not falsely flagged
def test_intentional_exclusive_range_not_falsely_flagged():
    # range(1, len(items))
    code_len = """
def process_tail(items):
    for i in range(1, len(items)):
        print(items[i])
"""
    warnings_len = check_logic(code_len)
    assert not any("off-by-one" in w.message.lower() for w in warnings_len)

    # range(n)
    code_zero_start = """
def print_n_times(n):
    for i in range(n):
        print(i)
"""
    warnings_zero = check_logic(code_zero_start)
    assert not any("off-by-one" in w.message.lower() for w in warnings_zero)

    # Correct inclusive sum range(1, n + 1)
    code_correct = """
def calculate_sum(n):
    total = 0
    for i in range(1, n + 1):
        total += i
    return total
"""
    warnings_correct = check_logic(code_correct)
    assert not any("off-by-one" in w.message.lower() for w in warnings_correct)


# 8. Nested-loop diagnostic
def test_nested_loops_diagnostic():
    # Nested loop over the same collection
    code = """
def print_pairs(numbers):
    for i in numbers:
        for j in numbers:
            print(i, j)
"""
    issues = check_smells(code)
    nested_issues = [i for i in issues if i["type"] == "NestedLoops"]
    assert len(nested_issues) >= 1, "Expected NestedLoops warning for pairwise iteration"
    assert any("numbers" in i["message"] for i in nested_issues)
    assert nested_issues[0]["concept"] == "Performance"


# 9. Single loop not incorrectly flagged as nested
def test_single_loop_not_flagged_as_nested():
    code = """
def print_items(numbers):
    for i in numbers:
        print(i)
"""
    issues = check_smells(code)
    assert not any(i["type"] == "NestedLoops" for i in issues)


# 10. Existing clean-code example remains warning-free
def test_clean_code_example_remains_warning_free():
    results = analyze_file("tests/test11_clean_code.py")
    assert results == [], f"Expected clean code to have zero findings, got: {results}"
