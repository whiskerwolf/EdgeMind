import json
import os
import subprocess
import sys
import time
import pytest

from core.runner import (
    execute_target_process,
    run_code,
    DEFAULT_TIMEOUT,
    DEFAULT_MAX_OUTPUT_BYTES,
)
from core.runtime import check_runtime
from core.analyzer import analyze_file, is_error


def test_script_completes_successfully(tmp_path):
    """Verify that normal scripts execute cleanly and return standard outputs."""
    script = tmp_path / "clean_script.py"
    script.write_text("print('Execution Successful')\n", encoding="utf-8")

    res = run_code(str(script))
    assert res["success"] is True
    assert res["returncode"] == 0
    assert "Execution Successful" in res["stdout"]
    assert res["error"] == ""

    diagnostics = check_runtime(str(script))
    assert diagnostics == []


def test_script_raises_exception(tmp_path):
    """Verify that standard runtime exceptions are caught, localized, and diagnosed."""
    script = tmp_path / "div_zero.py"
    script.write_text("def calc():\n    return 1 / 0\ncalc()\n", encoding="utf-8")

    res = run_code(str(script))
    assert res["success"] is False
    assert res["line"] == 2
    assert "ZeroDivisionError" in res["error"]

    diagnostics = check_runtime(str(script))
    assert len(diagnostics) == 1
    assert diagnostics[0].type == "ZeroDivisionError"
    assert diagnostics[0].line == 2


def test_script_exceeds_timeout(tmp_path):
    """Verify that a target script exceeding timeout is terminated cleanly."""
    script = tmp_path / "slow_script.py"
    script.write_text("import time\ntime.sleep(10)\n", encoding="utf-8")

    # Run with a short 0.4s timeout
    res = run_code(str(script), timeout=0.4)
    assert res["success"] is False
    assert res.get("timeout") is True
    assert "TimeoutError" in res["error"]

    diagnostics = check_runtime(str(script), timeout=0.4)
    assert len(diagnostics) == 1
    assert diagnostics[0].type == "Timeout Error"
    assert diagnostics[0].message == "The program took too long to finish."


def test_child_process_attempts_to_outlive_parent_cleaned_up(tmp_path):
    """
    Verify that when a target script spawns a background grandchild process,
    timing out the target script terminates the entire process tree.
    """
    pid_file = tmp_path / "grandchild.pid"
    script = tmp_path / "spawner.py"

    pid_path_repr = repr(str(pid_file))
    # Child script spawns a grandchild process that attempts to sleep 60 seconds
    script.write_text(
        f"import subprocess, sys, time\n"
        f"p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
        f"with open({pid_path_repr}, 'w', encoding='utf-8') as f:\n"
        f"    f.write(str(p.pid))\n"
        f"time.sleep(60)\n",
        encoding="utf-8",
    )

    grandchild_pid = None
    try:
        # Run with short 0.6s timeout
        exec_res = execute_target_process(str(script), timeout=0.6)
        assert exec_res.timed_out is True

        # Wait up to 2 seconds for pid_file to be readable
        deadline = time.time() + 2.0
        while time.time() < deadline:
            if pid_file.exists() and pid_file.stat().st_size > 0:
                break
            time.sleep(0.05)

        assert pid_file.exists(), "Grandchild PID file was not created"
        grandchild_pid = int(pid_file.read_text(encoding="utf-8").strip())
        assert grandchild_pid > 0

        # Allow OS kernel up to 1 second to finalize process reaping
        time.sleep(0.5)

        # Platform-specific verification that grandchild process is dead
        if sys.platform == "win32":
            import ctypes
            from ctypes import wintypes
            k32 = ctypes.windll.kernel32
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            h_proc = k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, grandchild_pid)
            if h_proc:
                exit_code = wintypes.DWORD()
                k32.GetExitCodeProcess(h_proc, ctypes.byref(exit_code))
                k32.CloseHandle(h_proc)
                # 259 is STILL_ACTIVE
                assert exit_code.value != 259, f"Grandchild process {grandchild_pid} was not terminated!"
        else:
            try:
                os.kill(grandchild_pid, 0)
                alive = True
            except OSError:
                alive = False
            assert not alive, f"Grandchild process {grandchild_pid} was not terminated!"

    finally:
        # Cleanup safeguard in case test failed
        if grandchild_pid:
            try:
                if sys.platform == "win32":
                    subprocess.run(
                        ["taskkill", "/F", "/PID", str(grandchild_pid)],
                        capture_output=True,
                    )
                else:
                    os.kill(grandchild_pid, 9)
            except Exception:
                pass


def test_excessive_stdout_truncated(tmp_path):
    """Verify that massive stdout output is bounded and reported as truncated."""
    script = tmp_path / "flood_stdout.py"
    # Print 50,000 lines (~1MB of text)
    script.write_text("for i in range(50000):\n    print('FLOOOOODING_DATA_LINE')\n", encoding="utf-8")

    # Run with small 2048-byte limit
    res = run_code(str(script), max_output_bytes=2048)
    assert res["success"] is True
    assert res["stdout_truncated"] is True
    assert "EdgeMind: stdout output truncated" in res["stdout"]
    # Total buffered memory must remain tightly bounded
    assert len(res["stdout"]) < 6000


def test_excessive_stderr_preserves_traceback(tmp_path):
    """
    Verify that when stderr is flooded before raising an exception,
    the output limit retains the exception traceback in the tail.
    """
    script = tmp_path / "flood_stderr.py"
    script.write_text(
        "import sys\n"
        "for i in range(20000):\n"
        "    sys.stderr.write('DEBUG LOG MESSAGE FLOODING\\n')\n"
        "raise ValueError('critical_issue_in_application')\n",
        encoding="utf-8",
    )

    # Run with small 4096-byte limit
    diagnostics = check_runtime(str(script), max_output_bytes=4096)
    assert len(diagnostics) == 1
    assert diagnostics[0].type == "ValueError"
    assert "critical_issue_in_application" in diagnostics[0].message


def test_static_only_mode_never_invokes_runtime_execution(tmp_path):
    """Verify that static-only mode never executes target code or creates side effects."""
    canary = tmp_path / "should_not_exist.txt"
    script = tmp_path / "side_effect_probe.py"
    script.write_text(
        f"with open({repr(str(canary))}, 'w') as f:\n    f.write('FAIL')\n",
        encoding="utf-8",
    )

    results = analyze_file(str(script), static_only=True)
    assert not canary.exists(), "Target file was executed in static-only mode!"
    assert [r for r in results if is_error(r)] == []


def test_existing_ai_source_consent_behavior(tmp_path):
    """Verify that AI source code sharing consent gate remains strictly enforced."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "core.analyzer",
            "tests/test11_clean_code.py",
            "--static-only",
            "--ai",
            "--json",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    parsed = json.loads(result.stdout)
    assert parsed["runtime_status"] == "SKIPPED"
    assert "ai_reasoning" in parsed
    assert parsed["ai_reasoning"]["status"] == "skipped"
    assert "--share-source" in result.stderr
