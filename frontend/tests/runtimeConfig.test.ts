import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  apiFetch,
  buildApiBaseUrl,
  buildWebSocketBaseUrl,
  buildWebSocketUrl,
  setApiAccessToken,
} from '../src/app/runtimeConfig';

const setWindowLocation = (url: string) => {
  Object.defineProperty(window, 'location', {
    configurable: true,
    value: new URL(url),
  });
};

beforeEach(() => {
  vi.stubEnv('VITE_API_BASE_URL', '');
  vi.stubEnv('VITE_WS_BASE_URL', '');
  window.localStorage.clear();
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.restoreAllMocks();
});

describe('runtimeConfig', () => {
  it('defaults to same-origin HTTP and WebSocket URLs', () => {
    setWindowLocation('http://localhost:5173/');

    expect(buildApiBaseUrl()).toBe('');
    expect(buildWebSocketBaseUrl()).toBe('ws://localhost:5173');
    expect(buildWebSocketUrl('finance', 'en', 'demo', 'AI=>Artificial intelligence')).toBe(
      'ws://localhost:5173/ws/meeting?scene=finance&target_lang=en&provider=demo&glossary_terms=AI%3D%3EArtificial+intelligence'
    );
  });

  it('uses WSS when the frontend page is HTTPS', () => {
    setWindowLocation('https://mobile.test.local/');

    expect(buildWebSocketBaseUrl()).toBe('wss://mobile.test.local');
  });

  it('keeps explicit non-loopback backend overrides', () => {
    setWindowLocation('http://localhost:5173/');
    vi.stubEnv('VITE_API_BASE_URL', 'https://api.example.com/');
    vi.stubEnv('VITE_WS_BASE_URL', 'wss://api.example.com/');

    expect(buildApiBaseUrl()).toBe('https://api.example.com');
    expect(buildWebSocketBaseUrl()).toBe('wss://api.example.com');
  });

  it('ignores localhost overrides when the page is opened from another device', () => {
    setWindowLocation('http://192.168.1.23:5173/');
    vi.stubEnv('VITE_API_BASE_URL', 'http://localhost:8080');
    vi.stubEnv('VITE_WS_BASE_URL', 'ws://localhost:8080');

    expect(buildApiBaseUrl()).toBe('');
    expect(buildWebSocketBaseUrl()).toBe('ws://192.168.1.23:5173');
  });

  it('adds the saved API token to WebSocket URLs and fetch headers', async () => {
    setWindowLocation('http://localhost:5173/');
    setApiAccessToken('secret-token');
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('{}'));

    expect(buildWebSocketUrl('general', 'en', 'demo', '')).toBe(
      'ws://localhost:5173/ws/meeting?scene=general&target_lang=en&provider=demo&access_token=secret-token'
    );

    await apiFetch('/api/meetings', {
      headers: {
        'Content-Type': 'application/json',
      },
    });

    const init = fetchSpy.mock.calls[0][1] as RequestInit;
    const headers = init.headers as Headers;
    expect(headers.get('Authorization')).toBe('Bearer secret-token');
    expect(headers.get('Content-Type')).toBe('application/json');
  });
});
