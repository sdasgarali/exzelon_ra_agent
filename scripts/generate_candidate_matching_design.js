/* Generates: Candidate_Matching_Design.docx
 * Design & planning doc for the Job<->Candidate Matching (fit>80%) capability.
 * Run: NODE_PATH="C:/Users/Anas/AppData/Roaming/npm/node_modules" node scripts/generate_candidate_matching_design.js
 */
const fs = require('fs');
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  AlignmentType, HeadingLevel, BorderStyle, WidthType, ShadingType,
  LevelFormat, PageBreak, Header, Footer, PageNumber, TabStopType, TabStopPosition,
} = require('docx');

const CONTENT_W = 9360; // US Letter, 1" margins
const NAVY = '1F3864', BLUE = '2E75B6', AMBER = 'B45F06', GRAY = '595959';

// ---------- helpers ----------
const H1 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun(t)] });
const H2 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun(t)] });
const H3 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_3, children: [new TextRun(t)] });
const P = (runs, opts = {}) => new Paragraph({
  spacing: { after: 120, line: 276 }, ...opts,
  children: Array.isArray(runs) ? runs : [new TextRun(runs)],
});
const T = (t, o = {}) => new TextRun({ text: t, ...o });
const bullet = (runs, level = 0) => new Paragraph({
  numbering: { reference: 'bul', level },
  spacing: { after: 60, line: 264 },
  children: Array.isArray(runs) ? runs : [new TextRun(runs)],
});
const num = (runs) => new Paragraph({
  numbering: { reference: 'ord', level: 0 }, spacing: { after: 60, line: 264 },
  children: Array.isArray(runs) ? runs : [new TextRun(runs)],
});
// monospace block for ASCII wireframes / code
const mono = (text, size = 15) => text.split('\n').map((ln) => new Paragraph({
  spacing: { after: 0, line: 200 },
  children: [new TextRun({ text: ln || ' ', font: 'Consolas', size })],
}));
const border = { style: BorderStyle.SINGLE, size: 1, color: 'BFBFBF' };
const borders = { top: border, bottom: border, left: border, right: border,
  insideHorizontal: border, insideVertical: border };
function table(headers, rows, widths) {
  const cw = widths;
  const cell = (txt, opts = {}) => new TableCell({
    width: { size: opts.w, type: WidthType.DXA },
    shading: opts.fill ? { fill: opts.fill, type: ShadingType.CLEAR } : undefined,
    margins: { top: 60, bottom: 60, left: 100, right: 100 },
    children: (Array.isArray(txt) ? txt : [txt]).map((line, i) => new Paragraph({
      spacing: { after: 0, line: 248 },
      children: [new TextRun({ text: line, bold: opts.head === true, color: opts.head ? 'FFFFFF' : '000000', size: 18 })],
    })),
  });
  const headRow = new TableRow({ tableHeader: true, children: headers.map((h, i) => cell(h, { w: cw[i], head: true, fill: NAVY })) });
  const bodyRows = rows.map((r, ri) => new TableRow({
    children: r.map((c, i) => cell(c, { w: cw[i], fill: ri % 2 ? 'F2F5FA' : 'FFFFFF' })),
  }));
  return new Table({ width: { size: CONTENT_W, type: WidthType.DXA }, columnWidths: cw, borders, rows: [headRow, ...bodyRows] });
}
const spacer = () => new Paragraph({ spacing: { after: 80 }, children: [new TextRun('')] });

// ---------- document body ----------
const body = [];

// Title block
body.push(new Paragraph({ spacing: { before: 1200, after: 60 }, children: [new TextRun({ text: 'Candidate–Job Matching Engine', bold: true, size: 52, color: NAVY, font: 'Arial' })] }));
body.push(new Paragraph({ spacing: { after: 40 }, children: [new TextRun({ text: 'Attaching best-fit, actively-looking candidates (fit > 80%) to every sourced job', size: 26, color: BLUE })] }));
body.push(new Paragraph({ spacing: { after: 40 }, children: [new TextRun({ text: 'Deep-research approach, cost model, architecture & UX design', size: 22, color: GRAY })] }));
body.push(new Paragraph({ spacing: { after: 40 }, children: [new TextRun({ text: 'Exzelon RA Agent  ·  Planning & Design Document  ·  v1.0  ·  2026-07-21', size: 20, color: GRAY })] }));
body.push(new Paragraph({ children: [new PageBreak()] }));

