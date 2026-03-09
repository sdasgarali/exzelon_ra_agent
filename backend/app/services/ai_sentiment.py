"""AI sentiment analysis for inbox replies."""
import structlog
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session

logger = structlog.get_logger()

# Category mapping
CATEGORIES = [
    "interested", "not_interested", "ooo", "question",
    "referral", "do_not_contact", "other",
]
SENTIMENTS = ["positive", "negative", "neutral"]


def analyze_reply_sentiment(body: str, subject: str = "", db: Optional[Session] = None) -> Dict[str, Any]:
    """Analyze an incoming reply to classify category and sentiment.

    Returns {category, sentiment, confidence}.
    """
    if not body:
        return {"category": "other", "sentiment": "neutral", "confidence": 0.0}

    body_lower = body.lower().strip()

    # Rule-based quick checks before hitting AI
    if any(kw in body_lower for kw in ["out of office", "away from", "automatic reply", "auto-reply", "ooo"]):
        return {"category": "ooo", "sentiment": "neutral", "confidence": 0.9}

    if any(kw in body_lower for kw in ["unsubscribe", "remove me", "stop emailing", "do not contact", "opt out"]):
        return {"category": "do_not_contact", "sentiment": "negative", "confidence": 0.95}

    if any(kw in body_lower for kw in ["not interested", "no thank", "not looking", "no need", "pass on this"]):
        return {"category": "not_interested", "sentiment": "negative", "confidence": 0.85}

    if any(kw in body_lower for kw in ["interested", "tell me more", "send me", "let's chat", "set up a call", "schedule", "love to"]):
        return {"category": "interested", "sentiment": "positive", "confidence": 0.85}

    if any(kw in body_lower for kw in ["forward", "refer", "pass this along", "colleague", "right person"]):
        return {"category": "referral", "sentiment": "neutral", "confidence": 0.8}

    # Try AI classification
    if db:
        try:
            from app.services.adapters.ai_content import get_ai_adapter
            adapter = get_ai_adapter(db)

            if adapter:
                prompt = (
                    f"Classify this email reply into one category and sentiment.\n\n"
                    f"Subject: {subject}\n"
                    f"Body: {body[:500]}\n\n"
                    f"Categories: {', '.join(CATEGORIES)}\n"
                    f"Sentiments: {', '.join(SENTIMENTS)}\n\n"
                    f"Reply in format: category|sentiment|confidence (0-1)\n"
                    f"Example: interested|positive|0.9"
                )

                response = adapter._call_api(
                    [{"role": "user", "content": prompt}],
                    max_tokens=50,
                )
                if response and "|" in response:
                    parts = response.strip().split("|")
                    if len(parts) >= 3:
                        cat = parts[0].strip().lower()
                        sent = parts[1].strip().lower()
                        try:
                            conf = float(parts[2].strip())
                        except ValueError:
                            conf = 0.5

                        if cat in CATEGORIES and sent in SENTIMENTS:
                            return {"category": cat, "sentiment": sent, "confidence": conf}

        except Exception as e:
            logger.warning("AI sentiment analysis failed, using default", error=str(e))

    return {"category": "other", "sentiment": "neutral", "confidence": 0.3}
