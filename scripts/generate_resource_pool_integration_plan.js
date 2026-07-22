/* Generates: Resource_Pool_Integration_Plan.docx
 * Analysis + plan: integrating the RA Agent (lead-gen/outreach) with the
 * Resource Pool ATS across the 10-step staffing workflow.
 * Run: NODE_PATH="C:/Users/Anas/AppData/Roaming/npm/node_modules" node scripts/generate_resource_pool_integration_plan.js
 */
const fs = require('fs');
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  AlignmentType, HeadingLevel, BorderStyle, WidthType, ShadingType,
  LevelFormat, PageBreak, Footer, PageNumber, TabStopType, TabStopPosition,
} = require('docx');

const CONTENT_W = 9360;
const NAVY = '1F3864', BLUE = '2E75B6', TEAL = '1B7A6E', AMBER = 'B45F06', GREEN = '2E7D32', GRAY = '595959';

const H1 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun(t)] });
const H2 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun(t)] });
const H3 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_3, children: [new TextRun(t)] });
const P = (runs, opts = {}) => new Paragraph({ spacing: { after: 120, line: 276 }, ...opts,
  children: Array.isArray(runs) ? runs : [new TextRun(runs)] });
const T = (t, o = {}) => new TextRun({ text: t, ...o });
const bullet = (runs, level = 0) => new Paragraph({ numbering: { reference: 'bul', level }, spacing: { after: 60, line: 264 },
  children: Array.isArray(runs) ? runs : [new TextRun(runs)] });
const numItem = (runs) => new Paragraph({ numbering: { reference: 'ord', level: 0 }, spacing: { after: 60, line: 264 },
  children: Array.isArray(runs) ? runs : [new TextRun(runs)] });
const mono = (text, size = 15) => text.split('\n').map((ln) => new Paragraph({ spacing: { after: 0, line: 200 },
  children: [new TextRun({ text: ln || ' ', font: 'Consolas', size })] }));
const spacer = () => new Paragraph({ spacing: { after: 80 }, children: [new TextRun('')] });
const border = { style: BorderStyle.SINGLE, size: 1, color: 'BFBFBF' };
const borders = { top: border, bottom: border, left: border, right: border, insideHorizontal: border, insideVertical: border };
function table(headers, rows, widths, opts = {}) {
  const cw = widths;
  const mkcell = (txt, o = {}) => new TableCell({
    width: { size: o.w, type: WidthType.DXA },
    shading: o.fill ? { fill: o.fill, type: ShadingType.CLEAR } : undefined,
    margins: { top: 60, bottom: 60, left: 100, right: 100 },
    children: (Array.isArray(txt) ? txt : String(txt).split('\n')).map((line) => new Paragraph({
      spacing: { after: 0, line: 248 },
      children: [new TextRun({ text: line, bold: o.head === true, color: o.head ? 'FFFFFF' : (o.color || '000000'), size: o.head ? 18 : 17 })],
    })),
  });
  const headRow = new TableRow({ tableHeader: true, children: headers.map((h, i) => mkcell(h, { w: cw[i], head: true, fill: NAVY })) });
  const bodyRows = rows.map((r, ri) => new TableRow({ children: r.map((c, i) => {
    const cellObj = (c && typeof c === 'object' && !Array.isArray(c)) ? c : { t: c };
    return mkcell(cellObj.t, { w: cw[i], fill: cellObj.fill || (ri % 2 ? 'F2F5FA' : 'FFFFFF'), color: cellObj.color });
  }) }));
  return new Table({ width: { size: CONTENT_W, type: WidthType.DXA }, columnWidths: cw, borders, rows: [headRow, ...bodyRows] });
}
// color pills for ownership
const RA = { t: 'RA Agent', fill: 'DCE6F5', color: NAVY };
const RP = { t: 'Resource Pool', fill: 'DBEEE9', color: TEAL };
const BOTH = { t: 'Both (overlap)', fill: 'FCE7D2', color: AMBER };

const body = [];

