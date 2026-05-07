from agent.prompts.system_prompts import (
    main_system_prompt,
    orchestrator_prompt,
    sub_agent_prompt,
)


def test_main_prompt_includes_workspace_selection_fields():
    prompt = main_system_prompt(
        tools_desc="- read_file",
        project_root="/repo",
        project_name="repo",
        workspace_key="repo-abc123",
        workspace_root="/central/workspaces/repo-abc123",
    )

    assert "/repo" in prompt
    assert "repo-abc123" in prompt
    assert "/central/workspaces/repo-abc123" in prompt
    assert "{project_name}" not in prompt


def test_orchestrator_prompt_renders_new_workspace_placeholders():
    prompt = orchestrator_prompt(
        tools_desc="- read_file",
        workspace_context="(ctx)",
        project_root="/repo",
        project_name="repo",
        workspace_key="repo-abc123",
        workspace_root="/central/workspaces/repo-abc123",
    )

    assert "(ctx)" in prompt
    assert "/repo" in prompt
    assert "repo-abc123" in prompt
    assert "{workspace_root}" not in prompt


def test_sub_agent_prompt_renders_workspace_metadata():
    prompt = sub_agent_prompt(
        task_spec="task body",
        tools_desc="- read_file",
        agent_name="backend-agent",
        project_spec="proj",
        directives="dir",
        inherited_context="ctx",
        project_root="/repo",
        project_name="repo",
        workspace_key="repo-abc123",
        workspace_root="/central/workspaces/repo-abc123",
    )

    assert "backend-agent" in prompt
    assert "/repo" in prompt
    assert "repo-abc123" in prompt
    assert "{workspace_key}" not in prompt
