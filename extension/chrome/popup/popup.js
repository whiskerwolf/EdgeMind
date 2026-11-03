/**
 * CodeDoctor Extension Popup Controller.
 *
 * Coordinates:
 * - API health verification (GET /health)
 * - Code extraction via MAIN-world script injection
 * - Language validation (Python/Python3 only)
 * - Client-side source size validation (max 64 KiB)
 * - Dispatching static analysis (POST /api/v1/analyze)
 * - Safe DOM rendering without string-based DOM injection
 */
(() => {
  "use strict";

  // Configuration constants
  const API_BASE_URL = "http://127.0.0.1:8000";
  const MAX_SOURCE_SIZE = 64 * 1024; // 64 KiB (65,536 bytes)
  const REQUEST_TIMEOUT_MS = 6000;

  // DOM Elements
  const elApiStatus = document.getElementById("api-status");
  const elApiStatusText = document.getElementById("api-status-text");
  const elPageTitle = document.getElementById("page-title");
  const elLangBadge = document.getElementById("lang-badge");
  const elBtnAnalyze = document.getElementById("btn-analyze");
  const elLoadingState = document.getElementById("loading-state");
  const elErrorBanner = document.getElementById("error-banner");
  const elErrorMessage = document.getElementById("error-message");
  const elEmptyState = document.getElementById("empty-state");
  const elResultsSection = document.getElementById("results-section");
  const elScoreValue = document.getElementById("score-value");
  const elOverallStatusBadge = document.getElementById("overall-status-badge");
  const elErrorsCount = document.getElementById("errors-count");
  const elWarningsCount = document.getElementById("warnings-count");
  const elSectionPills = document.getElementById("section-pills");
  const elFindingsList = document.getElementById("findings-list");
  const elNoFindingsMessage = document.getElementById("no-findings-message");
  const elFindingsTitle = document.getElementById("findings-title");

  let currentTab = null;
  let isApiOnline = false;

  /**
   * Safe helper to remove all children from a DOM container.
   */
  function clearElement(element) {
    while (element.firstChild) {
      element.removeChild(element.firstChild);
    }
  }

  /**
   * Set API connection status indicator.
   */
  function setApiStatus(status, text) {
    elApiStatus.className = `api-status ${status}`;
    elApiStatusText.textContent = text;
    isApiOnline = status === "online";
  }

  /**
   * Display or hide error alert banner safely.
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
  function setLoading(isLoading) {
    if (isLoading) {
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
   * Check whether CodeDoctor API is reachable.
   */
  async function checkApiHealth() {
    setApiStatus("checking", "Checking API...");
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 2500);

    try {
      const response = await fetch(`${API_BASE_URL}/health`, {
        method: "GET",
        signal: controller.signal
      });
      clearTimeout(timeoutId);

      if (response.ok) {
        const data = await response.json();
        if (data && data.status === "healthy") {
          setApiStatus("online", "API Online");
          return true;
        }
      }
      setApiStatus("offline", "API Error");
      return false;
    } catch {
      clearTimeout(timeoutId);
      setApiStatus("offline", "API Offline");
      return false;
    }
  }

  /**
   * Inspect active tab to confirm if it is a LeetCode problem page.
   */
  async function inspectActiveTab() {
    try {
      const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
      if (!tabs || tabs.length === 0) {
        elPageTitle.textContent = "No active tab";
        return null;
      }

      currentTab = tabs[0];
      const url = currentTab.url || "";

      if (url.includes("leetcode.com")) {
        elPageTitle.textContent = currentTab.title ? currentTab.title.replace(" - LeetCode", "") : "LeetCode Problem";
        elLangBadge.className = "badge badge-neutral";
        elLangBadge.textContent = "Python";
      } else {
        elPageTitle.textContent = "Not a LeetCode tab";
        elLangBadge.className = "badge badge-skip";
        elLangBadge.textContent = "Unsupported Site";
      }

      return currentTab;
    } catch (err) {
      elPageTitle.textContent = "Tab error";
      return null;
    }
  }

  /**
   * Render diagnostic section status pill (Syntax, Logic, Quality, Complexity, Runtime).
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
   * Safely render individual finding cards into the DOM.
   */
  function renderFindingCard(finding, isError) {
    const card = document.createElement("div");
    card.className = `finding-card ${isError ? "finding-error" : "finding-warning"}`;

    // Header row: Type and Line badge
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

    // Problem description
    if (finding.message) {
      const msg = document.createElement("p");
      msg.className = "finding-message";
      msg.textContent = finding.message;
      card.appendChild(msg);
    }

    // Explanation / Why
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

    // Suggested Fix
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
   * Render complete analysis report.
   */
  function renderReport(report) {
    elEmptyState.classList.add("hidden");
    elResultsSection.classList.remove("hidden");

    // Score
    const score = typeof report.score === "number" ? report.score : 0;
    elScoreValue.textContent = String(score);

    // Overall status badge
    const overall = report.overall_status || report.status || "UNKNOWN";
    elOverallStatusBadge.textContent = overall;
    elOverallStatusBadge.className = "badge badge-lg";

    if (overall === "PASS") {
      elOverallStatusBadge.classList.add("badge-pass");
    } else if (overall === "PASS WITH WARNINGS") {
      elOverallStatusBadge.classList.add("badge-warn");
    } else {
      elOverallStatusBadge.classList.add("badge-fail");
    }

    // Counts
    const errorCount = report.total_errors || (report.detailed_errors ? report.detailed_errors.length : 0);
    const warningCount = report.total_warnings || (report.detailed_warnings ? report.detailed_warnings.length : 0);
    elErrorsCount.textContent = `${errorCount} ${errorCount === 1 ? "Error" : "Errors"}`;
    elWarningsCount.textContent = `${warningCount} ${warningCount === 1 ? "Warning" : "Warnings"}`;

    // Section status pills
    clearElement(elSectionPills);
    const summary = report.summary || {};
    elSectionPills.appendChild(renderPill("Syntax", summary.syntax || report.syntax_status || "PASS"));
    elSectionPills.appendChild(renderPill("Logic", summary.logic || report.logic_status || "PASS"));
    elSectionPills.appendChild(renderPill("Quality", summary.quality || report.quality_status || "PASS"));
    elSectionPills.appendChild(renderPill("Complexity", summary.complexity || report.complexity_status || "PASS"));
    elSectionPills.appendChild(renderPill("Runtime", summary.runtime || report.runtime_status || "SKIPPED"));

    // Render findings
    clearElement(elFindingsList);
    const errors = report.detailed_errors || [];
    const warnings = report.detailed_warnings || [];
    const totalFindings = errors.length + warnings.length;

    elFindingsTitle.textContent = `Diagnostic Findings (${totalFindings})`;

    if (totalFindings === 0) {
      elNoFindingsMessage.classList.remove("hidden");
    } else {
      elNoFindingsMessage.classList.add("hidden");
      errors.forEach(e => elFindingsList.appendChild(renderFindingCard(e, true)));
      warnings.forEach(w => elFindingsList.appendChild(renderFindingCard(w, false)));
    }
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

    setLoading(true);

    try {
      // 2. Execute extraction script in MAIN world to query Monaco model
      const injectionResults = await chrome.scripting.executeScript({
        target: { tabId: currentTab.id },
        files: ["scripts/extractor.js"],
        world: "MAIN"
      });

      if (!injectionResults || injectionResults.length === 0 || !injectionResults[0].result) {
        throw new Error("Unable to communicate with the LeetCode editor. Please ensure the page has finished loading.");
      }

      const extraction = injectionResults[0].result;

      // Handle extraction errors
      if (!extraction.success) {
        throw new Error(extraction.error || "Failed to extract code from LeetCode editor.");
      }

      const code = extraction.code;
      const detectedLang = (extraction.language || "").toLowerCase();

      // Update language badge
      elLangBadge.textContent = detectedLang ? detectedLang.toUpperCase() : "PYTHON";
      elLangBadge.className = "badge badge-neutral";

      // 3. Validate language (Python / Python3 only)
      if (!detectedLang.includes("python")) {
        elLangBadge.className = "badge badge-fail";
        throw new Error(
          `Detected editor language '${extraction.language}'. CodeDoctor only analyzes Python code.`
        );
      }

      // 4. Validate source content
      if (!code || !code.trim()) {
        throw new Error("The LeetCode editor is empty. Please enter or reset solution code before analyzing.");
      }

      // 5. Enforce 64 KiB size limit client-side before sending
      const sourceByteSize = new TextEncoder().encode(code).length;
      if (sourceByteSize > MAX_SOURCE_SIZE) {
        throw new Error(
          `Code size (${sourceByteSize} bytes) exceeds the maximum allowed limit of ${MAX_SOURCE_SIZE} bytes (64 KiB).`
        );
      }

      // 6. Dispatch static analysis request to CodeDoctor API
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

      let response;
      try {
        response = await fetch(`${API_BASE_URL}/api/v1/analyze`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json"
          },
          body: JSON.stringify({
            code: code,
            filename: "leetcode_solution.py"
          }),
          signal: controller.signal
        });
        clearTimeout(timeoutId);
      } catch (networkErr) {
        clearTimeout(timeoutId);
        if (networkErr.name === "AbortError") {
          throw new Error("Analysis request timed out after 6 seconds. Please check server responsiveness.");
        }
        throw new Error(
          "Cannot connect to CodeDoctor API at http://127.0.0.1:8000. Is the server running? Start it with: uvicorn core.api:app --host 127.0.0.1 --port 8000"
        );
      }

      // Handle non-200 responses
      if (!response.ok) {
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

      // 7. Parse and validate report schema
      let reportData;
      try {
        reportData = await response.json();
      } catch {
        throw new Error("API returned malformed JSON response.");
      }

      if (!reportData || typeof reportData !== "object" || !("score" in reportData)) {
        throw new Error("API response did not match the expected CodeDoctor report schema.");
      }

      // 8. Render final report
      renderReport(reportData);
    } catch (err) {
      showError(err.message || "An unexpected error occurred during analysis.");
    } finally {
      setLoading(false);
    }
  }

  // Event Listeners
  elBtnAnalyze.addEventListener("click", handleAnalyze);

  // Initialize popup on open
  document.addEventListener("DOMContentLoaded", () => {
    checkApiHealth();
    inspectActiveTab();
  });
})();
