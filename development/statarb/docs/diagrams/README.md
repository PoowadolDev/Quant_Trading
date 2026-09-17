# Diagrams

| Diagram | File | What it shows |
|---|---|---|
| Research pipeline | [research-pipeline.md](research-pipeline.md) | The statarb gate sequence — every script under `code/`, every reject condition, and which real candidates died where |

This project is a research pipeline, not a service, so the usual C4/ER/module
diagrams do not apply: no database schema, no service boundary, no request
lifecycle. The one diagram here is the thing that actually matters — the order
gates run in and what has rejected on real data at each one.
