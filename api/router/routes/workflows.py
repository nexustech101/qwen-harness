"""Workflow routes — CRUD for workflows and their run history."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api.db.models import Workflow, WorkflowRun

router = APIRouter(tags=["workflows"])


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ── Schemas ────────────────────────────────────────────────────────────────────

class WorkflowCreate(BaseModel):
    name: str
    description: str = ""
    definition: dict[str, Any] = {}
    enabled: bool = True


class WorkflowUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    definition: dict[str, Any] | None = None
    enabled: bool | None = None


# ── Workflow CRUD ──────────────────────────────────────────────────────────────

@router.post("/workflows", status_code=201)
async def create_workflow(req: WorkflowCreate) -> dict[str, Any]:
    now = _utc_now()
    wf = Workflow.objects.create(
        id=str(uuid.uuid4()),
        name=req.name,
        description=req.description,
        definition=json.dumps(req.definition),
        enabled=req.enabled,
        created_at=now,
        updated_at=now,
    )
    return _wf_dict(wf)


@router.get("/workflows")
async def list_workflows() -> list[dict[str, Any]]:
    rows = Workflow.objects.filter(order_by="-created_at")
    return [_wf_dict(wf) for wf in rows]


@router.get("/workflows/{workflow_id}")
async def get_workflow(workflow_id: str) -> dict[str, Any]:
    try:
        wf = Workflow.objects.require(id=workflow_id)
    except Exception:
        raise HTTPException(404, "Workflow not found")
    return _wf_dict(wf)


@router.patch("/workflows/{workflow_id}")
async def update_workflow(workflow_id: str, req: WorkflowUpdate) -> dict[str, Any]:
    try:
        wf = Workflow.objects.require(id=workflow_id)
    except Exception:
        raise HTTPException(404, "Workflow not found")

    if req.name is not None:
        wf.name = req.name
    if req.description is not None:
        wf.description = req.description
    if req.definition is not None:
        wf.definition = json.dumps(req.definition)
    if req.enabled is not None:
        wf.enabled = req.enabled
    wf.updated_at = _utc_now()
    wf.save()
    return _wf_dict(wf)


@router.delete("/workflows/{workflow_id}", status_code=204)
async def delete_workflow(workflow_id: str) -> None:
    try:
        Workflow.objects.require(id=workflow_id)
    except Exception:
        raise HTTPException(404, "Workflow not found")
    WorkflowRun.objects.delete_where(workflow_id=workflow_id)
    Workflow.objects.delete(workflow_id)


# ── Workflow runs ──────────────────────────────────────────────────────────────

@router.get("/workflows/{workflow_id}/runs")
async def list_runs(workflow_id: str) -> list[dict[str, Any]]:
    try:
        Workflow.objects.require(id=workflow_id)
    except Exception:
        raise HTTPException(404, "Workflow not found")
    rows = WorkflowRun.objects.filter(workflow_id=workflow_id, order_by="-started_at")
    return [_run_dict(r) for r in rows]


def _topo_sort_steps(steps: list[dict], edges: list[dict]) -> list[dict]:
    """Topological sort of steps via Kahn's algorithm."""
    if not steps:
        return []
    step_map = {s["id"]: s for s in steps}
    out_edges: dict[str, list[str]] = {}
    in_degree: dict[str, int] = {s["id"]: 0 for s in steps}
    for edge in edges:
        src = edge.get("source", "")
        tgt = edge.get("target", "")
        if src in step_map and tgt in step_map:
            out_edges.setdefault(src, []).append(tgt)
            in_degree[tgt] = in_degree.get(tgt, 0) + 1
    queue = [sid for sid, deg in in_degree.items() if deg == 0]
    result: list[dict] = []
    visited: set[str] = set()
    while queue:
        node_id = queue.pop(0)
        result.append(step_map[node_id])
        visited.add(node_id)
        for neighbor in out_edges.get(node_id, []):
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)
    # Append any disconnected nodes
    result += [s for s in steps if s["id"] not in visited]
    return result


@router.post("/workflows/{workflow_id}/execute", status_code=202)
async def execute_workflow(workflow_id: str) -> dict[str, Any]:
    """Create a WorkflowRun and a ChatSession for executing the workflow."""
    try:
        wf = Workflow.objects.require(id=workflow_id)
    except Exception:
        raise HTTPException(404, "Workflow not found")

    from api.db.models import ChatSession

    definition = json.loads(wf.definition) if wf.definition else {}
    steps = definition.get("steps", [])
    edges = definition.get("edges", [])
    ordered = _topo_sort_steps(steps, edges)

    now = _utc_now()
    run = WorkflowRun.objects.create(
        id=str(uuid.uuid4()),
        workflow_id=workflow_id,
        status="pending",
        started_at=now,
        finished_at=None,
    )

    session_id = str(uuid.uuid4())
    ChatSession.objects.create(
        id=session_id,
        title=f"Workflow: {wf.name}",
        model="",
        status="idle",
        created_at=now,
        updated_at=now,
    )

    run.result = json.dumps({"session_id": session_id, "steps": len(ordered)})
    run.save()

    return {
        "run_id": run.id,
        "session_id": session_id,
        "steps": [
            {"id": s.get("id", ""), "title": s.get("title", ""), "prompt": s.get("prompt", "")}
            for s in ordered
        ],
    }


# ── Helpers ────────────────────────────────────────────────────────────────────

def _wf_dict(wf: Workflow) -> dict[str, Any]:
    return {
        "id": wf.id,
        "name": wf.name,
        "description": wf.description,
        "definition": json.loads(wf.definition) if wf.definition else {},
        "enabled": wf.enabled,
        "created_at": wf.created_at,
        "updated_at": wf.updated_at,
    }


def _run_dict(r: WorkflowRun) -> dict[str, Any]:
    return {
        "id": r.id,
        "workflow_id": r.workflow_id,
        "status": r.status,
        "result": json.loads(r.result) if r.result else None,
        "started_at": r.started_at,
        "finished_at": r.finished_at,
    }
