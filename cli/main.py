from __future__ import annotations

from cli.commands.billing import cli as billing_cli
from cli.commands.ops import cli as ops_cli
from cli.commands.sessions import cli as sessions_cli
from cli.commands.users import cli as users_cli

from registers.cli import CommandRegistry


registry = CommandRegistry()
try:
    registry.register_plugin(billing_cli)
    registry.register_plugin(users_cli)
    registry.register_plugin(ops_cli)
    registry.register_plugin(sessions_cli)
except Exception as exc:
    raise SystemError(f"Failed to load CLI plugins: {exc}")


def main() -> None:
    try:
        return registry.run(
            print_result=True,
            shell_title="User Account Admin CLI",
            shell_description="Manage user accounts and auth sessions.",
            shell_usage=True,
        )
    except Exception as exc:
        raise SystemError(f"CLI execution failed: {exc}") from exc


if __name__ == "__main__":
    main()
