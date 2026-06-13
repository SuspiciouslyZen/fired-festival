# Ops Runbook Harness

AI agent harness for infrastructure incident remediation. Submit an alert, get a remediation report.

## Quick start

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
export ANTHROPIC_API_KEY=your-key
python main.py
```

Then: `curl -X POST http://localhost:8000/run -H "Content-Type: application/json" -d '{"service":"web-api","severity":"high","description":"CPU spiking"}'`

## Docs

See [HARNESS.md](HARNESS.md) for full architecture documentation.
