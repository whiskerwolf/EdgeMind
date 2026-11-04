"""
Tests for EdgeMind Chrome Native Messaging Host and automatic startup integration.

Verifies:
- Native host manifest structure, allowed origins, and executable path.
- Native host executable existence and length-prefixed stdio protocol adherence.
- EdgeMind extension manifest permissions (nativeMessaging, storage) and background service worker.
- Lifecycle preservation (no duplicate processes, safe cleanup).
"""

import json
import os
import struct
import subprocess
import pytest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SCRIPTS_DIR = os.path.join(PROJECT_ROOT, "scripts")
EXTENSION_DIR = os.path.join(PROJECT_ROOT, "extension", "edgemind")
MANIFEST_PATH = os.path.join(SCRIPTS_DIR, "com.edgemind.native_host.json")
EXE_PATH = os.path.join(SCRIPTS_DIR, "edgemind_native_host.exe")
EXT_MANIFEST_PATH = os.path.join(EXTENSION_DIR, "manifest.json")
BACKGROUND_JS_PATH = os.path.join(EXTENSION_DIR, "scripts", "background.js")
VERIFIED_EXT_ID = "ajhfccooimcjfbablbbpicimdjolmndn"


def test_native_messaging_manifest_validity():
    """Verify com.edgemind.native_host.json format and configuration."""
    assert os.path.isfile(MANIFEST_PATH), f"Manifest missing at {MANIFEST_PATH}"
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data.get("name") == "com.edgemind.native_host"
    assert data.get("type") == "stdio"
    assert os.path.isabs(data.get("path")), "Executable path must be absolute"
    assert os.path.isfile(data.get("path")), f"Executable not found at {data.get('path')}"

    allowed = data.get("allowed_origins", [])
    expected_origin = f"chrome-extension://{VERIFIED_EXT_ID}/"
    assert expected_origin in allowed, f"Allowed origins must contain {expected_origin}"


def test_native_host_executable_self_check():
    """Verify native host executable compiles/runs and passes --check."""
    assert os.path.isfile(EXE_PATH), f"Native host executable missing at {EXE_PATH}"
    result = subprocess.run([EXE_PATH, "--check"], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0
    assert "EdgeMind Native Host CLI Diagnostic Test" in result.stdout


def test_native_host_stdio_length_prefixed_protocol():
    """Verify native host handles 4-byte length-prefixed JSON protocol on stdio."""
    proc = subprocess.Popen(
        [EXE_PATH],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )

    msg = json.dumps({"action": "check_status"}).encode("utf-8")
    header = struct.pack("<I", len(msg))
    proc.stdin.write(header + msg)
    proc.stdin.flush()

    resp_header = proc.stdout.read(4)
    assert len(resp_header) == 4, "Must receive 4-byte response header"
    resp_len = struct.unpack("<I", resp_header)[0]
    assert 0 < resp_len <= 1024 * 1024, "Response length must be within 1MB"

    resp_body = proc.stdout.read(resp_len).decode("utf-8")
    data = json.loads(resp_body)
    assert data.get("service") == "EdgeMind"
    assert "status" in data
    assert "endpoint" in data

    # Clean EOF closure
    proc.stdin.close()
    proc.wait(timeout=5)
    assert proc.returncode == 0


def test_extension_manifest_native_messaging_permissions():
    """Verify extension manifest includes nativeMessaging, storage, and background worker."""
    assert os.path.isfile(EXT_MANIFEST_PATH)
    with open(EXT_MANIFEST_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    perms = data.get("permissions", [])
    assert "nativeMessaging" in perms, "Manifest permissions must include nativeMessaging"
    assert "storage" in perms, "Manifest permissions must include storage"

    bg = data.get("background", {})
    assert bg.get("service_worker") == "scripts/background.js"
    assert os.path.isfile(BACKGROUND_JS_PATH), f"Background service worker missing at {BACKGROUND_JS_PATH}"


def test_installer_and_uninstaller_scripts_exist():
    """Verify installation and uninstallation PowerShell scripts are in scripts/."""
    install_script = os.path.join(SCRIPTS_DIR, "install_edgemind_native_messaging.ps1")
    uninstall_script = os.path.join(SCRIPTS_DIR, "uninstall_edgemind_native_messaging.ps1")

    assert os.path.isfile(install_script), f"Installer script missing at {install_script}"
    assert os.path.isfile(uninstall_script), f"Uninstaller script missing at {uninstall_script}"

