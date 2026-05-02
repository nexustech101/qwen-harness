from __future__ import annotations

import json

from registers.cli import CommandRegistry
from cli.commands.billing import cli as billing_cli
from cli.commands.ops import cli as ops_cli
from cli.commands.sessions import cli as sessions_cli
from cli.commands.users import cli as users_cli
from registers.db import RecordNotFoundError


registry = CommandRegistry()
try:
    registry.register_plugin(billing_cli)
    registry.register_plugin(users_cli)
    registry.register_plugin(ops_cli)
    registry.register_plugin(sessions_cli)
except Exception as exc:
    raise SystemError(f"Failed to load CLI plugins: {exc}")


def main(argv: list[str] | None = None, print_result: bool = True):
    try:
        return registry.run(
            argv,
            print_result=print_result,
            shell_title="User Account Admin CLI",
            shell_description="Manage user accounts and auth sessions.",
            shell_usage=True,
        )
    except RecordNotFoundError as exc:
        payload = {"error": "not_found", "detail": str(exc)}
        if print_result:
            print(json.dumps(payload, indent=2, sort_keys=True))
            return None
        return json.dumps(payload, indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
