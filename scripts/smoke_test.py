import argparse
import sys
import time
from pathlib import Path

import httpx


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test the transaction processing API.")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--csv", default="transactions.csv")
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args()

    csv_path = Path(args.csv)
    if not csv_path.exists():
        print(f"CSV file not found: {csv_path}", file=sys.stderr)
        return 1

    with httpx.Client(base_url=args.base_url, timeout=20) as client:
        health = client.get("/health")
        health.raise_for_status()

        with csv_path.open("rb") as handle:
            upload = client.post("/jobs/upload", files={"file": (csv_path.name, handle, "text/csv")})
        upload.raise_for_status()
        job_id = upload.json()["job_id"]

        deadline = time.time() + args.timeout
        status_payload = {}
        while time.time() < deadline:
            status_response = client.get(f"/jobs/{job_id}/status")
            status_response.raise_for_status()
            status_payload = status_response.json()
            if status_payload["status"] in {"completed", "failed"}:
                break
            time.sleep(2)

        if status_payload.get("status") != "completed":
            print(f"Job did not complete successfully: {status_payload}", file=sys.stderr)
            return 1

        results = client.get(f"/jobs/{job_id}/results")
        results.raise_for_status()
        result_payload = results.json()

    print(
        {
            "job_id": job_id,
            "status": status_payload["status"],
            "cleaned_transactions": len(result_payload["cleaned_transactions"]),
            "anomalies": len(result_payload["flagged_anomalies"]),
            "risk_level": result_payload["llm_summary"]["risk_level"],
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
