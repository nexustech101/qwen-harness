from __future__ import annotations

import json
from typing import Any

from registers.cli import CommandRegistry

from cli.bootstrap import bootstrap
from api.services.auth_service import issue_tokens_for_user, revoke_session_by_jti
from api.services.user_service import get_user_by_id

cli = CommandRegistry()

def _to_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True)


@cli.register(name="issue-token", description="Issue an access/refresh token pair for a user")
@cli.argument("user_id", type=int, help="User ID")
@cli.alias("--issue-token")
def issue_token_command(user_id: int) -> str:
    bootstrap()
    user = get_user_by_id(user_id)
    if not user.is_active:
        return _to_json({"action": "issue-token", "user_id": user.id, "error": "User is inactive"})

    tokens = issue_tokens_for_user(user)
    return _to_json({"action": "issue-token", "user_id": user.id, **tokens})


@cli.register(name="revoke-session", description="Revoke refresh session by token JTI")
@cli.argument("token_jti", type=str, help="Refresh token JTI")
@cli.alias("--revoke-session")
def revoke_session_command(token_jti: str) -> str:
    bootstrap()
    revoked = revoke_session_by_jti(token_jti)
    return _to_json({"action": "revoke-session", "token_jti": token_jti, "revoked": revoked})

