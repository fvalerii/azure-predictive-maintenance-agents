# 🏭 TireForge Predictive Maintenance — Multi-Agent AI System

[![Tests](https://github.com/fvalerii/azure-predictive-maintenance-agents/actions/workflows/tests.yml/badge.svg)](https://github.com/fvalerii/azure-predictive-maintenance-agents/actions/workflows/tests.yml)
[![Agent Quality Gate](https://github.com/fvalerii/azure-predictive-maintenance-agents/actions/workflows/evaluate.yml/badge.svg)](https://github.com/fvalerii/azure-predictive-maintenance-agents/actions/workflows/evaluate.yml)

A multi-agent AI system, built on **Microsoft Foundry (Azure AI Foundry Agent Service)**, that watches live sensor telemetry across a tire manufacturing plant, detects anomalies, diagnoses root causes, checks maintenance history and spare-part inventory, grounds its recommendations in the equipment manual, and — for critical faults — routes the decision through a human approval gate before opening a maintenance work order.

This started as the **Factory** scenario of Microsoft's *Foundry Agent-a-Thon* (FrontierWeekHack) hands-on lab and was extended well beyond the base exercises — see [What I Built](#what-i-built) below for what's original work versus lab scaffolding.

![scenario](./images/scenario.png)

## The Scenario

**TireForge Industries** operates a tire manufacturing plant with 5 critical machines, each streaming temperature, pressure, vibration, and RPM readings in real time:

| Machine | Role |
|---|---|
| **MX-001** — Mixer | Blends raw rubber compounds |
| **EX-002** — Extruder | Shapes rubber into tire tread profiles |
| **CP-003** — Curing Press | Vulcanizes tires under heat and pressure |
| **CU-004** — Cooling Unit | Gradually cools cured tires |
| **IS-005** — Inspection Station | Quality assurance via vibration analysis |

The goal: catch a failing machine from its sensor signature *before* it causes a production-line stoppage or scraps a batch — and hand the maintenance team a decision they can trust, not a black-box guess.

## What I Built

The base lab asks you to build two agents that detect anomalies and diagnose faults. I implemented that core, plus several of the lab's own "Next Steps" suggestions, turning it into a closer-to-production system:

- **Anomaly Detection Agent** — calls a `check_thresholds` tool grounded in real per-machine spec data (not model guesswork) to flag out-of-spec sensor readings across all 5 machines.
- **Fault Diagnosis Agent** — given a set of anomalies, it:
  - Calls **`fetch_maintenance_history`** to pull a machine's past repair record from a mock CMMS before reasoning about root cause.
  - Uses **File Search (RAG)** against `TireForge_Manual_V2.md`, uploaded to a Foundry vector store, so recommendations cite documented procedures instead of general LLM knowledge.
  - Calls **`lookup_spare_parts`** against a mock inventory system to check part availability before recommending a fix, and suggests a workaround if the part is out of stock.
  - Classifies urgency (`IMMEDIATE` / `WITHIN 24H` / `MONITOR`) and flags whether the action `REQUIRES_APPROVAL`.
- **Human-in-the-loop approval gate** — when the diagnosis is `IMMEDIATE`, the pipeline stops and asks a human to approve before the `create_work_order` tool is allowed to open a ticket. Reject it, and it escalates to a shift supervisor instead of auto-executing.
- **Confidence-gated escalation** — the Anomaly Detection Agent self-rates its confidence per machine; anything it flags as low-confidence (borderline readings, conflicting signals) is escalated to a human instead of being passed to Fault Diagnosis automatically, so an uncertain classification never gets laundered into a confident-sounding root-cause guess.
- **Parallel multi-agent execution** — the production workflow checks all 5 machines concurrently (one agent call per machine via a thread pool) instead of sequentially, and diagnoses every anomalous machine concurrently too, so total latency is bounded by the slowest machine rather than the sum of all of them.
- **Observability** — OpenTelemetry GenAI tracing exports every model call, tool call, and token count to Application Insights, so you can see exactly what data the model saw before it reached a conclusion.
- **Evaluation** — a 10-scenario LLM-as-judge dataset (coherence + fluency) for regression-testing prompt/model changes.
- **Multi-agent orchestration workflow** — both agents are wired into a `factory-health-workflow`, runnable either as Python code (step-by-step, with full function-call handling) or as a `WorkflowAgentDefinition` deployed to the Foundry portal and invoked asynchronously via the Responses API with background polling.

## Architecture

![architecture](./images/architecture.png)

![agentic-orchestration](./images/agentic-orchestration.png)

## Tech Stack

- **Microsoft Foundry / Azure AI Foundry Agent Service** — hosted, versioned agents (`azure-ai-projects`, `azure-ai-agents`)
- **Azure OpenAI** — reasoning model backing each agent
- **Function calling** — custom Python tools (`check_thresholds`, `fetch_maintenance_history`, `lookup_spare_parts`, `create_work_order`)
- **File Search / vector store** — retrieval-augmented generation over the equipment manual
- **OpenTelemetry + Azure Monitor** — distributed tracing (`azure-monitor-opentelemetry`)
- **Azure AI Evaluation SDK** — LLM-as-judge quality scoring
- **Azure CLI / Bash** — one-command infrastructure provisioning (`deploy.sh`) and teardown (`cleanup.sh`)

## Repository Structure

The folders are organized as build phases, each with its own detailed README:

| Folder | What's in it |
|---|---|
| [`challenge-0-setup/`](./challenge-0-setup/README.md) | `deploy.sh` — provisions the Foundry resource, project, model deployment, Log Analytics, and Application Insights via Azure CLI |
| [`challenge-1-build/`](./challenge-1-build/README.md) | `agents.py` — the Anomaly Detection + Fault Diagnosis agents, their tools, and the human-approval workflow; `sensor_data.json` — mock live telemetry |
| [`challenge-2-monitor/`](./challenge-2-monitor/README.md) | `monitor.py` — enables GenAI tracing and verifies traces land in Application Insights |
| [`challenge-3-evaluate/`](./challenge-3-evaluate/README.md) | `eval_portal.jsonl` — evaluation dataset; `evaluate.py` — scripted LLM-as-judge scoring, also run as a CI quality gate |
| [`challenge-4-deploy/`](./challenge-4-deploy/README.md) | `deploy.py` — multi-agent orchestration (Python + portal `WorkflowAgentDefinition`); `evaluation_dataset.json` |
| `TireForge_Manual_V2.md` | Mock equipment manual used as the RAG knowledge base |
| `inventory.json`, `maintenance_history.json` | Mock spare-parts and CMMS data used by the tool functions |
| `tests/` | `pytest` suite covering the local tool logic (no Azure required) |
| `cleanup.sh` | Tears down all Azure resources created by `deploy.sh` |

## Getting Started

```bash
git clone <this-repo-url>
cd azure-predictive-maintenance-agents
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
az login

# Provision Azure resources (writes .env to the repo root)
bash challenge-0-setup/deploy.sh

# Build & run both agents
cd challenge-1-build && python agents.py

# Enable tracing
cd ../challenge-2-monitor && python monitor.py

# Run the orchestrated multi-agent workflow
cd ../challenge-4-deploy && python deploy.py
```

Each folder's README walks through that step in detail, including what to expect in the Foundry portal. When you're done, tear everything down with `bash cleanup.sh` (reads the resource group from your `.env`).

## Testing (no Azure required)

The agents themselves need a deployed Foundry project to run, but the tool logic they call (`check_thresholds`, `fetch_maintenance_history`, `lookup_spare_parts`, `create_work_order`) is plain Python that only reads/writes local JSON — no cloud dependency. That logic has a `pytest` suite that runs on every push via GitHub Actions (see the badge above), so you can verify the core logic works without provisioning anything:

```bash
pip install -r requirements-dev.txt
pytest -v
```

## Roadmap

The base lab suggests several directions to extend the system further — here's what's done and what's still open:

- [x] Additional tools calling mock external systems (CMMS, inventory, ticketing)
- [x] Knowledge base / File Search grounding for the diagnosis agent
- [x] Human-in-the-loop approval for critical actions
- [x] Hosted, production-style workflow orchestration
- [x] CI/CD quality gate — `evaluate.py` runs the evaluation dataset on every pull request and fails the build if coherence/fluency drops below threshold (see [`challenge-3-evaluate/`](./challenge-3-evaluate/README.md#integrating-into-cicd))
- [x] Parallelize anomaly checks across all 5 machines instead of sequential tool calls (see [`challenge-4-deploy/`](./challenge-4-deploy/README.md#the-workflow))
- [x] Confidence thresholds — escalate to a human when the Anomaly Agent is uncertain, not just when faults are critical (see [`challenge-4-deploy/`](./challenge-4-deploy/README.md#the-workflow))
- [ ] Swap the mock JSON data sources (`sensor_data.json`, `inventory.json`, `maintenance_history.json`) for a live IoT Hub / real CMMS and ERP integration
- [ ] Fine-tune a model on TireForge-specific failure patterns — deliberately not attempted here: it needs real production-scale training data and a live training run to demonstrate credibly, which isn't practical for a mock dataset this size

## Acknowledgements

Built during Microsoft's **Foundry Agent-a-Thon** (FrontierWeekHack) hands-on lab — the Challenge 0–4 structure, base lab READMEs, mock sensor dataset, and Azure infrastructure scripts originate from [microsoft/FrontierWeekHack](https://github.com/microsoft/FrontierWeekHack) (MIT licensed). The agent tools beyond `check_thresholds` (maintenance history, spare parts, work orders), the RAG knowledge base integration, the human-in-the-loop approval flow, and the SDK bug fixes are my own extensions on top of that foundation.

## License

MIT — see [LICENSE](./LICENSE).
