/**
 * Safe, zero-dependency Markdown-to-HTML formatter for EdgeMind AI Diagnosis.
 *
 * Security Invariants:
 * 1. Strictly neutralizes all input HTML characters (&, <, >, ", ') BEFORE parsing.
 * 2. Only permits http: and https: protocols in markdown links (rejects javascript:, data:, vbscript:).
 * 3. Never renders raw unescaped HTML or allows script execution.
 * 4. Preserves fenced code blocks with language classes and inline code.
 * 5. Handles headings (###, ##, #), lists (- and 1.), bold (**), and italics (*).
 */

export function escapeHtml(str: unknown): string {
  if (str === null || str === undefined) {
    return '';
  }
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

export function isSafeUrl(url: string): boolean {
  if (!url || typeof url !== 'string') {
    return false;
  }
  const trimmed = url.trim();
  try {
    const parsed = new URL(trimmed);
    return parsed.protocol === 'http:' || parsed.protocol === 'https:';
  } catch {
    return false;
  }
}

export function renderSafeMarkdown(markdown: string): string {
  if (!markdown || typeof markdown !== 'string') {
    return '';
  }

  // First pass: extract fenced code blocks before line-by-line processing
  const codeBlocks: string[] = [];
  const placeholder = '___CODEBLOCK_';

  // Match closed code blocks: ```lang\n ... ```
  let sanitized = markdown.replace(/```([a-zA-Z0-9_-]*)\n([\s\S]*?)```/g, (_match, lang, code) => {
    const idx = codeBlocks.length;
    const escapedCode = escapeHtml(code.trimEnd());
    const langClass = lang ? ` class="language-${escapeHtml(lang)}"` : '';
    codeBlocks.push(`<pre><code${langClass}>${escapedCode}</code></pre>`);
    return `${placeholder}${idx}___\n`;
  });

  // Handle unclosed code block while streaming: ```lang\n ... (EOF)
  sanitized = sanitized.replace(/```([a-zA-Z0-9_-]*)\n([\s\S]*)$/g, (_match, lang, code) => {
    const idx = codeBlocks.length;
    const escapedCode = escapeHtml(code.trimEnd());
    const langClass = lang ? ` class="language-${escapeHtml(lang)}"` : '';
    codeBlocks.push(`<pre><code${langClass}>${escapedCode}</code></pre>`);
    return `${placeholder}${idx}___\n`;
  });

  // Split into lines for block-level parsing
  const rawLines = sanitized.split('\n');
  const resultBlocks: string[] = [];
  let inList = false;
  let listType: 'ul' | 'ol' = 'ul';
  let currentParagraph: string[] = [];

  const flushParagraph = () => {
    if (currentParagraph.length > 0) {
      const text = currentParagraph.join(' ').trim();
      if (text) {
        resultBlocks.push(`<p>${formatInline(text)}</p>`);
      }
      currentParagraph = [];
    }
  };

  const flushList = () => {
    if (inList) {
      resultBlocks.push(listType === 'ul' ? '</ul>' : '</ol>');
      inList = false;
    }
  };

  for (const rawLine of rawLines) {
    const trimmed = rawLine.trim();

    // Check codeblock placeholder
    const placeholderMatch = trimmed.match(/^___CODEBLOCK_(\d+)___$/);
    if (placeholderMatch) {
      flushParagraph();
      flushList();
      const codeIdx = parseInt(placeholderMatch[1], 10);
      if (codeBlocks[codeIdx] !== undefined) {
        resultBlocks.push(codeBlocks[codeIdx]);
      }
      continue;
    }

    if (!trimmed) {
      flushParagraph();
      flushList();
      continue;
    }

    // Horizontal rule: --- or *** or ___
    if (/^([-*_]){3,}$/.test(trimmed)) {
      flushParagraph();
      flushList();
      resultBlocks.push('<hr class="diag-hr" />');
      continue;
    }

    // Blockquote: > text
    const quoteMatch = trimmed.match(/^>\s*(.*)$/);
    if (quoteMatch) {
      flushParagraph();
      flushList();
      const content = formatInline(quoteMatch[1]);
      resultBlocks.push(`<blockquote class="diag-quote">${content}</blockquote>`);
      continue;
    }

    // Headings: ###, ##, #
    const headingMatch = trimmed.match(/^(#{1,6})\s+(.+)$/);
    if (headingMatch) {
      flushParagraph();
      flushList();
      const level = Math.min(6, headingMatch[1].length);
      const title = formatInline(headingMatch[2]);
      resultBlocks.push(`<h${level} class="diag-heading h${level}">${title}</h${level}>`);
      continue;
    }

    // Unordered list item: - or *
    const ulMatch = trimmed.match(/^[-*]\s+(.+)$/);
    if (ulMatch) {
      flushParagraph();
      if (!inList || listType !== 'ul') {
        flushList();
        resultBlocks.push('<ul>');
        inList = true;
        listType = 'ul';
      }
      resultBlocks.push(`<li>${formatInline(ulMatch[1])}</li>`);
      continue;
    }

    // Ordered list item: 1.
    const olMatch = trimmed.match(/^\d+\.\s+(.+)$/);
    if (olMatch) {
      flushParagraph();
      if (!inList || listType !== 'ol') {
        flushList();
        resultBlocks.push('<ol>');
        inList = true;
        listType = 'ol';
      }
      resultBlocks.push(`<li>${formatInline(olMatch[1])}</li>`);
      continue;
    }

    // Regular line, accumulate into paragraph
    currentParagraph.push(trimmed);
  }

  flushParagraph();
  flushList();

  return resultBlocks.join('\n');
}

/**
 * Formats inline Markdown elements (code, bold, italics, links) safely.
 */
function formatInline(text: string): string {
  // First escape HTML so any raw characters are safe
  let escaped = escapeHtml(text);

  // Inline code: `code`
  escaped = escaped.replace(/`([^`]+)`/g, (_m, code) => `<code class="inline-code">${code}</code>`);

  // Bold: **text**
  escaped = escaped.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');

  // Italic: *text*
  escaped = escaped.replace(/\*([^*]+)\*/g, '<em>$1</em>');

  // Links: [text](url) - strictly checked for safe protocol
  escaped = escaped.replace(/\[([^\]]+)\]\(([^)]+)\)/g, (_m, linkText, url) => {
    const rawUrl = url.replace(/&amp;/g, '&');
    if (isSafeUrl(rawUrl)) {
      const safeHref = escapeHtml(rawUrl);
      return `<a href="${safeHref}" target="_blank" rel="noopener noreferrer">${linkText}</a>`;
    }
    // For disallowed URLs (e.g. javascript:, file:), render text only without anchor tag
    return linkText;
  });

  return escaped;
}
