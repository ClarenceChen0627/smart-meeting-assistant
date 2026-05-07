export const asrProviderOptions = [
  {
    code: 'volcengine',
    name: 'Volcengine Doubao',
    description: 'Default live ASR with native speaker clustering',
    badge: 'Recommended',
  },
  {
    code: 'dashscope',
    name: 'DashScope Hybrid',
    description: 'Paraformer realtime ASR with live diart speakers and pyannote final check',
    badge: 'Fallback',
  },
  {
    code: 'demo',
    name: 'Demo Mode',
    description: 'Deterministic local workflow when the backend has DEMO_MODE=1',
    badge: 'Local',
  },
];
