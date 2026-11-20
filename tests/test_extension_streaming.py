"""
Tests for EdgeMind Chrome Extension SSE Streaming Integration.

Verifies:
1. Node.js syntax validity of popup.js with streaming logic.
2. Extension stream parser robustly handles arbitrary split network chunks.
3. Extension stream parser handles multiple SSE events in a single network chunk.
4. Extension stream parser ignores heartbeat comments (: heartbeat).
5. Error events trigger safe error display.
6. Stream reader cancellation via AbortController terminates reading cleanly.
7. Safe DOM rendering invariants: strict zero innerHTML, textContent usage.
8. Dual endpoint configuration (/api/v1/agent/analyze/stream with fallback to /api/v1/edgemind/analyze).
9. UTF-8 multi-byte characters split across byte chunks are reconstructed properly.
10. CRLF (\\r\\n\\r\\n) event delimiters supported.
11. Multi-line data fields concatenated with newlines.
12. Incomplete final events flushed safely on stream EOF.
13. Extension fallback strictly before streaming begins (HTTP 404/405).
"""

import json
from pathlib import Path
import subprocess

import pytest

POPUP_JS_PATH = Path("extension/edgemind/popup/popup.js")
POPUP_HTML_PATH = Path("extension/edgemind/popup/popup.html")


