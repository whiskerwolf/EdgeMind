import React from 'react';
import { Code2, Layout } from 'lucide-react';
import {
  AppSettings,
  EditorLineNumbersMode,
  EditorWordWrapMode,
  SETTINGS_LIMITS,
  SidebarDefaultMode,
} from '../../utils/settingsConfig';
import { Badge } from '../ui/Badge';

export interface GeneralEditorSectionProps {
  settings: AppSettings;
  onUpdateImmediate: (partial: Partial<AppSettings>) => void;
}

const SELECT_CLASS =
  'w-full h-9 px-2.5 rounded-md border border-em-border-default bg-em-workspace text-xs font-mono text-em-text-primary focus:outline-none focus:border-em-accent-primary focus:ring-1 focus:ring-em-accent-primary';

export const GeneralEditorSection: React.FC<GeneralEditorSectionProps> = ({
  settings,
  onUpdateImmediate,
}) => {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
      {/* GENERAL & INTERFACE */}
      <section
        aria-labelledby="settings-general-heading"
        className="lg:col-span-5 rounded-lg border border-em-border-default bg-em-card p-4 space-y-4"
      >
        <div className="flex flex-wrap items-center justify-between gap-2 pb-2.5 border-b border-em-border-hairline">
          <div className="flex items-center gap-2">
            <Layout className="w-4 h-4 text-em-accent-primary" />
            <h3
              id="settings-general-heading"
              className="text-xs font-semibold uppercase tracking-wider text-em-text-secondary"
            >
              General &amp; Interface
            </h3>
          </div>
          <Badge variant="info" size="sm">
            Applies Immediately
          </Badge>
        </div>

        <div className="space-y-3">
          <div className="space-y-1.5">
            <label
              htmlFor="settings-sidebar-mode"
              className="block text-[11px] font-mono uppercase tracking-wider text-em-text-dim"
            >
              Navigation Sidebar Mode
            </label>
            <select
              id="settings-sidebar-mode"
              value={settings.sidebarDefaultMode}
              onChange={(e) =>
                onUpdateImmediate({ sidebarDefaultMode: e.target.value as SidebarDefaultMode })
              }
              className={SELECT_CLASS}
            >
              <option value="auto">Auto (Collapsed on Tablet, Expanded on Desktop)</option>
              <option value="expanded">Always Expanded (240px)</option>
              <option value="collapsed">Compact Icon Rail (64px)</option>
            </select>
            <p className="text-[11px] text-em-text-muted">
              Controls desktop/tablet sidebar rail behavior across all dashboard routes.
            </p>
          </div>

          <div className="rounded-md border border-em-border-default bg-em-workspace p-3 space-y-1 text-xs">
            <div className="flex items-center justify-between">
              <span className="font-medium text-em-text-secondary">Interface Theme</span>
              <span className="font-mono text-em-text-primary">Obsidian Dark</span>
            </div>
            <p className="text-[11px] text-em-text-muted">
              EdgeMind is engineered exclusively for low-glare dark developer workspaces. Light
              theme switching is not supported.
            </p>
          </div>
        </div>
      </section>

      {/* WORKSPACE & EDITOR */}
      <section
        aria-labelledby="settings-editor-heading"
        className="lg:col-span-7 rounded-lg border border-em-border-default bg-em-card p-4 space-y-4"
      >
        <div className="flex flex-wrap items-center justify-between gap-2 pb-2.5 border-b border-em-border-hairline">
          <div className="flex items-center gap-2">
            <Code2 className="w-4 h-4 text-em-accent-primary" />
            <h3
              id="settings-editor-heading"
              className="text-xs font-semibold uppercase tracking-wider text-em-text-secondary"
            >
              Workspace &amp; Editor
            </h3>
          </div>
          <Badge variant="info" size="sm">
            Applies Immediately
          </Badge>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div className="space-y-1.5">
            <label
              htmlFor="settings-editor-font-size"
              className="block text-[11px] font-mono uppercase tracking-wider text-em-text-dim"
            >
              Editor Font Size
            </label>
            <select
              id="settings-editor-font-size"
              value={settings.editorFontSize}
              onChange={(e) =>
                onUpdateImmediate({ editorFontSize: Number(e.target.value) })
              }
              className={SELECT_CLASS}
            >
              {SETTINGS_LIMITS.editorFontSizes.map((sz) => (
                <option key={sz} value={sz}>
                  {sz}px (JetBrains Mono)
                </option>
              ))}
            </select>
          </div>

          <div className="space-y-1.5">
            <label
              htmlFor="settings-editor-tab-size"
              className="block text-[11px] font-mono uppercase tracking-wider text-em-text-dim"
            >
              Indentation Width
            </label>
            <select
              id="settings-editor-tab-size"
              value={settings.editorTabSize}
              onChange={(e) =>
                onUpdateImmediate({ editorTabSize: Number(e.target.value) as 2 | 4 })
              }
              className={SELECT_CLASS}
            >
              <option value={4}>4 spaces (PEP 8 Default)</option>
              <option value={2}>2 spaces</option>
            </select>
          </div>

          <div className="space-y-1.5">
            <label
              htmlFor="settings-editor-word-wrap"
              className="block text-[11px] font-mono uppercase tracking-wider text-em-text-dim"
            >
              Word Wrap
            </label>
            <select
              id="settings-editor-word-wrap"
              value={settings.editorWordWrap}
              onChange={(e) =>
                onUpdateImmediate({ editorWordWrap: e.target.value as EditorWordWrapMode })
              }
              className={SELECT_CLASS}
            >
              <option value="off">Off (Horizontal Scroll)</option>
              <option value="on">On (Wrap Long Lines)</option>
            </select>
          </div>

          <div className="space-y-1.5">
            <label
              htmlFor="settings-editor-line-numbers"
              className="block text-[11px] font-mono uppercase tracking-wider text-em-text-dim"
            >
              Gutter Line Numbers
            </label>
            <select
              id="settings-editor-line-numbers"
              value={settings.editorLineNumbers}
              onChange={(e) =>
                onUpdateImmediate({ editorLineNumbers: e.target.value as EditorLineNumbersMode })
              }
              className={SELECT_CLASS}
            >
              <option value="on">Shown</option>
              <option value="off">Hidden</option>
            </select>
          </div>
        </div>

        <label className="flex items-center justify-between gap-3 rounded-md border border-em-border-default bg-em-workspace px-3 py-2.5 cursor-pointer">
          <div>
            <span className="text-xs font-medium text-em-text-primary block">
              Show Monaco Minimap
            </span>
            <span className="text-[11px] text-em-text-muted">
              Displays a condensed code overview scrollbar in desktop Monaco Workspace view.
            </span>
          </div>
          <input
            type="checkbox"
            aria-label="Show Monaco Minimap"
            checked={settings.editorMinimap}
            onChange={(e) => onUpdateImmediate({ editorMinimap: e.target.checked })}
            className="h-4 w-4 rounded border-em-border-strong bg-em-card text-em-accent-primary focus:ring-em-accent-primary"
          />
        </label>
      </section>
    </div>
  );
};
