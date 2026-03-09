"""Deal task model for CRM task management."""
import enum
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Enum
from app.db.base import Base


class TaskStatus(str, enum.Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class TaskPriority(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class DealTask(Base):
    """Tasks associated with CRM deals."""
    __tablename__ = "deal_tasks"

    task_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    deal_id = Column(Integer, ForeignKey("deals.deal_id"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    assigned_to = Column(Integer, ForeignKey("users.user_id"), nullable=True)
    due_date = Column(DateTime, nullable=True)
    status = Column(Enum(TaskStatus, values_callable=lambda x: [e.value for e in x]), default=TaskStatus.PENDING)
    priority = Column(Enum(TaskPriority, values_callable=lambda x: [e.value for e in x]), default=TaskPriority.MEDIUM)
    created_by = Column(Integer, ForeignKey("users.user_id"), nullable=True)
    completed_at = Column(DateTime, nullable=True)

    def __repr__(self):
        return f"<DealTask {self.title} deal={self.deal_id}>"
