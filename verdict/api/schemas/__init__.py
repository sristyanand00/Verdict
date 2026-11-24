"""Request bodies for the API. Responses are plain JSON, described in
docs/API.md (the contract the frontend builds against)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    #: omitted: the current database from settings
    database_id: str | None = None
    #: omitted: the current model from settings
    model: str | None = None


class FlagRequest(BaseModel):
    note: str = Field(default="", max_length=2000)


class MeaningIn(BaseModel):
    term: str = Field(min_length=1, max_length=100)
    definition: str = Field(min_length=1, max_length=1000)
    sql_hint: str | None = Field(default=None, max_length=2000)


class ChooseRequest(BaseModel):
    option: int = Field(ge=0)
    save_meaning: MeaningIn | None = None


class KnownNumberIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class ResolveRequest(BaseModel):
    action: Literal["approve", "fix", "reject"]
    #: required for "fix"; for "approve" defaults to the draft SQL
    sql: str | None = Field(default=None, max_length=20000)
    note: str | None = Field(default=None, max_length=2000)
    save_meaning: MeaningIn | None = None
    #: save the approved answer as a known number under this name
    save_known_number: KnownNumberIn | None = None


class SqlRunRequest(BaseModel):
    database_id: str
    sql: str = Field(min_length=1, max_length=20000)


class NewMeaningRequest(MeaningIn):
    database_id: str


class SettingsIn(BaseModel):
    database_id: str | None = None
    model: str | None = None
    second_model: bool | None = None
    second_model_id: str | None = None
