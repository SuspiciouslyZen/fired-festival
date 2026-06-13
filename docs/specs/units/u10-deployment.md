# U10. Deployment + HARNESS.md

## Dependencies

- All prior units (U0–U9) — the Dockerfile bundles the complete project; HARNESS.md documents the full system

**Files created by this unit:**
- `Dockerfile`
- `HARNESS.md`
- `README.md`

---

## Dockerfile

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir .

COPY . .
RUN mkdir -p data

EXPOSE 8000

CMD ["python", "main.py"]
```

---

## HARNESS.md

Write this as the architecture deliverable. Structure:

1. **Overview** — one paragraph: what this harness does, what domain it operates in
2. **Architecture** — the four pillars, how they connect, a text diagram of the flow
3. **Guardrails** — what's declared in `guardrails.yaml`, how enforcement works, code pointer to `src/harness/guardrails.py`
4. **Checkpoints** — CP1-CP4 criteria, persistence to SQLite, replay mechanism, code pointer to `src/harness/checkpoints.py`
5. **Alarms** — alarm types with severity, structured output format, HITL escalation flow, code pointer to `src/harness/alarms.py`
6. **Material Handling** — input alert schema, output remediation report schema, code pointer to `src/harness/material.py`
7. **Agent Interface** — `BaseAgent` contract, how to swap agents, code pointer to `src/agents/base.py`
8. **Tools** — registry, allow-list enforcement, the 5 mock tools and their signatures
9. **API Endpoints** — table of all endpoints with method, path, description
10. **Running locally** — install, configure, run, test
11. **Deployment** — Railway setup, environment variables needed
