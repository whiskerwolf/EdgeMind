import { describe, it, before, after } from 'node:test';
import * as assert from 'node:assert';
import * as http from 'node:http';
import { ApiClient } from '../api/client';
import { validateBackendUrl } from '../utils/urlValidator';

describe('EdgeMind ApiClient & Connectivity Tests', () => {
  let mockServer: http.Server;
  let serverPort: number;
  let serverResponseCode = 200;
  let serverResponseBody = JSON.stringify({ status: 'healthy', service: 'EdgeMind' });
  let serverDelayMs = 0;

  before(async () => {
    mockServer = http.createServer((req, res) => {
      setTimeout(() => {
        if (req.url === '/health') {
          res.writeHead(serverResponseCode, { 'Content-Type': 'application/json' });
          res.end(serverResponseBody);
        } else {
          res.writeHead(404, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify({ error: 'Not Found', detail: 'Endpoint not found' }));
        }
      }, serverDelayMs);
    });

    await new Promise<void>((resolve) => {
      mockServer.listen(0, '127.0.0.1', () => {
        const addr = mockServer.address();
        if (addr && typeof addr === 'object') {
          serverPort = addr.port;
        }
        resolve();
      });
    });
  });

  after(async () => {
    await new Promise<void>((resolve) => {
      mockServer.close(() => resolve());
    });
  });

  it('1. should succeed on valid GET /health response', async () => {
    serverResponseCode = 200;
    serverResponseBody = JSON.stringify({ status: 'healthy', service: 'EdgeMind' });
    serverDelayMs = 0;

    const client = new ApiClient({
      baseUrl: `http://127.0.0.1:${serverPort}`,
      defaultTimeoutMs: 2000,
    });

    const res = await client.checkHealth();
    assert.strictEqual(res.success, true);
    assert.strictEqual(res.statusCode, 200);
    assert.ok(res.data);
    assert.strictEqual(res.data.status, 'healthy');
    assert.strictEqual(res.data.service, 'EdgeMind');
    assert.ok(typeof res.durationMs === 'number');
  });

  it('2. should handle connection refused gracefully when backend is offline', async () => {
    // Choose an unallocated closed port
    const client = new ApiClient({
      baseUrl: 'http://127.0.0.1:59999',
      defaultTimeoutMs: 1000,
    });

    const res = await client.checkHealth();
    assert.strictEqual(res.success, false);
    assert.ok(res.error);
    assert.ok(
      res.error.includes('Connection refused') || res.error.includes('failed'),
      `Expected connection error message, got: ${res.error}`
    );
  });

  it('3. should handle request timeout when backend is unresponsive', async () => {
    serverResponseCode = 200;
    serverResponseBody = JSON.stringify({ status: 'healthy', service: 'EdgeMind' });
    serverDelayMs = 500; // longer than client timeout

    const client = new ApiClient({
      baseUrl: `http://127.0.0.1:${serverPort}`,
      defaultTimeoutMs: 100, // short timeout
    });

    const res = await client.checkHealth(100);
    assert.strictEqual(res.success, false);
    assert.ok(res.error);
    assert.ok(
      res.error.includes('timed out') || res.error.includes('timeout'),
      `Expected timeout error, got: ${res.error}`
    );
  });

  it('4. should handle invalid/malformed JSON response', async () => {
    serverResponseCode = 200;
    serverResponseBody = '<html><body>502 Bad Gateway</body></html>';
    serverDelayMs = 0;

    const client = new ApiClient({
      baseUrl: `http://127.0.0.1:${serverPort}`,
      defaultTimeoutMs: 2000,
    });

    const res = await client.checkHealth();
    assert.strictEqual(res.success, false);
    assert.ok(res.error);
    assert.ok(
      res.error.includes('invalid or malformed JSON'),
      `Expected malformed JSON error, got: ${res.error}`
    );
  });

  it('5. should handle unexpected HTTP error status code (e.g. 503 Service Unavailable)', async () => {
    serverResponseCode = 503;
    serverResponseBody = JSON.stringify({
      error: 'Service Unavailable',
      detail: 'Database connection pool exhausted',
    });
    serverDelayMs = 0;

    const client = new ApiClient({
      baseUrl: `http://127.0.0.1:${serverPort}`,
      defaultTimeoutMs: 2000,
    });

    const res = await client.checkHealth();
    assert.strictEqual(res.success, false);
    assert.strictEqual(res.statusCode, 503);
    assert.ok(res.error);
    assert.ok(
      res.error.includes('Database connection pool exhausted'),
      `Expected detail from error response, got: ${res.error}`
    );
  });

  it('6. should validate backend URLs properly', () => {
    const validHttp = validateBackendUrl('http://127.0.0.1:8000/');
    assert.strictEqual(validHttp.valid, true);
    assert.strictEqual(validHttp.normalized, 'http://127.0.0.1:8000');

    const validHttps = validateBackendUrl('https://api.edgemind.dev:8443/custom');
    assert.strictEqual(validHttps.valid, true);
    assert.strictEqual(validHttps.normalized, 'https://api.edgemind.dev:8443/custom');

    const empty = validateBackendUrl('   ');
    assert.strictEqual(empty.valid, false);

    const invalidProto = validateBackendUrl('ftp://edgemind.local');
    assert.strictEqual(invalidProto.valid, false);

    const invalidFormat = validateBackendUrl('http://');
    assert.strictEqual(invalidFormat.valid, false);
  });
});
