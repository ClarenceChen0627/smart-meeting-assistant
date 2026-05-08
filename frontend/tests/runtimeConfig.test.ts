import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { buildApiBaseUrl, buildWebSocketBaseUrl, buildWebSocketUrl } from '../src/app/runtimeConfig';

const setWindowLocation = (url: string) => {
  Object.defineProperty(window, 'location', {
    configurable: true,
    value: new URL(url),
  });
};

beforeEach(() => {
  vi.stubEnv('VITE_API_BASE_URL', '');
  vi.stubEnv('VITE_WS_BASE_URL', '');
});

afterEach(() => {
  vi.unstubAllEnvs();
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
});
