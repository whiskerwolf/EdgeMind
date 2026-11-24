import React from 'react';
import { StatusIndicatorType } from '../ui/StatusIndicator';

export interface FooterBarProps {
  healthStatus: StatusIndicatorType;
  durationMs: number | null;
}

export const FooterBar: React.FC<FooterBarProps> = ({ healthStatus, durationMs }) => {
  return (
    <footer className="h-7 bg-em-sidebar border-t border-em-border-default px-4 flex items-center justify-between text-[11px] font-mono text-em-text-dim select-none shrink-0 z-20">
      <div className="flex items-center gap-4">
        <span className="hidden sm:inline">Python 3.13 (Static AST)</span>
        <span className="hidden sm:inline">·</span>
        <span>Storage: In-Memory (Stateless)</span>
        <span className="hidden md:inline">·</span>
        <span className="hidden md:inline">AI Model: Ollama qwen3:4b</span>
      </div>
      <div className="flex items-center gap-3">
        {durationMs !== null && healthStatus === 'connected' && (
          <span>Ping: {durationMs}ms</span>
        )}
        <span>UTF-8</span>
      </div>
    </footer>
  );
};
