from sqlmodel import SQLModel, Field
from sqlalchemy import Text
from typing import Optional
from datetime import datetime, timezone
import uuid

def get_utc_now():
    return datetime.now(timezone.utc)

class User(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    name: str
    email: str = Field(unique=True, index=True)
    password: str
    role: str = Field(default="OPERATOR") 
    created_at: datetime = Field(default_factory=get_utc_now)
    
class SessionRecord(SQLModel, table=True):
    __tablename__ = "session"
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    session_id: str = Field(unique=True, index=True)
    ficha: Optional[str] = None
    status: str = Field(default="PENDING")
    task_id: Optional[str] = None
    user_id: Optional[str] = Field(default=None, foreign_key="user.id")
    contact_name: Optional[str] = None
    session_url: Optional[str] = None
    drive_folder_url: Optional[str] = None
    raw_content: Optional[str] = Field(default=None, sa_type=Text)
    center_inserted: bool = Field(default=False)
    center_duplicate: bool = Field(default=False)
    error_message: Optional[str] = None
    created_at: datetime = Field(default_factory=get_utc_now)

class MediaFile(SQLModel, table=True):
    __tablename__ = "media_file"
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    session_id: str = Field(foreign_key="session.session_id", index=True)
    file_id: str = Field(unique=True, index=True)
    type: str
    url: Optional[str] = None
    status: str = Field(default="PENDING")
    hash: Optional[str] = None
    created_at: datetime = Field(default_factory=get_utc_now)

class Summary(SQLModel, table=True):
    __tablename__ = "summary"
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    session_id: str = Field(foreign_key="session.session_id", unique=True, index=True)
    original_summary: str
    edited_summary: Optional[str] = None
    created_at: datetime = Field(default_factory=get_utc_now)

class ScheduledSync(SQLModel, table=True):
    __tablename__ = "scheduled_sync"
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    session_id: str = Field(foreign_key="session.session_id", index=True)
    ficha: Optional[str] = None
    contact_name: Optional[str] = None
    task_id: str = Field(unique=True, index=True)
    run_at: datetime = Field(index=True)
    status: str = Field(default="PENDING")
    created_at: datetime = Field(default_factory=get_utc_now)


class AuditLog(SQLModel, table=True):
    __tablename__ = "audit_log"
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    user_id: Optional[str] = Field(default=None, foreign_key="user.id")
    action: str
    endpoint: Optional[str] = None
    session_id: Optional[str] = None
    ficha: Optional[str] = None
    status: str
    error: Optional[str] = None
    ip: Optional[str] = None
    payload: Optional[str] = None
    created_at: datetime = Field(default_factory=get_utc_now)
