# ☁ CloudPulse — AI-Powered Cloud Carbon Footprint Monitor

> **National Finalist (Top 150 of 1,400+ teams) — Cloud Hackathon 2026, Sustainable Workload Orchestration track.**
> A hackathon prototype that estimates the carbon footprint of AWS EC2 workloads and uses Claude to recommend greener, cheaper configurations.

---

## Why

Monitoring tools like CloudWatch show CPU and cost, but not carbon. The same workload can emit very different amounts of CO₂ depending on the region's electricity grid (for example, `us-east-1` at 0.415 kg CO₂/kWh vs `eu-north-1` at 0.012 kg CO₂/kWh). CloudPulse makes that visible and suggests what to change.

## What it does

| Feature | Where | Status |
|---|---|---|
| Pull EC2 CPU utilisation from **AWS CloudWatch** and list running instances via **boto3** | `backend/monitor.py` | Implemented (needs AWS credentials) |
| Convert CPU % → energy (kWh) → **CO₂ (kg)** using per-region carbon-intensity factors | `backend/monitor.py` | Implemented |
| Flag **idle instances** (< 5 % CPU) | `backend/monitor.py`, `backend/app.py` | Implemented |
| **Claude Sonnet** recommendations: ranked actions with estimated CO₂/cost savings and AWS CLI commands (JSON output) | `backend/monitor.py` → `ai_recommend()` | Implemented (needs Anthropic API key) |
| **Green region router**: ranks regions by carbon intensity and estimates % reduction from migrating | `backend/monitor.py` → `suggest_green_region()` | Implemented |
| **FastAPI** REST API for the dashboard | `backend/app.py` | Implemented; serves **mock fleet data** for demo |
| Remediation as ready-to-run **AWS CLI commands** (stop idle instances, scheduled scaling, region migration, S3 Intelligent-Tiering) | `backend/app.py` → `/api/recommendations` | Commands are generated, **not executed automatically** |
| Single-page **dashboard** (HTML + Chart.js): fleet table, 24h trend, recommendations, region comparison | `frontend/dashboard.html` | Static demo UI |

## Architecture

```
AWS CloudWatch / EC2  ──boto3──▶  monitor.py (carbon engine)  ──▶  Claude Sonnet (recommendations)
                                         │
                                         ▼
                                  app.py (FastAPI)  ──▶  dashboard.html (Chart.js)
```

Carbon formula (simplified):

```python
kwh    = WATTS_PER_VCPU * vcpus * (cpu_pct / 100) * hours
co2_kg = kwh * CARBON_FACTOR[region]
```

## Tech stack

- **Backend:** Python, FastAPI, Uvicorn, Pydantic, boto3 (CloudWatch, EC2), Anthropic SDK (Claude Sonnet)
- **Frontend:** HTML, CSS, JavaScript, Chart.js

## API

| Endpoint | Method | Description |
|---|---|---|
| `/` | GET | Health check |
| `/api/dashboard` | GET | Fleet summary, instances, 24h CO₂ series (mock data) |
| `/api/recommendations` | GET | Ranked recommendations with AWS CLI commands |
| `/api/regions` | GET | Carbon intensity for tracked AWS regions |
| `/api/carbon/{instance_id}` | GET | CO₂ estimate for a given CPU % and vCPU count |

## Run locally

```bash
pip install -r requirements.txt
cp .env.example .env        # template for ANTHROPIC_API_KEY and AWS keys
# the code reads them from environment variables / the AWS CLI config

cd backend
uvicorn app:app --reload    # API at http://localhost:8000, docs at /docs
```

Open `frontend/dashboard.html` in a browser to see the dashboard demo.

To try the live engine against your own AWS account:

```bash
cd backend
python monitor.py
```

## Limitations / next steps

- The API and dashboard currently use generated mock data; wiring them to `CloudPulseMonitor` for live data is the next step.
- Remediation commands are suggestions only; executing approved actions via boto3 is not implemented.
- Energy estimates use a simple per-vCPU model, not measured power draw.
- Carbon-intensity factors are static; a live source (e.g. Electricity Maps) would improve accuracy.

## Team

Built by Team CloudPulse for Cloud Hackathon 2026.
