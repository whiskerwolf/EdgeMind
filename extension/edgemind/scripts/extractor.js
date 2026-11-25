/**
 * EdgeMind Multi-Platform Solution & Buffer Extractor.
 *
 * Executed in the page's MAIN execution world via chrome.scripting.executeScript
 * to access in-memory editor models (Monaco, CodeMirror, ACE) directly without
 * isolated-world DOM restrictions.
 *
 * Supported Platforms:
 * 1. LeetCode (Monaco Editor models, active editor buffer, testcase models)
 * 2. HackerRank (Monaco Editor, CodeMirror, or active solution textarea)
 * 3. Codeforces (ACE Editor, CodeMirror, submit textarea, or graceful no-editor handling)
 *
 * Guarantees:
 * - Accesses in-memory buffer via model.getValue() / editor.getValue() (avoids line virtualization)
 * - Identifies and validates Python language models
 * - Never executes code
 * - Never triggers Run, Submit, or other website action buttons
 * - Does not interfere with the active editor
 */
(() => {
  "use strict";

  // 1. Detect platform
  const hostname = (window.location.hostname || "").toLowerCase();
  const isLeetCode = hostname.includes("leetcode.com");
  const isHackerRank = hostname.includes("hackerrank.com");
  const isCodeforces = hostname.includes("codeforces.com");

  if (!isLeetCode && !isHackerRank && !isCodeforces) {
    return {
      success: false,
      error: "Active page is not a supported platform. EdgeMind supports LeetCode, HackerRank, and Codeforces."
    };
  }

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

  // Helper to extract DOM sample inputs across platforms
  function extractDomSamples() {
    const samples = [];
    try {
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

      // Check standard example blocks
      const selectors = [
        ".example-block",
        "div[class*='example-block']",
        "div[class*='example_block']",
        "[data-track-load='description_content'] pre",
        ".elfjS pre",
        ".sample-tests .input pre",
        ".sample-test .input pre",
        ".challenge_sample_input pre",
        ".challenge-section-body pre",
        "pre"
      ];
      const blocks = Array.from(document.querySelectorAll(selectors.join(", ")));
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
          const text = (typeof block.innerText === "string" ? block.innerText : block.textContent) || "";
          if (/Input\s*:/i.test(text)) {
            extracted = cleanInputString(text);
          } else if (isCodeforces && block.closest && block.closest(".input")) {
            extracted = text.trim();
          } else if (isHackerRank) {
            const hrParent = block.closest ? block.closest(".challenge_sample_input, .challenge-section, div") : null;
            if (hrParent && /sample\s*input/i.test(hrParent.textContent || "")) {
              extracted = cleanHackerRankSampleInput(text.trim());
            }
          }
        }
        if (extracted && !samples.includes(extracted)) {
          samples.push(extracted);
        }
      }

      // Direct fallback for HackerRank sample inputs
      if (isHackerRank && samples.length === 0) {
        const headings = Array.from(document.querySelectorAll("h1, h2, h3, h4, h5, strong, b, p"))
          .filter(el => /^sample\s+input/i.test((el.textContent || "").trim()));
        for (const h of headings) {
          let sib = h.nextElementSibling || (h.parentElement ? h.parentElement.nextElementSibling : null);
          while (sib) {
            const pre = sib.tagName === "PRE" ? sib : (sib.querySelector ? sib.querySelector("pre, code") : null);
            if (pre) {
              const val = cleanHackerRankSampleInput((pre.textContent || "").trim());
              if (val && !samples.includes(val)) samples.push(val);
              break;
            }
            sib = sib.nextElementSibling;
          }
        }
      }
    } catch {
      // Ignore DOM extraction errors safely
    }
    return samples;
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
          k.textContent = " " + normalizeLatex(ann.textContent.trim()) + " ";
          return;
        }
        const mathml = k.querySelector ? k.querySelector(".katex-mathml, math") : null;
        const katexHtml = k.querySelector ? k.querySelector(".katex-html") : null;
        if (katexHtml) {
          if (mathml && mathml.remove) mathml.remove();
          k.textContent = " " + (katexHtml.textContent || "").trim() + " ";
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
        if (tex && script.parentNode) {
          const textNode = document.createTextNode ? document.createTextNode(" " + tex + " ") : { textContent: " " + tex + " " };
          script.parentNode.replaceChild(textNode, script);
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

  // Helper to extract DOM constraints across platforms
  function extractDomConstraints() {
    const constraints = [];
    try {
      if (isLeetCode) {
        const headers = Array.from(
          document.querySelectorAll("h1, h2, h3, h4, h5, h6, p, strong, b, em, div, span")
        ).filter(el => {
          const t = (el.textContent || "").trim().toLowerCase();
          if (/^constraints:?$/i.test(t) || t.startsWith("constraints")) {
            if (el.querySelector && el.querySelector("strong, b, em, span, h1, h2, h3, h4, h5, h6")) return false;
            return true;
          }
          return false;
        });

        if (headers.length > 0) {
          const header = headers[0];
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
          for (const cand of candidates) {
            if (!cand) continue;
            const items = cand.querySelectorAll ? cand.querySelectorAll("li, p") : [];
            items.forEach(li => {
              const text = extractTextWithSuperscripts(li);
              if (text && text.length < 250 && !constraints.includes(text)) constraints.push(text);
            });
            if (constraints.length > 0) break;
          }
        }

        if (constraints.length === 0) {
          const allLis = document.querySelectorAll(
            "[data-track-load='description_content'] ul li, .elfjS ul li, div[class*='description'] ul li"
          );
          allLis.forEach(li => {
            const text = extractTextWithSuperscripts(li);
            if (text && text.length < 250 && !constraints.includes(text)) {
              const low = text.toLowerCase();
              const hasInequality = text.includes("<=") || text.includes(">=") || text.includes("≤") || text.includes("≥") || text.includes("10^") || text.includes("2^") || /\d+\s*<|\b\d+\s*<=/.test(text);
              const hasConstraintWord = low.includes("only one") || low.includes("valid answer") || low.includes("length") || low.includes("nums");
              if (hasInequality || hasConstraintWord) {
                constraints.push(text);
              }
            }
          });
        }
      } else if (isHackerRank) {
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

        // 0. Extract from authoritative HackerRank initialData script
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

          const targetSlug = (window.location.pathname.match(/\/challenges\/([^/]+)/) || [])[1] || "";
          const candidateEls = [];
          const directEl = document.getElementById("initialData") || (document.querySelector && document.querySelector("script#initialData, script[id='initialData'], #initialData"));
          if (directEl) candidateEls.push(directEl);

          if (candidateEls.length === 0 && document.querySelectorAll) {
            const allScripts = document.querySelectorAll("script[type='application/json'], script:not([src])");
            for (const s of allScripts) {
              const text = s.textContent || "";
              if (text.includes("%22challenges%22") || text.includes("%22community%22") || text.includes("%22constraints%22") || (targetSlug && text.includes(targetSlug))) {
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
                    if (!targetSlug || key.includes(targetSlug) || (det.slug && det.slug === targetSlug)) {
                      addConstraintLine(det.constraints);
                      break;
                    }
                  }
                }
                if (constraints.length === 0) {
                  for (const key of Object.keys(chMap)) {
                    const det = chMap[key] && chMap[key].detail;
                    if (det && det.constraints) {
                      addConstraintLine(det.constraints);
                      break;
                    }
                  }
                }
              }
              if (constraints.length === 0) {
                const det = findChallengeDetailInObject(initData, targetSlug);
                if (det && det.constraints) {
                  addConstraintLine(det.constraints);
                }
              }
              if (constraints.length > 0) break;
            } catch {}
          }

          // 0b. Check window.HR or window.__INITIAL_STATE__ in MAIN world
          if (constraints.length === 0 && typeof window !== "undefined") {
            const hrGlobals = [
              window.HR,
              window.__INITIAL_STATE__,
              window.__INITIAL_DATA__,
              window.__HR__,
              window.initialData,
              window.community
            ];
            for (const hrObj of hrGlobals) {
              if (hrObj && typeof hrObj === "object") {
                const det = findChallengeDetailInObject(hrObj, targetSlug);
                if (det && det.constraints) {
                  addConstraintLine(det.constraints);
                  break;
                }
              }
            }
          }

          // 0c. Check React Fiber on constraint elements in MAIN world
          if (constraints.length === 0 && typeof document !== "undefined") {
            const reactRoots = document.querySelectorAll(".challenge_constraints, .challenge-body-html, #content, [data-analytics='challenge-title']");
            for (const rEl of reactRoots) {
              const keys = Object.keys(rEl);
              const fiberKey = keys.find(k => k.startsWith("__reactFiber$") || k.startsWith("__reactInternalInstance$"));
              if (!fiberKey) continue;
              let curr = rEl[fiberKey];
              let depth = 0;
              while (curr && depth < 30) {
                if (curr.memoizedProps) {
                  const p = curr.memoizedProps;
                  if (p.constraints && typeof p.constraints === "string") {
                    addConstraintLine(p.constraints);
                    break;
                  }
                  if (p.challenge && p.challenge.constraints && typeof p.challenge.constraints === "string") {
                    addConstraintLine(p.challenge.constraints);
                    break;
                  }
                  if (p.challenge && p.challenge.attributes && typeof p.challenge.attributes.constraints === "string") {
                    addConstraintLine(p.challenge.attributes.constraints);
                    break;
                  }
                  if (p.attributes && typeof p.attributes.constraints === "string") {
                    addConstraintLine(p.attributes.constraints);
                    break;
                  }
                  const det = findChallengeDetailInObject(p, targetSlug);
                  if (det && det.constraints) {
                    addConstraintLine(det.constraints);
                    break;
                  }
                }
                if (curr.memoizedState) {
                  const det = findChallengeDetailInObject(curr.memoizedState, targetSlug);
                  if (det && det.constraints) {
                    addConstraintLine(det.constraints);
                    break;
                  }
                }
                curr = curr.return;
                depth++;
              }
              if (constraints.length > 0) break;
            }
          }

          // 0d. Check MathJax in MAIN world if present
          if (constraints.length === 0 && typeof window !== "undefined" && window.MathJax) {
            try {
              if (window.MathJax.Hub && typeof window.MathJax.Hub.getAllJax === "function") {
                const allJax = window.MathJax.Hub.getAllJax();
                for (const jax of allJax) {
                  if (jax && jax.originalText) {
                    const norm = normalizeCollapsedExponents(jax.originalText);
                    if (isConstraintText(norm)) {
                      addConstraintLine(jax.originalText);
                    }
                  }
                }
              } else if (window.MathJax.startup && window.MathJax.startup.document && window.MathJax.startup.document.math) {
                for (const item of window.MathJax.startup.document.math) {
                  if (item && item.math) {
                    const norm = normalizeCollapsedExponents(item.math);
                    if (isConstraintText(norm)) {
                      addConstraintLine(item.math);
                    }
                  }
                }
              }
            } catch {}
          }
        } catch {}

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
            const deeper = el.querySelectorAll ? Array.from(el.querySelectorAll("h1, h2, h3, h4, h5, h6, strong, b, span")).filter(sub => {
              const st = (sub.textContent || "").trim().toLowerCase();
              return st.startsWith("constraint");
            }) : [];
            return deeper.length === 0;
          });

          for (const heading of allCandidateHeadings) {
            let container = null;

            let sib = heading.nextElementSibling;
            while (sib) {
              const tag = (sib.tagName || "").toUpperCase();
              if (["H1", "H2", "H3", "H4", "H5", "H6"].includes(tag)) break;
              container = sib;
              break;
            }

            if (!container && heading.parentElement) {
              let pSib = heading.parentElement.nextElementSibling;
              while (pSib) {
                const tag = (pSib.tagName || "").toUpperCase();
                if (["H1", "H2", "H3", "H4", "H5", "H6"].includes(tag)) break;
                container = pSib;
                break;
              }
            }

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
        if (constraints.length === 0) {
          const descEl = document.querySelector(".challenge-body-html, .problem-statement, div[class*='challenge-body']");
          if (descEl) {
            const items = descEl.querySelectorAll ? descEl.querySelectorAll("script[type*='math/tex'], script[type*='latex'], mjx-container, .MathJax, .MathJax_Display, [jax], .challenge_constraints, li, p") : [];
            items.forEach(item => {
              const t = extractTextWithSuperscripts(item);
              if (isConstraintText(t) && (t.includes("<") || t.includes(">") || t.includes("≤") || t.includes("≥") || t.includes("<="))) {
                addConstraintLine(t);
              }
            });
          }
        }
      }
    } catch {}
    return constraints;
  }

  // ============================================================================
  // A. LEETCODE EXTRACTION
  // ============================================================================
  if (isLeetCode) {
    // 2. Detect language from page DOM
    let detectedPageLang = null;
    const langSelectors = [
      "button[id*='headlessui-listbox-button']",
      "button[data-cy='lang-select']",
      "div[class*='lang-select'] button",
      "[data-track-load='code_editor'] button",
      "button.rounded"
    ];

    for (const selector of langSelectors) {
      const elements = document.querySelectorAll(selector);
      for (const el of elements) {
        const text = (el.textContent || "").trim().toLowerCase();
        if (text.includes("python3") || text === "python3") {
          detectedPageLang = "python3";
          break;
        } else if (text.includes("python") || text === "python") {
          detectedPageLang = "python";
          break;
        } else if (
          text === "c++" ||
          text.includes("cpp") ||
          text === "java" ||
          text === "c" ||
          text === "c#" ||
          text.includes("javascript") ||
          text.includes("typescript") ||
          text === "go" ||
          text === "rust" ||
          text === "ruby" ||
          text === "swift" ||
          text === "kotlin"
        ) {
          detectedPageLang = text.split("\n")[0].trim();
          break;
        }
      }
      if (detectedPageLang) break;
    }

    // 3. Early reject if LeetCode language dropdown indicates non-Python
    if (detectedPageLang && !detectedPageLang.includes("python")) {
      return {
        success: false,
        platform: "leetcode",
        language: detectedPageLang,
        error: `LeetCode language is set to '${detectedPageLang}'. EdgeMind currently analyzes Python only.`
      };
    }

    // 4. Inspect Monaco global API
    if (
      typeof window.monaco === "undefined" ||
      !window.monaco.editor ||
      typeof window.monaco.editor.getModels !== "function"
    ) {
      const hasMonacoDom = Boolean(document.querySelector(".monaco-editor"));
      if (hasMonacoDom) {
        return {
          success: false,
          platform: "leetcode",
          language: detectedPageLang || "unknown",
          error: "Monaco editor detected, but its editor models are still initializing. Please wait a moment and try again."
        };
      }

      return {
        success: false,
        platform: "leetcode",
        language: detectedPageLang || "unknown",
        error: "LeetCode code editor could not be found. Please ensure a problem page is open and fully loaded."
      };
    }

    // 5. Inspect active Monaco editor instance before querying background models
    let activeEditorLang = null;
    let activeEditorModel = null;
    if (typeof window.monaco.editor.getEditors === "function") {
      const editors = window.monaco.editor.getEditors();
      if (editors && editors.length > 0 && typeof editors[0].getModel === "function") {
        activeEditorModel = editors[0].getModel();
        if (activeEditorModel) {
          activeEditorLang = (
            typeof activeEditorModel.getLanguageId === "function"
              ? activeEditorModel.getLanguageId()
              : typeof activeEditorModel.getModeId === "function"
              ? activeEditorModel.getModeId()
              : ""
          ).toLowerCase();
        }
      }
    }

    if (activeEditorLang && !activeEditorLang.includes("python") && activeEditorLang !== "plaintext") {
      return {
        success: false,
        platform: "leetcode",
        language: activeEditorLang,
        error: `Active editor model language is '${activeEditorLang}'. EdgeMind currently analyzes Python only.`
      };
    }

    // 6. Query all active Monaco editor models
    const models = window.monaco.editor.getModels();
    if (!models || models.length === 0) {
      return {
        success: false,
        platform: "leetcode",
        language: detectedPageLang || "unknown",
        error: "No active Monaco editor models found. The editor may still be initializing."
      };
    }

    const pythonModels = [];
    const nonPythonModels = [];
    const testcaseModels = [];

    for (const model of models) {
      const langId = (
        typeof model.getLanguageId === "function"
          ? model.getLanguageId()
          : typeof model.getModeId === "function"
          ? model.getModeId()
          : ""
      ).toLowerCase();

      const uriStr = model.uri ? model.uri.toString().toLowerCase() : "";

      // Testcase / console buffer models
      if (
        uriStr.includes("testcase") ||
        uriStr.includes("console") ||
        uriStr.includes("input")
      ) {
        const val = (model.getValue() || "").trim();
        if (val) {
          testcaseModels.push({ uri: uriStr, value: val });
        }
        continue;
      }

      if (langId === "python" || langId === "python3") {
        pythonModels.push(model);
      } else if (langId && langId !== "plaintext") {
        nonPythonModels.push({ model, langId });
      }
    }

    // Reject if non-Python models exist and active editor is not verified Python
    if (nonPythonModels.length > 0) {
      if (!activeEditorModel || !activeEditorLang || !activeEditorLang.includes("python")) {
        const nonPyLang = (activeEditorLang && activeEditorLang !== "plaintext") ? activeEditorLang : nonPythonModels[0].langId;
        return {
          success: false,
          platform: "leetcode",
          language: nonPyLang,
          error: `Detected non-Python editor language ('${nonPyLang}'). EdgeMind currently analyzes Python only.`
        };
      }
    }

    const domSampleInputs = extractDomSamples();
    const domConstraints = extractDomConstraints();

    // Case A: Active editor has a verified Python model
    if (activeEditorModel && activeEditorLang && activeEditorLang.includes("python")) {
      const code = activeEditorModel.getValue();
      return {
        success: true,
        platform: "leetcode",
        code: code,
        language: activeEditorLang,
        modelUri: activeEditorModel.uri ? activeEditorModel.uri.toString() : "",
        testcaseBuffers: testcaseModels.map(m => m.value),
        domSampleInputs: domSampleInputs,
        domConstraints: domConstraints
      };
    }

    // Case B: Exactly one Python model exists
    if (pythonModels.length === 1) {
      const targetModel = pythonModels[0];
      const code = targetModel.getValue();
      return {
        success: true,
        platform: "leetcode",
        code: code,
        language: "python3",
        modelUri: targetModel.uri ? targetModel.uri.toString() : "",
        testcaseBuffers: testcaseModels.map(m => m.value),
        domSampleInputs: domSampleInputs,
        domConstraints: domConstraints
      };
    }

    // Case C: Multiple Python models exist
    if (pythonModels.length > 1) {
      return {
        success: false,
        platform: "leetcode",
        language: "python",
        error: `Multiple Python editor models found (${pythonModels.length}). Cannot safely determine active solution buffer.`
      };
    }

    return {
      success: false,
      platform: "leetcode",
      language: detectedPageLang || "unknown",
      error: "No Python code found in LeetCode editor. Please select Python3 and write your solution."
    };
  }

  // ============================================================================
  // B. HACKERRANK EXTRACTION
  // ============================================================================
  if (isHackerRank) {
    let detectedHrLang = "unknown";
    const hrLangSelectors = [
      "div[class*='select-language']",
      ".select-language select",
      "select[class*='select-language']",
      "button[class*='select-language']",
      ".Select-value-label",
      "[data-analytics='LanguageDropdown']",
      "[data-testid='language-dropdown']",
      ".select__single-value",
      "div[class*='singleValue']",
      "[aria-label*='language' i]"
    ];

    for (const selector of hrLangSelectors) {
      const el = document.querySelector(selector);
      if (el) {
        const text = (el.textContent || el.value || "").trim().toLowerCase();
        if (text) {
          if (text.includes("python 3") || text.includes("python3") || text === "pypy 3") {
            detectedHrLang = "python3";
            break;
          } else if (text.includes("python")) {
            detectedHrLang = "python";
            break;
          } else if (["c++", "cpp", "java", "c", "c#", "javascript", "go", "ruby", "rust"].some(l => text.includes(l))) {
            detectedHrLang = text.split("\n")[0].trim();
            break;
          }
        }
      }
    }

    // Helper to query all DOM roots (main document + same-origin iframes + shadow roots)
    function queryAllRoots(selector, root = document, visited = new Set()) {
      if (!root || visited.has(root)) return [];
      visited.add(root);
      let results = [];
      try {
        if (typeof root.querySelectorAll === "function") {
          results = Array.from(root.querySelectorAll(selector));
        }
      } catch {}

      // Traverse shadow roots and same-origin iframes safely
      try {
        if (typeof root.querySelectorAll === "function") {
          const iframes = root.querySelectorAll("iframe");
          for (const iframe of iframes) {
            try {
              if (iframe.contentDocument) {
                results = results.concat(queryAllRoots(selector, iframe.contentDocument, visited));
              }
            } catch {}
          }
          const shadowHosts = root.querySelectorAll("[data-shadow], [class*='shadow'], hr-app, div[id*='root'], div[id*='app']");
          for (const host of shadowHosts) {
            if (host.shadowRoot) {
              results = results.concat(queryAllRoots(selector, host.shadowRoot, visited));
            }
          }
        }
      } catch {}
      return results;
    }

    let code = "";
    let editorType = "unknown";

    // Tier 1: Monaco Global / Editor Instance
    if (typeof window.monaco !== "undefined" && window.monaco.editor) {
      if (typeof window.monaco.editor.getEditors === "function") {
        const editors = window.monaco.editor.getEditors();
        for (const ed of editors) {
          if (ed && typeof ed.getValue === "function") {
            const val = ed.getValue();
            if (val && val.trim()) {
              code = val;
              editorType = "monaco_active_editor";
              const model = typeof ed.getModel === "function" ? ed.getModel() : null;
              if (model) {
                const mId = (typeof model.getLanguageId === "function" ? model.getLanguageId() : (typeof model.getModeId === "function" ? model.getModeId() : "")).toLowerCase();
                if (mId.includes("python")) detectedHrLang = "python3";
              }
              break;
            }
          }
        }
      }
      if (!code && typeof window.monaco.editor.getModels === "function") {
        const models = window.monaco.editor.getModels();
        if (models && models.length > 0) {
          for (const model of models) {
            const langId = (
              typeof model.getLanguageId === "function"
                ? model.getLanguageId()
                : typeof model.getModeId === "function"
                ? model.getModeId()
                : ""
            ).toLowerCase();

            if (langId.includes("python") || models.length === 1) {
              code = model.getValue();
              editorType = "monaco";
              if (detectedHrLang === "unknown" && langId.includes("python")) {
                detectedHrLang = "python3";
              }
              break;
            }
          }
        }
      }
    }

    // Tier 2: Ace Editor (HackerRank's primary challenge editor)
    if (!code) {
      const aceEls = queryAllRoots(".ace_editor, [class*='ace_editor'], #editor, #codeeditor, #code-editor, .code-editor, .challenge-editor");
      for (const aceEl of aceEls) {
        // A. Check env.editor
        if (aceEl.env && aceEl.env.editor && typeof aceEl.env.editor.getValue === "function") {
          try {
            code = aceEl.env.editor.getValue();
            editorType = "ace";
            if (detectedHrLang === "unknown" && typeof aceEl.env.editor.getSession === "function") {
              const session = aceEl.env.editor.getSession();
              const modeId = session && session.getMode && session.getMode().$id ? session.getMode().$id.toLowerCase() : "";
              if (modeId.includes("python")) detectedHrLang = "python3";
            }
            if (code && code.trim()) break;
          } catch {}
        }

        // B. Check aceEl.editor
        if (!code && aceEl.editor && typeof aceEl.editor.getValue === "function") {
          try {
            code = aceEl.editor.getValue();
            editorType = "ace";
            if (detectedHrLang === "unknown" && typeof aceEl.editor.getSession === "function") {
              const session = aceEl.editor.getSession();
              const modeId = session && session.getMode && session.getMode().$id ? session.getMode().$id.toLowerCase() : "";
              if (modeId.includes("python")) detectedHrLang = "python3";
            }
            if (code && code.trim()) break;
          } catch {}
        }

        // C. Check aceEl._ace or aceEl.aceEditor
        if (!code && aceEl._ace && typeof aceEl._ace.getValue === "function") {
          try {
            code = aceEl._ace.getValue();
            editorType = "ace";
            if (code && code.trim()) break;
          } catch {}
        }

        // D. Check window.ace.edit(aceEl)
        if (!code && typeof window.ace !== "undefined" && typeof window.ace.edit === "function") {
          try {
            const ed = window.ace.edit(aceEl);
            if (ed && typeof ed.getValue === "function") {
              code = ed.getValue();
              editorType = "ace";
              if (detectedHrLang === "unknown" && typeof ed.getSession === "function") {
                const session = ed.getSession();
                const modeId = session && session.getMode && session.getMode().$id ? session.getMode().$id.toLowerCase() : "";
                if (modeId.includes("python")) detectedHrLang = "python3";
              }
              if (code && code.trim()) break;
            }
          } catch {}
        }

        // E. Check React Fiber on aceEl or parents
        if (!code) {
          try {
            const reactKey = Object.keys(aceEl).find(k => k.startsWith("__reactFiber") || k.startsWith("__reactInternalInstance"));
            if (reactKey && aceEl[reactKey]) {
              let fiber = aceEl[reactKey];
              let depth = 0;
              while (fiber && depth < 10) {
                if (fiber.memoizedProps && fiber.memoizedProps.editor && typeof fiber.memoizedProps.editor.getValue === "function") {
                  code = fiber.memoizedProps.editor.getValue();
                  editorType = "ace_react_fiber";
                  break;
                }
                if (fiber.memoizedProps && typeof fiber.memoizedProps.value === "string" && fiber.memoizedProps.value.trim()) {
                  code = fiber.memoizedProps.value;
                  editorType = "ace_react_props";
                  break;
                }
                if (fiber.stateNode && fiber.stateNode.editor && typeof fiber.stateNode.editor.getValue === "function") {
                  code = fiber.stateNode.editor.getValue();
                  editorType = "ace_react_state";
                  break;
                }
                fiber = fiber.return;
                depth++;
              }
              if (code && code.trim()) break;
            }
          } catch {}
        }
      }

      // Check global window.ace by ID if still not found
      if (!code && typeof window.ace !== "undefined" && typeof window.ace.edit === "function") {
        for (const id of ["editor", "codeeditor", "code-editor", "custom-code-editor", "challenge-editor"]) {
          try {
            const ed = window.ace.edit(id);
            if (ed && typeof ed.getValue === "function") {
              code = ed.getValue();
              if (code && code.trim()) {
                editorType = "ace";
                break;
              }
            }
          } catch {}
        }
      }

      // Check global window variables
      if (!code) {
        for (const g of [window.editor, window.codeEditor, window.hr_editor]) {
          if (g && typeof g.getValue === "function") {
            try {
              const val = g.getValue();
              if (val && val.trim()) {
                code = val;
                editorType = "ace_window_global";
                break;
              }
            } catch {}
          }
        }
      }
    }

    // Tier 3: CodeMirror (CM5 & CM6)
    if (!code) {
      // CM5
      const cmEls = queryAllRoots(".CodeMirror");
      for (const cmEl of cmEls) {
        if (cmEl.CodeMirror && typeof cmEl.CodeMirror.getValue === "function") {
          code = cmEl.CodeMirror.getValue();
          editorType = "codemirror";
          break;
        }
      }
      // CM6
      if (!code) {
        const cm6Els = queryAllRoots(".cm-editor");
        for (const cm6El of cm6Els) {
          if (cm6El.cmView && cm6El.cmView.state && cm6El.cmView.state.doc && typeof cm6El.cmView.state.doc.toString === "function") {
            code = cm6El.cmView.state.doc.toString();
            editorType = "codemirror6";
            break;
          }
        }
      }
    }

    // Tier 4: Textarea Fallback (excluding custominput and ace_text-input)
    if (!code) {
      const textareas = queryAllRoots("textarea[class*='code'], textarea[name='code'], textarea[id*='code'], textarea[class*='editor']:not(.ace_text-input):not(.custominput)");
      for (const ta of textareas) {
        if (ta && ta.value && ta.value.trim() && !ta.classList.contains("ace_text-input") && !ta.classList.contains("custominput")) {
          code = ta.value;
          editorType = "textarea";
          break;
        }
      }
    }

    // Tier 5: DOM Line Elements Fallback (Never treat a visible editor as empty!)
    if (!code) {
      // Check visible Ace lines
      const aceLines = queryAllRoots(".ace_editor .ace_line, .ace_line");
      if (aceLines.length > 0) {
        const lineTexts = aceLines.map(l => (typeof l.innerText === "string" ? l.innerText : (l.textContent || "")));
        const joined = lineTexts.join("\n");
        if (joined.trim()) {
          code = joined;
          editorType = "ace_dom_lines";
        }
      }

      // Check visible Monaco lines
      if (!code) {
        const monacoLines = queryAllRoots(".monaco-editor .view-line, .view-line");
        if (monacoLines.length > 0) {
          const lineTexts = monacoLines.map(l => (typeof l.innerText === "string" ? l.innerText : (l.textContent || "")));
          const joined = lineTexts.join("\n");
          if (joined.trim()) {
            code = joined;
            editorType = "monaco_dom_lines";
          }
        }
      }

      // Check visible CM6 / CM5 lines
      if (!code) {
        const cmLines = queryAllRoots(".cm-editor .cm-line, .CodeMirror-line");
        if (cmLines.length > 0) {
          const lineTexts = cmLines.map(l => (typeof l.innerText === "string" ? l.innerText : (l.textContent || "")));
          const joined = lineTexts.join("\n");
          if (joined.trim()) {
            code = joined;
            editorType = "cm_dom_lines";
          }
        }
      }
    }

    // If language was not detected from dropdown or session mode, inspect extracted code
    if (detectedHrLang === "unknown" && code) {
      if (/\b(?:def |import |class |print\(|if __name__ == '__main__':)/.test(code)) {
        detectedHrLang = "python3";
      }
    }

    // Language rejection if explicitly non-Python
    if (detectedHrLang !== "unknown" && !detectedHrLang.includes("python")) {
      return {
        success: false,
        platform: "hackerrank",
        language: detectedHrLang,
        error: `HackerRank language is set to '${detectedHrLang}'. EdgeMind currently analyzes Python only.`
      };
    }

    // Check if an editor element exists in the DOM to provide helpful error
    const hasEditorDom = Boolean(
      queryAllRoots(".ace_editor, [class*='ace_editor'], .monaco-editor, .cm-editor, .CodeMirror, textarea[class*='code'], textarea[name='code'], textarea[class*='editor']:not(.ace_text-input):not(.custominput)").length > 0 ||
      (typeof window.monaco !== "undefined" && window.monaco.editor) ||
      (typeof window.ace !== "undefined")
    );

    if (!code || !code.trim()) {
      if (hasEditorDom) {
        return {
          success: false,
          platform: "hackerrank",
          editorAvailable: true,
          language: detectedHrLang,
          error: "HackerRank code editor is empty. Please enter or reset your Python solution before analyzing."
        };
      }
      return {
        success: false,
        platform: "hackerrank",
        editorAvailable: false,
        language: detectedHrLang,
        error: "HackerRank code editor could not be found. Please ensure the challenge editor is loaded."
      };
    }

    const domSampleInputs = extractDomSamples();
    const domConstraints = extractDomConstraints();

    return {
      success: true,
      platform: "hackerrank",
      code: code,
      language: detectedHrLang.includes("python") ? detectedHrLang : "python3",
      editorType: editorType,
      domSampleInputs: domSampleInputs,
      domConstraints: domConstraints
    };
  }

  // ============================================================================
  // C. CODEFORCES EXTRACTION
  // ============================================================================
  if (isCodeforces) {
    let detectedCfLang = "unknown";
    const cfLangSelect = document.querySelector("select[name='programTypeId'], select#programTypeId, select[name*='programType'], select[name*='language']");
    if (cfLangSelect && cfLangSelect.options && cfLangSelect.selectedIndex >= 0) {
      const text = (cfLangSelect.options[cfLangSelect.selectedIndex].text || "").toLowerCase();
      if (text.includes("python 3") || text.includes("pypy 3")) {
        detectedCfLang = "python3";
      } else if (text.includes("python")) {
        detectedCfLang = "python";
      } else if (text) {
        detectedCfLang = (cfLangSelect.options[cfLangSelect.selectedIndex].text || "").trim();
      }
    }

    if (detectedCfLang !== "unknown" && !detectedCfLang.toLowerCase().includes("python")) {
      return {
        success: false,
        platform: "codeforces",
        language: detectedCfLang,
        error: `Codeforces selected language is '${detectedCfLang}'. EdgeMind currently analyzes Python only.`
      };
    }

    const domSampleInputs = extractDomSamples();
    const domConstraints = extractDomConstraints();

    // Check problem selection on Codeforces submit pages
    const isSubmitPage = (window.location.pathname || "").includes("/submit") || Boolean(document.querySelector("form.submit-form"));
    let cfProblemSelected = true;
    if (isSubmitPage) {
      const idxSelect = document.querySelector("select[name='submittedProblemIndex'], select[name*='problemIndex']");
      const codeInput = document.querySelector("input[name='submittedProblemCode'], input[name*='problemCode']");
      if (idxSelect && idxSelect.options && idxSelect.selectedIndex >= 0) {
        const opt = idxSelect.options[idxSelect.selectedIndex];
        const val = (idxSelect.value || (opt && opt.value) || "").trim();
        if (!val || /^(?:choose|select|none)\b|^\s*$/i.test(val)) {
          cfProblemSelected = false;
        }
      } else if (codeInput) {
        const val = (codeInput.value || "").trim();
        if (!val) {
          cfProblemSelected = false;
        }
      }
    }

    if (isSubmitPage && !cfProblemSelected) {
      return {
        success: false,
        platform: "codeforces",
        problemSelected: false,
        editorAvailable: true,
        language: detectedCfLang,
        error: "No problem selected on the Codeforces submission page. Please select a problem from the dropdown or enter a problem code.",
        domSampleInputs: domSampleInputs,
        domConstraints: domConstraints
      };
    }

    let code = "";
    let editorType = "unknown";

    // 1. Check embedded ACE editor
    const aceEl = document.querySelector(".ace_editor");
    if (aceEl && typeof window.ace !== "undefined" && typeof window.ace.edit === "function") {
      try {
        const ed = window.ace.edit(aceEl);
        if (ed && typeof ed.getValue === "function") {
          code = ed.getValue();
          editorType = "ace";
        }
      } catch {}
    }

    // 2. Check embedded CodeMirror
    if (!code) {
      const cmEl = document.querySelector(".CodeMirror");
      if (cmEl && cmEl.CodeMirror && typeof cmEl.CodeMirror.getValue === "function") {
        code = cmEl.CodeMirror.getValue();
        editorType = "codemirror";
      }
    }

    // 3. Check embedded Monaco
    if (!code && typeof window.monaco !== "undefined" && window.monaco.editor && typeof window.monaco.editor.getModels === "function") {
      const models = window.monaco.editor.getModels();
      if (models && models.length > 0) {
        code = models[0].getValue();
        editorType = "monaco";
      }
    }

    // 4. Check submit textarea (#sourceCodeTextarea, textarea[name='source'], textarea.source)
    if (!code) {
      const ta = document.querySelector("#sourceCodeTextarea, textarea[name='source'], textarea.source, textarea[id*='source'], textarea[name*='code']");
      if (ta && ta.value) {
        code = ta.value;
        editorType = "textarea";
      }
    }

    // Check if an editor or textarea element exists in the DOM
    const hasEditorDom = Boolean(
      document.querySelector(".ace_editor, .CodeMirror, #sourceCodeTextarea, textarea[name='source'], textarea.source, textarea[id*='source'], textarea[name*='code']") ||
      (typeof window.monaco !== "undefined" && window.monaco.editor && typeof window.monaco.editor.getModels === "function")
    );

    // If no code editor found on Codeforces problem page, handle gracefully
    if (!hasEditorDom) {
      return {
        success: false,
        platform: "codeforces",
        editorAvailable: false,
        problemSelected: cfProblemSelected,
        language: detectedCfLang,
        error: "No active code editor detected on this Codeforces page. Open the Submit page or paste your Python solution into EdgeMind.",
        domSampleInputs: domSampleInputs,
        domConstraints: domConstraints
      };
    }

    // If editor exists but is empty
    if (!code || !code.trim()) {
      return {
        success: false,
        platform: "codeforces",
        editorAvailable: true,
        problemSelected: cfProblemSelected,
        language: detectedCfLang,
        error: "Codeforces code editor is empty. Please enter your Python solution before analyzing.",
        domSampleInputs: domSampleInputs,
        domConstraints: domConstraints
      };
    }

    return {
      success: true,
      platform: "codeforces",
      editorAvailable: true,
      problemSelected: cfProblemSelected,
      code: code,
      language: detectedCfLang.toLowerCase().includes("python") ? detectedCfLang : "python3",
      editorType: editorType,
      domSampleInputs: domSampleInputs,
      domConstraints: domConstraints
    };
  }

  return {
    success: false,
    error: "Unsupported platform."
  };
})();
