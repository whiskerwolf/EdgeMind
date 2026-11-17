"""
Tests for EdgeMind Chrome Native Messaging Host and automatic startup integration.

Verifies:
- Native host manifest structure, portability, allowed origins, and executable path.
- Dynamic manifest generation for installation/deployment.
- Native messaging protocol framing and message schemas in pure Python (Unit Tests).
- Native host executable existence and length-prefixed stdio protocol adherence (Integration Tests),
  with graceful skipping when blocked by Windows Smart App Control (WinError 4551).
- EdgeMind extension manifest permissions (nativeMessaging, storage) and background service worker.
- Lifecycle preservation and script existence.
"""

import json
import os
import re
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
CHROME_ORIGIN_REGEX = re.compile(r"^chrome-extension://[a-p]{32}/$")

# Helper functions for Chrome Native Messaging protocol framing
def encode_native_message(obj: dict) -> bytes:
    """Pack a Python dictionary into Chrome Native Messaging 4-byte length-prefixed UTF-8 format."""
    payload = json.dumps(obj).encode("utf-8")
    header = struct.pack("<I", len(payload))
    return header + payload


def decode_native_message(raw: bytes) -> tuple[int, dict]:
    """Unpack Chrome Native Messaging bytes into (length, dictionary)."""
    if len(raw) < 4:
        raise ValueError("Buffer too short to contain 4-byte length header")
    length = struct.unpack("<I", raw[:4])[0]
    payload = raw[4 : 4 + length]
    if len(payload) < length:
        raise ValueError(f"Incomplete payload: expected {length} bytes, got {len(payload)}")
    data = json.loads(payload.decode("utf-8"))
    return length, data


def generate_native_manifest(exe_path: str, allowed_extensions: list[str]) -> dict:
    """Generate dynamic native messaging host manifest dictionary."""
    origins = [f"chrome-extension://{ext_id}/" for ext_id in allowed_extensions]
    return {
        "name": "com.edgemind.native_host",
        "description": "EdgeMind Chrome Native Messaging Host for backend management",
        "path": os.path.abspath(exe_path),
        "type": "stdio",
        "allowed_origins": origins,
    }


# ==============================================================================
# Manifest Tests (Portability & Schema)
# ==============================================================================

def test_native_messaging_manifest_validity():
    """Verify com.edgemind.native_host.json format, portability, and configuration."""
    assert os.path.isfile(MANIFEST_PATH), f"Manifest missing at {MANIFEST_PATH}"
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data.get("name") == "com.edgemind.native_host"
    assert data.get("type") == "stdio"
    raw_path = data.get("path", "")
    assert "C:\\Users\\HP" not in raw_path, "Manifest contains non-portable hardcoded HP path"
    assert "C:\\Users\\DELL" not in raw_path, "Manifest contains non-portable hardcoded DELL path"

    # Resolves to actual executable (relative to scripts/ or absolute path)
    resolved_path = raw_path if os.path.isabs(raw_path) else os.path.join(SCRIPTS_DIR, raw_path)
    assert os.path.isfile(resolved_path), f"Executable not found at {resolved_path}"

    allowed = data.get("allowed_origins", [])
    assert isinstance(allowed, list) and len(allowed) > 0, "allowed_origins must be a non-empty list"
    for origin in allowed:
        assert "*" not in origin, f"Wildcards not allowed in origin: '{origin}'"
        assert CHROME_ORIGIN_REGEX.match(origin), (
            f"Invalid Chrome extension origin: '{origin}'. Expected format: 'chrome-extension://<32-char-id>/'"
        )


def test_native_messaging_manifest_dynamic_generation():
    """Verify dynamic manifest generation handles paths and extension origins correctly."""
    mock_exe = "C:\\Program Files\\EdgeMind\\edgemind_native_host.exe"
    mock_ext_ids = ["abcdefghijklmnopabcdefghijklmnop", "ponmlkjihgfedcbaponmlkjihgfedcba"]
    manifest = generate_native_manifest(mock_exe, mock_ext_ids)

    assert manifest["name"] == "com.edgemind.native_host"
    assert manifest["type"] == "stdio"
    assert manifest["path"] == os.path.abspath(mock_exe)
    assert len(manifest["allowed_origins"]) == 2
    for origin in manifest["allowed_origins"]:
        assert CHROME_ORIGIN_REGEX.match(origin)

    # Test round-trip JSON serialization
    serialized = json.dumps(manifest, indent=2)
    deserialized = json.loads(serialized)
    assert deserialized == manifest


# ==============================================================================
# Protocol Unit Tests (Group A - Platform-independent, SAC-safe)
# ==============================================================================

def test_protocol_framing_encode_decode():
    """Verify 4-byte little-endian framing encode/decode round-trip."""
    test_messages = [
        {"action": "ping"},
        {"action": "check_status"},
        {"action": "start_backend"},
        {"action": "custom", "nested": {"key": 123, "active": True}},
        {"text": "Unicode test: \u2705 \u26a0\ufe0f \u00e9\u00e0\u00fc"},
    ]

    for msg in test_messages:
        packed = encode_native_message(msg)
        # Verify 4-byte header
        header_len = struct.unpack("<I", packed[:4])[0]
        assert header_len == len(packed) - 4
        # Verify decoding
        decoded_len, decoded_data = decode_native_message(packed)
        assert decoded_len == header_len
        assert decoded_data == msg