// Exec summary
body.push(H1('1. Executive Summary'));
body.push(P([
  T('This document specifies a new capability for the Exzelon RA Agent: for each sourced job posting (a hiring req at a target company), automatically find '),
  T('active, best-fit candidates', { bold: true }),
  T(', compute an explainable '),
  T('0–100 fit score', { bold: true }),
  T(', and surface only matches '),
  T('above 80%', { bold: true }),
  T(' — turning a one-sided lead list into a two-sided staffing marketplace. Ready candidates per open role is the single strongest accelerator of a staffing agency’s sales motion ("we already have 5 candidates >80% fit for your role").'),
]));
body.push(P([T('The recommended design is a ', {}), T('four-stage hybrid pipeline', { bold: true }),
  T(' (hard gates → cheap vector shortlist → cheap-LLM rubric re-score → calibrated fit score → threshold 80). It is the industry-standard "retrieve-then-rerank" cascade and is what keeps cost near zero: the expensive model only ever sees a pre-narrowed top-10 per job, never the full job×candidate cross-product.')]));
body.push(P([T('Headline cost: ', { bold: true }),
  T('embeddings and vector search are $0 (self-hosted), and the LLM re-rank scores '),
  T('1,000 jobs for ≈ $1.70', { bold: true }),
  T(' on gpt-4.1-nano / Gemini Flash-Lite — or effectively '),
  T('$0 on the Groq free tier', { bold: true }),
  T('. The costly part is candidate DATA, minimised by using Indeed Smart Sourcing (~$3–4 per active candidate) for the bulk of non-IT roles and a low-cost API (PDL) only for the manager/professional slice.')]));
body.push(P([T('~85% of the build reuses existing infrastructure', { bold: true }),
  T(' (contact-discovery adapters, send-gate, campaign engine, mailboxes, email validation). Net-new work is a Candidate model, a Job–Candidate match table, an embeddings client, the matching pipeline, and the candidate UI.')]));

// Business context
body.push(H1('2. Business Context & Objective'));
body.push(P([T('Today the RA Agent sources job postings and pitches the '), T('hiring company', { bold: true }), T(' (the job poster / decision-maker) on Exzelon’s staffing services. This feature adds the '), T('supply side', { bold: true }), T(': for each open req, source and rank job-seekers who could fill it.')]));
body.push(H3('Objective'));
body.push(bullet([T('For every job/lead, attach a ranked list of candidates with an explainable fit score, filtered to '), T('> 80%', { bold: true }), T('.')]));
body.push(bullet('Prioritise candidates who are actively looking (open-to-work / recent activity).'));
body.push(bullet('Enable compliant outreach to matched candidates, reusing existing send infrastructure.'));
body.push(bullet('Achieve the above at minimum cost and minimum new infrastructure.'));
body.push(H3('ICP reminder (drives every data/source decision)'));
body.push(P('Non-IT / mid-market roles at companies ≤ 200 employees: operations, manufacturing, construction, logistics/warehouse, HR, admin, finance/accounting managers, skilled trades, retail management. This ICP is decisive — it rules out IT-centric and B2B-sales data sources and favours resume-database sources with strong blue-collar/hourly coverage.'));

// Recommended approach / architecture
body.push(H1('3. Recommended Approach — Four-Stage Hybrid Pipeline'));
body.push(P([T('Do not score every job against every candidate with an LLM (an O(n·m) blow-up). Instead cascade cheap→precise stages so the LLM only re-ranks a shortlist:')]));
body.push(...mono(
`                 CANDIDATE + JOB TEXT  ──embed(bge-small, $0)──►  vectors in MySQL
                                                        (loaded to a numpy matrix)
   PER JOB
   ┌─ Stage 0  HARD GATES (SQL WHERE) ─────────────────────────────────────────┐
   │  work-auth · location/relocation · must-have skill · seniority floor ·      │
   │  salary sanity        →  drops ineligible candidates, shrinks the pool      │
   └────────────────────────────────────────────────────────────────────────────┘
                 │
   ┌─ Stage 1  VECTOR SHORTLIST ────────────────────────────────────────────────┐
   │  job_vec · candidate_matrix  (numpy matmul, <10 ms)  →  cosine top-K (K≈10)  │
   └────────────────────────────────────────────────────────────────────────────┘
                 │
   ┌─ Stage 2  LLM RUBRIC RE-SCORE  (only K calls / job) ───────────────────────┐
   │  cheap LLM (gpt-4.1-nano / Gemini Flash-Lite / Groq) with typed-JSON rubric  │
   │  →  per-criterion sub-scores 0–1 + short rationale                           │
   └────────────────────────────────────────────────────────────────────────────┘
                 │
   ┌─ Stage 3  DETERMINISTIC FIT SCORE (calibrated, explainable) ───────────────┐
   │  weighted rubric → GATE CAPS → sigmoid spread → Platt calibration →          │
   │  bounded ±5 LLM nudge  →  fit_0_100 + contribution breakdown + confidence    │
   └────────────────────────────────────────────────────────────────────────────┘
                 │
   OUTPUT   matches where  fit ≥ 80   with reasons-for / reasons-against`, 15));
