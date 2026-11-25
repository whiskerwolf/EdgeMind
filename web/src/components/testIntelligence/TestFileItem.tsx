import React from 'react';
import { ChevronDown, ChevronRight, FileWarning, Trash2 } from 'lucide-react';
import { ParsedTestFile } from '../../utils/testIntelligenceHelpers';
import { Badge } from '../ui/Badge';
import { cn } from '../../utils/cn';

export interface TestFileItemProps {
  file: ParsedTestFile;
  isSelected: boolean;
  isExpanded: boolean;
  onSelect: (file: ParsedTestFile) => void;
  onToggleExpand: (id: string) => void;
  onRemove: (id: string) => void;
}

function getFrameworkBadgeVariant(
  fw: ParsedTestFile['framework']
): 'info' | 'success' | 'warning' | 'neutral' {
  if (fw === 'pytest') return 'info';
  if (fw === 'unittest') return 'success';
  if (fw === 'unsupported') return 'warning';
  return 'neutral';
}

export const TestFileItem: React.FC<TestFileItemProps> = ({
  file,
  isSelected,
  isExpanded,
  onSelect,
  onToggleExpand,
  onRemove,
}) => {
  return (
    <div
      className={cn(
        'border-b border-em-border-hairline last:border-b-0 transition-colors',
        isSelected ? 'bg-em-elevated/80 border-l-2 border-l-em-accent-primary' : 'bg-em-card border-l-2 border-l-transparent'
      )}
    >
      <div className="p-3 flex items-start justify-between gap-2">
        <button
          type="button"
          onClick={() => onSelect(file)}
          aria-pressed={isSelected}
          className="flex-1 min-w-0 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-em-border-focus rounded"
        >
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="text-xs font-semibold font-mono text-em-text-primary truncate">
              {file.filename}
            </span>
            <Badge variant={getFrameworkBadgeVariant(file.framework)}>
              {file.framework}
            </Badge>
            {file.role === 'source' && <Badge variant="neutral">Source Module</Badge>}
          </div>

          <div className="mt-1.5 flex flex-wrap items-center gap-2 text-[11px] font-mono tabular-nums text-em-text-dim">
            {file.isSupported ? (
              file.role === 'test' ? (
                <>
                  <span>{file.testCases.length} test(s)</span>
                  <span>•</span>
                  <span>{file.imports.length} import(s)</span>
                  <span>•</span>
                  <span>{file.lineCount} lines</span>
                </>
              ) : (
                <>
                  <span>{file.functions.length} function(s)</span>
                  <span>•</span>
                  <span>{file.lineCount} lines</span>
                </>
              )
            ) : (
              <span className="text-em-status-warning inline-flex items-center gap-1 font-sans">
                <FileWarning className="w-3 h-3 shrink-0" aria-hidden="true" />
                <span>Unsupported test framework/extension</span>
              </span>
            )}
          </div>
        </button>

        <div className="flex items-center gap-1 shrink-0">
          {file.isSupported && (file.testCases.length > 0 || file.functions.length > 0) && (
            <button
              type="button"
              onClick={() => onToggleExpand(file.id)}
              aria-expanded={isExpanded}
              aria-label={isExpanded ? `Collapse ${file.filename}` : `Expand ${file.filename}`}
              className="p-1.5 text-em-text-muted hover:text-em-text-primary hover:bg-white/[0.04] rounded transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-em-border-focus"
            >
              {isExpanded ? (
                <ChevronDown className="w-3.5 h-3.5" />
              ) : (
                <ChevronRight className="w-3.5 h-3.5" />
              )}
            </button>
          )}
          <button
            type="button"
            onClick={() => onRemove(file.id)}
            aria-label={`Remove ${file.filename}`}
            className="p-1.5 text-em-text-dim hover:text-em-status-error hover:bg-em-status-error/10 rounded transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-em-border-focus"
          >
            <Trash2 className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {!file.isSupported && file.unsupportedReason && (
        <div className="px-3 pb-3">
          <p className="text-[11px] text-em-status-warning bg-em-status-warning/5 border border-em-status-warning/25 rounded p-2">
            {file.unsupportedReason}
          </p>
        </div>
      )}

      {isExpanded && file.isSupported && (
        <div className="px-3 pb-3 space-y-2">
          {file.role === 'test' && file.testCases.length > 0 && (
            <div className="rounded border border-em-border-hairline bg-em-workspace p-2 space-y-1.5">
              <span className="block text-[10px] font-mono uppercase tracking-wider text-em-text-dim">
                Discovered Test Functions
              </span>
              <ul className="space-y-1">
                {file.testCases.map((tc) => (
                  <li
                    key={tc.id}
                    className="flex flex-wrap items-center justify-between gap-2 text-[11px] font-mono py-0.5 border-b border-em-border-hairline last:border-b-0"
                  >
                    <span className="text-em-text-primary truncate">
                      {tc.className ? `${tc.className}.` : ''}
                      {tc.name}()
                    </span>
                    <span className="text-em-text-dim tabular-nums shrink-0">
                      Line {tc.line}
                      {tc.assertionsCount > 0 ? ` · ${tc.assertionsCount} assert` : ''}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {file.functions.length > 0 && (
            <div className="rounded border border-em-border-hairline bg-em-workspace p-2 space-y-1.5">
              <span className="block text-[10px] font-mono uppercase tracking-wider text-em-text-dim">
                Helper / Source Functions
              </span>
              <ul className="space-y-1">
                {file.functions.map((fn) => (
                  <li
                    key={fn.id}
                    className="flex items-center justify-between gap-2 text-[11px] font-mono"
                  >
                    <span className="text-em-text-secondary truncate">
                      {fn.className ? `${fn.className}.` : ''}
                      {fn.name}({fn.params.join(', ')})
                    </span>
                    <span className="text-em-text-dim tabular-nums shrink-0">Line {fn.line}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