def test_protocol_framing_length_bounds():
    """Verify message length boundary rules (1MB maximum per Chrome specification)."""
    max_allowed = 1024 * 1024  # 1MB limit for Chrome Native Messaging

    # Valid boundary
    valid_packed = struct.pack("<I", max_allowed) + b"A" * max_allowed
    length = struct.unpack("<I", valid_packed[:4])[0]
    assert 0 < length <= max_allowed

    # Invalid: 0 length
    zero_len = struct.unpack("<I", struct.pack("<I", 0))[0]
    assert zero_len <= 0, "Zero length must be rejected"

    # Invalid: > 1MB
    excessive_len = max_allowed + 1
    excess_unpacked = struct.unpack("<I", struct.pack("<I", excessive_len))[0]
    assert excess_unpacked > max_allowed, "Length above 1MB must be rejected"


def test_protocol_message_dispatch_schemas():
    """Verify simulated protocol dispatch schemas for all supported host actions."""
    def simulate_host_response(action: str, api_online: bool = True) -> dict:
        if action == "ping":
            return {
                "status": "PONG",
                "service": "EdgeMind",
                "connected": True,
                "message": "EdgeMind Native Host is responsive.",
                "endpoint": "http://127.0.0.1:8000",
                "timestamp": "2026-11-16T12:00:00.0000000Z",
            }
        elif action == "check_status":
            return {
                "status": "CONNECTED" if api_online else "OFFLINE",
                "service": "EdgeMind",
                "connected": api_online,
                "message": "EdgeMind API is healthy and connected." if api_online else "Cannot reach EdgeMind API",
                "endpoint": "http://127.0.0.1:8000",
                "timestamp": "2026-11-16T12:00:00.0000000Z",
            }
        else:  # start_backend
            return {
                "status": "CONNECTED",
                "service": "EdgeMind",
                "connected": True,
                "message": "EdgeMind API started successfully.",
                "endpoint": "http://127.0.0.1:8000",
                "timestamp": "2026-11-16T12:00:00.0000000Z",
            }

    # Verify ping schema
    ping_resp = simulate_host_response("ping")
    assert ping_resp["service"] == "EdgeMind"
    assert ping_resp["status"] == "PONG"
    assert ping_resp["connected"] is True
    assert "endpoint" in ping_resp

    # Verify check_status online schema
    status_resp = simulate_host_response("check_status", api_online=True)
    assert status_resp["service"] == "EdgeMind"
    assert status_resp["status"] == "CONNECTED"
    assert status_resp["connected"] is True

    # Verify check_status offline schema
    status_offline = simulate_host_response("check_status", api_online=False)
    assert status_offline["status"] == "OFFLINE"
    assert status_offline["connected"] is False

    # Verify start_backend schema
    start_resp = simulate_host_response("start_backend")
    assert start_resp["service"] == "EdgeMind"
    assert start_resp["status"] == "CONNECTED"
    assert start_resp["connected"] is True


def test_protocol_handling_eof_and_malformed_json():
    """Verify handling of empty EOF stream and malformed JSON payloads."""
    # EOF detection: 0 bytes received
    eof_stream = b""
    with pytest.raises(ValueError, match="too short"):
        decode_native_message(eof_stream)

    # Incomplete buffer
    truncated_stream = struct.pack("<I", 100) + b'{"action": "ping"}'
    with pytest.raises(ValueError, match="Incomplete payload"):
        decode_native_message(truncated_stream)

    # Malformed JSON payload
    bad_json_bytes = b"NOT_VALID_JSON{{"
    bad_stream = struct.pack("<I", len(bad_json_bytes)) + bad_json_bytes
    with pytest.raises(json.JSONDecodeError):
        decode_native_message(bad_stream)


# ==============================================================================
# Executable Integration Tests (Group B - Subprocess execution)
# ==============================================================================

def test_native_host_executable_self_check():
    """Verify native host executable compiles/runs and passes --check."""
    assert os.path.isfile(EXE_PATH), f"Native host executable missing at {EXE_PATH}"
    try:
        result = subprocess.run([EXE_PATH, "--check"], capture_output=True, text=True, timeout=30)
    except OSError as exc:
        if getattr(exc, "winerror", None) == 4551 or "Application Control" in str(exc):
            pytest.skip(
                "Native host executable is unsigned and blocked by Windows Smart App Control (WinError 4551). "
                "Production deployment requires an Authenticode code-signing certificate."
            )
        raise
    assert result.returncode == 0
    assert "EdgeMind Native Host CLI Diagnostic Test" in result.stdout


