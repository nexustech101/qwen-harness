from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class AuthEventPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int | None = None
    email: str
    ip_address: str | None = None
    user_agent: str | None = None
    request_id: str | None = None
    action: str
    success: bool
    details: str | None = None
    created_at: str

    @classmethod
    def from_model(cls, event: object) -> "AuthEventPublic":
        return cls.model_validate(event)


class AuthEventPage(BaseModel):
    items: list[AuthEventPublic]
    total: int
    limit: int
    offset: int


class MigrationRecord(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    version: int
    name: str
    applied_at: str
    details: str | None = None

    @classmethod
    def from_model(cls, migration: object) -> "MigrationRecord":
        return cls.model_validate(migration)


class MigrationMetadataResponse(BaseModel):
    current_schema_version: int
    applied_count: int
    migrations: list[MigrationRecord]


class VersionMetadataResponse(BaseModel):
    app_name: str
    api_version: str
    current_schema_version: int
    database_url: str
    migration_count: int

