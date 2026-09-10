import type { Metadata } from 'next'
import { IBM_Plex_Mono, Source_Serif_4 } from 'next/font/google'
import DocsRail from './DocsRail'
import { SECTIONS } from './sections'
import styles from './handbook.module.css'

// Two supporting roles alongside Archivo (supplied by the marketing layout):
// a serif that opens each section, and a mono for labels, counters and data.
// Self-hosted via next/font — the app CSP does not allow a remote font CDN.
const plexMono = IBM_Plex_Mono({
  subsets: ['latin'],
  weight: ['400', '500'],
  display: 'swap',
  variable: '--font-plex-mono',
})

const sourceSerif = Source_Serif_4({
  subsets: ['latin'],
  weight: ['400', '600'],
  display: 'swap',
  variable: '--font-source-serif',
})

export const metadata: Metadata = {
  title: 'Documentation',
  description:
    'The complete NeuraLeads customer handbook — every screen, workflow, safety rule, integration, plan and default, explained for the people who use the platform.',
  openGraph: {
    title: 'Documentation — NeuraLeads',
    description:
      'Every feature explained: lead sourcing, contact enrichment, validation, campaigns, the send gate, deals, AI, integrations, plans and business rules.',
  },
  alternates: {
    canonical: '/documentation',
  },
}

