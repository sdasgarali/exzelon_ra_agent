"""Data management: create/edit/delete leads, contacts and companies; duplicates and merge;
Google Sheet import; saved searches; company exclusions; export summaries.

Deletes are soft (archive) in NeuraLeads, but they are still destructive from the user's point
of view (records vanish from lists, a company delete archives its contacts), so they need an
admin-scoped key and confirm=true.
"""
from __future__ import annotations

import asyncio
import json
from datetime import date, timedelta
from typing import Literal, Optional

from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel, Field

from neuraleads_mcp.runtime import (
    DESTRUCTIVE, READ, WRITE, WRITE_IDEMPOTENT, Runtime, as_items, clamp_limit, compact,
    confirmation_required, items_of, pick,
)

LEAD_FIELDS = ("lead_id", "client_name", "job_title", "state", "posting_date", "job_link", "salary_min",
               "salary_max", "source", "employment_type", "lead_status", "skip_reason", "contact_count",
               "industry", "created_at")
CONTACT_FIELDS = ("contact_id", "first_name", "last_name", "title", "email", "phone", "client_name",
                  "location_state", "linkedin_url", "priority_level", "validation_status",
                  "outreach_status", "source", "lead_ids", "timezone", "created_at")
COMPANY_FIELDS = ("client_id", "client_name", "status", "client_category", "industry", "company_size",
                  "employee_count", "location_state", "website", "domain", "linkedin_url", "headquarters",
                  "description", "founded_year", "phone", "created_at")
EXCLUSION_FIELDS = ("exclusion_id", "company_name", "category", "is_active", "lob_id", "created_at")
Priority = Literal["p1_job_poster", "p2_hr_ta_recruiter", "p3_hr_manager", "p4_ops_leader",
                   "p5_functional_manager"]
MAX_MERGE = 50


class LeadFilters(BaseModel):
    """Filters a saved search stores. Use `query` alone for a natural-language search."""
    query: Optional[str] = Field(None, description="Natural-language search, e.g. 'nurses in Texas over 60k'")
    state: Optional[str] = Field(None, description="US state code, e.g. TX")
    industry: Optional[str] = None
    industries: Optional[list[str]] = None
    job_title: Optional[str] = None
    salary_min: Optional[int] = None
    status: Optional[str] = Field(None, description="Lead status, e.g. new, enriched, validated")
    source: Optional[str] = None
    days_ago: Optional[int] = Field(None, description="Only leads added in the last N days")


def _filters_to_lead_params(filters: dict) -> tuple[dict, list]:
    """Translate saved-search filters to tenant-scoped GET /leads parameters."""
    params: dict = {}
    unsupported = []
    for key, value in filters.items():
        if value in (None, "", []):
            continue
        if key == "state":
            params["state"] = [str(value).upper()]
        elif key == "industry":
            params.setdefault("industry", []).append(value)
        elif key == "industries" and isinstance(value, list):
            params.setdefault("industry", []).extend(value)
        elif key == "job_title":
            params["job_title"] = value
        elif key == "salary_min":
            params["salary_op"], params["salary_value"] = "gte", int(value)
        elif key == "status":
            params["status"] = value
        elif key == "source":
            params["source"] = value
        elif key == "days_ago":
            params["extracted_from"] = (date.today() - timedelta(days=int(value))).isoformat()
        else:
            unsupported.append(key)
    return params, unsupported


