"""
CloudPulse — AI-Powered Cloud Carbon Footprint Monitor
Core monitoring engine: fetches AWS metrics, calculates CO2, calls Claude AI
"""

import boto3
import json
import os
from datetime import datetime, timedelta
from anthropic import Anthropic

# ------------------------------------------------------------------
# Regional Carbon Intensity (kg CO2 per kWh) — source: electricityMap
# ------------------------------------------------------------------
CARBON_FACTOR = {
    "us-east-1":      0.415,   # Virginia — coal/gas heavy
    "us-west-2":      0.136,   # Oregon — hydro
    "eu-west-1":      0.316,   # Ireland
    "eu-north-1":     0.012,   # Stockholm — almost 100% hydro ⚡
    "ap-south-1":     0.708,   # Mumbai — coal heavy
    "ap-southeast-1": 0.493,   # Singapore
    "ca-central-1":   0.130,   # Canada — hydro
}

# Average power draw per vCPU at 50% utilization (kW)
WATTS_PER_VCPU = 0.003


class CloudPulseMonitor:
    """Fetches live metrics from AWS and calculates carbon footprint."""

    def __init__(self, region: str = "us-east-1"):
        self.region = region
        self.cw = boto3.client("cloudwatch", region_name=region)
        self.ec2 = boto3.client("ec2", region_name=region)
        self.ai = Anthropic()

    # ------------------------------------------------------------------
    # 1. Fetch EC2 CPU utilization from CloudWatch
    # ------------------------------------------------------------------
    def get_cpu_metrics(self, instance_id: str, hours: int = 1) -> float:
        """Returns average CPU % for the last N hours."""
        response = self.cw.get_metric_statistics(
            Namespace="AWS/EC2",
            MetricName="CPUUtilization",
            Dimensions=[{"Name": "InstanceId", "Value": instance_id}],
            StartTime=datetime.utcnow() - timedelta(hours=hours),
            EndTime=datetime.utcnow(),
            Period=3600,
            Statistics=["Average"],
        )
        datapoints = response.get("Datapoints", [])
        if not datapoints:
            return 0.0
        return sum(d["Average"] for d in datapoints) / len(datapoints)

    # ------------------------------------------------------------------
    # 2. Convert CPU% → kWh → kg CO2
    # ------------------------------------------------------------------
    def cpu_to_carbon(self, cpu_pct: float, vcpus: int, hours: float = 1.0) -> dict:
        """
        Returns energy consumption and carbon footprint.
        Formula: kWh = WATTS_PER_VCPU * vCPUs * (cpu_pct/100) * hours
        """
        kwh = WATTS_PER_VCPU * vcpus * (cpu_pct / 100) * hours
        co2_kg = kwh * CARBON_FACTOR.get(self.region, 0.4)
        return {
            "kwh": round(kwh, 4),
            "co2_kg": round(co2_kg, 4),
            "region": self.region,
            "carbon_factor": CARBON_FACTOR.get(self.region, 0.4),
        }

    # ------------------------------------------------------------------
    # 3. List all running instances + calculate their carbon
    # ------------------------------------------------------------------
    def scan_all_instances(self) -> list[dict]:
        """Returns a list of instances with their carbon footprint."""
        paginator = self.ec2.get_paginator("describe_instances")
        results = []

        for page in paginator.paginate(
            Filters=[{"Name": "instance-state-name", "Values": ["running"]}]
        ):
            for reservation in page["Reservations"]:
                for inst in reservation["Instances"]:
                    iid = inst["InstanceId"]
                    itype = inst["InstanceType"]
                    vcpus = inst.get("CpuOptions", {}).get("CoreCount", 2) * \
                            inst.get("CpuOptions", {}).get("ThreadsPerCore", 2)

                    cpu_pct = self.get_cpu_metrics(iid)
                    carbon = self.cpu_to_carbon(cpu_pct, vcpus)

                    # Tag: get Name if exists
                    name = next(
                        (t["Value"] for t in inst.get("Tags", []) if t["Key"] == "Name"),
                        iid,
                    )

                    results.append({
                        "instance_id": iid,
                        "name": name,
                        "type": itype,
                        "vcpus": vcpus,
                        "cpu_pct": round(cpu_pct, 1),
                        "kwh_per_hour": carbon["kwh"],
                        "co2_kg_per_hour": carbon["co2_kg"],
                        "is_idle": cpu_pct < 5.0,
                    })

        return results

    # ------------------------------------------------------------------
    # 4. Claude AI — get optimization recommendations
    # ------------------------------------------------------------------
    def ai_recommend(self, usage_summary: dict) -> str:
        """
        Sends usage data to Claude Sonnet and returns plain-English
        optimization steps ranked by CO2/cost impact.
        """
        prompt = f"""
You are a cloud sustainability expert. Analyze this AWS usage data and give
3-5 specific, actionable recommendations to reduce carbon emissions and cost.
For each recommendation include: action, estimated CO2 saving (kg/day), 
estimated cost saving ($/month), and implementation command.

Usage data:
{json.dumps(usage_summary, indent=2)}

Respond in JSON with this structure:
{{
  "total_co2_kg_day": <number>,
  "recommendations": [
    {{
      "priority": 1,
      "action": "...",
      "reason": "...",
      "co2_saving_kg_day": <number>,
      "cost_saving_usd_month": <number>,
      "command": "aws ..."
    }}
  ]
}}
"""
        response = self.ai.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text

    # ------------------------------------------------------------------
    # 5. Green region router — find lowest-carbon alternative
    # ------------------------------------------------------------------
    def suggest_green_region(self, current_region: str) -> dict:
        """Returns the lowest-carbon AWS region for your workload."""
        sorted_regions = sorted(CARBON_FACTOR.items(), key=lambda x: x[1])
        current_factor = CARBON_FACTOR.get(current_region, 0.4)
        best_region, best_factor = sorted_regions[0]
        savings_pct = round((1 - best_factor / current_factor) * 100, 1)

        return {
            "current_region": current_region,
            "current_factor_kg_kwh": current_factor,
            "recommended_region": best_region,
            "recommended_factor_kg_kwh": best_factor,
            "co2_reduction_pct": savings_pct,
            "note": f"Migrating to {best_region} would cut emissions by {savings_pct}%",
        }


