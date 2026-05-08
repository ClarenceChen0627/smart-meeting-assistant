const LOCAL_HOSTNAMES = new Set(['localhost', '127.0.0.1', '::1']);

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
  return `${buildWebSocketBaseUrl()}/ws/meeting?${params.toString()}`;
};