body.push(spacer());
body.push(P([T('Why hybrid wins: ', { bold: true }), T('a bi-encoder (embeddings) compresses each text independently — fast enough to scan the whole pool but loses cross-interaction; an LLM/cross-encoder reads the (job, candidate) pair jointly and is far more accurate but 10–100× more expensive per pair. Use the cheap encoder for recall, spend the expensive judge only on the top-K. This single decision cuts LLM calls ~500× versus scoring all pairs.')]));

// Data sourcing
body.push(H1('4. Candidate Data Sourcing (Minimum Cost)'));
body.push(P('The core tension: contact-ready candidate data WITH an "actively looking" signal is expensive; cheap sources are either employer-side (job ads) or lack the active signal. Pricing below is 2026, cited in the appendix.'));
body.push(table(
  ['Source', 'Data + active signal', 'Non-IT fit', 'API', 'Pricing (2026)'],
  [
    ['Indeed Smart Sourcing', 'Resume, contact, skills; strong active signal (recency + apply)', 'Excellent (largest US hourly/blue-collar/admin)', 'In-platform (msg credits)', '~$3–4 per contacted candidate'],
    ['Talroo TalentSync', 'First-party frontline/skilled-trades profiles; active', 'Best for blue-collar/trades', 'Data API / hireEZ', 'Quote-based (enterprise)'],
    ['People Data Labs (PDL)', 'Profile + contact; NO native active signal (infer job-change)', 'Broad; skews white-collar', 'Clean REST API', '$0.20–0.28 / profile'],
    ['Coresignal', 'Employee/candidate profile; no live active flag', 'White-collar-heavy', 'REST API', '$0.05–0.20 / record'],
    ['LinkedIn Recruiter', '#OpenToWork = gold-standard signal', 'Broad, white-collar', 'NO data API (InMail only)', '$8,999–$15,000 / seat / yr'],
    ['Apollo / RocketReach / Lusha', 'B2B sales contacts; NO job-seeker intent', 'Poor for blue-collar', 'Yes', 'Wrong data type'],
    ['Proxycurl / Nubela', 'LinkedIn scrape', '—', 'DEAD', 'Shut down Jul 2025 (lawsuit)'],
  ],
  [1700, 2860, 1600, 1500, 1700]));
body.push(spacer());
body.push(H3('Ranked recommendation (lowest-cost blended stack)'));
body.push(num([T('Indeed Smart Sourcing — PRIMARY.', { bold: true }), T(' Cheapest cost-per-active, non-IT/blue-collar candidate (~$3–4 each; ~$3–4k / 1,000). Contact is in-platform (message credits), which fits a match-to-req workflow.')]));
body.push(num([T('Talroo TalentSync — blue-collar depth.', { bold: true }), T(' First-party, active frontline/trades profiles (the exact segment PDL/Apollo cover poorly). Quote-based; worthwhile only if blue-collar is a dominant LOB.')]));
body.push(num([T('PDL API — programmatic top-up.', { bold: true }), T(' Only for manager/professional roles (HR, finance/accounting, ops leaders) where contact coverage is real. ~$200–280 / 1,000 profiles, but no active signal (infer from recent job change).')]));
body.push(H3('Dead-ends & ToS traps'));
body.push(bullet([T('Proxycurl/Nubela is DEAD', { bold: true }), T(' (shut down 2025-07-04 after LinkedIn+Microsoft suit). Scraper successors carry the same legal exposure — do not build on LinkedIn scraping (consistent with prior project findings).')]));
body.push(bullet([T('LinkedIn #OpenToWork is the best signal but has no compliant data API', { bold: true }), T(' and costs $9–15k/seat/yr — great signal, wrong access/cost profile for automation.')]));
body.push(bullet([T('Apollo/RocketReach/Lusha are the wrong data type', { bold: true }), T(' (B2B sales contacts, no job-seeker intent, little blue-collar contactability).')]));
body.push(bullet([T('Google Cloud Talent Solution is a trap by name', { bold: true }), T(' — employer-side job-matching infra, not a candidate database.')]));

// Fit scoring
body.push(H1('5. Fit-Scoring Methodology'));
body.push(P('A calibrated, explainable 0–100 score built from seven weighted signals, capped by hard gates, spread to be discriminative, and calibrated against real outcomes. This is what makes ">80%" trustworthy rather than noisy.'));
body.push(H3('5.1 Scoring rubric (defaults; expose weights as per-role overrides)'));
body.push(table(
  ['#', 'Signal', 'Weight', 'How the 0–1 sub-score is computed'],
  [
    ['1', 'Skills overlap', '28%', 'Must-have-weighted coverage (must-haves ~3× nice-to-have), matched semantically not by exact string'],
    ['2', 'Title / role match', '22%', 'max(rescaled cosine, O*NET/ESCO taxonomy floor) — synonymous titles not punished'],
    ['3', 'Seniority match', '15%', 'Asymmetric kernel exp(−a·under² − b·over²), a>b (under-qualified penalised harder)'],
    ['4', 'Location', '12%', 'Radius bands (≤25mi 1.0 · 25–50 0.7 · 50–100 0.4 · >100 0.1); remote bypasses to 1.0'],
    ['5', 'Industry', '10%', 'Tiered: exact 1.0 / adjacent 0.6 / unrelated 0.2'],
    ['6', 'Salary alignment', '8%', 'Band overlap of candidate expectation vs job band'],
    ['7', 'Active-recency', '5%', 'exp(−ln2 · days_since_active / 30) — 30-day half-life'],
  ],
  [500, 2100, 900, 5860]));
