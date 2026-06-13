---
name: Ops Runbook Harness
last_updated: 2026-06-12
---

# Ops Runbook Harness Strategy

## Target problem

When production systems break, ops teams page on-call engineers for problems with known fixes — restarting instances, killing hung queries, flushing DNS. The hard part isn't running the fix; it's knowing whether automation can safely act, verifying the fix actually worked, and catching downstream damage before it cascades.

## Our approach

Start constrained with pre-approved runbooks, then grow autonomy through documented learning. Every automated fix produces a full incident record — from initial alert through resolution — capturing what was tried, what happened, and what broke. The boundary between "auto-fix" and "escalate to a human" shifts over time based on evidence, not guesswork. The AI earns the right to act by proving it can.

## Who it's for

**Primary:** NOC / ops team leads — they're hiring the Ops Runbook Harness to cut MTTR on known-fix incidents and free engineers from routine on-call so they can focus on expansion and higher-value work.

## Key metrics

- **MTTR** — mean time to resolution from alert to confirmed fix; measured from alerting system timestamps
- **Auto-resolve rate** — % of incidents resolved without human intervention; should climb as the runbook grows
- **Escalation accuracy** — % of escalations where the human agreed it needed escalating; measures whether the AI knows its limits
- **Fix success rate** — % of automated remediations that pass post-action health checks without causing new incidents
- **Regression rate** — new incidents caused by automated fixes; target is zero

## Tracks

### Runbook engine

The core loop — ingesting alerts, matching to known playbooks, executing approved remediation actions (restart EC2 instances, kill long-running DB queries, flush DNS, restart dropped VPN tunnels, clear degraded app caches). When auto-scaling hits max thresholds, alert the team rather than attempt to scale further.

_Why it serves the approach:_ Pre-approved runbooks are the foundation; without a reliable execution engine, nothing else matters.

### Safety & verification

The harness must block any mutation not explicitly on the approved allow-list. The AI cannot execute non-approved actions in production — no exceptions. This includes post-action health checks, regression detection, and escalation logic. An unconstrained AI responding to a production incident can make the issue worse or take down the full system.

_Why it serves the approach:_ The AI can only earn autonomy if every action is verified and every unapproved action is blocked. This is what makes "start constrained" safe enough to trust.

### Learning loop

Every incident is documented end-to-end — from initial alert through diagnosis, remediation, and resolution — capturing actions taken, outcomes, human overrides, and downstream effects. This record feeds AI recommendations for new runbook entries and improves future diagnosis.

_Why it serves the approach:_ This is the mechanism that grows the runbook over time. Full incident documentation is what turns individual fixes into organizational knowledge.

### Observability & trust

Dashboards, audit trails, and the metrics that prove the system is working. If you can't see it, you can't trust it.

_Why it serves the approach:_ Ops teams won't hand off on-call to a system they can't observe. Transparency is what earns organizational trust.

## Milestones

- **2026-06-12 ~1:00 AM** — Architecture doc ready to defend
- **2026-06-12 ~6:00 AM** — Build complete (deployed URL, HARNESS.md, demo video)
