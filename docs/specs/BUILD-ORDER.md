# Build Order

## Repo Structure (Final State)

```
fired-festival/
├── docs/                           # Planning, research, architecture docs
│   ├── plans/
│   ├── specs/                      # This file lives here
│   └── architecture/               # Move architecture HTML/PDF here
├── src/                            # All harness source code
│   ├── harness/
│   │   ├── __init__.py
│   │   ├── loop.py                 # U7: Core agent loop
│   │   ├── guardrails.py           # U2: Guardrail loading + enforcement
│   │   ├── checkpoints.py          # U4: Checkpoint evaluation + persistence
│   │   ├── material.py             # U5: Input/output schema validation
│   │   ├── alarms.py               # U3: Alarm types + emission
│   │   └── models.py               # U1: Shared Pydantic models
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── base.py                 # U1: BaseAgent abstract class
│   │   ├── claude_agent.py         # U8: Claude implementation
│   │   └── openai_agent.py         # U8: OpenAI swap implementation
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── registry.py             # U6: Tool registration + allow-list check
│   │   ├── check_status.py         # U6: Mock tool
│   │   ├── restart_service.py      # U6: Mock tool
│   │   ├── read_logs.py            # U6: Mock tool
│   │   ├── kill_query.py           # U6: Mock tool
│   │   └── flush_dns.py            # U6: Mock tool
│   ├── db/
│   │   ├── __init__.py
│   │   └── store.py                # U4: SQLite checkpoint store
│   └── api/
│       ├── __init__.py
│       └── routes.py               # U9: FastAPI endpoints
├── tests/
│   ├── __init__.py
│   ├── test_models.py              # U1
│   ├── test_guardrails.py          # U2
│   ├── test_alarms.py              # U3
│   ├── test_checkpoints.py         # U4
│   ├── test_material.py            # U5
│   ├── test_tools.py               # U6
│   ├── test_loop.py                # U7
│   ├── test_agents.py              # U8
│   └── test_api.py                 # U9
├── fixtures/
│   ├── alerts/                     # Sample alert JSONs for demo + tests
│   │   ├── high_cpu_web_api.json
│   │   ├── hung_query_postgres.json
│   │   ├── dns_failure_cdn.json
│   │   └── unknown_service.json
│   └── mock_responses/             # Deterministic tool responses per scenario
│       ├── high_cpu_scenario.py
│       ├── hung_query_scenario.py
│       ├── dns_failure_scenario.py
│       └── unknown_service_scenario.py
├── guardrails.yaml                 # Declared guardrail config (root level, visible)
├── main.py                         # Entry point
├── pyproject.toml
├── Dockerfile
├── CLAUDE.md
├── HARNESS.md                      # Architecture doc (deliverable)
├── README.md
├── RESEARCH.md
└── STRATEGY.md
```

---

## Build Sequence for Sonnet

Execute these in order. Each unit should be fully tested before moving to the next.

| Step | Unit | What to build | Est. tokens |
|------|------|---------------|------------|
| 1 | U0 | Repo restructure, pyproject.toml, CLAUDE.md, guardrails.yaml, main.py, all `__init__.py` files | Low |
| 2 | U1 | `src/harness/models.py`, `src/agents/base.py`, `tests/test_models.py` | Low |
| 3 | U2 | `src/harness/guardrails.py`, `tests/test_guardrails.py` | Low |
| 4 | U3 | `src/harness/alarms.py`, `tests/test_alarms.py` | Low |
| 5 | U4 | `src/db/store.py`, `src/harness/checkpoints.py`, `tests/test_checkpoints.py` | Medium |
| 6 | U5 | `src/harness/material.py`, `tests/test_material.py` | Low |
| 7 | U6 | `src/tools/registry.py`, all 5 tool files, `src/tools/__init__.py`, `tests/test_tools.py` | Medium |
| 8 | U7 | `src/harness/loop.py`, `tests/test_loop.py` | High — use Opus |
| 9 | U8 | `src/agents/claude_agent.py`, `src/agents/openai_agent.py`, `tests/test_agents.py` | Medium |
| 10 | U9 | `src/api/routes.py`, `tests/test_api.py` | Medium |
| 11 | U10 | `Dockerfile`, `HARNESS.md`, `README.md` | Low |
| 12 | Fixtures | All 4 alert JSONs in `fixtures/alerts/` | Low |

**Recommendation**: Use Sonnet for all steps except U7 (the loop is the most architecturally critical piece and benefits from Opus reasoning). U8 agent implementations could also benefit from Opus for getting the SDK message format conversions right.
