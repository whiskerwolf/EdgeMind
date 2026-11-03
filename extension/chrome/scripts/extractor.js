/**
 * CodeDoctor LeetCode Code Extractor.
 *
 * Executed in the page's MAIN execution world via chrome.scripting.executeScript
 * to access Monaco Editor models directly without isolated-world restrictions.
 *
 * Guarantees:
 * - Accesses full in-memory buffer via model.getValue() (avoids Monaco line virtualization)
 * - Identifies and targets the Python solution model
 * - Halts safely if multiple candidate models exist
 * - Never executes code
 * - Never interacts with Run or Submit buttons
 */
(() => {
  "use strict";

  // 1. Verify hostname
  const hostname = window.location.hostname || "";
  if (!hostname.includes("leetcode.com")) {
    return {
      success: false,
      error: "Active page is not LeetCode. CodeDoctor currently supports LeetCode problem pages."
    };
  }

  // 2. Detect language from page DOM (LeetCode language selector dropdown)
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

  // 3. Inspect Monaco global API
  if (
    typeof window.monaco === "undefined" ||
    !window.monaco.editor ||
    typeof window.monaco.editor.getModels !== "function"
  ) {
    // Check if Monaco is present in DOM but API is not yet loaded
    const hasMonacoDom = Boolean(document.querySelector(".monaco-editor"));
    if (hasMonacoDom) {
      return {
        success: false,
        language: detectedPageLang || "unknown",
        error: "Monaco editor detected, but its editor models are still initializing. Please wait a moment and try again."
      };
    }

    return {
      success: false,
      language: detectedPageLang || "unknown",
      error: "LeetCode code editor could not be found. Please ensure a problem page is open and fully loaded."
    };
  }

  // 4. Query all active Monaco editor models
  const models = window.monaco.editor.getModels();
  if (!models || models.length === 0) {
    return {
      success: false,
      language: detectedPageLang || "unknown",
      error: "No active Monaco editor models found. The editor may still be initializing."
    };
  }

  // Separate models by language and exclude console/testcase buffers
  const pythonModels = [];
  const nonPythonModels = [];

  for (const model of models) {
    const langId = (
      typeof model.getLanguageId === "function"
        ? model.getLanguageId()
        : typeof model.getModeId === "function"
        ? model.getModeId()
        : ""
    ).toLowerCase();

    const uriStr = model.uri ? model.uri.toString().toLowerCase() : "";

    // Ignore testcase / console / input models
    if (
      uriStr.includes("testcase") ||
      uriStr.includes("console") ||
      uriStr.includes("input") ||
      uriStr.includes("output")
    ) {
      continue;
    }

    if (langId === "python" || langId === "python3") {
      pythonModels.push(model);
    } else if (langId && langId !== "plaintext") {
      nonPythonModels.push({ model, langId });
    }
  }

  // Case A: Exactly one Python model found (ideal case)
  if (pythonModels.length === 1) {
    const targetModel = pythonModels[0];
    const code = targetModel.getValue();
    const finalLang =
      typeof targetModel.getLanguageId === "function"
        ? targetModel.getLanguageId()
        : "python";

    return {
      success: true,
      code: code,
      language: finalLang,
      modelUri: targetModel.uri ? targetModel.uri.toString() : "",
      source: "monaco"
    };
  }

  // Case B: Multiple Python models exist (e.g. tabs or cached buffers)
  if (pythonModels.length > 1) {
    // Filter models with non-empty code
    const modelsWithCode = pythonModels.filter(m => m.getValue().trim().length > 0);
    if (modelsWithCode.length === 1) {
      const targetModel = modelsWithCode[0];
      return {
        success: true,
        code: targetModel.getValue(),
        language:
          typeof targetModel.getLanguageId === "function"
            ? targetModel.getLanguageId()
            : "python",
        modelUri: targetModel.uri ? targetModel.uri.toString() : "",
        source: "monaco"
      };
    }

    return {
      success: false,
      language: "python",
      error: `Detected ${pythonModels.length} active Python editor models. To ensure safety, extraction was halted to prevent analyzing an incorrect buffer.`
    };
  }

  // Case C: Non-Python model active
  if (nonPythonModels.length > 0) {
    const activeLang = nonPythonModels[0].langId;
    return {
      success: false,
      language: activeLang,
      error: `Detected non-Python editor language ('${activeLang}'). CodeDoctor currently analyzes Python only.`
    };
  }

  // Case D: Page language dropdown indicates non-Python
  if (detectedPageLang && !detectedPageLang.includes("python")) {
    return {
      success: false,
      language: detectedPageLang,
      error: `LeetCode language is set to '${detectedPageLang}'. CodeDoctor currently analyzes Python only.`
    };
  }

  return {
    success: false,
    language: detectedPageLang || "unknown",
    error: "Could not identify an active Python solution editor model. Please ensure the editor is set to Python or Python3."
  };
})();
