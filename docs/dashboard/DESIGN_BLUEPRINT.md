# EdgeMind Web Dashboard: Design System & Visual Blueprint

**Project**: EdgeMind Developer Intelligence Platform  
**Phase**: 6.3 - Design System & Visual Blueprint  
**Document**: `docs/dashboard/DESIGN_BLUEPRINT.md`  
**Date**: November 2026  
**Status**: APPROVED IMPLEMENTATION BLUEPRINT  

---

## 1. Executive Summary & Design Vision

This document establishes the implementation-ready design system, layout specifications, component architecture, and visual wireframes for the **EdgeMind Web Dashboard**. Built upon the approved research in `docs/dashboard/DESIGN_RESEARCH.md`, this blueprint translates high-level principles into exact pixel, token, layout, and behavioral decisions before any frontend code is authored.

### Design Vision: "The Precision Developer Intelligence Workspace"
EdgeMind is a developer-first tool. Its visual language reflects the technical rigor of modern software engineering:
- **Restrained & Monochromatic**: 95% of the visual structure relies on grayscale luminance across stepped obsidian surfaces (`#090A0F` to `#171927`).
- **Precision Typography**: Geometric clarity via `Inter Variable` with custom stylistic sets for interface labels, paired with `JetBrains Mono` with tabular figures for code, AST variables, line numbers, and metric counters.
- **Data-Dense & Non-Decorative**: Zero gimmick radial gauges, zero random gradients, zero glowing card borders, and zero fabricated "+14% this week" trend badges. Every UI element reflects verified static analysis, Adaptive Test Intelligence, or streaming AI diagnosis data from the EdgeMind FastAPI backend.
- **Keyboard-First & High Performance**: Global `Cmd+K` command interface, standard shortcut navigation (`⌘↵` to run analysis, `Esc` to dismiss), sub-150ms transitions, and an asymmetrical split-pane IDE-style workbench.

---

## 2. Finalized Design System Tokens

### 2.1 Color System

The EdgeMind palette is built on an **achromatic obsidian scale** with high-contrast functional color used exclusively for diagnostic status, interactive focus, and brand identity.

```css
:root {
  /* =========================================================================
     1. Surface Elevation Ladder (Cool Obsidian Undertones)
     ========================================================================= */
  --em-canvas:             #090A0F; /* Level 0: Viewport background floor */
  --em-surface-sidebar:    #0D0E15; /* Level 1: Sidebar rail & top bar */
  --em-surface-workspace:  #10121C; /* Level 2: Primary code editor & panels */
  --em-surface-card:       #141624; /* Level 3: Cards, table rows, finding tiles */
  --em-surface-elevated:   #191C2E; /* Level 4: Hovered rows, active selection */
  --em-surface-overlay:    #1F233A; /* Level 5: Dropdowns, popovers, modals */

  /* =========================================================================
     2. Hairlines, Dividers & Borders
     ========================================================================= */
  --em-border-hairline:    rgba(255, 255, 255, 0.06); /* Subtle internal dividers */
  --em-border-default:     #1E2235;                   /* Standard panel & card borders */
  --em-border-strong:      #2D334F;                   /* Hovered borders, active inputs */
  --em-border-focus:       #38BDF8;                   /* Focus ring (Sky-400) */

  /* =========================================================================
     3. Ink & Typographic Contrast Tokens
     ========================================================================= */
  --em-text-primary:       #F8FAFC; /* 98% Luminance: Headings, primary code */
  --em-text-secondary:     #CBD5E1; /* 85% Luminance: Body copy, findings */
  --em-text-muted:         #94A3B8; /* 65% Luminance: Labels, breadcrumbs, tags */
  --em-text-dim:           #64748B; /* 45% Luminance: Line numbers, shortcuts */
  --em-text-disabled:      #475569; /* 35% Luminance: Disabled buttons/inputs */

  /* =========================================================================
     4. Interactive Accent Tokens
     ========================================================================= */
  --em-accent-primary:     #38BDF8; /* Electric Cyan (Sky-400) */
  --em-accent-hover:       #0284C7; /* Sky-600 */
  --em-accent-subtle:      rgba(56, 189, 248, 0.10); /* Active pill backgrounds */
  --em-brand-indigo:       #818CF8; /* Indigo-400 (Brand emblem gradient) */
  --em-brand-gradient:     linear-gradient(135deg, #38BDF8 0%, #818CF8 100%);

  /* =========================================================================
     5. Semantic Diagnostic States (Directly mapped to core/analyzer.py)
     ========================================================================= */
  /* Error (SyntaxError, ZeroDivisionError, NameError, LogicError) */
  --em-status-error:          #EF4444; /* Red-500 */
  --em-status-error-bg:       rgba(239, 68, 68, 0.08);
  --em-status-error-border:   rgba(239, 68, 68, 0.25);
  --em-status-error-text:     #FCA5A5; /* Red-300 */

  /* Warning (HighComplexity, UnusedVariable, DeepNesting, Smells) */
  --em-status-warning:        #F59E0B; /* Amber-500 */
  --em-status-warning-bg:     rgba(245, 158, 11, 0.08);
  --em-status-warning-border: rgba(245, 158, 11, 0.25);
  --em-status-warning-text:   #FCD34D; /* Amber-300 */

  /* Info / Adaptive Test Intelligence / Context */
  --em-status-info:           #38BDF8; /* Sky-400 */
  --em-status-info-bg:        rgba(56, 189, 248, 0.08);
  --em-status-info-border:    rgba(56, 189, 248, 0.25);
  --em-status-info-text:      #7DD3FC; /* Sky-300 */

  /* Success / Pass / Valid Candidates */
  --em-status-success:        #10B981; /* Emerald-500 */
  --em-status-success-bg:     rgba(16, 185, 129, 0.08);
  --em-status-success-border: rgba(16, 185, 129, 0.25);
  --em-status-success-text:   #6EE7B7; /* Emerald-300 */
}
```