body.push(spacer());
body.push(H3('5.2 Combining formula (why >80 becomes meaningful)'));
body.push(...mono(
`raw       = Σ wᵢ·sᵢ                        # weighted rubric
gate_cap  = min(cap per failed knockout)    # hard-fail→25, soft-fail→50, pass→100
spread    = sigmoid(k·(raw − m))            # k≈8, m≈0.62 : stretch the crowded middle
prob      = platt(spread)                   # logistic fit on historical hire/advance labels
fit       = round(100 · min(prob, gate_cap/100))
fit       = clamp(fit + llm_adjust, 0, gate_cap)   # llm_adjust ∈ [−5,+5], never crosses a gate`, 16));
body.push(spacer());
body.push(bullet([T('Hard gates', { bold: true }), T(' cap disqualified candidates (wrong city, missing must-have, no work-auth) BEFORE spreading — a great résumé in the wrong location cannot score 84.')]));
body.push(bullet([T('Sigmoid/percentile spread', { bold: true }), T(' fixes the mid-range clustering that makes naïve weighted averages pile up at 60–75.')]));
body.push(bullet([T('Platt calibration', { bold: true }), T(' against historical outcomes makes ">80" literally mean ">80% predicted fit", verifiable on a held-out set.')]));
body.push(bullet([T('The LLM only nudges ±5 and never crosses a gate', { bold: true }), T(' — the deterministic score owns the number; the LLM adds qualitative nuance.')]));
body.push(bullet([T('LLM-judge reliability: ', { bold: true }), T('typed JSON schema, rubric decomposed into atomic 0–1 sub-scores, chain-of-thought before scoring (G-Eval), low temperature, few-shot anchors; recalibrate every 60–90 days against a 500+ human-labeled set.')]));
body.push(H3('5.3 Explainability output (per match)'));
body.push(...mono(
`Fit 84/100 · Confidence High (92% complete) · Gates: ALL PASSED
Skills    0.93 ×28% = 26.0  ✓ 8/9 must-haves; missing Go
Title     0.88 ×22% = 19.4  ✓ "Sr DevOps" ≈ target (O*NET 15-1244)
Seniority 1.00 ×15% = 15.0  ✓ exact
Location  0.70 ×12% =  8.4  ⚠ 38 mi, hybrid
Industry  1.00 ×10% = 10.0  ✓ Fintech = Fintech
Salary    0.80 ×8%  =  6.4  ⚠ expects $145–160k vs $130–155k band
Recency   0.50 ×5%  =  2.5  ⚠ last active 30 d`, 16));

// Cost model
body.push(H1('6. Cost Model'));
body.push(P([T('Embeddings self-hosted = $0. Vector shortlist (numpy) = $0. Only the Stage-2 LLM re-rank costs money. Assume ~700 input + 250 output tokens per (job, candidate) call and top-10 re-rank = 10 calls/job → 10,000 calls per 1,000 jobs.')]));
body.push(table(
  ['LLM re-ranker', 'Cost / job (×10 calls)', 'Cost / 1,000 jobs'],
  [
    ['Groq Llama-3.1-8B (paid)', '$0.00055', '$0.55'],
    ['gpt-4.1-nano  (recommended)', '$0.00170', '$1.70'],
    ['Gemini 2.5 Flash-Lite  (recommended)', '$0.00170', '$1.70'],
    ['Groq Llama-3.3-70B (paid)', '$0.00611', '$6.11'],
    ['gpt-4.1-mini', '$0.00680', '$6.80'],
    ['Claude Haiku 4.5', '$0.0195', '$19.50'],
  ],
  [3760, 2800, 2800]));
