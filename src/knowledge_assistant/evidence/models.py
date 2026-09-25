"""Strict external schemas and portable evidence-library domain models."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    model_validator,
)


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ManifestModule(_StrictModel):
    module_id: str = Field(min_length=1)
    title: str | None = None
    record_file: Path
    course_document: Path | None = Field(
        default=None,
        validation_alias=AliasChoices("course_document", "course_pdf"),
    )
    status: str | None = None
    source_count: int | None = Field(default=None, ge=0)


class EvidenceManifest(_StrictModel):
    schema_version: str
    description: str | None = None
    modules: list[ManifestModule] = Field(min_length=1)
    notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_modules(self) -> EvidenceManifest:
        values = [item.module_id.casefold() for item in self.modules]
        if len(values) != len(set(values)):
            raise ValueError("manifest module identifiers must be unique ignoring case")
        return self


class SourceRules(_StrictModel):
    require_pdf: bool
    require_authoritative_organisation: bool
    prefer_primary_guidelines_or_official_reports: bool
    download_validation: str


class ResearchPolicy(_StrictModel):
    schema_version: str = "1.0"
    approved_domains: list[str] = Field(default_factory=list)
    source_rules: SourceRules | None = None
    module_statuses: list[str] = Field(min_length=1)
    claim_assessments: list[str] = Field(
        min_length=1,
        validation_alias=AliasChoices("claim_assessments", "claim_statuses"),
    )
    download_statuses: list[str] | None = None


class EvidenceSubtopic(_StrictModel):
    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    course_pages: list[int] = Field(default_factory=list)


class EvidenceSource(_StrictModel):
    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    organisation: str = Field(min_length=1)
    authority_type: str | None = None
    url: HttpUrl | None = None
    local_file: Path | None = None
    download_status: str | None = None
    publication_date: str | None = None
    relevant_topics: list[str] = Field(default_factory=list)
    review_status: str | None = None


class ModuleClaimReview(_StrictModel):
    subtopic_id: str = Field(min_length=1)
    assessment: str = Field(min_length=1)
    notes: str = Field(min_length=1)


class ModuleRecord(_StrictModel):
    module_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    status: str = Field(min_length=1)
    course_document: Path = Field(
        validation_alias=AliasChoices("course_document", "course_pdf")
    )
    course_pdf_pages: int | None = Field(default=None, ge=0)
    subtopics: list[EvidenceSubtopic] = Field(default_factory=list)
    sources: list[EvidenceSource] = Field(default_factory=list)
    claim_reviews: list[ModuleClaimReview] = Field(
        default_factory=list,
        validation_alias=AliasChoices("claim_reviews", "claim_review"),
    )

    @model_validator(mode="after")
    def unique_local_identities(self) -> ModuleRecord:
        for label, values in (
            ("subtopic", [item.id.casefold() for item in self.subtopics]),
            ("source", [item.id.casefold() for item in self.sources]),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"{label} identifiers must be unique within a module")
        known = {item.id.casefold() for item in self.subtopics}
        unknown = [
            review.subtopic_id
            for review in self.claim_reviews
            if review.subtopic_id.casefold() not in known
        ]
        if unknown:
            raise ValueError(
                "claim review references unknown subtopic(s): " + ", ".join(unknown)
            )
        return self


class ClaimReview(_StrictModel):
    module_id: str
    subtopic_id: str
    assessment: str
    notes: str
    record_file: Path


class DocumentAssociation(_StrictModel):
    workspace: str
    source_root: str
    relative_path: Path
    source_path: Path
    document_role: Literal["course_module", "authoritative_source"]
    module_id: str
    module_title: str
    module_status: str
    source_id: str | None = None
    source_title: str | None = None
    organisation: str | None = None
    authority_type: str | None = None
    source_url: str | None = None
    subtopic_ids: list[str] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)


class EvidenceModule(_StrictModel):
    module_id: str
    title: str
    status: str
    course_document: Path
    course_pdf_pages: int | None = None
    subtopics: list[EvidenceSubtopic]
    sources: list[EvidenceSource]
    claim_reviews: list[ClaimReview]
    record_file: Path


class MetadataIssue(_StrictModel):
    severity: Literal["warn", "fatal"]
    code: str
    message: str


class MetadataSummary(_StrictModel):
    modules: int
    subtopics: int
    source_references: int
    local_source_references: int
    remote_only_references: int
    claim_reviews: int
    missing_references: int
    unmatched_documents: int
    associations: int


class EvidenceLibrary(_StrictModel):
    artifact_version: str = "1"
    schema_version: str
    workspace: str
    manifest_path: Path
    policy_path: Path
    policy: ResearchPolicy
    modules: list[EvidenceModule]
    document_associations: list[DocumentAssociation]
    claim_reviews: list[ClaimReview]
    validation_issues: list[MetadataIssue]
    summary: MetadataSummary

    def associations_for(
        self, source_root: str, relative_path: Path
    ) -> tuple[DocumentAssociation, ...]:
        key = (source_root.casefold(), relative_path.as_posix().casefold())
        return tuple(
            item
            for item in self.document_associations
            if (item.source_root.casefold(), item.relative_path.as_posix().casefold())
            == key
        )
