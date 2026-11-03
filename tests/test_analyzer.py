from core.quality import check_quality
from core.complexity import check_complexity
from core.smells import check_smells


# ==========================================
# QUALITY TESTS
# ==========================================

def test_unused_import():
    code = """
import math
print("Hello")
"""
    issues = check_quality(code)
    assert any(i["type"] == "UnusedImport" for i in issues)


def test_unused_variable():
    code = """
x = 10
print("Hello")
"""
    issues = check_quality(code)
    assert any(i["type"] == "UnusedVariable" for i in issues)


def test_no_unused_variable():
    code = """
x = 10
print(x)
"""
    issues = check_quality(code)
    assert not any(i["type"] == "UnusedVariable" for i in issues)


# ==========================================
# COMPLEXITY TESTS
# ==========================================

def test_medium_complexity():
    code = """
def calculate(a, b, c, d, e, f):
    if a:
        if b:
            if c:
                if d:
                    if e:
                        if f:
                            return 1
    return 0
"""
    issues = check_complexity(code)
    assert any(i["type"] == "MediumComplexity" for i in issues)


def test_simple_function_complexity():
    code = """
def add(a, b):
    return a + b
"""
    issues = check_complexity(code)
    assert not any(
        i["type"] in ["MediumComplexity", "HighComplexity"]
        for i in issues
    )


def test_high_complexity():
    code = """
def calculate(a, b, c, d, e, f, g, h, i):
    if a:
        if b:
            if c:
                if d:
                    if e:
                        if f:
                            if g:
                                if h:
                                    if i:
                                        return 1
    return 0
"""
    issues = check_complexity(code)
    assert any(i["type"] == "HighComplexity" for i in issues)


def test_nested_function_complexity():
    code = """
def outer():
    def inner(a, b, c, d, e, f):
        if a:
            if b:
                if c:
                    if d:
                        if e:
                            if f:
                                return 1
        return 0

    return 1
"""
    issues = check_complexity(code)
    assert not any(
        i["type"] in ["MediumComplexity", "HighComplexity"]
        and i["message"].startswith("Function 'outer'")
        for i in issues
    )


def test_boolean_condition_complexity():
    code = """
def check(a, b, c, d, e):
    if a and b and c and d and e:
        return True
    return False
"""
    issues = check_complexity(code)
    assert any(i["type"] == "MediumComplexity" for i in issues)


# ==========================================
# CODE SMELL TESTS
# ==========================================

def test_duplicate_calculation():
    code = """
price = 100
quantity = 5
total = price * quantity
amount = price * quantity
"""
    issues = check_smells(code)
    assert any(i["type"] == "DuplicateCode" for i in issues)


def test_simple_assignments_not_duplicate_code():
    code = """
x = 500
y = 500
"""
    issues = check_smells(code)
    assert not any(i["type"] == "DuplicateCode" for i in issues)


def test_empty_function():
    code = """
def unfinished():
    pass
"""
    issues = check_smells(code)
    assert any(i["type"] == "EmptyFunction" for i in issues)


def test_excessive_print():
    code = """
print(1)
print(2)
print(3)
print(4)
print(5)
print(6)
"""
    issues = check_smells(code)
    assert any(i["type"] == "ExcessivePrint" for i in issues)


def test_invalid_syntax_returns_empty_smells():
    code = """
def broken(
"""
    assert check_smells(code) == []


# ==========================================
# SCOPE-AWARE VARIABLE TESTS
# ==========================================

def test_variable_used_in_own_function():
    code = """
def first():
    value = 10
    print(value)

def second():
    value = 20
    print(value)
"""
    issues = check_quality(code)
    assert not any(
        i["type"] == "UnusedVariable" and "'value'" in i["message"]
        for i in issues
    )


def test_unused_variable_inside_function():
    code = """
def calculate():
    result = 100
    return 0
"""
    issues = check_quality(code)
    assert any(
        i["type"] == "UnusedVariable" and "'result'" in i["message"]
        for i in issues
    )


def test_variable_used_in_nested_function():
    code = """
def outer():
    value = 10

    def inner():
        print(value)

    inner()
"""
    issues = check_quality(code)
    assert not any(
        i["type"] == "UnusedVariable" and "'value'" in i["message"]
        for i in issues
    )


def test_unused_variable_not_hidden_by_another_scope():
    code = """
def first():
    value = 10
    return 0

def second():
    value = 20
    print(value)
"""
    issues = check_quality(code)
    assert any(
        i["type"] == "UnusedVariable"
        and "'value'" in i["message"]
        and i["line"] == 3
        for i in issues
    )