// Title
body.push(new Paragraph({ spacing: { before: 1100, after: 60 }, children: [new TextRun({ text: 'Integrating the RA Agent with', bold: true, size: 40, color: NAVY, font: 'Arial' })] }));
body.push(new Paragraph({ spacing: { after: 40 }, children: [new TextRun({ text: 'the Resource Pool ATS', bold: true, size: 44, color: NAVY, font: 'Arial' })] }));
body.push(new Paragraph({ spacing: { after: 40 }, children: [new TextRun({ text: 'One end-to-end staffing pipeline across two complementary systems', size: 24, color: BLUE })] }));
body.push(new Paragraph({ spacing: { after: 40 }, children: [new TextRun({ text: 'Analysis, integration architecture & phased plan', size: 22, color: GRAY })] }));
body.push(new Paragraph({ spacing: { after: 40 }, children: [new TextRun({ text: 'Exzelon  ·  Planning & Design Document  ·  v1.0  ·  2026-07-21', size: 20, color: GRAY })] }));
body.push(new Paragraph({ children: [new PageBreak()] }));

// 1. Exec summary
body.push(H1('1. Executive Summary'));
body.push(P([T('This analysis maps Exzelon’s 10-step staffing workflow against two existing systems and recommends how to combine them into a single pipeline:')]));
body.push(bullet([T('RA Agent', { bold: true, color: NAVY }), T(' (this codebase — FastAPI + MySQL): a high-scale '), T('demand-generation & cold-outreach engine', { bold: true }), T(' — job/lead sourcing, contact enrichment, and a mature cold-email campaign system (mailboxes, warm-up, deliverability/send-gate, sequences).')]));
body.push(bullet([T('Resource Pool', { bold: true, color: TEAL }), T(' (Next.js 16 + Prisma + PostgreSQL, port 3002): a production-ready '), T('ATS / recruiting-delivery platform', { bold: true }), T(' — candidate database + resume parsing, smart-match/AI-recruiter, submissions, e-signature agreements, interview scheduling, placements, timesheets & invoices, CRM, REST API v1 + webhooks.')]));
body.push(P([T('Key finding: the two systems are ', {}), T('complementary halves of the same funnel, not competitors.', { bold: true }), T(' RA Agent excels at exactly what Resource Pool lacks (sourcing at scale + a cold-email engine), and Resource Pool owns exactly what RA Agent lacks (candidate lifecycle, agreements, interviews, placements, billing). The single genuine overlap is candidate sourcing/matching.')]));
body.push(P([T('Recommendation: ', { bold: true }), T('run them as a two-stage pipeline connected by API + webhooks, with a clear system-of-record boundary — '),
  T('RA Agent owns steps 1, 2, 4 (front of funnel); Resource Pool owns steps 3, 5–10 (delivery).', { bold: true }),
  T(' Do NOT duplicate candidate matching in the RA Agent — Resource Pool already has a candidate database, smart-match and an AI recruiter, so the fit-scoring design from the prior document should be applied there instead. Both systems already run on the same VPS and both are multi-tenant, which makes the integration low-friction.')]));

// 2. Systems at a glance
body.push(H1('2. The Two Systems at a Glance'));
body.push(table(
  ['Dimension', 'RA Agent', 'Resource Pool'],
  [
    ['Role', {t:'Demand-gen + outreach front-end', color: NAVY}, {t:'ATS / delivery back-end', color: TEAL}],
    ['Stack', 'FastAPI (Python), MySQL', 'Next.js 16, Prisma, PostgreSQL'],
    ['Deploy', 'VPS 187.124.74.175 — API :8000, web :3000', 'Same VPS — PM2 :3002'],
    ['Core strength', 'Job sourcing (Fantastic.jobs + many adapters), firmographic + contact enrichment, cold-email campaigns, mailbox warm-up, deliverability/send-gate', 'Candidate DB (60+ fields) + resume parsing, smart-match + AI recruiter, submissions, e-sign, interviews, placements, timesheets/invoices, CRM'],
    ['Integration surface', 'REST API + internal services; can call out to RP', 'REST API v1 (API-key, scopes), webhooks (candidate/job/offer events), 13 config-gated integrations'],
    ['Multi-tenant', 'Yes (full)', 'Yes (foundation; per-query isolation planned)'],
    ['Cold email at scale', {t:'YES — core capability', color: GREEN}, {t:'NO — transactional candidate email only', color: AMBER}],
    ['Candidate lifecycle', {t:'NO — none today', color: AMBER}, {t:'YES — full (source → place → bill)', color: GREEN}],
  ],
  [1500, 3730, 4130]));

