"""Provider-neutral schemas for invoking Knowledge Assistant tools."""

from __future__ import annotations

from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class StrictToolModel(BaseModel):
    """Reject misspelled fields at the agent-tool boundary."""

    model_config = ConfigDict(extra="forbid")


class ToolEffect(StrEnum):
    """The authority a tool needs beyond reading a selected workspace."""

    READ_ONLY = "read_only"
    WRITE = "write"


class ToolContext(StrictToolModel):
    """Identity, workspace scope, and authority for one tool invocation."""

    workspace: str = Field(min_length=1)
    caller: str = Field(default="agent", min_length=1)
    run_id: str = Field(default_factory=lambda: str(uuid4()))
    allowed_tools: set[str] | None = None
    allow_write: bool = False


class ToolDescriptor(StrictToolModel):
    """Machine-readable public contract for one registered tool."""

    name: str = Field(pattern=r"^[a-z][a-z0-9_.-]*$")
    description: str = Field(min_length=1)
    effect: ToolEffect = ToolEffect.READ_ONLY
    workspace_scoped: bool = True
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]


class ToolResult(StrictToolModel):
    """Structured result returned to an agent, including an audit identity."""

    tool: str
    workspace: str
    run_id: str
    status: str
    result: dict[str, Any] | None = None
    error: str | None = None
    warnings: list[str] = Field(default_factory=list)
    duration_seconds: float = Field(ge=0)


class ToolAuditEvent(StrictToolModel):
    """Privacy-preserving audit record; tool arguments and results are omitted."""

    run_id: str
    caller: str
    workspace: str
    tool: str
    status: str
    duration_seconds: float = Field(ge=0)