---

### 2.2 Typography System

EdgeMind enforces a dual-typeface system with strict typographic discipline:

1. **Primary Interface Font**: `Inter Variable, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif`
   - Feature flags: `font-feature-settings: "cv01" 1, "cv02" 1, "cv11" 1, "ss01" 1;` (Yields clear uppercase `I`, digit `1`, curved lowercase `l`).
2. **Code, Telemetry & Tabular Figures**: `JetBrains Mono, Geist Mono, Menlo, Monaco, Consolas, monospace`
   - Feature flags: `font-variant-numeric: tabular-nums;` (Guarantees zero column jitter when scores or line numbers update).

#### Typographic Scale Table

| Token | Size | Weight | Line Height | Tracking | Purpose / Usage |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `type-title-lg` | 20px (1.25rem) | 600 (Semibold) | 28px | -0.02em | Page titles (Overview, Workspace) |
| `type-title-md` | 16px (1.00rem) | 600 (Semibold) | 22px | -0.015em | Panel headings, modal titles, card groups |
| `type-body-md` | 14px (0.875rem) | 500 (Medium) | 20px | -0.005em | Primary buttons, active tabs, summary labels |
| `type-body-sm` | 13px (0.8125rem) | 400 (Regular) | 18px | 0.00em | Diagnostic messages, why/fix text, table content |
| `type-caption` | 11px (0.6875rem) | 500 (Medium) | 14px | +0.02em | Badges, line pills, uppercase category eyebrows |
| `type-code-body`| 13px (0.8125rem) | 400 (Regular) | 20px | 0.00em | Monaco code editor, snippet context previews |
| `type-code-meta`| 12px (0.75rem) | 500 (Medium) | 16px | 0.00em | Latency metrics (14.2ms), scores (80/100), hashes |

---

### 2.3 Spacing, Grid & Sizing

The layout adheres strictly to an **8-point spatial system** with a 4-point micro-grid:

```
--em-space-1:   4px
--em-space-2:   8px
--em-space-3:   12px
--em-space-4:   16px
--em-space-5:   20px
--em-space-6:   24px
--em-space-8:   32px
--em-space-10:  40px
--em-space-12:  48px
```

- **Base Layout Padding**: Desktop viewports use `20px` gutter padding; compact/tablet use `16px`; mobile uses `12px`.
- **Card Padding**: Compact items use `12px 14px`; standard containers use `16px 18px`.
- **Table Row Heights**: Compact data table row is `36px`; standard finding row is `44px`.
- **Border Radius Tokens**:
  - `radius-sm`: `4px` (Keycap badges, tooltips, line number tags)
  - `radius-md`: `6px` (Standard buttons, inputs, filter pills, dropdown items)
  - `radius-lg`: `8px` (Cards, panels, modal dialogs, Monaco shell)
  - `radius-full`: `9999px` (Status indicators, pill counters, filter toggles)

---

### 2.4 Elevation, Hairlines & Shadow Policy

- **Shadow Policy**: Deep dark mode interfaces must not use heavy blurred drop shadows. Shadows appear muddy and artificial against `#090A0F`. Instead:
  - Surface differentiation is achieved by stepping up surface luminance (`--em-surface-*`).
  - Structural delineation is achieved via 1px crisp borders (`box-shadow: 0 0 0 1px var(--em-border-default)`).
- **Modal Elevation**: Floating dialogs and popovers use Level 5 surface (`#1F233A`) paired with a tight dark boundary:
  `box-shadow: 0 0 0 1px #2D334F, 0 16px 48px -8px rgba(0, 0, 0, 0.75)`.

---

## 3. Application Shell Specification

The application shell provides the framing context across all routes:

```
+---------------------------------------------------------------------------------------------------------+
| Top Bar (52px): [Brand Lockup] EdgeMind   /workspace   [● Backend Online: 8000] [⌘K Search] [Analyze ⌘↵]|
+---------+-----------------------------------------------------------------------------------------------+
| Sidebar | Main Workspace Region (calc(100vh - 52px - 28px))                                             |
| 240px   |                                                                                               |
|         |                                                                                               |
|         |                                                                                               |
|         |                                                                                               |
+---------+-----------------------------------------------------------------------------------------------+
| Footer Bar (28px): [Python 3.13]  [Mode: Stateless]  [Ollama: qwen3:4b]  [Latency: 14.2ms] [UTF-8]      |
+---------------------------------------------------------------------------------------------------------+
```

### 3.1 Sidebar Navigation
- **Dimensions**: Expanded width: `240px`; Collapsed icon-rail width: `64px`.
- **Header**: Features the official SVG brand emblem (Cyan-to-Indigo gradient) + `EdgeMind` logotype (`14px semibold`) with an uppercase `DEV WORKSPACE` eyebrow (`9px`).
- **Navigation Groups**:
  - **ANALYSIS**:
    - `Workspace` (Icon: `Code2`, Route: `/workspace`)
    - `Findings` (Icon: `AlertCircle`, Route: `/findings`, Badge: dynamic error count)
    - `Adaptive Intel` (Icon: `Cpu`, Route: `/test-intelligence`, Badge: gap count)
  - **MANAGEMENT**:
    - `Overview` (Icon: `LayoutDashboard`, Route: `/`)
    - `History` (Icon: `Clock`, Route: `/history`)
  - **SYSTEM**:
    - `Settings` (Icon: `Settings`, Route: `/settings`)
- **Active Navigation Styling**:
  - Background: `rgba(56, 189, 248, 0.08)`
  - Border left: `2px solid var(--em-accent-primary)`
  - Text color: `#F8FAFC` (Semibold 500)
  - Icon color: `#38BDF8`
- **Collapsed Tooltip**: When collapsed to 64px, hovering an icon instantly renders a clean Level 4 tooltip (`#1D2032`, `radius-sm`, `11px font`) offset by 8px to the right.
- **Mobile Drawer**: On screens $< 768\text{px}$, the sidebar transforms into an off-canvas drawer controlled by a top-left hamburger button and dismissable via swipe or overlay tap.

### 3.2 Top Header
- **Height**: Fixed `52px`, bordered at bottom with `--em-border-default` (`#1E2235`).
- **Breadcrumb Navigation**: `Workspace / snippet.py` with `13px medium` text and subtle chevron separators.
- **System Health Pill**:
  - Live pulse dot (8px green `#10B981` when healthy, amber `#F59E0B` when degraded, red `#EF4444` when unreachable).
  - Label: `Backend 8000` with tooltip showing exact latency (`14.2ms`) and version (`1.0.0`).
- **Global Actions**:
  - Quick Search button (`⌘K` indicator pill)
  - Primary CTA: `Run Analysis` button (`#38BDF8`, text `#090A0F`, icon `Play`, shortcut `⌘↵`).

### 3.3 Command Palette (`Cmd+K`)
- Triggered by `Cmd+K` (macOS) or `Ctrl+K` (Windows/Linux).
- Centered modal (`560px` width) with backdrop blur and Level 5 surface (`#1F233A`).
- Fuzzy-filters actions: "Run Static Analysis", "Open Clean Snippet Template", "Explain Active Finding", "Toggle Layout Split", "Export Report JSON", "Clear Diagnostics".

### 3.4 Persistent Footer Status Bar
- **Height**: Fixed `28px`, background `--em-surface-sidebar` (`#0D0E15`), border top `--em-border-default`.
- **Items (Left to Right)**:
  - Runtime: `Python 3.13 (Static AST)`
  - Persistence Mode: `Stateless (In-Memory)` or `Database (PostgreSQL Connected)`
  - Active AI Model: `Ollama: qwen3:4b (Local)`
  - Last Run Latency: `12.4ms`
  - Source Size: `1.2 KiB / 64 KiB`

---

## 4. Page-by-Page Visual Blueprints

### 4.1 Overview (`/`)
- **Purpose**: System pulse, recent analysis health, score distribution, and benchmark templates.
- **Design Decision on Radial Gauges**: Gimmick circular gauges are **rejected**. Radial gauges consume excessive vertical space while conveying only a single number. Instead, EdgeMind uses a **High-Precision Linear Metric Strip** showing exact score, status badge, issue counters, and response time with tabular numbers.