export default function DocumentationPage() {
  return (
    <div className={`${styles.handbook} ${plexMono.variable} ${sourceSerif.variable}`}>
      {/* ---------------- Masthead ---------------- */}
      <header className={styles.masthead}>
        <div className={styles.mastheadInner}>
          <div>
            <span className={styles.eyebrow}>Product documentation</span>
            <h1 className={styles.mastheadTitle}>The complete customer handbook</h1>
            <p className={styles.standfirst}>
              Everything the platform does, screen by screen — how leads are sourced, how contacts
              are found and verified, how email is sent safely, and how replies turn into deals.
              Written for the people who use it, not the people who build it.
            </p>
          </div>
          <div className={styles.metaStack}>
            <div className={styles.metaRow}>
              <span className={styles.chip}>29 screens</span>
              <span className={styles.chip}>3 plans</span>
              <span className={`${styles.chip} ${styles.chipAccent}`}>21 sections</span>
            </div>
          </div>
        </div>
      </header>

      <div className={styles.shell}>
        <DocsRail sections={SECTIONS} />

        <main className={styles.doc}>
          {/* ============ 01 ============ */}
          <section id="overview" className={styles.section}>
            <div className={styles.secHead}>
              <span className={styles.secNum}>01</span>
              <h2 className={styles.secTitle}>What NeuraLeads is</h2>
            </div>
            <p className={styles.secIntro}>
              NeuraLeads is an outbound revenue platform. It finds companies that are actively
              buying, identifies the decision-makers inside them, verifies their email addresses,
              runs personalised sequences from your own mailboxes, and tracks every reply through to
              a closed deal — with guardrails that stop your sending domain from being burned along
              the way.
            </p>

            <h3>Who it is built for</h3>
            <div className={`${styles.grid} ${styles.g2}`}>
              <div className={styles.card}>
                <h4>Staffing &amp; recruiting firms</h4>
                <p>
                  Detect live job postings, reach the hiring manager before the requisition goes to a
                  competitor, and track candidate submissions through to placement.
                </p>
              </div>
              <div className={styles.card}>
                <h4>Service businesses</h4>
                <p>
                  Revenue-cycle management, software development, AI services and digital marketing
                  teams each get their own prospecting signals and messaging profile.
                </p>
              </div>
              <div className={styles.card}>
                <h4>Sales &amp; business development teams</h4>
                <p>
                  A shared claim queue, per-rep ownership, task tracking and a Kanban pipeline, so
                  nobody works the same account twice.
                </p>
              </div>
              <div className={styles.card}>
                <h4>Agencies running multiple brands</h4>
                <p>
                  Each client or brand is a separate workspace with its own data, mailboxes,
                  branding, users and billing — fully isolated from every other workspace.
                </p>
              </div>
            </div>

            <h3>What makes it different</h3>
            <ul>
              <li>
                <strong>It sources its own leads.</strong> You are not uploading a purchased list.
                The platform pulls live buying signals — job postings, hiring activity, funding news,
                technology changes, provider registries — and turns them into leads.
              </li>
              <li>
                <strong>Every send passes a safety gate.</strong> Ten ordered checks run before any
                email leaves. If one fails, the email is not sent and the reason is recorded.
              </li>
              <li>
                <strong>Mailboxes are warmed, monitored and rested.</strong> A built-in warmup engine
                builds sending reputation, checks your DNS records and watches blacklists.
              </li>
              <li>
                <strong>AI is bounded, not autonomous.</strong> AI writes, rewrites, classifies and
                suggests — but a deterministic policy engine, not the model, decides whether an email
                may send.
              </li>
              <li>
                <strong>Flat pricing, no per-seat fee.</strong> Add your whole team on any plan.
              </li>
            </ul>

            <div className={styles.note}>
              <span className={styles.eyebrow}>Read this first</span>
              Two words are used precisely throughout this handbook. A <strong>lead</strong> is an
              opportunity at a company — typically a job posting or a buying signal. A{' '}
              <strong>contact</strong> is a person you can email. One lead can have several contacts,
              and one contact can belong to several leads.
            </div>
          </section>

          {/* ============ 02 ============ */}
          <section id="concepts" className={styles.section}>
            <div className={styles.secHead}>
              <span className={styles.secNum}>02</span>
              <h2 className={styles.secTitle}>Core concepts</h2>
            </div>
            <p className={styles.secIntro}>
              Nine terms carry most of the meaning in the product. Learn these and every screen
              becomes readable.
            </p>
            <div className={styles.tableWrap}>
              <table>
                <thead>
                  <tr>
                    <th>Term</th>
                    <th>What it means</th>
                    <th>Where you see it</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td>Workspace</td>
                    <td>
                      Your isolated account. All data, users, mailboxes, settings, branding and
                      invoices belong to exactly one workspace and are never visible to another.
                    </td>
                    <td>Everywhere — it is the boundary around everything</td>
                  </tr>
                  <tr>
                    <td>Line of Business</td>
                    <td>
                      A service line you sell, with its own lead sources, ideal-customer profile,
                      messaging tone and business rules. Six types ship in the box.
                    </td>
                    <td>Lines of Business</td>
                  </tr>
                  <tr>
                    <td>Lead</td>
                    <td>
                      An opportunity — usually a live job posting or a detected buying signal — with
                      a company, title, location, salary and status.
                    </td>
                    <td>Leads, Pipelines</td>
                  </tr>
                  <tr>
                    <td>Contact</td>
                    <td>
                      A named decision-maker with an email address, a priority tier (P1–P5) and a
                      validation status.
                    </td>
                    <td>Contacts, Validation</td>
                  </tr>
                  <tr>
                    <td>Client</td>
                    <td>
                      The company record behind leads and contacts — industry, size, website,
                      location and timezone.
                    </td>
                    <td>Clients</td>
                  </tr>
                  <tr>
                    <td>Mailbox</td>
                    <td>
                      A sending email account you connect. Each has a daily limit, a health score and
                      a warmup status.
                    </td>
                    <td>Mailboxes, Warmup Engine</td>
                  </tr>
                  <tr>
                    <td>Campaign</td>
                    <td>
                      A multi-step email sequence with its own schedule, send window, mailboxes and
                      enrolled contacts.
                    </td>
                    <td>Campaigns</td>
                  </tr>
                  <tr>
                    <td>Deal</td>
                    <td>
                      A revenue opportunity on the Kanban board, with a value, probability, stage and
                      owner.
                    </td>
                    <td>Deals</td>
                  </tr>
                  <tr>
                    <td>Pipeline run</td>
                    <td>
                      One execution of a data stage — sourcing, enrichment, validation or outreach —
                      with counters showing exactly what was kept and what was dropped.
                    </td>
                    <td>Pipelines</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </section>

          {/* ============ 03 ============ */}
          <section id="workflow" className={styles.section}>
            <div className={styles.secHead}>
              <span className={styles.secNum}>03</span>
              <h2 className={styles.secTitle}>The six-stage workflow</h2>
            </div>
            <p className={styles.secIntro}>
              The left-hand navigation inside the app is ordered as a working sequence, not an
              alphabet. Follow it top to bottom in your first week and the platform sets itself up in
              the right order.
            </p>
            <div className={styles.stages}>
              <div className={styles.stage}>
                <div className={styles.stageNum}>STAGE 1</div>
                <h4>Set up</h4>
                <p>Connect mailboxes, start warmup, confirm your DNS records are in place.</p>
              </div>
              <div className={styles.stage}>
                <div className={styles.stageNum}>STAGE 2</div>
                <h4>Source</h4>
                <p>Run lead sourcing. Job boards and signal sources become de-duplicated, filtered leads.</p>
              </div>
              <div className={styles.stage}>
                <div className={styles.stageNum}>STAGE 3</div>
                <h4>Enrich</h4>
                <p>Find the decision-makers at each company and rank them P1–P5 by relevance.</p>
              </div>
              <div className={styles.stage}>
                <div className={styles.stageNum}>STAGE 4</div>
                <h4>Validate</h4>
                <p>Verify every email address. Only addresses marked Valid ever reach outreach.</p>
              </div>
              <div className={styles.stage}>
                <div className={styles.stageNum}>STAGE 5</div>
                <h4>Engage</h4>
                <p>Build a sequence, preview and approve the drafts, and let the engine send inside your window.</p>
              </div>
              <div className={styles.stage}>
                <div className={styles.stageNum}>STAGE 6</div>
                <h4>Close</h4>
                <p>Work replies in the unified inbox, convert interest into deals, and track them to won.</p>
              </div>
            </div>
            <div className={`${styles.note} ${styles.noteGood}`}>
              <span className={styles.eyebrow}>Getting Started widget</span>
              A six-step checklist on your dashboard tracks exactly this sequence and ticks itself off
              as you complete each stage. A guided tour highlights each screen on your first visit,
              and the floating <strong>?</strong> button replays it any time. Dismissing the checklist
              is per user, so it does not hide it from your colleagues.
            </div>
          </section>

          {/* ============ 04 ============ */}
          <section id="setup" className={styles.section}>
            <div className={styles.secHead}>
              <span className={styles.secNum}>04</span>
              <h2 className={styles.secTitle}>Stage 1 — Mailboxes &amp; warmup</h2>
            </div>
            <p className={styles.secIntro}>
              Sending reputation is the one asset you cannot buy back. Everything in this stage exists
              to protect it.
            </p>

            <h3>Mailboxes</h3>
            <p>
              Connect any SMTP-capable email account — Google Workspace, Microsoft 365, or a custom
              domain host. For each mailbox you control:
            </p>
            <ul>
              <li>
                <strong>Daily send limit</strong> — how many emails this mailbox may send in a day
                (30 by default).
              </li>
              <li>
                <strong>Health score</strong> — a live rating combining bounce rate, complaint rate,
                warmup age and recent deliverability.
              </li>
              <li>
                <strong>Warmup status</strong> — not started, warming, or ready.
              </li>
              <li>
                <strong>Signature</strong> — appended automatically and available as a merge field in
                every template.
              </li>
              <li>
                <strong>Outreach role</strong> — which decides how the mailbox behaves, below.
              </li>
            </ul>

            <h4>Automated mailboxes vs. personal mailboxes</h4>
            <div className={styles.tableWrap}>
              <table>
                <thead>
                  <tr>
                    <th>Role type</th>
                    <th>Used for</th>
                    <th>Auto-selected for cold outbound?</th>
                    <th>Has a login user?</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td>Automated</td>
                    <td>Machine-sent cold sequences</td>
                    <td className={styles.yes}>Yes — the automatic pool</td>
                    <td className={styles.no}>No</td>
                  </tr>
                  <tr>
                    <td>Personal</td>
                    <td>Named individuals sending manually or from an assigned campaign</td>
                    <td className={styles.no}>No — manual assignment only</td>
                    <td className={styles.yes}>Yes — linked one-to-one to a user</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <p>
              When you create a personal mailbox, the platform can create or link the matching login
              user for you and map the outreach role to the right permission level automatically.
            </p>

            <h4>How a mailbox is chosen for a send</h4>
            <p>
              When a campaign has no mailboxes assigned, the platform picks the healthiest available
              automated mailbox on a weighted score: <strong>health 40% · remaining daily quota 30% ·
              warmup age 15% · deliverability 15%</strong>. When a campaign does have mailboxes
              assigned, it rotates round-robin through exactly those.
            </p>

            <h3>Warmup Engine</h3>
            <p>The warmup engine builds and defends reputation on every connected mailbox. It has seven tabs:</p>
            <div className={`${styles.grid} ${styles.g2}`}>
              <div className={styles.card}>
                <h4>Overview</h4>
                <p>Per-mailbox warmup status, current daily volume, health score and assessment history.</p>
              </div>
              <div className={styles.card}>
                <h4>Analytics</h4>
                <p>Warmup volume, inbox placement and reply rate over time.</p>
              </div>
              <div className={styles.card}>
                <h4>Email threads</h4>
                <p>The actual peer-to-peer warmup conversations, so you can confirm the engine is working.</p>
              </div>
              <div className={styles.card}>
                <h4>DNS &amp; blacklist</h4>
                <p>Automated SPF, DKIM and DMARC checks, plus blacklist monitoring for your sending domains and IPs.</p>
              </div>
              <div className={styles.card}>
                <h4>Profiles</h4>
                <p>Three ramp templates — Conservative (45 days), Standard (30 days), Aggressive (20 days).</p>
              </div>
              <div className={styles.card}>
                <h4>Alerts</h4>
                <p>Reputation warnings: failed DNS records, blacklist hits, health-score drops.</p>
              </div>
            </div>
            <p>
              Behind the tabs, the engine sends and auto-replies to peer warmup emails on a schedule,
              emulates human reading behaviour, resets daily counters, and runs a recovery check each
              morning for any mailbox whose reputation slipped.
            </p>

            <div className={`${styles.note} ${styles.noteStop}`}>
              <span className={styles.eyebrow}>Do not skip this</span>
              A brand-new domain that starts sending at volume will land in spam and can be
              blacklisted within days. Run at least one full warmup cycle on every new mailbox before
              enrolling it in a live campaign, and keep SPF, DKIM and DMARC green on the DNS tab.
            </div>
          </section>

          {/* ============ 05 ============ */}
          <section id="sourcing" className={styles.section}>
            <div className={styles.secHead}>
              <span className={styles.secNum}>05</span>
              <h2 className={styles.secTitle}>Stage 2 — Lead sourcing</h2>
            </div>
            <p className={styles.secIntro}>
              The sourcing pipeline queries your enabled sources, normalises everything into one
              shape, removes duplicates three different ways, and applies your exclusion rules before
              a single lead reaches your database.
            </p>

            <h3>What a sourcing run actually does</h3>
            <ol className={styles.plain}>
              <li>
                <strong>Query</strong> — every enabled source is queried in parallel with your job
                titles, locations and filters. Where a source supports it, your exclusion keywords are
                pushed into the query itself, so unwanted postings are filtered before they are ever
                downloaded.
              </li>
              <li>
                <strong>Normalise</strong> — results from different sources are mapped into one common
                lead shape.
              </li>
              <li>
                <strong>De-duplicate</strong> — three layers in order: exact posting identifier, then
                employer profile, then company + title + state + city.
              </li>
              <li>
                <strong>Company gate</strong> — confidential or blank employers are dropped, companies
                above your size ceiling are dropped, and excluded industries are dropped.
              </li>
              <li>
                <strong>Enrich the gaps</strong> — where a source did not report a company’s industry
                or size, an AI step fills it in, with an optional paid firmographic lookup for size
                specifically. An unknown value is never used as a reason to drop a company.
              </li>
              <li>
                <strong>Record</strong> — leads are saved with their source and sub-source, and the
                run’s counters show exactly how many were dropped and why.
              </li>
            </ol>

            <h3>Run counters — how to read a sourcing result</h3>
            <div className={styles.tableWrap}>
              <table>
                <thead>
                  <tr>
                    <th>Counter</th>
                    <th>Meaning</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td>Fetched</td>
                    <td>Raw results returned by all sources before any processing.</td>
                  </tr>
                  <tr>
                    <td>Duplicates removed</td>
                    <td>Removed by the three-layer de-duplication.</td>
                  </tr>
                  <tr>
                    <td>Excluded — confidential</td>
                    <td>The posting had no named employer, so no company could be researched.</td>
                  </tr>
                  <tr>
                    <td>Excluded — too large</td>
                    <td>The company exceeded your employee-count ceiling.</td>
                  </tr>
                  <tr>
                    <td>Excluded — industry</td>
                    <td>The company sits in an industry you have excluded.</td>
                  </tr>
                  <tr>
                    <td>Enriched companies</td>
                    <td>Companies whose missing size or industry was filled in during the run.</td>
                  </tr>
                  <tr>
                    <td>Saved</td>
                    <td>New leads written to your workspace.</td>
                  </tr>
                </tbody>
              </table>
            </div>

            <h3>Sourcing controls you own</h3>
            <ul>
              <li>
                <strong>Job titles and locations</strong> you target, and the <strong>keywords</strong>{' '}
                that exclude a posting outright.
              </li>
              <li>
                <strong>Company size ceiling</strong> — default 200 employees; set it to 0 to disable
                the limit entirely.
              </li>
              <li>
                <strong>Excluded industries</strong> — IT, staffing agencies and government by default.
              </li>
              <li>
                <strong>Minimum salary</strong> — default $40,000.
              </li>
              <li>
                <strong>Excluded companies</strong> — a permanent do-not-source list you manage on its
                own screen.
              </li>
              <li>
                <strong>Per-source tuning</strong> — batch size, page depth and result caps for each
                individual source, plus a global cap per source and how many sources are queried in
                parallel.
              </li>
            </ul>

            <div className={styles.note}>
              <span className={styles.eyebrow}>Why size filtering is deliberately strict</span>
              Company-size data varies in quality between sources. Where a source reports two
              different size signals, the platform judges on the <em>larger</em> one, so an oversized
              company is excluded rather than let through. Letting a 5,000-person enterprise through
              as a “156-person company” wastes paid enrichment credits on a prospect you never wanted.
            </div>
          </section>

          {/* ============ 06 ============ */}
          <section id="enrichment" className={styles.section}>
            <div className={styles.secHead}>
              <span className={styles.secNum}>06</span>
              <h2 className={styles.secTitle}>Stage 3 — Contact enrichment</h2>
            </div>
            <p className={styles.secIntro}>
              Enrichment turns a company into named people you can write to, ranked so the best
              contact is emailed first.
            </p>

            <h3>Priority tiers</h3>
            <div className={styles.tableWrap}>
              <table>
                <thead>
                  <tr>
                    <th>Tier</th>
                    <th>Who</th>
                    <th>Typical use</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td>P1</td>
                    <td>The person who posted the job or triggered the signal</td>
                    <td>Always contact first</td>
                  </tr>
                  <tr>
                    <td>P2</td>
                    <td>Direct hiring manager or budget owner</td>
                    <td>Primary alternative</td>
                  </tr>
                  <tr>
                    <td>P3</td>
                    <td>Talent acquisition or procurement lead</td>
                    <td>Reliable secondary route</td>
                  </tr>
                  <tr>
                    <td>P4</td>
                    <td>HR or operations leadership</td>
                    <td>Fallback</td>
                  </tr>
                  <tr>
                    <td>P5</td>
                    <td>Functional manager in the relevant department</td>
                    <td>Last resort</td>
                  </tr>
                </tbody>
              </table>
            </div>

            <h3>Rules applied during enrichment</h3>
            <ul>
              <li>
                A hard cap on how many contacts are pulled per company per opportunity —{' '}
                <strong>2 by default</strong> — so you never carpet-bomb one account.
              </li>
              <li>Contacts already in your workspace are matched and re-used rather than duplicated.</li>
              <li>Cost is recorded per provider on every run and appears in your cost analytics.</li>
              <li>
                Company records are created or updated alongside the contact, including the timezone
                derived from the company’s location — which is what makes timezone-aware sending
                possible later.
              </li>
            </ul>
          </section>

          {/* ============ 07 ============ */}
          <section id="validation" className={styles.section}>
            <div className={styles.secHead}>
              <span className={styles.secNum}>07</span>
              <h2 className={styles.secTitle}>Stage 4 — Email validation</h2>
            </div>
            <p className={styles.secIntro}>
              Validation is not optional and it is not advisory. Only contacts whose address is
              confirmed Valid can receive outreach — the send gate enforces it regardless of what any
              campaign says.
            </p>
            <div className={styles.tableWrap}>
              <table>
                <thead>
                  <tr>
                    <th>Status</th>
                    <th>Meaning</th>
                    <th>Can be emailed?</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td>Valid</td>
                    <td>The mailbox exists and accepts mail.</td>
                    <td className={styles.yes}>Yes</td>
                  </tr>
                  <tr>
                    <td>Invalid</td>
                    <td>The mailbox does not exist. Sending guarantees a hard bounce.</td>
                    <td className={styles.no}>Never</td>
                  </tr>
                  <tr>
                    <td>Catch-all</td>
                    <td>The domain accepts everything, so existence cannot be proven.</td>
                    <td>Only if you explicitly allow catch-alls</td>
                  </tr>
                  <tr>
                    <td>Unknown</td>
                    <td>The provider could not reach a verdict.</td>
                    <td className={styles.no}>No</td>
                  </tr>
                  <tr>
                    <td>Not validated</td>
                    <td>Never checked.</td>
                    <td className={styles.no}>No</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <p>
              Validation runs in bulk from the Validation screen or as part of a pipeline run. Results
              are written back to the contact, so a contact only needs validating once unless you
              re-check it. Per-contact validation cost is tracked in your cost analytics.
            </p>
          </section>

          {/* ============ 08 ============ */}
          <section id="campaigns" className={styles.section}>
            <div className={styles.secHead}>
              <span className={styles.secNum}>08</span>
              <h2 className={styles.secTitle}>Stage 5 — Campaigns &amp; outreach</h2>
            </div>
            <p className={styles.secIntro}>
              A campaign is a sequence of steps, a schedule, a set of mailboxes and a list of enrolled
              contacts. Everything else on this screen exists to make that sequence land in an inbox
              and sound like a person wrote it.
            </p>

            <h3>Building a sequence</h3>
            <p>Steps run in order and can be of six types:</p>
            <div className={`${styles.grid} ${styles.g3}`}>
              <div className={styles.card}>
                <h4>Email</h4>
                <p>Subject, body, optional A/B variants, optional template.</p>
              </div>
              <div className={styles.card}>
                <h4>Wait</h4>
                <p>A delay before the next step.</p>
              </div>
              <div className={styles.card}>
                <h4>Condition</h4>
                <p>Branch on whether the contact opened, clicked or replied.</p>
              </div>
              <div className={styles.card}>
                <h4>SMS</h4>
                <p>A text-message step, where SMS is enabled.</p>
              </div>
              <div className={styles.card}>
                <h4>LinkedIn</h4>
                <p>A manual task placeholder inside the sequence.</p>
              </div>
              <div className={styles.card}>
                <h4>Call</h4>
                <p>A manual call task placeholder inside the sequence.</p>
              </div>
            </div>

            <h4>Personalisation tools inside a step</h4>
            <ul>
              <li>
                <strong>Merge fields</strong> — recipient first name, sender first name, job title
                from the lead, job location, company name, mailbox signature and more.
              </li>
              <li>
                <strong>Spintax</strong> — write <code>{'{Hi|Hello|Hey}'}</code> and each recipient
                gets a different variant. Nested patterns are supported, so no two emails read
                identically.
              </li>
              <li>
                <strong>A/B variants</strong> — weighted variants per step, with automatic statistical
                selection of the winner once there is enough data.
              </li>
              <li>
                <strong>Templates</strong> — pull any active template from your library straight into
                a step, grouped into Outreach and Follow-up.
              </li>
              <li>
                <strong>AI assistance</strong> — generate a whole sequence from a brief, suggest five
                subject-line variants, or improve the campaign’s own name and description.
              </li>
            </ul>

            <h3>Campaign statuses</h3>
            <div className={styles.metaRow} style={{ margin: '12px 0 18px' }}>
              <span className={styles.chip}>Draft</span>
              <span className={`${styles.chip} ${styles.chipAccent}`}>Previewing</span>
              <span className={`${styles.chip} ${styles.chipGood}`}>Sending</span>
              <span className={styles.chip}>Paused</span>
              <span className={styles.chip}>Completed</span>
              <span className={styles.chip}>Archived</span>
            </div>

            <h3>Scheduling and send windows</h3>
            <ul>
              <li>
                <strong>Send window</strong> — the hours of the day the campaign may send, with a
                timezone.
              </li>
              <li>
                <strong>Send days</strong> — which weekdays are allowed.
              </li>
              <li>
                <strong>Multiple dated schedules</strong> — different windows for different date
                ranges on the same campaign, in a defined order.
              </li>
              <li>
                <strong>Per-contact timezone</strong> — where a contact’s timezone is known it
                overrides the campaign timezone, so an East-coast prospect is emailed on East-coast
                time.
              </li>
              <li>
                <strong>Optimal-hour scheduling</strong> — follow-up steps are placed into local
                business hours, with 9–11am treated as the strongest window.
              </li>
              <li>
                <strong>Slow ramp</strong> — increase daily volume by a set amount per day instead of
                starting at full throttle.
              </li>
            </ul>

            <h3>Enrolment</h3>
            <ul>
              <li>
                <strong>From leads</strong> — select leads and the platform names the campaign, builds
                a three-step sequence, assigns your active mailboxes and enrols the contacts in one
                action.
              </li>
              <li>
                <strong>Available leads view</strong> — shows only leads not already in an active
                campaign, with their contact counts, so you never double-enrol.
              </li>
              <li>
                <strong>Auto-enrolment</strong> — a scheduled job adds newly qualified contacts into
                eligible campaigns.
              </li>
              <li>
                <strong>Assignment modes</strong> — manual, round-robin or weighted distribution of
                enrolled contacts across your reps.
              </li>
            </ul>

            <h3>Automatic pausing</h3>
            <p>
              You set bounce-rate and spam-complaint thresholds per campaign. An hourly health check
              pauses any campaign that breaches them and tells you why. Complaint-rate monitoring
              pauses sending at a 0.3% complaint rate independently of that.
            </p>

            <h3>Preview mode and the Email Preview screen</h3>
            <p>
              Switch a campaign into preview mode and it generates drafts instead of sending. On the
              Email Preview screen every draft can be:
            </p>
            <ul>
              <li>Read exactly as the recipient will see it, with all merge fields resolved.</li>
              <li>
                Scored for <strong>spam risk</strong> — trigger words, suspicious patterns,
                link-to-image ratio — and for overall <strong>deliverability</strong>.
              </li>
              <li>Auto-fixed for the specific spam issues found, or rewritten by AI.</li>
              <li>Approved, rejected, or approved as a batch and released to send together.</li>
            </ul>
            <p>
              Drafts carry their source — campaign, pipeline or broadcast — so you can filter a review
              queue down to one origin.
            </p>
          </section>

          {/* ============ 09 ============ */}
          <section id="sendgate" className={styles.section}>
            <div className={styles.secHead}>
              <span className={styles.secNum}>09</span>
              <h2 className={styles.secTitle}>The send gate</h2>
            </div>
            <p className={styles.secIntro}>
              Every outbound email, from every path in the product, passes the same ten checks in the
              same order. The first failure stops the send and is recorded with its reason. This is
              the single most important safety mechanism in the platform.
            </p>
            <ol className={styles.gate}>
              <li>
                <div>
                  <b>Contact status</b>
                  Unsubscribed, bounced or inactive contacts are never mailed.
                </div>
              </li>
              <li>
                <div>
                  <b>Suppression list</b>
                  Blocks any address, or a whole domain, that you have suppressed.
                </div>
              </li>
              <li>
                <div>
                  <b>Email validation</b>
                  The address must be confirmed Valid, or an allowed catch-all.
                </div>
              </li>
              <li>
                <div>
                  <b>Cooldown</b>
                  No second email to the same person inside the cooldown period — 10 days by default.
                </div>
              </li>
              <li>
                <div>
                  <b>Per-lead limit</b>
                  Caps how many emails a single opportunity can generate.
                </div>
              </li>
              <li>
                <div>
                  <b>Company cap</b>
                  Caps concurrent conversations inside one company, so one account never receives a flood.
                </div>
              </li>
              <li>
                <div>
                  <b>Sequence fatigue</b>
                  Stops a contact who has already received many emails from receiving more.
                </div>
              </li>
              <li>
                <div>
                  <b>Domain throttle</b>
                  Limits how many emails go to one recipient domain per day — 30 to major consumer providers, 50 generally.
                </div>
              </li>
              <li>
                <div>
                  <b>Cross-campaign de-duplication</b>
                  Prevents two campaigns from independently emailing the same person.
                </div>
              </li>
              <li>
                <div>
                  <b>Policy decision</b>
                  A final go / no-go combining policy rules, content quality and lead score, with a written reason code.
                </div>
              </li>
            </ol>
            <div className={`${styles.note} ${styles.noteGood}`}>
              <span className={styles.eyebrow}>Testing safely</span>
              Contacts flagged as test contacts skip the volume-based checks (4 through 8) so you can
              rehearse a sequence end to end without waiting out cooldowns. They still pass the hard
              safety checks — suppression, unsubscribe and validation are never bypassed for anyone.
            </div>

            <h3>What happens after a send</h3>
            <ul>
              <li>
                <strong>Opens</strong> are tracked by a tracking pixel and <strong>clicks</strong> by a
                redirect on each link. You can point both at your own custom tracking domain, which the
                platform verifies for you.
              </li>
              <li>
                <strong>Hard bounces</strong> automatically suppress the address and mark the contact
                inactive — no manual clean-up.
              </li>
              <li>
                <strong>Complaints</strong> feed the complaint-rate monitor and can auto-pause the
                campaign.
              </li>
              <li>
                <strong>Replies</strong> stop the sequence for that contact immediately and appear in
                the unified inbox.
              </li>
              <li>
                <strong>Engagement scoring</strong> weights signals by strength — a reply counts far
                more than a click, a click far more than an open.
              </li>
            </ul>

            <h3>Content quality safeguards</h3>
            <ul>
              <li>
                <strong>Spam checker</strong> — over a hundred trigger words plus pattern and
                link-ratio checks, run before a send and on demand.
              </li>
              <li>
                <strong>Similarity guard</strong> — measures how close an email is to ones already
                sent, so near-identical mass mail is caught.
              </li>
              <li>
                <strong>Humaniser</strong> — varies sentence length and rhythm so copy does not read as
                machine-generated.
              </li>
              <li>
                <strong>Rendering check</strong> — warns about HTML that breaks in common email clients.
              </li>
              <li>
                <strong>Optional DKIM signing</strong> for custom SMTP connections.
              </li>
            </ul>
          </section>

          {/* ============ 10 ============ */}
          <section id="inbox" className={styles.section}>
            <div className={styles.secHead}>
              <span className={styles.secNum}>10</span>
              <h2 className={styles.secTitle}>Stage 6 — Inbox, replies &amp; deals</h2>
            </div>
            <p className={styles.secIntro}>
              Replies from every mailbox land in one place, already threaded, categorised and scored.
            </p>

            <h3>Unified inbox</h3>
            <ul>
              <li>
                <strong>Threading</strong> — messages are grouped into real conversations across
                mailboxes and campaigns.
              </li>
              <li>
                <strong>Sentiment</strong> — each inbound message is scored positive, negative or
                neutral.
              </li>
              <li>
                <strong>Categories</strong> — Interested, Not interested, Out of office, Question,
                Referral, Do not contact, Other.
              </li>
              <li>
                <strong>AI reply suggestions</strong> — drafted from the whole conversation, not just
                the last message.
              </li>
              <li>
                <strong>Reply macros</strong> — your own saved quick replies with variable substitution
                and usage tracking.
              </li>
              <li>
                <strong>Objection library</strong> — tested responses to common objections, seeded for
                you and extendable, each with an effectiveness score.
              </li>
            </ul>

            <h4>AI Reply Agent — two modes</h4>
            <div className={`${styles.grid} ${styles.g2}`}>
              <div className={styles.card}>
                <h4>Human in the loop</h4>
                <p>
                  The agent drafts a reply, detects the intent and scores its own confidence, then
                  waits for you to approve, edit or reject. Nothing sends without you.
                </p>
              </div>
              <div className={styles.card}>
                <h4>Autopilot</h4>
                <p>
                  High-confidence replies of permitted types send automatically after a delay you set,
                  up to a maximum count you set. Low confidence, or anything classed as a destructive
                  action, always escalates to a human.
                </p>
              </div>
            </div>
            <p>Replies categorised as interested can be forwarded into your CRM automatically.</p>

            <h3>Deals</h3>
            <p>
              A Kanban board across seven stages — <strong>New Lead → Contacted → Qualified → Proposal
              → Negotiation → Won or Lost</strong>. Stages are configurable per workspace.
            </p>

            <h4>The claim queue</h4>
            <p>
              New deals arrive unclaimed and are broadcast to every business developer and recruiter,
              in-app and by email. Any of them can claim a deal to take ownership; the claimer or an
              admin can release it back. Admins can also assign a deal directly to a named person, who
              is notified immediately. Both notification types respect each user’s own notification
              preferences.
            </p>

            <h4>Deal detail — the 360 view</h4>
            <ul>
              <li>The originating job or signal that created the opportunity.</li>
              <li>
                The full mail chain — outbound sends and inbound replies merged into one chronological
                history.
              </li>
              <li>
                Candidate submissions with their own lifecycle: Submitted → Reviewed → Sent to client →
                Placed or Rejected.
              </li>
              <li>
                Tasks with assignee, due date, priority and status, plus a personal “my tasks” view.
              </li>
              <li>A complete activity timeline.</li>
            </ul>

            <h4>Filtering the board</h4>
            <p>
              Filter by stage, by value or probability (equals, not equals, less than, greater than,
              between), by created-date range, by claim state (anyone, unclaimed, me, or a named
              person), by free-text search, or narrow to just your own deals. Each card shows who
              claimed it, its owner and its age in days.
            </p>

            <h3>Forecasting</h3>
            <p>
              An AI forecast engine projects pipeline outcomes from stage, value, probability and
              engagement history.
            </p>
          </section>

          {/* ============ 11 ============ */}
          <section id="ai" className={styles.section}>
            <div className={styles.secHead}>
              <span className={styles.secNum}>11</span>
              <h2 className={styles.secTitle}>What the AI does — and what it may not</h2>
            </div>
            <p className={styles.secIntro}>
              AI is used in fourteen places in the product. In none of them does a model have the
              final say over whether an email is sent.
            </p>

            <h3>Where AI helps</h3>
            <div className={styles.tableWrap}>
              <table>
                <thead>
                  <tr>
                    <th>Capability</th>
                    <th>What it produces</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td>Email content generation</td>
                    <td>First-draft outreach copy from the lead, company and role context.</td>
                  </tr>
                  <tr>
                    <td>Per-contact personalisation</td>
                    <td>
                      Rewrites the email at send time using that contact’s profile. Optional, and falls
                      back to the original copy on any failure.
                    </td>
                  </tr>
                  <tr>
                    <td>Sequence generation</td>
                    <td>A complete multi-step sequence from a short brief, with a non-AI template fallback.</td>
                  </tr>
                  <tr>
                    <td>Subject line variants</td>
                    <td>Five A/B-ready subject lines per step.</td>
                  </tr>
                  <tr>
                    <td>ICP Wizard</td>
                    <td>
                      A full ideal-customer profile — industries, titles, states, company sizes — with a
                      rule-based fallback.
                    </td>
                  </tr>
                  <tr>
                    <td>Natural-language lead search</td>
                    <td>Type “healthcare companies in Texas hiring nurses” and get the filtered result set.</td>
                  </tr>
                  <tr>
                    <td>Reply classification</td>
                    <td>
                      Intent detection on every inbound message, with a keyword-based fallback if the
                      model is unavailable.
                    </td>
                  </tr>
                  <tr>
                    <td>Reply drafting</td>
                    <td>A suggested response with a confidence score.</td>
                  </tr>
                  <tr>
                    <td>Next-best-action</td>
                    <td>A recommended next move on a conversation.</td>
                  </tr>
                  <tr>
                    <td>Lead scoring</td>
                    <td>
                      Hiring signals, company size, industry, salary and web presence combined into a
                      score, refreshed daily.
                    </td>
                  </tr>
                  <tr>
                    <td>Engagement scoring</td>
                    <td>Replies, clicks and opens combined into cold, warm, hot or dead.</td>
                  </tr>
                  <tr>
                    <td>Company enrichment</td>
                    <td>Fills missing industry and size during sourcing.</td>
                  </tr>
                  <tr>
                    <td>Spam remediation</td>
                    <td>Explains why copy scored badly and rewrites it to fix exactly those issues.</td>
                  </tr>
                  <tr>
                    <td>Forecasting</td>
                    <td>Pipeline projections from deal and engagement history.</td>
                  </tr>
                </tbody>
              </table>
            </div>

            <h3>The guardrails around it</h3>
            <ul>
              <li>
                <strong>A deterministic policy engine decides sends</strong>, not the model. Its rules
                are fixed, readable and overridable per workspace.
              </li>
              <li>
                <strong>Every AI decision is logged</strong> with its inputs, its output and its reason
                code, so any send or auto-reply can be explained after the fact.
              </li>
              <li>
                <strong>Inbound content is sanitised</strong> before it reaches a model, so text inside
                a prospect’s reply cannot issue instructions to your AI.
              </li>
              <li>
                <strong>Low confidence escalates to a human</strong>, and so does anything classified
                as a destructive action.
              </li>
              <li>
                <strong>Structured outputs are validated</strong> against a schema; malformed model
                output is rejected rather than acted on.
              </li>
              <li>
                <strong>Failures retry and fall back</strong> across providers, so an outage at one AI
                vendor does not stop your campaigns.
              </li>
              <li>
                <strong>Token cost is metered per call</strong> and appears in your cost analytics
                alongside every other provider.
              </li>
            </ul>
          </section>

          {/* ============ 12 ============ */}
          <section id="modules" className={styles.section}>
            <div className={styles.secHead}>
              <span className={styles.secNum}>12</span>
              <h2 className={styles.secTitle}>Screen-by-screen reference</h2>
            </div>
            <p className={styles.secIntro}>
              Every screen in the product, what it is for, and who reaches it by default.
            </p>
            <div className={styles.tableWrap}>
              <table>
                <thead>
                  <tr>
                    <th>Screen</th>
                    <th>What it does</th>
                    <th>Default access</th>
                  </tr>
                </thead>
                <tbody>
                  <tr><td>Dashboard</td><td>Live KPIs, the six-step getting-started checklist, recent activity and alerts.</td><td>Everyone</td></tr>
                  <tr><td>Mailboxes</td><td>Connect, configure, health-check and role-assign sending accounts.</td><td>Admin, BDM</td></tr>
                  <tr><td>Warmup Engine</td><td>Reputation building, DNS and blacklist monitoring, warmup analytics.</td><td>Admin, BDM</td></tr>
                  <tr><td>Pipelines</td><td>Run and monitor the four data stages independently, with per-run counters.</td><td>Admin, BDM</td></tr>
                  <tr><td>Leads</td><td>Every sourced opportunity — spreadsheet-style text and numeric filters, bulk actions, status override, export exactly as displayed, natural-language search, saved smart lists.</td><td>Everyone</td></tr>
                  <tr><td>Clients</td><td>Company records — industry, size, website, location, timezone — and everything attached to them.</td><td>Everyone</td></tr>
                  <tr><td>Contacts</td><td>People, priority tiers, validation status, unsubscribe state, bulk operations.</td><td>Everyone</td></tr>
                  <tr><td>Validation</td><td>Bulk address verification and its results.</td><td>Everyone</td></tr>
                  <tr><td>ICP Wizard</td><td>Build and store ideal-customer profiles that drive targeting.</td><td>Admin, BDM</td></tr>
                  <tr><td>Email Templates</td><td>Reusable templates by category and industry, one active per category, with preview, duplicate and a seeded starter library.</td><td>Admin, BDM</td></tr>
                  <tr><td>Campaigns</td><td>Sequences, schedules, enrolment, A/B tests, auto-pause rules.</td><td>Admin, BDM</td></tr>
                  <tr><td>Outreach</td><td>Direct send execution and outreach history.</td><td>Admin, BDM</td></tr>
                  <tr><td>Email Preview</td><td>Draft review, spam and deliverability scoring, AI rewrite, approve, reject or batch send.</td><td>Admin, BDM</td></tr>
                  <tr><td>Inbox</td><td>Unified replies, sentiment, categories, macros, AI drafts.</td><td>Admin, BDM</td></tr>
                  <tr><td>Deals</td><td>Kanban pipeline, claim queue, candidates, tasks, 360 detail view.</td><td>Admin, BDM</td></tr>
                  <tr><td>Reports</td><td>Six operational reports, all filterable, sortable and exportable.</td><td>Admin, BDM</td></tr>
                  <tr><td>Analytics</td><td>Revenue, win rate, average deal size, pipeline value, ROI, cost per lead, team leaderboard, campaign comparison.</td><td>Admin</td></tr>
                  <tr><td>Attribution</td><td>Which source, campaign and touch produced each won deal.</td><td>Admin, BDM</td></tr>
                  <tr><td>Visitors</td><td>Website visitor tracking via a small script — sessions, page visits, buying-intent scoring.</td><td>Admin</td></tr>
                  <tr><td>Automation</td><td>Switch each scheduled background job on or off; see its schedule and last run.</td><td>Admin</td></tr>
                  <tr><td>Activity Log</td><td>Login history, authentication audit, active users, account unlock.</td><td>Super admin</td></tr>
                  <tr><td>User Management</td><td>Create users, assign roles, set notification defaults, deactivate.</td><td>Admin, super admin</td></tr>
                  <tr><td>Roles &amp; Permissions</td><td>Per-module permission matrix; create custom roles.</td><td>Super admin</td></tr>
                  <tr><td>Lines of Business</td><td>Create and configure service lines, their sources, ICP, rules and intent signals.</td><td>Admin</td></tr>
                  <tr><td>Excluded Companies</td><td>Your permanent do-not-source list.</td><td>Admin</td></tr>
                  <tr><td>Billing</td><td>Invoices, PDFs, payment status, subscription management.</td><td>Admin, BDM</td></tr>
                  <tr><td>Data Backups</td><td>Create, download, restore and delete backups of your workspace data.</td><td>Admin</td></tr>
                  <tr><td>Settings</td><td>Eleven configuration tabs — see below.</td><td>Admin</td></tr>
                  <tr><td>Profile</td><td>Your own details, password and notification preferences.</td><td>Everyone</td></tr>
                </tbody>
              </table>
            </div>

            <h3>Reports in detail</h3>
            <div className={styles.tableWrap}>
              <table>
                <thead>
                  <tr>
                    <th>Report</th>
                    <th>Answers</th>
                    <th>Filters</th>
                  </tr>
                </thead>
                <tbody>
                  <tr><td>Client Analytics</td><td>Per-company contacts, leads, sends, replies, bounces, placements and unsubscribes.</td><td>Search, industry, category, date range</td></tr>
                  <tr><td>Campaign Performance</td><td>How each campaign performed, including unsubscribes.</td><td>Search, status, date range</td></tr>
                  <tr><td>Mailbox Health</td><td>Deliverability per sending account.</td><td>Search, warmup status</td></tr>
                  <tr><td>Daily Activity</td><td>Sent, opened, replied and bounced over time.</td><td>7–180 days, daily or weekly</td></tr>
                  <tr><td>Contact Engagement</td><td>How each individual has engaged across all outreach.</td><td>Search, client, minimum emails, has replied</td></tr>
                  <tr><td>Domain Deliverability</td><td>Performance broken down by recipient domain.</td><td>7–180 days</td></tr>
                </tbody>
              </table>
            </div>
            <p>Every report exports to file, capped at 10,000 rows per export.</p>

            <h3>Settings tabs</h3>
            <div className={styles.tableWrap}>
              <table>
                <thead>
                  <tr>
                    <th>#</th>
                    <th>Tab</th>
                    <th>Controls</th>
                  </tr>
                </thead>
                <tbody>
                  <tr><td className={styles.num}>1</td><td>Job Filters</td><td>Target titles, locations, exclusion keywords, salary floor.</td></tr>
                  <tr><td className={styles.num}>2</td><td>Job Source APIs</td><td>Which lead sources are enabled, and their credentials.</td></tr>
                  <tr><td className={styles.num}>3</td><td>AI / LLM</td><td>AI provider selection and model choice.</td></tr>
                  <tr><td className={styles.num}>4</td><td>Contacts</td><td>Contact discovery provider and enrichment behaviour.</td></tr>
                  <tr><td className={styles.num}>5</td><td>Validation</td><td>Validation provider and catch-all policy.</td></tr>
                  <tr><td className={styles.num}>6</td><td>Outreach</td><td>Send mode, personalisation, humanisation, tracking.</td></tr>
                  <tr><td className={styles.num}>7</td><td>Business Rules</td><td>Daily limit, cooldown, per-company cap, salary threshold, size ceiling, excluded industries.</td></tr>
                  <tr><td className={styles.num}>8</td><td>Deliverability</td><td>Throttles, bounce handling, complaint thresholds, DKIM.</td></tr>
                  <tr><td className={styles.num}>9</td><td>LOB Lead Sources</td><td>Signal-source credentials and the intent-signal scheduler switch.</td></tr>
                  <tr><td className={styles.num}>10</td><td>Source Tuning</td><td>Per-source batch size, page depth, result caps and parallelism.</td></tr>
                  <tr><td className={styles.num}>11</td><td>Notifications</td><td>The sender identity used for system and notification email, with a “send test” button.</td></tr>
                </tbody>
              </table>
            </div>
            <p>
              Every provider tab has a <strong>test connection</strong> button, so you can confirm a
              credential works before a pipeline depends on it. Stored credentials are encrypted and
              never displayed back to you — a saved field shows only that a value is set.
            </p>
          </section>

          {/* ============ 13 ============ */}
          <section id="lob" className={styles.section}>
            <div className={styles.secHead}>
              <span className={styles.secNum}>13</span>
              <h2 className={styles.secTitle}>Lines of Business</h2>
            </div>
            <p className={styles.secIntro}>
              A line of business is a self-contained way of selling one service. Each brings its own
              lead sources, ideal-customer profile, business rules, messaging tone, lead-table columns
              and intent signals.
            </p>
            <div className={styles.tableWrap}>
              <table>
                <thead>
                  <tr>
                    <th>Type</th>
                    <th>Prospecting approach</th>
                  </tr>
                </thead>
                <tbody>
                  <tr><td>Staffing &amp; Recruiting</td><td>Job-board sourcing and hiring decision-maker targeting.</td></tr>
                  <tr><td>Revenue Cycle Management</td><td>Healthcare provider targeting for medical billing and coding services.</td></tr>
                  <tr><td>Software Development</td><td>Tech company prospecting aimed at engineering leadership.</td></tr>
                  <tr><td>AI &amp; Agent Services</td><td>AI-adoption signal tracking and innovation-leader targeting.</td></tr>
                  <tr><td>Digital Marketing</td><td>Website-audit-based prospecting — SEO and performance gap analysis.</td></tr>
                  <tr><td>Custom</td><td>Define your own sources, profile and rules from scratch.</td></tr>
                </tbody>
              </table>
            </div>

            <h3>Intent signals</h3>
            <p>
              Beyond job boards, seven signal types can create leads on their own. Each line of
              business decides which apply to it:
            </p>
            <div className={`${styles.grid} ${styles.g3}`}>
              <div className={styles.card}><h4>Provider registry</h4><p>Licensed healthcare providers matching your criteria.</p></div>
              <div className={styles.card}><h4>Funding events</h4><p>Companies that recently raised — new budget, new hiring.</p></div>
              <div className={styles.card}><h4>Site performance</h4><p>Websites failing performance audits, for marketing and development offers.</p></div>
              <div className={styles.card}><h4>Technology stack</h4><p>Companies running, or conspicuously missing, specific technologies.</p></div>
              <div className={styles.card}><h4>Open-source activity</h4><p>Engineering organisations visible through their public repositories.</p></div>
              <div className={styles.card}><h4>Hiring patterns</h4><p>Mined from your existing lead data at no external cost.</p></div>
              <div className={styles.card}><h4>News</h4><p>Public news feeds indicating expansion, launches or change.</p></div>
            </div>
            <p>
              Signals are scored into four tiers — <strong>Cold, Warm, Hot, Burning</strong> — using
              weights tuned per line of business. You can run the intent engine for one line of
              business on demand, or leave it to the schedule.
            </p>
          </section>

          {/* ============ 14 ============ */}
          <section id="integrations" className={styles.section}>
            <div className={styles.secHead}>
              <span className={styles.secNum}>14</span>
              <h2 className={styles.secTitle}>Integrations</h2>
            </div>
            <p className={styles.secIntro}>
              You bring your own provider accounts and connect them in Settings. Every category has
              several options, so you are never locked to one vendor — and every category has a mock
              mode for training and testing without spending credits.
            </p>
            <div className={styles.tableWrap}>
              <table>
                <thead>
                  <tr>
                    <th>Category</th>
                    <th>Options</th>
                  </tr>
                </thead>
                <tbody>
                  <tr><td>Job &amp; lead sources</td><td>Apollo, JSearch, TheirStack, Google Jobs (SerpAPI), Adzuna, SearchAPI, USAJobs, Jooble, JobDataFeeds, Coresignal, Fantastic.jobs</td></tr>
                  <tr><td>Contact discovery</td><td>Apollo, Seamless, Hunter.io, Snov.io, RocketReach, People Data Labs, Proxycurl</td></tr>
                  <tr><td>Company enrichment</td><td>Clearbit, OpenCorporates, Apollo firmographics</td></tr>
                  <tr><td>Email validation</td><td>NeverBounce, ZeroBounce, Hunter, Clearout, Emailable, MailboxValidator, Reacher</td></tr>
                  <tr><td>Email sending</td><td>Any SMTP provider — Google Workspace, Microsoft 365, custom domains</td></tr>
                  <tr><td>AI engines</td><td>Groq, OpenAI, Anthropic, Google Gemini</td></tr>
                  <tr><td>CRM</td><td>HubSpot, Salesforce — bidirectional sync with a full sync history</td></tr>
                  <tr><td>Team notifications</td><td>Slack, Microsoft Teams</td></tr>
                  <tr><td>SMS &amp; calling</td><td>Twilio</td></tr>
                  <tr><td>Calendar</td><td>Calendly, Cal.com — bookings tracked against contacts and deals</td></tr>
                  <tr><td>Signal sources</td><td>Provider registry, Google Business, Crunchbase, BuiltWith, PageSpeed, GitHub, news feeds</td></tr>
                  <tr><td>Payments</td><td>Stripe for subscriptions and invoice checkout, or manual payment recording</td></tr>
                </tbody>
              </table>
            </div>

            <h3>Your own API access</h3>
            <ul>
              <li>
                <strong>API keys</strong> — create scoped keys with expiry dates for your own
                integrations, and revoke them at any time.
              </li>
              <li>
                <strong>Webhooks</strong> — subscribe to events and receive signed payloads you can
                verify. Failed deliveries retry three times with increasing delays.
              </li>
            </ul>
            <p>
              Webhook events available today: email sent, opened, clicked, replied and bounced;
              contact unsubscribed; campaign completed; lead created.
            </p>
          </section>

          {/* ============ 15 ============ */}
          <section id="automation" className={styles.section}>
            <div className={styles.secHead}>
              <span className={styles.secNum}>15</span>
              <h2 className={styles.secTitle}>Background automation</h2>
            </div>
            <p className={styles.secIntro}>
              Seventeen scheduled jobs keep the platform working while nobody is logged in. Every one
              can be switched off individually from the Automation screen — useful during a migration,
              a quiet period, or a provider outage.
            </p>
            <div className={styles.tableWrap}>
              <table>
                <thead>
                  <tr>
                    <th>Group</th>
                    <th>Job</th>
                    <th>Runs</th>
                  </tr>
                </thead>
                <tbody>
                  <tr><td rowSpan={9}>Warmup Engine</td><td>Daily warmup assessment</td><td className={styles.num}>Daily, 00:05 UTC</td></tr>
                  <tr><td>Peer warmup cycle</td><td className={styles.num}>Hourly, 9am–5pm UTC</td></tr>
                  <tr><td>Auto-reply cycle</td><td className={styles.num}>Hourly at :30, 9am–5pm UTC</td></tr>
                  <tr><td>Daily count reset</td><td className={styles.num}>Daily, 00:00 UTC</td></tr>
                  <tr><td>DNS health checks</td><td className={styles.num}>Every 12 hours</td></tr>
                  <tr><td>Blacklist checks</td><td className={styles.num}>Every 12 hours</td></tr>
                  <tr><td>Daily log snapshot</td><td className={styles.num}>Daily, 23:55 UTC</td></tr>
                  <tr><td>Auto recovery check</td><td className={styles.num}>Daily, 06:00 UTC</td></tr>
                  <tr><td>Read emulation</td><td className={styles.num}>Every 30 minutes</td></tr>
                  <tr><td>Lead Pipeline</td><td>Scheduled lead sourcing</td><td className={styles.num}>6× daily, every 4 hours</td></tr>
                  <tr><td rowSpan={4}>Campaign &amp; Outreach</td><td>Campaign sequence processor</td><td className={styles.num}>Every 2 minutes</td></tr>
                  <tr><td>Inbox sync</td><td className={styles.num}>Every 5 min, 8am–7pm UTC</td></tr>
                  <tr><td>Check outreach replies</td><td className={styles.num}>Every 15 min, 8am–7pm UTC</td></tr>
                  <tr><td>Campaign auto-enrolment</td><td className={styles.num}>Every 30 minutes</td></tr>
                  <tr><td rowSpan={3}>Intelligence</td><td>Daily lead scoring</td><td className={styles.num}>Daily, 03:00 UTC</td></tr>
                  <tr><td>Nightly CRM sync</td><td className={styles.num}>Daily, 04:00 UTC</td></tr>
                  <tr><td>Monthly cost analysis</td><td className={styles.num}>1st of month, 03:30 UTC</td></tr>
                  <tr><td rowSpan={3}>System</td><td>Daily data backup</td><td className={styles.num}>Daily, 02:00 UTC</td></tr>
                  <tr><td>Backup cleanup</td><td className={styles.num}>Daily, 02:30 UTC</td></tr>
                  <tr><td>Daily cost aggregation</td><td className={styles.num}>Daily, 23:45 UTC</td></tr>
                </tbody>
              </table>
            </div>
            <p>
              Additional monitors run alongside these: hourly campaign health checks that auto-pause on
              a threshold breach, and continuous complaint-rate monitoring. A locking mechanism
              guarantees a job never runs twice at the same moment, even across multiple servers.
            </p>
          </section>

          {/* ============ 16 ============ */}
          <section id="roles" className={styles.section}>
            <div className={styles.secHead}>
              <span className={styles.secNum}>16</span>
              <h2 className={styles.secTitle}>Users, roles &amp; permissions</h2>
            </div>
            <p className={styles.secIntro}>
              Four built-in roles cover most teams. Where they do not, you can build your own on top of
              them.
            </p>
            <div className={styles.tableWrap}>
              <table>
                <thead>
                  <tr>
                    <th>Role</th>
                    <th>Scope</th>
                    <th>Typical holder</th>
                  </tr>
                </thead>
                <tbody>
                  <tr><td>Super Admin</td><td>Everything, across all workspaces. Manages workspaces, roles and the audit log.</td><td>The platform operator</td></tr>
                  <tr><td>Admin</td><td>Everything inside one workspace, including settings, billing and backups. Cannot manage roles, workspaces or the audit log.</td><td>Workspace owner</td></tr>
                  <tr><td>BDM</td><td>Client-facing work: leads, contacts, campaigns, inbox, deals and reports. Read-only on the dashboard.</td><td>Business development</td></tr>
                  <tr><td>Recruiter</td><td>Focused on candidates and deal delivery.</td><td>Delivery team</td></tr>
                </tbody>
              </table>
            </div>

            <h3>The permission matrix</h3>
            <p>
              Permissions are set per module at four levels: <strong>Full access · Read &amp; write ·
              Read only · No access</strong>. Three modules go further and are controlled tab by tab
              rather than as a whole:
            </p>
            <ul>
              <li><strong>Warmup Engine</strong> — each of its seven tabs independently.</li>
              <li>
                <strong>Pipelines</strong> — each of the four stages independently, so a user can run
                sourcing but not outreach.
              </li>
              <li>
                <strong>Settings</strong> — each of the ten configuration tabs independently, so a user
                can tune sources without seeing everything else.
              </li>
            </ul>

            <h3>Custom roles</h3>
            <p>
              Create a role, give it a display name, base it on one of the built-in roles, then adjust
              its matrix. Built-in roles cannot be deleted, and neither can a role that is currently in
              use by a user.
            </p>

            <h3>Account security controls</h3>
            <ul>
              <li>Email verification is required before an account becomes active.</li>
              <li>Accounts lock automatically after repeated failed logins; a super admin can unlock them.</li>
              <li>
                Every login attempt is recorded with its outcome and reason — invalid credentials,
                inactive, unverified or locked.
              </li>
              <li>Sessions expire and refresh silently in the background, so you are not logged out mid-task.</li>
              <li>Each user belongs to exactly one workspace and cannot see another’s data.</li>
              <li>Unverified accounts older than 72 hours are cleaned up automatically.</li>
            </ul>

            <h3>Notification preferences</h3>
            <p>
              Every user has two master switches — in-app notifications and email notifications —
              editable by an admin or by the user on their own profile. They gate every notification the
              platform would otherwise send that person: deal broadcasts, assignments and system alerts.
            </p>
          </section>

          {/* ============ 17 ============ */}
          <section id="plans" className={styles.section}>
            <div className={styles.secHead}>
              <span className={styles.secNum}>17</span>
              <h2 className={styles.secTitle}>Plans, limits &amp; billing</h2>
            </div>
            <p className={styles.secIntro}>
              Flat monthly pricing with no per-seat charge, a 14-day trial on every plan, and 20% off
              when billed annually.
            </p>
            <div className={styles.tableWrap}>
              <table>
                <thead>
                  <tr>
                    <th>&nbsp;</th>
                    <th>Starter</th>
                    <th>Professional</th>
                    <th>Enterprise</th>
                  </tr>
                </thead>
                <tbody>
                  <tr><td>Monthly price</td><td className={styles.num}>$49</td><td className={styles.num}>$99</td><td className={styles.num}>$199</td></tr>
                  <tr><td>Annual, per month</td><td className={styles.num}>$39</td><td className={styles.num}>$79</td><td className={styles.num}>$159</td></tr>
                  <tr><td>Users</td><td className={styles.num}>3</td><td className={styles.num}>10</td><td>Unlimited</td></tr>
                  <tr><td>Mailboxes</td><td className={styles.num}>5</td><td className={styles.num}>25</td><td>Unlimited</td></tr>
                  <tr><td>Emails per day</td><td className={styles.num}>500</td><td className={styles.num}>2,500</td><td className={styles.num}>10,000+</td></tr>
                  <tr><td>Contacts</td><td className={styles.num}>500</td><td className={styles.num}>5,000</td><td>Unlimited</td></tr>
                  <tr><td>Leads</td><td className={styles.num}>1,000</td><td className={styles.num}>10,000</td><td>Unlimited</td></tr>
                  <tr><td>Active campaigns</td><td className={styles.num}>5</td><td className={styles.num}>25</td><td>Unlimited</td></tr>
                  <tr><td>Lead sources</td><td className={styles.num}>3</td><td className={styles.num}>7</td><td>All</td></tr>
                  <tr><td>Contact providers</td><td className={styles.num}>2</td><td className={styles.num}>5</td><td>All</td></tr>
                  <tr><td>AI engines</td><td className={styles.num}>1</td><td className={styles.num}>2</td><td>All 4</td></tr>
                  <tr><td>A/B testing</td><td className={styles.no}>—</td><td className={styles.yes}>Yes</td><td className={styles.yes}>Yes</td></tr>
                  <tr><td>Unified inbox</td><td className={styles.no}>—</td><td className={styles.yes}>Yes</td><td className={styles.yes}>Yes</td></tr>
                  <tr><td>CRM deals</td><td className={styles.no}>—</td><td className={styles.yes}>Yes</td><td className={styles.yes}>Yes</td></tr>
                  <tr><td>ICP Wizard</td><td className={styles.no}>—</td><td className={styles.yes}>Yes</td><td className={styles.yes}>Yes</td></tr>
                  <tr><td>Analytics</td><td>Basic</td><td>Advanced</td><td>Full, plus API</td></tr>
                  <tr><td>Webhooks &amp; integrations</td><td className={styles.no}>—</td><td>Basic</td><td>Full</td></tr>
                  <tr><td>Custom tracking domains</td><td className={styles.no}>—</td><td className={styles.num}>1</td><td>Unlimited</td></tr>
                  <tr><td>Self-hosted option</td><td className={styles.no}>—</td><td className={styles.no}>—</td><td className={styles.yes}>Yes</td></tr>
                  <tr><td>White-label</td><td className={styles.no}>—</td><td className={styles.no}>—</td><td className={styles.yes}>Yes</td></tr>
                  <tr><td>Support</td><td>Email</td><td>Email and chat</td><td>Dedicated manager</td></tr>
                </tbody>
              </table>
            </div>
            <p>
              Plan limits are enforced at the moment you create something, not silently in the
              background — you are told immediately if an action would exceed your plan, so nothing is
              ever created and then quietly discarded.
            </p>

            <h3>Invoicing</h3>
            <ul>
              <li>Invoices are generated monthly and numbered sequentially, with duplicate protection.</li>
              <li>Each invoice carries line items, tax at your configured rate, and a downloadable PDF.</li>
              <li>Status moves Draft → Sent → Paid, or → Overdue if the due date passes.</li>
              <li>
                Automated email at each point: a new invoice with the PDF attached, an overdue
                reminder, and a payment acknowledgement.
              </li>
              <li>
                Pay by card through hosted checkout, or have payments recorded manually — bank
                transfer, cheque or card.
              </li>
              <li>Subscriptions can be started, reviewed and cancelled at period end from the Billing screen.</li>
            </ul>

            <h3>Cost tracking &amp; ROI</h3>
            <p>
              Separate from what you pay for NeuraLeads, the platform meters what your own provider
              accounts cost you, in five categories: <strong>lead sourcing, contact discovery,
              validation, sending and AI</strong>. Costs are captured per call — accurate to fractions
              of a cent for AI tokens — and surface as cost per source, cost per lead and return on
              investment in Analytics. Credit usage is metered per workspace with a running balance.
            </p>
          </section>

          {/* ============ 18 ============ */}
          <section id="data" className={styles.section}>
            <div className={styles.secHead}>
              <span className={styles.secNum}>18</span>
              <h2 className={styles.secTitle}>Your data — privacy, control &amp; recovery</h2>
            </div>
            <p className={styles.secIntro}>
              You remain the controller of the contact data in your workspace. These are the controls
              the platform gives you to honour that responsibility.
            </p>

            <h3>Isolation</h3>
            <p>
              Every record belongs to exactly one workspace, and every query is scoped to the workspace
              of the person making it. There is no shared pool of contacts, leads or campaigns between
              customers.
            </p>

            <h3>Data-subject rights</h3>
            <div className={`${styles.grid} ${styles.g2}`}>
              <div className={styles.card}>
                <h4>Right of access</h4>
                <p>
                  Export everything held about one email address in a single action: their contact
                  record, every email sent to them, every reply, any site visits, and their suppression
                  status.
                </p>
              </div>
              <div className={styles.card}>
                <h4>Right to erasure</h4>
                <p>
                  Anonymise a person’s details on request. The address is added to your suppression
                  list at the same time, so erasure cannot accidentally lead to them being contacted
                  again, and the action is written to your audit trail.
                </p>
              </div>
            </div>

            <h3>Suppression &amp; unsubscribe</h3>
            <ul>
              <li>
                Every outbound email carries an unsubscribe path, and an unsubscribe is honoured
                immediately and permanently.
              </li>
              <li>You can suppress a single address or an entire domain by hand at any time.</li>
              <li>Hard bounces suppress automatically.</li>
              <li>A reply categorised “do not contact” removes that person from further outreach.</li>
              <li>
                Suppression is checked at position two of the send gate — before validation, before any
                campaign logic.
              </li>
            </ul>

            <h3>Backups</h3>
            <p>
              A backup of your workspace data is taken automatically every day, and old backups are
              cleaned up on a schedule. From the Data Backups screen you can create a backup on demand,
              download one, restore from one, or delete one. Restoring is a deliberate, confirmed
              action — you type the word RESTORE to proceed — because it replaces current data.
            </p>

            <h3>Audit trail</h3>
            <p>
              Login attempts, permission changes, AI decisions, scheduled job runs, campaign sends and
              data-erasure actions are all recorded. Administrators can review authentication history,
              currently active users and system activity at any time.
            </p>

            <h3>Platform security</h3>
            <ul>
              <li>
                Passwords are stored using a modern memory-hard hashing algorithm — they are never
                recoverable, only reset.
              </li>
              <li>Provider credentials you enter are encrypted at rest and never shown back to you.</li>
              <li>All traffic is served over HTTPS with strict transport security and a content security policy.</li>
              <li>Login, pipeline execution and billing actions are rate-limited to resist abuse.</li>
              <li>
                Webhook payloads are cryptographically signed, so your receiving system can verify they
                genuinely came from us.
              </li>
              <li>API keys are stored only as hashes, carry scopes, and can be given an expiry date.</li>
            </ul>
            <div className={styles.note}>
              <span className={styles.eyebrow}>Deliberately not documented here</span>
              This handbook does not publish infrastructure addresses, internal service names,
              credential formats, database structure or security configuration. If you need that level
              of detail for a vendor security review, request the security documentation pack through
              your account contact — it is shared under NDA.
            </div>
          </section>

          {/* ============ 19 ============ */}
          <section id="rules" className={styles.section}>
            <div className={styles.secHead}>
              <span className={styles.secNum}>19</span>
              <h2 className={styles.secTitle}>Default business rules</h2>
            </div>
            <p className={styles.secIntro}>
              These are the shipping defaults. All of them are configurable per workspace, and several
              can be overridden per line of business.
            </p>
            <div className={styles.tableWrap}>
              <table>
                <thead>
                  <tr>
                    <th>Rule</th>
                    <th>Default</th>
                    <th>Why it exists</th>
                  </tr>
                </thead>
                <tbody>
                  <tr><td>Daily send limit per mailbox</td><td className={styles.num}>30</td><td>Keeps volume inside what a real person could send, which is what inbox providers expect.</td></tr>
                  <tr><td>Cooldown between emails to one person</td><td className={styles.num}>10 days</td><td>Prevents the same prospect being chased from several angles at once.</td></tr>
                  <tr><td>Contacts per company per opportunity</td><td className={styles.num}>2</td><td>Protects the account relationship — no carpet-bombing.</td></tr>
                  <tr><td>Minimum salary on a sourced role</td><td className={styles.num}>$40,000</td><td>Filters out roles too small to be worth a placement.</td></tr>
                  <tr><td>Company size ceiling</td><td className={styles.num}>200 employees</td><td>Keeps sourcing inside the ideal-customer profile. Set to 0 to disable.</td></tr>
                  <tr><td>Excluded industries</td><td>IT, staffing, government</td><td>Competitors and non-buyers. Fully editable.</td></tr>
                  <tr><td>Domain throttle — major consumer providers</td><td className={styles.num}>30 / day</td><td>These providers are the strictest about volume from one sender.</td></tr>
                  <tr><td>Domain throttle — all other domains</td><td className={styles.num}>50 / day</td><td>Prevents one company’s mail server from seeing a burst.</td></tr>
                  <tr><td>Complaint-rate auto-pause</td><td className={styles.num}>0.3%</td><td>The industry line beyond which reputation damage compounds quickly.</td></tr>
                  <tr><td>Validation requirement</td><td>Valid only</td><td>Bounces are the fastest way to lose a sending domain.</td></tr>
                  <tr><td>Target industries</td><td>22 non-IT industries</td><td>The default ideal-customer profile. Editable per line of business.</td></tr>
                </tbody>
              </table>
            </div>
          </section>

          {/* ============ 20 ============ */}
          <section id="faq" className={styles.section}>
            <div className={styles.secHead}>
              <span className={styles.secNum}>20</span>
              <h2 className={styles.secTitle}>Frequently asked questions</h2>
            </div>

            <details className={styles.faqItem}>
              <summary>Do I need my own API keys, or is everything included?</summary>
              <div className={styles.faqBody}>
                <p>
                  You bring your own accounts for lead sources, contact discovery, validation and AI.
                  This is deliberate: you pay those providers at their own rates rather than a marked-up
                  reseller price, you keep the relationship and the data, and you can switch provider
                  whenever you like. Every category also has a free or low-cost option to start with,
                  and a mock mode so you can learn the product before spending anything.
                </p>
              </div>
            </details>

            <details className={styles.faqItem}>
              <summary>How long before I can send at full volume?</summary>
              <div className={styles.faqBody}>
                <p>
                  Plan for 20 to 45 days on a brand-new domain, depending on the warmup profile you
                  choose. An established domain that already sends business mail warms faster. The
                  platform will let you send sooner — it simply cannot protect you from the
                  consequences, which is why the warmup profiles exist.
                </p>
              </div>
            </details>

            <details className={styles.faqItem}>
              <summary>What happens if I exceed my daily email limit?</summary>
              <div className={styles.faqBody}>
                <p>
                  Nothing is lost. Emails beyond the limit are queued and sent on the next available day
                  inside your send window. You can also raise the limit, add mailboxes, or upgrade your
                  plan.
                </p>
              </div>
            </details>

            <details className={styles.faqItem}>
              <summary>Can I use Gmail or Outlook mailboxes?</summary>
              <div className={styles.faqBody}>
                <p>
                  Yes. Any SMTP-capable provider works, including Google Workspace, Microsoft 365 and
                  custom domain hosts. Note that some Microsoft 365 tenants disable basic SMTP
                  authentication by default — if a mailbox refuses to connect, ask your IT administrator
                  to enable authenticated SMTP for that account, or connect it over OAuth instead.
                </p>
              </div>
            </details>

            <details className={styles.faqItem}>
              <summary>Will an email ever send that I did not review?</summary>
              <div className={styles.faqBody}>
                <p>
                  That is your choice. Turn on preview mode and every email becomes a draft you approve
                  first. Leave it off and the campaign engine sends within your schedule, still subject
                  to all ten send-gate checks. The AI Reply Agent works the same way: human-in-the-loop
                  by default, autopilot only if you enable it.
                </p>
              </div>
            </details>

            <details className={styles.faqItem}>
              <summary>What stops two of my reps from emailing the same person?</summary>
              <div className={styles.faqBody}>
                <p>
                  Three separate mechanisms: cross-campaign de-duplication in the send gate, the
                  per-company contact cap, and the cooldown period. On the deal side, the claim queue
                  means a deal has exactly one owner from the moment someone claims it.
                </p>
              </div>
            </details>

            <details className={styles.faqItem}>
              <summary>Can I try the product without spending provider credits?</summary>
              <div className={styles.faqBody}>
                <p>
                  Yes. Every integration category has a mock mode that returns realistic sample data.
                  New Starter workspaces are also seeded with sample leads, contacts, a mailbox and a
                  campaign, so the interface is not empty on day one.
                </p>
              </div>
            </details>

            <details className={styles.faqItem}>
              <summary>Can I switch plans, and what happens to my data?</summary>
              <div className={styles.faqBody}>
                <p>
                  Upgrade at any time for immediate access to the new limits. Downgrade at any time and
                  your current plan runs to the end of the billing period. Your data is not deleted when
                  limits shrink — you simply cannot create new records above the new limit until you are
                  back under it.
                </p>
              </div>
            </details>

            <details className={styles.faqItem}>
              <summary>How do I know what my outreach actually costs me?</summary>
              <div className={styles.faqBody}>
                <p>
                  Analytics tracks every provider call in five categories and reports cost per source,
                  cost per lead and return on investment. AI token cost is metered per call rather than
                  estimated, so the figures are real, not averages.
                </p>
              </div>
            </details>

            <details className={styles.faqItem}>
              <summary>What happens to a contact who replies “not interested”?</summary>
              <div className={styles.faqBody}>
                <p>
                  Their sequence stops immediately. The message is categorised in your inbox, the
                  sentiment is recorded, and the send gate will not re-enter them into outreach. If the
                  reply reads as “do not contact”, they are suppressed outright.
                </p>
              </div>
            </details>

            <details className={styles.faqItem}>
              <summary>Can I export my data?</summary>
              <div className={styles.faqBody}>
                <p>
                  Yes. Leads, contacts and all six reports export to file, exactly as you have them
                  filtered and columned on screen. A data-subject export for one individual is a
                  separate, purpose-built action.
                </p>
              </div>
            </details>

            <details className={styles.faqItem}>
              <summary>What is the difference between a report and analytics?</summary>
              <div className={styles.faqBody}>
                <p>
                  Reports are operational — filterable, sortable, exportable tables you use to check
                  work and share with a client. Analytics is strategic — revenue, win rate, ROI, cost
                  per lead and team performance, aimed at decisions rather than tasks.
                </p>
              </div>
            </details>
          </section>

          {/* ============ 21 ============ */}
          <section id="firstweek" className={styles.section}>
            <div className={styles.secHead}>
              <span className={styles.secNum}>21</span>
              <h2 className={styles.secTitle}>Your first week</h2>
            </div>
            <p className={styles.secIntro}>
              A realistic path from an empty workspace to a first reply.
            </p>
            <div className={styles.tableWrap}>
              <table>
                <thead>
                  <tr>
                    <th>Day</th>
                    <th>Do this</th>
                    <th>Result</th>
                  </tr>
                </thead>
                <tbody>
                  <tr><td className={styles.num}>1</td><td>Connect your mailboxes, set signatures and daily limits, and start warmup on the Standard profile. Check that SPF, DKIM and DMARC are green on the DNS tab.</td><td>The reputation clock starts running.</td></tr>
                  <tr><td className={styles.num}>1</td><td>Pick your line of business and let it seed your sources, ICP and rules. Adjust the business rules to your reality.</td><td>Targeting is defined.</td></tr>
                  <tr><td className={styles.num}>2</td><td>Add credentials for one lead source, one contact provider, one validation provider and one AI engine. Use “test connection” on each.</td><td>Every dependency is proven before it matters.</td></tr>
                  <tr><td className={styles.num}>2</td><td>Run the ICP Wizard, then run lead sourcing once. Read the run counters, not just the total.</td><td>You learn which filter is doing the work.</td></tr>
                  <tr><td className={styles.num}>3</td><td>Run contact enrichment, then validation. Review the priority tiers on your contacts.</td><td>A clean, sendable list.</td></tr>
                  <tr><td className={styles.num}>4</td><td>Build a three-step sequence from a template, and turn on preview mode.</td><td>Drafts, not sends.</td></tr>
                  <tr><td className={styles.num}>4</td><td>Review every draft on the Email Preview screen. Fix anything scoring badly for spam. Approve a small batch.</td><td>You see exactly what a prospect will see.</td></tr>
                  <tr><td className={styles.num}>5</td><td>Release the batch inside a narrow send window at low volume. Watch the inbox and the mailbox health score.</td><td>First real sends, safely.</td></tr>
                  <tr><td className={styles.num}>6–7</td><td>Work the replies. Categorise them, use macros, convert interest into deals and claim them.</td><td>The loop is closed end to end.</td></tr>
                </tbody>
              </table>
            </div>
            <div className={`${styles.note} ${styles.noteGood}`}>
              <span className={styles.eyebrow}>The one habit worth forming</span>
              Read the pipeline run counters every time. The total number of leads tells you almost
              nothing; the drop reasons tell you whether your filters are too tight, too loose, or
              pointed at the wrong market. Ten minutes there is worth more than a week of extra volume.
            </div>
          </section>
        </main>
      </div>

      <div className={styles.closing}>
        <span>NeuraLeads AI Agent — customer handbook</span>
        <span>Questions your admin cannot answer belong with your account contact.</span>
      </div>
    </div>
  )
}
