const LOCAL_HOSTNAMES = new Set(['localhost', '127.0.0.1', '::1']);
const API_ACCESS_TOKEN_STORAGE_KEY = 'smartMeetingAssistant.apiAccessToken';

const trimBaseUrl = (baseUrl: string) => baseUrl.replace(/\/+$/, '');

const isLocalHostname = (hostname: string) => LOCAL_HOSTNAMES.has(hostname.toLowerCase());

const shouldIgnoreLoopbackOverride = (baseUrl: string) => {
  if (typeof window === 'undefined' || window.location.protocol === 'file:') {
    return false;
  }
  if (isLocalHostname(window.location.hostname)) {
    return false;
  }

  try {
    return isLocalHostname(new URL(baseUrl).hostname);
  } catch {
    return false;
  }
};

export const buildApiBaseUrl = () => {
  const explicitBaseUrl = import.meta.env.VITE_API_BASE_URL?.trim();
  if (explicitBaseUrl && !shouldIgnoreLoopbackOverride(explicitBaseUrl)) {
    return trimBaseUrl(explicitBaseUrl);
  }

  const webSocketBaseUrl = import.meta.env.VITE_WS_BASE_URL?.trim();
  if (webSocketBaseUrl && !shouldIgnoreLoopbackOverride(webSocketBaseUrl)) {
    return trimBaseUrl(webSocketBaseUrl.replace(/^ws/i, 'http'));
  }

  if (typeof window === 'undefined' || window.location.protocol === 'file:') {
    return 'http://localhost:8080';
  }

  return '';
};

export const buildWebSocketBaseUrl = () => {
  const explicitBaseUrl = import.meta.env.VITE_WS_BASE_URL?.trim();
  if (explicitBaseUrl && !shouldIgnoreLoopbackOverride(explicitBaseUrl)) {
    return trimBaseUrl(explicitBaseUrl);
  }

  if (typeof window === 'undefined' || window.location.protocol === 'file:') {
    return 'ws://localhost:8080';
  }

  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${protocol}//${window.location.host}`;
};

export const buildWebSocketUrl = (
  scene: string,
  targetLang: string,
  provider: string,
  glossaryTerms: string
) => {
  const params = new URLSearchParams({
    scene,
    target_lang: targetLang,
    provider,
  });
  if (glossaryTerms.trim()) {
    params.set('glossary_terms', glossaryTerms.trim());
  }
  const token = getApiAccessToken();
  if (token) {
    params.set('access_token', token);
  }
  return `${buildWebSocketBaseUrl()}/ws/meeting?${params.toString()}`;
};

export const getApiAccessToken = () => {
  if (typeof window === 'undefined') {
    return '';
  }
  return window.localStorage.getItem(API_ACCESS_TOKEN_STORAGE_KEY)?.trim() ?? '';
};

export const setApiAccessToken = (token: string) => {
  if (typeof window === 'undefined') {
    return;
  }
  const normalized = token.trim();
  if (normalized) {
    window.localStorage.setItem(API_ACCESS_TOKEN_STORAGE_KEY, normalized);
    return;
  }
  window.localStorage.removeItem(API_ACCESS_TOKEN_STORAGE_KEY);
};

export const buildApiHeaders = (headers?: HeadersInit) => {
  const nextHeaders = new Headers(headers);
  const token = getApiAccessToken();
  if (token && !nextHeaders.has('Authorization') && !nextHeaders.has('X-API-Token')) {
    nextHeaders.set('Authorization', `Bearer ${token}`);
  }
  return nextHeaders;
};

export const apiFetch = (input: RequestInfo | URL, init: RequestInit = {}) =>
  fetch(input, {
    ...init,
    headers: buildApiHeaders(init.headers),
  });
