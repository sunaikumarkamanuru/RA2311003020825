import os
import sys
import time
from typing import Any, Dict, List

import requests
from flask import Flask, jsonify, request

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from logging_middleware import Log


DEPOT_API = os.getenv(
    "DEPOT_API",
    "http://20.244.56.144/evaluation-service/depots",
)
VEHICLE_API = os.getenv(
    "VEHICLE_API",
    "http://20.244.56.144/evaluation-service/vehicles",
)

app = Flask(__name__)


def auth_headers() -> Dict[str, str]:
    token = request.headers.get("Authorization", "") or os.getenv("AFFORD_ACCESS_TOKEN", "")
    if token.startswith("Bearer "):
        return {"Authorization": token}
    if token:
        return {"Authorization": f"Bearer {token}"}
    return {}


def fetch_json(url: str, key: str) -> List[Dict[str, Any]]:
    Log("backend", "info", "service", f"Fetching {key} from evaluation service")
    response = requests.get(url, headers=auth_headers(), timeout=10)
    response.raise_for_status()
    data = response.json()
    return data.get(key, [])


def select_tasks(tasks: List[Dict[str, Any]], max_hours: int) -> List[Dict[str, Any]]:
    dp = [0] * (max_hours + 1)
    chosen: List[List[int]] = [[] for _ in range(max_hours + 1)]

    for index, task in enumerate(tasks):
        duration = int(task.get("Duration", 0))
        impact = int(task.get("Impact", 0))

        if duration <= 0 or duration > max_hours:
            continue

        for hours in range(max_hours, duration - 1, -1):
            candidate_score = dp[hours - duration] + impact
            if candidate_score > dp[hours]:
                dp[hours] = candidate_score
                chosen[hours] = chosen[hours - duration] + [index]

    return [tasks[index] for index in chosen[max_hours]]


def build_schedule() -> Dict[str, Any]:
    depots = fetch_json(DEPOT_API, "depots")
    vehicles = fetch_json(VEHICLE_API, "vehicles")

    schedules = []
    for depot in depots:
        depot_id = depot.get("ID")
        budget = int(depot.get("MechanicHours", 0))
        selected = select_tasks(vehicles, budget)
        total_time = sum(int(task.get("Duration", 0)) for task in selected)
        total_impact = sum(int(task.get("Impact", 0)) for task in selected)

        schedules.append(
            {
                "depotId": depot_id,
                "mechanicHours": budget,
                "usedHours": total_time,
                "unusedHours": budget - total_time,
                "totalImpact": total_impact,
                "selectedTaskCount": len(selected),
                "selectedTasks": selected,
            }
        )

    return {
        "depotCount": len(depots),
        "vehicleTaskCount": len(vehicles),
        "schedules": schedules,
    }


@app.get("/")
def health():
    return jsonify(
        {
            "service": "vehicle-maintenance-scheduler",
            "status": "running",
            "endpoints": ["/schedule"],
        }
    )


@app.get("/schedule")
def schedule():
    started = time.perf_counter()
    try:
        result = build_schedule()
        result["responseTimeMs"] = round((time.perf_counter() - started) * 1000, 2)
        Log("backend", "info", "controller", "Vehicle schedule generated successfully")
        return jsonify(result), 200
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else 502
        Log("backend", "error", "service", f"Evaluation API returned HTTP {status}")
        return jsonify({"error": "failed to fetch evaluation data", "status": status}), status
    except Exception as exc:
        Log("backend", "fatal", "handler", f"Vehicle scheduler failed: {exc}")
        return jsonify({"error": "internal scheduler error"}), 500


if __name__ == "__main__":
    app.run(debug=True, port=5001)