def test_function_parameters_are_not_unused_variables():
    code = """
def greet(name):
    print(name)
"""
    issues = check_quality(code)
    assert not any(i["type"] == "UnusedVariable" for i in issues)


def test_variable_shadowing():
    code = """
value = 10

def calculate():
    value = 20
    print(value)

print(value)
"""
    issues = check_quality(code)
    assert not any(
        i["type"] == "UnusedVariable" and "'value'" in i["message"]
        for i in issues
    )


# ==========================================
# GLOBAL AND NONLOCAL VARIABLE TESTS
# ==========================================

def test_global_variable_usage():
    code = """
count = 0

def update():
    global count
    count = 10

update()
print(count)
"""
    issues = check_quality(code)
    assert not any(
        i["type"] == "UnusedVariable" and "'count'" in i["message"]
        for i in issues
    )


def test_nonlocal_variable_usage():
    code = """
def outer():
    count = 0

    def inner():
        nonlocal count
        count = 10

    inner()
    print(count)
"""
    issues = check_quality(code)
    assert not any(
        i["type"] == "UnusedVariable" and "'count'" in i["message"]
        for i in issues
    )


def test_genuinely_unused_global_variable():
    code = """
unused_value = 100

def calculate():
    return 10
"""
    issues = check_quality(code)
    assert any(
        i["type"] == "UnusedVariable"
        and "'unused_value'" in i["message"]
        for i in issues
    )


# ==========================================
# UNREACHABLE CODE TESTS
# ==========================================

def test_unreachable_code_after_return():
    code = """
def calculate():
    return 10
    print("Never executes")
"""
    issues = check_quality(code)
    assert any(i["type"] == "UnreachableCode" for i in issues)


def test_unreachable_code_after_both_branches_return():
    code = """
def calculate(value):
    if value:
        return 10
    else:
        return 20

    print("Never executes")
"""
    issues = check_quality(code)
    assert any(
        i["type"] == "UnreachableCode" and i["line"] == 8
        for i in issues
    )


def test_reachable_code_after_if_without_else():
    code = """
def calculate(value):
    if value:
        return 10

    print("Can execute")
"""
    issues = check_quality(code)
    assert not any(
        i["type"] == "UnreachableCode" and i["line"] == 5
        for i in issues
    )

def test_nested_function_unreachable_code_not_duplicated():
    from core.quality import check_quality

    code = """
def outer():
    def inner():
        return
        print("Never executes")
"""

    issues = check_quality(code)

    unreachable = [
        issue for issue in issues
        if issue["type"] == "UnreachableCode"
    ]

    assert len(unreachable) == 1

def test_unused_import_inside_function():
    from core.quality import check_quality

    code = """
def calculate():
    import json
    return 10
"""

    issues = check_quality(code)

    unused_imports = [
        issue for issue in issues
        if issue["type"] == "UnusedImport"
    ]

    assert len(unused_imports) == 1
    assert unused_imports[0]["message"] == (
        "'json' is imported but never used."
    )

def test_import_usage_is_scope_aware():
    from core.quality import check_quality

    code = """
import json

def first():
    import math
    return math.sqrt(16)

def second():
    import json
    return 10

print(json.dumps({"status": "ok"}))
"""

    issues = check_quality(code)

    unused_imports = [
        issue for issue in issues
        if issue["type"] == "UnusedImport"
    ]

    assert len(unused_imports) == 1
    assert unused_imports[0]["message"] == (
        "'json' is imported but never used."
    )
    assert unused_imports[0]["line"] == 9

def test_unreachable_code_after_try_finally_return():
    from core.quality import check_quality

    code = """
def calculate():
    try:
        return 10
    finally:
        print("Cleanup")

    print("Never executes")
"""

    issues = check_quality(code)

    unreachable = [
        issue for issue in issues
        if issue["type"] == "UnreachableCode"
    ]

    assert any(
        issue["line"] == 8
        for issue in unreachable
    )


def test_unreachable_code_when_finally_returns():
    code = """
def calculate():
    try:
        print("Hello")
    finally:
        return 10

    print("Never executes")
"""
    issues = check_quality(code)
    unreachable = [i for i in issues if i["type"] == "UnreachableCode"]
    assert any(i["line"] == 8 for i in unreachable)


def test_finally_block_itself_not_marked_unreachable():
    code = """
def calculate():
    try:
        return 10
    finally:
        print("Cleanup")
"""
    issues = check_quality(code)
    unreachable = [i for i in issues if i["type"] == "UnreachableCode"]
    assert len(unreachable) == 0


