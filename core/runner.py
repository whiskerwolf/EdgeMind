import os
import subprocess
import sys
import re


def get_project_root(filename):
    """
    Find the project root for a given file by searching for common root markers
    (e.g., .git, pyproject.toml, pytest.ini, requirements.txt, setup.py).
    Falls back to current working directory or file directory.
    """
    abs_path = os.path.abspath(filename)
    start_dir = abs_path if os.path.isdir(abs_path) else os.path.dirname(abs_path)

    markers = {
        ".git",
        "pyproject.toml",
        "setup.py",
        "setup.cfg",
        "pytest.ini",
        "requirements.txt",
    }

    current = start_dir
    while True:
        for marker in markers:
            if os.path.exists(os.path.join(current, marker)):
                return current
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent

    cwd = os.getcwd()
    try:
        if os.path.commonpath([cwd, abs_path]) == cwd:
            return cwd
    except ValueError:
        pass

    return start_dir


def get_execution_env(filename):
    """
    Construct the subprocess environment and working directory for running target files.
    Ensures the target file directory, project root, and current working directory
    are on PYTHONPATH so legitimate relative imports and package imports work.
    """
    abs_filename = os.path.abspath(filename)
    file_dir = os.path.dirname(abs_filename)
    project_root = get_project_root(abs_filename)
    cwd = os.getcwd()

    env = os.environ.copy()

    # Priority order for PYTHONPATH:
    # 1. file_dir (so the script can import sibling modules)
    # 2. project_root (so project-level packages like core, adapters are found)
    # 3. cwd (so current workspace imports work)
    # 4. existing PYTHONPATH
    paths_to_add = []
    for candidate in [file_dir, project_root, cwd]:
        if candidate and os.path.isdir(candidate) and candidate not in paths_to_add:
            paths_to_add.append(candidate)

    existing_pythonpath = env.get("PYTHONPATH", "")
    if existing_pythonpath:
        for p in existing_pythonpath.split(os.pathsep):
            if p and p not in paths_to_add:
                paths_to_add.append(p)

    env["PYTHONPATH"] = os.pathsep.join(paths_to_add)

    # Determine subprocess working directory:
    # If the file is within cwd, use cwd. Otherwise use project_root.
    target_cwd = cwd
    try:
        if os.path.commonpath([cwd, abs_filename]) != cwd:
            target_cwd = project_root
    except ValueError:
        target_cwd = project_root

    return env, target_cwd, abs_filename


import collections
import ctypes
import signal
import threading
from typing import Tuple

IS_WINDOWS = sys.platform == "win32"
IS_POSIX = os.name == "posix"

DEFAULT_TIMEOUT = 5.0
DEFAULT_MAX_OUTPUT_BYTES = 256 * 1024  # 256 KB


class ProcessExecutionResult:
    """Encapsulates the result of executing a target process with resource limits."""

    def __init__(
        self,
        returncode: int,
        stdout: str,
        stderr: str,
        timed_out: bool = False,
        stdout_truncated: bool = False,
        stderr_truncated: bool = False,
    ):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.timed_out = timed_out
        self.stdout_truncated = stdout_truncated
        self.stderr_truncated = stderr_truncated


if IS_WINDOWS:
    from ctypes import wintypes

    class IO_COUNTERS(ctypes.Structure):
        _fields_ = [
            ("ReadOperationCount", ctypes.c_uint64),
            ("WriteOperationCount", ctypes.c_uint64),
            ("OtherOperationCount", ctypes.c_uint64),
            ("ReadTransferCount", ctypes.c_uint64),
            ("WriteTransferCount", ctypes.c_uint64),
            ("OtherTransferCount", ctypes.c_uint64),
        ]

    class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_int64),
            ("PerJobUserTimeLimit", ctypes.c_int64),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
            ("IoInfo", IO_COUNTERS),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryLimit", ctypes.c_size_t),
            ("PeakJobMemoryLimit", ctypes.c_size_t),
        ]

    JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
    JobObjectExtendedLimitInformation = 9


class WindowsJobTracker:
    """
    Manages a Win32 Job Object with JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE.
    Ensures that when a timeout occurs or the job is closed, all processes
    in the process tree (including grandchild processes) are terminated.
    """

    def __init__(self):
        self.h_job = None
        if not IS_WINDOWS:
            return
        try:
            k32 = ctypes.windll.kernel32
            self.h_job = k32.CreateJobObjectW(None, None)
            if self.h_job:
                info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
                info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
                res = k32.SetInformationJobObject(
                    self.h_job,
                    JobObjectExtendedLimitInformation,
                    ctypes.byref(info),
                    ctypes.sizeof(info),
                )
                if not res:
                    self.close()
        except Exception:
            self.close()

    def assign_process(self, proc: subprocess.Popen) -> bool:
        if self.h_job and hasattr(proc, "_handle") and proc._handle:
            try:
                k32 = ctypes.windll.kernel32
                res = k32.AssignProcessToJobObject(self.h_job, int(proc._handle))
                return bool(res)
            except Exception:
                return False
        return False

    def terminate_all(self, exit_code: int = 1) -> None:
        if self.h_job:
            try:
                ctypes.windll.kernel32.TerminateJobObject(self.h_job, exit_code)
            except Exception:
                pass

    def close(self) -> None:
        if self.h_job:
            try:
                ctypes.windll.kernel32.CloseHandle(self.h_job)
            except Exception:
                pass
            self.h_job = None