body.push(spacer());
body.push(bullet([T('Recommended: gpt-4.1-nano or Gemini 2.5 Flash-Lite at $1.70 / 1,000 jobs', { bold: true }), T(' (strong JSON, huge context). Prompt-caching the static ~700-token rubric prefix cuts this further.')]));
body.push(bullet([T('Free option: Groq free tier', { bold: true }), T(' (~30 RPM / 14,400 req/day ≈ 1,440 jobs/day at $0) for low-volume or MVP.')]));
body.push(bullet([T('The alternative — LLM over every pair — is O(n·m): 1,000 jobs × 5,000 candidates ≈ 5,000,000 calls ≈ $850–$9,750 per pass and days of compute. The shortlist collapses that to 10,000 calls (~500× cheaper).', {})]));
body.push(P([T('Bottom line: ', { bold: true }), T('the matching engine’s marginal compute cost is ≈ $1.70 per 1,000 jobs (or $0 on Groq free tier). The real budget line is candidate data acquisition (Section 4).')]));

// Architecture / integration
body.push(H1('7. System Architecture & Codebase Integration'));
body.push(P('The feature slots into the existing pipeline between lead sourcing and outreach, and reuses the current adapter / send-gate / campaign infrastructure.'));
body.push(H3('7.1 Pipeline placement'));
body.push(...mono(
`Lead Sourcing ─► Candidate Matching (NEW) ─► Contact Enrichment ─► Email Validation ─► Outreach
                 • embed + shortlist + score            (hiring managers)      (both recipient types)
                 • attach matches > 80% to each lead`, 16));
body.push(H3('7.2 New data model'));
body.push(bullet([T('candidates', { bold: true }), T(' — candidate_id, tenant_id, name, email (unique/tenant), phone, current_title/company/industry, target_titles, seniority_level, employment_status, skills_json, resume_url, linkedin_url, location_state/city, source, source_id, validation_status, outreach_status, data_type.')]));
body.push(bullet([T('job_candidate_matches', { bold: true }), T(' — match_id, tenant_id, lead_id (FK), candidate_id (FK), fit_score (0–100), fit_breakdown_json, reasoning, matching_run_id, status (pending/matched/outreach_sent/replied/archived); indexes on (tenant_id, lead_id), (tenant_id, candidate_id), (tenant_id, status).')]));
body.push(bullet([T('lead_details.job_description', { bold: true }), T(' — add a LONGTEXT column (needed for semantic matching; capture from job sources where available). Migrate via the existing main.py lifespan ALTER pattern.')]));
body.push(bullet([T('Embeddings', { bold: true }), T(' — store float32 vectors as a BLOB/VECTOR column in MySQL; load to a normalised numpy matrix at process start. MySQL 9 Community can STORE vectors but cannot run distance search (HeatWave-only), so similarity math runs in Python (numpy matmul) — no new DB engine.')]));
body.push(H3('7.3 Reuse vs net-new'));
body.push(table(
  ['Area', 'Reuse (existing)', 'Net-new'],
  [
    ['Candidate sourcing', 'contact_discovery adapters (PDL, Apollo, Proxycurl-class) with a candidate-oriented filter', 'candidate_source factory + Indeed/Talroo adapter'],
    ['Embeddings', '—', 'bge-small (self-host) or OpenAI/Voyage embeddings client'],
    ['Vector search', 'MySQL storage', 'numpy brute-force shortlist (FAISS only >100k vectors)'],
    ['Scoring', 'AI adapters (OpenAI/Gemini/Groq JSON)', 'rubric + gate/spread/Platt calibration'],
    ['Outreach to candidates', 'send_gate, campaign_engine, mailboxes, humanizer, email validation', 'recipient_type flag + candidate email templates + suppression'],
    ['Settings/UI', 'settings tab + roles pattern', 'candidate_matching settings + Candidates UI'],
  ],
  [1700, 4160, 3500]));
body.push(spacer());
body.push(P([T('Effort estimate: ', { bold: true }), T('~1,500 LOC net-new + ~500 LOC of light modifications; roughly 85% of the outreach/sourcing plumbing is reused.')]));

