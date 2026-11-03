/**
 * CodeDoctor Content Script.
 *
 * Runs in an isolated world on LeetCode pages.
 * Handles page metadata queries and health checks from popup.js.
 */
(() => {
  "use strict";

  chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request && request.action === "PING") {
      sendResponse({
        status: "OK",
        url: window.location.href,
        isLeetCode: window.location.hostname.includes("leetcode.com")
      });
      return true;
    }

    if (request && request.action === "GET_PAGE_INFO") {
      const problemTitleEl = document.querySelector(
        "div[data-cy='question-title'], .text-title-large, a[href*='/problems/']"
      );
      const title = problemTitleEl
        ? problemTitleEl.textContent.trim()
        : document.title;

      sendResponse({
        isLeetCode: window.location.hostname.includes("leetcode.com"),
        isProblemPage: window.location.pathname.includes("/problems/"),
        title: title || "LeetCode Problem",
        url: window.location.href
      });
      return true;
    }
  });
})();