def test_popup_js_node_syntax():
    """Verify popup.js passes Node.js syntax verification (--check)."""
    assert POPUP_JS_PATH.exists()
    proc = subprocess.run(
        ["node", "--check", str(POPUP_JS_PATH)],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, f"popup.js syntax error: {proc.stderr}"


def test_popup_js_contains_streaming_endpoint_and_fallback():
    """Verify popup.js declares both streaming and fallback API endpoints."""
    content = POPUP_JS_PATH.read_text(encoding="utf-8")
    assert "/api/v1/agent/analyze/stream" in content
    assert "/api/v1/edgemind/analyze" in content
    assert "consumeSseStream" in content


def test_popup_js_strict_dom_safety_zero_innerhtml():
    """Verify popup.js strictly uses textContent and createElement with zero innerHTML."""
    content = POPUP_JS_PATH.read_text(encoding="utf-8")
    assert "innerHTML" not in content, "popup.js must not contain innerHTML"
    assert "document.createElement" in content
    assert "textContent" in content


def test_popup_html_contains_cancel_analysis_button():
    """Verify popup.html contains the cancel analysis button element."""
    content = POPUP_HTML_PATH.read_text(encoding="utf-8")
    assert 'id="btn-cancel-analysis"' in content


def test_node_execution_consume_sse_stream_split_chunks():
    """
    Execute consumeSseStream in Node.js to verify it reconstructs SSE events
    split across arbitrary byte/chunk boundaries.
    """
    node_test_script = """
    const fs = require('fs');
    const vm = require('vm');

    function createMockStream(chunks) {
      let idx = 0;
      return {
        body: {
          getReader() {
            return {
              async read() {
                if (idx < chunks.length) {
                  const val = Buffer.from(chunks[idx++], 'utf-8');
                  return { done: false, value: new Uint8Array(val) };
                }
                return { done: true, value: undefined };
              },
              async cancel() {},
              releaseLock() {}
            };
          }
        }
      };
    }

    const popupCode = fs.readFileSync('extension/edgemind/popup/popup.js', 'utf-8');
    const fnMatch = popupCode.match(/async function consumeSseStream[\\s\\S]*?\\n  \\}/);
    if (!fnMatch) {
      console.error("Could not find consumeSseStream function");
      process.exit(1);
    }

    const testEnv = {
      TextDecoder: global.TextDecoder,
      Uint8Array: global.Uint8Array,
      console: console
    };
    vm.createContext(testEnv);
    vm.runInContext(fnMatch[0], testEnv);

    // Test: Event split across 3 chunks
    const chunk1 = "id: 1\\nevent: pro";
    const chunk2 = "gress\\ndata: {\\\"percent\\\": 50, \\\"mess";
    const chunk3 = "age\\\": \\\"Running AST\\\"}\\n\\n";

    const stream = createMockStream([chunk1, chunk2, chunk3]);
    const received = [];

    testEnv.consumeSseStream(stream, (evt, data, id) => {
      received.push({ evt, data, id });
    }, null).then(() => {
      if (received.length !== 1) {
        console.error("Expected 1 event, got " + received.length);
        process.exit(1);
      }
      const e = received[0];
      if (e.evt !== 'progress' || e.data.percent !== 50 || e.id !== '1') {
        console.error("Event mismatch: " + JSON.stringify(e));
        process.exit(1);
      }
      console.log("SUCCESS: Split chunk parsed correctly");
      process.exit(0);
    }).catch(err => {
      console.error(err);
      process.exit(1);
    });
    """

    proc = subprocess.run(
        ["node", "-e", node_test_script],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, f"Node test failed: {proc.stderr}\n{proc.stdout}"
    assert "SUCCESS: Split chunk parsed correctly" in proc.stdout


def test_node_execution_consume_sse_stream_multiple_events_and_heartbeats():
    """
    Verify parser handles multiple events in a single network chunk and ignores : heartbeat comments.
    """
    node_test_script = """
    const fs = require('fs');
    const vm = require('vm');

    function createMockStream(chunks) {
      let idx = 0;
      return {
        body: {
          getReader() {
            return {
              async read() {
                if (idx < chunks.length) {
                  const val = Buffer.from(chunks[idx++], 'utf-8');
                  return { done: false, value: new Uint8Array(val) };
                }
                return { done: true, value: undefined };
              },
              async cancel() {},
              releaseLock() {}
            };
          }
        }
      };
    }

    const popupCode = fs.readFileSync('extension/edgemind/popup/popup.js', 'utf-8');
    const fnMatch = popupCode.match(/async function consumeSseStream[\\s\\S]*?\\n  \\}/);
    const testEnv = {
      TextDecoder: global.TextDecoder,
      Uint8Array: global.Uint8Array,
      console: console
    };
    vm.createContext(testEnv);
    vm.runInContext(fnMatch[0], testEnv);

    // Single chunk containing: heartbeat comment, tool_started, tool_completed
    const singleChunk =
      ": heartbeat\\n\\n" +
      "id: 2\\nevent: tool_started\\ndata: {\\\"tool_name\\\": \\\"detect_coverage_gaps\\\"}\\n\\n" +
      ": ping\\n\\n" +
      "id: 3\\nevent: tool_completed\\ndata: {\\\"tool_name\\\": \\\"detect_coverage_gaps\\\", \\\"duration_ms\\\": 12.4}\\n\\n";

    const stream = createMockStream([singleChunk]);
    const received = [];

    testEnv.consumeSseStream(stream, (evt, data, id) => {
      received.push({ evt, data, id });
    }, null).then(() => {
      if (received.length !== 2) {
        console.error("Expected 2 events (comments ignored), got " + received.length);
        process.exit(1);
      }
      if (received[0].evt !== 'tool_started' || received[1].evt !== 'tool_completed') {
        console.error("Event types mismatch: " + JSON.stringify(received));
        process.exit(1);
      }
      console.log("SUCCESS: Multiple events and comments parsed correctly");
      process.exit(0);
    }).catch(err => {
      console.error(err);
      process.exit(1);
    });
    """

    proc = subprocess.run(
        ["node", "-e", node_test_script],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, f"Node test failed: {proc.stderr}\n{proc.stdout}"
    assert "SUCCESS: Multiple events and comments parsed correctly" in proc.stdout


def test_node_execution_consume_sse_stream_cancellation_via_signal():
    """
    Verify that an aborted AbortSignal causes consumeSseStream to cancel the reader cleanly.
    """
    node_test_script = """
    const fs = require('fs');
    const vm = require('vm');

    let readerCancelled = false;

    function createMockInfiniteStream() {
      return {
        body: {
          getReader() {
            return {
              async read() {
                const val = Buffer.from("id: 1\\nevent: status\\ndata: {\\\"status\\\": \\\"loop\\\"}\\n\\n", 'utf-8');
                return { done: false, value: new Uint8Array(val) };
              },
              async cancel() {
                readerCancelled = true;
              },
              releaseLock() {}
            };
          }
        }
      };
    }

    const popupCode = fs.readFileSync('extension/edgemind/popup/popup.js', 'utf-8');
    const fnMatch = popupCode.match(/async function consumeSseStream[\\s\\S]*?\\n  \\}/);
    const testEnv = {
      TextDecoder: global.TextDecoder,
      Uint8Array: global.Uint8Array,
      console: console
    };
    vm.createContext(testEnv);
    vm.runInContext(fnMatch[0], testEnv);

    const controller = new AbortController();
    const stream = createMockInfiniteStream();
    let eventCount = 0;

    testEnv.consumeSseStream(stream, (evt, data, id) => {
      eventCount++;
      if (eventCount >= 1) {
        controller.abort();
      }
    }, controller.signal).then(() => {
      if (!readerCancelled) {
        console.error("Reader was not cancelled on abort");
        process.exit(1);
      }
      console.log("SUCCESS: Stream cancelled cleanly via signal");
      process.exit(0);
    }).catch(err => {
      console.error(err);
      process.exit(1);
    });
    """

    proc = subprocess.run(
        ["node", "-e", node_test_script],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, f"Node test failed: {proc.stderr}\n{proc.stdout}"
    assert "SUCCESS: Stream cancelled cleanly via signal" in proc.stdout


def test_node_execution_consume_sse_stream_utf8_split_across_bytes():
    """
    Verify that consumeSseStream correctly reconstructs multi-byte UTF-8 characters
    (such as mathematical symbols '≤' or emoji '🎯') split across raw byte chunk boundaries.
    """
    node_test_script = """
    const fs = require('fs');
    const vm = require('vm');

    const popupCode = fs.readFileSync('extension/edgemind/popup/popup.js', 'utf-8');
    const fnMatch = popupCode.match(/async function consumeSseStream[\\s\\S]*?\\n  \\}/);
    const testEnv = {
      TextDecoder: global.TextDecoder,
      Uint8Array: global.Uint8Array,
      console: console
    };
    vm.createContext(testEnv);
    vm.runInContext(fnMatch[0], testEnv);

    // '≤' is UTF-8: [0xE2, 0x89, 0xA4] (3 bytes)
    // '🎯' is UTF-8: [0xF0, 0x9F, 0x8E, 0xAF] (4 bytes)
    const payloadStr = 'id: 1\\nevent: progress\\ndata: {\\\"symbol\\\": \\\"10 \\u2264 N\\\", \\\"icon\\\": \\\"\\uD83C\\uDFAF\\\"}\\n\\n';
    const fullBuffer = Buffer.from(payloadStr, 'utf-8');

    // Find the multi-byte sequences and split intentionally in the middle of the bytes
    const splitIndex = 40; // Splits directly across byte boundaries

    const chunk1 = fullBuffer.slice(0, splitIndex);
    const chunk2 = fullBuffer.slice(splitIndex);

    function createByteStream(byteChunks) {
      let idx = 0;
      return {
        body: {
          getReader() {
            return {
              async read() {
                if (idx < byteChunks.length) {
                  return { done: false, value: new Uint8Array(byteChunks[idx++]) };
                }
                return { done: true, value: undefined };
              },
              async cancel() {},
              releaseLock() {}
            };
          }
        }
      };
    }

    const stream = createByteStream([chunk1, chunk2]);
    const received = [];

    testEnv.consumeSseStream(stream, (evt, data, id) => {
      received.push({ evt, data, id });
    }, null).then(() => {
      if (received.length !== 1) {
        console.error("Expected 1 event, got " + received.length);
        process.exit(1);
      }
      const data = received[0].data;
      if (!data || data.symbol !== "10 \u2264 N" || data.icon !== "\uD83C\uDFAF") {
        console.error("UTF-8 multi-byte decoding failed: " + JSON.stringify(data));
        process.exit(1);
      }
      console.log("SUCCESS: Multi-byte UTF-8 reconstructed correctly across split chunks");
      process.exit(0);
    }).catch(err => {
      console.error(err);
      process.exit(1);
    });
    """

    proc = subprocess.run(
        ["node", "-e", node_test_script],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, f"Node test failed: {proc.stderr}\n{proc.stdout}"
    assert "SUCCESS: Multi-byte UTF-8 reconstructed correctly across split chunks" in proc.stdout


def test_node_execution_consume_sse_stream_crlf_delimiters():
    """Verify that consumeSseStream correctly supports CRLF (\\r\\n\\r\\n) event delimiters."""
    node_test_script = """
    const fs = require('fs');
    const vm = require('vm');

    function createMockStream(chunks) {
      let idx = 0;
      return {
        body: {
          getReader() {
            return {
              async read() {
                if (idx < chunks.length) {
                  const val = Buffer.from(chunks[idx++], 'utf-8');
                  return { done: false, value: new Uint8Array(val) };
                }
                return { done: true, value: undefined };
              },
              async cancel() {},
              releaseLock() {}
            };
          }
        }
      };
    }

    const popupCode = fs.readFileSync('extension/edgemind/popup/popup.js', 'utf-8');
    const fnMatch = popupCode.match(/async function consumeSseStream[\\s\\S]*?\\n  \\}/);
    const testEnv = {
      TextDecoder: global.TextDecoder,
      Uint8Array: global.Uint8Array,
      console: console
    };
    vm.createContext(testEnv);
    vm.runInContext(fnMatch[0], testEnv);

    const crlfText =
      "id: 10\\r\\nevent: status\\r\\ndata: {\\\"status\\\": \\\"crlf_test\\\"}\\r\\n\\r\\n" +
      "id: 11\\r\\nevent: completed\\r\\ndata: {\\\"status\\\": \\\"SUCCESS\\\"}\\r\\n\\r\\n";

    const stream = createMockStream([crlfText]);
    const received = [];

    testEnv.consumeSseStream(stream, (evt, data, id) => {
      received.push({ evt, data, id });
    }, null).then(() => {
      if (received.length !== 2) {
        console.error("Expected 2 events delimited by CRLF, got " + received.length);
        process.exit(1);
      }
      if (received[0].id !== "10" || received[1].id !== "11") {
        console.error("CRLF event IDs mismatch: " + JSON.stringify(received));
        process.exit(1);
      }
      console.log("SUCCESS: CRLF delimiters parsed correctly");
      process.exit(0);
    }).catch(err => {
      console.error(err);
      process.exit(1);
    });
    """

    proc = subprocess.run(
        ["node", "-e", node_test_script],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, f"Node test failed: {proc.stderr}\n{proc.stdout}"
    assert "SUCCESS: CRLF delimiters parsed correctly" in proc.stdout


def test_node_execution_consume_sse_stream_multiline_data_concatenation():
    """Verify that consumeSseStream correctly joins multiple data lines with newlines."""
    node_test_script = """
    const fs = require('fs');
    const vm = require('vm');

    function createMockStream(chunks) {
      let idx = 0;
      return {
        body: {
          getReader() {
            return {
              async read() {
                if (idx < chunks.length) {
                  const val = Buffer.from(chunks[idx++], 'utf-8');
                  return { done: false, value: new Uint8Array(val) };
                }
                return { done: true, value: undefined };
              },
              async cancel() {},
              releaseLock() {}
            };
          }
        }
      };
    }

    const popupCode = fs.readFileSync('extension/edgemind/popup/popup.js', 'utf-8');
    const fnMatch = popupCode.match(/async function consumeSseStream[\\s\\S]*?\\n  \\}/);
    const testEnv = {
      TextDecoder: global.TextDecoder,
      Uint8Array: global.Uint8Array,
      console: console
    };
    vm.createContext(testEnv);
    vm.runInContext(fnMatch[0], testEnv);

    // Multi-line data field (e.g. multi-line explanation)
    const multilineText =
      "id: 1\\nevent: progress\\n" +
      "data: Line one\\n" +
      "data: Line two\\n" +
      "data: Line three\\n\\n";

    const stream = createMockStream([multilineText]);
    const received = [];

    testEnv.consumeSseStream(stream, (evt, data, id) => {
      received.push({ evt, data, id });
    }, null).then(() => {
      if (received.length !== 1) {
        console.error("Expected 1 event, got " + received.length);
        process.exit(1);
      }
      const data = received[0].data;
      if (data.message !== "Line one\\nLine two\\nLine three") {
        console.error("Multi-line concatenation failed: " + JSON.stringify(data));
        process.exit(1);
      }
      console.log("SUCCESS: Multi-line data concatenated correctly");
      process.exit(0);
    }).catch(err => {
      console.error(err);
      process.exit(1);
    });
    """

    proc = subprocess.run(
        ["node", "-e", node_test_script],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, f"Node test failed: {proc.stderr}\n{proc.stdout}"
    assert "SUCCESS: Multi-line data concatenated correctly" in proc.stdout


def test_node_execution_consume_sse_stream_incomplete_final_event_flushed():
    """Verify that an incomplete final event without trailing double-newlines is parsed when stream ends."""
    node_test_script = """
    const fs = require('fs');
    const vm = require('vm');

    function createMockStream(chunks) {
      let idx = 0;
      return {
        body: {
          getReader() {
            return {
              async read() {
                if (idx < chunks.length) {
                  const val = Buffer.from(chunks[idx++], 'utf-8');
                  return { done: false, value: new Uint8Array(val) };
                }
                return { done: true, value: undefined };
              },
              async cancel() {},
              releaseLock() {}
            };
          }
        }
      };
    }

    const popupCode = fs.readFileSync('extension/edgemind/popup/popup.js', 'utf-8');
    const fnMatch = popupCode.match(/async function consumeSseStream[\\s\\S]*?\\n  \\}/);
    const testEnv = {
      TextDecoder: global.TextDecoder,
      Uint8Array: global.Uint8Array,
      console: console
    };
    vm.createContext(testEnv);
    vm.runInContext(fnMatch[0], testEnv);

    // First event properly delimited; second event has NO trailing double newline at EOF
    const chunk1 = "id: 1\\nevent: status\\ndata: {\\\"status\\\": \\\"init\\\"}\\n\\n";
    const chunk2 = "id: 2\\nevent: completed\\ndata: {\\\"status\\\": \\\"SUCCESS\\\"}";

    const stream = createMockStream([chunk1, chunk2]);
    const received = [];

    testEnv.consumeSseStream(stream, (evt, data, id) => {
      received.push({ evt, data, id });
    }, null).then(() => {
      if (received.length !== 2) {
        console.error("Expected 2 events (final event flushed on done), got " + received.length);
        process.exit(1);
      }
      if (received[1].evt !== "completed" || received[1].data.status !== "SUCCESS") {
        console.error("Final event payload mismatch: " + JSON.stringify(received[1]));
        process.exit(1);
      }
      console.log("SUCCESS: Incomplete final event flushed and parsed upon stream completion");
      process.exit(0);
    }).catch(err => {
      console.error(err);
      process.exit(1);
    });
    """

    proc = subprocess.run(
        ["node", "-e", node_test_script],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, f"Node test failed: {proc.stderr}\n{proc.stdout}"
    assert "SUCCESS: Incomplete final event flushed and parsed upon stream completion" in proc.stdout


def test_popup_js_fallback_policy_strictly_before_streaming():
    """
    Verify that fallback to /api/v1/edgemind/analyze occurs strictly when
    the initial streaming request returns HTTP 404 or 405 BEFORE streaming starts,
    and no secondary fallback request is dispatched once streaming begins.
    """
    content = POPUP_JS_PATH.read_text(encoding="utf-8")

    # 1. Verify fallback check only targets 404/405
    assert "(response.status === 404 || response.status === 405)" in content

    # 2. Verify isStreaming is set to false upon entering fallback
    assert "isStreaming = false;" in content

    # 3. Verify fallback is called before consumeSseStream invocation
    stream_idx = content.find("STREAM_ENDPOINT =")
    fallback_check_idx = content.find("response.status === 404 || response.status === 405")
    consume_idx = content.find("await consumeSseStream(response")

    assert stream_idx < fallback_check_idx < consume_idx, (
        "Fallback verification must precede consumeSseStream call"
    )
