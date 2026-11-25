/**
 * EdgeMind Multi-Platform Content Script.
 *
 * Runs on LeetCode, HackerRank, and Codeforces problem pages in an isolated world.
 * Automatically detects platform and extracts problem title, slug/id, URL,
 * description, constraints, input/output specifications, and public example inputs.
 *
 * Supports SPA navigation and dynamic DOM observation across all supported platforms.
 */
(() => {
  "use strict";

  // ============================================================================
  // 1. Platform Detection
  // ============================================================================
  const Platform = {
    LEETCODE: "leetcode",
    HACKERRANK: "hackerrank",
    CODEFORCES: "codeforces",
    UNKNOWN: "unknown"
  };

  function detectPlatform(url = (typeof window !== "undefined" && window.location ? window.location.href : ""), hostname = (typeof window !== "undefined" && window.location ? window.location.hostname : "")) {
    const host = (hostname || "").toLowerCase();
    const fullUrl = (url || "").toLowerCase();
    if (host.includes("leetcode.com") || fullUrl.includes("leetcode.com")) return Platform.LEETCODE;
    if (host.includes("hackerrank.com") || fullUrl.includes("hackerrank.com")) return Platform.HACKERRANK;
    if (host.includes("codeforces.com") || fullUrl.includes("codeforces.com")) return Platform.CODEFORCES;
    return Platform.UNKNOWN;
  }

  let lastUrl = typeof window !== "undefined" && window.location ? window.location.href : "";
  let cachedInfo = null;
  let debounceTimer = null;

  // ============================================================================
  // 2. Shared Normalization Utilities
  // ============================================================================

  function cleanInputString(raw) {
    if (!raw) return "";
    let cleaned = raw.split(/Output\s*:/i)[0];
    cleaned = cleaned.split(/Explanation\s*:/i)[0];
    cleaned = cleaned.replace(/^[\s\S]*?Input\s*:\s*/i, "").trim();

    const lines = cleaned
      .split(/\r?\n/)
      .map(l => l.trim())
      .filter(l => l.length > 0 && !l.toLowerCase().startsWith("output") && !l.toLowerCase().startsWith("explanation"));

    if (lines.length === 0) return "";
    if (lines.length > 1 && lines.every(l => l.includes("="))) {
      return lines.join(", ");
    }
    return lines.join(" ");
  }

  function normalizeLatex(str) {
    if (!str || typeof str !== "string") return "";
    let s = str.replace(/\$/g, "");
    // 0. Unescape HTML entities
    s = s.replace(/&le;|&leq;|&#8804;/gi, "<=");
    s = s.replace(/&ge;|&geq;|&#8805;/gi, ">=");
    s = s.replace(/&lt;|&#60;/gi, "<");
    s = s.replace(/&gt;|&#62;/gi, ">");
    s = s.replace(/&amp;/gi, "&");

    // 1. LaTeX operators
    s = s.replace(/\\le\b|\\leq\b/g, "<=");
    s = s.replace(/\\ge\b|\\geq\b/g, ">=");
    s = s.replace(/\\lt\b/g, "<");
    s = s.replace(/\\gt\b/g, ">");
    s = s.replace(/\\times\b|\\cdot\b/g, "*");
    s = s.replace(/\\ne\b|\\neq\b/g, "!=");

    // 2. LaTeX whitespace commands
    s = s.replace(/\\quad\b/g, " ");
    s = s.replace(/\\qquad\b/g, " ");
    s = s.replace(/\\[,;:! ]/g, " ");
    s = s.replace(/~/g, " ");

    // 3. LaTeX powers: e.g. 10^{9} -> 10^9, 2^{31} -> 2^31
    s = s.replace(/\^\{([+-]?\d+)\}/g, "^$1");

    // 4. Iteratively unwrap \text{...}, text{...}, \mathbf{...}, \math...{...}
    const wrapperPattern = /\\?(?:text|textbf|textit|mathrm|mathbf|mathit|mathtt|operatorname|math[a-zA-Z]*)\{([^{}]*)\}/g;
    for (let i = 0; i < 10; i++) {
      const prev = s;
      s = s.replace(wrapperPattern, "$1");
      if (prev === s) break;
    }

    // 5. Unicode inequality and minus characters
    s = s.replace(/≤|\u2264/g, "<=").replace(/≥|\u2265/g, ">=").replace(/−|\u2212/g, "-");

    // 6. Clean up excessive whitespace
    s = s.replace(/[ \t]+/g, " ").trim();
    return s;
  }

  function normalizeCollapsedExponents(str) {
    if (!str || typeof str !== "string") return "";
    let s = normalizeLatex(str);
    const unicodeMap = {
      "⁰": "0", "¹": "1", "²": "2", "³": "3", "⁴": "4",
      "⁵": "5", "⁶": "6", "⁷": "7", "⁸": "8", "⁹": "9",
      "⁺": "+", "⁻": "-"
    };
    s = s.replace(/[⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻]/g, ch => unicodeMap[ch] || ch);
    s = s.replace(/−/g, "-").replace(/≤|\u2264/g, " <= ").replace(/≥|\u2265/g, " >= ");
    // Restore collapsed exponents from scrapers or flattened DOM: e.g. -109 -> -10^9, 104 -> 10^4
    s = s.replace(/(^|[<>=,\s([-])231\b/g, "$12^31");
    s = s.replace(/(^|[<>=,\s([-])10([3-9])\b/g, "$110^$2");
    s = s.replace(/[ \t]+/g, " ").trim();
    return s;
  }

  function extractTextWithSuperscripts(element) {
    if (!element) return "";
    try {
      if (element.matches && element.matches("script[type*='math/tex'], script[type*='latex']")) {
        return normalizeCollapsedExponents(normalizeLatex(element.textContent || ""));
      }

      const clone = element.cloneNode ? element.cloneNode(true) : element;

      // 1. Process all KaTeX elements
      const katexEls = [];
      if (clone.matches && clone.matches(".katex, [data-katex]")) katexEls.push(clone);
      if (clone.querySelectorAll) {
        clone.querySelectorAll(".katex, [data-katex]").forEach(k => katexEls.push(k));
      }
      katexEls.forEach(k => {
        const ann = k.querySelector ? k.querySelector("annotation") : null;
        if (ann && ann.textContent && ann.textContent.trim()) {
          let rawTex = ann.textContent.trim();
          rawTex = normalizeLatex(rawTex);
          k.textContent = " " + rawTex + " ";
          return;
        }

        const mathml = k.querySelector ? k.querySelector(".katex-mathml, math") : null;
        const katexHtml = k.querySelector ? k.querySelector(".katex-html") : null;

        if (katexHtml) {
          if (mathml && mathml.remove) mathml.remove();

          const msupsubs = katexHtml.querySelectorAll ? katexHtml.querySelectorAll(".msupsub") : [];
          msupsubs.forEach(sub => {
            const expText = (sub.textContent || "").trim();
            if (expText && !expText.startsWith("^")) {
              sub.textContent = "^" + expText;
            }
          });

          const mrels = katexHtml.querySelectorAll ? katexHtml.querySelectorAll(".mrel") : [];
          mrels.forEach(rel => {
            const relText = (rel.textContent || "").trim();
            if (relText === "≤" || relText === "\u2264") {
              rel.textContent = " <= ";
            } else if (relText === "≥" || relText === "\u2265") {
              rel.textContent = " >= ";
            }
          });

          k.textContent = " " + (katexHtml.textContent || "").trim() + " ";
          return;
        }

        if (mathml) {
          const msups = mathml.querySelectorAll ? mathml.querySelectorAll("msup") : [];
          msups.forEach(msup => {
            const children = Array.from(msup.children || []).filter(c => (c.textContent || "").trim());
            if (children.length >= 2) {
              const base = (children[0].textContent || "").trim();
              const exp = (children[1].textContent || "").trim();
              msup.textContent = base + "^" + exp;
            }
          });
          const mos = mathml.querySelectorAll ? mathml.querySelectorAll("mo") : [];
          mos.forEach(mo => {
            const t = (mo.textContent || "").trim();
            if (t === "≤" || t === "\u2264") mo.textContent = " <= ";
            else if (t === "≥" || t === "\u2265") mo.textContent = " >= ";
          });
          k.textContent = " " + (mathml.textContent || "").trim() + " ";
          return;
        }
      });

      // 2. Process standard HTML <sup> elements and MathJax superscripts
      if (clone.querySelectorAll) {
        clone.querySelectorAll("sup, mjx-sup, .mjx-sup").forEach(sup => {
          const supText = (sup.textContent || "").trim();
          if (supText && !supText.startsWith("^")) {
            sup.textContent = "^" + supText;
          }
        });
      }

      // 3. Clean up MathJax preview elements
      if (clone.querySelectorAll) {
        clone.querySelectorAll(".MathJax_Preview").forEach(p => {
          if (p.remove) p.remove();
        });
      }

      // 4. Process TeX script tags (MathJax 2 / Codeforces)
      const texScripts = [];
      if (clone.matches && clone.matches("script[type*='math/tex'], script[type*='latex']")) {
        texScripts.push(clone);
      }
      if (clone.querySelectorAll) {
        clone.querySelectorAll("script[type*='math/tex'], script[type*='latex']").forEach(s => texScripts.push(s));
      }
      texScripts.forEach(script => {
        const tex = normalizeLatex((script.textContent || "").trim());
        // Remove preceding visual .MathJax frame if present to avoid duplicating formula text
        if (script.previousElementSibling && script.previousElementSibling.matches && script.previousElementSibling.matches(".MathJax, .MathJax_Display")) {
          if (script.previousElementSibling.remove) script.previousElementSibling.remove();
        }
        if (tex) {
          const textNode = document.createTextNode ? document.createTextNode(" " + tex + " ") : { textContent: " " + tex + " " };
          if (script.parentNode) script.parentNode.replaceChild(textNode, script);
        }
      });

      // 5. Process remaining MathJax elements & containers (MathJax 3 / standalone MathJax 2)
      const mjxContainers = [];
      if (clone.matches && clone.matches("mjx-container, .MathJax, .MathJax_Display, [jax]")) {
        mjxContainers.push(clone);
      }
      if (clone.querySelectorAll) {
        clone.querySelectorAll("mjx-container, .MathJax, .MathJax_Display, [jax]").forEach(el => mjxContainers.push(el));
      }

      mjxContainers.forEach(mc => {
        // A. Extract aria-label or data-tex from container or inner glyph/math/svg element
        let label = (mc.getAttribute && (mc.getAttribute("aria-label") || mc.getAttribute("data-tex") || mc.getAttribute("data-latex"))) || "";
        if (!label && mc.querySelector) {
          const innerLabeled = mc.querySelector("[aria-label], [data-tex], [data-latex], svg[aria-label], mjx-math[aria-label]");
          if (innerLabeled && innerLabeled.getAttribute) {
            label = innerLabeled.getAttribute("aria-label") || innerLabeled.getAttribute("data-tex") || innerLabeled.getAttribute("data-latex") || "";
          }
        }
        if (label && label.trim()) {
          mc.textContent = " " + normalizeLatex(label) + " ";
          return;
        }

        // B. Extract from assistive MathML or MathML annotation
        const mathml = mc.querySelector ? mc.querySelector("math, mjx-assistive-mml") : null;
        if (mathml) {
          const ann = mathml.querySelector ? mathml.querySelector("annotation") : null;
          if (ann && ann.textContent && ann.textContent.trim()) {
            mc.textContent = " " + normalizeLatex(ann.textContent) + " ";
            return;
          }
          const mos = mathml.querySelectorAll ? mathml.querySelectorAll("mo") : [];
          mos.forEach(mo => {
            const t = (mo.textContent || "").trim();
            if (t === "≤" || t === "\u2264" || t === "<=" || t === "&le;" || t === "&leq;") mo.textContent = " <= ";
            else if (t === "≥" || t === "\u2265" || t === ">=" || t === "&ge;" || t === "&geq;") mo.textContent = " >= ";
            else if (t === "&lt;") mo.textContent = " < ";
            else if (t === "&gt;") mo.textContent = " > ";
          });
          const mText = (mathml.textContent || "").trim();
          if (mText) {
            mc.textContent = " " + normalizeLatex(mText) + " ";
            return;
          }
        }

        // C. Clean up decorative visual glyphs if present
        if (mc.querySelectorAll) {
          mc.querySelectorAll("mjx-math[aria-hidden='true']").forEach(hidden => {
            if (hidden.remove) hidden.remove();
          });
        }
      });

      let text = (clone.textContent || "").trim();
      return normalizeCollapsedExponents(text);
    } catch {
      return normalizeCollapsedExponents((element.textContent || "").trim());
    }
  }

  function isValidProblemTitle(t) {
    if (!t || typeof t !== "string") return false;
    const trimmed = t.trim();
    if (trimmed.length < 2 || trimmed.length > 150) return false;
    if (!/[a-zA-Z]{2,}/.test(trimmed)) return false;
    if (trimmed === "-" || trimmed === "—" || trimmed === "–") return false;
    if (trimmed.toLowerCase().includes("leetcode") && !trimmed.includes(" ")) return false;
    return true;
  }

  // ============================================================================
  // 3. Platform Adapters
  // ============================================================================

  /**
   * LeetCode Adapter.
   */
  const LeetCodeAdapter = {
    platform: Platform.LEETCODE,

    isProblemPage(url = window.location.href, pathname = window.location.pathname) {
      return pathname.includes("/problems/");
    },

    extract() {
      const pathname = window.location.pathname || "";
      const isProblemPage = this.isProblemPage(window.location.href, pathname);

      // 1. Problem ID / Slug from URL
      let problemId = "";
      const match = pathname.match(/\/problems\/([^/]+)/);
      if (match && match[1]) {
        problemId = match[1];
      }

      // 2. Problem Title with robust validation
      let title = "";
      const titleSelectors = [
        "div[data-cy='question-title']",
        "h1[data-cy='question-title']",
        "h1.text-title-large",
        ".text-title-large",
        "[data-track-load='description_content'] h1",
        "[data-track-load='description_content'] h4",
        "div.flex.items-start.gap-2 h1",
        "div.flex.items-start h1",
        "h1"
      ];

      for (const sel of titleSelectors) {
        const el = document.querySelector(sel);
        if (el) {
          const text = (el.textContent || "").trim();
          if (isValidProblemTitle(text)) {
            title = text;
            break;
          }
        }
      }

      if (!isValidProblemTitle(title) && document.title) {
        const docClean = document.title.replace(/\s*-\s*LeetCode.*$/i, "").trim();
        if (isValidProblemTitle(docClean)) {
          title = docClean;
        }
      }

      if (!isValidProblemTitle(title) && problemId) {
        title = problemId.split("-").map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(" ");
      }

      if (!isValidProblemTitle(title)) {
        title = problemId.toLowerCase().includes("two-sum") ? "Two Sum" : "LeetCode Problem";
      }

      // 3. Problem Description
      let description = "";
      const descEl = document.querySelector(
        "[data-track-load='description_content'], .elfjS, div[class*='description'], div[class*='question-content']"
      );
      if (descEl) {
        description = (descEl.innerText || descEl.textContent || "").trim();
      }

      // 4. Active Editor Language from DOM dropdown
      let detectedLanguage = "unknown";
      const langSelectors = [
        "button[id*='headlessui-listbox-button']",
        "button[data-cy='lang-select']",
        "div[class*='lang-select'] button",
        "[data-track-load='code_editor'] button"
      ];
      for (const selector of langSelectors) {
        const elements = document.querySelectorAll(selector);
        for (const el of elements) {
          const text = (el.textContent || "").trim();
          if (text) {
            const low = text.toLowerCase();
            if (low.includes("python3") || low === "python3") {
              detectedLanguage = "Python3";
              break;
            } else if (low.includes("python") || low === "python") {
              detectedLanguage = "Python";
              break;
            } else if (["c++", "java", "c", "c#", "javascript", "typescript", "go", "rust", "ruby", "swift", "kotlin"].some(l => low === l || low.includes(l))) {
              detectedLanguage = text.split("\n")[0].trim();
              break;
            }
          }
        }
        if (detectedLanguage !== "unknown") break;
      }

      // 5. Constraints
      const constraints = [];
      const constraintHeaders = Array.from(
        document.querySelectorAll("h1, h2, h3, h4, h5, h6, p, strong, b, em, div, span")
      ).filter(el => {
        const t = (el.textContent || "").trim().toLowerCase();
        if (/^constraints:?$/i.test(t) || t.startsWith("constraints")) {
          if (el.querySelector && el.querySelector("strong, b, em, span, h1, h2, h3, h4, h5, h6")) return false;
          return true;
        }
        return false;
      });

      if (constraintHeaders.length > 0) {
        const header = constraintHeaders[0];
        const candidates = [
          header.nextElementSibling,
          header.parentElement ? header.parentElement.nextElementSibling : null,
          header.parentElement && header.parentElement.parentElement ? header.parentElement.parentElement.nextElementSibling : null
        ];
        if (header.closest) {
          const container = header.closest("div, section, article");
          if (container) {
            const list = container.querySelector("ul, ol");
            if (list && !candidates.includes(list)) candidates.push(list);
          }
        }
        for (let nextEl of candidates) {
          while (nextEl && (nextEl.tagName === "UL" || nextEl.tagName === "OL" || nextEl.tagName === "DIV")) {
            const items = nextEl.querySelectorAll("li, p");
            if (items.length > 0) {
              items.forEach(li => {
                const text = extractTextWithSuperscripts(li);
                if (text && text.length < 250 && !constraints.includes(text)) constraints.push(text);
              });
              break;
            }
            nextEl = nextEl.nextElementSibling;
          }
          if (constraints.length > 0) break;
        }
      }

      if (constraints.length === 0) {
        const allLis = document.querySelectorAll(
          "[data-track-load='description_content'] ul li, .elfjS ul li, div[class*='description'] ul li, div[class*='question-content'] ul li"
        );
        allLis.forEach(li => {
          const text = extractTextWithSuperscripts(li);
          if (text && text.length < 250 && !constraints.includes(text)) {
            const low = text.toLowerCase();
            const hasInequality = text.includes("<=") || text.includes(">=") || text.includes("≤") || text.includes("≥") || text.includes("10^") || text.includes("2^") || /\d+\s*<|\b\d+\s*<=/.test(text);
            const hasConstraintWord = low.includes("only one") || low.includes("valid answer") || low.includes("length") || low.includes("nums") || low.includes("integer") || low.includes("array") || low.includes("strictly");
            if (hasInequality || hasConstraintWord) {
              constraints.push(text);
            }
          }
        });
      }

      // 6. Public Examples
      const sampleInputs = [];
      const containerSelectors = [
        ".example-block",
        "div[class*='example-block']",
        "div[class*='example_block']",
        "[data-track-load='description_content'] pre",
        ".elfjS pre",
        "div[data-track-load] pre",
        "pre",
        "div[class*='example']"
      ];
      const blocks = Array.from(document.querySelectorAll(containerSelectors.join(", ")));

      const exampleHeadings = Array.from(
        document.querySelectorAll("strong, b, p, h4, h3, div")
      ).filter(el => {
        const t = (el.textContent || "").trim();
        return /^example\s*\d+\s*:/i.test(t);
      });

      exampleHeadings.forEach(heading => {
        let sibling = heading.nextElementSibling;
        if (sibling && !blocks.includes(sibling)) {
          blocks.push(sibling);
        } else if (heading.parentElement && !blocks.includes(heading.parentElement)) {
          const parentSibling = heading.parentElement.nextElementSibling;
          if (parentSibling && !blocks.includes(parentSibling)) {
            blocks.push(parentSibling);
          }
        }
      });

      for (const block of blocks) {
        if (!block) continue;
        let extracted = "";

        const inputElements = typeof block.querySelectorAll === "function"
          ? Array.from(block.querySelectorAll("p, div, li")).filter(el => {
              const t = (el.textContent || "").trim();
              return /Input\s*:/i.test(t);
            })
          : [];

        for (const el of inputElements) {
          const codeTags = el.querySelectorAll("code");
          if (codeTags.length > 0) {
            const codeTexts = Array.from(codeTags).map(c => (c.textContent || "").trim()).filter(Boolean);
            if (codeTexts.length > 0) {
              extracted = codeTexts.join(", ");
              break;
            }
          }
          const text = el.textContent || "";
          if (/Input\s*:/i.test(text)) {
            extracted = cleanInputString(text);
            if (extracted) break;
          }
        }

        if (!extracted) {
          const blockText = (typeof block.innerText === "string" ? block.innerText : block.textContent) || "";
          const match = blockText.match(/(?:^|\b)Input\s*:\s*([\s\S]*?)(?=(?:Output\s*:|Explanation\s*:|$))/i);
          if (match && match[1]) {
            extracted = cleanInputString(match[1]);
          }
        }

        if (extracted && !sampleInputs.includes(extracted)) {
          sampleInputs.push(extracted);
        }
      }

      if (sampleInputs.length === 0) {
        const descContainer = document.querySelector(
          "[data-track-load='description_content'], .elfjS, div[class*='description'], div[class*='question-content']"
        ) || document.body;
        if (descContainer) {
          const descText = (typeof descContainer.innerText === "string" ? descContainer.innerText : descContainer.textContent) || "";
          const globalRegex = /(?:^|\b)Input\s*:\s*([\s\S]*?)(?=(?:Output\s*:|Explanation\s*:|\n\s*\n|$))/gi;
          let gMatch;
          while ((gMatch = globalRegex.exec(descText)) !== null) {
            const clean = cleanInputString(gMatch[1]);
            if (clean && !sampleInputs.includes(clean)) {
              sampleInputs.push(clean);
            }
          }
        }
      }

      return {
        platform: Platform.LEETCODE,
        isLeetCode: true,
        isProblemPage,
        title: title || "LeetCode Problem",
        problemId,
        url: window.location.href,
        description,
        language: detectedLanguage,
        constraints,
        sampleInputs,
        sampleOutputs: []
      };
    }
  };

  /**
   * Helper to clean HackerRank STDIN diagram/explanation blocks.
   * Strips headers (e.g. 'STDIN Function', '----- --------', 'ar[] size n = 6')
   * and preserves pure STDIN lines (e.g. '6\n1 2 3 4 10 11').
   */
  function cleanHackerRankSampleInput(raw) {
    if (!raw || typeof raw !== "string") return "";
    const isHrDiagram = /stdin\s+function/i.test(raw) || (/ar\[\]\s*size/i.test(raw) && /n\s*=/i.test(raw));
    if (!isHrDiagram) return raw.trim();

    const lines = raw.split(/\r?\n/).map(l => l.trim()).filter(Boolean);
    const stdinLines = [];

    for (const line of lines) {
      if (/^stdin\s+function/i.test(line)) continue;
      if (/^[-=\s]+$/.test(line)) continue;
      if (/^output/i.test(line) || /^explanation/i.test(line)) break;

      const assignMatch = line.match(/^([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*(\[[\s\S]*\])$/);
      if (assignMatch) continue;

      const colMatch = line.match(/^([0-9\s-]+?)(?:\s+[a-zA-Z_\[\]].*)$/);
      if (colMatch && colMatch[1].trim()) {
        stdinLines.push(colMatch[1].trim());
        continue;
      }

      if (/^[0-9\s-]+$/.test(line)) {
        stdinLines.push(line.trim());
        continue;
      }
    }

    return stdinLines.length > 0 ? stdinLines.join("\n") : raw.trim();
  }

  /**
   * HackerRank Adapter.
   */
  const HackerRankAdapter = {
    platform: Platform.HACKERRANK,

    isProblemPage(url = window.location.href, pathname = window.location.pathname) {
      return pathname.includes("/challenges/");
    },

    extract() {
      const pathname = window.location.pathname || "";
      const isProblemPage = this.isProblemPage(window.location.href, pathname);

      // 1. Problem ID / Slug from URL first to guide initialData search
      let problemId = "";
      const match = pathname.match(/\/challenges\/([^/]+)/);
      if (match && match[1]) {
        problemId = match[1];
      }

      // 0. Check authoritative initialData script if present on page
      let hrInitialDetail = null;
      try {
        function robustDecodeUri(str) {
          if (!str || typeof str !== "string") return "";
          try { return decodeURIComponent(str); } catch {}
          try { return decodeURIComponent(str.replace(/%(?![0-9a-fA-F]{2})/g, "%25")); } catch {}
          try { return unescape(str); } catch {}
          try { return decodeURI(str); } catch {}
          return "";
        }

        function findChallengeDetailInObject(obj, targetSlug) {
          if (!obj || typeof obj !== "object") return null;
          if (obj.constraints && typeof obj.constraints === "string") {
            if (!targetSlug || obj.slug === targetSlug || (obj.slug && targetSlug.includes(obj.slug)) || (obj.name && targetSlug.includes(obj.slug))) {
              return obj;
            }
          }
          for (const k of Object.keys(obj)) {
            try {
              const res = findChallengeDetailInObject(obj[k], targetSlug);
              if (res) return res;
            } catch {}
          }
          return null;
        }

        const candidateEls = [];
        const directEl = document.getElementById("initialData") || (document.querySelector && document.querySelector("script#initialData, script[id='initialData'], #initialData"));
        if (directEl) candidateEls.push(directEl);

        if (candidateEls.length === 0 && document.querySelectorAll) {
          const allScripts = document.querySelectorAll("script[type='application/json'], script:not([src])");
          for (const s of allScripts) {
            const text = s.textContent || "";
            if (text.includes("%22challenges%22") || text.includes("%22community%22") || text.includes("%22constraints%22") || (problemId && text.includes(problemId))) {
              candidateEls.push(s);
              break;
            }
          }
        }

        for (const el of candidateEls) {
          const raw = (el.textContent || el.innerText || el.innerHTML || "").trim();
          if (!raw) continue;
          const decoded = robustDecodeUri(raw);
          if (!decoded) continue;
          try {
            const initData = JSON.parse(decoded);
            const chMap = initData && initData.community && initData.community.challenges && initData.community.challenges.challenge
              ? initData.community.challenges.challenge
              : null;
            if (chMap && typeof chMap === "object") {
              for (const key of Object.keys(chMap)) {
                const det = chMap[key] && chMap[key].detail;
                if (det && det.constraints) {
                  if (!problemId || key.includes(problemId) || (det.slug && det.slug === problemId)) {
                    hrInitialDetail = det;
                    break;
                  }
                }
              }
              if (!hrInitialDetail) {
                for (const key of Object.keys(chMap)) {
                  const det = chMap[key] && chMap[key].detail;
                  if (det && det.constraints) {
                    hrInitialDetail = det;
                    break;
                  }
                }
              }
            }
            if (!hrInitialDetail) {
              hrInitialDetail = findChallengeDetailInObject(initData, problemId);
            }
            if (hrInitialDetail) break;
          } catch {}
        }
      } catch {}

      if (!problemId && hrInitialDetail && hrInitialDetail.slug) {
        problemId = hrInitialDetail.slug;
      }

      // 2. Problem Title
      let title = (hrInitialDetail && hrInitialDetail.name && isValidProblemTitle(hrInitialDetail.name))
        ? hrInitialDetail.name
        : "";
      const titleSelectors = [
        "h1.ui-icon-label",
        "h1.hr-challenge-title",
        "h1[class*='challenge-title']",
        ".challenge-title",
        "h1.ui-heading",
        ".challenge-header h1",
        "div[class*='challenge-header'] h1",
        ".challenge-view-header h1",
        "h1"
      ];

      for (const sel of titleSelectors) {
        const el = document.querySelector(sel);
        if (el) {
          const text = (el.textContent || "").trim();
          if (isValidProblemTitle(text)) {
            title = text;
            break;
          }
        }
      }

      if (!isValidProblemTitle(title) && document.title) {
        const docClean = document.title
          .replace(/\s*\|\s*HackerRank.*$/i, "")
          .replace(/^Solve\s+/i, "")
          .trim();
        if (isValidProblemTitle(docClean)) {
          title = docClean;
        }
      }

      if (!isValidProblemTitle(title) && problemId) {
        title = problemId.split("-").map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(" ");
      }

      if (!isValidProblemTitle(title)) {
        title = "HackerRank Challenge";
      }

      // 3. Problem Description Container
      let description = "";
      let descEl = document.querySelector(
        ".challenge-body-html, .problem-statement, div[class*='challenge-body'], .challenge-text, .problem-description"
      );
      if (descEl) {
        description = (descEl.innerText || descEl.textContent || "").trim();
      }

      // 4. Detected Language from HackerRank dropdown / UI
      let detectedLanguage = "unknown";
      const langSelectors = [
        "div[class*='select-language']",
        ".select-language select",
        "select[class*='select-language']",
        "button[class*='select-language']",
        ".Select-value-label",
        "[data-analytics='LanguageDropdown']"
      ];
      for (const selector of langSelectors) {
        const el = document.querySelector(selector);
        if (el) {
          const text = (el.textContent || el.value || "").trim();
          if (text) {
            const low = text.toLowerCase();
            if (low.includes("python 3") || low.includes("python3") || low === "pypy 3") {
              detectedLanguage = "Python3";
              break;
            } else if (low.includes("python")) {
              detectedLanguage = "Python";
              break;
            } else {
              detectedLanguage = text.split("\n")[0].trim();
              break;
            }
          }
        }
      }

      // 5. Constraints
      const constraints = [];

      function isConstraintText(t) {
        if (!t || typeof t !== "string") return false;
        const s = t.trim();
        if (s.length === 0 || s.length > 250) return false;
        if (s.includes("<=") || s.includes(">=") || s.includes("≤") || s.includes("≥") || s.includes("10^") || s.includes("2^")) return true;
        if (/\d+\s*<\s*[a-zA-Z]/.test(s) || /[a-zA-Z]\s*<\s*\d+/.test(s)) return true;
        if (/\d+\s*(?:<=|≤|<)\s*[a-zA-Z0-9_\[\], ]+/.test(s)) return true;
        if (/[a-zA-Z0-9_\[\], ]+\s*(?:<=|≤|<)\s*\d+/.test(s)) return true;
        if (/^[0-9\s<>=≤≥,a-zA-Z_\[\]+-]+$/.test(s) && (s.includes("<") || s.includes(">") || s.includes("="))) return true;
        return false;
      }

      function addConstraintLine(raw) {
        if (!raw) return;
        const lines = raw.split(/\r?\n/).map(l => l.trim()).filter(Boolean);
        lines.forEach(l => {
          const norm = normalizeCollapsedExponents(l);
          if (isConstraintText(norm) && !constraints.includes(norm)) {
            constraints.push(norm);
          }
        });
      }

      // 0. Extract from authoritative initialData if available
      if (hrInitialDetail && hrInitialDetail.constraints) {
        addConstraintLine(hrInitialDetail.constraints);
      }

      // 1. Direct scan for HackerRank specific constraint containers
      if (constraints.length === 0) {
        const directConstraintSecs = Array.from(
          document.querySelectorAll(".challenge_constraints, [data-analytics='challenge-constraints'], div[class*='challenge_constraints'], div[class*='challenge-section'][class*='constraint'], section[class*='constraint']")
        );
        for (const sec of directConstraintSecs) {
          const items = sec.querySelectorAll ? sec.querySelectorAll("script[type*='math/tex'], script[type*='latex'], mjx-container, .MathJax, .MathJax_Display, [jax], .tex-span, li, p, pre, div") : [];
          items.forEach(it => {
            addConstraintLine(extractTextWithSuperscripts(it));
          });
          if (constraints.length === 0) {
            addConstraintLine(extractTextWithSuperscripts(sec));
          }
        }
      }

      // 2. Heading scan: find section headings explicitly labeled "Constraints"
      if (constraints.length === 0) {
        const allCandidateHeadings = Array.from(
          document.querySelectorAll("h1, h2, h3, h4, h5, h6, strong, b, p, div, span, label, header")
        ).filter(el => {
          const t = (el.textContent || "").trim().toLowerCase();
          if (!t.startsWith("constraint") && t !== "constraints" && t !== "constraints:") return false;
          // Ignore container if it holds a deeper heading with the same text
          const deeper = el.querySelectorAll ? Array.from(el.querySelectorAll("h1, h2, h3, h4, h5, h6, strong, b, span")).filter(sub => {
            const st = (sub.textContent || "").trim().toLowerCase();
            return st.startsWith("constraint");
          }) : [];
          return deeper.length === 0;
        });

        for (const heading of allCandidateHeadings) {
          let container = null;

          // Check direct next sibling
          let sib = heading.nextElementSibling;
          while (sib) {
            const tag = (sib.tagName || "").toUpperCase();
            if (["H1", "H2", "H3", "H4", "H5", "H6"].includes(tag)) break;
            container = sib;
            break;
          }

          // Check parent's next sibling (e.g. heading wrapped in a title div or p)
          if (!container && heading.parentElement) {
            let pSib = heading.parentElement.nextElementSibling;
            while (pSib) {
              const tag = (pSib.tagName || "").toUpperCase();
              if (["H1", "H2", "H3", "H4", "H5", "H6"].includes(tag)) break;
              container = pSib;
              break;
            }
          }

          // Walk up to enclosing section container
          if (!container && heading.closest) {
            const sec = heading.closest(".challenge-section, section, div[class*='challenge'], div[class*='section']");
            if (sec) {
              container = sec.querySelector(".challenge_constraints, [data-analytics='challenge-constraints'], div[class*='challenge_constraints'], .challenge-section-body, ul, ol, p");
            }
          }

          if (container) {
            const items = container.querySelectorAll ? container.querySelectorAll("script[type*='math/tex'], script[type*='latex'], mjx-container, .MathJax, .MathJax_Display, [jax], .tex-span, li, p, pre, div") : [];
            items.forEach(it => {
              addConstraintLine(extractTextWithSuperscripts(it));
            });
            if (constraints.length === 0) {
              addConstraintLine(extractTextWithSuperscripts(container));
            }
          }
          if (constraints.length > 0) break;
        }
      }

      // 3. Fallback: scan for mathematical inequalities inside description container
      if (constraints.length === 0 && descEl) {
        const items = descEl.querySelectorAll ? descEl.querySelectorAll("script[type*='math/tex'], script[type*='latex'], mjx-container, .MathJax, .MathJax_Display, [jax], .challenge_constraints, li, p") : [];
        items.forEach(item => {
          const t = extractTextWithSuperscripts(item);
          if (isConstraintText(t) && (t.includes("<") || t.includes(">") || t.includes("≤") || t.includes("≥") || t.includes("<="))) {
            addConstraintLine(t);
          }
        });
      }

      // 6. Sample Inputs and Outputs
      const sampleInputs = [];
      const sampleOutputs = [];

      const sampleInputHeadings = Array.from(
        document.querySelectorAll("h1, h2, h3, h4, h5, strong, b, p, div")
      ).filter(el => {
        const t = (el.textContent || "").trim();
        if (!/^sample\s+input(?:\s+\d+)?\s*:?$/i.test(t)) return false;
        if (el.querySelector && el.querySelector("h1, h2, h3, h4, h5, strong, b")) return false;
        return true;
      });

      sampleInputHeadings.forEach(heading => {
        let el = heading.nextElementSibling;
        if (!el && heading.parentElement) {
          el = heading.parentElement.nextElementSibling;
        }
        if (!el && heading.closest) {
          const sec = heading.closest(".challenge-section, div[class*='section']");
          if (sec) el = sec.querySelector(".challenge-section-body, [class*='body'], pre");
        }
        while (el) {
          const pre = el.tagName === "PRE" ? el : (el.querySelector ? el.querySelector("pre, code") : null);
          if (pre) {
            let val = (pre.textContent || "").trim();
            val = cleanHackerRankSampleInput(val);
            if (val && !sampleInputs.includes(val)) {
              sampleInputs.push(val);
            }
            break;
          }
          el = el.nextElementSibling;
        }
      });

      const sampleOutputHeadings = Array.from(
        document.querySelectorAll("h1, h2, h3, h4, h5, strong, b, p, div")
      ).filter(el => {
        const t = (el.textContent || "").trim();
        if (!/^sample\s+output(?:\s+\d+)?\s*:?$/i.test(t)) return false;
        if (el.querySelector && el.querySelector("h1, h2, h3, h4, h5, strong, b")) return false;
        return true;
      });

      sampleOutputHeadings.forEach(heading => {
        let el = heading.nextElementSibling;
        if (!el && heading.parentElement) {
          el = heading.parentElement.nextElementSibling;
        }
        if (!el && heading.closest) {
          const sec = heading.closest(".challenge-section, div[class*='section']");
          if (sec) el = sec.querySelector(".challenge-section-body, [class*='body'], pre");
        }
        while (el) {
          const pre = el.tagName === "PRE" ? el : (el.querySelector ? el.querySelector("pre, code") : null);
          if (pre) {
            const val = (pre.textContent || "").trim();
            if (val && !sampleOutputs.includes(val)) {
              sampleOutputs.push(val);
            }
            break;
          }
          el = el.nextElementSibling;
        }
      });

      // 7. Input/Output Format sections
      let inputFormat = "";
      let outputFormat = "";
      const formatHeadings = Array.from(
        document.querySelectorAll("h3, h4, h5, strong, b, p")
      ).filter(el => {
        const t = (el.textContent || "").trim().toLowerCase();
        return t.startsWith("input format") || t.startsWith("output format");
      });

      formatHeadings.forEach(h => {
        const t = (h.textContent || "").trim().toLowerCase();
        let content = "";
        let sib = h.nextElementSibling;
        while (sib && !["H2", "H3", "H4", "H5"].includes(sib.tagName)) {
          content += (sib.textContent || "").trim() + " ";
          sib = sib.nextElementSibling;
        }
        if (t.startsWith("input format")) inputFormat = content.trim();
        else if (t.startsWith("output format")) outputFormat = content.trim();
      });

      return {
        platform: Platform.HACKERRANK,
        isLeetCode: false,
        isProblemPage,
        title: title || "HackerRank Challenge",
        problemId,
        url: window.location.href,
        description,
        inputFormat,
        outputFormat,
        language: detectedLanguage,
        constraints,
        sampleInputs,
        sampleOutputs
      };
    }
  };

  // ============================================================================
  // Codeforces URL Parsing & Context Retention
  // ============================================================================

  // Codeforces problem context cache for safely retaining previously detected problem details
  const cfProblemCache = new Map();

  function saveCachedProblemContext(problemId, ctx) {
    if (!problemId || !ctx) return;
    cfProblemCache.set(problemId, ctx);
    try {
      if (typeof sessionStorage !== "undefined" && sessionStorage.setItem) {
        sessionStorage.setItem("edgemind_cf_" + problemId, JSON.stringify(ctx));
      }
    } catch {}
  }

  function getCachedProblemContext(problemId) {
    if (!problemId) return null;
    if (cfProblemCache.has(problemId)) {
      return cfProblemCache.get(problemId);
    }
    try {
      if (typeof sessionStorage !== "undefined" && sessionStorage.getItem) {
        const item = sessionStorage.getItem("edgemind_cf_" + problemId);
        if (item) {
          const parsed = JSON.parse(item);
          cfProblemCache.set(problemId, parsed);
          return parsed;
        }
      }
    } catch {}
    return null;
  }

  /**
   * Parse Codeforces URL to extract contestId, problemIndex, pageType, and submit status.
   */
  function parseCodeforcesUrl(urlStr = (typeof window !== "undefined" && window.location ? window.location.href : ""), pathname = (typeof window !== "undefined" && window.location ? window.location.pathname : "")) {
    let contestId = "";
    let problemIndex = "";
    let isSubmitPage = false;
    let pageType = "other";

    const cleanPath = pathname || "";

    // 1. Problemset Problem: /problemset/problem/{contestId}/{problemIndex}
    const psetProbMatch = cleanPath.match(/\/problemset\/problem\/(\d+)\/([a-zA-Z0-9]+)/i);
    if (psetProbMatch) {
      contestId = psetProbMatch[1];
      problemIndex = psetProbMatch[2].toUpperCase();
      pageType = "problem";
      return { contestId, problemIndex, pageType, isSubmitPage: false };
    }

    // 2. Contest Problem: /contest/{contestId}/problem/{problemIndex}
    const contestProbMatch = cleanPath.match(/\/contest\/(\d+)\/problem\/([a-zA-Z0-9]+)/i);
    if (contestProbMatch) {
      contestId = contestProbMatch[1];
      problemIndex = contestProbMatch[2].toUpperCase();
      pageType = "problem";
      return { contestId, problemIndex, pageType, isSubmitPage: false };
    }

    // 3. Gym Problem: /gym/{contestId}/problem/{problemIndex}
    const gymProbMatch = cleanPath.match(/\/gym\/(\d+)\/problem\/([a-zA-Z0-9]+)/i);
    if (gymProbMatch) {
      contestId = gymProbMatch[1];
      problemIndex = gymProbMatch[2].toUpperCase();
      pageType = "gym_problem";
      return { contestId, problemIndex, pageType, isSubmitPage: false };
    }

    // 4. Contest Submit: /contest/{contestId}/submit
    const contestSubmitMatch = cleanPath.match(/\/contest\/(\d+)\/submit/i);
    if (contestSubmitMatch) {
      contestId = contestSubmitMatch[1];
      isSubmitPage = true;
      pageType = "submit";
    }

    // 5. Gym Submit: /gym/{contestId}/submit
    const gymSubmitMatch = cleanPath.match(/\/gym\/(\d+)\/submit/i);
    if (gymSubmitMatch) {
      contestId = gymSubmitMatch[1];
      isSubmitPage = true;
      pageType = "gym_submit";
    }

    // 6. Problemset Submit: /problemset/submit
    if (cleanPath.includes("/problemset/submit")) {
      isSubmitPage = true;
      pageType = "submit";
    }

    // Inspect URL search params for problem code/index if on submit page
    if (isSubmitPage && urlStr) {
      try {
        const queryIdx = urlStr.indexOf("?");
        if (queryIdx !== -1) {
          const queryString = urlStr.slice(queryIdx);
          const searchParams = new URLSearchParams(queryString);
          const pCode = searchParams.get("problemCode") || searchParams.get("submittedProblemCode");
          if (pCode) {
            const m = pCode.match(/^(\d+)([a-zA-Z0-9]+)$/);
            if (m) {
              if (!contestId) contestId = m[1];
              problemIndex = m[2].toUpperCase();
            }
          }
          const pIdx = searchParams.get("problemIndex") || searchParams.get("problem");
          if (pIdx && !problemIndex) {
            problemIndex = pIdx.toUpperCase();
          }
        }
      } catch {}
    }

    return { contestId, problemIndex, pageType, isSubmitPage };
  }

  /**
   * Codeforces Adapter.
   */
  const CodeforcesAdapter = {
    platform: Platform.CODEFORCES,

    isProblemPage(url = (typeof window !== "undefined" && window.location ? window.location.href : ""), pathname = (typeof window !== "undefined" && window.location ? window.location.pathname : "")) {
      return (
        pathname.includes("/problem/") ||
        pathname.includes("/contest/") ||
        pathname.includes("/problemset/") ||
        pathname.includes("/gym/") ||
        Boolean(typeof document !== "undefined" && document.querySelector && document.querySelector(".problem-statement, form.submit-form, #sourceCodeTextarea, select[name='programTypeId']"))
      );
    },

    extract() {
      const pathname = typeof window !== "undefined" && window.location ? window.location.pathname || "" : "";
      const href = typeof window !== "undefined" && window.location ? window.location.href || "" : "";
      const isProblemPage = this.isProblemPage(href, pathname);

      const parsedUrl = parseCodeforcesUrl(href, pathname);
      let contestId = parsedUrl.contestId || "";
      let problemIndex = parsedUrl.problemIndex || "";
      const isSubmitPage = parsedUrl.isSubmitPage;

      // Check DOM if problemIndex or contestId is missing (especially on submit pages)
      if (typeof document !== "undefined" && document.querySelector) {
        if (!problemIndex) {
          // 1. Check contest submit select: select[name="submittedProblemIndex"]
          const idxSelect = document.querySelector("select[name='submittedProblemIndex'], select[name*='problemIndex']");
          if (idxSelect && idxSelect.options && idxSelect.selectedIndex >= 0) {
            const opt = idxSelect.options[idxSelect.selectedIndex];
            const val = (idxSelect.value || (opt && opt.value) || "").trim();
            if (val && !/^(?:choose|select|none)\b|^\s*$/i.test(val)) {
              problemIndex = val.toUpperCase();
            }
          }
        }

        if (!problemIndex || !contestId) {
          // 2. Check problemset submit input or select: input[name="submittedProblemCode"]
          const codeInput = document.querySelector("input[name='submittedProblemCode'], input[name*='problemCode']");
          if (codeInput && codeInput.value) {
            const val = codeInput.value.trim();
            const m = val.match(/^(\d+)([a-zA-Z0-9]+)$/);
            if (m) {
              if (!contestId) contestId = m[1];
              if (!problemIndex) problemIndex = m[2].toUpperCase();
            }
          }
          const codeSelect = document.querySelector("select[name='submittedProblemCode']");
          if (codeSelect && codeSelect.options && codeSelect.selectedIndex >= 0) {
            const opt = codeSelect.options[codeSelect.selectedIndex];
            const val = (codeSelect.value || (opt && opt.value) || (opt && opt.text) || "").trim();
            const m = val.match(/^(\d+)([a-zA-Z0-9]+)$/);
            if (m) {
              if (!contestId) contestId = m[1];
              if (!problemIndex) problemIndex = m[2].toUpperCase();
            }
          }
        }
      }

      // Build problemId
      let problemId = "";
      if (contestId && problemIndex) {
        problemId = parsedUrl.pageType.startsWith("gym") ? `gym-${contestId}${problemIndex}` : `${contestId}${problemIndex}`;
      } else if (problemIndex) {
        problemId = problemIndex;
      }

      // 2. Problem Title
      let title = "";
      if (typeof document !== "undefined" && document.querySelector) {
        const titleEl = document.querySelector(".problem-statement .header .title, .problemindexholder .title");
        if (titleEl) {
          title = (titleEl.textContent || "").trim();
        }

        if (!isValidProblemTitle(title) && typeof document.title === "string" && document.title) {
          const docClean = document.title
            .replace(/\s*-\s*Codeforces.*$/i, "")
            .replace(/^Problem\s*-\s*/i, "")
            .trim();
          if (isValidProblemTitle(docClean)) {
            title = docClean;
          }
        }

        // Check if selected option on submit page contains problem title
        if (!isValidProblemTitle(title) && isSubmitPage) {
          const idxSelect = document.querySelector("select[name='submittedProblemIndex'], select[name*='problemIndex']");
          if (idxSelect && idxSelect.options && idxSelect.selectedIndex >= 0) {
            const opt = idxSelect.options[idxSelect.selectedIndex];
            const optVal = (idxSelect.value || (opt && opt.value) || "").trim();
            const optText = (opt && opt.text || "").trim();
            if (optVal && optText && !/^(?:choose|select|none)\b|^\s*$/i.test(optText)) {
              title = optText;
            }
          }
        }
      }

      if (!isValidProblemTitle(title) && problemId) {
        title = `Codeforces Problem ${problemId}`;
      }

      if (!isValidProblemTitle(title)) {
        title = isSubmitPage ? (contestId ? `Codeforces Contest ${contestId} Submission` : "Codeforces Submission") : "Codeforces Problem";
      }

      // If problemId is still empty, derive letter from title e.g. "A. Watermelon" -> "A"
      if (!problemId && title) {
        const letterMatch = title.match(/^([A-Z0-9]+)\.\s+/);
        if (letterMatch) {
          problemIndex = letterMatch[1].toUpperCase();
          if (contestId) {
            problemId = `${contestId}${problemIndex}`;
          } else {
            problemId = problemIndex;
          }
        }
      }

      if (isSubmitPage && !problemId) {
        title = contestId ? `Codeforces Contest ${contestId} Submission` : "Codeforces Submission";
      }

      // 3. Problem Statement & Description
      let description = "";
      let timeLimit = "";
      let memoryLimit = "";
      let inputSpecification = "";
      let outputSpecification = "";
      const constraints = [];
      const sampleInputs = [];
      const sampleOutputs = [];

      if (typeof document !== "undefined" && document.querySelector) {
        const problemStatementEl = document.querySelector(".problem-statement");
        if (problemStatementEl) {
          const headerEl = problemStatementEl.querySelector(".header");
          const inputSpecEl = problemStatementEl.querySelector(".input-specification");

          const paras = [];
          let cur = headerEl ? headerEl.nextElementSibling : problemStatementEl.firstElementChild;
          while (cur && cur !== inputSpecEl) {
            if (cur.classList && (cur.classList.contains("input-specification") || cur.classList.contains("output-specification") || cur.classList.contains("sample-tests"))) {
              break;
            }
            paras.push((cur.innerText || cur.textContent || "").trim());
            cur = cur.nextElementSibling;
          }
          description = paras.filter(Boolean).join("\n\n");
        }

        const timeLimitEl = document.querySelector(".problem-statement .header .time-limit");
        if (timeLimitEl) {
          timeLimit = (timeLimitEl.textContent || "").replace("time limit per test", "").trim();
        }
        const memLimitEl = document.querySelector(".problem-statement .header .memory-limit");
        if (memLimitEl) {
          memoryLimit = (memLimitEl.textContent || "").replace("memory limit per test", "").trim();
        }

        const inputSpecEl = document.querySelector(".problem-statement .input-specification");
        if (inputSpecEl) {
          inputSpecification = (inputSpecEl.innerText || inputSpecEl.textContent || "").replace(/^Input\s*/i, "").trim();

          const mathScripts = inputSpecEl.querySelectorAll ? inputSpecEl.querySelectorAll("script[type='math/tex']") : [];
          mathScripts.forEach(script => {
            const raw = (script.textContent || "").trim();
            const norm = normalizeLatex(raw);
            if (norm && (norm.includes("<=") || norm.includes(">=") || norm.includes("length") || norm.includes("10^")) && !constraints.includes(norm)) {
              constraints.push(norm);
            }
          });

          const texSpans = inputSpecEl.querySelectorAll ? inputSpecEl.querySelectorAll(".tex-span, span.tex-font-style-tt, mjx-container") : [];
          texSpans.forEach(span => {
            const norm = extractTextWithSuperscripts(span);
            if (norm && (norm.includes("<=") || norm.includes(">=") || norm.includes("≤") || norm.includes("≥")) && !constraints.includes(norm)) {
              constraints.push(norm);
            }
          });

          const paras = inputSpecEl.querySelectorAll ? inputSpecEl.querySelectorAll("p") : [];
          paras.forEach(p => {
            const t = extractTextWithSuperscripts(p);
            const matches = t.match(/\(?\s*\d+\s*(?:<=|≤|<)\s*[^<>=,\n]+?\s*(?:<=|≤|<)\s*\d+(?:\^\d+)?\s*\)?/g);
            if (matches) {
              matches.forEach(m => {
                const clean = m.replace(/[()]/g, "").trim();
                if (clean && !constraints.includes(clean)) constraints.push(clean);
              });
            }
          });

          if (inputSpecification) {
            const textMatches = inputSpecification.match(/\(?\s*\d+\s*(?:<=|≤|<)\s*[^<>=,\n]+?\s*(?:<=|≤|<)\s*\d+(?:\^\d+)?\s*\)?/g);
            if (textMatches) {
              textMatches.forEach(m => {
                const clean = m.replace(/[()]/g, "").trim();
                if (clean && !constraints.includes(clean)) constraints.push(clean);
              });
            }
          }
        }

        if (timeLimit) constraints.unshift(`Time limit: ${timeLimit}`);
        if (memoryLimit) constraints.unshift(`Memory limit: ${memoryLimit}`);

        const outputSpecEl = document.querySelector(".problem-statement .output-specification");
        if (outputSpecEl) {
          outputSpecification = (outputSpecEl.innerText || outputSpecEl.textContent || "").replace(/^Output\s*/i, "").trim();
        }

        const sampleTestEl = document.querySelector(".problem-statement .sample-tests, .sample-test");
        if (sampleTestEl && sampleTestEl.querySelectorAll) {
          const inputDivs = sampleTestEl.querySelectorAll(".input pre");
          inputDivs.forEach(pre => {
            const lineDivs = pre.querySelectorAll ? pre.querySelectorAll(".test-example-line") : [];
            let val = "";
            if (lineDivs.length > 0) {
              val = Array.from(lineDivs).map(l => (l.textContent || "").trim()).filter(Boolean).join("\n");
            } else {
              val = (pre.textContent || "").trim();
            }
            if (val && !sampleInputs.includes(val)) {
              sampleInputs.push(val);
            }
          });

          const outputDivs = sampleTestEl.querySelectorAll(".output pre");
          outputDivs.forEach(pre => {
            const val = (pre.textContent || "").trim();
            if (val && !sampleOutputs.includes(val)) {
              sampleOutputs.push(val);
            }
          });
        }
      }

      // Safe context retention vs caching:
      if (isSubmitPage) {
        if (problemId) {
          const cached = getCachedProblemContext(problemId);
          if (cached) {
            if (!description && cached.description) description = cached.description;
            if (constraints.length === 0 && Array.isArray(cached.constraints)) constraints.push(...cached.constraints);
            if (sampleInputs.length === 0 && Array.isArray(cached.sampleInputs)) sampleInputs.push(...cached.sampleInputs);
            if (sampleOutputs.length === 0 && Array.isArray(cached.sampleOutputs)) sampleOutputs.push(...cached.sampleOutputs);
            if (!timeLimit && cached.timeLimit) timeLimit = cached.timeLimit;
            if (!memoryLimit && cached.memoryLimit) memoryLimit = cached.memoryLimit;
            if (!inputSpecification && cached.inputSpecification) inputSpecification = cached.inputSpecification;
            if (!outputSpecification && cached.outputSpecification) outputSpecification = cached.outputSpecification;
            if (isValidProblemTitle(cached.title)) {
              title = cached.title;
            }
          }
        }
      } else {
        if (problemId && (description || constraints.length > 0)) {
          saveCachedProblemContext(problemId, {
            title,
            description,
            timeLimit,
            memoryLimit,
            constraints,
            sampleInputs,
            sampleOutputs,
            inputSpecification,
            outputSpecification,
            contestId,
            problemIndex
          });
        }
      }

      // Language detection
      let detectedLanguage = "unknown";
      if (typeof document !== "undefined" && document.querySelector) {
        const langSelect = document.querySelector("select[name='programTypeId'], select#programTypeId, select[name*='programType']");
        if (langSelect && langSelect.options && langSelect.selectedIndex >= 0) {
          const optText = (langSelect.options[langSelect.selectedIndex].text || "").toLowerCase();
          if (optText.includes("python 3") || optText.includes("pypy 3")) {
            detectedLanguage = "Python3";
          } else if (optText.includes("python")) {
            detectedLanguage = "Python";
          } else if (optText) {
            detectedLanguage = (langSelect.options[langSelect.selectedIndex].text || "").trim();
          }
        }
      }

      const problemSelected = Boolean(problemId);

      return {
        platform: Platform.CODEFORCES,
        isLeetCode: false,
        isProblemPage,
        isSubmitPage,
        contestId: contestId || null,
        problemIndex: problemIndex || null,
        problemId: problemId || "",
        problemSelected,
        title: title || (isSubmitPage ? "Codeforces Submission" : "Codeforces Problem"),
        url: href,
        description,
        timeLimit,
        memoryLimit,
        inputSpecification,
        outputSpecification,
        language: detectedLanguage,
        constraints,
        sampleInputs,
        sampleOutputs
      };
    }
  };

  // ============================================================================
  // 4. Extraction Dispatcher
  // ============================================================================

  function extractProblemInfo() {
    const platform = detectPlatform();

    let adapter = null;
    switch (platform) {
      case Platform.LEETCODE:
        adapter = LeetCodeAdapter;
        break;
      case Platform.HACKERRANK:
        adapter = HackerRankAdapter;
        break;
      case Platform.CODEFORCES:
        adapter = CodeforcesAdapter;
        break;
      default:
        return {
          platform: Platform.UNKNOWN,
          isLeetCode: false,
          isProblemPage: false,
          title: "Unsupported Platform",
          problemId: "",
          url: window.location.href,
          description: "",
          language: "unknown",
          constraints: [],
          sampleInputs: [],
          sampleOutputs: []
        };
    }

    const data = adapter.extract();

    // Compute extraction confidence and unavailable fields
    const unavailableFields = [];
    if (!data.problemId) unavailableFields.push("problem");
    if (!data.description) unavailableFields.push("description");
    if (!data.constraints || data.constraints.length === 0) unavailableFields.push("constraints");
    if (!data.sampleInputs || data.sampleInputs.length === 0) unavailableFields.push("sampleInputs");

    let confidence = "HIGH";
    if (data.isSubmitPage && !data.problemSelected) {
      confidence = "NONE";
    } else if (unavailableFields.length >= 2) {
      confidence = "LOW";
    } else if (unavailableFields.length === 1) {
      confidence = "MEDIUM";
    }

    data.extractionConfidence = confidence;
    data.unavailableFields = unavailableFields;
    return data;
  }

  // ============================================================================
  // 5. SPA Navigation & Dynamic DOM Observation
  // ============================================================================

  function handleUrlChange() {
    const currentUrl = window.location.href;
    if (currentUrl !== lastUrl) {
      lastUrl = currentUrl;
      cachedInfo = null;
      triggerDebouncedExtraction(300);
    }
  }

  if (typeof window !== "undefined") {
    if (typeof window.addEventListener === "function") {
      window.addEventListener("popstate", handleUrlChange);
    }
    if (typeof setInterval === "function") {
      const pollTimer = setInterval(handleUrlChange, 1000);
      if (pollTimer && typeof pollTimer.unref === "function") {
        pollTimer.unref();
      }
    }
  }

  function triggerDebouncedExtraction(delay = 350) {
    if (debounceTimer) clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => {
      cachedInfo = extractProblemInfo();
    }, delay);
  }

  if (typeof document !== "undefined" && document.body && typeof MutationObserver !== "undefined") {
    const observer = new MutationObserver((mutations) => {
      let relevant = false;
      for (const m of mutations) {
        if (m.type === "childList" && m.addedNodes.length > 0) {
          for (const node of m.addedNodes) {
            if (node.nodeType === Node.ELEMENT_NODE) {
              const el = /** @type {Element} */ (node);
              if (
                el.matches &&
                (el.matches(".example-block, [data-track-load], div[class*='description'], pre, .challenge-body-html, .problem-statement, .sample-tests") ||
                  (el.querySelector && el.querySelector(".example-block, pre, [data-track-load], .challenge-body-html, .problem-statement, .sample-tests")))
              ) {
                relevant = true;
                break;
              }
            }
          }
        }
        if (relevant) break;
      }
      if (relevant) {
        triggerDebouncedExtraction(300);
      }
    });

    observer.observe(document.body, { childList: true, subtree: true });
  }

  // ============================================================================
  // 6. Chrome Runtime Messaging
  // ============================================================================

  if (typeof chrome !== "undefined" && chrome.runtime && chrome.runtime.onMessage) {
    chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
      if (!request || typeof request !== "object") {
        return false;
      }

      const platform = detectPlatform();

      if (request.action === "PING") {
        sendResponse({
          status: "OK",
          url: typeof window !== "undefined" ? window.location.href : "",
          platform: platform,
          isSupported: platform !== Platform.UNKNOWN,
          isLeetCode: platform === Platform.LEETCODE
        });
        return true;
      }

      if (request.action === "GET_PROBLEM_INFO" || request.action === "REFRESH_PROBLEM_INFO") {
        if (request.action === "REFRESH_PROBLEM_INFO") {
          cachedInfo = null;
        }
        const data = extractProblemInfo();
        cachedInfo = data;
        sendResponse(data);
        return true;
      }

      return false;
    });
  }

  // Export for automated testing in Node.js
  if (typeof module !== "undefined" && module.exports) {
    module.exports = {
      Platform,
      detectPlatform,
      cleanInputString,
      normalizeLatex,
      normalizeCollapsedExponents,
      extractTextWithSuperscripts,
      isValidProblemTitle,
      LeetCodeAdapter,
      HackerRankAdapter,
      CodeforcesAdapter,
      parseCodeforcesUrl,
      saveCachedProblemContext,
      getCachedProblemContext,
      cfProblemCache,
      extractProblemInfo
    };
  }
})();
