import { describe, it } from 'node:test';
import * as assert from 'node:assert';
import { DiagnosisClient, DiagnosisClientError } from '../api/diagnosisClient';
import { DiagnoseFindingRequest, DiagnosisStreamEvent } from '../types/diagnosis';

describe('EdgeMind DiagnosisClient Streaming Integration Tests', () => {
  const sampleRequest: DiagnoseFindingRequest = {
    finding: {
      finding_id: 'EM-DIV0',
      type: 'division_by_zero',
      severity: 'error',
      message: 'Divide by zero on line 3',
      line: 3,
      static_why: 'Denom can be zero',
      static_fix: 'Guard with if',
    },
    code_context: 'def div(a, b):\n    return a / b\n',
    context_start_line: 1,
    context_end_line: 3,
    filename: 'math_ops.py',
    language: 'python',
  };

  function createMockResponse(
    chunks: string[],
    status = 200,
    headers: Record<string, string> = { 'content-type': 'text/event-stream' },
    onCancel?: () => void
  ): Response {
    let idx = 0;
    const stream = new ReadableStream({
      async pull(controller) {
        if (idx < chunks.length) {
          const text = chunks[idx++];
          controller.enqueue(new TextEncoder().encode(text));
        } else {
          controller.close();
        }
      },
      cancel() {
        onCancel?.();
      },
    });

    return new Response(stream, {
      status,
      headers: new Headers(headers),
    });
  }

  it('A-F. should stream diagnosis events in order with started, chunks, and completed', async () => {
    const sseWire = [
      'id: 1\nevent: diagnosis_started\ndata: {"session_id":"s_100","finding_id":"EM-DIV0","finding_type":"division_by_zero","line":3,"sequence_id":1,"timestamp":"2026-11-24T12:00:00Z"}\n\n',
      'id: 2\nevent: response_chunk\ndata: {"session_id":"s_100","finding_id":"EM-DIV0","chunk":"### Root Cause\\n","sequence_id":2,"timestamp":"2026-11-24T12:00:00.1Z"}\n\n',
      'id: 3\nevent: response_chunk\ndata: {"session_id":"s_100","finding_id":"EM-DIV0","chunk":"Zero division occurs.\\n","sequence_id":3,"timestamp":"2026-11-24T12:00:00.2Z"}\n\n',
      'id: 4\nevent: completed\ndata: {"session_id":"s_100","finding_id":"EM-DIV0","status":"completed","duration_ms":120.5,"finish_reason":"stop","sequence_id":4,"timestamp":"2026-11-24T12:00:00.3Z"}\n\n',
    ];

    const mockFetch = async () => createMockResponse(sseWire);
    const client = new DiagnosisClient({ fetchFn: mockFetch as unknown as typeof fetch });

    const received: DiagnosisStreamEvent[] = [];
    for await (const evt of client.streamDiagnosis(sampleRequest)) {
      received.push(evt);
    }

    assert.strictEqual(received.length, 4);

    // Event order
    assert.strictEqual(received[0].event, 'diagnosis_started');
    assert.strictEqual(received[1].event, 'response_chunk');
    assert.strictEqual(received[2].event, 'response_chunk');
    assert.strictEqual(received[3].event, 'completed');

    // DiagnosisStarted verification
    if (received[0].event === 'diagnosis_started') {
      assert.strictEqual(received[0].finding_id, 'EM-DIV0');
      assert.strictEqual(received[0].line, 3);
      assert.strictEqual(received[0].sequence_id, 1);
    }

    // Response chunk verification
    if (received[1].event === 'response_chunk' && received[2].event === 'response_chunk') {
      assert.strictEqual(received[1].chunk, '### Root Cause\n');
      assert.strictEqual(received[2].chunk, 'Zero division occurs.\n');
    }

    // Completed verification
    if (received[3].event === 'completed') {
      assert.strictEqual(received[3].status, 'completed');
      assert.strictEqual(received[3].duration_ms, 120.5);
    }
  });

  it('G-H. should verify sequential IDs and finding/session correlation', async () => {
    const sseWire = [
      'id: 1\nevent: diagnosis_started\ndata: {"session_id":"sess_corr","finding_id":"EM-DIV0","sequence_id":1}\n\n',
      'id: 2\nevent: response_chunk\ndata: {"session_id":"sess_corr","finding_id":"EM-DIV0","chunk":"text","sequence_id":2}\n\n',
      'id: 3\nevent: completed\ndata: {"session_id":"sess_corr","finding_id":"EM-DIV0","status":"completed","duration_ms":50,"sequence_id":3}\n\n',
    ];

    const client = new DiagnosisClient({
      fetchFn: (async () => createMockResponse(sseWire)) as unknown as typeof fetch,
    });

    const received: DiagnosisStreamEvent[] = [];
    for await (const evt of client.streamDiagnosis(sampleRequest)) {
      received.push(evt);
    }

    assert.strictEqual(received.length, 3);
    for (let i = 0; i < received.length; i++) {
      assert.strictEqual(received[i].session_id, 'sess_corr');
      assert.strictEqual(received[i].finding_id, 'EM-DIV0');
      assert.strictEqual(received[i].sequence_id, i + 1);
    }
  });

  it('I. should reject HTTP 400 Bad Request with DiagnosisClientError', async () => {
    const mockFetch = async () =>
      new Response(JSON.stringify({ detail: 'Invalid parameters' }), {
        status: 400,
        headers: { 'content-type': 'application/json' },
      });

    const client = new DiagnosisClient({ fetchFn: mockFetch as unknown as typeof fetch });

    await assert.rejects(
      async () => {
        // eslint-disable-next-line @typescript-eslint/no-unused-vars
        for await (const _ of client.streamDiagnosis(sampleRequest)) {
          // should throw
        }
      },
      (err: unknown) => {
        assert.ok(err instanceof DiagnosisClientError);
        assert.strictEqual(err.statusCode, 400);
        assert.ok(err.message.includes('Invalid parameters'));
        return true;
      }
    );
  });

  it('J. should reject HTTP 401 Unauthorized with isUnauthorized=true', async () => {
    const mockFetch = async () =>
      new Response(JSON.stringify({ detail: 'Invalid or expired access token' }), {
        status: 401,
        headers: { 'content-type': 'application/json' },
      });

    const client = new DiagnosisClient({ fetchFn: mockFetch as unknown as typeof fetch });

    await assert.rejects(
      async () => {
        for await (const _ of client.streamDiagnosis(sampleRequest)) {}
      },
      (err: unknown) => {
        assert.ok(err instanceof DiagnosisClientError);
        assert.strictEqual(err.statusCode, 401);
        assert.strictEqual(err.isUnauthorized, true);
        return true;
      }
    );
  });

  it('K. should reject HTTP 422 Unprocessable Entity with validation details', async () => {
    const mockFetch = async () =>
      new Response(JSON.stringify({ detail: 'Finding line 5 is outside context range' }), {
        status: 422,
        headers: { 'content-type': 'application/json' },
      });

    const client = new DiagnosisClient({ fetchFn: mockFetch as unknown as typeof fetch });

    await assert.rejects(
      async () => {
        for await (const _ of client.streamDiagnosis(sampleRequest)) {}
      },
      (err: unknown) => {
        assert.ok(err instanceof DiagnosisClientError);
        assert.strictEqual(err.statusCode, 422);
        assert.ok(err.message.includes('outside context range'));
        return true;
      }
    );
  });

  it('L. should reject HTTP 429 Rate Limit with isRateLimit=true', async () => {
    const mockFetch = async () =>
      new Response(JSON.stringify({ detail: 'Rate limit exceeded' }), {
        status: 429,
        headers: { 'content-type': 'application/json' },
      });

    const client = new DiagnosisClient({ fetchFn: mockFetch as unknown as typeof fetch });

    await assert.rejects(
      async () => {
        for await (const _ of client.streamDiagnosis(sampleRequest)) {}
      },
      (err: unknown) => {
        assert.ok(err instanceof DiagnosisClientError);
        assert.strictEqual(err.statusCode, 429);
        assert.strictEqual(err.isRateLimit, true);
        return true;
      }
    );
  });

  it('M. should reject HTTP 500 Internal Server Error', async () => {
    const mockFetch = async () =>
      new Response(JSON.stringify({ detail: 'Internal failure' }), {
        status: 500,
        headers: { 'content-type': 'application/json' },
      });

    const client = new DiagnosisClient({ fetchFn: mockFetch as unknown as typeof fetch });

    await assert.rejects(
      async () => {
        for await (const _ of client.streamDiagnosis(sampleRequest)) {}
      },
      (err: unknown) => {
        assert.ok(err instanceof DiagnosisClientError);
        assert.strictEqual(err.statusCode, 500);
        return true;
      }
    );
  });

  it('N. should reject unexpected Content-Type', async () => {
    const mockFetch = async () =>
      new Response('{"msg":"ok"}', {
        status: 200,
        headers: { 'content-type': 'application/json' },
      });

    const client = new DiagnosisClient({ fetchFn: mockFetch as unknown as typeof fetch });

    await assert.rejects(
      async () => {
        for await (const _ of client.streamDiagnosis(sampleRequest)) {}
      },
      (err: unknown) => {
        assert.ok(err instanceof DiagnosisClientError);
        assert.ok(err.message.includes("Expected 'text/event-stream'"));
        return true;
      }
    );
  });

  it('O. should reject empty response body', async () => {
    const mockFetch = async () =>
      new Response(null, {
        status: 200,
        headers: { 'content-type': 'text/event-stream' },
      });

    const client = new DiagnosisClient({ fetchFn: mockFetch as unknown as typeof fetch });

    await assert.rejects(
      async () => {
        for await (const _ of client.streamDiagnosis(sampleRequest)) {}
      },
      (err: unknown) => {
        assert.ok(err instanceof DiagnosisClientError);
        assert.ok(err.message.includes('empty'));
        return true;
      }
    );
  });

  it('P. should reject on network failure (fetch throws)', async () => {
    const mockFetch = async () => {
      throw new Error('ECONNREFUSED 127.0.0.1:8000');
    };

    const client = new DiagnosisClient({ fetchFn: mockFetch as unknown as typeof fetch });

    await assert.rejects(
      async () => {
        for await (const _ of client.streamDiagnosis(sampleRequest)) {}
      },
      (err: unknown) => {
        assert.ok(err instanceof DiagnosisClientError);
        assert.strictEqual(err.isNetworkError, true);
        assert.ok(err.message.includes('ECONNREFUSED'));
        return true;
      }
    );
  });

  it('Q. should safely ignore malformed JSON event data without crashing', async () => {
    const sseWire = [
      'event: diagnosis_started\ndata: {"session_id":"s1","finding_id":"f1"}\n\n',
      'event: response_chunk\ndata: {NOT_JSON_CORRUPT_BYTES\n\n',
      'event: response_chunk\ndata: {"session_id":"s1","finding_id":"f1","chunk":"valid chunk"}\n\n',
      'event: completed\ndata: {"session_id":"s1","finding_id":"f1","status":"completed"}\n\n',
    ];

    const client = new DiagnosisClient({
      fetchFn: (async () => createMockResponse(sseWire)) as unknown as typeof fetch,
    });

    const received: DiagnosisStreamEvent[] = [];
    for await (const evt of client.streamDiagnosis(sampleRequest)) {
      received.push(evt);
    }

    // Malformed chunk ignored, valid events preserved
    assert.strictEqual(received.length, 3);
    assert.strictEqual(received[0].event, 'diagnosis_started');
    assert.strictEqual(received[1].event, 'response_chunk');
    assert.strictEqual(received[2].event, 'completed');
  });

  it('R. should safely ignore unknown event types without crashing', async () => {
    const sseWire = [
      'event: diagnosis_started\ndata: {"session_id":"s1","finding_id":"f1"}\n\n',
      'event: ping_telemetry\ndata: {"some":"telemetry"}\n\n',
      'event: completed\ndata: {"session_id":"s1","finding_id":"f1","status":"completed"}\n\n',
    ];

    const client = new DiagnosisClient({
      fetchFn: (async () => createMockResponse(sseWire)) as unknown as typeof fetch,
    });

    const received: DiagnosisStreamEvent[] = [];
    for await (const evt of client.streamDiagnosis(sampleRequest)) {
      received.push(evt);
    }

    assert.strictEqual(received.length, 2);
    assert.strictEqual(received[0].event, 'diagnosis_started');
    assert.strictEqual(received[1].event, 'completed');
  });

  it('S & AB. should emit DiagnosisErrorEvent and terminate when provider error event arrives', async () => {
    const sseWire = [
      'event: diagnosis_started\ndata: {"session_id":"s1","finding_id":"f1"}\n\n',
      'event: error\ndata: {"session_id":"s1","finding_id":"f1","error_type":"provider_unavailable","message":"No AI provider configured","retryable":false}\n\n',
      'event: completed\ndata: {"session_id":"s1","finding_id":"f1","status":"completed"}\n\n',
    ];

    const client = new DiagnosisClient({
      fetchFn: (async () => createMockResponse(sseWire)) as unknown as typeof fetch,
    });

    const received: DiagnosisStreamEvent[] = [];
    for await (const evt of client.streamDiagnosis(sampleRequest)) {
      received.push(evt);
    }

    assert.strictEqual(received.length, 2);
    assert.strictEqual(received[0].event, 'diagnosis_started');
    assert.strictEqual(received[1].event, 'error');

    const errEvt = received[1] as { event: string; error_type: string; retryable: boolean };
    assert.strictEqual(errEvt.error_type, 'provider_unavailable');
    assert.strictEqual(errEvt.retryable, false);

    // Completed after error must NOT be emitted
    assert.ok(!received.some((e) => e.event === 'completed'));
  });

  it('T & X. should throw on premature stream termination without completed or error event', async () => {
    const sseWire = [
      'event: diagnosis_started\ndata: {"session_id":"s1","finding_id":"f1"}\n\n',
      'event: response_chunk\ndata: {"session_id":"s1","finding_id":"f1","chunk":"halfway..."}\n\n',
      // Stream terminates abruptly here without completed or error!
    ];

    const client = new DiagnosisClient({
      fetchFn: (async () => createMockResponse(sseWire)) as unknown as typeof fetch,
    });

    await assert.rejects(
      async () => {
        for await (const _ of client.streamDiagnosis(sampleRequest)) {}
      },
      (err: unknown) => {
        assert.ok(err instanceof DiagnosisClientError);
        assert.ok(err.message.includes('terminated prematurely'));
        return true;
      }
    );
  });

  it('U. should immediately return when AbortSignal is pre-aborted', async () => {
    let fetchCalled = false;
    const mockFetch = async () => {
      fetchCalled = true;
      return createMockResponse([]);
    };

    const client = new DiagnosisClient({ fetchFn: mockFetch as unknown as typeof fetch });
    const controller = new AbortController();
    controller.abort();

    const received: DiagnosisStreamEvent[] = [];
    for await (const evt of client.streamDiagnosis(sampleRequest, { signal: controller.signal })) {
      received.push(evt);
    }

    assert.strictEqual(received.length, 0);
    assert.strictEqual(fetchCalled, false);
  });

  it('V, W, Y, Z, AA. should handle mid-stream cancellation, cancel body, and release lock', async () => {
    let cancelCalled = false;
    const controller = new AbortController();

    const sseWire = [
      'event: diagnosis_started\ndata: {"session_id":"s1","finding_id":"f1"}\n\n',
      'event: response_chunk\ndata: {"session_id":"s1","finding_id":"f1","chunk":"c1"}\n\n',
      'event: response_chunk\ndata: {"session_id":"s1","finding_id":"f1","chunk":"c2"}\n\n',
      'event: completed\ndata: {"session_id":"s1","finding_id":"f1","status":"completed"}\n\n',
    ];

    const mockFetch = async () =>
      createMockResponse(sseWire, 200, { 'content-type': 'text/event-stream' }, () => {
        cancelCalled = true;
      });

    const client = new DiagnosisClient({ fetchFn: mockFetch as unknown as typeof fetch });

    const callbacksReceived: DiagnosisStreamEvent[] = [];
    const generatorReceived: DiagnosisStreamEvent[] = [];

    for await (const evt of client.streamDiagnosis(sampleRequest, {
      signal: controller.signal,
      onEvent: (e) => callbacksReceived.push(e),
    })) {
      generatorReceived.push(evt);
      if (generatorReceived.length === 2) {
        // Abort mid-stream after second event
        controller.abort();
      }
    }

    assert.strictEqual(generatorReceived.length, 2);
    assert.strictEqual(callbacksReceived.length, 2);
    assert.ok(cancelCalled, 'Expected stream body cancel to be called on abort');
    // Completed event must NOT be emitted after abort
    assert.ok(!generatorReceived.some((e) => e.event === 'completed'));
  });

  it('Z. should redact sensitive credentials in DiagnosisClientError messages', () => {
    const err = new DiagnosisClientError(
      'Error connecting with Bearer secret_jwt_token_12345 and sk-proj-abcde123456789012345678 to host'
    );
    assert.ok(!err.message.includes('secret_jwt_token_12345'));
    assert.ok(!err.message.includes('sk-proj-abcde123456789012345678'));
    assert.ok(err.message.includes('[REDACTED]'));
  });

  it('AA. should normalize base URL correctly', () => {
    const client = new DiagnosisClient({ baseUrl: 'http://127.0.0.1:8000///' });
    assert.strictEqual(client.getBaseUrl(), 'http://127.0.0.1:8000');

    client.setBaseUrl('https://api.edgemind.dev// ');
    assert.strictEqual(client.getBaseUrl(), 'https://api.edgemind.dev');
  });

  it('AB. should send correctly formatted JSON request body to backend', async () => {
    let capturedBody = '';
    let capturedMethod = '';
    let capturedUrl = '';

    const mockFetch = async (url: string | URL | Request, init?: RequestInit) => {
      capturedUrl = String(url);
      capturedMethod = init?.method || '';
      capturedBody = String(init?.body || '');
      return createMockResponse([
        'event: diagnosis_started\ndata: {"session_id":"s1","finding_id":"EM-DIV0"}\n\n',
        'event: completed\ndata: {"session_id":"s1","finding_id":"EM-DIV0","status":"completed"}\n\n',
      ]);
    };

    const client = new DiagnosisClient({
      baseUrl: 'http://127.0.0.1:8000',
      fetchFn: mockFetch as unknown as typeof fetch,
    });

    for await (const _ of client.streamDiagnosis(sampleRequest)) {}

    assert.strictEqual(capturedMethod, 'POST');
    assert.strictEqual(capturedUrl, 'http://127.0.0.1:8000/api/v1/diagnose/stream');

    const parsed = JSON.parse(capturedBody);
    assert.strictEqual(parsed.finding.finding_id, 'EM-DIV0');
    assert.strictEqual(parsed.finding.severity, 'error');
    assert.strictEqual(parsed.context_start_line, 1);
    assert.strictEqual(parsed.context_end_line, 3);
  });
});
