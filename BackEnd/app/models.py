import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


def new_id() -> str:
    return uuid.uuid4().hex[:12]


def now() -> datetime:
    return datetime.now(timezone.utc)


class Patient(Base):
    __tablename__ = "patients"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    age: Mapped[int | None]
    gender: Mapped[str | None] = mapped_column(String(20))
    blood_group: Mapped[str | None] = mapped_column(String(5))
    abha_id: Mapped[str | None] = mapped_column(String(40))
    language: Mapped[str] = mapped_column(String(5), default="en")
    conditions: Mapped[list] = mapped_column(JSON, default=list)
    allergies: Mapped[list] = mapped_column(JSON, default=list)
    family: Mapped[list] = mapped_column(JSON, default=list)
    # Where the patient lives, for the nearby-doctor finder. Nullable: the browser location wins when given.
    city: Mapped[str | None] = mapped_column(String(80))
    lat: Mapped[float | None] = mapped_column(Float)
    lng: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Document(Base):
    """One timeline record: prescription, lab report, consultation note, scan."""
    __tablename__ = "documents"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    date: Mapped[str] = mapped_column(String(10))  # YYYY-MM-DD
    type: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(200))
    source: Mapped[str | None] = mapped_column(String(200))
    summary: Mapped[str | None] = mapped_column(Text)
    summary_ml: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    items: Mapped[list] = mapped_column(JSON, default=list)
    image_path: Mapped[str | None] = mapped_column(String(300))
    # Phase 2: richer upload data. All nullable so existing seed rows still fit.
    status: Mapped[str | None] = mapped_column(String(10))  # good | watch | alert
    provider: Mapped[str | None] = mapped_column(String(200))
    doctor: Mapped[str | None] = mapped_column(String(200))
    followup: Mapped[str | None] = mapped_column(Text)
    source_kind: Mapped[str | None] = mapped_column(String(20))  # image | pdf
    source_lines: Mapped[list] = mapped_column(JSON, default=list)
    source_highlight: Mapped[list] = mapped_column(JSON, default=list)
    file_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    # Phase 6: where the record came from ("fhir" for hospital imports) and its
    # stable id in the source system, used to dedupe repeat imports.
    origin: Mapped[str | None] = mapped_column(String(20))
    external_id: Mapped[str | None] = mapped_column(String(120), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Medicine(Base):
    __tablename__ = "medicines"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    document_id: Mapped[str | None] = mapped_column(ForeignKey("documents.id"))
    name: Mapped[str] = mapped_column(String(120))
    generic: Mapped[str | None] = mapped_column(String(120))
    dose: Mapped[str | None] = mapped_column(String(60))
    frequency: Mapped[str | None] = mapped_column(String(60))
    times: Mapped[list] = mapped_column(JSON, default=list)
    instructions: Mapped[str | None] = mapped_column(String(200))
    start_date: Mapped[str | None] = mapped_column(String(10))
    prescribed_by: Mapped[str | None] = mapped_column(String(120))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Phase 5: nullable course length. None = ongoing (no end).
    duration_days: Mapped[int | None] = mapped_column(default=None)
    # Phase 5: optional refill date (YYYY-MM-DD). None = no refill tracked.
    refill_due: Mapped[str | None] = mapped_column(String(10))


class Observation(Base):
    """One lab value, e.g. HbA1c 7.8 %."""
    __tablename__ = "observations"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    document_id: Mapped[str | None] = mapped_column(ForeignKey("documents.id"))
    date: Mapped[str] = mapped_column(String(10))
    code: Mapped[str] = mapped_column(String(40))  # e.g. hba1c
    name: Mapped[str] = mapped_column(String(120))
    value: Mapped[float] = mapped_column(Float)
    unit: Mapped[str | None] = mapped_column(String(30))
    # Phase 6: LOINC code and source tag (None = own upload, "fhir" = hospital import).
    loinc: Mapped[str | None] = mapped_column(String(20))
    source: Mapped[str | None] = mapped_column(String(20))
    # The reference range printed on the report, used to judge tests that have no built-in rule.
    ref_range: Mapped[str | None] = mapped_column(String(60))


class Alert(Base):
    __tablename__ = "alerts"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    severity: Mapped[str] = mapped_column(String(10))  # high | medium | low
    kind: Mapped[str] = mapped_column(String(20))  # interaction | duplicate | lab
    title: Mapped[str] = mapped_column(String(200))
    message: Mapped[str] = mapped_column(Text)
    message_ml: Mapped[str | None] = mapped_column(Text)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Consultation(Base):
    __tablename__ = "consultations"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    doctor_name: Mapped[str] = mapped_column(String(120))
    # transcript_lines is the structured list [{speaker,text}]; transcript keeps
    # the plain-text join for display/backwards compat.
    transcript: Mapped[str | None] = mapped_column(Text)
    transcript_lines: Mapped[list] = mapped_column(JSON, default=list)
    soap: Mapped[dict] = mapped_column(JSON, default=dict)      # live/partial, then draft
    final_note: Mapped[dict] = mapped_column(JSON, default=dict)  # post-approve
    edited_fields: Mapped[list] = mapped_column(JSON, default=list)
    flags: Mapped[list] = mapped_column(JSON, default=list)
    questions: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(20), default="active")  # active | draft | approved
    share_token: Mapped[str | None] = mapped_column(String(64), index=True)
    document_id: Mapped[str | None] = mapped_column(ForeignKey("documents.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ShareLink(Base):
    __tablename__ = "share_links"
    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    scope: Mapped[str] = mapped_column(String(20), default="full")
    # Phase 8: set when a doctor opened the console from their account, so revoking that doctor kills the link.
    doctor_user_id: Mapped[str | None] = mapped_column(String(32), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ReminderSettings(Base):
    """Per-patient reminder preferences. Phase 5."""
    __tablename__ = "reminder_settings"
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    channel_phone: Mapped[bool] = mapped_column(Boolean, default=False)
    channel_telegram: Mapped[bool] = mapped_column(Boolean, default=False)
    channel_family: Mapped[bool] = mapped_column(Boolean, default=False)
    telegram_chat_id: Mapped[str | None] = mapped_column(String(40))
    family_chat_id: Mapped[str | None] = mapped_column(String(40))
    family_name: Mapped[str | None] = mapped_column(String(60))
    missed_after_minutes: Mapped[int] = mapped_column(default=60)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class SentDose(Base):
    """One row per (medicine, dose clock, date). Phase 5 — scheduler dedup."""
    __tablename__ = "sent_doses"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    medicine_id: Mapped[str] = mapped_column(ForeignKey("medicines.id"), index=True)
    clock: Mapped[str] = mapped_column(String(5))      # "HH:MM"
    date: Mapped[str] = mapped_column(String(10))      # YYYY-MM-DD, IST
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    taken: Mapped[bool] = mapped_column(Boolean, default=False)
    taken_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    missed_notified: Mapped[bool] = mapped_column(Boolean, default=False)
    # Hourly "still to take" nudges (nullable so existing rows and databases need no migration step beyond ADD COLUMN).
    nudges: Mapped[int | None] = mapped_column(default=0)
    last_nudge_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SentNotice(Base):
    """Once-only notices (refill, appointment). `key` is unique per notice."""
    __tablename__ = "sent_notices"
    key: Mapped[str] = mapped_column(String(160), primary_key=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class AccessLog(Base):
    __tablename__ = "access_logs"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    who: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(40))
    action: Mapped[str] = mapped_column(String(200))
    via: Mapped[str] = mapped_column(String(40))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class User(Base):
    """A login. Patients own a Patient row (patient_id); doctors have a profile instead. Phase 8."""
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(300))
    role: Mapped[str] = mapped_column(String(10))  # patient | doctor
    name: Mapped[str] = mapped_column(String(120))
    patient_id: Mapped[str | None] = mapped_column(ForeignKey("patients.id"), index=True)
    specialty: Mapped[str | None] = mapped_column(String(80))
    hospital: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class InviteCode(Base):
    """One-time code a patient gives a doctor so the doctor can see the record."""
    __tablename__ = "invite_codes"
    code: Mapped[str] = mapped_column(String(12), primary_key=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_by: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class CareLink(Base):
    """Doctor <-> patient access. `revoked` is kept (not deleted) so the history stays."""
    __tablename__ = "care_links"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    doctor_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(String(10), default="active")  # active | revoked
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class AiDecision(Base):
    """Audit trail for every Laya answer: what was asked (hash only, never the text), what came back, how long it took."""
    __tablename__ = "ai_decisions"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    kind: Mapped[str] = mapped_column(String(20), index=True)  # triage | line
    input_hash: Mapped[str] = mapped_column(String(64), index=True)
    model: Mapped[str | None] = mapped_column(String(80))
    result: Mapped[dict] = mapped_column(JSON, default=dict)   # labels and probabilities
    final: Mapped[dict] = mapped_column(JSON, default=dict)    # what the app actually used after the rules merge
    latency_ms: Mapped[float | None] = mapped_column(Float)
    cached: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class AgentAudit(Base):
    """One row per agent tool call: who, which agent, what, on whom, outcome. Never stores document text or secrets."""
    __tablename__ = "agent_audit"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    actor_id: Mapped[str] = mapped_column(String(32), index=True)           # patient id or doctor user id
    actor_role: Mapped[str] = mapped_column(String(10))                      # patient | doctor
    agent_type: Mapped[str] = mapped_column(String(10))                      # patient | doctor
    patient_id: Mapped[str | None] = mapped_column(ForeignKey("patients.id"), index=True)
    request_id: Mapped[str | None] = mapped_column(String(32), index=True)
    tool: Mapped[str] = mapped_column(String(60), index=True)
    category: Mapped[str] = mapped_column(String(30))
    level: Mapped[int] = mapped_column(default=1)
    target: Mapped[str | None] = mapped_column(String(80))                   # id of the record touched, not its content
    status: Mapped[str] = mapped_column(String(24))                          # ok | denied | invalid | failed | needs_confirmation | declined
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    result_ref: Mapped[str | None] = mapped_column(String(80))
    detail: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class AgentFile(Base):
    """Metadata for one file the person gave the agent. The bytes live encrypted in the vault, never in the DB or under a
    guessable path. `sha256` is of the plaintext and is for integrity / duplicate checks only (not a secret)."""
    __tablename__ = "agent_files"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    uploaded_by: Mapped[str] = mapped_column(String(32))
    uploader_role: Mapped[str] = mapped_column(String(10), default="patient")
    display_name: Mapped[str] = mapped_column(String(120))
    mime: Mapped[str] = mapped_column(String(60))
    size: Mapped[int] = mapped_column(default=0)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    storage_key: Mapped[str] = mapped_column(String(64), unique=True)       # random; the vault path derives from it
    status: Mapped[str] = mapped_column(String(20), default="uploaded")     # uploaded | classified | extracted | confirmed | discarded
    classification: Mapped[dict] = mapped_column(JSON, default=dict)        # {type, confidence, source}
    extraction: Mapped[dict] = mapped_column(JSON, default=dict)            # structured fields with provenance (phase 7)
    document_id: Mapped[str | None] = mapped_column(ForeignKey("documents.id"))  # set once confirmed into the timeline
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class AgentTask(Base):
    """One agent job: queued -> planning -> running -> (waiting_for_confirmation) -> completed | failed | cancelled."""
    __tablename__ = "agent_tasks"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(String(32), index=True)            # patient id or doctor user id
    agent_type: Mapped[str] = mapped_column(String(10))                      # patient | doctor
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    conversation_id: Mapped[str | None] = mapped_column(String(32))
    intent: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(24), default="queued", index=True)
    steps: Mapped[list] = mapped_column(JSON, default=list)                  # [{tool, args, label, status, result?, confirmationId?}]
    result: Mapped[dict] = mapped_column(JSON, default=dict)                 # final formatted response
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
