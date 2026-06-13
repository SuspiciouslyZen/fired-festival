# Fired Festival — Harness Challenge Research & Analysis

## Challenge Overview

Build a harness — a framework that an AI agent lives inside. The harness defines what the
agent gets for free: guardrails that constrain its behavior, checkpoints that evaluate its
outputs, clean interfaces for passing material in and out, and alarms that fire when
something goes wrong.

**Domain is your choice. The harness is what you're being evaluated on.**

---

## Requirements (from PDF)

### Must
- All four pillars implemented and **demonstrably separate from the worker** — guardrails, checkpoints, material handling, and alarms each exist as distinct, identifiable components in the code
- The harness governs an AI agent and the **agent's behavior changes meaningfully** based on guardrail or checkpoint feedback
- Guardrails are **declared, not implicit**. Checkpoints with **explicit pass/fail criteria**.
- Alarms produce **structured output** — named alarm types with context, severity, and a recommended action
- The harness runs on a **real input from the engineer's own work** at demo time
- An `HARNESS.md` file that covers the architecture and design of the harness

### Should
- **Swappable agent interface** — dropping in a different agent requires no changes to the harness
- **Checkpoint results are persisted** — you can replay a run from any checkpoint forward without re-running prior stages
- **Human-in-the-loop escalation paths** — the harness knows when to stop and ask rather than guess

### Bonus
- A second worker is swapped in during the demo to prove portability

---

## Deliverables

### Due Friday 11:30 PM
- 1-page Harness Planning Document

### Due Saturday 4:30 PM
- Project repo URL
- Deployed Harness URL
- `HARNESS.md` in the code repo
- 5-minute demo video

---

## Slide Deck Content (fired-festival.com/harness)

### The Core Idea
> "The model is the engine. The harness is the car."

An LLM only maps tokens to tokens. Everything that makes it useful and safe — memory, actions, retries, limits, logging — lives in the code wrapped around it.

| Raw model call | Model + harness |
|---|---|
| One prompt in, one completion out | Multi-turn loop with state |
| No memory of prior turns | Calls tools and reads results |
| Can't take actions | Validated, bounded, retried |
| No limits, no audit trail | Every step traced |

---

### The 4 Pillars (as taught in the slides)

The slides use slightly different terminology than the challenge PDF. Mapping:

| Slides | Challenge PDF |
|---|---|
| Loop | (implicit — you build this) |
| Tools | Material Handling |
| Guardrails | Guardrails |
| Observability | Checkpoints + Alarms (split into two) |

**This split matters.** The judges will expect you to distinguish between a checkpoint (pass/fail evaluation of output quality) and an alarm (structured signal that something broke). Do not conflate them.

---

### Pillar 1 — Chat / Loop

The core control structure: keep calling the model, feeding back tool results, until it emits a final answer or hits a limit.

```
1. Build context (system prompt + history + new input)
2. Call model (get text or a tool request)
3. Run tool (execute, capture result)
4. Append (add result to history)
5. Repeat / stop (loop until done or capped)
```

**The stop condition matters as much as the steps:** cap turns, tokens, and wall-clock time so a confused agent can't spin forever.

In code — the whole harness conceptually is ~15 lines:
```js
let messages = [systemPrompt, userInput];
for (let turn = 0; turn < MAX_TURNS; turn++) {
  const reply = await model(messages, tools);
  messages.push(reply);
  if (!reply.toolCalls) return reply.text; // done
  for (const call of reply.toolCalls) {
    const result = await runTool(call); // guardrails wrap this
    messages.push(result);
  }
}
throw new Error("turn limit reached");
```

---

### Pillar 2 — Tools (Material Handling)

A tool is a typed function the model can request. The harness validates the arguments, executes it, and returns the result as the next message.

- **Schema:** Name, description, and a typed parameter spec the model reads to decide how to call it
- **Executor:** Your real code — DB query, API call, file write — that runs when the model invokes the tool
- **Result contract:** Return predictable, parseable output. Errors come back as data the model can react to, not crashes

Engineering concerns: idempotency, per-tool timeouts, retries with backoff, and truncating large results before they blow the context window.

---

### Pillar 3 — Guardrails

Layered checks on the way in, the way out, and around the loop. The model will eventually do the wrong thing — design so it can't do damage.

- **Input:** Strip injection, validate and size-limit what enters the prompt
- **Action:** Allow-list tools, scope permissions, require approval for risky calls
- **Output:** Schema-check, filter, and fact-gate responses before they ship

Plus hard limits: turn caps, token budgets, timeouts, and spend ceilings.

**Key requirement from PDF:** Guardrails must be declared (e.g. a config file), not embedded implicitly in prompt engineering.

---

### Pillar 4 — Observability (Checkpoints + Alarms)

> "If you can't see it, you can't fix it."

Agents fail in non-obvious ways across many steps. Emit a structured span per model and tool call so you can replay, alert, and score.

Four signals that move reliability:
- **p95 latency** — per model & tool span
- **$/run** — token cost, input + output, per trace
- **err%** — tool error rate, failures & retries
- **eval** — pass rate scored vs. a test set

Instrument with OpenTelemetry:
```python
from opentelemetry import trace
tracer = trace.get_tracer("agent")

def chat_traced(messages, tools):
  with tracer.start_as_current_span("llm.call") as span:
    reply = client.chat(messages, tools)
    span.set_attribute("llm.model", reply.model)
    span.set_attribute("llm.tokens_in", reply.usage.input)
    span.set_attribute("llm.tokens_out", reply.usage.output)
    span.set_attribute("llm.cost_usd", reply.cost)
  return reply
```