```
+----------------------------------------------------------------------------------------------------+
| OVERVIEW                                                                                           |
| Developer Intelligence & System Diagnostics                                                        |
+----------------------------------------------------------------------------------------------------+
| SYSTEM STATUS & BENCHMARK SUMMARY                                                                  |
| [● Backend Healthy]  [Service: EdgeMind 1.0.0]  [AI: Ollama qwen3:4b]  [Storage: In-Memory / Ready]|
+----------------------------------------------------------------------------------------------------+
| ACTIVE ANALYSIS METRICS (Last Executed Analysis)                                                   |
| +--------------------+ +--------------------+ +--------------------+ +--------------------+       |
| | CODE SCORE         | | TOTAL ISSUES       | | ERRORS (CRITICAL)  | | WARNINGS / SMELLS  |       |
| | 80 / 100           | | 2 Findings         | | 1 Syntax / Runtime | | 1 Code Smell       |       |
| | [PASS W/ WARNINGS] | | Score penalty: -20 | | Penalty: -20 pts   | | Penalty: -5 pts    |       |
| +--------------------+ +--------------------+ +--------------------+ +--------------------+       |
+----------------------------------------------------------------------------------------------------+
| QUICK BENCHMARK TEMPLATES (Click to load into Workspace)                                           |
| +--------------------------------+ +--------------------------------+ +-------------------------+ |
| | Clean Function (100/100)       | | Divide-by-Zero Trap (80/100)   | | High Complexity (75/100)| |
| | def add(a, b): return a + b    | | def calc(a, b): return a / b   | | Nested loops & logic  | |
| | [Load Template ↗]              | | [Load Template ↗]              | | [Load Template ↗]     | |
| +--------------------------------+ +--------------------------------+ +-------------------------+ |
+----------------------------------------------------------------------------------------------------+
| RECENT ANALYSIS ACTIVITY                                                                           |
| [Search sessions...]                                                    [Filter: All Modes ▾]     |
| TIME      FILE         STATUS               SCORE   ERRORS   WARNINGS   DURATION   ACTION          |
| 20:14:10  calc.py      PASS WITH WARNINGS   80/100  1        1          12.4ms     [Open in Editor]|
| 20:12:02  snippet.py   PASS                 100/100 0        0          8.1ms      [Open in Editor]|
+----------------------------------------------------------------------------------------------------+
```

- **Empty State**: Renders informative card: *"No analysis executed yet. Run an analysis in Workspace or select a quick benchmark template above."*
- **API Failure State**: Renders high-visibility banner: *"Backend connection refused at 127.0.0.1:8000. Ensure the EdgeMind API is running via scripts/start_edgemind_api.ps1."*

---

### 4.2 Code Workspace (`/workspace`)
- **Purpose**: Core IDE-style coding, file upload, AST analysis, and findings review workbench.
- **Layout**: Asymmetrical 55/45 split pane with resizable border separator.

```
+----------------------------------------------------+-----------------------------------------------+
| EDITOR TOOLBAR: snippet.py [64 KiB Max]  [Upload ⇪]| RESULTS: 80/100 [PASS W/ WARNINGS]  12.4ms    |
| [Format Code]  [Clear]               [Run Analysis ⌘↵]| TABS: [Findings (2)]  [Test Intel]  [Raw JSON]|
+----------------------------------------------------+-----------------------------------------------+
| 1  def calculate_average(numbers: list) -> float:  | FILTERS: [All (2)] [Errors (1)] [Warnings (1)]|
| 2      total = sum(numbers)                        |                                               |
| 3      return total / len(numbers)  ~~~~~~~~~~~~~~ | #finding-0  ZeroDivisionError          Line 3 |
| 4                                   [ZeroDivision] | Division by zero when 'numbers' is empty.     |
| 5  def format_result(val: float) -> str:           | WHY: len(numbers) evaluates to 0 on empty list|
| 6      res = f"Average: {val}"                     | FIX: Add check: if not numbers: return 0.0    |
| 7      return res                                  | [View Context ▾]       [Explain Finding 🪄]   |
| 8                                                  +-----------------------------------------------+
| 9                                                  | #finding-1  UnusedVariable             Line 6 |
| 10                                                 | Variable 'res' is assigned but never reused.  |
|                                                    | WHY: Immediate return of redundant temporary. |
|                                                    | FIX: Inline return f"Average: {val}".         |
|                                                    | [View Context ▾]       [Explain Finding 🪄]   |
+----------------------------------------------------+-----------------------------------------------+
```

- **Monaco Editor Placement**: Left pane, initialized with dark theme matching `--em-surface-workspace` (`#10121C`), JetBrains Mono 13px, line height 20px, minimap disabled on viewports $< 1366\text{px}$.
- **Mobile Strategy**: On screens $< 768\text{px}$, the split view is replaced by a **Tabbed Mobile Workbench**:
  `[ Tab: Code Editor (Full) ] | [ Tab: Findings (2) ] | [ Tab: AI Diagnosis ]`.
  A persistent bottom floating toolbar provides `[ Run Analysis ]` and `[ Upload File ]`.

---

### 4.3 Findings Explorer (`/findings`)
- **Purpose**: Searchable, deep diagnostic issue stream with Sentry-style tokenized filtering.

