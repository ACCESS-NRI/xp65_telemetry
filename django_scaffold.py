"""Minimal Django scaffold for xp65 telemetry ingestion.

This file is intentionally standalone so it can be copied into a Django app and
used as a starting point for:

- ORM models matching the current telemetry tables
- a small ingestion service that validates/filter-normalises package payloads
- a Django view that accepts batched JSON events and writes them via the ORM

It is not wired into this repository's current Docker stack; it's a scaffold for
future migration work.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import sys
from typing import Iterable

from django.db import models, transaction
from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST


STDLIB_MODULES = set(getattr(sys, "stdlib_module_names", []))
VERSION_SPLIT_RE = re.compile(r"[<>=!~ ]")


def normalize_package_name(raw_pkg: str | None) -> str | None:
    if not isinstance(raw_pkg, str):
        return None
    pkg = raw_pkg.strip()
    if not pkg:
        return None
    top_level = pkg.split(".", 1)[0]
    if top_level.startswith("_"):
        return None
    if top_level in STDLIB_MODULES:
        return None
    return top_level


class CondaEnvSession(models.Model):
    event_hash = models.TextField(primary_key=True)
    event_time = models.DateTimeField()
    env_name = models.TextField()
    user_id = models.TextField()
    pid = models.BigIntegerField(null=True, blank=True)
    sys_executable = models.TextField(null=True, blank=True)
    sys_prefix = models.TextField(null=True, blank=True)
    source_file = models.TextField(null=True, blank=True)
    source_line = models.IntegerField(null=True, blank=True)
    inserted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "conda_env_sessions"
        indexes = [
            models.Index(fields=["event_time"], name="idx_conda_env_sessions_time"),
            models.Index(fields=["env_name", "event_time"], name="idx_conda_env_sessions_env_time"),
            models.Index(fields=["user_id", "event_time"], name="idx_conda_env_sessions_user_time"),
        ]


class CondaEnvPackage(models.Model):
    session = models.ForeignKey(
        CondaEnvSession,
        on_delete=models.CASCADE,
        db_column="event_hash",
        related_name="packages",
    )
    package_name = models.TextField()
    inserted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "conda_env_packages"
        constraints = [
            models.UniqueConstraint(fields=["session", "package_name"], name="conda_env_packages_pkey")
        ]
        indexes = [models.Index(fields=["package_name"], name="idx_conda_env_packages_name")]


class CondaEnvIngestRun(models.Model):
    run_at = models.DateTimeField(auto_now_add=True)
    input_file = models.TextField()
    rows_in_file = models.IntegerField()
    rows_parsed = models.IntegerField()
    bad_rows = models.IntegerField()

    class Meta:
        db_table = "conda_env_ingest_runs"


def build_event_hash(*, day: str, env_name: str | None, user_id: str | None) -> str:
    payload = {"day": day, "env_name": env_name, "user_id": user_id}
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def parse_event(payload: dict) -> tuple[CondaEnvSession, list[CondaEnvPackage]] | None:
    raw_ts = str(payload.get("timestamp") or "").strip()
    if not raw_ts:
        return None

    ts = dt.datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
    day = ts.astimezone(dt.timezone.utc).date().isoformat()
    env_name = payload.get("env_name")
    user_id = payload.get("user_id")
    event_hash = build_event_hash(day=day, env_name=env_name, user_id=user_id)

    session = CondaEnvSession(
        event_hash=event_hash,
        event_time=dt.datetime.fromisoformat(f"{day}T00:00:00+00:00"),
        env_name=env_name,
        user_id=user_id,
        pid=payload.get("pid"),
        sys_executable=payload.get("sys_executable"),
        sys_prefix=payload.get("sys_prefix"),
        source_file=payload.get("source_file"),
        source_line=payload.get("source_line"),
    )

    seen = set()
    package_rows: list[CondaEnvPackage] = []
    for raw_pkg in payload.get("packages", []):
        normalized = normalize_package_name(raw_pkg)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        package_rows.append(CondaEnvPackage(session=session, package_name=normalized))

    return session, package_rows


def ingest_payloads(payloads: Iterable[dict], *, input_file: str = "django-endpoint") -> dict:
    sessions: list[CondaEnvSession] = []
    package_rows: list[CondaEnvPackage] = []
    rows_seen = 0
    bad_rows = 0

    for payload in payloads:
        rows_seen += 1
        try:
            parsed = parse_event(payload)
        except Exception:
            bad_rows += 1
            continue
        if parsed is None:
            bad_rows += 1
            continue
        session, packages = parsed
        sessions.append(session)
        package_rows.extend(packages)

    with transaction.atomic():
        CondaEnvSession.objects.bulk_create(
            sessions,
            ignore_conflicts=True,
            batch_size=500,
        )
        CondaEnvPackage.objects.bulk_create(
            package_rows,
            ignore_conflicts=True,
            batch_size=500,
        )
        CondaEnvIngestRun.objects.create(
            input_file=input_file,
            rows_in_file=rows_seen,
            rows_parsed=len(sessions),
            bad_rows=bad_rows,
        )

    return {
        "rows_in_file": rows_seen,
        "rows_parsed": len(sessions),
        "packages_inserted": len(package_rows),
        "bad_rows": bad_rows,
    }


@csrf_exempt
@require_POST
def ingest_telemetry_view(request: HttpRequest) -> JsonResponse:
    """Example Django endpoint.

    Expected body:
    {
      "events": [
        {
          "env_name": "analysis3-25.04",
          "user_id": "abc123",
          "timestamp": "2026-05-20T04:12:00Z",
          "pid": 123,
          "sys_executable": "/path/python",
          "sys_prefix": "/path/env",
          "packages": ["xarray", "numpy.linalg"],
          "source_file": "/logs/env/user/imports.jsonl",
          "source_line": 42
        }
      ]
    }
    """
    try:
        body = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        return JsonResponse({"error": "invalid JSON body"}, status=400)

    events = body.get("events")
    if not isinstance(events, list):
        return JsonResponse({"error": "body must contain an 'events' list"}, status=400)

    summary = ingest_payloads(events)
    return JsonResponse(summary, status=202)
