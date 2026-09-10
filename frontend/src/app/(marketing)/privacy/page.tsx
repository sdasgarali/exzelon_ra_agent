import type { Metadata } from 'next'
import Link from 'next/link'
import LegalShell, {
  LegalSectionBlock,
  Note,
  Pending,
  TableWrap,
} from '@/components/marketing/legal/LegalShell'
import type { LegalSection } from '@/components/marketing/legal/types'

export const metadata: Metadata = {
  title: 'Privacy Policy',
  description:
    'How NeuraLeads handles personal data — what we collect as a controller, what we process on our customers’ behalf, our sub-processors, and how to exercise your rights.',
  alternates: { canonical: '/privacy' },
}

const SECTIONS: LegalSection[] = [
  { id: 'roles', title: 'Two different roles' },
  { id: 'controller-data', title: 'Data we collect about you' },
  { id: 'customer-data', title: 'Data we process for customers' },
  { id: 'sources', title: 'Where prospect data comes from' },
  { id: 'purposes', title: 'Why we use data' },
  { id: 'ai', title: 'AI processing' },
  { id: 'subprocessors', title: 'Sub-processors' },
  { id: 'cookies', title: 'Cookies and tracking' },
  { id: 'transfers', title: 'International transfers' },
  { id: 'retention', title: 'How long we keep data' },
  { id: 'security', title: 'How we protect data' },
  { id: 'rights', title: 'Your rights as a customer' },
  { id: 'recipients', title: 'If you received an email' },
  { id: 'children', title: 'Children' },
  { id: 'changes', title: 'Changes to this policy' },
  { id: 'contact', title: 'Contacting us' },
]

const EFFECTIVE = '10 September 2026'