// UX
body.push(H1('8. User-Friendly Design (UX/UI)'));
body.push(P('Synthesised from LinkedIn Recruiter, SeekOut, hireEZ, Gem, Loxo, Bullhorn, Findem, Ashby. Two guiding findings: (1) pair a coarse tier with an optional precise %, and (2) explainability is the #1 differentiator — never ship a black-box score.'));
body.push(H3('8.1 Per-lead "Candidates" panel (master–detail)'));
body.push(...mono(
`┌─ Lead: Sr. Accountant — Acme Mfg (Dallas, TX)      [Job ▸ Contacts ▸ Candidates] ┐
│ Filters: Fit ≥ [===●==] 80  Location[Dallas ▾]  ☑ Open-to-work  Seniority[Any ▾] │
│ Tiers: ● Strong 6   ◐ Good 14   ○ Partial 41        Sort[Fit% ▾]      [Clear]     │
│ ┌ Ranked candidates (61) ─────────────┐  ┌ Detail: Jordan Lee ───────────[X] ┐   │
│ │ ☐ ●92 Strong  Jordan Lee  🟢 Open    │  │ ●92/100  Strong fit                │  │
│ │ ☐ ●88 Strong  Priya N.    🟢 Open    │  │ ─ Why this fits ─────────────────  │  │
│ │ ☐ ◐79 Good    Marcus B.              │  │ ✓ Title: Sr Accountant  (exact)    │  │
│ │ ☐ ◐74 Good    Dana K.  ⚡ Likely reply│ │ ✓ Skills: GAAP, SOX, NetSuite 5/6  │  │
│ │ ...                                  │  │ ◐ Seniority 7 yrs (target 5–8)     │  │
│ │                                      │  │ ✗ Missing: CPA license             │  │
│ │                                      │  │ [◀ Prev][Shortlist ★][Add campaign]│  │
│ └──────────────────────────────────────┘  └────────────────────────────────────┘  │
│ Bulk (3): [★ Shortlist] [✉ Add to candidate campaign] [✕ Dismiss] [⤢ Compare]     │
└────────────────────────────────────────────────────────────────────────────────────┘`, 14));
body.push(spacer());
body.push(H3('8.2 Candidate card (with explainability)'));
body.push(...mono(
`┌──────────────────────────────────────────────────────────────────────┐
│ ☐  ●92 Strong   Jordan Lee            🟢 Open  ⚡ Likely reply          │
│    Sr. Accountant · Dallas, TX · 7 yrs                                  │
│    [GAAP ✓] [SOX ✓] [NetSuite ✓] [CPA ✗]     [★ Shortlist] [✉] [✕]     │
└──────────────────────────────────────────────────────────────────────┘
  hover/focus popover → Title ✓ · Skills 5/6 ✓ · Seniority ◐ · Location ✓ · CPA ✗`, 14));
body.push(spacer());
body.push(H3('8.3 Cross-job "Candidate Pool" dashboard'));
body.push(bullet('Table of candidates × best-matched job with fit, "+N other matches", status, quick actions; toggle to a Kanban by status (New · Shortlisted · Contacted · Replied · Dismissed).'));
body.push(bullet('Surfacing "matches N jobs" prevents double-contacting one person across reqs and helps place them against the best-fit role.'));
body.push(H3('8.4 Key design rules'));
body.push(bullet([T('Fit badge = icon + number + label together', { bold: true }), T(' (never colour alone). Blue→orange scale, not red-green. Strong ● / Good ◐ / Partial ○.')]));
body.push(bullet([T('Hard filters vs weighted criteria', { bold: true }), T(' (Gem’s model): filters set the eligible pool; criteria rank it; a live pool-size preview prevents "filtered to zero".')]));
body.push(bullet([T('Explainability everywhere', { bold: true }), T(' — per-criterion ✓/◐/✗ with plain-language reasons and a Missing-Skills callout; matched keywords highlighted in the résumé timeline.')]));
body.push(bullet([T('Shortlist + one-click outreach in the same surface', { bold: true }), T('; bulk actions on the filtered / "Yes" set; a side-by-side compare table (an unmet gap across competitors).')]));
body.push(bullet([T('Calibration loop', { bold: true }), T(' — a lightweight per-card Yes/No/Maybe with reason capture feeds score retraining.')]));
body.push(H3('8.5 Accessibility & responsive'));
body.push(bullet('Color-blind-safe scores (WCAG 1.4.1): number-as-text + shape + label; blue-orange palette; ≥3:1 lightness between tiers.'));
body.push(bullet('Detail drawer = APG modal dialog: aria-modal, focus trap, Esc closes, focus returns to the card; icon-only buttons get aria-labels; badge aria-label "Match fit: 92 of 100, Strong".'));
body.push(bullet('Score popover holds focusable content → non-modal dialog (not role="tooltip"); keyboard-triggerable, dismissible, hoverable.'));
body.push(bullet('Responsive master-detail: side-by-side wide; list-OR-detail with Back at tablet/phone; drawer becomes a full-screen sheet on mobile; wide tables scroll inside overflow-x-auto with min-w-0. Touch targets ≥ 44px.'));

