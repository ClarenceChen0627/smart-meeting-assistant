import { Cpu, ChevronDown } from 'lucide-react';
import { useState, useRef, useEffect } from 'react';
import type { ASRProvider } from '../../types';

interface ASRProviderControlsProps {
  currentProvider: ASRProvider;
  onProviderChange: (provider: ASRProvider) => void;
}

const providers: Array<{ code: ASRProvider; name: string; description: string; badge: string }> = [
  {
    code: 'volcengine',
    name: 'Volcengine Doubao',
    description: 'Default live ASR with native speaker clustering',
    badge: 'Recommended',
  },
  {
    code: 'dashscope',
    name: 'DashScope + pyannote',
    description: 'Realtime ASR with finalize-time diarization fallback',
    badge: 'Fallback',
  },
];

export function ASRProviderControls({ currentProvider, onProviderChange }: ASRProviderControlsProps) {
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  const selectedProvider = providers.find((provider) => provider.code === currentProvider) || providers[0];

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    }

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  return (
    <div className="relative" ref={dropdownRef}>
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-2 px-4 py-2 bg-gray-100 hover:bg-gray-200 rounded-lg transition-colors text-sm text-gray-700"
      >
        <Cpu className="w-4 h-4" />
        <span>{selectedProvider.name}</span>
        <ChevronDown className={`w-4 h-4 transition-transform ${isOpen ? 'rotate-180' : ''}`} />
      </button>

      {isOpen && (
        <div className="absolute right-0 mt-2 w-72 bg-white rounded-lg shadow-lg border border-gray-200 py-2 z-50">
          <div className="px-3 py-2 border-b border-gray-100">
            <p className="text-xs text-gray-500">Select ASR provider</p>
          </div>

          <div className="max-h-80 overflow-y-auto">
            {providers.map((provider) => (
              <button
                key={provider.code}
                onClick={() => {
                  onProviderChange(provider.code);
                  setIsOpen(false);
                }}
                className={`w-full text-left px-4 py-3 hover:bg-gray-50 transition-colors ${
                  currentProvider === provider.code ? 'bg-blue-50 text-blue-600' : 'text-gray-700'
                }`}
              >
                <div className="flex items-center justify-between gap-3 mb-1">
                  <span className="text-sm">{provider.name}</span>
                  <span className="text-[10px] px-2 py-0.5 rounded-full bg-gray-100 text-gray-500 border border-gray-200">
                    {provider.badge}
                  </span>
                </div>
                <p className="text-xs text-gray-500 leading-relaxed">{provider.description}</p>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
