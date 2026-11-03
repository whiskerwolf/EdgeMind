from core.diagnosis import diagnose


def test_index_error():
    result = diagnose("IndexError: list index out of range")
    assert result["type"] == "IndexError"


def test_zero_division_error():
    result = diagnose("ZeroDivisionError: division by zero")
    assert result["type"] == "ZeroDivisionError"


def test_name_error():
    result = diagnose("NameError: name 'x' is not defined")
    assert result["type"] == "NameError"


def test_value_error():
    result = diagnose("ValueError: invalid literal")
    assert result["type"] == "ValueError"


def test_key_error():
    result = diagnose("KeyError: 'age'")

    assert result["type"] == "KeyError"
    assert "age" in result["message"]
    assert result["why"]
    assert result["fix"]
    assert result["concept"]


def test_file_not_found_error():
    result = diagnose("FileNotFoundError: file not found")
    assert result["type"] == "FileNotFoundError"


def test_module_not_found_error():
    result = diagnose("ModuleNotFoundError: No module named 'abc'")
    assert result["type"] == "ModuleNotFoundError"


def test_unknown_error():
    result = diagnose("SomeUnknownError: something went wrong")
    assert result["type"] == "Runtime Error"


def test_empty_error():
    result = diagnose("")
    assert result["type"] == "UnknownError"


def test_multiline_traceback():
    error = (
        "Traceback (most recent call last):\n"
        "  File 'main.py', line 2, in <module>\n"
        "IndexError: list index out of range"
    )

    result = diagnose(error)
    assert result["type"] == "IndexError"


def test_diagnosis_fields():
    result = diagnose("TypeError: unsupported operation")

    for field in ("type", "message", "why", "fix", "concept"):
        assert field in result