import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { ApiClient } from '../api/client';

describe('ApiClient', () => {
  let client: ApiClient;

  beforeEach(() => {
    client = new ApiClient('http://127.0.0.1:8000', 3000);
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('correctly sets and returns base URL', () => {
    expect(client.getBaseUrl()).toBe('http://127.0.0.1:8000');
    client.setBaseUrl('http://localhost:9000/');
    expect(client.getBaseUrl()).toBe('http://localhost:9000');
  });

  it('fetches health endpoint successfully', async () => {
    const mockHealth = { status: 'healthy', service: 'EdgeMind' };
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      headers: {
        get: (h: string) => (h === 'content-type' ? 'application/json' : null),
      },
      json: async () => mockHealth,
    });

    const result = await client.getHealth();
    expect(result).toEqual(mockHealth);
    expect(globalThis.fetch).toHaveBeenCalledWith(
      'http://127.0.0.1:8000/health',
      expect.objectContaining({ method: 'GET' })
    );
  });

  it('normalizes HTTP 500 error responses into ApiError', async () => {
    const errorBody = { error: 'Internal Server Error', detail: 'Database unreachable' };
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      statusText: 'Internal Server Error',
      headers: {
        get: (h: string) => {
          if (h === 'content-type') return 'application/json';
          if (h === 'X-Request-ID') return 'req-1234';
          return null;
        },
      },
      json: async () => errorBody,
    });

    await expect(client.getHealth()).rejects.toMatchObject({
      error: 'Internal Server Error',
      detail: 'Database unreachable',
      status_code: 500,
      request_id: 'req-1234',
    });
  });

  it('handles network failure properly', async () => {
    globalThis.fetch = vi.fn().mockRejectedValue(new Error('Connection refused'));

    await expect(client.getHealth()).rejects.toMatchObject({
      error: 'NetworkError',
      detail: 'Connection refused',
      status_code: 0,
    });
  });
});