```
+----------------------------------------------------------------------------------------------------+
| FINDINGS EXPLORER                                                                                  |
| Inspect static analysis issues, code quality findings, and security boundary warnings              |
+----------------------------------------------------------------------------------------------------+
| FILTER QUERY: [🔍 is:error rule:ZeroDivisionError                                   ] [Reset Filters]|
| QUICK TOGGLES: [All (2)]  [● Errors (1)]  [▲ Warnings (1)]  [ℹ Info (0)]   SORT: [Line Number (Asc) ▾] |
+----------------------------------------------------------------------------------------------------+
| [● ERROR] ZeroDivisionError                                                      Line 3 · snippet.py|
| Message: Division by zero when evaluated with empty collection.                                     |
| Location: Line 3, Column 12                                                                         |
|                                                                                                    |
| Root Cause (Static Analysis):                                                                      |
| Python raises ZeroDivisionError at runtime when dividing by an integer zero or empty length count. |
|                                                                                                    |
| Recommended Remediation:                                                                            |
| Guard the division with a boundary check: if not numbers: return 0.0                               |
|                                                                                                    |
| Code Context Preview:                                                                              |
|   1 | def calculate_average(numbers: list) -> float:                                               |
|   2 |     total = sum(numbers)                                                                     |
| > 3 |     return total / len(numbers)                                                               |
|   4 |                                                                                               |
|                                                                                                    |
| ACTIONS: [Copy Rule ID]   [Jump to Line in Editor ↗]                     [Explain with AI 🪄 (SSE)]|
+----------------------------------------------------------------------------------------------------+
```

---

### 4.4 AI Diagnosis Integration (Streaming SSE)
- **Integration**: Nested directly inside any finding card or rendered in a dedicated right-hand side drawer.
- **Trigger**: User clicks `Explain Finding 🪄`.
- **Streaming Lifecycle**:
  1. **Initiation**: `POST /api/v1/diagnose/stream` is called with `DiagnoseFindingRequest`. Button turns to `Streaming...` with a rotating spinner and timer (`0.0s`).
  2. **SSE Streaming**:
     - `event: diagnosis_started`: Captures session ID (`diag_7da680563647`).
     - `event: response_chunk`: Tokens append smoothly into a Markdown block.
     - `event: completed`: Stops timer (`Completed in 14.8s · 412 tokens`).
     - `event: error`: Renders error card with retry action.
  3. **Cancellation**: A prominent `[Cancel]` button aborts the browser `AbortController`. The card preserves partial tokens and marks state as `[Diagnosis Cancelled]`.
  4. **Markdown Formatting**: Renders strict headers `### Root Cause`, `### Why This Happens`, `### Recommended Fix`, and `### Example` with dark code blocks and a `[Copy Code]` button.
  5. **Secret Redaction**: Any API key or password caught by the backend `StreamSecretBuffer` renders cleanly as `[REDACTED]`.

---

### 4.5 Adaptive Test Intelligence (`/test-intelligence`)
- **Purpose**: Coverage gap exploration, parameter constraint inspection, and synthesized edge-case candidates.

```
+----------------------------------------------------------------------------------------------------+
| ADAPTIVE TEST INTELLIGENCE                                                                         |
| Coverage Gap Evaluation & Edge-Case Input Synthesis (Zero Runtime Execution)                       |
+----------------------------------------------------------------------------------------------------+
| CONTEXT & OPERATING MODE                                                                           |
| [MODE: BASELINE_DRIVEN]  [Function: calculate_average]  [Params: numbers: list]  [Constraints: None]|
+----------------------------------------------------------------------------------------------------+
| IDENTIFIED INPUT DOMAIN COVERAGE GAPS                                                              |
| [EMPTY_COLLECTION (High Risk)]  [SINGLE_ELEMENT (Medium)]  [EXTREME_MAGNITUDE (Low)]               |
| Description: Existing baseline inputs do not test empty list [] or extreme integer boundaries.     |
+----------------------------------------------------------------------------------------------------+
| SYNTHESIZED TEST CANDIDATES (UNVERIFIED CANDIDATE INPUTS)                                          |
| Note: Generated candidates target input-domain gaps. Expected outputs are null (zero execution).   |
|                                                                                                    |
| +------------------------------------------------------------------------------------------------+ |
| | CANDIDATE #1  [VALID CANDIDATE]                                          Target Gap: EMPTY_LIST | |
| | Input Parameters:                                                                              | |
| |   numbers: []                                                                                  | |
| | Rationale: Tests behavior when collection length is 0 (evaluates ZeroDivisionError boundary).   | |
| | Expected Output: null (Unverified by reference oracle)                                         | |
| | ACTIONS: [Copy JSON Input]   [Copy STDIN Format]                             [Add to Workspace] | |
| +------------------------------------------------------------------------------------------------+ |
| | CANDIDATE #2  [ROBUSTNESS PROBE]                                    Target Gap: EXTREME_SCALE  | |
| | Input Parameters:                                                                              | |
| |   numbers: [1000000000, -1000000000]                                                          | |
| | Rationale: Evaluates numeric overflow and sign cancellation behavior.                          | |
| | Expected Output: null (Unverified by reference oracle)                                         | |
| | ACTIONS: [Copy JSON Input]   [Copy STDIN Format]                             [Add to Workspace] | |
| +------------------------------------------------------------------------------------------------+ |
+----------------------------------------------------------------------------------------------------+
```

