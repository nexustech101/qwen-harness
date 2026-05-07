from agent.core.dispatcher import Dispatcher
from agent.core.orchestrator import Orchestrator
from agent.core.state import TaskSpec


def _spec(task_id: str, depends_on=None):
    return TaskSpec(
        task_id=task_id,
        goal=f"goal-{task_id}",
        agent_name=f"agent-{task_id}",
        depends_on=depends_on or [],
    )


def test_dispatcher_topological_sort_uses_task_ids():
    specs = [
        _spec("task-c", depends_on=["task-b"]),
        _spec("task-a"),
        _spec("task-b", depends_on=["task-a"]),
    ]

    ordered = Dispatcher._topological_sort(specs)
    ids = [s.task_id for s in ordered]
    assert ids.index("task-a") < ids.index("task-b") < ids.index("task-c")


def test_rule_router_decomposes_for_parallel_multi_domain_prompt():
    orch = Orchestrator(use_dispatch=True)
    mode, reason, specs = orch._rule_route(
        "Create agents to work in parallel: one for frontend React UI and one for backend API changes."
    )

    assert mode == "decompose"
    assert len(specs) >= 2
    assert all(s.task_id for s in specs)


def test_rule_router_defaults_to_direct_for_simple_prompt():
    orch = Orchestrator(use_dispatch=True)
    mode, _reason, specs = orch._rule_route("Fix typo in app/config.py")

    assert mode == "direct"
    assert specs == []
