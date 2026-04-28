from __future__ import annotations

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from api.db.models import User


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=120)
    is_active: bool | None = None
    is_admin: bool | None = None


class UserPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    full_name: str
    is_active: bool
    is_admin: bool
    created_at: str
    updated_at: str
    last_login_at: str | None = None

    @classmethod
    def from_model(cls, user: User) -> "UserPublic":
        return cls.model_validate(user)


class UserPage(BaseModel):
    items: list[UserPublic]
    total: int
    limit: int
    offset: int
