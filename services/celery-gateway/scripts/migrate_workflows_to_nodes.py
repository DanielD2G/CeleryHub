#!/usr/bin/env python3
"""Export step-model workflows and re-import them as node-model workflows.

The 1-node-1-task migration (alembic 0004) drops ``workflow_steps`` without
copying it, and the Postgres migration creates its schema from scratch, so
workflows defined on the old deployment do not survive either step. This
script bridges both: it reads the definitions over HTTP from a running
step-model instance, expands every step into one node per task name, and
writes a JSON file that can later be POSTed to a node-model instance.

Run ``export`` BEFORE deploying the Postgres PR, and ``import`` after the
node-model PR is deployed.

    ./scripts/migrate_workflows_to_nodes.py export http://buddy1:3000 -o backup.json
    ./scripts/migrate_workflows_to_nodes.py import http://buddy1:3000 -i backup.json
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
import uuid

# Canvas layout constants; mirrors the spacing the editor uses for new nodes.
_COLUMN_WIDTH = 320.0
_ROW_HEIGHT = 120.0

_TIMEOUT = 30


def _get(base: str, path: str) -> object:
    with urllib.request.urlopen(f"{base.rstrip('/')}{path}", timeout=_TIMEOUT) as r:
        return json.loads(r.read())


def _post(base: str, path: str, payload: dict) -> dict:
    req = urllib.request.Request(
        f"{base.rstrip('/')}{path}",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
        return json.loads(r.read())


def _loads(value: object, fallback: object) -> object:
    """Old rows store JSON as strings; tolerate nulls and already-parsed values."""
    if value is None:
        return fallback
    if isinstance(value, str):
        return json.loads(value) if value.strip() else fallback
    return value


def _step_levels(steps: list[dict]) -> dict[str, int]:
    """Longest-path depth per step, used only to lay nodes out left to right."""
    by_id = {s["id"]: s for s in steps}
    levels: dict[str, int] = {}

    def depth(step_id: str, seen: frozenset[str]) -> int:
        if step_id in levels:
            return levels[step_id]
        if step_id in seen or step_id not in by_id:
            return 0
        deps = _loads(by_id[step_id].get("dependsOn"), [])
        value = 1 + max((depth(d, seen | {step_id}) for d in deps), default=-1)
        levels[step_id] = value
        return value

    for step in steps:
        depth(step["id"], frozenset())
    return levels


def _expand(workflow: dict) -> dict:
    """Turn one step-model workflow into a node-model create payload."""
    steps = workflow.get("steps") or []
    levels = _step_levels(steps)

    # One node per (step, task_name). Downstream steps depend on every node the
    # upstream step expanded into, which preserves the original condition
    # semantics: all_completed over N sibling nodes == all_completed over a
    # step that ran N tasks.
    nodes_by_step: dict[str, list[str]] = {}
    nodes: list[dict] = []
    row_cursor: dict[int, int] = {}

    for step in steps:
        task_names = _loads(step.get("taskNames"), [])
        if isinstance(task_names, str):
            task_names = [task_names]
        level = levels.get(step["id"], 0)
        ids: list[str] = []
        for task_name in task_names:
            row = row_cursor.get(level, 0)
            row_cursor[level] = row + 1
            node_id = str(uuid.uuid4())
            ids.append(node_id)
            nodes.append(
                {
                    "id": node_id,
                    # Single-task steps keep their label; fan-out steps would
                    # otherwise produce N identically named nodes.
                    "label": step["label"]
                    if len(task_names) == 1
                    else f"{step['label']} — {task_name}",
                    "taskName": task_name,
                    "args": step.get("args"),
                    "kwargs": step.get("kwargs"),
                    "queue": step.get("queue"),
                    "dependsOn": [],
                    "condition": step.get("condition") or "all_succeeded",
                    "timeoutSeconds": step.get("timeoutSeconds"),
                    "positionX": level * _COLUMN_WIDTH,
                    "positionY": row * _ROW_HEIGHT,
                }
            )
        nodes_by_step[step["id"]] = ids

    index = {n["id"]: n for n in nodes}
    for step in steps:
        deps = _loads(step.get("dependsOn"), [])
        resolved = [nid for dep in deps for nid in nodes_by_step.get(dep, [])]
        for node_id in nodes_by_step[step["id"]]:
            index[node_id]["dependsOn"] = list(resolved)

    return {
        "name": workflow["name"],
        "description": workflow.get("description"),
        "scheduleType": workflow.get("scheduleType", "none"),
        "intervalSeconds": workflow.get("intervalSeconds"),
        "cronExpression": workflow.get("cronExpression"),
        "enabled": workflow.get("enabled", True),
        "maxRunCount": workflow.get("maxRunCount"),
        "nodes": nodes,
    }


def _export(base: str, out_path: str) -> int:
    summaries = _get(base, "/api/workflows")
    assert isinstance(summaries, list)
    payloads = []
    for summary in summaries:
        detail = _get(base, f"/api/workflows/{summary['id']}")
        assert isinstance(detail, dict)
        if "steps" not in detail:
            print(
                f"! {detail['name']}: no 'steps' key — instance already on the "
                f"node model, skipping",
                file=sys.stderr,
            )
            continue
        payload = _expand(detail)
        payloads.append(payload)
        print(
            f"  {payload['name']}: {len(detail['steps'])} step(s) -> "
            f"{len(payload['nodes'])} node(s)"
        )

    with open(out_path, "w") as fh:
        json.dump({"workflows": payloads}, fh, indent=2)
    print(f"\nWrote {len(payloads)} workflow(s) to {out_path}")
    return 0


def _import(base: str, in_path: str, dry_run: bool) -> int:
    with open(in_path) as fh:
        data = json.load(fh)
    payloads = data["workflows"]

    existing = _get(base, "/api/workflows")
    assert isinstance(existing, list)
    taken = {w["name"] for w in existing}

    failures = 0
    for payload in payloads:
        if payload["name"] in taken:
            print(f"! {payload['name']}: already exists on target, skipping")
            continue
        if dry_run:
            print(f"  would create {payload['name']} ({len(payload['nodes'])} nodes)")
            continue
        try:
            created = _post(base, "/api/workflows", payload)
            print(f"  created {created['name']} -> {created['id']}")
        except urllib.error.HTTPError as exc:
            failures += 1
            print(
                f"! {payload['name']}: {exc.code} {exc.read().decode()[:300]}",
                file=sys.stderr,
            )
    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    export = sub.add_parser("export", help="read a step-model instance")
    export.add_argument("base_url")
    export.add_argument("-o", "--output", default="workflows-backup.json")

    imp = sub.add_parser("import", help="write to a node-model instance")
    imp.add_argument("base_url")
    imp.add_argument("-i", "--input", default="workflows-backup.json")
    imp.add_argument("--dry-run", action="store_true")

    args = parser.parse_args()
    if args.command == "export":
        return _export(args.base_url, args.output)
    return _import(args.base_url, args.input, args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
