"""
CloudPulse — FastAPI REST Server
Exposes endpoints for the React dashboard to consume
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import json
import random
import math
from datetime import datetime, timedelta
from monitor import CloudPulseMonitor, CARBON_FACTOR

app = FastAPI(title="CloudPulse API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

monitor = CloudPulseMonitor(region="us-east-1")


# ------------------------------------------------------------------
# Mock data generator (for demo without real AWS)
# ------------------------------------------------------------------
def mock_instances():
    types = ["t3.micro", "t3.medium", "t3.large", "m5.xlarge", "c5.2xlarge"]
    names = ["web-server", "api-gateway", "db-replica", "ml-trainer", "batch-job",
             "log-processor", "cache-node", "dev-instance", "staging-app", "idle-worker"]
    instances = []
    for i in range(10):
        cpu = random.uniform(0.5, 95) if i < 7 else random.uniform(0.1, 3)
        itype = random.choice(types)
        vcpus = {"t3.micro": 2, "t3.medium": 2, "t3.large": 2,
                 "m5.xlarge": 4, "c5.2xlarge": 8}.get(itype, 2)
        co2 = 0.003 * vcpus * (cpu / 100) * CARBON_FACTOR["us-east-1"]
        instances.append({
            "instance_id": f"i-{random.randint(100000, 999999):06x}",
            "name": names[i],
            "type": itype,
            "vcpus": vcpus,
            "cpu_pct": round(cpu, 1),
            "co2_kg_per_hour": round(co2, 5),
            "is_idle": cpu < 5.0,
            "region": "us-east-1",
        })
    return instances


def mock_24h_series():
    """Returns 24 hourly CO2 readings (kg) for charting."""
    base = 180
    series = []
    for h in range(24):
        noise = random.gauss(0, 12)
        wave = 40 * math.sin(h * math.pi / 12)
        series.append({
            "hour": h,
            "co2_kg": round(max(50, base + wave + noise), 1),
            "kwh": round(max(120, (base + wave + noise) / 0.415), 1),
        })
    return series


# ------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------
@app.get("/")
def root():
    return {"service": "CloudPulse API", "status": "running", "version": "1.0.0"}


@app.get("/api/dashboard")
def get_dashboard():
    """Main dashboard data — KPIs + instance list + 24h series."""
    instances = mock_instances()
    series = mock_24h_series()
    total_co2_day = sum(i["co2_kg_per_hour"] * 24 for i in instances)
    idle_count = sum(1 for i in instances if i["is_idle"])

    return {
        "timestamp": datetime.utcnow().isoformat(),
        "kpis": {
            "co2_today_kg": round(total_co2_day, 2),
            "cloud_spend_inr": round(total_co2_day * 28.4, 0),
            "green_energy_pct": 62,
            "idle_instances": idle_count,
        },
        "instances": instances,
        "series_24h": series,
        "workload_distribution": {
            "Compute": 38,
            "Storage": 26,
            "Network": 20,
            "Database": 16,
        },
    }


@app.get("/api/recommendations")
def get_recommendations():
    """AI-generated optimization recommendations (mock for demo)."""
    instances = mock_instances()
    idle = [i for i in instances if i["is_idle"]]

    recs = [
        {
            "priority": 1,
            "action": f"Scale down {len(idle)} idle instances in us-east-1",
            "reason": "CPU < 5% for 6+ hours — clear zombie workloads",
            "co2_saving_kg_day": round(sum(i["co2_kg_per_hour"] * 24 for i in idle), 2),
            "cost_saving_inr_month": round(len(idle) * 420, 0),
            "command": "aws ec2 stop-instances --instance-ids " +
                       " ".join(i["instance_id"] for i in idle[:3]),
        },
        {
            "priority": 2,
            "action": "Enable scheduled scaling 11PM–6AM",
            "reason": "Night traffic drops 80% — auto-scale down saves energy",
            "co2_saving_kg_day": 18.4,
            "cost_saving_inr_month": 3800,
            "command": "aws autoscaling put-scheduled-update-group-action "
                       "--auto-scaling-group-name prod-asg "
                       "--scheduled-action-name night-scale-down "
                       "--recurrence '0 23 * * *' --desired-capacity 2",
        },
        {
            "priority": 3,
            "action": "Migrate batch jobs to eu-north-1 (Iceland)",
            "reason": "Carbon factor 0.012 vs 0.415 — 97% cleaner electricity",
            "co2_saving_kg_day": 31.2,
            "cost_saving_inr_month": 0,
            "command": "aws ec2 copy-image --source-region us-east-1 "
                       "--source-image-id ami-XXXXXXXX --region eu-north-1",
        },
        {
            "priority": 4,
            "action": "Enable S3 Intelligent-Tiering on all buckets",
            "reason": "Auto-moves cold data to cheaper, lower-power storage tiers",
            "co2_saving_kg_day": 4.1,
            "cost_saving_inr_month": 1200,
            "command": "aws s3api put-bucket-intelligent-tiering-configuration "
                       "--bucket YOUR_BUCKET --id cloudpulse-tiering "
                       "--intelligent-tiering-configuration Status=Enabled",
        },
    ]
    return {"recommendations": recs, "generated_at": datetime.utcnow().isoformat()}


@app.get("/api/regions")
def get_region_comparison():
    """Carbon factor for all tracked AWS regions."""
    return {
        "regions": [
            {"region": k, "carbon_factor": v,
             "label": "🌱 Greenest" if v < 0.05 else ("⚠️ High" if v > 0.5 else "OK")}
            for k, v in sorted(CARBON_FACTOR.items(), key=lambda x: x[1])
        ]
    }


@app.get("/api/carbon/{instance_id}")
def get_instance_carbon(instance_id: str, cpu_pct: float = 50.0, vcpus: int = 2):
    """Calculate carbon footprint for given CPU% and vCPU count."""
    result = monitor.cpu_to_carbon(cpu_pct, vcpus)
    return {
        "instance_id": instance_id,
        "input": {"cpu_pct": cpu_pct, "vcpus": vcpus},
        "output": result,
        "daily_projection": {
            "co2_kg_day": round(result["co2_kg"] * 24, 3),
            "kwh_day": round(result["kwh"] * 24, 3),
        },
    }
