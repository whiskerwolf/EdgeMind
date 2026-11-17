# EdgeMind â€” Chrome Web Store Production Release & Listing Specification

**Product Name:** EdgeMind
**Internal Package:** `dist/edgemind-chrome-web-store.zip`
**Manifest Version:** 3 (MV3 compliant)
**Version:** `1.0.0`
**Category:** Developer Tools / Productivity
**Default Language:** English

---

## 1. Store Descriptions

### 1.1 Short Description (Maximum 132 Characters)
```text
Adaptive static code analysis and edge-case test intelligence for Python solutions on LeetCode. Zero code execution.
```
*(Character count: 114 / 132)*

### 1.2 Full Description
```markdown
EdgeMind is an intelligent developer companion for technical interview preparation, providing real-time static code analysis and adaptive edge-case test intelligence for Python on LeetCode.

Unlike conventional code execution tools that run untrusted code in containers or cloud sandboxes, EdgeMind performs 100% deterministic, AST-driven static analysis. It identifies edge-case hazards, time/space complexity bottlenecks, recursion depth limits, and corner-case failures before you hit "Submit".

KEY CAPABILITIES:
- Instant Problem Context Extraction: Reads active LeetCode problem constraints, examples, and Monaco solution buffers without virtualized DOM degradation.
- Zero-Execution Static Intelligence: Evaluates Python abstract syntax trees (AST) locally without executing arbitrary code or consuming LeetCode submission quotas.
- Edge-Case Synthesis: Generates targeted boundary tests tailored to constraints (e.g. empty inputs, negative values, integer overflow, 10^9 scale, duplicates, and recursion limits).
- Complexity Diagnostics: Estimates algorithmic Big-O time and space complexity with clear theoretical breakdowns.
- Local Privacy Architecture: Analyzes code directly against your local EdgeMind backend. No code is transmitted to third-party ad networks or public telemetry servers.

HOW IT WORKS:
1. Open any Python problem on LeetCode.
2. Click the EdgeMind icon in your Chrome toolbar.
3. EdgeMind automatically reads the problem constraints and current solution draft.
4. Review generated edge cases, complexity feedback, and code hygiene hints.
5. Apply insights and submit with confidence.

REQUIREMENTS:
- Works seamlessly alongside the local EdgeMind engine for offline privacy or with managed EdgeMind team workspaces.
```

---

## 2. Permission Justifications (for Chrome Web Store Reviewers)

| Permission | Technical Requirement | Review Justification |
| :--- | :--- | :--- |
| `activeTab` | Temporary access to the currently active LeetCode tab upon user action (clicking popup). | Required to read the active problem tab and attach context when the developer opens EdgeMind. It only operates on the foreground tab when explicitly invoked. |
| `scripting` | `chrome.scripting.executeScript` into the page's `MAIN` execution world. | Required to safely read the in-memory Monaco editor solution buffer via `window.monaco.editor.getModels()`. LeetCode's editor uses virtualized DOM rendering; reading the buffer directly from Monaco is essential to prevent incomplete or missing code extraction. Does not execute user code. |
| `nativeMessaging` | `chrome.runtime.sendNativeMessage` targeting `com.edgemind.native_host`. | Required to communicate with the local Windows native host to verify backend health and start the local API service automatically in the background. |
| `storage` | `chrome.storage.local` | Used solely to cache developer UI preferences (theme, last status, view options) and local backend connectivity status across popup sessions. |
| `host_permissions` (`http://127.0.0.1:8000/*`, `http://localhost:8000/*`) | Local HTTP/REST API calls. | Required for the extension popup and background service worker to query the local EdgeMind FastAPI service (`/health`, `/api/v1/edgemind/analyze`). Scoped exclusively to local loopback. |

---

## 3. Privacy Policy Draft

```markdown
# Privacy Policy for EdgeMind Chrome Extension

Last Updated: November 17, 2026

1. Overview
EdgeMind ("we", "our", or "the extension") is committed to protecting your privacy. This Privacy Policy explains our data handling practices for the EdgeMind Chrome Extension and associated local software.

2. Information We Handle
- Source Code & Problem Context: When you click to analyze a LeetCode problem, EdgeMind reads your active Python solution code and problem constraints strictly to generate static analysis feedback and test recommendations.
- Local Storage: EdgeMind stores local UI preferences and connection states in your browser's chrome.storage.local.

3. Zero Third-Party Transmission
- EdgeMind does NOT sell, monetize, transmit, or share your source code, browsing activity, or personal information with third-party advertising networks, analytics providers, or external data brokers.
- No analytics SDKs, session trackers, or advertising scripts are embedded in the extension.

4. On-Premises & Local Data Processing
- Code analysis is performed by your designated local or self-hosted EdgeMind API backend.
- Communication occurs over encrypted channels or local loopback (127.0.0.1).

5. Security
- We enforce strict Manifest V3 Content Security Policies (`script-src 'self'`).
- The extension contains zero `eval()` calls and executes zero dynamic remote scripts.

6. Changes & Contact
Any future updates to this policy will be posted alongside extension updates. For questions regarding this policy, contact support@edgemind.dev.
```

---

## 4. Chrome Web Store Asset & Screenshot Checklist

| Asset | Dimensions | Requirement | Status |
| :--- | :--- | :--- | :--- |
| **Extension Icon 128x128** | `128 x 128 px` PNG | Standard icon in Web Store search and details | Ready (`icons/icon128.png`) |
| **Small Promo Tile** | `440 x 280 px` PNG/JPEG | Displayed in Chrome Web Store category listings | Specification drafted |
| **Large Marquee Promo** | `1400 x 560 px` PNG/JPEG | Optional featured placement tile | Specification drafted |
| **Screenshot 1** | `1280 x 800 px` (16:10) | EdgeMind popup analyzing Two Sum on LeetCode | Capture checklist defined |
| **Screenshot 2** | `1280 x 800 px` (16:10) | Edge-case boundary test generation cards | Capture checklist defined |
| **Screenshot 3** | `1280 x 800 px` (16:10) | Complexity breakdown & AST hygiene diagnostics | Capture checklist defined |
| **Screenshot 4** | `1280 x 800 px` (16:10) | Status indicator & seamless local backend health | Capture checklist defined |

---

## 5. Build & Packaging Verification

- **Package Location:** `dist/edgemind-chrome-web-store.zip`
- **Checksum File:** `dist/edgemind-chrome-web-store.zip.sha256`
- **Builder Command:** `python scripts/package_extension.py`
- **Prohibited Exclusions:** Confirmed that `.env`, `.git`, `*.py`, `README.md`, `tests/`, and backend source code are strictly omitted from the archive.