// 3. Workflow ownership map
body.push(H1('3. Workflow → System Ownership Map'));
body.push(P('Mapping each of the 10 steps to the system that should own it, based on current capability (evidence from both codebases).'));
body.push(table(
  ['#', 'Workflow step', 'RA Agent', 'Resource Pool', 'Owner'],
  [
    ['1', 'Jobs / leads sourcing', 'Strong (adapters, Fantastic.jobs)', 'Manual job entry only', RA],
    ['2', 'Contact / firmographic enrichment', 'Strong (contact discovery, Apollo/PDL)', 'Candidate-oriented sourcing', RA],
    ['3', 'Candidate sourcing per job', 'Designed only (prior doc)', 'Strong (DB, sourcing, smart-match, AI recruiter)', RP],
    ['4', 'Cold email to contacts / clients', 'Strong (campaigns, warm-up, deliverability)', 'Missing', RA],
    ['5', 'Contact selected candidates', 'Cold-email engine (reusable)', 'Candidate email/SMS/WhatsApp + follow-ups', RP],
    ['6', 'Client agreement e-signature', 'None', 'Strong (SignatureRequest, DocuSign, offer PDF)', RP],
    ['7', 'Send candidate resumes to clients', 'None', 'Strong (submissions, documents, client portals)', RP],
    ['8', 'Interview scheduling', 'None', 'Strong (self-book, video, scorecards, calendar)', RP],
    ['9', 'Client approves & hires', 'None', 'Strong (offers, placements, onboarding)', RP],
    ['10', 'Client pays fees', 'SaaS billing (different purpose)', 'Strong (timesheets, invoices, bill/pay rates)', RP],
  ],
  [420, 2760, 2340, 2340, 1500]));
body.push(spacer());
body.push(P([T('The boundary is crisp: ', { bold: true }),
  T('RA Agent = steps 1, 2, 4 (generate demand and engage the client); Resource Pool = steps 3, 5–10 (source candidates and deliver the placement). The hand-off happens between step 4 and the delivery stages, triggered by a positive client response to the cold campaign.')]));

// 4. Overlap & reconciliation
body.push(H1('4. The Overlap & How to Reconcile It'));
body.push(P('Three areas exist in both systems. Left unmanaged they cause duplicate data and conflicting logic; the plan assigns a single system of record (SoR) to each.'));
body.push(table(
  ['Overlap', 'RA Agent has', 'Resource Pool has', 'Decision (SoR)'],
  [
    ['Candidate sourcing & matching', 'Fit-score design (prior doc), not built', 'Candidate DB + smart-match + AI recruiter + Apollo/PDL/RocketReach sourcing + resume parsing', {t:'Resource Pool. Apply the calibrated fit-score rubric there; do NOT rebuild in RA Agent.', color: TEAL}],
    ['CRM (companies/contacts)', 'ClientInfo + ContactDetails (from sourcing/enrichment)', 'Company + Contact + Opportunity (sales pipeline)', {t:'RA Agent for cold-stage; push to RP as Company/Contact/Opportunity on positive reply (RP is SoR once engaged).', color: NAVY}],
    ['Outbound messaging', 'Cold-email engine (deliverability, warm-up)', 'Candidate email/SMS/WhatsApp (transactional)', {t:'RA Agent = cold client outreach; RP = candidate lifecycle comms. Optionally expose RA’s sender as a service to RP later.', color: AMBER}],
  ],
  [1900, 2400, 2560, 2500]));