// Compliance
body.push(H1('9. Compliance & Risk'));
body.push(P([T('Research synthesis, not legal advice — have counsel review the SMS-consent flow and the CCPA "sale/sharing" analysis before launch.', { italics: true })]));
body.push(H3('9.1 Checklist'));
body.push(bullet([T('CAN-SPAM (email): ', { bold: true }), T('real sender identity, non-deceptive subject, valid physical postal address, clear commercial disclosure (no B2B exemption), one-click opt-out live ≥30 days honored ≤10 business days. Penalty up to ~$53,088 per email.')]));
body.push(bullet([T('TCPA (SMS/calls): ', { bold: true }), T('do NOT cold-text sourced candidates without prior express written consent; restrict marketing SMS to opted-in (applied/replied); honor STOP/HELP + quiet hours. $500–$1,500 per message, private right of action. (The FCC "one-to-one consent" rule was vacated Jan 2025; the written-consent requirement still stands.)')]));
body.push(bullet([T('CCPA/CPRA + ~20 state laws: ', { bold: true }), T('serve a notice at collection (applicant data has been fully in scope since Jan 2023); provide "Do Not Sell/Share" and honor Global Privacy Control (mandatory in 12 states from Jan 1, 2026); do not use sensitive PI for outreach.')]));
body.push(bullet([T('GDPR (EU candidates): ', { bold: true }), T('complete a Legitimate Interest Assessment; serve an Article 14 notice at first contact; check member-state ePrivacy email rules.')]));
body.push(bullet([T('Governance: ', { bold: true }), T('a global permanent suppression list (opt-outs/STOP/bounces/complaints) across all campaigns/mailboxes/tenants; data minimisation; retention limits; audit trail of source + consent + opt-out.')]));
body.push(H3('9.2 Safe vs risky sources'));
body.push(table(
  ['Source', 'Risk', 'Why'],
  [
    ['Direct applicants (your ATS)', 'SAFE', 'Direct relationship, lawful basis, no third-party ToS'],
    ['Consent-based candidate networks', 'SAFE', 'Meets GDPR/CCPA consent with an auditable ledger'],
    ['Licensed providers (right-to-use)', 'SAFE*', 'Verify the license grants outreach + honors erasure'],
    ['#OpenToWork inside LinkedIn Recruiter', 'MODERATE', 'Compliant in-platform; exporting/scraping it breaks the User Agreement'],
    ['Purchased lists (unknown provenance)', 'RISKY', 'No verifiable consent; CAN-SPAM/GDPR/CCPA exposure'],
    ['Scraped resume DBs used off-platform', 'RISKY', 'Indeed/ZipRecruiter ban pooling/reuse outside the hiring purpose'],
    ['Scraped LinkedIn (bots/fake accounts)', 'HIGH', 'The hiQ / Mantheos fact pattern: breach of contract, state law, bans'],
  ],
  [3200, 1300, 4860]));
body.push(spacer());
body.push(P([T('The hiQ takeaway: ', { bold: true }), T('"public data isn’t a CFAA crime" (9th Cir., 2022) is NOT a green light to scrape LinkedIn — hiQ still lost on breach of contract, paid a $500K judgment, and is defunct. The real exposure is contract/ToS + state computer-access law + account bans. Keep to consent-based and licensed sources.')]));

// Phasing / plan
body.push(H1('10. Implementation Plan (Phased)'));
body.push(H3('Phase 0 — Spike (1 week)'));
body.push(bullet('Add job_description capture; stand up the embeddings client (bge-small) + numpy shortlist; prove the pipeline on 50 leads with a small candidate sample (Groq free tier). No UI.'));
body.push(H3('Phase 1 — MVP (2–3 weeks)'));
body.push(bullet('candidates + job_candidate_matches tables; candidate_matching pipeline stage; PDL adapter for manager/professional roles; rubric + gate/spread scoring (Platt deferred); per-lead Candidates tab with ranked cards, fit badge, breakdown popover, filters. Read-only (no candidate outreach yet).'));
body.push(H3('Phase 2 — Outreach + depth (3–4 weeks)'));
body.push(bullet('Indeed Smart Sourcing (+ Talroo if blue-collar LOB); recipient_type in campaign/send-gate + candidate templates + suppression + compliance (opt-out, postal address, GPC); Candidate Pool dashboard + Kanban; compare table; calibration loop (Platt on collected labels).'));
body.push(H3('Phase 3 — Optimise'));
body.push(bullet('Prompt caching; per-role weight overrides; FAISS if the pool crosses ~100k vectors; recalibration cadence (60–90 days).'));

// Open decisions
body.push(H1('11. Open Decisions'));
body.push(num('Candidate data budget & primary source: confirm Indeed Smart Sourcing (in-platform contact) vs an API-first path (PDL) for the first LOBs.'));
body.push(num('Embeddings: self-host bge-small ($0, needs a small model runtime) vs OpenAI/Voyage API ($0.02/1M, zero ops).'));
body.push(num('LLM re-ranker: Groq free tier (MVP, rate-limited) vs gpt-4.1-nano / Gemini Flash-Lite ($1.70/1k).'));
body.push(num('Candidate outreach in scope for v1, or matching-only (present candidates to the client) first?'));
body.push(num('Fit threshold default (80) and whether it is tenant-configurable (recommended 60–95 range).'));