def terminate_posix_process_tree(proc: subprocess.Popen) -> None:
    """Terminate the process group of a POSIX subprocess."""
    try:
        pgid = os.getpgid(proc.pid)
        os.killpg(pgid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        try:
            proc.kill()
        except OSError:
            pass


def _read_bounded_stream(
    stream,
    max_bytes: int,
    is_stderr: bool = False,
) -> Tuple[str, bool]:
    """
    Read bytes from stream into bounded memory buffers.
    For stderr, retains head and tail to ensure traceback information is preserved.
    """
    captured_head = bytearray()
    head_limit = max_bytes // 2 if is_stderr else max_bytes
    tail_limit = max_bytes // 2 if is_stderr else 0
    tail_deque = collections.deque(maxlen=tail_limit) if tail_limit > 0 else None
    truncated = False

    try:
        while True:
            chunk = stream.read(4096)
            if not chunk:
                break
            if len(captured_head) < head_limit:
                needed = head_limit - len(captured_head)
                captured_head.extend(chunk[:needed])
                overflow = chunk[needed:]
            else:
                overflow = chunk
                truncated = True

            if tail_deque is not None and overflow:
                truncated = True
                tail_deque.extend(overflow)
    except Exception:
        pass
    finally:
        try:
            stream.close()
        except Exception:
            pass

    head_str = captured_head.decode("utf-8", errors="replace")
    if truncated:
        if tail_deque:
            tail_str = bytes(tail_deque).decode("utf-8", errors="replace")
            content = (
                head_str
                + f"\n\n... [EdgeMind: stderr output truncated: exceeded {max_bytes} bytes limit] ...\n\n"
                + tail_str
            )
        else:
            content = (
                head_str
                + f"\n\n... [EdgeMind: stdout output truncated: exceeded {max_bytes} bytes limit] ..."
            )
        return content, True

    return head_str, False


def execute_target_process(
    filename: str,
    timeout: float = DEFAULT_TIMEOUT,
    max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES,
) -> ProcessExecutionResult:
    """
    Execute a Python file in a managed child process with process-tree cleanup
    and memory-bounded output collection.
    """
    env, target_cwd, abs_filename = get_execution_env(filename)

    job_tracker = WindowsJobTracker() if IS_WINDOWS else None

    popen_kwargs = {
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "cwd": target_cwd,
        "env": env,
    }
    if IS_POSIX:
        popen_kwargs["start_new_session"] = True

    proc = subprocess.Popen(
        [sys.executable, abs_filename],
        **popen_kwargs,
    )

    if job_tracker:
        job_tracker.assign_process(proc)

    stdout_res = ["", False]
    stderr_res = ["", False]

    def read_stdout():
        stdout_res[0], stdout_res[1] = _read_bounded_stream(
            proc.stdout, max_output_bytes, is_stderr=False
        )

    def read_stderr():
        stderr_res[0], stderr_res[1] = _read_bounded_stream(
            proc.stderr, max_output_bytes, is_stderr=True
        )

    t_stdout = threading.Thread(target=read_stdout, daemon=True)
    t_stderr = threading.Thread(target=read_stderr, daemon=True)
    t_stdout.start()
    t_stderr.start()

    timed_out = False
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        if job_tracker:
            job_tracker.terminate_all(exit_code=1)
        elif IS_POSIX:
            terminate_posix_process_tree(proc)
        else:
            try:
                proc.kill()
            except OSError:
                pass

        try:
            proc.wait(timeout=2.0)
        except (subprocess.TimeoutExpired, OSError):
            try:
                proc.kill()
                proc.wait(timeout=1.0)
            except OSError:
                pass
    finally:
        if job_tracker:
            job_tracker.close()

    t_stdout.join(timeout=1.5)
    t_stderr.join(timeout=1.5)

    return ProcessExecutionResult(
        returncode=proc.returncode if proc.returncode is not None else (1 if timed_out else 0),
        stdout=stdout_res[0],
        stderr=stderr_res[0],
        timed_out=timed_out,
        stdout_truncated=stdout_res[1],
        stderr_truncated=stderr_res[1],
    )


def run_code(
    filename: str,
    timeout: float = DEFAULT_TIMEOUT,
    max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES,
):
    try:
        exec_result = execute_target_process(
            filename,
            timeout=timeout,
            max_output_bytes=max_output_bytes,
        )

        if exec_result.timed_out:
            return {
                "success": False,
                "error": "TimeoutError: Program took too long to finish.",
                "line": 0,
                "timeout": True,
                "stdout": exec_result.stdout,
                "stderr": exec_result.stderr,
                "stdout_truncated": exec_result.stdout_truncated,
                "stderr_truncated": exec_result.stderr_truncated,
            }

        if exec_result.returncode == 0:
            return {
                "success": True,
                "error": "",
                "line": 0,
                "returncode": 0,
                "stdout": exec_result.stdout,
                "stderr": exec_result.stderr,
                "stdout_truncated": exec_result.stdout_truncated,
                "stderr_truncated": exec_result.stderr_truncated,
            }

        error = exec_result.stderr.strip()
        lines = re.findall(r'File ".*?", line (\d+)', error)
        line = int(lines[-1]) if lines else 0

        return {
            "success": False,
            "error": error,
            "line": line,
            "returncode": exec_result.returncode,
            "stdout": exec_result.stdout,
            "stderr": exec_result.stderr,
            "stdout_truncated": exec_result.stdout_truncated,
            "stderr_truncated": exec_result.stderr_truncated,
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "line": 0,
        }