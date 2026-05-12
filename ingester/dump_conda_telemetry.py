#!/usr/bin/env python3
import argparse
import datetime
import json
from pathlib import Path


def iter_import_files(source_dir: Path):
    for path in source_dir.glob("*/*/imports.jsonl"):
        if path.is_file():
            yield path


def main():
    parser = argparse.ArgumentParser(
        description="Flatten xp65 conda telemetry imports.jsonl files into one ndjson dump"
    )
    parser.add_argument("--source-dir", required=True, help="Root directory containing env/user/imports.jsonl")
    parser.add_argument("--output-file", required=True, help="Output ndjson file")
    parser.add_argument(
        "--max-files",
        type=int,
        default=0,
        help="Optional cap on number of imports.jsonl files processed (0 means all)",
    )
    parser.add_argument(
        "--allow-missing-source",
        action="store_true",
        help="Do not fail if source-dir does not exist",
    )
    args = parser.parse_args()

    source_dir = Path(args.source_dir)
    output_file = Path(args.output_file)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    if not source_dir.exists():
        if args.allow_missing_source:
            with output_file.open("w", encoding="utf-8") as fh:
                fh.write("")
            print(f"source directory not found, wrote empty dump: {source_dir}")
            return
        raise FileNotFoundError(f"source directory not found: {source_dir}")

    import_files = sorted(iter_import_files(source_dir))
    if args.max_files > 0:
        import_files = import_files[: args.max_files]

    stats = {
        "files": 0,
        "events": 0,
        "bad_lines": 0,
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }

    with output_file.open("w", encoding="utf-8") as out_fh:
        for imports_file in import_files:
            stats["files"] += 1
            rel = imports_file.relative_to(source_dir)
            env_name = rel.parts[0]
            user_from_path = rel.parts[1]

            with imports_file.open("r", encoding="utf-8") as in_fh:
                for line_no, raw in enumerate(in_fh, start=1):
                    raw = raw.strip()
                    if not raw:
                        continue
                    try:
                        payload = json.loads(raw)
                    except json.JSONDecodeError:
                        stats["bad_lines"] += 1
                        continue

                    packages = payload.get("packages", [])
                    if not isinstance(packages, list):
                        packages = []

                    event = {
                        "env_name": env_name,
                        "user_id": payload.get("user") or user_from_path,
                        "timestamp": payload.get("timestamp"),
                        "pid": payload.get("pid"),
                        "sys_executable": payload.get("sys_executable"),
                        "sys_prefix": payload.get("sys_prefix"),
                        "packages": packages,
                        "source_file": str(imports_file),
                        "source_line": line_no,
                    }
                    out_fh.write(json.dumps(event, sort_keys=True))
                    out_fh.write("\n")
                    stats["events"] += 1

    print(json.dumps(stats, sort_keys=True))


if __name__ == "__main__":
    main()