body.push(spacer());
body.push(P([T('Important reconciliation with the prior "Candidate Matching Engine" document: ', { bold: true }),
  T('that design targeted the RA Agent, but Resource Pool already ships a candidate database, a smart-match engine and an AI recruiter. Building matching again in the RA Agent would duplicate a mature capability. The right move is to '),
  T('port the calibrated 0–100 fit-score rubric (gates → vector shortlist → cheap-LLM re-rank → Platt calibration) into Resource Pool’s existing smart-match', { bold: true }),
  T(' — one candidate system, no duplication. The RA Agent instead consumes match summaries to power its cold-email pitch ("we already have N candidates >80% fit for your role").')]));

// 5. Recommended architecture
body.push(H1('5. Recommended Integration Architecture'));
body.push(P('Keep the two systems separate (different languages, DBs and release cycles) and connect them as a pipeline over HTTP — Resource Pool’s REST API v1 + webhooks, plus a small connector on each side. No shared database.'));
body.push(...mono(
`  RA AGENT  (demand-gen + outreach)                RESOURCE POOL  (ATS / delivery)
  ─────────────────────────────────                ────────────────────────────────
  1 Source jobs (Fantastic.jobs, …)
  2 Enrich company + contacts
        │                                            3 Match candidates per job
        │   (a) push job/company/contact ───────────►   (smart-match + AI recruiter,
        │        as Job + Company + Opportunity          calibrated fit-score >80%)
        │   (b) ◄─── match summary per job ──────────    returns "N candidates >80%"
        ▼
  4 Cold-email client contacts  ──"we have N fit candidates for <role>"──►  client
        │
        │   positive reply / meeting booked  (HAND-OFF)
        │   push Opportunity=QUALIFIED + Contact ───►  5  Contact selected candidates
        │                                              6  Client signs agreement (e-sign)
        │                                              7  Send resumes to client
        │                                              8  Schedule interviews
        │                                              9  Client approves & hires (placement)
        │                                              10 Timesheets → invoice → paid
        ▼
  Attribution / ROI  ◄──── webhooks: offer.created, placement.created, invoice.paid ────┘
  (campaign → lead → placement → revenue)`, 15));
body.push(spacer());
body.push(H3('5.1 System-of-record boundary'));
body.push(bullet([T('Sourced jobs & cold-stage leads/contacts: ', { bold: true }), T('RA Agent (until a client engages).')]));
body.push(bullet([T('Engaged reqs, candidates, submissions, interviews, offers, placements, invoices: ', { bold: true }), T('Resource Pool.')]));
body.push(bullet([T('Cross-system identity map: ', { bold: true }), T('store RA lead_id ↔ RP job id, RA contact ↔ RP contact/company, campaign_id ↔ opportunity id, so both sides stay idempotent and attributable.')]));
body.push(H3('5.2 Why API + webhooks (not a shared DB or a merge)'));
body.push(bullet('Different stacks (Python/MySQL vs TypeScript/Postgres) — a shared schema or rewrite is high-cost and high-risk.'));
body.push(bullet('Resource Pool already exposes REST API v1 (API-key + scopes), webhooks (candidate/job/offer events) and an encrypted-secret config pattern — the integration primitives already exist.'));
body.push(bullet('Both run on the same VPS, so connector calls are loopback (fast, private). Loose coupling lets each system evolve independently.'));

