# Sonic Local Assistant — Product Requirements

**Status:** Draft v1  
**Date:** 28 September 2026  
**Platform:** Windows desktop (this machine is Windows 10/11)  
**Orchestration:** LangChain + LangGraph  
**Decision model:** [Laya](https://huggingface.co/convaiinnovations/laya) (Apache 2.0), ONNX in the background, GPU when the PC has one and CPU otherwise  
**Tool caller:** [Needle 3](https://huggingface.co/Cactus-Compute/needle3) (Apache 2.0)  
**Wake word:** the existing Sonic model, resident in the background  
**Cloud writer:** any OpenAI-compatible chat endpoint, used only when the turn needs generated language  
**Browser loop:** [jev-ultrafast](https://github.com/browser-use/jev-ultrafast) action space, with the remote TypeSafe call replaced by local Laya

---

## 1. Summary

Sonic is a local PC assistant. It stays resident, listens for the Sonic wake word, and turns one spoken or typed request into either a PC action, a browser action, a Google Workspace call, or a written answer.

Four models share that job, and they are not interchangeable:

| Model | Job | What it must never do |
|---|---|---|
| **Sonic** | Wake word. Opens one turn, then goes back to listening | Transcribe, route, or call tools |
| **Laya** | One forward pass over typed questions: which route, which risk level, which on-screen control | Generate prose, invent selectors, emit coordinates |
| **Needle 3** | Fill tool arguments from the user’s words, with a grammar so the JSON always parses, plus a confidence score | Guess a tool when none fits; drive the mouse from free text |
| **Cloud LLM** | Write the answer, or compose text that must be typed, when the utterance is a general question or needs reasoning | Become the click policy; run on a turn Laya marked as a local action |

The product problem this PRD exists to solve: **after Laya chooses a route, the same user request must be handed to exactly one executor, with the arguments that executor can safely run.** A cloud model that “also” emits a click, or a local model that answers a question it was only asked to route, is a failed turn.

V1 is a step-at-a-time assistant (continuous mode). Autonomous multi-step runs come after the single-step path is reliable.

---

## 2. Problem

Today there is no single place that:

1. Hears a request while the rest of the PC is in use.
2. Decides, locally and quickly, whether the request is a PC action, a desktop click, a browser goal, a Google call, a web lookup, or a general question that needs a written answer.
3. Sends that decision to the model that can actually carry it out.
4. Executes only against something the computer just observed (an accessibility node, a browser element index, a declared tool), and checks that target again before input.

Without that handoff, “use two models” becomes two models both trying to act. The routing contract in section 8 is the requirement that prevents that.

---

## 3. What v1 is

A background Windows process that:

- Listens with the existing Sonic wake-word model.
- Transcribes the utterance after Sonic fires.
- Asks Laya, in one pass, for route, risk, and whether a tool is required.
- If the route is an action, asks Needle 3 for tool calls and runs them only above a confidence threshold. That path stays on the PC.
- If the route is a general question or needs composed language, calls one cloud OpenAI-compatible model. There is no local writer.
- Can open an app, focus a window, type into the focused field, and click a control chosen from a fresh accessibility snapshot.
- Can run one web search.
- Can sign into Google with a desktop OAuth client and read calendar events.
- Supports **continuous mode**: one mutating action, then back to listening.
- Speaks or shows a short result.

## 4. Out of scope for v1

- Booking, purchasing, sending email, or deleting files.
- Screenshot-driven clicking. The decision path uses accessibility text and roles. Screenshots are for the human inspector only.
- Full Jarvis personality, long-term memory, or multi-user accounts.
- Shadow DOM, cross-origin iframes, canvas apps, file uploads, and arbitrary keyboard widgets in the browser (same boundary as jev-ultrafast’s MVP).
- A local generative LLM. Actions stay on Laya and Needle. Written answers go to the cloud model.
- Fine-tuning Laya or Needle on day one. V1 uses published weights and a small labeled eval set. Fine-tuning is a later phase if the eval misses the bar.
- Replacing Chrome’s login. The browser agent uses the existing Chrome profile through Browser Harness.

---

## 5. Assumptions

These are explicit so they can be corrected before Phase 0 ends.

1. **Sonic** is the wake-word model already on this PC. The listener loads that model and no other wake-word engine. Weights path is configuration (`SONIC_WAKE_MODEL`). Sonic does not transcribe and does not route.
2. The cloud model is the only writer. It is configured as base URL + API key + model name. OpenAI is the default vendor. Any other OpenAI-compatible host is a config change. A turn that Laya routes to a tool does not call it.
3. The assistant runs on Windows and uses UI Automation for on-screen controls.
4. Google access uses an OAuth **desktop** client (client id + client secret) created in Google Cloud, with incremental scopes. Secrets live in Windows Credential Manager, not in the repo.
5. Laya’s useful checkpoint for agent-style decisions is `laya-typed-decisions`, not the base English checkpoint. Published numbers: on the typed-decisions benchmark the fine-tuned checkpoint scores **0.766** accuracy; the base English and multilingual checkpoints score **0.362** and **0.352**, below the majority-class baseline of 0.461. Those figures are on that benchmark’s own distribution. Sonic must measure its own utterances before any route is trusted. Source: [Laya model card / package notes](https://pypi.org/project/laya/).
6. A single Laya `choice` question stays at or under **20 options**. Above that, option text shares a fixed token budget and accuracy collapses (Banking77: Laya 0.425 vs Jev 0.870 at 70+ labels). Desktop and browser targets are shortlisted in code first. `predict_shortlist(..., k=20)` is the supported escape hatch.
7. Local inference uses the GPU when one is available and the model’s runtime can run on it. Otherwise that model runs on CPU. The assistant still starts. See section 11.1.

---

## 6. Research findings that constrain the design

### 6.1 Laya

[Laya](https://huggingface.co/convaiinnovations/laya) (Convai Innovations, Apache 2.0, `pip install laya`, Python ≥ 3.10) is a non-autoregressive decision model. Input is a state plus typed questions. Output is labels and probabilities. It does not generate text, so there is nothing to parse.

Question types:

| Type | Returns | Use in Sonic |
|---|---|---|
| `choice` | Winning label, per-option probabilities, confidence | Route, which app family, which control index |
| `score` | Expected level on an ordered rubric | Risk: observe / confirm / refuse |
| `noul` | P(true) from 0 to 1 | Use sparingly. On the English checkpoint, `noul` can follow the words “true/false” instead of the state. Prefer a two-way `choice` with semantic labels until we calibrate `noul` on our data |

Checkpoints:

| Checkpoint | Size | Context | Role in Sonic |
|---|---|---|---|
| `laya` | 421M, ModernBERT-large | 512 | English fallback only |
| `laya-multilingual` | 322M, mmBERT-base | 1024 (encoder up to 8k) | Non-English utterances. The built-in `Router` picks this from script/language before the forward pass |
| `laya-typed-decisions` | 421M | 1024 | **Default for route and control questions** |

Runtime:

- One question is about **33–40 ms** on a T4; CPU is roughly **200–500 ms**. Batching is faster per question.
- `pip install "laya[langchain]"` provides `LayaRouter` for LangGraph conditional edges, with a confidence threshold and a fallback branch. Docs: [LangChain and LangGraph integration](https://nandhakishorm.github.io/laya/langchain/).
- `pip install "laya[onnx]"` provides `ONNXAgent` for the background process so the listener does not need a full PyTorch server on every wake.
- `Router(preload=True)` keeps checkpoints hot. Language detection itself is sub-millisecond. A cold load is seconds; do it at process start.
- Arithmetic, counting, date math, and “which item is the third” stay in Python. Laya is not the place for those.
- Confidence is over-confident until a temperature is fit on held-out Sonic data. Do not ship a numeric threshold taken from the model card.

Background fit: the Sonic wake-word model stays resident and opens a turn. Laya ONNX is the decision brain loaded beside it. They are separate models (section 11).

### 6.2 Needle 3

[Needle 3](https://huggingface.co/Cactus-Compute/needle3) (Cactus Compute, Apache 2.0) is an on-device model for three jobs: tool calls, structured extraction, and embeddings. The shipped file is about **8–29 MB** depending on layer depth (2 to 20 layers). The full model is 121M parameters with most of them in an n-gram memory, so the math is closer to a 50M model. Windows x64 ships as `needle.exe` plus a sub-1 MB engine (`windows-x86_64`). `pip install cactus-needle` fetches the engine once into a local cache. Inference does not call the network.

Behavior Sonic will rely on:

- Declare tools as Python functions, Pydantic models, or JSON schema. A byte-level grammar compiled from those schemas constrains every token. The call parses or it does not return.
- Two requests in one sentence become two calls in order.
- If no tool covers the request, the result is an **empty list**, not a guessed call.
- Every response includes `function_calls`, `reasoning`, and `confidence`.
- `confidence` is the minimum of a calibrated head (over the prompt and the finished call) and the decode probability. The engine withholds calls under **0.1**. Above that, Sonic sets the threshold. Wrong calls should sit low, so raising the threshold trades extra confirmations for fewer wrong executions.
- Confidence is calibrated for the **base** weights. Tuned `.cact` files report `confidence: null`. V1 uses base weights so the gate exists.
- **Five or fewer tools** are all visible. **More than five** triggers retrieval: only the top five embedding matches enter the prompt, and the grammar is rebuilt so the other tools are unreachable. Persist the index with `tool_index_path`.
- `needle.extract(text, schema)` is the path for “pull the city and date out of this sentence” without a side effect.
- `needle_embed` can rank a list of control names before Laya sees them.

Tool-design rules from Cactus, applied here: one tool per action, names a person would say, formats in the description, hard constraints in the schema. A light action (open Notepad) can act around 0.5. A send, delete, or purchase stays confirm-only even at 0.9.

### 6.3 jev-ultrafast

[browser-use/jev-ultrafast](https://github.com/browser-use/jev-ultrafast) (MIT) is a browser agent whose policy is an indexed table, not generated code.

What it does well, and what Sonic copies:

- Each observation builds a numbered table of visible controls: role, accessible name, current value.
- Operations are a closed set: `CLICK`, `TYPE_TEXT`, `SELECT`, `SCROLL_UP`, `SCROLL_DOWN`, `WAIT`, `DONE`, `BLOCKED`. Only operations the page currently supports are offered.
- Operation and target are decided together. Targets are speculative: if the operation is `CLICK`, only `click_target` executes. One decision cycle, one model request.
- The model returns an **index**. The executor resolves that index to a node it already holds. Output never becomes a CSS selector, a coordinate, shell, or JavaScript.
- `TYPE_TEXT` is the only step that needs a writer model. The writer must return a small JSON object `{"text": "..."}` before anything is typed.
- Before the click, the executor checks that the document is still the one that was read, that the node is still there, and that it is not covered.
- The default loop does not send screenshots to the model. The local inspector at `http://127.0.0.1:8766` can show them to a person.
- A `DONE` from the model is not success. A separate check confirms the goal (the flights example checks route, date, and that options are visible).

What it does not do, so Sonic will not promise it:

- Shadow roots, iframes, canvas, file uploads, popup tabs, nested scrolling, and custom keyboard widgets.
- Full accessible-name computation. It reads common HTML and ARIA.
- Site-specific scripts. The policy is the goal plus the live table.

Why it is not dropped in unchanged:

- The decision call is **TypeSafe’s hosted Jev** (`TYPESAFE_API_KEY`). The text writer is a second hosted model (`TEXT_MODEL_API_KEY`, example model `inception/mercury-2.5` via OpenRouter).
- Jev is strong when a page has dozens of controls (up to 255 options). Laya is not, at default settings.
- Published speed (one Google Flights task, three repeats): median about **7.1 s**, browser protocol calls reduced from about 1,092 to 101 versus their previous loop. That is one task on one profile, not a general reliability number.

Sonic’s browser agent keeps `snapshot.js`, `browser.py`, and the executor checks, and replaces `model.py`’s TypeSafe request with local Laya questions after a shortlist. A community prototype of that idea already exists as `laya-onnx-ultrafast` ([gdelatournelle/laya-onnx](https://huggingface.co/gdelatournelle/laya-onnx)); Phase 5 starts by reading that loop before writing a second one.

There is also a purpose split inside “browser”:

| Purpose | Mechanism | Model |
|---|---|---|
| Look up a fact | `web_search` tool, HTTP, no page control | Needle fills the query; a fixed template speaks the top snippet |
| Operate a logged-in site | jev-style element table in the user’s Chrome | Laya picks the index; Needle copies a value from the goal into the field. The cloud model writes the field only when the text has to be composed |
| Read a public page | Fetch and extract | Needle `extract` on the main text, no clicks |

Most “what’s the weather / who won” requests should never open the browser agent.

### 6.4 How a turn is handed off

```
Sonic wake word
        │
        ▼
speech-to-text
        │
        ▼
   Laya (one pass)          route, risk, needs_tool
        │
        ├── desktop / browser / google / search ──► Needle 3 fills calls
        │                                              │
        │                                              ├─ confidence ≥ act ──► executor
        │                                              ├─ confirm band ──► ask, then executor
        │                                              ├─ below band or [] ──► one cloud plan
        │                                              │                         or ask the user
        │                                              └─ executor re-checks the live target
        │
        └── general question / composed language ──► cloud chat model
```

The cloud model returns text. It does not return clicks. If it is asked to plan because Needle abstained, that plan is submitted to Laya and Needle again. That second pass is what “transfer the action to the particular model” means. A local action and a cloud answer never both execute on the same turn.

---

## 7. Users and jobs

One user, on their own Windows PC.

| Job | Example | Route |
|---|---|---|
| Launch and focus | “Open Spotify” | Needle `open_app` |
| On-screen action | “Click the Save button” | Snapshot, shortlist, Laya index, `click_control` |
| Dictate | “Type good morning in this box” | Needle `type_text` into the focused editable control |
| Fact | “What’s the time in Tokyo?” | `web_search`, then a template speaks the top snippet |
| Arithmetic | “What’s 15% of 80?” | Python calculator. No model writes the number |
| General question | “Compare these two error logs and tell me what to try” | Cloud writer |
| Calendar | “What’s on my calendar tomorrow?” | Google read tool |
| Web task | “Find one-way flights from Zurich to London on 20 September” | Browser subgraph, then an independent check |

---

## 8. Routing contract

This is the functional requirement behind “based on the model routing, the action should be transferred to the particular model.”

### 8.1 One state, one forward pass

After speech-to-text, LangGraph calls Laya with the utterance, a short description of the foreground window, and the names of available tool groups. Questions in that pass:

| Question | Type | Options |
|---|---|---|
| `route` | choice | `desktop`, `browser`, `web_search`, `google`, `cloud_answer`, `clarify` |
| `risk` | score | `observe`, `confirm`, `refuse` |
| `needs_tool` | choice | `tool`, `prose` |
| `complexity` | score | `single_step`, `multi_step`, `open_reasoning` |

Option descriptions are semantic (“open or click something already on this computer”), not yes/no words.

Checkpoint: `laya-typed-decisions` for English. `Router` may send a non-English utterance to `laya-multilingual`, then the same questions run there. If multilingual confidence is below the calibrated threshold, the turn goes to `clarify` or `cloud_answer` rather than a guessed route.

### 8.2 Transfer rules

A route is valid only if the next node is the one in this table. The graph has no edge that skips the table.

| `route` | Next node | Model that runs | Allowed output |
|---|---|---|---|
| `desktop` | `needle_desktop` | Needle, desktop tool group | Tool calls whose arguments match the schema |
| `browser` | `browser_graph` | Laya on the element table; writer only for `TYPE_TEXT` | An operation plus an index that exists in the current table |
| `web_search` | `needle_search` | Needle | `web_search.query` |
| `google` | `needle_google` | Needle, Google tool group | A read call. Writes are refused until a later phase |
| `cloud_answer` | `cloud_chat` | Cloud chat model | Assistant text, or a plan object that is fed back into section 8.1 |
| `clarify` | `ask_user` | None | One spoken question |

Overrides, applied in order, after Laya returns:

1. `risk = refuse` ends the turn. Examples to seed the rubric: purchases, password changes, sending mail, deleting, disabling security.
2. `needs_tool = prose` is rewritten to `cloud_answer`. It cannot enter Needle.
3. `needs_tool = tool` cannot enter the cloud writer as the final step. The cloud model may still be asked once for a plan when Needle returns nothing, and that plan comes back through this table.
4. Arithmetic and date math are intercepted in Python before Laya, when the utterance matches the calculator. Laya never owns those.
5. Needle `function_calls: []` does not fall through into a click. It becomes `clarify`, or one cloud tool-calling attempt if `complexity` is not `single_step`.
6. Needle confidence below the act threshold does not execute. Confirm band asks the user. Below the confirm band escalates once to the cloud tool-caller, then asks the user if that also fails.
7. A cloud plan that names a click still re-enters the desktop or browser node. The cloud model’s words are not executed.

### 8.3 Confidence defaults (to be replaced by the Phase 0 eval)

Starting gates, not promises:

| Gate | Starting value | Meaning |
|---|---|---|
| Laya route act | 0.75 | Below this, `clarify` |
| Needle act | 0.55 for `open_app`, `web_search`, calendar read | Execute |
| Needle confirm | 0.35–0.55 | Speak the intended action and wait |
| Needle withhold | engine floor 0.1, plus anything under 0.35 | Do not execute |
| Click and type | confirm in continuous mode until the desktop eval passes | Then act at ≥ 0.70 |
| Send, delete, pay, OAuth scope upgrade | always confirm | No threshold removes this |

Temperature scaling for Laya is fit in Phase 0 on a 100-example set before these numbers are treated as real.

### 8.4 What each model sees

| Model | Context it receives | Context it does not receive |
|---|---|---|
| Laya | Utterance, foreground window title, tool-group names, and for clicks the shortlist of controls (≤ 20) | Full screen image, raw UIA tree, secrets, full page HTML |
| Sonic | Microphone audio, until the wake word fires | Utterance text, tools, screen contents |
| Needle | Utterance, tool schemas for the routed group, a one-line system fact (“foreground: Notepad”) | Other groups’ tools when retrieval can hide them; OAuth tokens |
| Cloud | Utterance, dialogue, and only the fields required for the question | Accessibility dumps and browser tables, unless the user asked about a specific copied error |

---

## 9. Modes

### 9.1 Continuous mode (v1 default)

The background listener is always on. The Sonic wake word opens one turn.

1. Transcribe.
2. Route and, if needed, run **one** mutating tool call or one answer.
3. Speak the result.
4. Return to wake-word listening.

“Click Save, then type the title” is two turns. The user can keep talking; each wake is a new turn. This matches jev’s “Choose next” inspector: the policy can see the page, and a person lets one action through.

State that survives between turns: conversation buffer (last 10 turns), Google token, last snapshot id (invalidated on any foreground change).

### 9.2 Autonomous mode (later phase)

The user states a goal. The graph loops:

`observe → Laya operation/target → execute → verify freshness → repeat`

Stop when:

- Laya returns `DONE` **and** a deterministic checker agrees, or
- Laya returns `BLOCKED` or `clarify`, or
- step count hits 8 (desktop) or 12 (browser), or
- a confirm-gated tool appears (the run pauses and speaks the proposed action).

Autonomous mode is off until continuous mode’s click accuracy clears the Phase 2 bar. The same nodes are used; only the loop edge changes.

---

## 10. System architecture

```
┌─────────────────────────────────────────────────────────┐
│  Background process (starts with Windows)               │
│                                                         │
│  Sonic wake word  →  STT  →  LangGraph turn           │
│                                      │                  │
│                         Laya ONNXAgent (resident)       │
│                                      │                  │
│                 ┌────────────────────┼────────────┐     │
│                 ▼                    ▼            ▼     │
│              Needle               Cloud        Browser │
│              tools                OpenAI       subgraph│
│                 │                    │                  │
│                 ▼                    │                  │
│        Windows UI Automation         │                  │
│        open / focus / type / click   │                  │
│                                      ▼                  │
│                            Chrome + Harness             │
│                            indexed elements             │
└─────────────────────────────────────────────────────────┘
```

LangGraph is the only orchestrator. Laya is a node and a conditional edge (`LayaRouter`), not a second agent framework. Needle is a tool node. The cloud model is one chat node. There is no local chat model.

Suggested packages:

- `sonic/graph/` — state, nodes, edges
- `sonic/models/` — Laya ONNX session, Needle agent, cloud client
- `sonic/desktop/` — UIA snapshot, shortlist, executor
- `sonic/browser/` — vendored or imported jev snapshot + executor, local `choose()`
- `sonic/google/` — OAuth and thin API wrappers
- `sonic/voice/` — Sonic wake word, VAD, STT, TTS
- `sonic/eval/` — labeled utterances and UI fixtures

Graph state (minimum):

`utterance, history, route, risk, complexity, tool_calls, confidence, snapshot_id, observation, result_text, error, mode`

---

## 11. Voice and the ONNX background

The listener and the decision model stay separate:

| Workload | Model | When it runs |
|---|---|---|
| Wake word | **Sonic**, the model already trained for this assistant | Always, while listening is enabled |
| Decisions | Laya `ONNXAgent` | Loaded at startup, called once per turn |
| Transcription | A local speech-to-text model (faster-whisper or an ONNX Whisper build) | After Sonic fires, until end of speech |
| Speech out | A local TTS model | After the turn, one short sentence |

Sonic’s only output is “wake” or “not wake.” On wake, STT captures the rest of the utterance and the graph starts. Sonic does not see tool schemas, the screen, or the cloud key.

The wake-word process does not load Needle or Chrome. Those start on the first turn that needs them, then stay warm for 10 minutes.

Push-to-talk is a required fallback (a global hotkey) so development does not depend on Sonic firing. The hotkey skips Sonic and starts STT directly.

V1 voice is English. Multilingual STT can land with `laya-multilingual` routing once English turns are stable.

### 11.1 GPU when present, CPU otherwise

Default is `SONIC_DEVICE=auto`. At startup the process probes once and records the choice in the log. A missing or failed GPU does not stop the assistant.

Provider order on Windows:

1. **CUDA**, when an NVIDIA GPU and the ONNX Runtime CUDA provider both load.
2. **DirectML**, when a GPU is present and CUDA is not usable (AMD, Intel, or NVIDIA without the CUDA build).
3. **CPU**, when no GPU provider loads.

Each local ONNX session follows that order on its own: Sonic (if the wake-word file is ONNX), Laya, speech-to-text, and TTS. One model falling back to CPU leaves the others on the GPU.

Needle 3 stays on the Cactus engine shipped for Windows. That engine is CPU. It is small enough that the GPU rule does not apply to it.

`SONIC_DEVICE=cpu` forces every ONNX session onto CPU, which is the test for the fallback. `SONIC_DEVICE=gpu` refuses to start only if the user asked for GPU and neither CUDA nor DirectML loads. `auto` never refuses.

Published Laya timing stays the expectation band: about 33–40 ms per question on a GPU, about 200–500 ms on CPU. Phase latency bars are measured on `auto` for this PC, and the log line for that run names the provider.

---

## 12. Desktop tools (v1)

Needle’s desktop group. The graph takes the snapshot **before** Needle is asked to click, and Needle may only return an id from that snapshot.

| Tool | Arguments | Behavior |
|---|---|---|
| `open_app` | `name: str` | Resolve against an allowlist (Start menu / App Paths). Refuse names that are not installed apps. No raw shell from the model |
| `focus_window` | `title_query: str` | Bring a top-level window to the foreground if the title matches one candidate. If several match, clarify |
| `type_text` | `text: str` | Type into the focused editable UIA control. If focus is not editable, clarify |
| `press_keys` | `keys: list[str]` | A small allowlist: Enter, Escape, Tab, arrows, common shortcuts such as Ctrl+S. No arbitrary command strings |
| `click_control` | `control_id: str` | Id from the current snapshot only. Re-query the element, reject if disabled, off-screen, or occluded |
| `web_search` | `query: str` | One HTTP search, return titles and snippets. No browser |

Snapshot contents, per control, text only:

`id, control_type, name, value, enabled, focused, window_title`

Filter before any model sees the list:

- Foreground window only.
- Enabled, on-screen, with a non-empty name.
- Prefer buttons, links, menu items, edit fields, tabs, checkboxes, radio buttons.
- Rank the rest with Needle embeddings against the utterance (`predict_shortlist` or Needle embed), keep **≤ 20**, then Laya `choice` over those ids.

Laya questions on a snapshot:

- `operation`: `CLICK`, `TYPE_TEXT`, `PRESS_KEYS`, `DONE`, `BLOCKED` (only those the snapshot supports).
- `click_target`: the shortlist, asked speculatively.
- `type_target`: editable controls only, asked speculatively.

The executor uses the target head that matches `operation`, same rule as jev-ultrafast.

Click execution uses UI Automation’s invoke or a click on the element’s current bounding rectangle after the occlusion check. The model never supplies x,y.

### Allowlist for `open_app`

Ship with a user-editable list: browser, file explorer, notepad, terminal, and the apps the user adds in settings. An unknown name asks once: “I don’t have an allowlist entry for X. Add it?”

---

## 13. Browser agent

### 13.1 Requirement

Given a URL (or the current tab) and a natural-language goal, operate the page through the indexed action space until the goal is verified or the run stops.

### 13.2 Build approach

1. Spike `laya-onnx-ultrafast` on one local HTML fixture. Record whether operation and target heads match the jev contract.
2. If the spike is close, wrap it. If it is not, copy the jev-ultrafast split:
   - `snapshot.js` for the atomic DOM read and node identity.
   - `browser.py` for Chrome via Browser Harness, geometry, and execution.
   - Replace `model.choose()` so it calls local Laya instead of TypeSafe.
3. Shortlist elements to ≤ 20 with embeddings before the Laya `choice`. Pages with huge tables scroll or search first; they are not stuffed into one question.
4. `TYPE_TEXT` text comes from Needle `extract` when the value is a slot in the user goal (“London”, “20 September 2026”). If the words to type are not in the goal and have to be composed, the cloud model writes the JSON `{"text": "..."}` and nothing else on that step. The same reuse rule as jev: keep a generated string across a stale-page retry only when the writer input is unchanged.
5. `DONE` runs a goal checker written in code for v1 scenarios (section 17). A model saying done is not the checker.

### 13.3 Chrome

- `uv run browser-harness --doctor` is the setup check, as in the jev README.
- The agent attaches to the user’s Chrome with remote debugging, so existing logins can be reused.
- Focus emulation can keep a background tab rendering; Sonic will not switch the user’s visible tab unless the goal says to.
- The inspector (numbered elements, probabilities, executed action) is a dev window, not the product UI.

### 13.4 Limits to document in the product, not just here

If the page is a canvas, a closed shadow tree, or an iframe the snapshot cannot see, the run returns `BLOCKED` and says so. It does not fall back to screenshot coordinates in v1.

---

## 14. Google

### 14.1 Setup

1. A Google Cloud project owned by the user.
2. OAuth consent screen. External/testing is enough for a single-user desktop app.
3. Client type: Desktop. Client id and client secret are stored in Windows Credential Manager.
4. Installed-app flow with PKCE. The redirect is a loopback port.
5. Scopes are requested when first needed, not all at install.

### 14.2 Phase split

| Phase | Scope | Tools |
|---|---|---|
| First Google slice | `openid`, `email`, `calendar.readonly` | `calendar_list_events(time_min, time_max)` |
| Later read | `gmail.readonly`, `drive.readonly` | list and fetch, Needle extraction on the body |
| Later write | `calendar.events`, `gmail.send` | Always `risk = confirm`. Draft first, send only after a spoken yes |

Tokens refresh locally. A failed refresh speaks “Google needs you to sign in again” and opens the browser OAuth flow. It does not retry with a cloud model.

Google tool schemas are a separate Needle group from desktop tools, so a “what’s on tomorrow” utterance cannot retrieve `click_control`.

---

## 15. Safety

- Destructive and outbound actions are confirm-only regardless of confidence and regardless of mode.
- `open_app` cannot launch arbitrary executables from model text.
- Click ids that are not in the current snapshot are dropped.
- Browser and desktop executors re-read the target after the decision and abort if the tree changed.
- Cloud requests are opt-in per turn via the route. A desktop click does not upload the accessibility tree.
- Logs store route, tool name, confidence, and latency. They do not store OAuth tokens, client secrets, or typed passwords. A password field (UIA is-password) is never read back into the model context.
- The Sonic wake word can be disabled with the hotkey. Continuous listening is a user setting, default off until the user turns it on.

---

## 16. Phases

Each phase has an exit bar. The next phase does not start by widening tools until the current bar is met. Dates are relative to the start of that phase.

### Phase 0 — Contracts and a labeled set

**Goal:** Prove the routing handoff on text, with no mouse and no microphone.

**Build:**

- Repo layout, LangGraph skeleton, config for the cloud base URL and the Sonic wake-word weights path.
- Laya `ONNXAgent` loaded on `laya-typed-decisions`.
- Needle desktop schemas compiled, not executed (dry run).
- 100 labeled utterances covering the six routes, including “this is not a tool” and “this should be refused.”
- A script that prints route, confidence, and which node would have run.

**Exit:**

- Route accuracy ≥ 85% on the 100, measured as exact match on `route`.
- Zero cases where a `refuse` utterance is assigned an executable tool.
- A written note of the fitted Laya temperature and the Needle threshold that hits that accuracy.
- The cloud endpoint answers one canned prompt through the graph. A tool-routed utterance from the same set does not call it.
- Startup on this PC logs one provider per ONNX model. With `SONIC_DEVICE=cpu`, the same canned route still returns an answer.

**Size:** about one week.

### Phase 1 — Continuous listener

**Goal:** Sonic wake word → text → route → spoken one-line result. Cloud answers, plus `open_app` on the allowlist.

**Build:**

- Background process loads the existing Sonic wake-word weights. Hotkey fallback, STT, TTS.
- Device probe from section 11.1 runs before the first turn. The tray tooltip shows `gpu` or `cpu`.
- Laya resident. Needle executes `open_app` and `focus_window` only.
- Continuous mode: one action, then listen again.
- Tray icon: listening / thinking / idle, and a kill switch.

**Exit:**

- From a cold wake, `open_app` starts in under 3 seconds on this PC, excluding the user’s speaking time. Cloud answers are under 8 seconds on a normal connection.
- `open_app` succeeds for every allowlisted app in a 10-app test.
- An unknown app name does not spawn a process.
- The process stays under a documented idle CPU budget (target: under 5% of one core while Sonic is waiting).

**Size:** about one to two weeks.

### Phase 2 — Desktop hands

**Goal:** Click and type from the accessibility tree, one action per turn.

**Build:**

- UIA snapshot, shortlist to ≤ 20, Laya operation + target, executor with occlusion and freshness checks.
- `type_text` and `press_keys`.
- A fixture pack: Notepad, Explorer, one Win32 dialog, one Settings page. Each fixture has the expected control id for 10 commands.
- Dev overlay that lists the shortlist and the chosen id. No screenshot in the decision path.

**Exit:**

- ≥ 80% exact-control accuracy on the fixture pack (40 commands).
- 0 clicks on a control that was not in the snapshot.
- A covered or disabled control is skipped and the user is told.
- Median time from end of speech to click under 1.5 seconds when Laya and Needle are warm.

**Size:** about two weeks.

### Phase 3 — Model transfer under failure

**Goal:** The escalation path is real, not a diagram.

**Build:**

- Needle empty-call and low-confidence branches.
- One cloud tool-calling attempt that returns a plan, then re-enters Laya/Needle.
- Cloud used for `cloud_answer` and for composed `TYPE_TEXT` only.
- Logging of which model actually ran.

**Exit:**

- On a 30-example failure set (ambiguous, multi-intent, missing slots), every example ends in exactly one of: executed local tool, cloud answer, or a clarify question. None end in two models both acting.
- A forced Needle failure (tool removed) produces a clarify or a cloud answer, and no click.
- Traces show a single `model_used` field per turn.

**Size:** about one week.

### Phase 4 — Google read

**Goal:** One account, calendar read, confirm-free because it does not mutate.

**Build:**

- Desktop OAuth with PKCE, credential storage, refresh.
- `calendar_list_events`.
- Needle group isolated from desktop tools.
- Spoken line is a template over the events Needle returned (“3 events tomorrow, first is Standup at 9”). The cloud model is not on this path.

**Exit:**

- Sign-in once, then “what’s on tomorrow” returns the right events against a calendar fixture.
- Revoking the token in Google produces the re-auth prompt, not a crash or a cloud retry with the old secret.
- Client secret is absent from the repo and from logs.

**Size:** about one week.

### Phase 5 — Browser, local policy

**Goal:** One verified web goal on the jev action space without a TypeSafe key.

**Build:**

- Spike `laya-onnx-ultrafast`. Then either adopt it or rewire jev-ultrafast’s `choose()` to Laya.
- Shortlist, speculative target heads, JSON text helper, freshness and occlusion checks.
- Independent checker for one goal. The flights-style goal is the reference scenario; a local HTML fixture is the CI scenario.
- `web_search` remains the path for simple lookups so the browser is not opened for them.

**Exit:**

- The local HTML fixture task passes 5/5 with no TypeSafe calls (assert by network log).
- One live task (the flights goal or a simpler public page if flights markup has moved) passes an independent checker.
- `DONE` without the checker passing does not get reported as success.
- A canvas or empty snapshot returns `BLOCKED` with a spoken reason.
- Median decision step (snapshot + Laya, no typing) under 500 ms warm.

**Size:** about two to three weeks.

### Phase 6 — Autonomous mode

**Goal:** A goal can run more than one step, with the same safety gates.

**Build:**

- Loop edge, step caps, pause on confirm-gated tools.
- Checkers for two desktop goals (“open Notepad and type this sentence”) and one browser goal.
- The user can say “stop” (Sonic, then “stop”, or the hotkey) and the loop halts before the next input.

**Exit:**

- Both scripted goals pass 3/3.
- “Stop” interrupts before the next click in under 300 ms.
- No run exceeds its step cap, and a cap-out tells the user what was last done.

**Size:** about one to two weeks.

### Phase 7 — Breadth

Only after Phase 6. Pick from, in this order:

- Gmail and Drive **read**.
- Calendar create and Gmail send, confirm-only.
- More apps on the allowlist, user-taught control names.
- Multilingual utterances through `laya-multilingual`.
- Optional LoRA on Needle for Sonic’s tool names if the base model’s confidence stays under the act threshold on the eval set. A tuned Needle reports null confidence, so a replacement gate (eval accuracy, or a held-out checker) must exist before that swap.
- Optional Laya fine-tune on Sonic’s route and control labels if Phase 2 stays under 80%.

---

## 17. V1 scenario pack

These are the acceptance stories. Continuous mode unless noted.

1. “Open Notepad.” Notepad is in the foreground. Nothing else launches.
2. “Type hello.” The focused Notepad document contains hello. A non-editable focus asks instead of typing into the wrong window.
3. “Click Format.” The Format menu opens. The id in the log is the Format menu item from that snapshot.
4. “What’s 15% of 80?” The Python calculator answers 12. No cloud call, no Needle tool.
5. “Explain why my Python venv can’t see the package I just installed.” Route is `cloud_answer`. The trace shows the cloud model and no desktop tool.
6. “Search the web for the Laya model card.” `web_search` runs. Chrome is not driven.
7. “What’s on my calendar tomorrow?” After Google sign-in, events are spoken. Desktop tools do not run.
8. “Send an email to my boss.” The turn refuses or asks to confirm, and no message is sent. Gmail send is not installed in v1.
9. Browser fixture: a local page with a From field, a To field, and a Search button. Goal text names both values. The checker sees both values in the inputs and the results region. Works with `TYPESAFE_API_KEY` unset.
10. Autonomous, Phase 6: “Open Notepad and type the sentence good morning.” Two steps, one goal, checker sees the text.

---

## 18. Metrics

| Metric | V1 target | Where |
|---|---|---|
| Route exact-match | ≥ 85% | Phase 0 set |
| Refused actions that still execute | 0 | All phases |
| Desktop control exact-match | ≥ 80% | Phase 2 fixtures |
| Clicks on ids outside the snapshot | 0 | Phase 2+ |
| Warm `open_app` latency | < 3 s | Phase 1 |
| Warm click latency | < 1.5 s | Phase 2 |
| Idle CPU | < 5% of one core | Phase 1 |
| Browser fixture | 5/5 without TypeSafe | Phase 5 |
| Turns where two models both act | 0 | Phase 3+ |

Latency is measured from end of speech (or Enter, in the text harness) to the start of the side effect or the start of TTS.

---

## 19. Risks

| Risk | Why it is real | Mitigation |
|---|---|---|
| Base Laya is weak on unseen decision types | The published typed-decisions score lives on the fine-tuned checkpoint; base checkpoints are near chance | Use `laya-typed-decisions`, then measure Sonic’s own 100. Fine-tune only if Phase 0 misses 85% |
| Too many on-screen controls | Choice quality drops past ~20 labels because of `head_max_len` | Shortlist with embeddings; never pass the raw tree |
| `noul` label bias | English checkpoint can answer “no” because the option text says false | Use `choice` with semantic labels for gates |
| Needle retrieval hides the right tool | Only five tools enter context once the catalogue exceeds five | Separate tool groups per route so each group stays small |
| Tuned Needle has no confidence | Documented: confidence is null on tuned weights | Stay on base weights until a replacement gate exists |
| jev’s speed depends on hosted Jev | Local Laya is faster per decision but weaker on huge tables | Shortlist; keep the executor’s freshness checks; do not copy the API key dependency |
| UI Automation gaps | Some apps (games, custom-drawn UI, elevated windows) expose little or nothing | `BLOCKED` plus a spoken reason. No screenshot fallback in v1 |
| OAuth secret handling | Client secrets leak easily if they sit in `.env` that gets committed | Credential Manager, `.env` gitignored, log redaction |
| Chrome remote debugging | Attaching to the daily profile is powerful and easy to misuse | Browser subgraph only on `route = browser`; confirm before any page that can pay or send |
| Sonic false fires | An always-on mic will misfire | Default off, hotkey fallback, low-confidence routes ask rather than act |
| GPU provider fails halfway | A driver or CUDA install can load and then throw | That session retries once on CPU and logs the fallback. `auto` keeps the process up |

---

## 20. Configuration surface

```
SONIC_WAKE_ENABLED=false
SONIC_WAKE_MODEL=path/to/sonic-wake-word
SONIC_DEVICE=auto
SONIC_LAYA_CHECKPOINT=typed-decisions
SONIC_LAYA_RUNTIME=onnx
SONIC_NEEDLE_WEIGHTS=needle3.cact
SONIC_NEEDLE_ACT_THRESHOLD=0.55
SONIC_CLOUD_BASE_URL=https://api.openai.com/v1
SONIC_CLOUD_MODEL=
SONIC_CLOUD_API_KEY=
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
```

Cloud key and Google client secret are written into Credential Manager on first run. The file above is the list of knobs, not the place the secrets live.

---

## 21. Sources

- Laya model card: https://huggingface.co/convaiinnovations/laya
- Laya package and limits (choice budget, ONNX, LangGraph extras, typed-decisions numbers): https://pypi.org/project/laya/
- Laya LangGraph integration: https://nandhakishorm.github.io/laya/langchain/
- Laya ONNX export and local ultrafast loop: https://huggingface.co/gdelatournelle/laya-onnx
- Needle 3: https://huggingface.co/Cactus-Compute/needle3
- Needle confidence and tool retrieval: https://cactuscompute.com/blog/needle-confidence and https://cactuscompute.com/blog/needle-python-docs
- Needle device builds, including Windows x64: https://cactuscompute.com/blog/needle-supported-devices
- jev-ultrafast: https://github.com/browser-use/jev-ultrafast

---

## 22. Decision log

| Date | Decision | Reason |
|---|---|---|
| 2026-09-28 | LangGraph is the only orchestrator | Matches the requested stack and Laya’s `LayaRouter` edge |
| 2026-09-28 | Laya decides, Needle fills tools, the cloud model writes | Laya does not generate text; Needle does not do open answers; the writer does not click |
| 2026-09-28 | No local generative model | Simple work is a local tool call. General questions and composed typing go to the cloud model |
| 2026-09-28 | Wake word is the existing Sonic model | Already trained for this assistant. It only opens a turn |
| 2026-09-28 | GPU if available, otherwise CPU | `auto` probes CUDA, then DirectML, then CPU. A failed GPU session falls back. Needle stays on its CPU engine |
| 2026-09-28 | Continuous mode is v1; autonomous is Phase 6 | One action per wake is the safer way to earn click rights |
| 2026-09-28 | Accessibility text, not screenshots, for targeting | Same invariant as jev-ultrafast, and it keeps screen contents off the cloud path |
| 2026-09-28 | Browser policy is local Laya on jev’s action space | The upstream loop’s decision API is hosted TypeSafe; the executor and snapshot are the parts worth keeping |
