"""Goal/target tracking for KPIs."""
from sqlalchemy import Column, Integer, String, Float, ForeignKey, Index
from app.db.base import Base


class GoalTarget(Base):
    __tablename__ = "goal_targets"

    goal_id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenants.tenant_id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.user_id"), nullable=True)  # None = team-wide goal

    metric = Column(String(50), nullable=False)  # leads_sourced/emails_sent/deals_won/revenue
    target_value = Column(Float, nullable=False)
    current_value = Column(Float, default=0.0, nullable=False)
    period = Column(String(20), default='monthly', nullable=False)  # weekly/monthly/quarterly
    period_start = Column(String(10), nullable=True)  # YYYY-MM-DD
    period_end = Column(String(10), nullable=True)

    __table_args__ = (
        Index("idx_goal_tenant", "tenant_id"),
        Index("idx_goal_metric", "metric"),
    )

    def __repr__(self) -> str:
        return f"<GoalTarget(goal_id={self.goal_id}, metric='{self.metric}', progress={self.current_value}/{self.target_value})>"