// 6. Data flow & handoffs
body.push(H1('6. Hand-off Points & Data Flow'));
body.push(H3('6.1 RA Agent → Resource Pool (push)'));
body.push(numItem([T('On qualified job/lead: ', { bold: true }), T('create/upsert in RP a Job (title, client, location, skills, description, bill rate), a Company + Contact (from enrichment), and an Opportunity (stage LEAD).')]));
body.push(numItem([T('On positive cold-email reply / meeting: ', { bold: true }), T('advance the Opportunity to QUALIFIED and flag the req as active — this is the moment delivery (steps 5–10) begins in RP.')]));
body.push(H3('6.2 Resource Pool → RA Agent (feedback for attribution)'));
body.push(numItem([T('Subscribe RA Agent to RP webhooks: ', { bold: true }), T('offer.created, offer.accepted, placement.created, invoice.paid (add the last three to RP’s webhook events).')]));
body.push(numItem([T('RA Agent records the outcome against the originating campaign/lead ', {}), T('→ closes the ROI loop: which sourcing source + campaign produced a placement and how much revenue.')]));
body.push(H3('6.3 Optional — match summary feed (powers the pitch)'));
body.push(bullet('RP exposes GET /jobs/{id}/match-summary (count of candidates ≥ 80%, top 3 anonymized highlights). RA Agent pulls it before composing the cold email so the pitch leads with ready candidates.'));

// 7. What to build
body.push(H1('7. What to Build'));
body.push(table(
  ['Component', 'Where', 'Effort', 'Notes'],
  [
    ['Lead-intake endpoint (Job+Company+Contact+Opportunity upsert)', 'Resource Pool API v1', 'M', 'Extend v1 beyond candidates/jobs-read; idempotent upsert by external key'],
    ['RP client connector (push jobs/leads, pull match summary)', 'RA Agent (service + settings key)', 'M', 'HTTP client to RP API; store RP API key encrypted; retry + idempotency'],
    ['Webhook events: placement.created, offer.accepted, invoice.paid', 'Resource Pool', 'S', 'Add to existing webhook dispatcher'],
    ['Webhook receiver + attribution store', 'RA Agent (endpoint + table)', 'M', 'Verify HMAC; map event → campaign/lead → revenue'],
    ['Cross-system ID map + dedup keys', 'Both', 'S', 'email / domain / job_link / linkedin as natural keys'],
    ['Calibrated fit-score rubric in smart-match', 'Resource Pool', 'M', 'Port the prior doc’s rubric/gates/Platt into existing matching'],
    ['Tenant mapping (RA tenant ↔ RP tenant)', 'Both (config)', 'S', 'Single-agency = 1↔1; SaaS later = mapping table'],
  ],
  [3050, 2100, 700, 3510]));
body.push(spacer());
body.push(P([T('Auth & security: ', { bold: true }), T('RP issues an API key (scoped) stored encrypted in RA Agent settings; RA issues a key for RP→RA callbacks; all webhooks HMAC-signed (RP already signs with X-Exzelon-Signature). No direct DB access across systems.')]));

// 8. Entity mapping
body.push(H1('8. Entity Mapping (RA Agent → Resource Pool)'));
body.push(table(
  ['RA Agent entity', 'Resource Pool model', 'Sync', 'Key fields'],
  [
    ['LeadDetails (job posting)', 'Job', 'RA → RP', 'jobTitle, clientName, location, requiredSkills, description, billRate, status'],
    ['ClientInfo (company)', 'Company', 'RA → RP', 'name, industry, website, location'],
    ['ContactDetails (client contact)', 'Contact (under Company)', 'RA → RP', 'name, email, phone, title'],
    ['Campaign reply / engaged lead', 'Opportunity', 'RA → RP', 'stage (LEAD→QUALIFIED), value, ownerId'],
    ['Candidate (do NOT build in RA)', 'Candidate', 'RP is SoR', 'RP-native; RA consumes summary only'],
    ['Placement / offer / invoice outcome', '(events back to RA)', 'RP → RA', 'placement.created, offer.accepted, invoice.paid'],
  ],
  [2450, 2250, 1300, 3360]));