// Appendix sources
body.push(H1('Appendix — Key Sources'));
const src = (label, url) => new Paragraph({ spacing: { after: 40 }, children: [new TextRun({ text: label + ': ', bold: true, size: 18 }), new TextRun({ text: url, size: 18, color: BLUE })] });
body.push(H3('Data sources & pricing'));
body.push(src('Indeed pricing', 'hiretruffle.com/blog/indeed-pricing'));
body.push(src('ZipRecruiter pricing', 'checkthat.ai/brands/ziprecruiter/pricing'));
body.push(src('Monster+ pricing', 'hiring.monster.com/pricing-3'));
body.push(src('PDL credit pricing', 'support.peopledatalabs.com — Pricing/credits'));
body.push(src('Coresignal pricing', 'coresignal.com/pricing'));
body.push(src('Proxycurl shutdown', 'linkedapi.io/guides/proxycurl-alternatives'));
body.push(H3('Matching, embeddings & cost'));
body.push(src('Retrieve-then-rerank', 'pinecone.io/learn/series/rag/rerankers · sbert.net'));
body.push(src('LLM-as-judge (G-Eval)', 'arXiv:2303.16634 · futureagi.com/blog'));
body.push(src('Cosine anisotropy', 'arXiv:2504.16318 · mixpeek.com/guides/embedding-space-geometry'));
body.push(src('Embeddings', 'huggingface.co/BAAI/bge-small-en-v1.5 · blog.voyageai.com · openai.com'));
body.push(src('MySQL VECTOR limits', 'dev.mysql.com/doc/refman/9.7/en/vector-functions.html · bugs.mysql.com/115846'));
body.push(src('LLM pricing', 'pricepertoken.com · aicostcheck.com · klymentiev.com/blog/groq-pricing'));
body.push(H3('Compliance & UX'));
body.push(src('CAN-SPAM / FTC penalties', 'ftc.gov — CAN-SPAM guide · 2025 penalty amounts'));
body.push(src('TCPA / one-to-one vacated', 'crowell.com — Facebook v. Duguid · daypitney.com'));
body.push(src('CCPA applicant scope / 2026 laws', 'healthlawadvisor.com · multistate.us'));
body.push(src('hiQ v. LinkedIn', 'cdn.ca9.uscourts.gov — 17-16783 · privacyworld.blog'));
body.push(src('UX patterns', 'help.gem.com · support.seekout.com · docs.ashbyhq.com · kb.bullhorn.com'));
body.push(src('Accessibility', 'w3.org/WAI — WCAG 1.4.1 / 1.4.13 / 2.5.8 · APG Dialog'));

// ---------- assemble ----------
const doc = new Document({
  creator: 'Exzelon RA Agent',
  title: 'Candidate–Job Matching Engine — Design',
  styles: {
    default: { document: { run: { font: 'Arial', size: 21 } } },
    paragraphStyles: [
      { id: 'Heading1', name: 'Heading 1', basedOn: 'Normal', next: 'Normal', quickFormat: true,
        run: { size: 30, bold: true, color: NAVY, font: 'Arial' },
        paragraph: { spacing: { before: 320, after: 160 }, outlineLevel: 0, keepNext: true } },
      { id: 'Heading2', name: 'Heading 2', basedOn: 'Normal', next: 'Normal', quickFormat: true,
        run: { size: 25, bold: true, color: BLUE, font: 'Arial' },
        paragraph: { spacing: { before: 220, after: 120 }, outlineLevel: 1, keepNext: true } },
      { id: 'Heading3', name: 'Heading 3', basedOn: 'Normal', next: 'Normal', quickFormat: true,
        run: { size: 22, bold: true, color: '2A2A2A', font: 'Arial' },
        paragraph: { spacing: { before: 160, after: 80 }, outlineLevel: 2, keepNext: true } },
    ],
  },
  numbering: {
    config: [
      { reference: 'bul', levels: [
        { level: 0, format: LevelFormat.BULLET, text: '•', alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 460, hanging: 260 } } } },
        { level: 1, format: LevelFormat.BULLET, text: '◦', alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 900, hanging: 260 } } } },
      ] },
      { reference: 'ord', levels: [
        { level: 0, format: LevelFormat.DECIMAL, text: '%1.', alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 460, hanging: 260 } } } },
      ] },
    ],
  },
  sections: [{
    properties: { page: { size: { width: 12240, height: 15840 }, margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 } } },
    footers: { default: new Footer({ children: [new Paragraph({
      tabStops: [{ type: TabStopType.RIGHT, position: TabStopPosition.MAX }],
      children: [
        new TextRun({ text: 'Exzelon RA Agent — Candidate Matching Design (Confidential)', size: 16, color: GRAY }),
        new TextRun({ text: '\tPage ', size: 16, color: GRAY }),
        new TextRun({ children: [PageNumber.CURRENT], size: 16, color: GRAY }),
      ],
    })] }) },
    children: body,
  }],
});

Packer.toBuffer(doc).then((buf) => {
  fs.writeFileSync('Candidate_Matching_Design.docx', buf);
  console.log('WROTE Candidate_Matching_Design.docx (' + buf.length + ' bytes)');
});
