#!/usr/bin/env python3
"""Tiny demo client for posting telemetry events to the example Django endpoint."""

from __future__ import annotations

import argparse
import json
import urllib.request
from pathlib import Path


def iter_events(input_path: Path):
    with input_path.open("r", encoding="utf-8") as fh:
        for line_no, raw in enumerate(fh, start=1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                yield json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSON on line {line_no}: {exc}") from exc


def batched(items, batch_size: int):
    batch = []
    for item in items:
        batch.append(item)
        if len(batch) >= batch_size:
            yield batch
            batch = []
    if batch:
        yield batch


def post_batch(endpoint: str, batch: list[dict], timeout: int):
    payload = json.dumps({"events": batch}).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read().decode("utf-8")
        return response.status, body


def main():
    parser = argparse.ArgumentParser(description="POST telemetry NDJSON to a Django ingestion endpoint")
    parser.add_argument("endpoint", help="Django ingestion endpoint URL")
    parser.add_argument("input_file", help="NDJSON file containing telemetry events")
    parser.add_argument("--batch-size", type=int, default=100, help="Events per POST request")
    parser.add_argument("--timeout", type=int, default=30, help="HTTP timeout in seconds")
    args = parser.parse_args()

    input_path = Path(args.input_file)
    events = iter_events(input_path)
    total_sent = 0

    for batch_no, batch in enumerate(batched(events, args.batch_size), start=1):
        status, body = post_batch(args.endpoint, batch, args.timeout)
        total_sent += len(batch)
        print(json.dumps({
            "batch": batch_no,
            "status": status,
            "events_sent": len(batch),
            "total_sent": total_sent,
            "response": body,
        }))


if __name__ == "__main__":
    main()
