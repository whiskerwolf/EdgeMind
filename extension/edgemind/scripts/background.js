/**
 * EdgeMind Background Service Worker.
 *
 * Coordinates automatic backend startup via Chrome Native Messaging:
 * - Triggers on Chrome profile startup (chrome.runtime.onStartup)
 * - Triggers on extension load/install (chrome.runtime.onInstalled)
 * - Handles on-demand startup requests from popup
 * - Prevents duplicate concurrent startup invocations (single-flight locking)
 * - Persists and broadcasts backend health status to extension UI
 */
(() => {
  "use strict";

  const NATIVE_HOST_NAME = "com.edgemind.native_host";
  const API_HEALTH_URL = "http://127.0.0.1:8000/health";
  const HEALTH_TIMEOUT_MS = 2000;

  let isStartupInProgress = false;
  let activeStartupPromise = null;

  /**
   * Fast check of backend health endpoint.
   */
  async function checkHealth() {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), HEALTH_TIMEOUT_MS);
    try {
      const resp = await fetch(API_HEALTH_URL, {
        method: "GET",
        signal: controller.signal
      });
      clearTimeout(timeoutId);
      if (resp.ok) {
        const data = await resp.json();
        return data && data.status === "healthy";
      }
      return false;
    } catch {
      clearTimeout(timeoutId);
      return false;
    }
  }

  /**
   * Send length-prefixed request to EdgeMind Native Messaging Host.
   */
  function sendNativeMessage(msg) {
    return new Promise((resolve, reject) => {
      chrome.runtime.sendNativeMessage(NATIVE_HOST_NAME, msg, response => {
        if (chrome.runtime.lastError) {
          reject(new Error(chrome.runtime.lastError.message));
        } else {
          resolve(response);
        }
      });
    });
  }

  /**
   * Update backend status in chrome.storage.local for popup consumption.
   */
  async function updateStatus(status, message, details = null) {
    const payload = {
      backendStatus: status, // "connected", "connecting", "offline", "error"
      statusMessage: message,
      details: details,
      updatedAt: Date.now()
    };
    try {
      await chrome.storage.local.set({ edgeMindBackend: payload });
    } catch (e) {
      console.warn("Storage update error:", e);
    }
    return payload;
  }

  /**
   * Main startup coordinator. Single-flight locked against duplicate invocations.
   */
  async function ensureBackendRunning(reason = "auto") {
    if (isStartupInProgress && activeStartupPromise) {
      console.log(`[EdgeMind Background] Startup already in progress (${reason}), awaiting existing task...`);
      return activeStartupPromise;
    }

    isStartupInProgress = true;
    activeStartupPromise = (async () => {
      try {
        console.log(`[EdgeMind Background] Initiating backend check/startup (trigger: ${reason})...`);
        await updateStatus("connecting", "Connecting to EdgeMind backend...");

        // 1. If already healthy, skip native host launch
        const alreadyHealthy = await checkHealth();
        if (alreadyHealthy) {
          console.log("[EdgeMind Background] Backend is already running and healthy.");
          return await updateStatus("connected", "Connected to EdgeMind backend.");
        }

        // 2. Request native host to start the backend
        console.log("[EdgeMind Background] Contacting Native Messaging Host to start backend...");
        let nativeResp;
        try {
          nativeResp = await sendNativeMessage({ action: "start_backend" });
        } catch (nativeErr) {
          console.error("[EdgeMind Background] Native Host invocation failed:", nativeErr);
          return await updateStatus(
            "offline",
            `Native Host Error: ${nativeErr.message}`,
            nativeErr.message
          );
        }

        console.log("[EdgeMind Background] Native Host responded:", nativeResp);

        // 3. Confirm health via HTTP socket
        let verified = false;
        const maxAttempts = 15;
        for (let i = 0; i < maxAttempts; i++) {
          await new Promise(r => setTimeout(r, 400));
          if (await checkHealth()) {
            verified = true;
            break;
          }
        }

        if (verified) {
          console.log("[EdgeMind Background] Backend verified healthy and reachable.");
          return await updateStatus("connected", "Connected to EdgeMind backend.");
        } else {
          const detail = nativeResp && nativeResp.message ? nativeResp.message : "Health check timed out.";
          console.warn("[EdgeMind Background] Backend failed to respond to /health:", detail);
          return await updateStatus("error", `Backend startup timed out: ${detail}`, detail);
        }
      } catch (err) {
        console.error("[EdgeMind Background] Unexpected startup error:", err);
        return await updateStatus("error", `Unexpected error: ${err.message}`, err.message);
      } finally {
        isStartupInProgress = false;
        activeStartupPromise = null;
      }
    })();

    return activeStartupPromise;
  }

  // =========================================================================
  // Extension Lifecycle Events
  // =========================================================================

  // Triggered when Chrome Profile 7 opens
  chrome.runtime.onStartup.addListener(() => {
    console.log("[EdgeMind Background] chrome.runtime.onStartup fired.");
    ensureBackendRunning("onStartup");
  });

  // Triggered when extension is loaded or updated
  chrome.runtime.onInstalled.addListener(() => {
    console.log("[EdgeMind Background] chrome.runtime.onInstalled fired.");
    ensureBackendRunning("onInstalled");
  });

  // Handle messages from popup
  chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (!request || !request.action) return false;

    if (request.action === "START_BACKEND") {
      ensureBackendRunning("popup_request").then(status => {
        sendResponse(status);
      });
      return true; // Keep message channel open for async response
    }

    if (request.action === "GET_BACKEND_STATUS") {
      chrome.storage.local.get(["edgeMindBackend"], res => {
        const current = (res && res.edgeMindBackend) || {
          backendStatus: "offline",
          statusMessage: "Backend status unknown"
        };
        sendResponse(current);
      });
      return true;
    }

    return false;
  });

})();