---

### 4.6 Analysis History (`/history`)
- **Purpose**: Audit past analyses and inspect stored JSONB reports.
- **Dual-State Logic**:
  - **State A (PostgreSQL Connected)**: Renders paginated table of analysis sessions (`GET /api/v1/analyses`), with filters for project, date range, and status. Clicking a session opens the full stored JSONB report.
  - **State B (Stateless Mode / DB Unreachable)**: Displays clear, honest banner:
    *"Stateless Mode: PostgreSQL persistence is currently offline. EdgeMind analyses run entirely in-memory. Recent sessions from this browser are temporarily available below until page reload."*

---

### 4.7 Settings (`/settings`)
- **Purpose**: Verified configuration and environment diagnostic controls (zero decorative settings).
- **Sections**:
  1. **API Connection**:
     - Backend Base URL: `http://127.0.0.1:8000` (Editable, with `Test Connection` button).
     - Health Status: Response time, service name, database connection status.
  2. **AI Provider Inspector**:
     - Configured Provider: `Ollama (Local)` or `Live (OpenAI / Gemini)`.
     - Active Model: `qwen3:4b`.
     - Context Limit: `120 lines / 64 KiB`.
  3. **Editor Preferences**:
     - Tab Size: `4 spaces` (Default for Python).
     - Font Size: `13px` (Default).
     - Minimap: `Enabled` / `Disabled`.

---

## 5. Implementation-Ready Wireframes

### 5.1 Desktop Workspace Wireframe (1440px)

```
0px                  240px                                             880px                           1440px
+--------------------+-------------------------------------------------+-------------------------------+
| [E] EdgeMind       | Topbar: Workspace / snippet.py                  | [● 8000: 14ms]  [⌘K] [Run ⌘↵] |
+--------------------+-------------------------------------------------+-------------------------------+
| ANALYSIS           | CODE EDITOR PANE                                | DIAGNOSTIC FINDINGS PANE      |
| > Workspace        | Tab: snippet.py [Python 3]                      | Score: 80/100  [FAIL]  12ms   |
|   Findings     (2) | +---------------------------------------------+ | +---------------------------+ |
|   Adaptive Intel   | | 1 | def calculate_average(nums: list):      | | | [All (2)] [Errors (1)]    | |
|                    | | 2 |     total = sum(nums)                   | | +---------------------------+ |
| MANAGEMENT         | | 3 |     return total / len(nums)            | | #finding-0 ZeroDivision     | |
|   Overview         | | 4 |                                         | | Line 3: Division by zero    | |
|   History          | | 5 |                                         | | [Explain Finding 🪄]       | |
|                    | | 6 |                                         | | +-------------------------+ | |
| SYSTEM             | | 7 |                                         | | | AI Diagnosis (Streaming)| | |
|   Settings         | | 8 |                                         | | | Root Cause: len(nums)==0| | |
|                    | +---------------------------------------------+ | +-------------------------+ | |
|                    | Gutter: 64 KiB Max | UTF-8 | Tab: 4            | #finding-1 UnusedVariable   | |
+--------------------+-------------------------------------------------+-------------------------------+
| Footer Status: [Python 3.13 Static]  [Ollama: qwen3:4b]  [Memory: Stateless]   [⌘↵: Run Analysis]   |
+------------------------------------------------------------------------------------------------------+
```

### 5.2 Mobile Workspace Wireframe (375px)

```
0px                                                             375px
+-------------------------------------------------------------------+
| [≡] [E] EdgeMind                [● Online]            [⌘K Search] |
+-------------------------------------------------------------------+
| BREADCRUMB: Workspace / snippet.py                                |
+-------------------------------------------------------------------+
| TAB SWITCHER: [ Editor (Active) ]  [ Findings (2) ]  [ Test Intel]|
+-------------------------------------------------------------------+
| CODE EDITOR (Compact Mode)                                        |
| 1 | def calculate_average(nums: list):                            |
| 2 |     total = sum(nums)                                         |
| 3 |     return total / len(nums)                                  |
| 4 |                                                               |
| 5 |                                                               |
| 6 |                                                               |
| 7 |                                                               |
| 8 |                                                               |
+-------------------------------------------------------------------+
| FILE ACTIONS: [ ⇪ Upload ]  [ Clear ]              [ Python 3 ▾ ] |
+-------------------------------------------------------------------+
| FLOATING BOTTOM ACTION BAR:                                       |
| [ ▶ Run Static Analysis (⌘↵)                        Score: 80/100]|
+-------------------------------------------------------------------+
```

---

## 6. Component Inventory & Technical Specifications

