/**
 * EdgeMind LeetCode Solution & Input Buffer Extractor.
 *
 * Executed in the page's MAIN execution world via chrome.scripting.executeScript
 * to access Monaco Editor models directly without isolated-world restrictions.
 *
 * Guarantees:
 * - Accesses in-memory buffer via model.getValue() (avoids Monaco line virtualization)
 * - Targets the Python solution model
 * - Extracts active testcase/console editor models if present
 * - Halts safely if multiple candidate models exist
 * - Never executes code
 * - Never triggers Run or Submit buttons
 */
(() => {
  "use strict";

  // 1. Verify hostname
  const hostname = window.location.hostname || "";
  if (!hostname.includes("leetcode.com")) {
    return {
      success: false,
      error: "Active page is not LeetCode. EdgeMind currently supports LeetCode problem pages."
    };
  }

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
      language: activeEditorLang,
      error: `Active editor model language is '${activeEditorLang}'. EdgeMind currently analyzes Python only.`
    };
  }

  // 6. Query all active Monaco editor models
  const models = window.monaco.editor.getModels();
  if (!models || models.length === 0) {
    return {
      success: false,
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
        language: nonPyLang,
        error: `Detected non-Python editor language ('${nonPyLang}'). EdgeMind currently analyzes Python only.`
      };
    }
  }

  // Also collect DOM example inputs if available
  const domSampleInputs = [];
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

      if (extracted && !domSampleInputs.includes(extracted)) {
        domSampleInputs.push(extracted);
      }
    }

    if (domSampleInputs.length === 0) {
      const descContainer = document.querySelector(
        "[data-track-load='description_content'], .elfjS, div[class*='description'], div[class*='question-content']"
      ) || document.body;
      if (descContainer) {
        const descText = (typeof descContainer.innerText === "string" ? descContainer.innerText : descContainer.textContent) || "";
        const globalRegex = /(?:^|\b)Input\s*:\s*([\s\S]*?)(?=(?:Output\s*:|Explanation\s*:|\n\s*\n|$))/gi;
        let gMatch;
        while ((gMatch = globalRegex.exec(descText)) !== null) {
          const clean = cleanInputString(gMatch[1]);
          if (clean && !domSampleInputs.includes(clean)) {
            domSampleInputs.push(clean);
          }
        }
      }
    }
  } catch {
    // Ignore DOM extraction errors safely
  }

  // Case A: Active editor has a verified Python model
  if (activeEditorModel && activeEditorLang && activeEditorLang.includes("python")) {
    const code = activeEditorModel.getValue();
    return {
      success: true,
      code: code,
      language: activeEditorLang,
      modelUri: activeEditorModel.uri ? activeEditorModel.uri.toString() : "",
      testcaseBuffers: testcaseModels.map(m => m.value),
      domSampleInputs: domSampleInputs,
      source: "monaco"
    };
  }

  // Case B: Exactly one Python model found in memory
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
      testcaseBuffers: testcaseModels.map(m => m.value),
      domSampleInputs: domSampleInputs,
      source: "monaco"
    };
  }

  // Case C: Multiple Python models exist (filter non-empty)
  if (pythonModels.length > 1) {
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
        testcaseBuffers: testcaseModels.map(m => m.value),
        domSampleInputs: domSampleInputs,
        source: "monaco"
      };
    }

    return {
      success: false,
      language: "python",
      error: `Detected ${pythonModels.length} active Python editor models. To ensure safety, extraction was halted to prevent analyzing an incorrect buffer.`
    };
  }

  return {
    success: false,
    language: detectedPageLang || "unknown",
    error: "Could not identify an active Python solution editor model. Please ensure the editor is set to Python or Python3."
  };
})();
