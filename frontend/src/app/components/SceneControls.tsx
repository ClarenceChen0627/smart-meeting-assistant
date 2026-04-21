import { Briefcase, ChevronDown } from 'lucide-react';
import { useState, useRef, useEffect } from 'react';

interface SceneControlsProps {
  currentScene: string;
  onSceneChange: (scene: string) => void;
}

const scenes = [
  { code: 'general', name: 'General Meeting', icon: '📝' },
  { code: 'finance', name: 'Finance Review', icon: '📈' },
  { code: 'hr', name: 'HR / Interview', icon: '👥' }
];

export function SceneControls({ currentScene, onSceneChange }: SceneControlsProps) {
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  const selectedScene = scenes.find(s => s.code === currentScene) || scenes[0];

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
        <Briefcase className="w-4 h-4" />
        <span className="text-lg">{selectedScene.icon}</span>
        <span>{selectedScene.name}</span>
        <ChevronDown className={`w-4 h-4 transition-transform ${isOpen ? 'rotate-180' : ''}`} />
      </button>

      {isOpen && (
        <div className="absolute right-0 mt-2 w-56 bg-white rounded-lg shadow-lg border border-gray-200 py-2 z-50">
          <div className="px-3 py-2 border-b border-gray-100">
            <p className="text-xs text-gray-500">Select meeting scene</p>
          </div>

          <div className="max-h-80 overflow-y-auto">
            {scenes.map((scene) => (
              <button
                key={scene.code}
                onClick={() => {
                  onSceneChange(scene.code);
                  setIsOpen(false);
                }}
                className={`w-full flex items-center gap-3 px-4 py-2 hover:bg-gray-50 transition-colors ${
                  currentScene === scene.code ? 'bg-blue-50 text-blue-600' : 'text-gray-700'
                }`}
              >
                <span className="text-lg">{scene.icon}</span>
                <span className="text-sm">{scene.name}</span>
                {currentScene === scene.code && (
                  <svg className="w-4 h-4 ml-auto" fill="currentColor" viewBox="0 0 20 20">
                    <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                  </svg>
                )}
              </button>
            ))}
          </div>

          <div className="px-4 py-2 border-t border-gray-100 mt-2">
            <p className="text-xs text-gray-500">
              Helps AI extract appropriate summaries
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
