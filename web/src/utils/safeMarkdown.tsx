import React from 'react';

function isSafeHttpUrl(url: string): boolean {
  try {
    const parsed = new URL(url.trim());
    return parsed.protocol === 'http:' || parsed.protocol === 'https:';
  } catch {
    return false;
  }
}

function renderInlineNodes(text: string, keyPrefix: string): React.ReactNode[] {
  const nodes: React.ReactNode[] = [];
  const tokenRegex = /(`[^`]+`|\*\*[^*]+\*\*|\*[^*]+\*|\[[^\]]+\]\([^)]+\))/g;

  let lastIdx = 0;
  let match: RegExpExecArray | null;
  let tokenIdx = 0;

  while ((match = tokenRegex.exec(text)) !== null) {
    if (match.index > lastIdx) {
      nodes.push(text.slice(lastIdx, match.index));
    }

    const token = match[0];
    const key = `${keyPrefix}-${tokenIdx++}`;

    if (token.startsWith('`') && token.endsWith('`')) {
      nodes.push(
        <code
          key={key}
          className="px-1 py-0.5 rounded bg-em-overlay text-em-accent-primary font-mono text-[11px]"
        >
          {token.slice(1, -1)}
        </code>
      );
    } else if (token.startsWith('**') && token.endsWith('**')) {
      nodes.push(
        <strong key={key} className="font-semibold text-em-text-primary">
          {token.slice(2, -2)}
        </strong>
      );
    } else if (token.startsWith('*') && token.endsWith('*')) {
      nodes.push(
        <em key={key} className="italic text-em-text-secondary">
          {token.slice(1, -1)}
        </em>
      );
    } else if (token.startsWith('[')) {
      const linkParts = token.match(/^\[([^\]]+)\]\(([^)]+)\)$/);
      if (linkParts) {
        const [, label, href] = linkParts;
        if (isSafeHttpUrl(href)) {
          nodes.push(
            <a
              key={key}
              href={href}
              target="_blank"
              rel="noopener noreferrer"
              className="text-em-accent-primary underline hover:text-em-accent-hover"
            >
              {label}
            </a>
          );
        } else {
          nodes.push(label);
        }
      } else {
        nodes.push(token);
      }
    }

    lastIdx = match.index + token.length;
  }

  if (lastIdx < text.length) {
    nodes.push(text.slice(lastIdx));
  }

  return nodes.length > 0 ? nodes : [text];
}

export interface SafeMarkdownProps {
  content: string;
}

/**
 * Pure-React streaming Markdown renderer.
 * Avoids dangerouslySetInnerHTML entirely while supporting headings, fenced
 * code blocks (including incomplete trailing blocks during SSE streaming),
 * ordered/unordered lists, blockquotes, horizontal rules, inline code,
 * emphasis, and validated http/https links.
 */
export const SafeMarkdown: React.FC<SafeMarkdownProps> = ({ content }) => {
  if (!content) return null;

  const lines = content.split('\n');
  const elements: React.ReactNode[] = [];

  let paragraphLines: string[] = [];
  let listItems: string[] = [];
  let listType: 'ul' | 'ol' | null = null;
  let inCodeBlock = false;
  let codeLang = '';
  let codeLines: string[] = [];
  let blockKey = 0;

  const flushParagraph = () => {
    if (paragraphLines.length === 0) return;
    const text = paragraphLines.join(' ').trim();
    paragraphLines = [];
    if (!text) return;
    const key = `p-${blockKey++}`;
    elements.push(
      <p key={key} className="text-xs text-em-text-secondary leading-relaxed">
        {renderInlineNodes(text, key)}
      </p>
    );
  };

  const flushList = () => {
    if (listItems.length === 0 || !listType) return;
    const key = `list-${blockKey++}`;
    const Tag = listType;
    elements.push(
      <Tag
        key={key}
        className={
          listType === 'ul'
            ? 'list-disc pl-4 space-y-1 text-xs text-em-text-secondary leading-relaxed'
            : 'list-decimal pl-4 space-y-1 text-xs text-em-text-secondary leading-relaxed'
        }
      >
        {listItems.map((item, idx) => (
          <li key={`${key}-li-${idx}`}>{renderInlineNodes(item, `${key}-li-${idx}`)}</li>
        ))}
      </Tag>
    );
    listItems = [];
    listType = null;
  };

  const flushCodeBlock = () => {
    const key = `code-${blockKey++}`;
    elements.push(
      <div
        key={key}
        className="rounded-md border border-em-border-default bg-em-canvas overflow-x-auto"
      >
        {codeLang && (
          <div className="px-3 py-1 border-b border-em-border-hairline text-[10px] font-mono uppercase text-em-text-dim">
            {codeLang}
          </div>
        )}
        <pre className="p-3 text-[11px] font-mono text-em-text-primary leading-relaxed overflow-x-auto">
          <code>{codeLines.join('\n')}</code>
        </pre>
      </div>
    );
    codeLines = [];
    codeLang = '';
    inCodeBlock = false;
  };

  for (const rawLine of lines) {
    const trimmed = rawLine.trim();

    if (trimmed.startsWith('```')) {
      if (!inCodeBlock) {
        flushParagraph();
        flushList();
        inCodeBlock = true;
        codeLang = trimmed.slice(3).trim();
        codeLines = [];
      } else {
        flushCodeBlock();
      }
      continue;
    }

    if (inCodeBlock) {
      codeLines.push(rawLine);
      continue;
    }

    if (!trimmed) {
      flushParagraph();
      flushList();
      continue;
    }

    if (/^([-*_]){3,}$/.test(trimmed)) {
      flushParagraph();
      flushList();
      elements.push(<hr key={`hr-${blockKey++}`} className="border-em-border-hairline" />);
      continue;
    }

    const headingMatch = trimmed.match(/^(#{1,6})\s+(.+)$/);
    if (headingMatch) {
      flushParagraph();
      flushList();
      const level = headingMatch[1].length;
      const title = headingMatch[2];
      const key = `h-${blockKey++}`;
      const sizeClass =
        level <= 2
          ? 'text-xs font-semibold text-em-text-primary pt-1'
          : 'text-[11px] font-semibold uppercase tracking-wider text-em-accent-primary pt-1.5';
      elements.push(
        <div key={key} role="heading" aria-level={Math.min(6, level + 2)} className={sizeClass}>
          {renderInlineNodes(title, key)}
        </div>
      );
      continue;
    }

    const quoteMatch = trimmed.match(/^>\s*(.*)$/);
    if (quoteMatch) {
      flushParagraph();
      flushList();
      const key = `q-${blockKey++}`;
      elements.push(
        <blockquote
          key={key}
          className="border-l-2 border-em-accent-primary/40 pl-3 text-xs text-em-text-muted italic leading-relaxed"
        >
          {renderInlineNodes(quoteMatch[1], key)}
        </blockquote>
      );
      continue;
    }

    const ulMatch = trimmed.match(/^[-*]\s+(.+)$/);
    if (ulMatch) {
      flushParagraph();
      if (listType !== 'ul') {
        flushList();
        listType = 'ul';
      }
      listItems.push(ulMatch[1]);
      continue;
    }

    const olMatch = trimmed.match(/^\d+\.\s+(.+)$/);
    if (olMatch) {
      flushParagraph();
      if (listType !== 'ol') {
        flushList();
        listType = 'ol';
      }
      listItems.push(olMatch[1]);
      continue;
    }

    flushList();
    paragraphLines.push(trimmed);
  }

  if (inCodeBlock) {
    flushCodeBlock();
  }
  flushParagraph();
  flushList();

  return <div className="space-y-2.5">{elements}</div>;
};
