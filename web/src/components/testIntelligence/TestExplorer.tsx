import React, { useMemo, useRef, useState } from 'react';
import { FilePlus2, FlaskConical, Search, Trash2, Upload, X } from 'lucide-react';
import {
  DetectedTestFramework,
  ParsedTestFile,
  SuppliedCodeFile,
} from '../../utils/testIntelligenceHelpers';
import { TestFileItem } from './TestFileItem';
import { Input } from '../ui/Input';
import { Button } from '../ui/Button';
import { EmptyState } from '../ui/EmptyState';
import { cn } from '../../utils/cn';

type FrameworkFilter = 'all' | DetectedTestFramework;

export interface TestExplorerProps {
  parsedFiles: ParsedTestFile[];
  selectedFileId: string | null;
  onSelectFile: (file: ParsedTestFile) => void;
  onAddFiles: (files: SuppliedCodeFile[]) => void;
  onRemoveFile: (id: string) => void;
  onClearAllFiles: () => void;
  onLoadSampleSuite: () => void;
}

export const TestExplorer: React.FC<TestExplorerProps> = ({
  parsedFiles,
  selectedFileId,
  onSelectFile,
  onAddFiles,
  onRemoveFile,
  onClearAllFiles,
  onLoadSampleSuite,
}) => {
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [search, setSearch] = useState('');
  const [frameworkFilter, setFrameworkFilter] = useState<FrameworkFilter>('all');
  const [expandedIds, setExpandedIds] = useState<Record<string, boolean>>({});

  // Inline "Paste / Add Test File" composer
  const [showPasteBox, setShowPasteBox] = useState(false);
  const [pasteFilename, setPasteFilename] = useState('test_custom.py');
  const [pasteContent, setPasteContent] = useState('');
  const [pasteError, setPasteError] = useState<string | null>(null);

  const availableFrameworks = useMemo(() => {
    const seen = new Set<DetectedTestFramework>();
    parsedFiles.forEach((f) => seen.add(f.framework));
    return Array.from(seen);
  }, [parsedFiles]);

  const filteredFiles = useMemo(() => {
    const q = search.trim().toLowerCase();
    return parsedFiles.filter((file) => {
      if (frameworkFilter !== 'all' && file.framework !== frameworkFilter) {
        return false;
      }
      if (!q) return true;
      const text = [
        file.filename,
        file.framework,
        ...file.imports,
        ...file.testCases.map((tc) => `${tc.className || ''} ${tc.name}`),
        ...file.functions.map((fn) => fn.name),
      ]
        .join(' ')
        .toLowerCase();
      return text.includes(q);
    });
  }, [parsedFiles, frameworkFilter, search]);

  const handleToggleExpand = (id: string) => {
    setExpandedIds((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  const handleFileInput = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []);
    if (files.length === 0) return;
    const loaded: SuppliedCodeFile[] = await Promise.all(
      files.map(async (f, idx) => ({
        id: `file-${Date.now()}-${idx}-${f.name}`,
        filename: f.name,
        content: await f.text(),
      }))
    );
    onAddFiles(loaded);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const handleAddPastedFile = (e: React.FormEvent) => {
    e.preventDefault();
    const cleanName = pasteFilename.trim();
    if (!cleanName) {
      setPasteError('Enter a filename such as test_solution.py.');
      return;
    }
    if (!pasteContent.trim()) {
      setPasteError('Paste test or module code before adding.');
      return;
    }
    setPasteError(null);
    onAddFiles([
      {
        id: `pasted-${Date.now()}-${cleanName}`,
        filename: cleanName,
        content: pasteContent,
      },
    ]);
    setPasteContent('');
    setShowPasteBox(false);
  };

  return (
    <section
      aria-labelledby="test-explorer-heading"
      className="flex flex-col rounded-lg border border-em-border-default bg-em-card overflow-hidden"
    >
      {/* Header */}
      <div className="px-4 py-2.5 border-b border-em-border-hairline flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <FlaskConical className="w-4 h-4 text-em-accent-primary shrink-0" aria-hidden="true" />
          <h3
            id="test-explorer-heading"
            className="text-xs font-semibold uppercase tracking-wider text-em-text-secondary"
          >
            Supplied Test Explorer
          </h3>
        </div>

        <div className="flex flex-wrap items-center gap-1.5">
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept=".py,.pyi,.ts,.tsx,.js,.jsx,.txt"
            onChange={(e) => {
              void handleFileInput(e);
            }}
            className="hidden"
            aria-label="Upload test or source files"
          />
          <Button
            variant="outline"
            size="sm"
            leftIcon={<Upload className="w-3 h-3" />}
            onClick={() => fileInputRef.current?.click()}
          >
            Upload Files
          </Button>
          <Button
            variant="secondary"
            size="sm"
            leftIcon={<FilePlus2 className="w-3 h-3" />}
            onClick={() => setShowPasteBox((prev) => !prev)}
          >
            {showPasteBox ? 'Close Editor' : 'Paste Test File'}
          </Button>
          {parsedFiles.length > 0 && (
            <Button
              variant="ghost"
              size="sm"
              leftIcon={<Trash2 className="w-3 h-3" />}
              onClick={onClearAllFiles}
              aria-label="Clear supplied files"
            >
              Clear
            </Button>
          )}
        </div>
      </div>

      {/* Inline Paste Box */}
      {showPasteBox && (
        <form
          onSubmit={handleAddPastedFile}
          className="p-3 bg-em-workspace border-b border-em-border-hairline space-y-2.5"
        >
          <div className="grid grid-cols-1 sm:grid-cols-12 gap-2 items-center">
            <div className="sm:col-span-5">
              <Input
                type="text"
                value={pasteFilename}
                onChange={(e) => setPasteFilename(e.target.value)}
                aria-label="Pasted file name"
                placeholder="e.g. test_solution.py"
              />
            </div>
            <div className="sm:col-span-7 text-[11px] text-em-text-muted">
              Parsed statically in-browser without executing code. Supports pytest, unittest, or .py source modules.
            </div>
          </div>

          <textarea
            rows={5}
            value={pasteContent}
            onChange={(e) => setPasteContent(e.target.value)}
            aria-label="Pasted Python test source"
            placeholder={'import pytest\n\ndef test_example():\n    assert 1 + 1 == 2'}
            className="w-full rounded-md border border-em-border-default bg-em-canvas p-2.5 text-xs font-mono text-em-text-primary placeholder:text-em-text-dim focus:outline-none focus:border-em-accent-primary"
          />

          {pasteError && <p className="text-[11px] text-em-status-error">{pasteError}</p>}

          <div className="flex items-center justify-end gap-2">
            <Button type="button" variant="ghost" size="sm" onClick={() => setShowPasteBox(false)}>
              Cancel
            </Button>
            <Button type="submit" variant="primary" size="sm">
              Add File to Explorer
            </Button>
          </div>
        </form>
      )}

      {/* Search & Filter Toolbar (only shown when files exist) */}
      {parsedFiles.length > 0 && (
        <div className="p-3 border-b border-em-border-hairline bg-em-workspace space-y-2.5">
          <Input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            aria-label="Search test files or test functions"
            placeholder="Search test files, functions, classes, or imports..."
            leftIcon={<Search className="w-3.5 h-3.5" />}
            rightIcon={
              search ? (
                <button
                  type="button"
                  onClick={() => setSearch('')}
                  aria-label="Clear test search"
                  className="p-0.5 text-em-text-dim hover:text-em-text-primary"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              ) : undefined
            }
          />

          <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label="Framework filter">
            <button
              type="button"
              onClick={() => setFrameworkFilter('all')}
              aria-pressed={frameworkFilter === 'all'}
              className={cn(
                'px-2 py-1 rounded text-[11px] font-mono transition-colors',
                frameworkFilter === 'all'
                  ? 'bg-em-accent-subtle text-em-accent-primary font-semibold border border-em-accent-primary/35'
                  : 'text-em-text-muted hover:text-em-text-primary border border-em-border-hairline'
              )}
            >
              All ({parsedFiles.length})
            </button>
            {availableFrameworks.map((fw) => (
              <button
                key={fw}
                type="button"
                onClick={() => setFrameworkFilter(fw)}
                aria-pressed={frameworkFilter === fw}
                className={cn(
                  'px-2 py-1 rounded text-[11px] font-mono transition-colors',
                  frameworkFilter === fw
                    ? 'bg-em-accent-subtle text-em-accent-primary font-semibold border border-em-accent-primary/35'
                    : 'text-em-text-muted hover:text-em-text-primary border border-em-border-hairline'
                )}
              >
                {fw}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* List / Empty States */}
      <div className="max-h-[420px] overflow-y-auto">
        {parsedFiles.length === 0 ? (
          <div className="p-4">
            <EmptyState
              icon={FlaskConical}
              title="No Test Files Discovered or Loaded"
              description="EdgeMind does not auto-scan server directories. Upload .py test files, paste test source, or load our deterministic sample target and pytest suite."
              action={
                <Button variant="secondary" size="sm" onClick={onLoadSampleSuite}>
                  Load Sample Source & Pytest Suite
                </Button>
              }
              className="my-0 border-em-border-hairline"
            />
          </div>
        ) : filteredFiles.length === 0 ? (
          <div className="p-6 text-center space-y-2">
            <p className="text-xs text-em-text-muted">No supplied files match your current filter.</p>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                setSearch('');
                setFrameworkFilter('all');
              }}
            >
              Reset Test Filter
            </Button>
          </div>
        ) : (
          <div role="list">
            {filteredFiles.map((file) => (
              <div key={file.id} role="listitem">
                <TestFileItem
                  file={file}
                  isSelected={selectedFileId === file.id}
                  isExpanded={Boolean(expandedIds[file.id])}
                  onSelect={onSelectFile}
                  onToggleExpand={handleToggleExpand}
                  onRemove={onRemoveFile}
                />
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  );
};
