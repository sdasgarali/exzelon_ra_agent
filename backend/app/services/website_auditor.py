"""Website Auditor — combines PageSpeed + BuiltWith data for Digital Marketing LOB.

Generates comprehensive website audit reports stored as JSON on lead metadata.
Used to identify prospects with poor web presence for digital marketing outreach.
"""
import json
import structlog
from datetime import datetime
from typing import Dict, Any, Optional, List

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.settings_resolver import get_tenant_setting

logger = structlog.get_logger()


def run_website_audit(
    domain: str,
    db: Optional[Session] = None,
    tenant_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Run a full website audit combining PageSpeed and BuiltWith data.

    Args:
        domain: Website domain to audit (e.g., "example.com")
        db: Optional DB session for API key lookups
        tenant_id: Optional tenant context

    Returns:
        Audit report dict with scores, issues, and recommendations.
    """
    report = {
        "domain": domain,
        "audit_date": datetime.utcnow().isoformat(),
        "performance": None,
        "tech_profile": None,
        "overall_score": 0,
        "issues": [],
        "recommendations": [],
        "audit_status": "pending",
    }

    # PageSpeed audit
    try:
        from app.services.adapters.lead_sources.pagespeed import PageSpeedAdapter
        google_key = ""
        if db:
            google_key = get_tenant_setting(db, "google_places_api_key", tenant_id=tenant_id) or settings.GOOGLE_PLACES_API_KEY
        adapter = PageSpeedAdapter(api_key=google_key)
        results = adapter.audit_domains([domain], strategy="mobile")
        if results:
            perf_data = results[0].get("metadata", {})
            report["performance"] = {
                "performance_score": perf_data.get("performance_score"),
                "accessibility_score": perf_data.get("accessibility_score"),
                "best_practices_score": perf_data.get("best_practices_score"),
                "seo_score": perf_data.get("seo_score"),
                "fcp_ms": perf_data.get("fcp_ms"),
                "lcp_ms": perf_data.get("lcp_ms"),
                "cls": perf_data.get("cls"),
                "tbt_ms": perf_data.get("tbt_ms"),
                "speed_index_ms": perf_data.get("speed_index_ms"),
            }

            # Generate performance issues
            _analyze_performance(report)
    except Exception as e:
        logger.warning("website_audit_pagespeed_error", domain=domain, error=str(e))
        report["issues"].append({"category": "performance", "severity": "info", "message": "PageSpeed audit unavailable"})

    # BuiltWith tech profile
    try:
        from app.services.adapters.lead_sources.builtwith import BuiltWithAdapter
        bw_key = ""
        if db:
            bw_key = get_tenant_setting(db, "builtwith_api_key", tenant_id=tenant_id) or settings.BUILTWITH_API_KEY
        if bw_key:
            adapter = BuiltWithAdapter(api_key=bw_key)
            result = adapter._lookup_domain(domain)
            if result:
                tech_meta = result.get("metadata", {})
                report["tech_profile"] = {
                    "tech_stack": tech_meta.get("tech_stack", []),
                    "cms": tech_meta.get("cms", []),
                    "frameworks": tech_meta.get("frameworks", []),
                    "analytics": tech_meta.get("analytics", []),
                }
                _analyze_tech_stack(report)
    except Exception as e:
        logger.warning("website_audit_builtwith_error", domain=domain, error=str(e))

    # Calculate overall score
    report["overall_score"] = _calculate_overall_score(report)
    report["audit_status"] = "completed"

    # Generate recommendations
    _generate_recommendations(report)

    logger.info("website_audit_completed", domain=domain, score=report["overall_score"])
    return report


def _analyze_performance(report: Dict[str, Any]) -> None:
    """Analyze PageSpeed data and add issues."""
    perf = report.get("performance") or {}

    perf_score = perf.get("performance_score")
    if perf_score is not None:
        if perf_score < 0.3:
            report["issues"].append({
                "category": "performance",
                "severity": "critical",
                "message": f"Very poor performance score ({int(perf_score * 100)}/100) — site is likely losing visitors",
            })
        elif perf_score < 0.5:
            report["issues"].append({
                "category": "performance",
                "severity": "high",
                "message": f"Below-average performance ({int(perf_score * 100)}/100) — significant room for improvement",
            })

    lcp = perf.get("lcp_ms", 0)
    if lcp > 4000:
        report["issues"].append({
            "category": "performance",
            "severity": "high",
            "message": f"Largest Contentful Paint is {lcp}ms (should be under 2500ms) — main content loads slowly",
        })

    cls = perf.get("cls", 0)
    if cls > 0.25:
        report["issues"].append({
            "category": "performance",
            "severity": "medium",
            "message": f"Cumulative Layout Shift is {cls:.3f} (should be under 0.1) — page elements jump around",
        })

    seo_score = perf.get("seo_score")
    if seo_score is not None and seo_score < 0.7:
        report["issues"].append({
            "category": "seo",
            "severity": "high",
            "message": f"SEO score is {int(seo_score * 100)}/100 — search engine visibility is compromised",
        })

    access_score = perf.get("accessibility_score")
    if access_score is not None and access_score < 0.7:
        report["issues"].append({
            "category": "accessibility",
            "severity": "medium",
            "message": f"Accessibility score is {int(access_score * 100)}/100 — may exclude users with disabilities",
        })


def _analyze_tech_stack(report: Dict[str, Any]) -> None:
    """Analyze technology stack and add issues."""
    tech = report.get("tech_profile") or {}

    cms_list = tech.get("cms", [])
    analytics = tech.get("analytics", [])
    frameworks = tech.get("frameworks", [])

    # Check for outdated CMS
    outdated_cms = {"WordPress 4", "WordPress 3", "Drupal 7", "Drupal 6", "Joomla 2", "Joomla 1"}
    for cms in cms_list:
        for old in outdated_cms:
            if old.lower() in cms.lower():
                report["issues"].append({
                    "category": "technology",
                    "severity": "high",
                    "message": f"Outdated CMS detected ({cms}) — security vulnerabilities and performance issues likely",
                })

    # Check for missing analytics
    has_ga = any("google analytics" in a.lower() or "gtag" in a.lower() or "ga4" in a.lower() for a in analytics)
    if not has_ga and not analytics:
        report["issues"].append({
            "category": "analytics",
            "severity": "medium",
            "message": "No analytics tracking detected — business is flying blind on web traffic",
        })

    # Check for jQuery dependency (potential modernization opportunity)
    has_jquery = any("jquery" in f.lower() for f in frameworks)
    if has_jquery:
        report["issues"].append({
            "category": "technology",
            "severity": "low",
            "message": "jQuery detected — consider modern JavaScript framework for better performance",
        })


def _calculate_overall_score(report: Dict[str, Any]) -> int:
    """Calculate overall audit score (0-100)."""
    perf = report.get("performance") or {}

    scores = []
    if perf.get("performance_score") is not None:
        scores.append(perf["performance_score"] * 100)
    if perf.get("seo_score") is not None:
        scores.append(perf["seo_score"] * 100)
    if perf.get("accessibility_score") is not None:
        scores.append(perf["accessibility_score"] * 100)
    if perf.get("best_practices_score") is not None:
        scores.append(perf["best_practices_score"] * 100)

    if not scores:
        return 0

    # Deduct for tech issues
    issue_penalty = len([i for i in report.get("issues", []) if i["severity"] in ("critical", "high")]) * 5
    avg = sum(scores) / len(scores)
    return max(0, min(100, int(avg - issue_penalty)))


def _generate_recommendations(report: Dict[str, Any]) -> None:
    """Generate actionable recommendations based on issues found."""
    issues = report.get("issues", [])
    perf = report.get("performance") or {}
    overall = report.get("overall_score", 0)

    if overall < 50:
        report["recommendations"].append(
            "Website needs significant optimization — a comprehensive redesign should be considered"
        )

    for issue in issues:
        if issue["severity"] == "critical" and "performance" in issue["category"]:
            report["recommendations"].append(
                "Optimize images, enable compression, and implement lazy loading to improve load times"
            )
            break

    if any(i["category"] == "seo" for i in issues):
        report["recommendations"].append(
            "Implement proper meta tags, structured data, and improve content hierarchy for SEO"
        )

    if any(i["category"] == "analytics" for i in issues):
        report["recommendations"].append(
            "Set up Google Analytics 4 and Google Search Console to track traffic and search performance"
        )

    if any(i["category"] == "technology" and "outdated" in i.get("message", "").lower() for i in issues):
        report["recommendations"].append(
            "Upgrade CMS to latest version or consider migration to a modern platform"
        )

    if not report["recommendations"]:
        report["recommendations"].append(
            "Website is in reasonable shape — focus on content strategy and conversion rate optimization"
        )


def store_audit_on_lead(db: Session, lead_id: int, audit_report: Dict[str, Any]) -> bool:
    """Store audit report as metadata on a lead record.

    Merges audit data into existing metadata_json.
    """
    from app.db.models.lead import LeadDetails

    lead = db.query(LeadDetails).filter(LeadDetails.lead_id == lead_id).first()
    if not lead:
        return False

    try:
        existing_meta = json.loads(lead.metadata_json) if lead.metadata_json else {}
    except (json.JSONDecodeError, TypeError):
        existing_meta = {}

    existing_meta["website_audit"] = audit_report
    lead.metadata_json = json.dumps(existing_meta)
    db.commit()
    return True