export default function PrivacyPage() {
  return (
    <LegalShell
      eyebrow="Legal"
      title="Privacy Policy"
      standfirst="NeuraLeads is an outbound sales platform. That means we hold two very different kinds of personal data, under two different responsibilities — and this policy keeps them clearly apart."
      effective={EFFECTIVE}
      updated={EFFECTIVE}
      sections={SECTIONS}
      closing={
        <p>
          Read alongside our <Link href="/terms">Terms of Service</Link>. If anything here
          conflicts with a signed agreement between us, the signed agreement governs.
        </p>
      }
    >
      <LegalSectionBlock id="roles" num={1} title="Two different roles">
        <p>
          NeuraLeads (“we”, “us”) is operated by <Pending>legal entity name</Pending>, registered
          at <Pending>registered address</Pending>. This policy explains how personal data is
          handled across the NeuraLeads website and platform.
        </p>
        <p>
          Almost every privacy question about this service depends on <em>whose</em> data is being
          discussed, because we act in two capacities:
        </p>
        <TableWrap>
          <table>
            <thead>
              <tr>
                <th>Whose data</th>
                <th>Examples</th>
                <th>Our role</th>
                <th>Who decides how it is used</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>Our customers</td>
                <td>The account holder and their team — name, work email, password, billing details, usage logs</td>
                <td>Controller</td>
                <td>Us</td>
              </tr>
              <tr>
                <td>Our customers’ prospects</td>
                <td>People a customer sources, enriches and contacts — name, work email, job title, employer, engagement events</td>
                <td>Processor</td>
                <td>The customer</td>
              </tr>
            </tbody>
          </table>
        </TableWrap>
        <p>
          Where we act as a <strong>processor</strong>, we handle prospect data only on the
          documented instructions of the customer who put it into their workspace. That customer
          decides who to contact, on what legal basis, and for how long the data is kept. We do not
          sell personal data, and we do not use one customer’s data for another customer’s benefit.
        </p>
        <Note label="If you are a prospect">
          <p>
            If you received an email that was sent through NeuraLeads and want it to stop, go
            straight to <Link href="#recipients">section 13</Link>. It explains what to do and who
            is actually responsible.
          </p>
        </Note>
      </LegalSectionBlock>

      <LegalSectionBlock id="controller-data" num={2} title="Data we collect about you as a customer">
        <p>When you visit our site, trial the product, or hold an account, we collect:</p>
        <ul>
          <li>
            <strong>Account data</strong> — name, work email address, hashed password, workspace
            name, role, and email-verification status.
          </li>
          <li>
            <strong>Billing data</strong> — billing name, billing email, billing address, tax rate,
            plan, invoice history and payment records. Card details are handled by our payment
            processor and never reach our servers.
          </li>
          <li>
            <strong>Configuration data</strong> — settings you choose, including credentials for
            the third-party providers you connect. These are encrypted at rest and are never
            displayed back to you.
          </li>
          <li>
            <strong>Usage and security logs</strong> — sign-in attempts with their outcome, IP
            address, browser user agent, actions taken in the product, background job runs, and
            errors. We use these to run, secure and debug the service.
          </li>
          <li>
            <strong>Support correspondence</strong> — what you send us when you ask for help.
          </li>
        </ul>
        <p>
          Our legal bases are performance of our contract with you, our legitimate interest in
          operating and securing the service, and compliance with legal obligations such as tax
          record-keeping.
        </p>
      </LegalSectionBlock>

      <LegalSectionBlock id="customer-data" num={3} title="Data we process on our customers’ behalf">
        <p>
          When a customer uses the platform, personal data about the people they intend to contact
          is stored in their workspace. Typically this is:
        </p>
        <ul>
          <li>Business contact details — name, work email address, job title, and employer.</li>
          <li>Company information — industry, size, website, location and timezone.</li>
          <li>
            The opportunity that prompted the outreach — for example a public job posting, with its
            title, location and salary range.
          </li>
          <li>
            Outreach and engagement records — messages sent, opens, clicks, replies, bounces,
            unsubscribes, and any notes or deal records the customer creates.
          </li>
        </ul>
        <p>
          Each workspace is isolated. Data in one workspace is never visible to another customer,
          and there is no shared pool of contacts between customers.
        </p>
        <p>
          The customer is the controller of this data. They are responsible for having a lawful
          basis to contact each person, for honouring opt-outs, and for responding to requests from
          the people concerned. We assist them — the product includes tooling to export everything
          held about one email address and to erase it on request.
        </p>
      </LegalSectionBlock>

      <LegalSectionBlock id="sources" num={4} title="Where prospect data comes from">
        <p>
          We think people are entitled to know how their details reached a system they never signed
          up for. Prospect data in a customer workspace originates from:
        </p>
        <ul>
          <li>
            <strong>Public job postings and company websites</strong>, retrieved through job-board
            and job-search providers.
          </li>
          <li>
            <strong>Business contact databases</strong> operated by third-party providers, which
            the customer connects using their own account with that provider.
          </li>
          <li>
            <strong>Public registries and public signals</strong> — for example professional
            registries, company records, public code repositories, published news, and technology
            or performance characteristics of a public website.
          </li>
          <li>
            <strong>The customer’s own records</strong>, including data they import or create.
          </li>
          <li>
            <strong>Interactions with the customer’s outreach</strong> — whether a message was
            opened, clicked or replied to — and, where the customer has installed the visitor
            script on their own website, visits to that site.
          </li>
        </ul>
        <p>
          The platform is intended for business-to-business outreach to people in a professional
          capacity. It is not designed for, and must not be used for, marketing to consumers at
          their personal addresses.
        </p>
      </LegalSectionBlock>

      <LegalSectionBlock id="purposes" num={5} title="Why we use data">
        <ul>
          <li>To provide, operate and maintain the platform and the website.</li>
          <li>To authenticate users, enforce plan limits, and prevent abuse of the service.</li>
          <li>To protect sending reputation — for example applying rate limits, throttles, bounce handling and complaint monitoring.</li>
          <li>To bill for the service and keep the records the law requires.</li>
          <li>To provide support and respond to what you ask us.</li>
          <li>To measure and improve the product in aggregate.</li>
          <li>To send service messages such as verification, password resets, invoices and important notices.</li>
        </ul>
        <p>
          We do not sell personal data. We do not share customer or prospect data with advertising
          networks or data brokers.
        </p>
      </LegalSectionBlock>

      <LegalSectionBlock id="ai" num={6} title="AI processing">
        <p>
          The platform uses AI models to draft and rewrite outreach copy, classify inbound replies,
          score leads, enrich company records and suggest next actions. This has two consequences
          worth stating plainly.
        </p>
        <p>
          <strong>Content is sent to an AI provider.</strong> To generate or classify text, the
          relevant content — which may include a prospect’s name, job title, employer and the text
          of their reply — is transmitted to the AI provider configured for that workspace.
        </p>
        <p>
          <strong>In most cases that provider relationship is the customer’s, not ours.</strong>{' '}
          Customers connect their own AI provider accounts using their own keys. Where that is the
          case, the customer’s agreement with that provider governs how the provider may use the
          content, including whether it may be retained or used for model training. We encourage
          customers to review those terms and to select providers and settings that match their own
          commitments to the people they contact.
        </p>
        <p>
          Within our own systems: inbound message content is sanitised before it reaches a model, no
          model is given authority to send an email on its own, every AI decision is logged with its
          reason, and we do not use customer or prospect data to train our own models.
        </p>
      </LegalSectionBlock>

      <LegalSectionBlock id="subprocessors" num={7} title="Sub-processors and third-party providers">
        <p>
          Running the platform means data passes through other organisations. Two categories, with
          an important difference between them:
        </p>
        <h3>Providers we engage</h3>
        <p>
          These support the service itself and act as our sub-processors: cloud hosting and
          infrastructure, database and backup storage, our payment processor, and the mail provider
          used for transactional messages such as verification and invoices.
        </p>
        <h3>Providers the customer connects</h3>
        <p>
          The platform integrates with providers that a customer enables using their own account and
          credentials. Where a customer does so, that provider is the customer’s vendor, and the
          customer’s agreement with them applies. Categories and examples:
        </p>
        <TableWrap>
          <table>
            <thead>
              <tr>
                <th>Category</th>
                <th>Providers that can be connected</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>Job and lead sources</td>
                <td>Apollo, JSearch, TheirStack, SerpAPI, Adzuna, SearchAPI, USAJobs, Jooble, JobDataFeeds, Coresignal, Fantastic.jobs</td>
              </tr>
              <tr>
                <td>Contact discovery</td>
                <td>Apollo, Seamless, Hunter.io, Snov.io, RocketReach, People Data Labs, Proxycurl</td>
              </tr>
              <tr>
                <td>Company enrichment</td>
                <td>Clearbit, OpenCorporates</td>
              </tr>
              <tr>
                <td>Email validation</td>
                <td>NeverBounce, ZeroBounce, Hunter, Clearout, Emailable, MailboxValidator, Reacher</td>
              </tr>
              <tr>
                <td>Email sending</td>
                <td>The customer’s own mail provider, over SMTP</td>
              </tr>
              <tr>
                <td>AI engines</td>
                <td>Groq, OpenAI, Anthropic, Google Gemini</td>
              </tr>
              <tr>
                <td>CRM</td>
                <td>HubSpot, Salesforce</td>
              </tr>
              <tr>
                <td>Messaging and notifications</td>
                <td>Twilio, Slack, Microsoft Teams</td>
              </tr>
              <tr>
                <td>Scheduling</td>
                <td>Calendly, Cal.com</td>
              </tr>
              <tr>
                <td>Payments</td>
                <td>Stripe</td>
              </tr>
            </tbody>
          </table>
        </TableWrap>
        <p>
          A current list of the sub-processors we engage is available on request from{' '}
          <Pending>privacy address</Pending>.
        </p>
      </LegalSectionBlock>

      <LegalSectionBlock id="cookies" num={8} title="Cookies and tracking">
        <h3>On this website</h3>
        <p>
          We use cookies and equivalent browser storage that are necessary to run the site and the
          application — keeping you signed in, remembering your session, and holding interface
          preferences such as a collapsed sidebar. These are required for the service to function.
        </p>
        <h3>Tracking inside customer outreach</h3>
        <p>
          The platform can add an open-tracking pixel and click-tracking redirects to emails a
          customer sends, and offers a script a customer can install on their own website to record
          visits. Where these are used, <strong>the customer is the controller</strong> of the
          resulting data and is responsible for disclosing it in their own privacy notice and for
          obtaining any consent their jurisdiction requires. Customers can disable tracking and can
          route it through their own domain.
        </p>
      </LegalSectionBlock>

      <LegalSectionBlock id="transfers" num={9} title="International transfers">
        <p>
          We and the providers described above may process data in countries other than your own,
          including outside the European Economic Area and the United Kingdom. Where personal data
          is transferred internationally, we rely on an appropriate safeguard such as an adequacy
          decision or standard contractual clauses. The governing jurisdiction for our own
          processing is <Pending>jurisdiction</Pending>.
        </p>
      </LegalSectionBlock>

      <LegalSectionBlock id="retention" num={10} title="How long we keep data">
        <TableWrap>
          <table>
            <thead>
              <tr>
                <th>Data</th>
                <th>Retention</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>Workspace content, including prospect data</td>
                <td>For as long as the customer keeps it, and until they delete it or close the account</td>
              </tr>
              <tr>
                <td>Account data</td>
                <td>For the life of the account, then deleted after the wind-down period in our Terms</td>
              </tr>
              <tr>
                <td>Unverified sign-ups</td>
                <td>Removed automatically after 72 hours</td>
              </tr>
              <tr>
                <td>Backups</td>
                <td>Taken daily and rotated on a schedule; deletions propagate as backups age out</td>
              </tr>
              <tr>
                <td>Suppression and unsubscribe records</td>
                <td>Kept for as long as needed to keep honouring the opt-out — deleting them would risk contacting the person again</td>
              </tr>
              <tr>
                <td>Billing and tax records</td>
                <td>As required by law</td>
              </tr>
              <tr>
                <td>Security and sign-in logs</td>
                <td>Retained for a limited period for security and troubleshooting</td>
              </tr>
            </tbody>
          </table>
        </TableWrap>
      </LegalSectionBlock>

      <LegalSectionBlock id="security" num={11} title="How we protect data">
        <ul>
          <li>Passwords are stored using a modern memory-hard hashing algorithm and are never recoverable.</li>
          <li>Provider credentials are encrypted at rest and are never displayed back after saving.</li>
          <li>Traffic is served over HTTPS with strict transport security and a content security policy.</li>
          <li>Every workspace is isolated, and every query is scoped to the workspace of the person making it.</li>
          <li>Role-based permissions control what each user can see and do.</li>
          <li>Sign-in, configuration changes and administrative actions are recorded in an audit trail.</li>
          <li>Sensitive endpoints are rate-limited, and accounts lock after repeated failed sign-ins.</li>
          <li>Data is backed up daily.</li>
        </ul>
        <p>
          No system is perfectly secure. If we become aware of a breach affecting personal data, we
          will notify affected customers and the relevant authorities as the law requires.
        </p>
      </LegalSectionBlock>

      <LegalSectionBlock id="rights" num={12} title="Your rights as a customer">
        <p>
          Depending on where you live, you may have the right to access the personal data we hold
          about you, correct it, delete it, restrict or object to how we use it, receive it in a
          portable form, and complain to your data protection authority. You can exercise most of
          these directly in the product, or by contacting us.
        </p>
        <p>
          If your request concerns data in a customer’s workspace rather than your own account, see
          the next section — we will route it to the customer responsible.
        </p>
      </LegalSectionBlock>

      <LegalSectionBlock id="recipients" num={13} title="If you received an email sent through NeuraLeads">
        <p>
          NeuraLeads is a tool. We did not choose to contact you and we are not the sender. The
          business whose name is on the message decided to contact you, wrote it, and is the
          controller of your data. That said, here is exactly what you can do.
        </p>
        <ul>
          <li>
            <strong>To stop the emails:</strong> use the unsubscribe link in the message. It is
            honoured immediately and permanently, and the address is added to a suppression list so
            further campaigns cannot reach it. Replying to say you are not interested also stops the
            sequence.
          </li>
          <li>
            <strong>To ask what data is held about you, or to have it erased:</strong> contact the
            sender directly — they control the data and can action it. The platform gives them
            one-click tooling to export or erase everything held about an address.
          </li>
          <li>
            <strong>If the sender does not respond:</strong> contact us at{' '}
            <Pending>privacy address</Pending> with a copy of the message. We will identify the
            customer responsible and require them to act.
          </li>
          <li>
            <strong>To report abuse of the platform:</strong> email{' '}
            <Pending>privacy address</Pending>. Sending unlawful or unsolicited mail breaches our{' '}
            <Link href="/terms">Terms of Service</Link>, and we suspend accounts that do it.
          </li>
        </ul>
        <p>
          You can also complain to your local data protection authority. Erasing your details does
          not remove your address from the suppression list, because that record is what prevents
          you from being contacted again.
        </p>
      </LegalSectionBlock>

      <LegalSectionBlock id="children" num={14} title="Children">
        <p>
          The service is a business tool and is not directed at children. We do not knowingly
          collect personal data from anyone under 16. If you believe a child’s data has reached the
          service, contact us and we will remove it.
        </p>
      </LegalSectionBlock>

      <LegalSectionBlock id="changes" num={15} title="Changes to this policy">
        <p>
          We may update this policy as the product and the law change. The effective date at the top
          of this page always reflects the current version. If a change materially affects how we
          handle personal data, we will tell account holders before it takes effect.
        </p>
      </LegalSectionBlock>

      <LegalSectionBlock id="contact" num={16} title="Contacting us">
        <p>
          For privacy questions, data-subject requests, sub-processor lists or a copy of our data
          processing agreement, contact <Pending>privacy address</Pending>, or write to{' '}
          <Pending>registered address</Pending>. General enquiries are answered through the{' '}
          <Link href="/contact">contact page</Link>.
        </p>
      </LegalSectionBlock>
    </LegalShell>
  )
}