def register(mcp: MCPServer, rt: Runtime) -> None:
    write = not rt.settings.read_only

    async def missing_ids(ctx: Context, path_fmt: str, ids: list) -> list:
        """Ids a tenant-scoped GET doesn't find (not in this workspace)."""
        sem = asyncio.Semaphore(8)

        async def check(i: int) -> Optional[int]:
            async with sem:
                try:
                    await rt.get(ctx, path_fmt.format(int(i)))
                    return None
                except ToolError:
                    return i

        return [i for i in await asyncio.gather(*(check(i) for i in ids)) if i is not None]

    async def require_owned(ctx: Context, path_fmt: str, ids: list, what: str) -> None:
        missing = await missing_ids(ctx, path_fmt, ids)
        if missing:
            raise ToolError(f"{what} not found in this workspace: {missing[:20]}")

    # ── leads ───────────────────────────────────────────────────────────
    if write:
        @mcp.tool(annotations=WRITE)
        async def create_lead(
            ctx: Context, client_name: str, job_title: str, state: Optional[str] = None,
            posting_date: Optional[date] = None, job_link: Optional[str] = None,
            salary_min: Optional[float] = None, salary_max: Optional[float] = None,
            source: str = "manual", employment_type: Optional[str] = None,
        ) -> dict:
            """Add a lead (a job posting at a target company) by hand. Duplicate job links are rejected.
            Leads at excluded companies or out of scope are saved with status `excluded` and a
            skip_reason. Counts towards the plan's lead limit; costs no credits."""
            body = compact({"client_name": client_name, "job_title": job_title, "state": state,
                            "posting_date": posting_date.isoformat() if posting_date else None,
                            "job_link": job_link, "salary_min": salary_min, "salary_max": salary_max,
                            "source": source, "employment_type": employment_type})
            return pick(await rt.post(ctx, "/leads", json=body), LEAD_FIELDS)

        @mcp.tool(annotations=WRITE_IDEMPOTENT)
        async def update_lead(
            ctx: Context, lead_id: int, client_name: Optional[str] = None, job_title: Optional[str] = None,
            state: Optional[str] = None, posting_date: Optional[date] = None, job_link: Optional[str] = None,
            salary_min: Optional[float] = None, salary_max: Optional[float] = None,
            employment_type: Optional[str] = None,
        ) -> dict:
            """Edit a lead's details. Only the fields you pass change. Change status with
            update_lead_status."""
            body = compact({"client_name": client_name, "job_title": job_title, "state": state,
                            "posting_date": posting_date.isoformat() if posting_date else None,
                            "job_link": job_link, "salary_min": salary_min, "salary_max": salary_max,
                            "employment_type": employment_type})
            if not body:
                return {"status": "no_change", "message": "Pass at least one field to update."}
            return pick(await rt.put(ctx, f"/leads/{lead_id}", json=body), LEAD_FIELDS)

        @mcp.tool(annotations=DESTRUCTIVE)
        async def delete_lead(ctx: Context, lead_id: int, confirm: bool = False) -> dict:
            """Archive a lead (it leaves every list; contacts are kept). Needs an admin-scoped key.
            Requires confirm=true."""
            lead = pick(await rt.get(ctx, f"/leads/{lead_id}"), ("lead_id", "client_name", "job_title",
                                                                 "lead_status", "contact_count"))
            if not confirm:
                return confirmation_required("delete_lead", lead)
            await rt.delete(ctx, f"/leads/{lead_id}")
            return {"status": "archived", "lead_id": lead_id}

    # ── contacts ────────────────────────────────────────────────────────
    @mcp.tool(annotations=READ)
    async def list_duplicate_contacts(ctx: Context, limit: int = 25) -> dict:
        """Groups of contacts that share an email address — candidates for merge_contacts."""
        data = await rt.get(ctx, "/contacts/duplicates")
        groups = items_of(data, ("duplicates",))[: clamp_limit(limit)]
        return {"total_groups": data.get("total_groups", len(groups)) if isinstance(data, dict) else len(groups),
                "groups": [{"email": g.get("email"), "count": g.get("count"),
                            "contacts": [pick(c, ("contact_id", "first_name", "last_name", "client_name",
                                                  "title", "validation_status", "lead_ids"))
                                         for c in g.get("contacts") or []]} for g in groups]}

    if write:
        @mcp.tool(annotations=WRITE)
        async def create_contact(
            ctx: Context, client_name: str, first_name: str, last_name: str, email: str,
            title: Optional[str] = None, phone: Optional[str] = None, location_state: Optional[str] = None,
            linkedin_url: Optional[str] = None, priority_level: Optional[Priority] = None,
            lead_ids: Optional[list[int]] = None,
        ) -> dict:
            """Add a decision-maker contact by hand (company, first and last name and email are
            required) and optionally link it to leads. Its email is unvalidated until you run
            validate_contact_emails; only valid emails get outreach. Duplicate emails are rejected."""
            ids = list(dict.fromkeys(lead_ids or []))
            if ids:
                # The backend links lead ids without checking they belong to this workspace.
                await require_owned(ctx, "/leads/{}", ids, "Leads")
            body = compact({"client_name": client_name, "first_name": first_name, "last_name": last_name,
                            "email": email, "title": title, "phone": phone, "location_state": location_state,
                            "linkedin_url": linkedin_url, "priority_level": priority_level,
                            "source": "manual", "lead_ids": ids or None})
            return pick(await rt.post(ctx, "/contacts", json=body), CONTACT_FIELDS)

        @mcp.tool(annotations=WRITE_IDEMPOTENT)
        async def update_contact(
            ctx: Context, contact_id: int, client_name: Optional[str] = None, first_name: Optional[str] = None,
            last_name: Optional[str] = None, email: Optional[str] = None, title: Optional[str] = None,
            phone: Optional[str] = None, location_state: Optional[str] = None,
            linkedin_url: Optional[str] = None, priority_level: Optional[Priority] = None,
        ) -> dict:
            """Edit a contact. Only the fields you pass change. Changing the email clears its validation
            status, so it must be validated again before outreach. Unsubscribe and validation status
            can't be changed here."""
            body = compact({"client_name": client_name, "first_name": first_name, "last_name": last_name,
                            "email": email, "title": title, "phone": phone, "location_state": location_state,
                            "linkedin_url": linkedin_url, "priority_level": priority_level})
            if not body:
                return {"status": "no_change", "message": "Pass at least one field to update."}
            if email is not None:
                current = await rt.get(ctx, f"/contacts/{contact_id}")
                if (current.get("email") or "").strip().lower() != email.strip().lower():
                    body["validation_status"] = None  # a new address has not been verified
            return pick(await rt.put(ctx, f"/contacts/{contact_id}", json=body), CONTACT_FIELDS)

        @mcp.tool(annotations=DESTRUCTIVE)
        async def merge_contacts(ctx: Context, primary_contact_id: int, merge_contact_ids: list[int],
                                 confirm: bool = False) -> dict:
            """Merge duplicate contacts into one: the others are archived and their lead links move to
            the primary. Can't be undone from here. Requires confirm=true."""
            ids = [i for i in dict.fromkeys(merge_contact_ids) if i != primary_contact_id]
            if not ids:
                return {"status": "no_change", "message": "merge_contact_ids is empty."}
            if len(ids) > MAX_MERGE:
                return {"status": "rejected", "message": f"At most {MAX_MERGE} contacts per merge."}
            primary = pick(await rt.get(ctx, f"/contacts/{primary_contact_id}"), CONTACT_FIELDS)
            await require_owned(ctx, "/contacts/{}", ids, "Contacts")
            if not confirm:
                return confirmation_required("merge_contacts", {
                    "keep": primary, "archive_contact_ids": ids,
                    "note": "Lead links move to the kept contact; the others are archived."})
            return await rt.post(ctx, "/contacts/merge", json={"primary_contact_id": primary_contact_id,
                                                               "merge_contact_ids": ids})

        @mcp.tool(annotations=DESTRUCTIVE)
        async def delete_contact(ctx: Context, contact_id: int, confirm: bool = False) -> dict:
            """Archive a contact (it leaves every list and gets no more outreach). Needs an admin-scoped
            key. Requires confirm=true."""
            c = pick(await rt.get(ctx, f"/contacts/{contact_id}"),
                     ("contact_id", "first_name", "last_name", "email", "client_name"))
            if not confirm:
                return confirmation_required("delete_contact", c)
            await rt.delete(ctx, f"/contacts/{contact_id}")
            return {"status": "archived", "contact_id": contact_id}

    # ── companies ───────────────────────────────────────────────────────
    if write:
        @mcp.tool(annotations=WRITE)
        async def create_company(
            ctx: Context, client_name: str, industry: Optional[str] = None, company_size: Optional[str] = None,
            location_state: Optional[str] = None, status: Literal["active", "inactive"] = "active",
        ) -> dict:
            """Add a target company. Names must be unique in the workspace. Fill in firmographics later
            with update_company or enrich_company."""
            body = compact({"client_name": client_name, "industry": industry, "company_size": company_size,
                            "location_state": location_state, "status": status})
            return pick(await rt.post(ctx, "/clients", json=body), COMPANY_FIELDS)

        @mcp.tool(annotations=WRITE_IDEMPOTENT)
        async def update_company(
            ctx: Context, company_id: int, client_name: Optional[str] = None,
            status: Optional[Literal["active", "inactive"]] = None, industry: Optional[str] = None,
            company_size: Optional[str] = None, employee_count: Optional[int] = None,
            location_state: Optional[str] = None, headquarters: Optional[str] = None,
            website: Optional[str] = None, domain: Optional[str] = None, linkedin_url: Optional[str] = None,
            description: Optional[str] = None, founded_year: Optional[int] = None, phone: Optional[str] = None,
        ) -> dict:
            """Edit a company's profile. Only the fields you pass change. Contacts and leads are linked
            by company name, so renaming doesn't move them."""
            body = compact({"client_name": client_name, "status": status, "industry": industry,
                            "company_size": company_size, "employee_count": employee_count,
                            "location_state": location_state, "headquarters": headquarters, "website": website,
                            "domain": domain, "linkedin_url": linkedin_url, "description": description,
                            "founded_year": founded_year, "phone": phone})
            if not body:
                return {"status": "no_change", "message": "Pass at least one field to update."}
            return pick(await rt.put(ctx, f"/clients/{company_id}", json=body), COMPANY_FIELDS)

        @mcp.tool(annotations=DESTRUCTIVE)
        async def delete_company(ctx: Context, company_id: int, confirm: bool = False) -> dict:
            """Archive a company AND all of its contacts (matched by company name). Needs an
            admin-scoped key. Requires confirm=true."""
            company = pick(await rt.get(ctx, f"/clients/{company_id}"), ("client_id", "client_name", "status"))
            if not confirm:
                contacts = await rt.get(ctx, "/contacts", client_name=company.get("client_name"), page_size=1)
                return confirmation_required("delete_company", {
                    **company, "contacts_also_archived": contacts.get("total") if isinstance(contacts, dict) else None})
            await rt.delete(ctx, f"/clients/{company_id}")
            return {"status": "archived", "company_id": company_id}

    # ── Google Sheet import ─────────────────────────────────────────────
    @mcp.tool(annotations=READ)
    async def preview_google_sheet_import(ctx: Context, sheet_url: str) -> dict:
        """Read a PUBLIC Google Sheet of job postings (columns like Company Name, Job Title, State, Job
        Link, Contact Name, Email) and show the first rows, total rows and how many are duplicates.
        Imports nothing."""
        return await rt.post(ctx, "/leads/import/google-sheet/preview", json={"sheet_url": sheet_url})

    if write:
        @mcp.tool(annotations=WRITE)
        async def import_google_sheet(ctx: Context, sheet_url: str, skip_duplicates: bool = True,
                                      confirm: bool = False) -> dict:
            """Import leads (and any contacts listed) from a public Google Sheet. Rows whose job link
            already exists are skipped unless skip_duplicates=false; out-of-scope companies are
            skipped. Costs no credits. Requires confirm=true (the first call returns a preview)."""
            if not confirm:
                preview = await rt.post(ctx, "/leads/import/google-sheet/preview", json={"sheet_url": sheet_url})
                return confirmation_required("import_google_sheet", {
                    "sheet_url": sheet_url, "skip_duplicates": skip_duplicates,
                    "total_rows": preview.get("total_rows"), "new_rows": preview.get("new_count"),
                    "duplicates": preview.get("duplicate_count")},
                    preview=(preview.get("preview") or [])[:10])
            return await rt.post(ctx, "/leads/import/google-sheet",
                                 json={"sheet_url": sheet_url, "skip_duplicates": skip_duplicates})

    # ── saved searches ──────────────────────────────────────────────────
    async def saved_search(ctx: Context, search_id: int) -> dict:
        rows = await rt.get(ctx, "/saved-searches")
        found = next((s for s in items_of(rows) if s.get("search_id") == search_id), None)
        if found is None:
            raise ToolError(f"Saved search {search_id} not found (or not shared with you).")
        return found

    def _decode(s: dict) -> dict:
        out = pick(s, ("search_id", "name", "description", "is_shared", "is_own", "created_at"))
        try:
            out["filters"] = json.loads(s.get("filters_json") or "{}")
        except ValueError:
            out["filters"] = {}
        return out

    @mcp.tool(annotations=READ)
    async def list_saved_searches(ctx: Context) -> dict:
        """Your saved lead searches plus ones teammates shared, with their filters."""
        return as_items([_decode(s) for s in items_of(await rt.get(ctx, "/saved-searches"))])

    @mcp.tool(annotations=READ)
    async def run_saved_search(ctx: Context, search_id: int, page: int = 1, page_size: int = 25) -> dict:
        """Run a saved search and return the matching leads in this workspace."""
        s = _decode(await saved_search(ctx, search_id))
        filters = s.get("filters") or {}
        if filters.get("query"):
            data = await rt.post(ctx, "/leads/ai-search", json={"query": filters["query"],
                                                                "limit": clamp_limit(page_size)})
            return {"search": s, **(data if isinstance(data, dict) else {"results": data})}
        params, unsupported = _filters_to_lead_params(filters)
        data = await rt.get(ctx, "/leads", page=max(1, page), page_size=clamp_limit(page_size), **params)
        out = {"search": s, "total": data.get("total"), "page": data.get("page"),
               "items": [pick(lead, LEAD_FIELDS) for lead in items_of(data)]}
        if unsupported:
            out["ignored_filters"] = unsupported
        return out

    if write:
        @mcp.tool(annotations=WRITE)
        async def create_saved_search(ctx: Context, name: str, filters: LeadFilters,
                                      description: Optional[str] = None, is_shared: bool = False) -> dict:
            """Save a lead search under a name (optionally shared with the team). Run it later with
            run_saved_search."""
            f = filters.model_dump(exclude_none=True)
            if not f:
                raise ToolError("Give at least one filter.")
            return _decode(await rt.post(ctx, "/saved-searches", json=compact({
                "name": name, "description": description, "filters_json": json.dumps(f), "is_shared": is_shared})))

        @mcp.tool(annotations=WRITE_IDEMPOTENT)
        async def update_saved_search(ctx: Context, search_id: int, name: Optional[str] = None,
                                      description: Optional[str] = None, filters: Optional[LeadFilters] = None,
                                      is_shared: Optional[bool] = None) -> dict:
            """Rename, re-filter or (un)share one of your saved searches. `filters` replaces the old ones."""
            body = compact({"name": name, "description": description, "is_shared": is_shared,
                            "filters_json": json.dumps(filters.model_dump(exclude_none=True)) if filters else None})
            if not body:
                return {"status": "no_change", "message": "Pass at least one field to update."}
            await rt.put(ctx, f"/saved-searches/{search_id}", json=body)
            return _decode(await saved_search(ctx, search_id))

        @mcp.tool(annotations=DESTRUCTIVE)
        async def delete_saved_search(ctx: Context, search_id: int, confirm: bool = False) -> dict:
            """Delete one of your saved searches. Needs an admin-scoped key. Requires confirm=true."""
            s = _decode(await saved_search(ctx, search_id))
            if not confirm:
                return confirmation_required("delete_saved_search", s)
            return await rt.delete(ctx, f"/saved-searches/{search_id}")

    # ── company exclusions ──────────────────────────────────────────────
    @mcp.tool(annotations=READ)
    async def list_company_exclusions(ctx: Context, search: Optional[str] = None, category: Optional[str] = None,
                                      is_active: Optional[bool] = None, offset: int = 0, limit: int = 50) -> dict:
        """Companies on the do-not-target list (lead sourcing skips them and outreach never reaches
        them while the exclusion is active). Workspace admins only."""
        rows = await rt.get(ctx, "/company-exclusions", search=search, category=category, is_active=is_active,
                            skip=max(0, offset), limit=clamp_limit(limit, 50))
        out = as_items(rows, EXCLUSION_FIELDS)
        counts = await rt.get(ctx, "/company-exclusions/count", search=search, category=category,
                              is_active=is_active)
        if isinstance(out, dict) and isinstance(counts, dict):
            out.update(total=counts.get("total"), active=counts.get("active"))
        return out

    if write:
        @mcp.tool(annotations=WRITE)
        async def add_company_exclusions(ctx: Context, company_names: list[str],
                                         category: Optional[str] = None) -> dict:
            """Add companies (up to 500) to the do-not-target list, e.g. existing customers or
            competitors. Names are matched loosely (Inc/LLC and case ignored); already-excluded ones
            are skipped."""
            names = [n.strip() for n in dict.fromkeys(company_names) if n and n.strip()][:500]
            if not names:
                return {"status": "no_change", "message": "company_names is empty."}
            if len(names) == 1:
                return pick(await rt.post(ctx, "/company-exclusions",
                                          json=compact({"company_name": names[0], "category": category})),
                            EXCLUSION_FIELDS)
            return await rt.post(ctx, "/company-exclusions/bulk", json={
                "companies": [compact({"company_name": n, "category": category}) for n in names]})

        @mcp.tool(annotations=WRITE_IDEMPOTENT)
        async def update_company_exclusion(ctx: Context, exclusion_id: int, is_active: Optional[bool] = None,
                                           company_name: Optional[str] = None,
                                           category: Optional[str] = None) -> dict:
            """Edit an exclusion. is_active=false pauses it (the company can be targeted again) without
            deleting it."""
            body = compact({"is_active": is_active, "company_name": company_name, "category": category})
            if not body:
                return {"status": "no_change", "message": "Pass at least one field to update."}
            return pick(await rt.put(ctx, f"/company-exclusions/{exclusion_id}", json=body), EXCLUSION_FIELDS)

        @mcp.tool(annotations=DESTRUCTIVE)
        async def remove_company_exclusion(ctx: Context, exclusion_id: int, confirm: bool = False) -> dict:
            """Delete an exclusion for good, so the company can be sourced and emailed again. Needs an
            admin-scoped key. Requires confirm=true."""
            if not confirm:
                return confirmation_required("remove_company_exclusion", {
                    "exclusion_id": exclusion_id,
                    "note": "The company becomes eligible for lead sourcing and outreach again. "
                            "update_company_exclusion(is_active=false) pauses it instead."})
            return await rt.delete(ctx, f"/company-exclusions/{exclusion_id}")

    # ── export summary ──────────────────────────────────────────────────
    @mcp.tool(annotations=READ)
    async def export_summary(
        ctx: Context, entity: Literal["leads", "contacts", "companies"], search: Optional[str] = None,
        status: Optional[str] = None, states: Optional[list[str]] = None, company: Optional[str] = None,
        validation_status: Optional[Literal["valid", "invalid", "catch_all", "unknown"]] = None,
        sample_size: int = 10,
    ) -> dict:
        """How many records an export would contain, plus the first rows, for leads, contacts or
        companies. Files aren't produced here; download the CSV from the NeuraLeads web app."""
        n = max(1, min(sample_size, 50))
        if entity == "leads":
            data = await rt.get(ctx, "/leads", search=search, status=status, state=states, client_name=company,
                                page=1, page_size=n)
            fields, page = LEAD_FIELDS, "leads"
        elif entity == "contacts":
            data = await rt.get(ctx, "/contacts", search=search, client_name=company,
                                validation_status=validation_status,
                                state=states[0] if states else None, page=1, page_size=n)
            fields, page = CONTACT_FIELDS, "contacts"
        else:
            data = await rt.get(ctx, "/clients", search=search, location_state=states[0] if states else None,
                                skip=0, limit=n)
            fields, page = COMPANY_FIELDS, "clients"
        rows = items_of(data)
        total = data.get("total") if isinstance(data, dict) else None
        return {"entity": entity, "total": total if total is not None else len(rows),
                "sample": [pick(r, fields) for r in rows[:n]],
                "full_export": f"Download the full CSV in NeuraLeads: {rt.app_url}/dashboard/{page} → Export."}
