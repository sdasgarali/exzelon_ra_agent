"""Shared outreach email prompts — centralizes the owner's cold email voice and methodology.

All 4 AI adapters (Groq, OpenAI, Anthropic, Gemini) import from here so every
outreach email follows the same AIDA structure and writing style.
"""
from typing import Optional, Dict, Any


OUTREACH_SYSTEM_PROMPT = """You are a senior business development strategist, expert cold email writer, expert recruiter-staffing sales writer.

Write cold outreach emails in a specific voice with these characteristics:
- direct, practical, result-oriented
- respectful but assertive
- natural and human sounding
- not overly polished, not fluffy, not marketing-heavy, not too casual
- sounds like an experienced delivery/project/business leader
- shows ownership, confidence, and execution mindset
- focuses on business value and usefulness

Writing style rules:
- State the main point clearly
- Add context naturally
- Explain the practical benefit
- Stay focused on outcome
- Avoid unnecessary decorative wording
- Avoid robotic or template-heavy language

EMAIL WRITING RULES:
- Keep the email personalized based on the hiring/open roles context
- Mention published open positions naturally, without sounding creepy
- Do not sound like mass spam
- Do not use hype language
- Do not overpromise
- Do not say "best-in-class," "world-class," "cutting-edge," or similar fluff
- Avoid generic openings like "Hope you are doing well"
- Avoid robotic phrases like "I came across your company and was impressed"
- Avoid too many adjectives
- Keep wording plain, strong, and useful
- Make the CTA simple and easy to respond to
- No HTML formatting in the plain text version
- No bold, no bullet points, no markdown formatting in email body
- Short paragraphs (1-2 sentences each), separated by blank lines
- Under 120 words total (excluding signature)

ANTI-PATTERNS — never use these phrases:
- "I hope this finds you well"
- "I wanted to reach out" / "I came across your company"
- "synergy", "leverage", "cutting-edge", "innovative", "game-changer"
- Feature dumps or service listings
- Questions you already know the answer to
- "Let me know if you're interested" (too passive)
- Exclamation marks

SUBJECT LINE RULES:
- Under 50 characters
- No clickbait, no ALL CAPS, no hype
- Reference something specific (role, company, or situation)
- Natural, plain language

CTA STYLE — prefer these patterns:
- Would it make sense if I send a few matched profiles for your current priority roles?
- If useful, I can share a few relevant candidate profiles for review.
- If hiring is active for these roles, happy to send a few matched candidates.

ANTI-AI-DETECTION (critical — your email WILL be flagged if you ignore these):
- Write as if you're a busy sales rep typing on your phone between meetings.
- Vary sentence length — mix very short (3-5 words) with longer sentences.
- Include one natural imperfection per email (a dash, ellipsis, or parenthetical aside).
- NEVER start with "I hope this email finds you well" or "I wanted to reach out" — these are AI red flags.
- Use first-person observations: "I noticed", "I saw that", "Something caught my eye".
- Contractions are fine but don't use them consistently — mix "I'm" and "I am" naturally.
- Keep it under 120 words. Shorter = more human.
- Avoid uniform sentence length — humans write in bursts (some short, some long).

QUALITY CHECK before responding:
- Does it sound like a real human wrote it?
- Is it direct, practical, ownership-driven?
- Is it relevant to the prospect's hiring need?
- Is it concise but still useful?
- Does it avoid spammy recruiter language?
- Is the CTA easy?
- Would an AI detector flag this? If yes, rewrite."""


