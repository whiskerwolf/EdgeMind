/**
 * EdgeMind Content Script.
 *
 * Runs on LeetCode pages in an isolated world.
 * Automatically extracts problem title, problem slug, problem URL,
 * description, constraints, and public example inputs from the DOM.
 * Supports LeetCode SPA navigation and dynamic DOM observation with debouncing.
 */
(() => {
  "use strict";

  let lastUrl = window.location.href;
  let cachedInfo = null;
  let debounceTimer = null;

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
    let s = str;
    // 1. LaTeX operators
    s = s.replace(/\\le\b|\\leq\b/g, "<=");
    s = s.replace(/\\ge\b|\\geq\b/g, ">=");
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
    // Handles nested wrappers like \text{text{grid}} or \text{\text{grid}}
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
      const clone = element.cloneNode(true);

      // 1. Process all KaTeX elements
      const katexEls = clone.querySelectorAll(".katex, [data-katex]");
      katexEls.forEach(k => {
        // A. If LaTeX annotation exists, use it directly
        const ann = k.querySelector("annotation");
        if (ann && ann.textContent && ann.textContent.trim()) {
          let rawTex = ann.textContent.trim();
          rawTex = normalizeLatex(rawTex);
          k.textContent = " " + rawTex + " ";
          return;
        }

        // B. Handle KaTeX HTML layout (.msupsub contains the exponent)
        const mathml = k.querySelector(".katex-mathml, math");
        const katexHtml = k.querySelector(".katex-html");

        if (katexHtml) {
          // Remove hidden MathML tree to prevent duplicate text concatenation
          if (mathml) mathml.remove();

          const msupsubs = katexHtml.querySelectorAll(".msupsub");
          msupsubs.forEach(sub => {
            const expText = (sub.textContent || "").trim();
            if (expText && !expText.startsWith("^")) {
              sub.textContent = "^" + expText;
            }
          });

          const mrels = katexHtml.querySelectorAll(".mrel");
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

        // C. Handle pure MathML <msup> if KaTeX HTML is absent
        if (mathml) {
          const msups = mathml.querySelectorAll("msup");
          msups.forEach(msup => {
            const children = Array.from(msup.children).filter(c => (c.textContent || "").trim());
            if (children.length >= 2) {
              const base = (children[0].textContent || "").trim();
              const exp = (children[1].textContent || "").trim();
              msup.textContent = base + "^" + exp;
            }
          });
          const mos = mathml.querySelectorAll("mo");
          mos.forEach(mo => {
            const t = (mo.textContent || "").trim();
            if (t === "≤" || t === "\u2264") mo.textContent = " <= ";
            else if (t === "≥" || t === "\u2265") mo.textContent = " >= ";
          });
          k.textContent = " " + (mathml.textContent || "").trim() + " ";
          return;
        }
      });

      // 2. Process standard HTML <sup> elements
      const sups = clone.querySelectorAll("sup");
      sups.forEach(sup => {
        const supText = (sup.textContent || "").trim();
        if (supText && !supText.startsWith("^")) {
          sup.textContent = "^" + supText;
        }
      });

      // 3. Process MathJax elements
      const mjxSups = clone.querySelectorAll("mjx-sup, .mjx-sup");
      mjxSups.forEach(sup => {
        const supText = (sup.textContent || "").trim();
        if (supText && !supText.startsWith("^")) {
          sup.textContent = "^" + supText;
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
    if (trimmed.toLowerCase().includes("leetcode")) return false;
    return true;
  }

  function extractProblemInfo() {
    const isLeetCode = window.location.hostname.includes("leetcode.com");
    const pathname = window.location.pathname || "";
    const isProblemPage = pathname.includes("/problems/");

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
      document.querySelectorAll("p, strong, em, div")
    ).filter(el => (el.textContent || "").trim().toLowerCase().startsWith("constraints:"));

    if (constraintHeaders.length > 0) {
      const header = constraintHeaders[0];
      const candidates = [header.nextElementSibling];
      if (header.parentElement) {
        candidates.push(header.parentElement.nextElementSibling);
      }
      for (let nextEl of candidates) {
        while (nextEl && (nextEl.tagName === "UL" || nextEl.tagName === "OL" || nextEl.tagName === "DIV")) {
          const items = nextEl.querySelectorAll("li, p");
          if (items.length > 0) {
            items.forEach(li => {
              const text = extractTextWithSuperscripts(li);
              if (text && text.length < 200 && !constraints.includes(text)) constraints.push(text);
            });
            break;
          }
          nextEl = nextEl.nextElementSibling;
        }
        if (constraints.length > 0) break;
      }
    }

    // Fallback if list structure was not adjacent to Constraints header
    if (constraints.length === 0) {
      const allLis = document.querySelectorAll("[data-track-load='description_content'] ul li, .elfjS ul li, div[class*='description'] ul li");
      allLis.forEach(li => {
        const text = extractTextWithSuperscripts(li);
        if (text && (text.includes("<=") || text.includes(">=") || text.includes("length") || text.includes("nums")) && text.length < 200 && !constraints.includes(text)) {
          constraints.push(text);
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
      let extracted = "";

      const inputElements = Array.from(block.querySelectorAll("p, div, li")).filter(el => {
        const t = (el.textContent || "").trim();
        return /Input\s*:/i.test(t);
      });

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
      isLeetCode,
      isProblemPage,
      title: title || "LeetCode Problem",
      problemId,
      url: window.location.href,
      description,
      language: detectedLanguage,
      constraints,
      sampleInputs
    };
  }

  // SPA Navigation and Dynamic DOM Observation
  function handleUrlChange() {
    const currentUrl = window.location.href;
    if (currentUrl !== lastUrl) {
      lastUrl = currentUrl;
      cachedInfo = null;
      triggerDebouncedExtraction(300);
    }
  }

  window.addEventListener("popstate", handleUrlChange);
  setInterval(handleUrlChange, 1000);

  function triggerDebouncedExtraction(delay = 350) {
    if (debounceTimer) clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => {
      cachedInfo = extractProblemInfo();
    }, delay);
  }

  if (document.body) {
    const observer = new MutationObserver((mutations) => {
      let relevant = false;
      for (const m of mutations) {
        if (m.type === "childList" && m.addedNodes.length > 0) {
          for (const node of m.addedNodes) {
            if (node.nodeType === Node.ELEMENT_NODE) {
              const el = /** @type {Element} */ (node);
              if (
                el.matches &&
                (el.matches(".example-block, [data-track-load], div[class*='description'], pre") ||
                  (el.querySelector && el.querySelector(".example-block, pre, [data-track-load]")))
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

  // Message Listener
  chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (!request || typeof request !== "object") {
      return false;
    }

    if (request.action === "PING") {
      sendResponse({
        status: "OK",
        url: window.location.href,
        isLeetCode: window.location.hostname.includes("leetcode.com")
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
})();