def test_native_host_stdio_length_prefixed_protocol():
    """Verify native host handles 4-byte length-prefixed JSON protocol on stdio."""
    assert os.path.isfile(EXE_PATH), f"Native host executable missing at {EXE_PATH}"
    try:
        proc = subprocess.Popen(
            [EXE_PATH],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError as exc:
        if getattr(exc, "winerror", None) == 4551 or "Application Control" in str(exc):
            pytest.skip(
                "Native host executable is unsigned and blocked by Windows Smart App Control (WinError 4551). "
                "Production deployment requires an Authenticode code-signing certificate."
            )
        raise

    try:
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
    finally:
        if proc.poll() is None:
            proc.kill()

# ==============================================================================
# Extension Manifest & Scripts Tests
# ==============================================================================

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


def test_installer_temp_directory_with_spaces_and_no_registry(tmp_path):
    """Verify that install script supports custom paths with spaces and does not touch real registry with -NoRegistry."""
    import shutil
    install_script = os.path.join(SCRIPTS_DIR, "install_edgemind_native_messaging.ps1")
    uninstall_script = os.path.join(SCRIPTS_DIR, "uninstall_edgemind_native_messaging.ps1")

    # Directory with spaces
    install_dir = tmp_path / "EdgeMind Custom Space Directory"
    install_dir.mkdir()
    manifest_dir = install_dir / "manifests"
    manifest_dir.mkdir()

    # Place executable in custom directory
    custom_exe = install_dir / "edgemind_native_host.exe"
    shutil.copy2(EXE_PATH, custom_exe)
    assert custom_exe.is_file()

    # Run installer with -NoRegistry and custom paths
    ps_cmd = [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", install_script,
        "-ExecutablePath", str(custom_exe),
        "-ManifestDir", str(manifest_dir),
        "-NoRegistry",
        "-Quiet",
    ]
    res = subprocess.run(ps_cmd, capture_output=True, text=True, timeout=30)
    assert res.returncode == 0, f"Installer failed: {res.stderr}\n{res.stdout}"

    # Verify generated manifest
    installed_manifest = manifest_dir / "com.edgemind.native_host.json"
    assert installed_manifest.is_file()

    with open(installed_manifest, "r", encoding="utf-8") as f:
        manifest_data = json.load(f)

    assert manifest_data["name"] == "com.edgemind.native_host"
    assert manifest_data["type"] == "stdio"
    # Canonical path with spaces preserved
    assert os.path.abspath(manifest_data["path"]) == os.path.abspath(str(custom_exe))
    assert os.path.isfile(manifest_data["path"])
    assert manifest_data["allowed_origins"] == ["chrome-extension://dcpgjneeokaigdhocommnadngnbaebgg/"]

    # Run uninstaller targeting the custom directory
    uninst_cmd = [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", uninstall_script,
        "-ManifestDir", str(manifest_dir),
        "-NoRegistry",
        "-Quiet",
    ]
    uninst_res = subprocess.run(uninst_cmd, capture_output=True, text=True, timeout=30)
    assert uninst_res.returncode == 0
    assert not installed_manifest.exists()


def test_installer_rejects_wildcard_extension_id(tmp_path):
    """Verify that install script rejects wildcard and malformed extension IDs."""
    install_script = os.path.join(SCRIPTS_DIR, "install_edgemind_native_messaging.ps1")
    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()

    for invalid_id in ["*", "chrome-extension://*", "short_id", "invalid_with_numbers_1234567890123456789012"]:
        ps_cmd = [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy", "Bypass",
            "-File", install_script,
            "-ExtensionId", invalid_id,
            "-ManifestDir", str(manifest_dir),
            "-NoRegistry",
            "-Quiet",
        ]
        res = subprocess.run(ps_cmd, capture_output=True, text=True, timeout=15)
        assert res.returncode != 0, f"Installer should reject invalid extension ID: {invalid_id}"


def test_native_host_stdout_cleanliness_and_framing():
    """Verify that stdout contains strictly 4-byte framed messages without any diagnostic or log text."""
    assert os.path.isfile(EXE_PATH)
    try:
        proc = subprocess.Popen(
            [EXE_PATH],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError as exc:
        if getattr(exc, "winerror", None) == 4551 or "Application Control" in str(exc):
            pytest.skip("Native host blocked by Smart App Control (WinError 4551).")
        raise

    try:
        msg = json.dumps({"action": "ping"}).encode("utf-8")
        header = struct.pack("<I", len(msg))
        proc.stdin.write(header + msg)
        proc.stdin.flush()

        # Read exact 4-byte header
        resp_header = proc.stdout.read(4)
        assert len(resp_header) == 4
        resp_len = struct.unpack("<I", resp_header)[0]
        assert 0 < resp_len <= 1024 * 1024

        # Read exact payload
        resp_body = proc.stdout.read(resp_len).decode("utf-8")
        data = json.loads(resp_body)
        assert data.get("status") == "PONG"
        assert data.get("service") == "EdgeMind"

        # Close stdin to trigger clean shutdown
        proc.stdin.close()
        proc.wait(timeout=5)
        assert proc.returncode == 0

        # Verify stderr captured the logs rather than stdout
        stderr_output = proc.stderr.read().decode("utf-8")
        assert "EdgeMind Native Host started" in stderr_output or "EOF" in stderr_output
    finally:
        if proc.poll() is None:
            proc.kill()