def build_outreach_user_prompt(
    contact_name: str,
    contact_title: str,
    company_name: str,
    job_title: str,
    context: Optional[Dict[str, Any]] = None,
    step_number: int = 1,
) -> str:
    """Build the user prompt for outreach email generation.

    Args:
        contact_name: Recipient first name
        contact_title: Recipient job title
        company_name: Recipient company name
        job_title: The open position(s) at their company
        context: Dict with optional keys: industry, location, description,
                 company_size, headquarters, sender_name, sender_title,
                 additional_jobs
        step_number: 1=initial, 2=day-3 follow-up, 3=day-7, 4+=break-up
    """
    ctx = context or {}
    industry = ctx.get("industry") or "their industry"
    location = ctx.get("location") or ""
    description = ctx.get("description") or ""
    company_size = ctx.get("company_size") or ""
    headquarters = ctx.get("headquarters") or ""
    sender_name = ctx.get("sender_name") or "Account Executive"
    sender_title = ctx.get("sender_title") or "Account Executive"
    additional_jobs = ctx.get("additional_jobs") or ""

    # Build the company context block
    company_context_parts = []
    if industry and industry != "their industry":
        company_context_parts.append(f"Industry: {industry}")
    if description:
        company_context_parts.append(f"Description: {description}")
    if company_size:
        company_context_parts.append(f"Company size: {company_size}")
    if headquarters:
        company_context_parts.append(f"Headquarters: {headquarters}")
    company_context_block = "\n".join(company_context_parts) if company_context_parts else "No additional context available."

    # Build open positions block
    positions = job_title
    if additional_jobs:
        positions += f"\n{additional_jobs}"

    if step_number == 1:
        return f"""Write a cold email to offer matched skilled candidates for their published open positions.

--- RECIPIENT ---
Name: {contact_name}
Title: {contact_title}
Company: {company_name}
{f'Location: {location}' if location else ''}

--- THEIR OPEN POSITIONS ---
{positions}

--- CANDIDATE TYPES WE HAVE ---
Staffing/recruitment agency specializing in non-IT roles:
manufacturing, warehouse, logistics, healthcare, skilled trades, hospitality, construction.
We provide temporary, temp-to-hire, and direct-hire staffing solutions.

--- COMPANY CONTEXT ---
{company_context_block}

--- OUR DIFFERENTIATORS ---
- Pre-screened and matched candidates, not random resumes
- Reduce hiring effort, screening time, and time-to-fill
- Flexible: contract, contract-to-hire, or full-time
- Quality-focused and practical to work with

--- SENDER ---
Name: {sender_name}
Title: {sender_title}
Company: Exzelon Inc.

--- OUTPUT FORMAT ---
Respond in this exact format:
SUBJECT: [subject line]
---
[email body — plain HTML with <p> tags only]
---
[email body — plain text version]"""

    elif step_number == 2:
        return f"""Write a SHORT follow-up email (Day 3).

Recipient: {contact_name} ({contact_title}) at {company_name}
Their open role: {job_title}

Rules:
- Completely different angle from the first email
- Do NOT reference "my previous email" or "following up"
- New value point: mention reducing time-to-fill or pre-screened candidates
- Under 80 words
- Plain, direct, human

--- OUTPUT FORMAT ---
Respond in this exact format:
SUBJECT: [subject line]
---
[email body — plain HTML with <p> tags only]
---
[email body — plain text version]"""

    elif step_number == 3:
        return f"""Write a SECOND follow-up email (Day 7).

Recipient: {contact_name} ({contact_title}) at {company_name}
Their open role: {job_title}

Rules:
- Different value proposition from previous emails
- Even shorter and more direct
- Under 60 words
- Could mention flexibility (temp, temp-to-hire, direct) or quality guarantee

--- OUTPUT FORMAT ---
Respond in this exact format:
SUBJECT: [subject line]
---
[email body — plain HTML with <p> tags only]
---
[email body — plain text version]"""

    else:  # step_number >= 4 — break-up
        return f"""Write a BREAK-UP email (final touch).

Recipient: {contact_name} ({contact_title}) at {company_name}
Their open role: {job_title}

Rules:
- Gracious, leave the door open
- Ultra-short, under 50 words
- No guilt, no pressure
- Simple close: "If timing changes, happy to help."

--- OUTPUT FORMAT ---
Respond in this exact format:
SUBJECT: [subject line]
---
[email body — plain HTML with <p> tags only]
---
[email body — plain text version]"""


def parse_ai_email_response(text: str, contact_name: str, job_title: str) -> Dict[str, str]:
    """Parse the SUBJECT/---/body_html/---/body_text format returned by AI.

    Returns dict with keys: subject, body_html, body_text.
    Falls back to safe defaults on parse failure.
    """
    try:
        parts = text.split("---")
        subject = parts[0].replace("SUBJECT:", "").strip()
        body_html = parts[1].strip() if len(parts) > 1 else ""
        body_text = parts[2].strip() if len(parts) > 2 else ""

        # Basic sanity: subject and body must exist
        if not subject or not body_html:
            raise ValueError("Empty subject or body")

        return {
            "subject": subject,
            "body_html": body_html,
            "body_text": body_text or body_html.replace("<p>", "").replace("</p>", "\n").strip(),
        }
    except Exception:
        return {
            "subject": f"Regarding your {job_title} opening",
            "body_html": (
                f"<p>Hi {contact_name},</p>"
                f"<p>I noticed your {job_title} posting and wanted to reach out "
                "about how our staffing services could help.</p>"
                "<p>Best regards</p>"
            ),
            "body_text": (
                f"Hi {contact_name},\n\n"
                f"I noticed your {job_title} posting and wanted to reach out "
                "about how our staffing services could help.\n\n"
                "Best regards"
            ),
        }
