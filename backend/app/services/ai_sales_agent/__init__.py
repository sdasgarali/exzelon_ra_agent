"""Autonomous AI Sales-Agent Layer.

Policy-constrained, audited AI modules for outbound sales execution.

Modules:
- agent_context: Aggregates lead/contact/history for AI consumption
- policy_engine: Deterministic rules engine with per-tenant config
- scoring_engine: Composable scoring with reason codes
- prompt_registry: Named, versioned prompt templates
- reply_intelligence: LLM-powered intent detection + next-best-action
- draft_intelligence: Context-aware email generation strategy
- send_decision: Structured go/no-go decisions
- learning_engine: Outcome tracking for optimization
- orchestrator: Coordinates all modules
"""
from app.services.ai_sales_agent.orchestrator import orchestrate_send, orchestrate_reply

__all__ = ["orchestrate_send", "orchestrate_reply"]
