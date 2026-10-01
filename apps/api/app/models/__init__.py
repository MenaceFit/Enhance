"""ORM models.

Every user-owned row carries ``user_id`` so that queries are always scoped to
the authenticated user (isolation), and storage keys are namespaced the same
way (``users/{user_id}/...``) so that deleting an account is one prefix
deletion.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, JSONType


def utcnow() -> datetime:
    return datetime.now(UTC)


def new_id() -> uuid.UUID:
    return uuid.uuid4()


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


# --- users & privacy ------------------------------------------------------------------


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    email: Mapped[str | None] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str | None] = mapped_column(String(255))
    display_name: Mapped[str | None] = mapped_column(String(80))
    is_guest: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    token_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    plan_code: Mapped[str] = mapped_column(String(32), default="free", nullable=False)
    retention_days: Mapped[int | None] = mapped_column(Integer)
    preferences: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    projects: Mapped[list[Project]] = relationship(back_populates="user", cascade="all, delete-orphan", passive_deletes=True)


class Consent(TimestampMixin, Base):
    __tablename__ = "consents"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(32))  # privacy_policy | analytics | marketing
    granted: Mapped[bool] = mapped_column(Boolean)
    version: Mapped[str] = mapped_column(String(32))


# --- billing --------------------------------------------------------------------------


class Plan(Base):
    __tablename__ = "plans"

    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(64))
    monthly_credits: Mapped[int] = mapped_column(Integer)
    price_cents: Mapped[int] = mapped_column(Integer, default=0)
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    features: Mapped[dict] = mapped_column(JSONType, default=dict)


class Subscription(TimestampMixin, Base):
    __tablename__ = "subscriptions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    plan_code: Mapped[str] = mapped_column(ForeignKey("plans.code"))
    status: Mapped[str] = mapped_column(String(16), default="active")  # active | canceled | past_due
    current_period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    current_period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    provider: Mapped[str] = mapped_column(String(16), default="manual")  # manual | stripe
    provider_ref: Mapped[str | None] = mapped_column(String(128), index=True)


class CreditTransaction(TimestampMixin, Base):
    __tablename__ = "credit_transactions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    delta: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(String(32))  # enhance | refund | bonus
    photo_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    job_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)

    __table_args__ = (Index("ix_credit_user_created", "user_id", "created_at"),)


# --- photos ---------------------------------------------------------------------------


class Project(TimestampMixin, Base):
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    marketplace: Mapped[str] = mapped_column(String(32), default="vinted")
    consistency_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    settings: Mapped[dict] = mapped_column(JSONType, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    user: Mapped[User] = relationship(back_populates="projects")
    photos: Mapped[list[Photo]] = relationship(
        back_populates="project", order_by="Photo.position", cascade="all, delete-orphan", passive_deletes=True
    )


class Photo(TimestampMixin, Base):
    __tablename__ = "photos"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer, default=1)
    original_filename: Mapped[str] = mapped_column(String(255))
    source_format: Mapped[str] = mapped_column(String(8))
    size_bytes: Mapped[int] = mapped_column(Integer)
    width: Mapped[int] = mapped_column(Integer, default=0)
    height: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="queued")  # queued | processing | ready | failed
    error: Mapped[str | None] = mapped_column(Text)
    storage_prefix: Mapped[str] = mapped_column(String(255))
    original_key: Mapped[str] = mapped_column(String(255))
    working_key: Mapped[str | None] = mapped_column(String(255))
    thumb_key: Mapped[str | None] = mapped_column(String(255))
    mask_key: Mapped[str | None] = mapped_column(String(255))
    labels_key: Mapped[str | None] = mapped_column(String(255))
    analysis: Mapped[dict | None] = mapped_column(JSONType)
    defect_state: Mapped[dict] = mapped_column(JSONType, default=dict)  # defect id → "acknowledged"
    current_version_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    is_favorite: Mapped[bool] = mapped_column(Boolean, default=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    project: Mapped[Project] = relationship(back_populates="photos")
    versions: Mapped[list[PhotoVersion]] = relationship(
        back_populates="photo", order_by="PhotoVersion.created_at", cascade="all, delete-orphan", passive_deletes=True
    )

    __table_args__ = (Index("ix_photos_user_created", "user_id", "created_at"),)


class PhotoVersion(TimestampMixin, Base):
    __tablename__ = "photo_versions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    photo_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("photos.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(16))  # ai | edited | final
    label: Mapped[str | None] = mapped_column(String(80))
    settings: Mapped[dict] = mapped_column(JSONType)
    metrics: Mapped[dict] = mapped_column(JSONType, default=dict)
    after_key: Mapped[str] = mapped_column(String(255))
    before_key: Mapped[str] = mapped_column(String(255))
    thumb_key: Mapped[str] = mapped_column(String(255))
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)

    photo: Mapped[Photo] = relationship(back_populates="versions")


# --- jobs, providers, exports -----------------------------------------------------------


class Job(TimestampMixin, Base):
    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String(24))  # enhance | rerender | export | project_export | gdpr_export | benchmark
    status: Mapped[str] = mapped_column(String(16), default="queued", index=True)  # queued | running | succeeded | failed
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    stage: Mapped[str | None] = mapped_column(String(48))
    stage_label: Mapped[str | None] = mapped_column(String(120))
    params: Mapped[dict] = mapped_column(JSONType, default=dict)
    result: Mapped[dict | None] = mapped_column(JSONType)
    error: Mapped[str | None] = mapped_column(Text)
    photo_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True)
    project_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    cost_cents: Mapped[float] = mapped_column(Float, default=0.0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (Index("ix_jobs_type_created", "type", "created_at"),)


class ProviderCall(TimestampMixin, Base):
    __tablename__ = "provider_calls"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    job_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("jobs.id", ondelete="SET NULL"), index=True)
    capability: Mapped[str] = mapped_column(String(32))
    provider: Mapped[str] = mapped_column(String(32))
    model: Mapped[str | None] = mapped_column(String(128))
    duration_ms: Mapped[float] = mapped_column(Float)
    cost_cents: Mapped[float] = mapped_column(Float, default=0.0)
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    error: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (Index("ix_provider_calls_created", "created_at"),)


class Export(TimestampMixin, Base):
    __tablename__ = "exports"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    photo_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("photos.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    version_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    format: Mapped[str] = mapped_column(String(8))
    quality: Mapped[str] = mapped_column(String(16))
    key: Mapped[str] = mapped_column(String(255))
    filename: Mapped[str] = mapped_column(String(120))
    width: Mapped[int] = mapped_column(Integer, default=0)
    height: Mapped[int] = mapped_column(Integer, default=0)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)


class BenchmarkRun(TimestampMixin, Base):
    __tablename__ = "benchmark_runs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    job_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    profiles: Mapped[dict] = mapped_column(JSONType)
    image_source: Mapped[str] = mapped_column(String(32))  # synthetic | photos
    image_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="queued")
    summary: Mapped[list | None] = mapped_column(JSONType)
    results: Mapped[list | None] = mapped_column(JSONType)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


__all__ = [
    "BenchmarkRun", "Consent", "CreditTransaction", "Export", "Job", "Photo", "PhotoVersion", "Plan", "Project",
    "ProviderCall", "Subscription", "User", "utcnow",
]
