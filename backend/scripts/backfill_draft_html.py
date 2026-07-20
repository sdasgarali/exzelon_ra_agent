"""One-time backfill: convert existing outreach_drafts bodies to native HTML.

Older drafts stored the message as plain text (\\n newlines) with an HTML
signature appended, so newlines collapsed in HTML views. This rewrites each
draft's body_html / original_body_html so the message uses <br> (native HTML),
leaving the signature block untouched. Idempotent (drafts already HTML are
skipped). Dry-run by default; pass --commit to apply.

Usage:
  python scripts/backfill_draft_html.py            # dry-run
  python scripts/backfill_draft_html.py --commit   # apply
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.db.base import SessionLocal
from app.db.models.outreach_draft import OutreachDraft
from app.services.email_humanizer import _split_signature
from app.services.email_preview_service import _message_to_html


def _to_native_html(body):
    """Convert a draft body to native HTML: message -> <br>, signature kept."""
    if not body:
        return body
    message, signature = _split_signature(body)
    return _message_to_html(message) + signature


def main(commit: bool) -> None:
    db = SessionLocal()
    try:
        drafts = db.query(OutreachDraft).all()
        changed = 0
        for d in drafts:
            new_html = _to_native_html(d.body_html)
            new_orig = _to_native_html(d.original_body_html)
            if new_html != d.body_html or new_orig != d.original_body_html:
                d.body_html = new_html
                d.original_body_html = new_orig
                changed += 1

        print(f"Drafts scanned  : {len(drafts)}")
        print(f"Drafts rewritten: {changed}")
        if commit:
            db.commit()
            print("COMMITTED.")
        else:
            db.rollback()
            print("DRY-RUN (no changes saved). Re-run with --commit to apply.")
    finally:
        db.close()


if __name__ == "__main__":
    main(commit="--commit" in sys.argv)