| Component Name | File Path | Props / Variants | States | Accessibility & ARIA |
| :--- | :--- | :--- | :--- | :--- |
| `AppShell` | `components/layout/AppShell.tsx` | `children`, `sidebarCollapsed` | Default, Sidebar Open, Mobile Drawer | `role="region"`, `aria-label="Application"` |
| `Sidebar` | `components/layout/Sidebar.tsx` | `collapsed: boolean`, `onToggle` | Default (240px), Rail (64px), Mobile | `role="navigation"`, `aria-label="Main Navigation"` |
| `TopBar` | `components/layout/TopBar.tsx` | `breadcrumbs`, `onRunAnalysis` | Idle, Analyzing, Network Error | `role="banner"` |
| `MonacoShell` | `components/editor/MonacoShell.tsx`| `code`, `onChange`, `readOnly` | Idle, Focused, ReadOnly, Loading | `aria-label="Python Code Editor"` |
| `FindingCard` | `components/findings/FindingCard.tsx`| `finding: ReportFinding`, `onDiagnose`| Default, Expanded, Focused, Streaming | `role="article"`, `aria-expanded` |
| `DiagnosisStream` | `components/diagnosis/DiagnosisStream.tsx`| `findingId`, `streamState`, `onCancel`| Idle, Streaming, Completed, Error | `aria-live="polite"`, `aria-busy="true"` |
| `CandidateCard`| `components/testIntel/CandidateCard.tsx`| `candidate: TestCase`, `onCopy` | Default, Copied Toast, Expanded | `role="region"`, `aria-label="Test Candidate"` |
| `FilterBar` | `components/findings/FilterBar.tsx` | `query`, `counts`, `onChange` | Default, Focused, Filter Active | `role="search"`, `aria-label="Filter Findings"` |
| `SeverityBadge`| `components/common/SeverityBadge.tsx` | `severity: 'error'\|'warning'\|'info'` | Default, Small, Pill | `role="status"` |
| `ScoreBadge` | `components/common/ScoreBadge.tsx` | `score: number`, `status: string` | Pass (Green), Warn (Amber), Fail (Red)| `role="status"`, `aria-label="Analysis Score"` |
| `CommandPalette`| `components/common/CommandPalette.tsx`| `isOpen`, `onClose` | Open, Closed, Searching | `role="dialog"`, `aria-modal="true"` |

---

## 7. Interaction, Feedback & Motion System

### 7.1 Duration & Easing Scale
- **Micro-interactions** (button hover, tab indicator, dropdown item hover):
  - Duration: `120ms`
  - Easing: `cubic-bezier(0.16, 1, 0.3, 1)`
- **Macro-transitions** (sidebar toggle, modal fade-in, drawer slide):
  - Duration: `200ms`
  - Easing: `cubic-bezier(0.16, 1, 0.3, 1)`
- **Prohibited Animations**:
  - ❌ Bouncy spring physics
  - ❌ Infinite glowing card borders
  - ❌ Layout property animations (`width`, `height`, `padding`, `margin`)

### 7.2 Keyboard Navigation Standards
- `⌘↵` / `Ctrl+Enter`: Triggers static analysis in Workspace.
- `⌘K` / `Ctrl+K`: Opens Global Command Palette.
- `Esc`: Closes open modals, drawers, or cancels active AI diagnosis streaming.
- `Tab` / `Shift+Tab`: Logical sequential focus traversal through interactive elements with high-visibility focus ring (`box-shadow: 0 0 0 2px #38BDF8`).

---

## 8. Comprehensive Responsive Design Strategy

| Screen Breakpoint | Layout Behavior | Sidebar | Code Editor | Diagnostic Inspector |
| :--- | :--- | :--- | :--- | :--- |
| **375px (Mobile)** | Single-column tabbed view | Off-canvas drawer | Full width (300px min-height) | Separate tab view |
| **430px (Large Mobile)**| Single-column tabbed view | Off-canvas drawer | Full width (340px min-height) | Separate tab view |
| **768px (Tablet Portrait)**| Dual-section vertical stack | Compact rail (64px) | Full width (400px height) | Bottom full-width pane |
| **1024px (Tablet Landscape)**| Side-by-side 50/50 split | Collapsible (64px / 200px) | Left pane (50%) | Right pane (50%) |
| **1366px (Laptop)** | Side-by-side 55/45 split | Standard sidebar (240px) | Left pane (55%) | Right pane (45%) |
| **1440px (Desktop)** | Side-by-side 50/50 split | Standard sidebar (240px) | Left pane (50%) | Right pane (50%) |
| **1920px (Ultrawide)**| 3-Column Full Workbench | Standard sidebar (240px) | Left pane (45%) | Center Findings (30%), Right Intel (25%) |

---

## 9. Accessibility Standards (WCAG 2.1 AA)

1. **Color Contrast**:
   - Primary text (`#F8FAFC`) on Level 0 canvas (`#090A0F`): Contrast ratio **18.2:1** (Exceeds AAA).
   - Secondary text (`#CBD5E1`) on Level 2 workspace (`#10121C`): Contrast ratio **11.4:1** (Exceeds AAA).
   - Muted text (`#94A3B8`) on Level 3 card (`#141624`): Contrast ratio **6.2:1** (Exceeds AA standard of 4.5:1).