# ------------------------------------------------------------------
# Quick CLI demo (runs without real AWS creds using mock data)
# ------------------------------------------------------------------
if __name__ == "__main__":
    print("=" * 60)
    print("CloudPulse — Carbon Footprint Demo (mock data)")
    print("=" * 60)

    monitor = CloudPulseMonitor(region="us-east-1")

    # Mock usage summary (replace with monitor.scan_all_instances() in prod)
    mock_summary = {
        "region": "us-east-1",
        "timestamp": datetime.utcnow().isoformat(),
        "instances": [
            {"id": "i-001", "type": "t3.large", "cpu_pct": 3.2, "co2_kg_hr": 0.0018, "idle": True},
            {"id": "i-002", "type": "m5.xlarge", "cpu_pct": 78.4, "co2_kg_hr": 0.0124, "idle": False},
            {"id": "i-003", "type": "t3.medium", "cpu_pct": 1.1, "co2_kg_hr": 0.0009, "idle": True},
        ],
        "total_co2_kg_hr": 0.0151,
        "total_co2_kg_day": 0.362,
    }

    print("\n📊 Usage Summary:")
    print(json.dumps(mock_summary, indent=2))

    print("\n🌍 Green Region Suggestion:")
    suggestion = monitor.suggest_green_region("us-east-1")
    print(json.dumps(suggestion, indent=2))

    print("\n🤖 Getting AI recommendations...")
    try:
        recs = monitor.ai_recommend(mock_summary)
        print(recs)
    except Exception as e:
        print(f"[Set ANTHROPIC_API_KEY to enable AI recommendations]\nError: {e}")
