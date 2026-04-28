from __future__ import annotations

import json

import registers.cli as cli
from registers.db import RecordNotFoundError

from . import commands  # noqa: F401


def main(argv: list[str] | None = None, print_result: bool = True):
    try:
        return cli.run(
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