def test_unreachable_code_after_try_except_both_return():
    code = """
def calculate(val):
    try:
        if val > 0:
            return 10
        raise ValueError("Invalid")
    except ValueError:
        return -1
    finally:
        print("Cleanup")

    print("Never executes")
"""
    issues = check_quality(code)
    unreachable = [i for i in issues if i["type"] == "UnreachableCode"]
    assert any(i["line"] == 12 for i in unreachable)


def test_reachable_code_when_except_does_not_terminate():
    code = """
def calculate():
    try:
        return 10
    except ValueError:
        print("Caught")
    finally:
        print("Cleanup")

    print("Can execute if exception occurred")
"""
    issues = check_quality(code)
    unreachable = [i for i in issues if i["type"] == "UnreachableCode"]
    assert not any(i["line"] == 10 for i in unreachable)


def test_reachable_code_after_try_finally_without_return():
    code = """
def calculate():
    try:
        print("Executing")
    finally:
        print("Cleanup")

    print("Can execute")
"""
    issues = check_quality(code)
    unreachable = [i for i in issues if i["type"] == "UnreachableCode"]
    assert not any(i["line"] == 8 for i in unreachable)


def test_unreachable_code_nested_try_finally():
    code = """
def calculate():
    try:
        try:
            return 10
        finally:
            print("Inner cleanup")
    finally:
        print("Outer cleanup")

    print("Never executes")
"""
    issues = check_quality(code)
    unreachable = [i for i in issues if i["type"] == "UnreachableCode"]
    assert any(i["line"] == 11 for i in unreachable)


def test_unreachable_code_try_except_else_all_terminate():
    code = """
def calculate():
    try:
        print("Trying")
    except ValueError:
        return 20
    else:
        return 30
    finally:
        print("Cleanup")

    print("Never executes")
"""
    issues = check_quality(code)
    unreachable = [i for i in issues if i["type"] == "UnreachableCode"]
    assert any(i["line"] == 12 for i in unreachable)


# ==========================================
# PHASE 6 REGRESSION TESTS (A - G)
# ==========================================

def test_unreachable_code_inside_try_else_when_try_returns():
    """A. Unreachable statements inside try...else when the try body returns."""
    code = """
def calculate():
    try:
        return 10
    except ValueError:
        pass
    else:
        print("Unreachable in else")
"""
    issues = check_quality(code)
    unreachable = [i for i in issues if i["type"] == "UnreachableCode"]
    assert any(i["line"] == 8 for i in unreachable)
    assert not any(i["line"] > 8 for i in unreachable)


def test_reachable_code_inside_try_else_when_try_completes_normally():
    """B. Reachable statements inside try...else when the try body completes normally."""
    code = """
def calculate():
    try:
        print("Working")
    except ValueError:
        pass
    else:
        print("Reachable in else")
"""
    issues = check_quality(code)
    unreachable = [i for i in issues if i["type"] == "UnreachableCode"]
    assert len(unreachable) == 0


def test_reachable_code_after_except_fallthrough():
    """C. An except handler that can fall through."""
    code = """
def calculate():
    try:
        return 10
    except ValueError:
        print("Caught")

    print("Reachable after try-except")
"""
    issues = check_quality(code)
    unreachable = [i for i in issues if i["type"] == "UnreachableCode"]
    assert not any(i["line"] == 8 for i in unreachable)


def test_finally_block_executable_statements_reachable():
    """D. A finally block that contains executable statements."""
    code = """
def calculate():
    try:
        return 10
    finally:
        print("Cleanup 1")
        print("Cleanup 2")
"""
    issues = check_quality(code)
    unreachable = [i for i in issues if i["type"] == "UnreachableCode"]
    assert len(unreachable) == 0


def test_return_inside_try_overridden_by_return_in_finally():
    """E. A return inside try overridden by return inside finally."""
    code = """
def calculate():
    try:
        return 10
    finally:
        return 20

    print("Unreachable after try-finally")
"""
    issues = check_quality(code)
    unreachable = [i for i in issues if i["type"] == "UnreachableCode"]
    assert not any(i["line"] in (4, 6) for i in unreachable)
    assert any(i["line"] == 8 for i in unreachable)


def test_break_inside_finally_overriding_return_inside_loop():
    """F. A break inside finally overriding a return inside a loop."""
    code = """
def find_item():
    for x in [1, 2, 3]:
        try:
            return x
        finally:
            break
        print("Unreachable inside loop")

    print("Reachable after loop")
"""
    issues = check_quality(code)
    unreachable = [i for i in issues if i["type"] == "UnreachableCode"]
    assert any(i["line"] == 8 for i in unreachable)
    assert not any(i["line"] == 10 for i in unreachable)


