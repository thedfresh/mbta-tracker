import os
import time
import json
import requests
from datetime import datetime, timezone

BASE_URL = "https://api-v3.mbta.com"
ROUTE = "109"
INTERVAL = 60  # seconds

API_KEY = os.environ.get("MBTA_API_KEY")
if not API_KEY:
    raise RuntimeError("MBTA_API_KEY not set")

HEADERS = {
    "x-api-key": API_KEY
}

def fetch(endpoint):
    r = requests.get(f"{BASE_URL}{endpoint}", headers=HEADERS, timeout=10)
    r.raise_for_status()
    return r.json()

def log_jsonl(filename, record):
    with open(filename, "a") as f:
        f.write(json.dumps(record) + "\n")

def main():
    while True:
        ts = datetime.now(timezone.utc).isoformat()

        try:
            predictions = fetch(
                f"/predictions?filter[route]={ROUTE}&include=vehicle,trip"
            )
            vehicles = fetch(
                f"/vehicles?filter[route]={ROUTE}"
            )

            log_jsonl(
                "logs/predictions.jsonl",
                {"timestamp": ts, "data": predictions}
            )
            log_jsonl(
                "logs/vehicles.jsonl",
                {"timestamp": ts, "data": vehicles}
            )

        except Exception as e:
            log_jsonl(
                "logs/errors.jsonl",
                {"timestamp": ts, "error": str(e)}
            )

        time.sleep(INTERVAL)

if __name__ == "__main__":
    main()
