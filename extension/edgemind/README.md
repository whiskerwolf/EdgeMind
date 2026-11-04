# EdgeMind Chrome Extension

EdgeMind is an adaptive test-intelligence and static code analysis Chrome Manifest V3 extension. It maps input equivalence partitions, identifies coverage gaps, and synthesizes targeted edge-case candidates from the local EdgeMind API.

## Folder Layout

```text
extension/edgemind/
â”œâ”€â”€ manifest.json
â”œâ”€â”€ README.md
â”œâ”€â”€ icons/
â”‚   â”œâ”€â”€ icon16.png
â”‚   â”œâ”€â”€ icon48.png
â”‚   â””â”€â”€ icon128.png
â”œâ”€â”€ popup/
â”‚   â”œâ”€â”€ popup.html
â”‚   â”œâ”€â”€ popup.css
â”‚   â””â”€â”€ popup.js
â””â”€â”€ scripts/
    â”œâ”€â”€ content.js
    â””â”€â”€ extractor.js
```

## Running the EdgeMind Backend

From the project root:

```powershell
.venv\Scripts\python.exe -m uvicorn core.api:app --host 127.0.0.1 --port 8000
```

Verify backend health:

```powershell
curl.exe http://127.0.0.1:8000/health
```

Expected output:
```json
{"status":"healthy","service":"EdgeMind"}
```

## Loading the EdgeMind Extension in Google Chrome

1. Open Google Chrome.
2. Navigate to `chrome://extensions/`.
3. Enable **Developer mode** (top-right toggle).
4. Click **Load unpacked**.
5. Select the `extension/edgemind` directory.
6. Pin EdgeMind to the Chrome toolbar for quick access.

## Using EdgeMind on LeetCode

1. Navigate to any LeetCode problem page (e.g. `https://leetcode.com/problems/two-sum/`).
2. Ensure the problem editor language is set to **Python** or **Python3**.
3. Click the **EdgeMind** extension icon (`âš¡`).
4. Review the detected problem title and baseline input samples.
5. Click **Analyze & Discover Edge Cases**.
6. EdgeMind will display:
   - **Test Intelligence**: Identified input coverage gaps (severity, risk, suggested action) and ranked synthesized edge-case candidates.
   - **Code Health**: Deterministic static analysis score out of 100 with syntax, logic, quality, and complexity diagnostics.

## Guarantees & Disclaimers

- Pure static analysis and constraint-aware partition analysis.
- Code execution is permanently disabled; candidate expected outputs are null and unverified.
- All synthesized candidates are labeled with source `GENERATED_TEST`.
- No source code or browsing telemetry is transmitted externally.
