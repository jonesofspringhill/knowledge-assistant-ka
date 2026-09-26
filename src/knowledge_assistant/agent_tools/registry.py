"""Tool registry, authority checks, and built-in knowledge-tool implementations."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from pydantic import BaseModel, Field

from knowledge_assistant.config import Settings
from knowledge_assistant.managers import PromptManager, WorkspaceManager
from knowledge_assistant.question_answering import answer_question
from knowledge_assistant.retrieval import search_workspace

from .models import (
    StrictToolModel,
    ToolAuditEvent,
    ToolContext,
    ToolDescriptor,
    ToolEffect,
    ToolResult,
)


class AgentToolError(RuntimeError):
    """Raised when a tool cannot complete an agent invocation."""


class ToolNotFoundError(AgentToolError):
    """Raised when no registered tool has the requested name."""


class ToolNotAllowedError(AgentToolError):
    """Raised when caller authority does not permit a registered tool."""


class AgentTool(Protocol):
    """A provider-neutral tool callable by an external agent or workflow."""

    descriptor: ToolDescriptor

    def invoke(self, context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
        """Validate arguments and return a JSON-serialisable result."""


AuditWriter = Callable[[ToolAuditEvent], None]


class AgentToolRegistry:
    """Register tools once and enforce scope and authority on every call."""

    def __init__(self, audit_writer: AuditWriter | None = None) -> None:
        self._tools: dict[str, AgentTool] = {}
        self._audit_writer = audit_writer

    def register(self, tool: AgentTool) -> None:
        name = tool.descriptor.name
        if name in self._tools:
            raise ValueError(f"tool is already registered: {name}")
        self._tools[name] = tool

    def descriptors(self) -> tuple[ToolDescriptor, ...]:
        return tuple(self._tools[name].descriptor for name in sorted(self._tools))

    def descriptor(self, name: str) -> ToolDescriptor:
        return self._get(name).descriptor

    def invoke(
        self, name: str, context: ToolContext, arguments: dict[str, Any]
    ) -> ToolResult:
        started = time.monotonic()
        status = "error"
        result: dict[str, Any] | None = None
        error: str | None = None
        try:
            tool = self._get(name)
            self._authorise(tool.descriptor, context)
            result = tool.invoke(context, arguments)
            status = "ok"
        except Exception as exc:  # noqa: BLE001 - a tool boundary returns JSON errors.
            error = str(exc)
        duration = time.monotonic() - started
        response = ToolResult(
            tool=name,
            workspace=context.workspace,
            run_id=context.run_id,
            status=status,
            result=result,
            error=error,
            duration_seconds=duration,
        )
        if self._audit_writer is not None:
            self._audit_writer(
                ToolAuditEvent(
                    run_id=context.run_id,
                    caller=context.caller,
                    workspace=context.workspace,
                    tool=name,
                    status=status,
                    duration_seconds=duration,
                )
            )
        return response

    def _get(self, name: str) -> AgentTool:
        try:
            return self._tools[name]
        except KeyError as error:
            raise ToolNotFoundError(f"unknown agent tool: {name}") from error

    @staticmethod
    def _authorise(descriptor: ToolDescriptor, context: ToolContext) -> None:
        if context.allowed_tools is not None and descriptor.name not in context.allowed_tools:
            raise ToolNotAllowedError(f"tool is not allowed for caller: {descriptor.name}")
        if descriptor.effect is ToolEffect.WRITE and not context.allow_write:
            raise ToolNotAllowedError(f"write authority is required: {descriptor.name}")


@dataclass(frozen=True, slots=True)
class AgentToolRuntime:
    """Runtime dependencies and audit storage for the built-in tool set."""

    settings: Settings
    workspaces: WorkspaceManager

    def audit(self, event: ToolAuditEvent) -> None:
        workspace = self.workspaces.get(event.workspace)
        output = workspace.artifacts / "agent-tools" / "audit.jsonl"
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("a", encoding="utf-8") as file:
            file.write(event.model_dump_json() + "\n")


class _ToolBase:
    input_model: type[BaseModel]
    output_model: type[BaseModel]
    descriptor: ToolDescriptor

    def __init__(self, runtime: AgentToolRuntime) -> None:
        self.runtime = runtime

    def invoke(self, context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
        payload = self.input_model.model_validate(arguments)
        output = self.execute(context, payload)
        return self.output_model.model_validate(output).model_dump(mode="json")

    def execute(self, context: ToolContext, payload: BaseModel) -> BaseModel:
        raise NotImplementedError


class WorkspaceDescribeInput(StrictToolModel):
    """No additional arguments; the workspace comes from ToolContext."""


class WorkspaceDescribeOutput(BaseModel):
    name: str
    description: str
    collection: str
    enabled: bool
    source_roots: list[str]


class WorkspaceDescribeTool(_ToolBase):
    input_model = WorkspaceDescribeInput
    output_model = WorkspaceDescribeOutput
    descriptor = ToolDescriptor(
        name="knowledge.workspace.describe",
        description="Describe the selected workspace without reading its documents.",
        input_schema=WorkspaceDescribeInput.model_json_schema(),
        output_schema=WorkspaceDescribeOutput.model_json_schema(),
    )

    def execute(
        self, context: ToolContext, payload: WorkspaceDescribeInput
    ) -> WorkspaceDescribeOutput:
        del payload
        workspace = self.runtime.workspaces.get(context.workspace)
        return WorkspaceDescribeOutput(
            name=workspace.name,
            description=workspace.description,
            collection=workspace.collection,
            enabled=workspace.enabled,
            source_roots=[source.name for source in workspace.sources],
        )


class SearchInput(StrictToolModel):
    query: str = Field(min_length=1)
    top_k: int | None = Field(default=None, gt=0)
    threshold: float | None = Field(default=None, ge=0, le=1)
    filters: dict[str, str | int | float | bool] = Field(default_factory=dict)


class SearchItem(BaseModel):
    chunk_id: str
    document_id: str
    document_title: str | None
    section_title: str | None
    source_path: str
    source_location: str
    similarity: float
    text: str


class SearchOutput(BaseModel):
    query: str
    results: list[SearchItem]
    retrieval_latency_seconds: float


class SearchTool(_ToolBase):
    input_model = SearchInput
    output_model = SearchOutput
    descriptor = ToolDescriptor(
        name="knowledge.search",
        description="Search one workspace and return ranked, citation-ready evidence.",
        input_schema=SearchInput.model_json_schema(),
        output_schema=SearchOutput.model_json_schema(),
    )

    def execute(self, context: ToolContext, payload: SearchInput) -> SearchOutput:
        workspace = self.runtime.workspaces.get(context.workspace)
        results, latency = search_workspace(
            workspace,
            self.runtime.settings.chroma.directory,
            self.runtime.settings.retrieval,
            self.runtime.settings.embedding,
            payload.query,
            top_k=payload.top_k,
            threshold=payload.threshold,
            filters=payload.filters,
        )
        return SearchOutput(
            query=payload.query,
            results=[
                SearchItem(
                    chunk_id=item.chunk_id,
                    document_id=item.document_id,
                    document_title=item.document_title,
                    section_title=item.section_title,
                    source_path=item.source_path.as_posix(),
                    source_location=item.source_location,
                    similarity=item.similarity,
                    text=item.text,
                )
                for item in results
            ],
            retrieval_latency_seconds=latency,
        )


class AskInput(StrictToolModel):
    question: str = Field(min_length=1)
    top_k: int | None = Field(default=None, gt=0)
    threshold: float | None = Field(default=None, ge=0, le=1)
    filters: dict[str, str | int | float | bool] = Field(default_factory=dict)


class AskCitation(BaseModel):
    label: str
    source: str
    chunk_id: str
    document_id: str
    source_location: str


class AskOutput(BaseModel):
    question: str
    answer: str
    status: str
    uncertainty: str | None
    citations: list[AskCitation]
    context_sources: list[str]
    retrieval_latency_seconds: float
    generation_latency_seconds: float


class AskTool(_ToolBase):
    input_model = AskInput
    output_model = AskOutput
    descriptor = ToolDescriptor(
        name="knowledge.ask",
        description="Answer one question from selected-workspace evidence with citations.",
        input_schema=AskInput.model_json_schema(),
        output_schema=AskOutput.model_json_schema(),
    )

    def execute(self, context: ToolContext, payload: AskInput) -> AskOutput:
        workspace = self.runtime.workspaces.get(context.workspace)
        result = answer_question(
            workspace,
            self.runtime.settings.chroma.directory,
            self.runtime.settings.retrieval,
            self.runtime.settings.embedding,
            self.runtime.settings.llm,
            self.runtime.settings.environment,
            PromptManager(self.runtime.settings.prompts),
            payload.question,
            qa_settings=self.runtime.settings.question_answering,
            top_k=payload.top_k,
            threshold=payload.threshold,
            filters=payload.filters,
        )
        return AskOutput(
            question=result.question,
            answer=result.answer,
            status=result.status,
            uncertainty=result.uncertainty,
            citations=[AskCitation(**citation.model_dump()) for citation in result.citations],
            context_sources=[path.as_posix() for path in result.context_sources],
            retrieval_latency_seconds=result.retrieval_latency_seconds,
            generation_latency_seconds=result.generation_latency_seconds,
        )


def build_default_registry(runtime: AgentToolRuntime) -> AgentToolRegistry:
    """Return the initial read-only tools available to generic agent workflows."""
    registry = AgentToolRegistry(audit_writer=runtime.audit)
    for tool in (WorkspaceDescribeTool(runtime), SearchTool(runtime), AskTool(runtime)):
        registry.register(tool)
    return registry
