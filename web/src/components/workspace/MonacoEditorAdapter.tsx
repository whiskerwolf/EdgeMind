import React, { useEffect, useRef, useState } from 'react';
import Editor, { loader, OnMount, BeforeMount, Monaco } from '@monaco-editor/react';
import * as monacoApi from 'monaco-editor/editor/editor.api';
import 'monaco-editor/languages/definitions/python/register';
import 'monaco-editor/languages/definitions/javascript/register';
import 'monaco-editor/languages/definitions/typescript/register';
import editorWorker from 'monaco-editor/editor/editor.worker?worker';
import type { editor as MonacoEditorNS } from 'monaco-editor';
import { ReportFinding } from '../../types/api';

let monacoConfigured = false;
function ensureMonacoConfigured() {
  if (monacoConfigured) return;
  monacoConfigured = true;

  if (typeof self !== 'undefined') {
    self.MonacoEnvironment = {
      getWorker() {
        return new editorWorker();
      },
    };
  }
  loader.config({ monaco: monacoApi as unknown as typeof import('monaco-editor') });
}

export interface WorkspaceFindingDecoration extends ReportFinding {
  severity: 'error' | 'warning';
}

export interface MonacoEditorAdapterProps {
  value: string;
  language: string;
  findings: WorkspaceFindingDecoration[];
  navigationTarget: { line: number; seq: number } | null;
  onChange: (value: string) => void;
  onAnalyzeShortcut: () => void;
  fontSize?: number;
  tabSize?: 2 | 4;
  minimap?: boolean;
  wordWrap?: 'off' | 'on';
  lineNumbers?: 'on' | 'off';
}

const MonacoEditorAdapter: React.FC<MonacoEditorAdapterProps> = ({
  value,
  language,
  findings,
  navigationTarget,
  onChange,
  onAnalyzeShortcut,
  fontSize = 13,
  tabSize = 4,
  minimap = false,
  wordWrap = 'off',
  lineNumbers = 'on',
}) => {
  ensureMonacoConfigured();

  const editorRef = useRef<MonacoEditorNS.IStandaloneCodeEditor | null>(null);
  const monacoRef = useRef<Monaco | null>(null);
  const decorationsRef = useRef<MonacoEditorNS.IEditorDecorationsCollection | null>(null);
  const analyzeCallbackRef = useRef(onAnalyzeShortcut);
  const [editorMountSeq, setEditorMountSeq] = useState(0);

  useEffect(() => {
    analyzeCallbackRef.current = onAnalyzeShortcut;
  }, [onAnalyzeShortcut]);

  const handleBeforeMount: BeforeMount = (monaco) => {
    monaco.editor.defineTheme('edgemind-dark', {
      base: 'vs-dark',
      inherit: true,
      rules: [
        { token: 'comment', foreground: '64748B', fontStyle: 'italic' },
        { token: 'keyword', foreground: '38BDF8' },
        { token: 'string', foreground: '6EE7B7' },
        { token: 'number', foreground: 'FCD34D' },
        { token: 'type', foreground: '818CF8' },
      ],
      colors: {
        'editor.background': '#10121C',
        'editor.foreground': '#F8FAFC',
        'editor.lineHighlightBackground': '#171927',
        'editor.selectionBackground': '#38BDF826',
        'editorCursor.foreground': '#38BDF8',
        'editorLineNumber.foreground': '#64748B',
        'editorLineNumber.activeForeground': '#CBD5E1',
        'editorGutter.background': '#10121C',
        'editorWidget.background': '#141624',
        'editorWidget.border': '#1E2235',
      },
    });
  };

  const handleMount: OnMount = (editor, monaco) => {
    editorRef.current = editor;
    monacoRef.current = monaco;

    editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.Enter, () => {
      analyzeCallbackRef.current();
    });
    setEditorMountSeq((prev) => prev + 1);
  };

  // Sync line decorations when findings change
  useEffect(() => {
    const editor = editorRef.current;
    const monaco = monacoRef.current;
    if (!editor || !monaco) return;

    const model = editor.getModel();
    const maxLine = model ? model.getLineCount() : 1;

    const nextDecorations: MonacoEditorNS.IModelDeltaDecoration[] = findings
      .map((f) => {
        const line = f.line || f.line_number || 1;
        if (line < 1 || line > maxLine) return null;
        const isErr = f.severity === 'error';
        return {
          range: new monaco.Range(line, 1, line, 1),
          options: {
            isWholeLine: true,
            className: isErr ? 'em-monaco-line-error' : 'em-monaco-line-warning',
            glyphMarginClassName: isErr ? 'em-monaco-glyph-error' : 'em-monaco-glyph-warning',
            hoverMessage: { value: `**${f.type}**: ${f.message}` },
          },
        };
      })
      .filter((item): item is NonNullable<typeof item> => item !== null);

    if (decorationsRef.current) {
      decorationsRef.current.clear();
    }
    decorationsRef.current = editor.createDecorationsCollection(nextDecorations);
  }, [findings, value, editorMountSeq]);

  // Navigate to source line when finding is selected
  useEffect(() => {
    if (!navigationTarget || navigationTarget.line < 1 || editorMountSeq === 0) return;
    const editor = editorRef.current;
    if (!editor) return;

    const model = editor.getModel();
    const boundedLine = model
      ? Math.max(1, Math.min(model.getLineCount(), navigationTarget.line))
      : navigationTarget.line;

    editor.revealLineInCenter(boundedLine);
    editor.setPosition({ lineNumber: boundedLine, column: 1 });
    editor.focus();
  }, [navigationTarget, editorMountSeq]);

  return (
    <Editor
      height="100%"
      language={language}
      theme="edgemind-dark"
      value={value}
      beforeMount={handleBeforeMount}
      onMount={handleMount}
      onChange={(nextValue) => onChange(nextValue ?? '')}
      options={{
        minimap: { enabled: minimap },
        fontSize,
        lineHeight: Math.round(fontSize * 1.54),
        fontFamily: "'JetBrains Mono', 'Geist Mono', Menlo, Monaco, Consolas, monospace",
        scrollBeyondLastLine: false,
        automaticLayout: true,
        tabSize,
        insertSpaces: true,
        wordWrap,
        lineNumbers,
        glyphMargin: true,
        renderLineHighlight: 'line',
        padding: { top: 12, bottom: 12 },
        overviewRulerLanes: 2,
      }}
    />
  );
};

export default MonacoEditorAdapter;