// 9. Phasing
body.push(H1('9. Phased Plan'));
body.push(H3('Phase 1 — One-way hand-off (2–3 weeks)'));
body.push(bullet('Build RP lead-intake endpoint + RA→RP connector. On qualified lead, push Job + Company + Contact + Opportunity. Manual trigger first, then automatic on positive reply. Delivers the core "RA generates → RP delivers" pipeline.'));
body.push(H3('Phase 2 — Feedback loop & attribution (2 weeks)'));
body.push(bullet('Add RP webhooks (placement/offer/invoice) + RA receiver + attribution reporting (campaign → placement → revenue). Now leadership can see ROI end-to-end.'));
body.push(H3('Phase 3 — Candidate consolidation & pitch feed (3–4 weeks)'));
body.push(bullet('Port the calibrated fit-score rubric into RP smart-match; expose match-summary API; RA cold emails lead with "N ready candidates". Retire any duplicate candidate-matching intent in RA Agent.'));
body.push(H3('Phase 4 — Tighten (ongoing)'));
body.push(bullet('Shared suppression/consent across systems; unified tenant model as the SaaS story matures; optional: expose RA’s deliverability sender to RP for candidate outreach.'));

// 10. Risks & decisions
body.push(H1('10. Risks & Open Decisions'));
body.push(table(
  ['Item', 'Recommendation'],
  [
    ['Where does candidate matching live?', 'Resource Pool (it already has the engine). Port the fit-score rubric there; do not rebuild in RA Agent.'],
    ['Who owns the client CRM record?', 'RA Agent while cold; Resource Pool once the Opportunity is QUALIFIED. Keep an ID map both ways.'],
    ['Duplicate candidate/company data', 'Idempotent upserts keyed on email/domain/job_link/linkedin; a cross-system ID map; nightly reconciliation.'],
    ['Candidate outreach engine', 'Start with RP’s native candidate comms; later optionally route through RA’s deliverability engine.'],
    ['Compliance across the boundary', 'Share a global suppression/consent list; honor opt-outs on both sides (CAN-SPAM/GDPR/CCPA).'],
    ['Multi-tenant mapping', 'Single Exzelon tenant now (1↔1). Add a tenant-map table only when either system is sold as SaaS.'],
  ],
  [3200, 6160]));

// 11. Conclusion
body.push(H1('11. Conclusion'));
body.push(P([T('The RA Agent and Resource Pool already cover the full 10-step workflow between them with almost no wasted duplication — RA Agent brings sourcing + cold-email demand generation, Resource Pool brings the entire recruiting-delivery back office. The lowest-cost, lowest-risk path is not to merge or rebuild, but to ', {}),
  T('wire them into one pipeline via Resource Pool’s existing API + webhooks', { bold: true }),
  T(', assign a single system of record per entity, and consolidate candidate matching into Resource Pool. Phase 1 alone (a one-way hand-off) turns two standalone tools into an end-to-end staffing machine: source and engage in the RA Agent, deliver and bill in Resource Pool, with revenue attributed back to the campaign that started it.')]));

// assemble
const doc = new Document({
  creator: 'Exzelon',
  title: 'RA Agent × Resource Pool — Integration Plan',
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
  numbering: { config: [
    { reference: 'bul', levels: [
      { level: 0, format: LevelFormat.BULLET, text: '•', alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 460, hanging: 260 } } } },
      { level: 1, format: LevelFormat.BULLET, text: '◦', alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 900, hanging: 260 } } } },
    ] },
    { reference: 'ord', levels: [ { level: 0, format: LevelFormat.DECIMAL, text: '%1.', alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 460, hanging: 260 } } } } ] },
  ] },
  sections: [{
    properties: { page: { size: { width: 12240, height: 15840 }, margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 } } },
    footers: { default: new Footer({ children: [new Paragraph({
      tabStops: [{ type: TabStopType.RIGHT, position: TabStopPosition.MAX }],
      children: [
        new TextRun({ text: 'Exzelon — RA Agent × Resource Pool Integration (Confidential)', size: 16, color: GRAY }),
        new TextRun({ text: '\tPage ', size: 16, color: GRAY }),
        new TextRun({ children: [PageNumber.CURRENT], size: 16, color: GRAY }),
      ],
    })] }) },
    children: body,
  }],
});
Packer.toBuffer(doc).then((buf) => { fs.writeFileSync('Resource_Pool_Integration_Plan.docx', buf); console.log('WROTE Resource_Pool_Integration_Plan.docx (' + buf.length + ' bytes)'); });