def test_unreachable_code_after_try_finally():
    """G. Existing unreachable-code detection after try/finally."""
    code = """
def calculate():
    try:
        return 10
    finally:
        print("Cleanup")

    print("Unreachable after try-finally")
"""
    issues = check_quality(code)
    unreachable = [i for i in issues if i["type"] == "UnreachableCode"]
    assert any(i["line"] == 8 for i in unreachable)


# ==========================================
# CONVENTIONAL METHOD RECEIVER REGRESSION TESTS
# ==========================================

def test_instance_method_self_not_flagged_as_unused():
    """Conventional self parameter of an instance method is not an unused variable."""
    code = """
class Solution:
    def average(self, a: int, b: int) -> float:
        return (a + b) / 2
"""
    issues = check_quality(code)
    assert not any(i["type"] == "UnusedVariable" for i in issues)


def test_async_instance_method_self_not_flagged_as_unused():
    """Conventional self parameter of an async instance method is not flagged."""
    code = """
class Solution:
    async def average(self, a: int, b: int) -> float:
        return (a + b) / 2
"""
    issues = check_quality(code)
    assert not any(i["type"] == "UnusedVariable" for i in issues)


def test_class_method_cls_not_flagged_as_unused():
    """Conventional cls parameter of a classmethod is not an unused variable."""
    code = """
class Solution:
    @classmethod
    def factory(cls, a: int, b: int) -> int:
        return a + b
"""
    issues = check_quality(code)
    assert not any(i["type"] == "UnusedVariable" for i in issues)


def test_dunder_new_cls_not_flagged_as_unused():
    """Conventional cls parameter of __new__ is not an unused variable even if unused."""
    code = """
class Solution:
    def __new__(cls):
        return 1
"""
    issues = check_quality(code)
    assert not any(i["type"] == "UnusedVariable" for i in issues)


def test_method_genuinely_unused_local_variable_is_flagged():
    """Genuinely unused local variable inside a method is still detected."""
    code = """
class Solution:
    def average(self, a: int, b: int) -> float:
        unused_val = 100
        return (a + b) / 2
"""
    issues = check_quality(code)
    assert any(
        i["type"] == "UnusedVariable" and "'unused_val'" in i["message"]
        for i in issues
    )


def test_method_genuinely_unused_parameter_is_flagged():
    """Genuinely unused parameter beyond self is still detected."""
    code = """
class Solution:
    def average(self, a: int, b: int, extra_unused: int) -> float:
        return (a + b) / 2
"""
    issues = check_quality(code)
    assert any(
        i["type"] == "UnusedVariable" and "'extra_unused'" in i["message"]
        for i in issues
    )


def test_top_level_function_unused_self_and_cls_are_flagged():
    """Self or cls on top-level functions (not methods) are not conventional receivers and are flagged."""
    code_self = """
def standalone(self, a: int) -> int:
    return a
"""
    issues_self = check_quality(code_self)
    assert any(
        i["type"] == "UnusedVariable" and "'self'" in i["message"]
        for i in issues_self
    )

    code_cls = """
def standalone(cls, a: int) -> int:
    return a
"""
    issues_cls = check_quality(code_cls)
    assert any(
        i["type"] == "UnusedVariable" and "'cls'" in i["message"]
        for i in issues_cls
    )


def test_staticmethod_unused_self_and_cls_are_flagged():
    """Staticmethod does not receive self or cls, so unused parameters are flagged."""
    code_self = """
class Solution:
    @staticmethod
    def calc(self, a: int) -> int:
        return a
"""
    issues_self = check_quality(code_self)
    assert any(
        i["type"] == "UnusedVariable" and "'self'" in i["message"]
        for i in issues_self
    )

    code_cls = """
class Solution:
    @staticmethod
    def calc(cls, a: int) -> int:
        return a
"""
    issues_cls = check_quality(code_cls)
    assert any(
        i["type"] == "UnusedVariable" and "'cls'" in i["message"]
        for i in issues_cls
    )


def test_local_assignment_to_self_or_cls_in_method_is_flagged_if_unused():
    """Local assignments in method bodies to self or cls are flagged if unused."""
    code_cls = """
class Solution:
    def average(self, a: int, b: int) -> float:
        cls = 42
        return (a + b) / 2
"""
    issues = check_quality(code_cls)
    assert any(
        i["type"] == "UnusedVariable" and "'cls'" in i["message"]
        for i in issues
    )