Tooling options mentioned:
- **Hosted:** Langfuse, LangSmith, Arize Phoenix, Helicone, Braintrust, W&B Weave, Datadog LLM Obs
- **Self-host:** Phoenix, SigNoz, Jaeger, Grafana Tempo, Prometheus+Grafana, OTel Collector
- **Eval:** Promptfoo, DeepEval, Ragas, OpenAI Evals, Braintrust, LangSmith datasets

---

### Full Picture — How the Pillars Stack

A request flows down through layers and back. Guardrails wrap the loop; observability watches all of it.

```
Guardrails (input) → validate incoming request
        ↓
Loop + Tools → model reasons, calls allow-listed tools, iterates to answer
        ↓
Guardrails (output) → validate final response
        ↓
Observability → every step above emits a trace event
```

---

### Domain Examples from Slides

| Domain | Tools | Guardrail |
|---|---|---|
| Coding agent | read/write files, run tests, grep | sandbox + diff review |
| Research assistant | web search, fetch, cite | source allow-list + claim checks |
| Support triage | ticket lookup, KB search, tag | human approval to reply |
| Data copilot | SQL query, chart | read-only DB role + row limits |
| Inbox agent | search mail, draft | draft-only, never auto-send |
| **Ops runbook** | **check status, restart** | **dry-run + on-call confirm** |

The ops runbook is explicitly named in the slides — directly relevant to a DevOps background.

---

### Slide Takeaway

> "Start with the loop. Harden from there."
> "The model is a commodity you call. Your harness — the loop, the tools, the guardrails, the traces — is the durable engineering, and where reliability is actually won."

Build order recommended by slides:
1. Loop first — get a bounded loop working end to end
2. Add tools — one typed tool at a time, with clear contracts
3. Wrap guardrails — limits and validation before you scale up
4. Instrument — trace from day one, not after the first outage

---

## Chosen Domain: Ops Runbook Harness

An AI agent that responds to infrastructure alerts by following runbooks. The harness enforces safety constraints the agent cannot override.

### Why This Domain
- Directly named in the slides as an example
- Authentic to a DevOps background — high credibility in the room
- Real-time value is obvious and defensible
- Real input for demo = a real incident or alert from own work history

### The 4 Pillars Mapped to This Domain

**Guardrails (declared in `guardrails.yaml`):**
- Action allow-list: only `check_status`, `restart_service`, `scale_pod`, `read_logs` — never `delete`, `drop`, `terminate`
- Environment scope: `staging` by default; `production` requires human approval
- Dry-run mode: all destructive actions forced through approval gate
- Hard limits: max turns, token budget, wall-clock timeout

**Checkpoints (explicit pass/fail, persisted to SQLite):**
- CP1: Alert parsed and enriched (pass = known service + severity extracted)
- CP2: Root cause hypothesis formed (pass = hypothesis confidence > threshold)
- CP3: Remediation plan validated (pass = all proposed actions on allow-list)
- CP4: Post-action health check (pass = service metrics within SLA bounds)
- Replay: load prior checkpoint state, skip completed stages, resume from any point

**Material Handling:**
- Input schema: alert/incident JSON (PagerDuty format or custom)
- Output schema: structured remediation report — actions taken, rationale, metrics before/after

**Alarms (structured Pydantic model — `{type, context, severity, recommended_action}`):**
- `UNKNOWN_SERVICE` (warning) — alert references unrecognized service → escalate to on-call
- `DESTRUCTIVE_ACTION_REQUESTED` (critical) — agent proposed action not on allow-list → halt + human approval
- `REMEDIATION_FAILED` (critical) — post-action health check failed → escalate immediately
- `TURN_LIMIT_REACHED` (warning) — agent exceeded max turns → human review needed
- `CONFIDENCE_LOW` (info) — hypothesis confidence below threshold → request human input

### Should/Bonus Requirements

**Swappable agent interface:**
- `BaseAgent` abstract class
- `ClaudeAgent` implementation (primary)
- `OpenAIAgent` implementation (bonus demo swap — ~30 lines)
- Model selection via config, zero harness changes required

**Human-in-the-loop:**
- CRITICAL alarms halt the loop
- Emit escalation event with full context
- FastAPI pause/resume endpoint — harness waits for human decision before continuing

**Checkpoint persistence + replay:**
- SQLite, one row per checkpoint per run
- Run ID tracked throughout
- CLI flag `--replay-from=CP2` skips CP1, loads state, resumes

---

## Stack

| Layer | Tech |
|---|---|
| Language | Python |
| Web / API | FastAPI |
| LLM | Anthropic SDK (Claude), OpenAI SDK (swap) |
| Structured types | Pydantic |
| Checkpoint persistence | SQLite |
| Guardrails config | YAML |
| Deployment | Railway or Render |

---

## Level of Effort (AI-First — Claude Code writes the code)

| Phase | Human time |
|---|---|
| Planning doc (tonight) | 30-45 min |
| Core harness skeleton | 30 min |
| All 4 pillar modules | 45 min |
| Tools + mock implementations | 20 min |
| Checkpoint persistence + replay | 30 min |
| Human-in-the-loop | 20 min |
| Swappable agent + GPT-4 swap | 15 min |
| FastAPI + deploy | 30 min |
| HARNESS.md | 20 min |
| **Total** | **~4 hours** |

### The AI-First Story
Using Claude Code to build a Claude-powered harness **is the point**. The demo video should make this explicit — an AI-first engineer used an AI coding agent to build an AI harness. That's not a footnote, it's the headline.

---

## Key Risks

1. **Deployed URL** — needs actual deployment, not just local. Don't leave this to the last hour.
2. **Checkpoint replay** — the replay feature adds real complexity. Build and test it early.
3. **Demo input** — have a real incident/alert ready before demo. Don't improvise this live.
4. **Conflating checkpoints and alarms** — judges wrote the slides. They know the difference. Keep them architecturally separate.
