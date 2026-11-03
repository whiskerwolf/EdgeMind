/**
 * EdgeMind Extension Popup Controller.
 *
 * Coordinates:
 * - API health verification (GET /health)
 * - Page metadata extraction via content script
 * - Solution code & Monaco buffer extraction via MAIN-world script injection
 * - Client-side validation (Python language check, 64 KiB size bound)
 * - EdgeMind Adaptive Test Intelligence dispatch (POST /api/v1/edgemind/analyze)
 * - Safe DOM rendering using textContent and createElement
 */
(() => {
  "use strict";

  // Configuration constants
  const API_BASE_URL = "http://127.0.0.1:8000";
  const MAX_SOURCE_SIZE = 64 * 1024; // 64 KiB
  const REQUEST_TIMEOUT_MS = 10000;

  // DOM Elements
  const elApiStatus = document.getElementById("api-status");
  const elApiStatusText = document.getElementById("api-status-text");
  const elPageTitle = document.getElementById("page-title");
  const elLangBadge = document.getElementById("lang-badge");
  const elConstraintsBadge = document.getElementById("constraints-badge");
  const elSamplesCountBadge = document.getElementById("samples-count-badge");
  const elBtnToggleSamples = document.getElementById("btn-toggle-samples");
  const elSamplesBody = document.getElementById("samples-body");
  const elSamplesDetectedBadge = document.getElementById("samples-detected-badge");
  const elSamplesFoundCount = document.getElementById("samples-found-count");
  const elSamplesSourceValue = document.getElementById("samples-source-value");
  const elSamplesEmptyMsg = document.getElementById("samples-empty-msg");
  const elSamplesList = document.getElementById("samples-list");
  let detectedSampleInputs = [];
  const elBtnAnalyze = document.getElementById("btn-analyze");
  const elLoadingState = document.getElementById("loading-state");
  const elLoadingMessage = document.getElementById("loading-message");
  const elErrorBanner = document.getElementById("error-banner");
  const elErrorMessage = document.getElementById("error-message");
  const elEmptyState = document.getElementById("empty-state");
  const elResultsSection = document.getElementById("results-section");

  // Mode Banner & Status Elements
  const elModeBanner = document.getElementById("mode-banner");
  const elModeTitle = document.getElementById("mode-title");
  const elModeBadge = document.getElementById("mode-badge");
  const elModeExamplesCount = document.getElementById("mode-examples-count");
  const elModeContextStatus = document.getElementById("mode-context-status");
  const elModeConstraintsStatus = document.getElementById("mode-constraints-status");
  const elModeParametersIdentified = document.getElementById("mode-parameters-identified");
  const elContextModeDisclaimer = document.getElementById("context-mode-disclaimer");
  const elGapsSectionTitle = document.getElementById("gaps-section-title");
  const elCandidatesSectionTitle = document.getElementById("candidates-section-title");
  const elStatGapsLabel = document.getElementById("stat-gaps-label");
  const elNoGapsText = document.getElementById("no-gaps-text");

  // Tabs
  const elTabBtnIntel = document.getElementById("tab-btn-intel");
  const elTabBtnCode = document.getElementById("tab-btn-code");
  const elPanelIntel = document.getElementById("panel-intel");
  const elPanelCode = document.getElementById("panel-code");
  const elBadgeGapsCount = document.getElementById("badge-gaps-count");
  const elBadgeCodeScore = document.getElementById("badge-code-score");

  // Intel panel elements
  const elStatGaps = document.getElementById("stat-gaps");
  const elStatCandidates = document.getElementById("stat-candidates");
  const elStatDedup = document.getElementById("stat-dedup");
  const elGapsList = document.getElementById("gaps-list");
  const elGapsSubhead = document.getElementById("gaps-subhead");
  const elNoGapsMsg = document.getElementById("no-gaps-msg");
  const elCandidatesList = document.getElementById("candidates-list");
  const elCandidatesSubhead = document.getElementById("candidates-subhead");
  const elNoCandidatesMsg = document.getElementById("no-candidates-msg");
  const elBtnToggleAllGaps = document.getElementById("btn-toggle-all-gaps");
  const elBtnToggleAllCandidates = document.getElementById("btn-toggle-all-candidates");

  let allGapsData = [];
  let isAllGapsExpanded = false;
  let allCandidatesData = [];
  let isAllCandidatesExpanded = false;
  let currentAnalysisMode = "BASELINE_DRIVEN";
  const elBtnTogglePatterns = document.getElementById("btn-toggle-patterns");
  const elPatternsBody = document.getElementById("patterns-body");
  const elPatternsContent = document.getElementById("patterns-content");

  // Code Health elements
  const elScoreValue = document.getElementById("score-value");
  const elOverallStatusBadge = document.getElementById("overall-status-badge");
  const elErrorsCount = document.getElementById("errors-count");
  const elWarningsCount = document.getElementById("warnings-count");
  const elSectionPills = document.getElementById("section-pills");
  const elFindingsList = document.getElementById("findings-list");
  const elNoFindingsMessage = document.getElementById("no-findings-message");
  const elFindingsTitle = document.getElementById("findings-title");

  let currentTab = null;
  let detectedPageInfo = null;

  /**
   * Normalize LaTeX macros, formatting wrappers, and spacing commands.
   */
  function normalizeLatex(str) {
    if (!str || typeof str !== "string") return "";
    let s = str;
    s = s.replace(/\\le\b|\\leq\b/g, "<=");
    s = s.replace(/\\ge\b|\\geq\b/g, ">=");
    s = s.replace(/\\times\b|\\cdot\b/g, "*");
    s = s.replace(/\\ne\b|\\neq\b/g, "!=");
    s = s.replace(/\\quad\b/g, " ");
    s = s.replace(/\\qquad\b/g, " ");
    s = s.replace(/\\[,;:! ]/g, " ");
    s = s.replace(/~/g, " ");
    s = s.replace(/\^\{([+-]?\d+)\}/g, "^$1");

    const wrapperPattern = /\\?(?:text|textbf|textit|mathrm|mathbf|mathit|mathtt|operatorname|math[a-zA-Z]*)\{([^{}]*)\}/g;
    for (let i = 0; i < 10; i++) {
      const prev = s;
      s = s.replace(wrapperPattern, "$1");
      if (prev === s) break;
    }

    s = s.replace(/≤|\u2264/g, "<=").replace(/≥|\u2265/g, ">=").replace(/−|\u2212/g, "-");
    return s.replace(/[ \t]+/g, " ").trim();
  }

  /**
   * Normalize collapsed exponents from scrapers or flattened DOM (e.g. -109 -> -10^9, 104 -> 10^4).
   */
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
    s = s.replace(/(^|[<>=,\s([-])231\b/g, "$12^31");
    s = s.replace(/(^|[<>=,\s([-])10([3-9])\b/g, "$110^$2");
    s = s.replace(/[ \t]+/g, " ").trim();
    return s;
  }

  /**
   * Validate whether a string is a meaningful problem title (rejects "-", empty, or generic placeholders).
   */
  function isValidTitle(t) {
    if (!t || typeof t !== "string") return false;
    const s = t.trim();
    if (s.length < 2 || s.length > 150) return false;
    if (s === "-" || s === "—" || s === "–" || s.toLowerCase() === "leetcode") return false;
    if (s.toLowerCase().includes("detecting")) return false;
    return /[a-zA-Z]{2,}/.test(s);
  }

  /**
   * Derive a reliable fallback title from Chrome tab or URL slug.
   */
  function getFallbackTitle(tab) {
    if (!tab) return "LeetCode Problem";
    if (tab.title) {
      const cleaned = tab.title.replace(/\s*-\s*LeetCode.*$/i, "").trim();
      if (isValidTitle(cleaned)) return cleaned;
    }
    if (tab.url) {
      const urlMatch = tab.url.match(/problems\/([^/]+)/);
      if (urlMatch && urlMatch[1]) {
        const slugTitle = urlMatch[1].split("-").map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(" ");
        if (isValidTitle(slugTitle)) return slugTitle;
      }
    }
    return "LeetCode Problem";
  }


  /**
   * Safe helper to remove all children from a DOM container.
   */
  function clearElement(element) {
    while (element.firstChild) {
      element.removeChild(element.firstChild);
    }
  }

  const SVG_NS = "http://www.w3.org/2000/svg";

  /**
   * Safe helper to create SVG icons via DOM API (pure DOM manipulation).
   */
  function createSvgIcon(name, extraClass = "", size = 13) {
    const svg = document.createElementNS(SVG_NS, "svg");
    svg.setAttribute("width", String(size));
    svg.setAttribute("height", String(size));
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("fill", "none");
    svg.setAttribute("stroke", "currentColor");
    svg.setAttribute("stroke-width", "2");
    svg.setAttribute("stroke-linecap", "round");
    svg.setAttribute("stroke-linejoin", "round");
    svg.setAttribute("aria-hidden", "true");
    if (extraClass) {
      svg.setAttribute("class", extraClass);
    }

    if (name === "check") {
      const path = document.createElementNS(SVG_NS, "path");
      path.setAttribute("d", "M20 6L9 17l-5-5");
      svg.appendChild(path);
    } else if (name === "alert") {
      const path1 = document.createElementNS(SVG_NS, "path");
      path1.setAttribute("d", "M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z");
      const line1 = document.createElementNS(SVG_NS, "line");
      line1.setAttribute("x1", "12");
      line1.setAttribute("y1", "9");
      line1.setAttribute("x2", "12");
      line1.setAttribute("y2", "13");
      const line2 = document.createElementNS(SVG_NS, "line");
      line2.setAttribute("x1", "12");
      line2.setAttribute("y1", "17");
      line2.setAttribute("x2", "12.01");
      line2.setAttribute("y2", "17");
      svg.appendChild(path1);
      svg.appendChild(line1);
      svg.appendChild(line2);
    } else if (name === "help") {
      const circle = document.createElementNS(SVG_NS, "circle");
      circle.setAttribute("cx", "12");
      circle.setAttribute("cy", "12");
      circle.setAttribute("r", "10");
      const path = document.createElementNS(SVG_NS, "path");
      path.setAttribute("d", "M9.09 9a3 3 0 015.83 1c0 2-3 3-3 3");
      const line = document.createElementNS(SVG_NS, "line");
      line.setAttribute("x1", "12");
      line.setAttribute("y1", "17");
      line.setAttribute("x2", "12.01");
      line.setAttribute("y2", "17");
      svg.appendChild(circle);
      svg.appendChild(path);
      svg.appendChild(line);
    } else if (name === "copy") {
      const rect = document.createElementNS(SVG_NS, "rect");
      rect.setAttribute("x", "9");
      rect.setAttribute("y", "9");
      rect.setAttribute("width", "13");
      rect.setAttribute("height", "13");
      rect.setAttribute("rx", "2");
      rect.setAttribute("ry", "2");
      const path = document.createElementNS(SVG_NS, "path");
      path.setAttribute("d", "M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1");
      svg.appendChild(rect);
      svg.appendChild(path);
    } else if (name === "spark") {
      const path = document.createElementNS(SVG_NS, "path");
      path.setAttribute("d", "M13 2L3 14h9l-1 8 10-12h-9l1-8z");
      path.setAttribute("fill", "currentColor");
      path.setAttribute("stroke-width", "1.5");
      svg.appendChild(path);
    } else if (name === "chevron-down") {
      const polyline = document.createElementNS(SVG_NS, "polyline");
      polyline.setAttribute("points", "6 9 12 15 18 9");
      svg.appendChild(polyline);
    } else if (name === "chevron-up") {
      const polyline = document.createElementNS(SVG_NS, "polyline");
      polyline.setAttribute("points", "18 15 12 9 6 15");
      svg.appendChild(polyline);
    } else if (name === "chevron-right") {
      const polyline = document.createElementNS(SVG_NS, "polyline");
      polyline.setAttribute("points", "9 18 15 12 9 6");
      svg.appendChild(polyline);
    }

    return svg;
  }

  /**
   * Set API connection status indicator.
   * Supports 'connected', 'offline', 'connecting', 'error'.
   */
  function setApiStatus(status, text) {
    elApiStatus.className = `api-status ${status}`;
    elApiStatusText.textContent = text;
    elApiStatus.title = `EdgeMind API: ${text}`;
  }

  /**
   * Display or hide error banner safely.
   */
  function showError(message) {
    if (!message) {
      elErrorBanner.classList.add("hidden");
      clearElement(elErrorMessage);
      return;
    }
    clearElement(elErrorMessage);
    const p = document.createElement("p");
    p.textContent = String(message);
    elErrorMessage.appendChild(p);
    elErrorBanner.classList.remove("hidden");
  }

  function hideError() {
    showError(null);
  }

  /**
   * Toggle loading spinner state.
   */
  function setLoading(isLoading, message) {
    if (isLoading) {
      elLoadingMessage.textContent = message || "Running EdgeMind analysis...";
      elLoadingState.classList.remove("hidden");
      elBtnAnalyze.disabled = true;
      hideError();
      elEmptyState.classList.add("hidden");
      elResultsSection.classList.add("hidden");
    } else {
      elLoadingState.classList.add("hidden");
      elBtnAnalyze.disabled = false;
    }
  }

  /**
   * Verify whether EdgeMind API is reachable.
   */
  async function checkApiHealth() {
    setApiStatus("connecting", "Connecting");
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 2500);

    try {
      const response = await fetch(`${API_BASE_URL}/health`, {
        method: "GET",
        signal: controller.signal
      });
      clearTimeout(timeoutId);

      if (response.ok) {
        let isHealthy = false;
        try {
          const data = await response.json();
          if (data && data.status === "healthy") {
            isHealthy = true;
          }
        } catch {
          // Response body was not JSON
        }
        if (isHealthy) {
          setApiStatus("connected", "Connected");
          return true;
        } else {
          setApiStatus("error", "Error");
          return false;
        }
      }
      setApiStatus("error", "Error");
      return false;
    } catch {
      clearTimeout(timeoutId);
      setApiStatus("offline", "Offline");
      return false;
    }
  }

  /**
   * Inspect active tab and extract LeetCode page metadata.
   */
  async function inspectActiveTab() {
    try {
      const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
      if (!tabs || tabs.length === 0) {
        elPageTitle.textContent = "No active tab";
        if (elSamplesSourceValue) {
          elSamplesSourceValue.textContent = "Unavailable — Open a LeetCode problem";
        }
        if (elSamplesEmptyMsg) {
          elSamplesEmptyMsg.textContent = "Unavailable — Open a LeetCode problem page.";
        }
        return null;
      }

      currentTab = tabs[0];
      const url = currentTab.url || "";

      if (url.includes("leetcode.com")) {
        elBtnAnalyze.disabled = false;
        elBtnAnalyze.title = "";
        const fallbackTitle = getFallbackTitle(currentTab);
        elPageTitle.textContent = fallbackTitle;
        elPageTitle.title = fallbackTitle;
        elLangBadge.className = "badge badge-neutral";
        elLangBadge.textContent = "Detecting...";
        if (elSamplesSourceValue) {
          elSamplesSourceValue.textContent = "LeetCode Public Examples";
        }
        if (elSamplesEmptyMsg) {
          elSamplesEmptyMsg.textContent = "No public examples detected on this problem page.";
        }

        // Query content script for deeper problem info
        try {
          chrome.tabs.sendMessage(currentTab.id, { action: "GET_PROBLEM_INFO" }, response => {
            if (chrome.runtime.lastError || !response) {
              return;
            }
            detectedPageInfo = response;
            if (isValidTitle(response.title)) {
              elPageTitle.textContent = response.title;
              elPageTitle.title = response.title;
            } else if (!isValidTitle(elPageTitle.textContent)) {
              elPageTitle.textContent = fallbackTitle;
              elPageTitle.title = fallbackTitle;
            }
            if (response.language && response.language !== "unknown") {
              const langLow = response.language.toLowerCase();
              elLangBadge.textContent = response.language.toUpperCase();
              if (langLow.includes("python")) {
                elLangBadge.className = "badge badge-neutral";
              } else {
                elLangBadge.className = "badge badge-fail";
              }
            }
            if (response.constraints && response.constraints.length > 0) {
              elConstraintsBadge.textContent = `${response.constraints.length} Constraints`;
              elConstraintsBadge.classList.remove("hidden");
            } else {
              elConstraintsBadge.textContent = "0 Constraints";
              elConstraintsBadge.classList.remove("hidden");
            }
            if (response.sampleInputs) {
              populateSampleInputs(response.sampleInputs);
            }
          });
        } catch {
          // Content script not yet injected or tab loading
        }
      } else {
        elPageTitle.textContent = "LeetCode Problem Required";
        elPageTitle.title = "Open a LeetCode problem page to analyze.";
        elLangBadge.className = "badge badge-neutral";
        elLangBadge.textContent = "Inactive";
        elConstraintsBadge.classList.add("hidden");
        elBtnAnalyze.disabled = true;
        elBtnAnalyze.title = "Open a LeetCode problem page to analyze";
        if (elSamplesSourceValue) {
          elSamplesSourceValue.textContent = "Unavailable — Open a LeetCode problem";
        }
        if (elSamplesEmptyMsg) {
          elSamplesEmptyMsg.textContent = "Unavailable — Open a LeetCode problem page.";
        }
      }

      return currentTab;
    } catch {
      elPageTitle.textContent = "Tab error";
      if (elSamplesSourceValue) {
        elSamplesSourceValue.textContent = "Unavailable — Open a LeetCode problem";
      }
      return null;
    }
  }

  /**
   * Populate read-only baseline input samples section from detected public examples.
   */
  function populateSampleInputs(samples) {
    const list = Array.isArray(samples) ? samples : [];
    detectedSampleInputs = list;
    const count = list.length;

    if (elSamplesCountBadge) elSamplesCountBadge.textContent = String(count);
    if (elSamplesFoundCount) elSamplesFoundCount.textContent = String(count);

    const isLeetCode = Boolean(currentTab && currentTab.url && currentTab.url.includes("leetcode.com"));
    if (elSamplesSourceValue) {
      elSamplesSourceValue.textContent = isLeetCode ? "LeetCode Public Examples" : "Unavailable — Open a LeetCode problem";
    }

    if (count > 0) {
      if (elSamplesDetectedBadge) {
        elSamplesDetectedBadge.textContent = "YES";
        elSamplesDetectedBadge.className = "badge badge-pass";
      }
      if (elSamplesEmptyMsg) elSamplesEmptyMsg.classList.add("hidden");
      if (elSamplesList) {
        elSamplesList.classList.remove("hidden");
        elSamplesList.replaceChildren();
        list.forEach((sample, idx) => {
          const item = document.createElement("div");
          item.className = "sample-item";
          item.textContent = `Example ${idx + 1}: ${sample}`;
          elSamplesList.appendChild(item);
        });
      }
    } else {
      if (elSamplesDetectedBadge) {
        elSamplesDetectedBadge.textContent = "NO";
        elSamplesDetectedBadge.className = "badge badge-neutral";
      }
      if (elSamplesEmptyMsg) {
        elSamplesEmptyMsg.classList.remove("hidden");
        elSamplesEmptyMsg.textContent = isLeetCode
          ? "No public examples detected on this problem page."
          : "Unavailable — Open a LeetCode problem page.";
      }
      if (elSamplesList) {
        elSamplesList.classList.add("hidden");
        elSamplesList.replaceChildren();
      }
    }
  }

  /**
   * Parse key-value variable assignments from a string, supporting nested brackets (matrices),
   * quotes, numbers, booleans, and None.
   */
  function parseAssignmentString(line) {
    const pairs = {};
    let i = 0;
    const n = line.length;

    while (i < n) {
      const remaining = line.slice(i);
      const match = remaining.match(/([a-zA-Z_][a-zA-Z0-9_]*)\s*=/);
      if (!match) break;

      const key = match[1];
      let valStart = i + match.index + match[0].length;

      while (valStart < n && /\s/.test(line[valStart])) {
        valStart++;
      }
      if (valStart >= n) break;

      const firstChar = line[valStart];
      let valEnd = valStart;

      if (firstChar === "[") {
        let depth = 0;
        let j = valStart;
        let inQuote = null;
        while (j < n) {
          const c = line[j];
          if (inQuote) {
            if (c === inQuote && line[j - 1] !== "\\") inQuote = null;
          } else {
            if (c === '"' || c === "'") inQuote = c;
            else if (c === "[") depth++;
            else if (c === "]") {
              depth--;
              if (depth === 0) {
                j++;
                break;
              }
            }
          }
          j++;
        }
        valEnd = j;
      } else if (firstChar === "{") {
        let depth = 0;
        let j = valStart;
        let inQuote = null;
        while (j < n) {
          const c = line[j];
          if (inQuote) {
            if (c === inQuote && line[j - 1] !== "\\") inQuote = null;
          } else {
            if (c === '"' || c === "'") inQuote = c;
            else if (c === "{") depth++;
            else if (c === "}") {
              depth--;
              if (depth === 0) {
                j++;
                break;
              }
            }
          }
          j++;
        }
        valEnd = j;
      } else if (firstChar === '"' || firstChar === "'") {
        const quote = firstChar;
        let j = valStart + 1;
        while (j < n) {
          if (line[j] === quote && line[j - 1] !== "\\") {
            j++;
            break;
          }
          j++;
        }
        valEnd = j;
      } else {
        let j = valStart;
        while (j < n) {
          if (line[j] === ",") break;
          const sub = line.slice(j);
          if (/^\s+[a-zA-Z_][a-zA-Z0-9_]*\s*=/.test(sub)) break;
          j++;
        }
        valEnd = j;
      }

      const rawVal = line.slice(valStart, valEnd).trim();
      let parsedVal = rawVal;

      if (rawVal === "True") parsedVal = true;
      else if (rawVal === "False") parsedVal = false;
      else if (rawVal === "None") parsedVal = null;
      else if ((rawVal.startsWith('"') && rawVal.endsWith('"')) || (rawVal.startsWith("'") && rawVal.endsWith("'"))) {
        parsedVal = rawVal.slice(1, -1);
      } else if (rawVal.startsWith("[") || rawVal.startsWith("{")) {
        try {
          parsedVal = JSON.parse(rawVal.replace(/'/g, '"'));
        } catch {
          parsedVal = rawVal;
        }
      } else if (!isNaN(Number(rawVal)) && rawVal.length > 0) {
        parsedVal = Number(rawVal);
      }

      pairs[key] = parsedVal;
      i = valEnd;
    }

    return pairs;
  }

  /**
   * Parse input samples into structured test_cases for backend consumption.
   * Accepts either an array of sample strings or a raw formatted string.
   */
  function parseUserSampleInputs(inputData) {
    if (!inputData) return [];

    // 1. Array of sample strings or sample objects
    if (Array.isArray(inputData)) {
      const cases = [];
      inputData.forEach((item, idx) => {
        if (!item) return;
        if (typeof item === "object") {
          cases.push({
            id: `sample_${idx + 1}`,
            source: "PUBLIC_SAMPLE",
            input_data: "input_data" in item ? item.input_data : item
          });
        } else if (typeof item === "string") {
          const dict = parseAssignmentString(item);
          if (dict && Object.keys(dict).length > 0) {
            cases.push({
              id: `sample_${cases.length + 1}`,
              source: "PUBLIC_SAMPLE",
              input_data: dict
            });
          }
        }
      });
      return cases;
    }

    if (typeof inputData !== "string") return [];
    const trimmed = inputData.trim();
    if (!trimmed) return [];

    // 2. Direct JSON format
    if (trimmed.startsWith("[") || trimmed.startsWith("{")) {
      try {
        const parsed = JSON.parse(trimmed);
        if (Array.isArray(parsed)) {
          return parseUserSampleInputs(parsed);
        } else if (parsed && typeof parsed === "object") {
          return [{ id: "sample_1", source: "PUBLIC_SAMPLE", input_data: parsed }];
        }
      } catch {
        // Fall back to line/block parsing
      }
    }

    // 3. Blocks separated by blank lines or Example headings
    const rawBlocks = trimmed.split(/\n\s*\n+|(?=Example\s*\d+:?)/i);
    const blocks = rawBlocks.map(b => b.trim()).filter(b => b.length > 0);
    const cases = [];

    blocks.forEach(block => {
      const lines = block.split("\n").map(l => l.trim()).filter(l => l.length > 0);
      let currentCase = {};

      lines.forEach(line => {
        const cleanLine = line.split(/Output\s*:/i)[0].split(/Explanation\s*:/i)[0];
        const pairs = parseAssignmentString(cleanLine);
        if (!pairs || Object.keys(pairs).length === 0) return;

        const hasMultiple = Object.keys(pairs).length > 1;
        const collision = Object.keys(pairs).some(k => k in currentCase);

        if (collision || (hasMultiple && Object.keys(currentCase).length > 0)) {
          if (Object.keys(currentCase).length > 0) {
            cases.push({
              id: `sample_${cases.length + 1}`,
              source: "PUBLIC_SAMPLE",
              input_data: currentCase
            });
          }
          currentCase = { ...pairs };
        } else {
          Object.assign(currentCase, pairs);
        }
      });

      if (Object.keys(currentCase).length > 0) {
        cases.push({
          id: `sample_${cases.length + 1}`,
          source: "PUBLIC_SAMPLE",
          input_data: currentCase
        });
      }
    });

    return cases;
  }

  /**
   * Switch between Test Intelligence and Code Health tabs.
   */
  function switchTab(target) {
    if (target === "intel") {
      elTabBtnIntel.classList.add("active");
      elTabBtnIntel.setAttribute("aria-selected", "true");
      elTabBtnCode.classList.remove("active");
      elTabBtnCode.setAttribute("aria-selected", "false");
      elPanelIntel.classList.remove("hidden");
      elPanelCode.classList.add("hidden");
    } else {
      elTabBtnCode.classList.add("active");
      elTabBtnCode.setAttribute("aria-selected", "true");
      elTabBtnIntel.classList.remove("active");
      elTabBtnIntel.setAttribute("aria-selected", "false");
      elPanelCode.classList.remove("hidden");
      elPanelIntel.classList.add("hidden");
    }
  }

  /**
   * Render diagnostic section status pill.
   */
  function renderPill(label, status) {
    const pill = document.createElement("span");
    const upper = String(status).toUpperCase();
    let statusClass = "pill-skip";

    if (upper === "PASS") statusClass = "pill-pass";
    else if (upper === "WARNING" || upper === "WARN") statusClass = "pill-warn";
    else if (upper === "FAIL") statusClass = "pill-fail";
    else if (upper === "SKIPPED") statusClass = "pill-skip";

    pill.className = `section-pill ${statusClass}`;

    const labelSpan = document.createElement("span");
    labelSpan.textContent = `${label}:`;
    const statusSpan = document.createElement("span");
    statusSpan.textContent = upper;

    pill.appendChild(labelSpan);
    pill.appendChild(statusSpan);
    return pill;
  }

  /**
   * Format preview for a 1D row or array.
   */
  function formatRowPreview(row) {
    if (!Array.isArray(row)) return JSON.stringify(row);
    if (row.length > 8) {
      const head = row.slice(0, 5).map(x => JSON.stringify(x));
      const tail = row.slice(-3).map(x => JSON.stringify(x));
      return `[${head.join(", ")}, ..., ${tail.join(", ")}]`;
    }
    return JSON.stringify(row);
  }

  /**
   * Format concise input summary without mutating or truncating original data.
   * Handles large arrays (shows count, previews first 5 & last 3 with ellipsis),
   * large strings (shows count, previews prefix & suffix with ellipsis),
   * and 2D matrices (shows dimensions and cell count).
   */
  function formatValueSummary(val) {
    // 1. Array
    if (Array.isArray(val)) {
      const len = val.length;
      if (len === 0) {
        return { preview: "[]", countTag: "(0 items)" };
      }
      // 2D Matrix
      if (Array.isArray(val[0])) {
        const rows = len;
        const cols = val[0].length;
        if (rows > 5) {
          const firstRows = val.slice(0, 3).map(r => formatRowPreview(r));
          const lastRows = val.slice(-2).map(r => formatRowPreview(r));
          return {
            preview: `[${firstRows.join(", ")}, ..., ${lastRows.join(", ")}]`,
            countTag: `(${rows}×${cols} matrix, ${rows * cols} cells)`,
          };
        } else {
          const rowPreviews = val.map(r => formatRowPreview(r));
          return {
            preview: `[${rowPreviews.join(", ")}]`,
            countTag: `(${rows}×${cols} matrix)`,
          };
        }
      }
      // 1D Array
      if (len > 8) {
        const head = val.slice(0, 5).map(x => JSON.stringify(x));
        const tail = val.slice(-3).map(x => JSON.stringify(x));
        return {
          preview: `[${head.join(", ")}, ..., ${tail.join(", ")}]`,
          countTag: `(${len} items)`,
        };
      } else {
        return {
          preview: JSON.stringify(val),
          countTag: `(${len} items)`,
        };
      }
    }

    // 2. String
    if (typeof val === "string") {
      const len = val.length;
      if (len > 35) {
        const prefix = val.slice(0, 15);
        const suffix = val.slice(-10);
        return {
          preview: `"${prefix}...${suffix}"`,
          countTag: `(${len} chars)`,
        };
      } else {
        return {
          preview: JSON.stringify(val),
          countTag: `(${len} chars)`,
        };
      }
    }

    // 3. Object / Dict
    if (val && typeof val === "object") {
      const keys = Object.keys(val);
      return {
        preview: `{${keys.slice(0, 3).join(", ")}${keys.length > 3 ? ", ..." : ""}}`,
        countTag: `(${keys.length} keys)`,
      };
    }

    // 4. Scalar
    return {
      preview: String(val),
      countTag: null,
    };
  }

  /**
   * Render Coverage Gap card (compact layout with expandable risk/action).
   */
  function renderGapCard(gap) {
    const card = document.createElement("div");
    const severity = (gap.severity || "MEDIUM").toLowerCase();
    card.className = `gap-card severity-${severity}`;

    // Header
    const header = document.createElement("div");
    header.className = "gap-header";

    const catSpan = document.createElement("span");
    catSpan.className = "gap-category";
    catSpan.textContent = gap.category || "COVERAGE_GAP";

    const badgesDiv = document.createElement("div");
    badgesDiv.className = "gap-badges";

    if (gap.param_name) {
      const paramBadge = document.createElement("span");
      paramBadge.className = "badge badge-neutral gap-param-badge";
      paramBadge.textContent = gap.param_name;
      badgesDiv.appendChild(paramBadge);
      badgesDiv.appendChild(document.createTextNode(" "));
    }

    const sevPill = document.createElement("span");
    sevPill.className = `severity-pill pill-${severity}`;
    sevPill.textContent = (gap.severity || "MEDIUM").toUpperCase();
    badgesDiv.appendChild(sevPill);

    header.appendChild(catSpan);
    header.appendChild(badgesDiv);
    card.appendChild(header);

    // One-line explanation
    if (gap.rationale) {
      const p = document.createElement("p");
      p.className = "gap-rationale";
      p.textContent = gap.rationale;
      card.appendChild(p);
    }

    // Expandable details (Risk & Action)
    if (gap.risk_explained || gap.suggested_action) {
      const detailsContainer = document.createElement("div");
      detailsContainer.className = "gap-expandable-details hidden";

      if (gap.risk_explained) {
        const row = document.createElement("div");
        row.className = "gap-detail-row";

        const label = document.createElement("span");
        label.className = "gap-detail-label";
        label.textContent = "Risk:";

        const text = document.createElement("span");
        text.className = "gap-detail-text";
        text.textContent = gap.risk_explained;

        row.appendChild(label);
        row.appendChild(text);
        detailsContainer.appendChild(row);
      }

      if (gap.suggested_action) {
        const row = document.createElement("div");
        row.className = "gap-detail-row";

        const label = document.createElement("span");
        label.className = "gap-detail-label";
        label.textContent = "Action:";

        const text = document.createElement("span");
        text.className = "gap-detail-text gap-action";
        text.textContent = gap.suggested_action;

        row.appendChild(label);
        row.appendChild(text);
        detailsContainer.appendChild(row);
      }

      const toggleBtn = document.createElement("button");
      toggleBtn.className = "btn-gap-details-toggle";
      toggleBtn.type = "button";
      toggleBtn.appendChild(createSvgIcon("chevron-right", "toggle-chevron", 11));
      toggleBtn.appendChild(document.createTextNode(" Show Details"));

      toggleBtn.addEventListener("click", () => {
        const isHidden = detailsContainer.classList.contains("hidden");
        clearElement(toggleBtn);
        if (isHidden) {
          detailsContainer.classList.remove("hidden");
          toggleBtn.appendChild(createSvgIcon("chevron-down", "toggle-chevron", 11));
          toggleBtn.appendChild(document.createTextNode(" Hide Details"));
        } else {
          detailsContainer.classList.add("hidden");
          toggleBtn.appendChild(createSvgIcon("chevron-right", "toggle-chevron", 11));
          toggleBtn.appendChild(document.createTextNode(" Show Details"));
        }
      });

      card.appendChild(toggleBtn);
      card.appendChild(detailsContainer);
    }

    return card;
  }

  /**
   * Render Synthesized Edge-Case Candidate card.
   * Displays concise input summary with element/char counts,
   * expandable full JSON, and full clipboard copying.
   */
  function renderCandidateCard(candidate, rankIndex) {
    const card = document.createElement("div");
    card.className = "candidate-card";

    // Complete untruncated JSON string for copying and expanded inspection
    const fullInputString = JSON.stringify(candidate.input_data, null, 2);

    // Header: Rank + Label + Score
    const header = document.createElement("div");
    header.className = "candidate-header";

    const rankGroup = document.createElement("div");
    rankGroup.className = "candidate-rank-group";

    const rankBadge = document.createElement("span");
    rankBadge.className = "candidate-rank";
    rankBadge.textContent = `#${rankIndex + 1}`;

    const labelSpan = document.createElement("span");
    labelSpan.className = "candidate-label";
    labelSpan.textContent = candidate.label || `Candidate ${rankIndex + 1}`;

    rankGroup.appendChild(rankBadge);
    rankGroup.appendChild(labelSpan);

    const scorePill = document.createElement("span");
    scorePill.className = "candidate-score-pill";
    const scoreVal = typeof candidate.relevance_score === "number" ? Math.round(candidate.relevance_score * 100) : 0;
    scorePill.textContent = `Relevance: ${scoreVal}%`;

    header.appendChild(rankGroup);
    header.appendChild(scorePill);
    card.appendChild(header);

    // Tags Row: Target Gap, Boundary & Classification
    const tagsRow = document.createElement("div");
    tagsRow.className = "candidate-tags-row";

    function appendCandidateTag(element) {
      if (tagsRow.children.length > 0) {
        const sep = document.createElement("span");
        sep.className = "tag-separator";
        sep.textContent = " | ";
        tagsRow.appendChild(sep);
        tagsRow.appendChild(document.createTextNode(" "));
      }
      tagsRow.appendChild(element);
    }

    // Classification tag
    const classification = candidate.classification || "CONSTRAINT VALIDITY UNKNOWN";
    const classTag = document.createElement("span");
    if (classification === "VALID") {
      classTag.className = "tag-classification classification-valid";
      classTag.appendChild(createSvgIcon("check", "tag-icon", 11));
      classTag.appendChild(document.createTextNode(" VALID"));
      classTag.title = candidate.classification_reason || "Satisfies all supported problem constraints.";
    } else if (classification === "ROBUSTNESS PROBE") {
      classTag.className = "tag-classification classification-probe";
      classTag.appendChild(createSvgIcon("alert", "tag-icon", 11));
      classTag.appendChild(document.createTextNode(" ROBUSTNESS PROBE"));
      classTag.title = candidate.classification_reason || "Deliberately violates a known constraint.";
    } else {
      classTag.className = "tag-classification classification-unknown";
      classTag.appendChild(createSvgIcon("help", "tag-icon", 11));
      classTag.appendChild(document.createTextNode(" VALIDITY UNKNOWN"));
      classTag.title = candidate.classification_reason || "Insufficient constraint information to determine validity.";
    }
    appendCandidateTag(classTag);

    if (candidate.target_gap) {
      const gapTag = document.createElement("span");
      gapTag.className = "tag-gap";
      gapTag.textContent = candidate.target_gap;
      appendCandidateTag(gapTag);
    }

    if (candidate.is_boundary) {
      const boundTag = document.createElement("span");
      boundTag.className = "tag-boundary";
      boundTag.textContent = "BOUNDARY";
      appendCandidateTag(boundTag);
    }

    if (candidate.is_performance) {
      const perfTag = document.createElement("span");
      perfTag.className = "tag-scale";
      perfTag.textContent = "SCALE";
      appendCandidateTag(perfTag);
    }

    if (tagsRow.children.length > 0) {
      card.appendChild(tagsRow);
    }

    // Classification reason / validity explanation
    if (candidate.classification_reason) {
      const reasonRow = document.createElement("div");
      reasonRow.className = "candidate-reason-row";

      const rLabel = document.createElement("span");
      rLabel.className = "candidate-reason-label";
      rLabel.textContent = "Validity:";

      const rText = document.createElement("span");
      rText.className = "candidate-reason-text";
      rText.textContent = candidate.classification_reason;

      reasonRow.appendChild(rLabel);
      reasonRow.appendChild(rText);
      card.appendChild(reasonRow);
    }

    // Concise Input Summary Box
    const inputSummaryBox = document.createElement("div");
    inputSummaryBox.className = "input-summary-box";

    const inputData = candidate.input_data || {};
    const entries = Object.entries(inputData);

    if (entries.length === 0) {
      const emptyRow = document.createElement("div");
      emptyRow.className = "input-summary-row";
      emptyRow.textContent = "{}";
      inputSummaryBox.appendChild(emptyRow);
    } else {
      entries.forEach(([pName, pVal]) => {
        const row = document.createElement("div");
        row.className = "input-summary-row";

        const nameSpan = document.createElement("span");
        nameSpan.className = "input-param-name";
        nameSpan.textContent = `${pName}:`;

        const { preview, countTag } = formatValueSummary(pVal);

        const valSpan = document.createElement("span");
        valSpan.className = "input-param-val";
        valSpan.textContent = preview;

        row.appendChild(nameSpan);
        row.appendChild(valSpan);

        if (countTag) {
          const countSpan = document.createElement("span");
          countSpan.className = "input-count-badge";
          countSpan.textContent = countTag;
          row.appendChild(countSpan);
        }

        inputSummaryBox.appendChild(row);
      });
    }
    card.appendChild(inputSummaryBox);

    // Actions Row: Toggle Full JSON + Copy Full Input Button
    const actionsRow = document.createElement("div");
    actionsRow.className = "candidate-actions-row";

    const toggleJsonBtn = document.createElement("button");
    toggleJsonBtn.className = "btn-toggle-json";
    toggleJsonBtn.type = "button";
    toggleJsonBtn.appendChild(createSvgIcon("chevron-right", "toggle-chevron", 11));
    toggleJsonBtn.appendChild(document.createTextNode(" Show Full JSON"));

    const copyBtn = document.createElement("button");
    copyBtn.className = "btn-copy-summary";
    copyBtn.type = "button";
    copyBtn.title = "Copy complete untruncated candidate input to clipboard";
    copyBtn.appendChild(createSvgIcon("copy", "btn-icon", 12));
    copyBtn.appendChild(document.createTextNode(" Copy Full Input"));

    copyBtn.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(fullInputString);
        clearElement(copyBtn);
        copyBtn.appendChild(createSvgIcon("check", "btn-icon", 12));
        copyBtn.appendChild(document.createTextNode(" Copied"));
        setTimeout(() => {
          clearElement(copyBtn);
          copyBtn.appendChild(createSvgIcon("copy", "btn-icon", 12));
          copyBtn.appendChild(document.createTextNode(" Copy Full Input"));
        }, 1500);
      } catch {
        clearElement(copyBtn);
        copyBtn.textContent = "Error";
      }
    });

    actionsRow.appendChild(toggleJsonBtn);
    actionsRow.appendChild(copyBtn);
    card.appendChild(actionsRow);

    // Expandable JSON Container
    const jsonContainer = document.createElement("div");
    jsonContainer.className = "candidate-json-details hidden";

    const codeBox = document.createElement("div");
    codeBox.className = "candidate-code-container";

    const pre = document.createElement("pre");
    pre.className = "candidate-code";
    pre.textContent = fullInputString;

    codeBox.appendChild(pre);
    jsonContainer.appendChild(codeBox);
    card.appendChild(jsonContainer);

    toggleJsonBtn.addEventListener("click", () => {
      const isHidden = jsonContainer.classList.contains("hidden");
      clearElement(toggleJsonBtn);
      if (isHidden) {
        jsonContainer.classList.remove("hidden");
        toggleJsonBtn.appendChild(createSvgIcon("chevron-down", "toggle-chevron", 11));
        toggleJsonBtn.appendChild(document.createTextNode(" Hide JSON"));
      } else {
        jsonContainer.classList.add("hidden");
        toggleJsonBtn.appendChild(createSvgIcon("chevron-right", "toggle-chevron", 11));
        toggleJsonBtn.appendChild(document.createTextNode(" Show Full JSON"));
      }
    });

    // Provenance footer
    const provDiv = document.createElement("div");
    provDiv.className = "candidate-provenance";

    const provSpan = document.createElement("span");
    provSpan.className = "provenance-tag";
    provSpan.appendChild(createSvgIcon("spark", "provenance-icon", 11));
    provSpan.appendChild(document.createTextNode(" GENERATED_TEST"));

    const oracleSpan = document.createElement("span");
    oracleSpan.textContent = "Expected output: unverified";

    provDiv.appendChild(provSpan);
    provDiv.appendChild(oracleSpan);
    card.appendChild(provDiv);

    return card;
  }

  /**
   * Render Observed Input Patterns container.
   */
  function renderPatterns(patterns, isContextBased) {
    clearElement(elPatternsContent);
    if (isContextBased) {
      const p = document.createElement("p");
      p.className = "samples-hint";
      p.textContent = "Observed Baseline Coverage: Not Available (Context-Based Mode active).";
      elPatternsContent.appendChild(p);
      return;
    }
    if (!patterns || !patterns.parameters || Object.keys(patterns.parameters).length === 0) {
      const p = document.createElement("p");
      p.className = "samples-hint";
      p.textContent = "No baseline parameter patterns observed.";
      elPatternsContent.appendChild(p);
      return;
    }

    Object.entries(patterns.parameters).forEach(([pName, pProf]) => {
      const itemDiv = document.createElement("div");
      itemDiv.className = "pattern-param-item";

      const title = document.createElement("span");
      title.className = "pattern-param-title";
      title.textContent = `${pName} (${(pProf.types_observed || []).join(", ") || "unknown"}):`;
      itemDiv.appendChild(title);

      const tagsDiv = document.createElement("div");
      tagsDiv.className = "pattern-tags";

      if (pProf.collection && pProf.collection.observed_lengths) {
        const tag = document.createElement("span");
        tag.className = "pattern-tag";
        tag.textContent = `lengths: [${pProf.collection.observed_lengths.join(", ")}]`;
        tagsDiv.appendChild(tag);
      }

      if (pProf.numeric) {
        const num = pProf.numeric;
        if (num.has_negative === "OBSERVED") {
          const t = document.createElement("span");
          t.className = "pattern-tag";
          t.textContent = "has negatives";
          tagsDiv.appendChild(t);
        }
        if (num.has_zero === "OBSERVED") {
          const t = document.createElement("span");
          t.className = "pattern-tag";
          t.textContent = "has zero";
          tagsDiv.appendChild(t);
        }
        if (num.min_value !== null && num.max_value !== null && num.min_value !== undefined) {
          const t = document.createElement("span");
          t.className = "pattern-tag";
          t.textContent = `range: [${num.min_value}, ${num.max_value}]`;
          tagsDiv.appendChild(t);
        }
      }

      if (pProf.multiplicity) {
        const mult = pProf.multiplicity;
        if (mult.has_duplicates === "OBSERVED") {
          const t = document.createElement("span");
          t.className = "pattern-tag";
          t.textContent = "duplicates observed";
          tagsDiv.appendChild(t);
        }
      }

      itemDiv.appendChild(tagsDiv);
      elPatternsContent.appendChild(itemDiv);
    });
  }

  /**
   * Render diagnostic finding cards for Code Health tab.
   */
  function renderFindingCard(finding, isError) {
    const card = document.createElement("div");
    card.className = `finding-card ${isError ? "finding-error" : "finding-warning"}`;

    const header = document.createElement("div");
    header.className = "finding-header";

    const typeSpan = document.createElement("span");
    typeSpan.className = "finding-type";
    typeSpan.textContent = finding.type || "Diagnostic";

    const lineSpan = document.createElement("span");
    lineSpan.className = "finding-line";
    const lineNum = finding.line || finding.line_number || 0;
    lineSpan.textContent = lineNum > 0 ? `Line ${lineNum}` : "File Scope";

    header.appendChild(typeSpan);
    header.appendChild(lineSpan);
    card.appendChild(header);

    if (finding.message) {
      const msg = document.createElement("p");
      msg.className = "finding-message";
      msg.textContent = finding.message;
      card.appendChild(msg);
    }

    const whyText = finding.why || finding.explanation;
    if (whyText) {
      const detailRow = document.createElement("div");
      detailRow.className = "finding-detail-row";

      const label = document.createElement("span");
      label.className = "finding-detail-label";
      label.textContent = "Why:";

      const text = document.createElement("span");
      text.className = "finding-detail-text";
      text.textContent = whyText;

      detailRow.appendChild(label);
      detailRow.appendChild(text);
      card.appendChild(detailRow);
    }

    const fixText = finding.fix || finding.suggested_fix;
    if (fixText) {
      const detailRow = document.createElement("div");
      detailRow.className = "finding-detail-row";

      const label = document.createElement("span");
      label.className = "finding-detail-label";
      label.textContent = "Suggested Fix:";

      const text = document.createElement("span");
      text.className = "finding-detail-text finding-fix";
      text.textContent = fixText;

      detailRow.appendChild(label);
      detailRow.appendChild(text);
      card.appendChild(detailRow);
    }

    return card;
  }

  /**
   * Update coverage gaps list display based on current pagination state.
   */
  function updateGapsDisplay() {
    clearElement(elGapsList);
    const isContextBased = currentAnalysisMode === "CONTEXT_BASED";

    if (isContextBased) {
      elNoGapsMsg.classList.remove("hidden");
      if (elNoGapsText) {
        clearElement(elNoGapsText);
        elNoGapsText.textContent = "Observed Baseline Coverage: Not Available (Context-Based Mode active).";
      }
      if (elBtnToggleAllGaps) elBtnToggleAllGaps.classList.add("hidden");
      return;
    }

    if (allGapsData.length === 0) {
      elNoGapsMsg.classList.remove("hidden");
      if (elNoGapsText) {
        clearElement(elNoGapsText);
        elNoGapsText.appendChild(createSvgIcon("check", "gap-check-icon", 13));
        elNoGapsText.appendChild(document.createTextNode(" No significant domain coverage gaps detected."));
      }
      if (elBtnToggleAllGaps) elBtnToggleAllGaps.classList.add("hidden");
      return;
    }

    elNoGapsMsg.classList.add("hidden");
    const displayedGaps = isAllGapsExpanded ? allGapsData : allGapsData.slice(0, 5);
    displayedGaps.forEach(gap => elGapsList.appendChild(renderGapCard(gap)));

    if (elBtnToggleAllGaps) {
      if (allGapsData.length > 5) {
        elBtnToggleAllGaps.classList.remove("hidden");
        clearElement(elBtnToggleAllGaps);
        const icon = createSvgIcon(isAllGapsExpanded ? "chevron-up" : "chevron-down", "btn-icon", 12);
        elBtnToggleAllGaps.appendChild(icon);
        const text = isAllGapsExpanded
          ? " Show Top 5 Gaps"
          : ` View All Gaps (${allGapsData.length})`;
        elBtnToggleAllGaps.appendChild(document.createTextNode(text));
      } else {
        elBtnToggleAllGaps.classList.add("hidden");
      }
    }
  }

  /**
   * Update generated candidates list display based on current pagination state.
   */
  function updateCandidatesDisplay() {
    clearElement(elCandidatesList);
    if (allCandidatesData.length === 0) {
      elNoCandidatesMsg.classList.remove("hidden");
      if (elBtnToggleAllCandidates) elBtnToggleAllCandidates.classList.add("hidden");
      return;
    }

    elNoCandidatesMsg.classList.add("hidden");
    const displayedCandidates = isAllCandidatesExpanded ? allCandidatesData : allCandidatesData.slice(0, 5);
    displayedCandidates.forEach((cand, idx) => elCandidatesList.appendChild(renderCandidateCard(cand, idx)));

    if (elBtnToggleAllCandidates) {
      if (allCandidatesData.length > 5) {
        elBtnToggleAllCandidates.classList.remove("hidden");
        clearElement(elBtnToggleAllCandidates);
        const icon = createSvgIcon(isAllCandidatesExpanded ? "chevron-up" : "chevron-down", "btn-icon", 12);
        elBtnToggleAllCandidates.appendChild(icon);
        const text = isAllCandidatesExpanded
          ? " Show Top 5 Candidates"
          : ` View All Candidates (${allCandidatesData.length})`;
        elBtnToggleAllCandidates.appendChild(document.createTextNode(text));
      } else {
        elBtnToggleAllCandidates.classList.add("hidden");
      }
    }
  }

  /**
   * Render complete EdgeMind report.
   */
  function renderReport(report) {
    elEmptyState.classList.add("hidden");
    elResultsSection.classList.remove("hidden");

    // 0. Update Problem Name & ID in context summary
    if (elPageTitle) {
      const pContext = report.context || (report.test_intelligence && report.test_intelligence.problem_context) || {};
      const probId = pContext.problem_id || (detectedPageInfo ? detectedPageInfo.problemId : "");
      const probTitle = pContext.title || (detectedPageInfo ? detectedPageInfo.problemTitle : "");
      if (probId && probTitle && !probTitle.startsWith(probId)) {
        elPageTitle.textContent = `${probId}. ${probTitle}`;
      } else if (probTitle) {
        elPageTitle.textContent = probTitle;
      } else if (probId) {
        elPageTitle.textContent = `Problem #${probId}`;
      }
    }

    // 1. Process Test Intelligence
    const intel = report.test_intelligence || {};
    const gaps = intel.coverage_gaps || [];
    const candidates = intel.generated_candidates || [];
    const rankingSummary = intel.ranking_summary || {};
    const patterns = intel.detected_patterns || {};

    const isContextBased = report.analysis_mode === "CONTEXT_BASED";
    currentAnalysisMode = report.analysis_mode || "BASELINE_DRIVEN";

    // Update Mode Banner
    if (elModeTitle) {
      elModeTitle.textContent = isContextBased
        ? "CONTEXT-BASED INTELLIGENCE"
        : "BASELINE-DRIVEN INTELLIGENCE";
    }
    if (elModeBadge) {
      elModeBadge.textContent = isContextBased ? "Mode: Context-Based" : "Mode: Baseline-Driven";
      elModeBadge.className = `badge ${isContextBased ? "badge-mode-context" : "badge-mode-baseline"}`;
    }
    if (elModeExamplesCount) {
      elModeExamplesCount.textContent = String(
        isContextBased ? 0 : (intel.existing_tests_analyzed || 0)
      );
    }
    if (elModeContextStatus) {
      const cStatus = report.context_completeness || "Detected";
      elModeContextStatus.textContent = cStatus === "DETECTED" ? "Detected" : (cStatus === "PARTIAL" ? "Partial" : "Insufficient");
    }
    if (elModeConstraintsStatus) {
      const pConstraints = report.parsed_constraints || {};
      const constStatus = pConstraints.status || "UNAVAILABLE";
      if (constStatus === "PARSED") {
        elModeConstraintsStatus.textContent = "Parsed";
      } else if (constStatus === "PARTIALLY_PARSED") {
        elModeConstraintsStatus.textContent = "Partially Parsed";
      } else {
        elModeConstraintsStatus.textContent = "Unavailable";
      }
    }
    if (elModeParametersIdentified) {
      const pCount = (report.identified_parameters || []).length;
      elModeParametersIdentified.textContent = String(pCount);
    }

    // Update stats & section headers according to operating mode
    if (isContextBased) {
      elStatGaps.textContent = "N/A";
      if (elStatGapsLabel) elStatGapsLabel.textContent = "Baseline Coverage";
      elBadgeGapsCount.textContent = "Not Available";

      if (elGapsSectionTitle) elGapsSectionTitle.textContent = "Potential Edge Cases";
      if (elGapsSubhead) elGapsSubhead.textContent = "Observed Baseline Coverage: Not Available";
      if (elCandidatesSectionTitle) elCandidatesSectionTitle.textContent = "Context-Derived Candidates";
      if (elContextModeDisclaimer) elContextModeDisclaimer.classList.remove("hidden");
    } else {
      elStatGaps.textContent = String(gaps.length);
      if (elStatGapsLabel) elStatGapsLabel.textContent = "Coverage Gaps";
      elBadgeGapsCount.textContent = `${gaps.length} Gaps`;

      if (elGapsSectionTitle) elGapsSectionTitle.textContent = "Identified Coverage Gaps";
      elGapsSubhead.textContent = `${gaps.length} ${gaps.length === 1 ? "Gap" : "Gaps"}`;
      if (elCandidatesSectionTitle) elCandidatesSectionTitle.textContent = "Synthesized Edge-Case Candidates";
      if (elContextModeDisclaimer) elContextModeDisclaimer.classList.add("hidden");
    }

    elStatCandidates.textContent = String(candidates.length);
    elStatDedup.textContent = String(rankingSummary.exact_duplicates_removed || 0);
    elCandidatesSubhead.textContent = `${candidates.length} ${candidates.length === 1 ? "Candidate" : "Candidates"}`;

    // Render coverage gaps with 5-item initial view & "View All" toggle
    allGapsData = gaps;
    isAllGapsExpanded = false;
    updateGapsDisplay();

    // Render candidates with 5-item initial view & "View All" toggle
    allCandidatesData = candidates;
    isAllCandidatesExpanded = false;
    updateCandidatesDisplay();

    // Render observed patterns
    renderPatterns(patterns, isContextBased);

    // 2. Process Code Health
    const codeAnalysis = report.code_analysis || {};
    const score = typeof codeAnalysis.score === "number" ? codeAnalysis.score : 0;
    elScoreValue.textContent = String(score);
    elBadgeCodeScore.textContent = `${score}/100`;

    const overall = codeAnalysis.overall_status || codeAnalysis.status || "UNKNOWN";
    elOverallStatusBadge.textContent = overall;
    elOverallStatusBadge.className = "badge badge-lg";

    if (overall === "PASS") {
      elOverallStatusBadge.classList.add("badge-pass");
    } else if (overall === "PASS WITH WARNINGS") {
      elOverallStatusBadge.classList.add("badge-warn");
    } else {
      elOverallStatusBadge.classList.add("badge-fail");
    }

    const errors = codeAnalysis.detailed_errors || [];
    const warnings = codeAnalysis.detailed_warnings || [];
    elErrorsCount.textContent = `${errors.length} ${errors.length === 1 ? "Error" : "Errors"}`;
    elWarningsCount.textContent = `${warnings.length} ${warnings.length === 1 ? "Warning" : "Warnings"}`;

    clearElement(elSectionPills);
    const summary = codeAnalysis.summary || {};
    elSectionPills.appendChild(renderPill("Syntax", summary.syntax || codeAnalysis.syntax_status || "PASS"));
    elSectionPills.appendChild(renderPill("Logic", summary.logic || codeAnalysis.logic_status || "PASS"));
    elSectionPills.appendChild(renderPill("Quality", summary.quality || codeAnalysis.quality_status || "PASS"));
    elSectionPills.appendChild(renderPill("Complexity", summary.complexity || codeAnalysis.complexity_status || "PASS"));
    elSectionPills.appendChild(renderPill("Runtime", summary.runtime || codeAnalysis.runtime_status || "SKIPPED"));

    clearElement(elFindingsList);
    const totalFindings = errors.length + warnings.length;
    elFindingsTitle.textContent = `Diagnostic Findings (${totalFindings})`;

    if (totalFindings === 0) {
      elNoFindingsMessage.classList.remove("hidden");
    } else {
      elNoFindingsMessage.classList.add("hidden");
      errors.forEach(e => elFindingsList.appendChild(renderFindingCard(e, true)));
      warnings.forEach(w => elFindingsList.appendChild(renderFindingCard(w, false)));
    }

    // Default to Test Intelligence tab
    switchTab("intel");
  }

  /**
   * Main analysis execution handler.
   */
  async function handleAnalyze() {
    hideError();

    // 1. Validate active tab
    if (!currentTab || !currentTab.url || !currentTab.url.includes("leetcode.com")) {
      showError("Please navigate to a LeetCode problem page before analyzing code.");
      return;
    }

    setLoading(true, "Extracting Python code and Monaco buffer models...");

    try {
      // 2. Execute extraction script in MAIN world
      const injectionResults = await chrome.scripting.executeScript({
        target: { tabId: currentTab.id },
        files: ["scripts/extractor.js"],
        world: "MAIN"
      });

      if (!injectionResults || injectionResults.length === 0 || !injectionResults[0].result) {
        throw new Error("Unable to communicate with the LeetCode editor. Please ensure the page has finished loading.");
      }

      const extraction = injectionResults[0].result;

      if (!extraction.success) {
        if (extraction.language && extraction.language !== "unknown") {
          elLangBadge.textContent = extraction.language.toUpperCase();
          if (!extraction.language.toLowerCase().includes("python")) {
            elLangBadge.className = "badge badge-fail";
          }
        }
        throw new Error(extraction.error || "Failed to extract code from LeetCode editor.");
      }

      const code = extraction.code;
      const detectedLang = (extraction.language || "").toLowerCase();

      elLangBadge.textContent = extraction.language ? extraction.language.toUpperCase() : "PYTHON";

      // 3. Validate language (Python / Python3 only)
      if (!detectedLang.includes("python")) {
        elLangBadge.className = "badge badge-fail";
        throw new Error(
          `Detected editor language '${extraction.language}'. EdgeMind currently analyzes Python code only.`
        );
      }
      elLangBadge.className = "badge badge-neutral";

      // 4. Validate source content
      if (!code || !code.trim()) {
        throw new Error("The LeetCode editor is empty. Please enter or reset solution code before analyzing.");
      }

      // 5. Enforce 64 KiB client-side size limit
      const sourceByteSize = new TextEncoder().encode(code).length;
      if (sourceByteSize > MAX_SOURCE_SIZE) {
        throw new Error(
          `Code size (${sourceByteSize} bytes) exceeds the maximum allowed limit of ${MAX_SOURCE_SIZE} bytes (64 KiB).`
        );
      }

      // 6. Automatically retrieve public examples and convert to test cases
      let rawSamples = detectedSampleInputs || [];
      if (rawSamples.length === 0 && extraction.domSampleInputs && extraction.domSampleInputs.length > 0) {
        rawSamples = extraction.domSampleInputs;
        populateSampleInputs(rawSamples);
      }
      if (rawSamples.length === 0 && extraction.testcaseBuffers && extraction.testcaseBuffers.length > 0) {
        rawSamples = extraction.testcaseBuffers;
        populateSampleInputs(rawSamples);
      }

      let testCases = [];
      if (rawSamples.length > 0) {
        testCases = parseUserSampleInputs(rawSamples);
      }

      // When zero public examples are detected, EdgeMind automatically engages
      // Context-Based Intelligence (Mode B) without requiring manual sample entry.
      // (Fallback notice preserved: "No public examples detected on this problem page.")

      // 7. Prepare problem context
      let probTitle = "";
      if (detectedPageInfo && isValidTitle(detectedPageInfo.title)) {
        probTitle = detectedPageInfo.title;
      }
      if (!probTitle) {
        probTitle = getFallbackTitle(currentTab);
      }
      if (!isValidTitle(probTitle)) {
        probTitle = "LeetCode Problem";
      }

      let probId = (detectedPageInfo && detectedPageInfo.problemId) ? detectedPageInfo.problemId : "";
      if (!probId && currentTab.url) {
        const urlMatch = currentTab.url.match(/problems\/([^/]+)/);
        if (urlMatch && urlMatch[1]) {
          probId = urlMatch[1];
        }
      }

      elPageTitle.textContent = probTitle;
      elPageTitle.title = probTitle;

      const rawConstraints = detectedPageInfo && detectedPageInfo.constraints ? detectedPageInfo.constraints : [];
      const normalizedConstraints = rawConstraints.map(c => normalizeCollapsedExponents(c));

      const paramSet = new Set();
      if (detectedPageInfo && Array.isArray(detectedPageInfo.parameters)) {
        detectedPageInfo.parameters.forEach(p => {
          if (p && typeof p === "string") paramSet.add(p);
        });
      }
      if (Array.isArray(testCases)) {
        testCases.forEach(tc => {
          if (tc && tc.input_data && typeof tc.input_data === "object") {
            Object.keys(tc.input_data).forEach(k => paramSet.add(k));
          }
        });
      }

      const problemContext = {
        platform: "leetcode",
        problem_id: probId,
        title: probTitle,
        description: detectedPageInfo ? detectedPageInfo.description : "",
        constraints: normalizedConstraints,
        parameters: Array.from(paramSet)
      };

      setLoading(true, "Evaluating domain partitions & generating edge-case candidates...");

      // 8. Dispatch analysis request to EdgeMind API
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

      let response;
      try {
        response = await fetch(`${API_BASE_URL}/api/v1/edgemind/analyze`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json"
          },
          body: JSON.stringify({
            code: code,
            filename: "leetcode_solution.py",
            problem_context: problemContext,
            test_cases: testCases,
            max_candidates: 10
          }),
          signal: controller.signal
        });
        clearTimeout(timeoutId);
      } catch (networkErr) {
        clearTimeout(timeoutId);
        setApiStatus("offline", "Offline");
        if (networkErr.name === "AbortError") {
          throw new Error("Analysis request timed out after 10 seconds. Please check server responsiveness.");
        }
        throw new Error(
          "Cannot connect to EdgeMind API at http://127.0.0.1:8000. Is the server running? Start it with: python -m uvicorn core.api:app --host 127.0.0.1 --port 8000"
        );
      }

      if (!response.ok) {
        setApiStatus("error", "Error");
        let errorDetail = `API returned error status ${response.status}.`;
        try {
          const errorJson = await response.json();
          if (errorJson && errorJson.detail) {
            errorDetail = errorJson.detail;
          }
        } catch {
          // Non-JSON response
        }
        throw new Error(errorDetail);
      }

      setApiStatus("connected", "Connected");

      // 9. Parse and validate report
      let reportData;
      try {
        reportData = await response.json();
      } catch {
        throw new Error("EdgeMind API returned malformed JSON response.");
      }

      if (!reportData || typeof reportData !== "object" || !("test_intelligence" in reportData)) {
        throw new Error("API response did not match the expected EdgeMind report schema.");
      }

      // 10. Handle INSUFFICIENT_CONTEXT warning gracefully
      if (reportData.status === "INSUFFICIENT_CONTEXT") {
        const warningMsg = (reportData.warnings && reportData.warnings.length > 0)
          ? reportData.warnings[0]
          : "No public examples detected on this problem page.";
        showError(warningMsg);
      }

      // 11. Render final report
      renderReport(reportData);
    } catch (err) {
      showError(err.message || "An unexpected error occurred during analysis.");
    } finally {
      setLoading(false);
    }
  }

  // Event Listeners
  elBtnAnalyze.addEventListener("click", handleAnalyze);
  elTabBtnIntel.addEventListener("click", () => switchTab("intel"));
  elTabBtnCode.addEventListener("click", () => switchTab("code"));

  if (elBtnToggleAllGaps) {
    elBtnToggleAllGaps.addEventListener("click", () => {
      isAllGapsExpanded = !isAllGapsExpanded;
      updateGapsDisplay();
    });
  }

  if (elBtnToggleAllCandidates) {
    elBtnToggleAllCandidates.addEventListener("click", () => {
      isAllCandidatesExpanded = !isAllCandidatesExpanded;
      updateCandidatesDisplay();
    });
  }

  elBtnToggleSamples.addEventListener("click", () => {
    elSamplesBody.classList.toggle("hidden");
    elBtnToggleSamples.classList.toggle("rotated");
  });

  elBtnTogglePatterns.addEventListener("click", () => {
    elPatternsBody.classList.toggle("hidden");
    elBtnTogglePatterns.classList.toggle("rotated");
  });

  // Initialize popup on open
  document.addEventListener("DOMContentLoaded", () => {
    checkApiHealth();
    inspectActiveTab();
  });
})();
