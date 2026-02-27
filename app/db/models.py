try:
    from aiogram.fsm.state import State, StatesGroup
except Exception:  # pragma: no cover - for migration/runtime isolation
    class StatesGroup:  # type: ignore
        pass

    class State:  # type: ignore
        pass
from sqlalchemy import Column, DateTime, Integer, LargeBinary, String
from sqlalchemy.sql import func

from app.db.base import Base


class NotionCredential(Base):
    __tablename__ = "notion_credentials"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    workspace_name = Column(String(255))
    database_id = Column(String(64), index=True)
    database_id = Column(String(100), nullable=True)
    encrypted_key = Column(LargeBinary, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<NotionCredential(user_id={self.user_id})>"


class NotionSetup(StatesGroup):
    waiting_for_key = State()