2. **Keyboard Navigation & Focus Management**:
   - All interactive controls feature `:focus-visible` outline: `2px solid #38BDF8`, offset `2px`.
   - Modals trap focus; focus returns to trigger upon dismissal.
3. **Screen Readers**:
   - Live AI streaming container declared with `aria-live="polite"` and `aria-busy="true"`.
   - Monaco Editor annotated with `aria-label="Python Code Editor"`.
4. **Touch Targets**:
   - All mobile buttons, tabs, and icon hitboxes maintain a minimum dimension of `44px x 44px`.

---

## 10. Frontend Performance Standards

1. **Initial Bundle Target**: $< 220\text{ KiB}$ gzip (excluding Monaco Editor).
2. **Monaco Dynamic Splitting**: Monaco Editor is strictly loaded via `React.lazy()` with an inline skeleton loader.
3. **SSE Stream Buffer**: Tokens arriving from `POST /api/v1/diagnose/stream` are batched using `requestAnimationFrame` to limit DOM reflows to at most 60 updates per second.
4. **Virtualization**: Findings lists and Test Intelligence candidate lists exceeding 40 items utilize `@tanstack/react-virtual` to ensure smooth 60 FPS scrolling.
5. **Cumulative Layout Shift (CLS)**: Zero CLS. Button dimensions remain constant during loading states by substituting icon SVGs with equal-sized spinners.

---

## 11. API and Data Accuracy Mapping

Every dashboard component maps directly to existing EdgeMind backend endpoints:

| Route / View | Component | Backend Endpoint | Request / Payload | Consumed Fields | Fallback / Offline Behavior |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **All Routes** | `SystemHealthPill` | `GET /health` | None | `status`, `service`, `database` | Amber pill if degraded, Red if unreachable |
| **Overview** | `ActiveMetricStrip` | `POST /api/v1/analyze` | `AnalyzeCodeRequest` | `score`, `overall_status`, `summary`, `total_errors` | Displays empty placeholder if no analysis run |
| **Overview** | `RecentActivityTable`| `GET /api/v1/analyses` | Pagination query | `id`, `created_at`, `analysis_status`, `duration_ms` | Falls back to in-memory browser storage if DB offline |
| **Workspace** | `MonacoShell` | `POST /api/v1/analyze` | `code`, `filename` | `results`, `errors`, `warnings`, `score` | In-editor squiggles & line markers |
| **Findings** | `FindingCard` | `POST /api/v1/analyze` | None (from result) | `type`, `line`, `message`, `why`, `fix`, `concept` | Renders clean empty state when 0 issues found |
| **Findings** | `DiagnosisStream` | `POST /api/v1/diagnose/stream`| `DiagnoseFindingRequest` | SSE: `diagnosis_started`, `response_chunk`, `completed` | Displays actionable retry button on timeout/error |
| **Test Intel** | `CandidateCard` | `POST /api/v1/edgemind/analyze`| `EdgeMindAnalyzeRequest`| `test_intelligence.generated_candidates` | Explicitly marked: `expected_output: null (Unverified)` |
| **History** | `HistoryTable` | `GET /api/v1/analyses/report` | Query filters | `session_id`, `project_name`, `problem_slug`, `created_at`| Displays informative banner if DB is not configured |
| **Settings** | `AIProviderCard` | `GET /health` & config | None | `agent_provider`, `model`, `max_source_size` | Read-only verified system telemetry |

---

## 12. Visual QA Checklist

Before merging any Phase 6 implementation PR, verify the following checklist:

- [ ] **Luminance & Contrast**:
  - Canvas is `#090A0F`. No pure `#000000` or raw unstyled white backgrounds.
  - Text contrast meets minimum 4.5:1 on all surfaces.
- [ ] **Typography**:
  - Inter Variable for UI text; JetBrains Mono / Geist Mono for code, metrics, and line numbers.
  - Tabular figures (`tabular-nums`) enabled on all score badges, line numbers, and duration timers.
  - Maximum font weight is `600` (semibold); zero `700`+ bold weights in UI chrome.
- [ ] **No AI Gimmicks**:
  - Zero glowing border animations. Zero mesh gradients. Zero emojis (100% Lucide SVG icons).
  - Zero fabricated trend metrics or unbacked percentage deltas.
- [ ] **Layout & Responsiveness**:
  - Zero whole-page horizontal scrolling on 375px, 430px, 768px, 1024px, 1366px, 1440px, and 1920px.
  - Monaco editor properly adapts or switches to tabbed workbench on mobile.
- [ ] **Interaction & Feedback**:
  - Visible focus rings (`box-shadow: 0 0 0 2px #38BDF8`) on all keyboard-focused elements.
  - Hover states apply within 120ms without layout jitter.
- [ ] **Data Integrity**:
  - Generated test candidates are clearly labeled as candidates with null expected outputs.
  - History view honestly discloses whether PostgreSQL persistence is active or in-memory mode is active.
