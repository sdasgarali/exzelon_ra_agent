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
  title: 'Terms of Service',
  description:
    'The agreement governing use of NeuraLeads — accounts, subscriptions and billing, acceptable use for outbound email, liability, and termination.',
  alternates: { canonical: '/terms' },
}

const SECTIONS: LegalSection[] = [
  { id: 'agreement', title: 'The agreement' },
  { id: 'accounts', title: 'Accounts and workspaces' },
  { id: 'plans', title: 'Plans, trials and billing' },
  { id: 'providers', title: 'Third-party providers' },
  { id: 'acceptable-use', title: 'Acceptable use' },
  { id: 'anti-spam', title: 'Email conduct' },
  { id: 'enforcement', title: 'Monitoring and suspension' },
  { id: 'your-data', title: 'Your data' },
  { id: 'our-ip', title: 'Our intellectual property' },
  { id: 'confidentiality', title: 'Confidentiality' },
  { id: 'availability', title: 'Availability and support' },
  { id: 'warranties', title: 'Warranties and disclaimers' },
  { id: 'liability', title: 'Limitation of liability' },
  { id: 'indemnity', title: 'Indemnity' },
  { id: 'termination', title: 'Termination' },
  { id: 'changes', title: 'Changes' },
  { id: 'general', title: 'General' },
]

const EFFECTIVE = '10 September 2026'

export default function TermsPage() {
  return (
    <LegalShell
      eyebrow="Legal"
      title="Terms of Service"
      standfirst="NeuraLeads sends email on your instruction, to people you choose. These terms set out what we provide, what you are responsible for, and the limits on both."
      effective={EFFECTIVE}
      updated={EFFECTIVE}
      sections={SECTIONS}
      closing={
        <p>
          Read alongside our <Link href="/privacy">Privacy Policy</Link>. If anything here conflicts
          with a signed agreement between us, the signed agreement governs.
        </p>
      }
    >
      <LegalSectionBlock id="agreement" num={1} title="The agreement">
        <p>
          These terms form an agreement between you and <Pending>legal entity name</Pending>{' '}
          (“NeuraLeads”, “we”, “us”), registered at <Pending>registered address</Pending>. They
          apply when you create an account, use the platform, or use this website.
        </p>
        <p>
          The service is provided for business use. By accepting these terms you confirm you are
          acting on behalf of a business, that you are at least 18, and that you have authority to
          bind that business. If you do not accept these terms, do not use the service.
        </p>
        <p>
          In these terms, <strong>“your data”</strong> means everything you put into or generate in
          your workspace, including contact records, campaigns and message content.{' '}
          <strong>“Prospect”</strong> means a person you contact using the service.
        </p>
      </LegalSectionBlock>

      <LegalSectionBlock id="accounts" num={2} title="Accounts and workspaces">
        <ul>
          <li>
            Your data lives in a workspace. Each workspace is isolated from every other customer.
          </li>
          <li>
            You are responsible for your account credentials and for everything done under your
            account. Tell us promptly if you suspect unauthorised access.
          </li>
          <li>
            Administrators in your workspace can create users, assign roles and see workspace data.
            Choose who holds those roles carefully — we act on the instructions of any user with
            sufficient permissions.
          </li>
          <li>
            You must verify your email address before the account becomes active. Unverified
            sign-ups are removed automatically after 72 hours.
          </li>
          <li>
            You must give accurate account and billing information and keep it current.
          </li>
        </ul>
      </LegalSectionBlock>

      <LegalSectionBlock id="plans" num={3} title="Plans, trials and billing">
        <ul>
          <li>
            <strong>Trial.</strong> Every plan includes a 14-day trial. If you do not subscribe by
            the end of it, the account stops sending.
          </li>
          <li>
            <strong>Flat fee.</strong> Subscriptions are charged per workspace, not per seat. Each plan
            includes one user login for the workspace.
          </li>
          <li>
            <strong>Renewal.</strong> Subscriptions renew automatically each period until cancelled.
          </li>
          <li>
            <strong>Annual billing.</strong> Where you choose annual billing, the discounted rate
            applies for the committed year and is charged in advance.
          </li>
          <li>
            <strong>Cancellation.</strong> You can cancel at any time. Your plan continues to the end
            of the paid period and is not renewed. We do not provide pro-rata refunds for unused
            time unless the law requires it.
          </li>
          <li>
            <strong>Upgrades and downgrades.</strong> Upgrading takes effect immediately. Downgrading
            takes effect at the end of the current period. Your data is not deleted when limits
            shrink, but you cannot create new records above the new limit until you are back under
            it.
          </li>
          <li>
            <strong>Plan limits.</strong> Limits on users, mailboxes, contacts, leads and campaigns
            are enforced when you create something, so you are told immediately rather than losing
            work silently.
          </li>
          <li>
            <strong>Taxes.</strong> Prices exclude taxes, which are added where applicable.
          </li>
          <li>
            <strong>Non-payment.</strong> If an invoice is unpaid we may issue reminders and,
            after notice, suspend the account until it is settled.
          </li>
          <li>
            <strong>Price changes.</strong> We may change prices with at least 30 days’ notice
            before your next renewal. If you do not accept a change, cancel before it takes effect.
          </li>
        </ul>
      </LegalSectionBlock>

      <LegalSectionBlock id="providers" num={4} title="Third-party providers">
        <p>
          The platform connects to providers for lead sourcing, contact discovery, email validation,
          AI, CRM, messaging and payments. For most of these you supply your own account and
          credentials.
        </p>
        <ul>
          <li>
            Your agreement with each provider is between you and them. You pay them directly at
            their rates, and their terms govern how they may use data you send.
          </li>
          <li>
            We are not responsible for a provider’s availability, accuracy, pricing, or how they use
            data under your agreement with them.
          </li>
          <li>
            You are responsible for the costs your usage generates with those providers. The
            platform meters and reports those costs, but the meter is a report, not a cap.
          </li>
          <li>
            You must keep your use of each provider within that provider’s own terms.
          </li>
        </ul>
      </LegalSectionBlock>

      <LegalSectionBlock id="acceptable-use" num={5} title="Acceptable use">
        <p>You must not use the service to:</p>
        <ul>
          <li>Break any law that applies to you or to the people you contact.</li>
          <li>
            Send unlawful, deceptive, harassing, defamatory, obscene or discriminatory content, or
            content that infringes someone else’s rights.
          </li>
          <li>Impersonate another person or organisation, or misrepresent your affiliation.</li>
          <li>Distribute malware, phishing content, or links intended to deceive.</li>
          <li>Promote unlawful products or run fraudulent schemes.</li>
          <li>
            Attempt to breach, probe or circumvent the security of the service, access another
            customer’s workspace, or interfere with the platform’s operation.
          </li>
          <li>
            Circumvent the platform’s safety mechanisms, including the send gate, cooldowns,
            per-company caps, domain throttles, suppression lists or rate limits.
          </li>
          <li>Resell or provide the service to third parties except as your plan permits.</li>
          <li>
            Reverse engineer the service or copy its features to build a competing product, except
            to the extent the law permits.
          </li>
        </ul>
      </LegalSectionBlock>

      <LegalSectionBlock id="anti-spam" num={6} title="Email conduct">
        <p>
          This is the part of these terms that matters most. The service sends email in your name,
          from your mailboxes, to people you choose. You are the sender in every sense that counts.
        </p>
        <p>You are responsible for ensuring that every message you send:</p>
        <ul>
          <li>
            Complies with the law that applies to you and to each recipient, including the CAN-SPAM
            Act, the GDPR and ePrivacy rules, CASL, and any equivalent local regime.
          </li>
          <li>
            Rests on a lawful basis for contacting that person. Deciding whether you have one is
            your responsibility, not ours.
          </li>
          <li>
            Identifies you accurately — a truthful sender name, a genuine reply-to address, a
            non-deceptive subject line, and a valid postal address where required.
          </li>
          <li>
            Contains a working, obvious way to opt out, and that opt-outs are honoured promptly. The
            platform honours them immediately and permanently.
          </li>
          <li>
            Goes to business contacts in a professional capacity. You must not use the service to
            market to consumers at personal addresses.
          </li>
        </ul>
        <p>You must not:</p>
        <ul>
          <li>
            Upload or send to purchased, rented, scraped or otherwise illegitimately obtained
            consumer lists.
          </li>
          <li>Contact anyone who has opted out, or remove someone from a suppression list in order to contact them again.</li>
          <li>Use mailboxes or domains you are not authorised to send from.</li>
          <li>Create accounts or domains to evade a suspension, a filter or a complaint history.</li>
        </ul>
        <Note label="Why we are strict about this">
          <p>
            Deliverability is a shared resource. One customer sending unlawful or unwanted mail
            damages the reputation of the infrastructure everyone relies on. The platform enforces
            these limits automatically, and these terms back that enforcement.
          </p>
        </Note>
      </LegalSectionBlock>

      <LegalSectionBlock id="enforcement" num={7} title="Monitoring and suspension">
        <p>
          We do not review the content of your campaigns as a matter of course. We do monitor
          operational signals — bounce rates, spam-complaint rates, blacklist activity and abuse
          reports — because they affect the service as a whole.
        </p>
        <p>We may suspend sending, or the account, where:</p>
        <ul>
          <li>Bounce or complaint rates exceed the thresholds applied by the platform.</li>
          <li>We receive credible reports of unlawful or unsolicited mail.</li>
          <li>An account is compromised, or is being used to evade a previous suspension.</li>
          <li>Payment is overdue after notice.</li>
          <li>Continuing would expose us or other customers to legal or reputational harm.</li>
        </ul>
        <p>
          Where practical we will tell you first and give you a chance to fix the problem. Where the
          risk is immediate, we may act first and explain afterwards.
        </p>
      </LegalSectionBlock>

      <LegalSectionBlock id="your-data" num={8} title="Your data">
        <ul>
          <li>
            <strong>You own your data.</strong> We claim no ownership of the contacts, content or
            records in your workspace.
          </li>
          <li>
            You grant us a limited licence to host, process, transmit and back up your data purely
            so we can provide the service to you.
          </li>
          <li>
            Where your data includes personal data about prospects, you are the controller and we
            are your processor. Our <Link href="/privacy">Privacy Policy</Link> explains the split,
            and a data processing agreement is available on request.
          </li>
          <li>
            You are responsible for having the right to put that data into the service, and for
            responding to requests from the people it concerns. The platform provides export and
            erasure tooling to help you do so.
          </li>
          <li>
            You can export your data at any time. We back up workspace data daily, but you remain
            responsible for keeping your own copies of anything you cannot afford to lose.
          </li>
        </ul>
      </LegalSectionBlock>

      <LegalSectionBlock id="our-ip" num={9} title="Our intellectual property">
        <p>
          The platform, the website, and everything we provide with them — software, design,
          documentation and branding — remain ours. You get a non-exclusive, non-transferable right
          to use the service during your subscription, and nothing more is granted by implication.
        </p>
        <p>
          If you send us feedback or suggestions, we may use them without obligation or payment to
          you.
        </p>
      </LegalSectionBlock>

      <LegalSectionBlock id="confidentiality" num={10} title="Confidentiality">
        <p>
          Each party may receive information the other treats as confidential. Each will protect the
          other’s confidential information with at least reasonable care, use it only to perform
          this agreement, and not disclose it except to people who need it and are under similar
          obligations. This does not cover information that is public, independently developed, or
          required to be disclosed by law.
        </p>
      </LegalSectionBlock>

      <LegalSectionBlock id="availability" num={11} title="Availability and support">
        <p>
          We aim to keep the service available continuously, but we do not guarantee uninterrupted
          operation. We may carry out maintenance, and will try to schedule disruptive work outside
          peak hours.
        </p>
        <TableWrap>
          <table>
            <thead>
              <tr>
                <th>Plan</th>
                <th>Support</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>Free</td>
                <td>Email support</td>
              </tr>
              <tr>
                <td>Pro</td>
                <td>Email support</td>
              </tr>
              <tr>
                <td>Max</td>
                <td>Priority support with an SLA</td>
              </tr>
              <tr>
                <td>Custom</td>
                <td>Named account manager and priority response</td>
              </tr>
            </tbody>
          </table>
        </TableWrap>
        <p>
          A contractual uptime commitment is available only where it is set out in a signed
          agreement.
        </p>
      </LegalSectionBlock>

      <LegalSectionBlock id="warranties" num={12} title="Warranties and disclaimers">
        <p>
          We provide the service with reasonable skill and care. Beyond that, and to the extent the
          law allows, the service is provided “as is” and we disclaim all other warranties, express
          or implied, including fitness for a particular purpose and non-infringement.
        </p>
        <p>In particular, we do not warrant that:</p>
        <ul>
          <li>
            Your messages will be delivered, will reach the inbox rather than a spam folder, or will
            avoid filtering or blocking by any mail provider.
          </li>
          <li>
            You will achieve any particular open rate, reply rate, meeting count, pipeline or
            revenue.
          </li>
          <li>
            Data obtained through third-party providers is accurate, complete or current. Contact
            data decays, and validation reduces but does not eliminate bounces.
          </li>
          <li>
            AI-generated content is accurate or suitable. You are responsible for reviewing what you
            send.
          </li>
          <li>The service will be uninterrupted or error-free.</li>
        </ul>
        <p>
          Sending reputation depends on your domains, your content and your recipients. The platform
          gives you tools to protect it; it cannot guarantee the outcome.
        </p>
      </LegalSectionBlock>

      <LegalSectionBlock id="liability" num={13} title="Limitation of liability">
        <p>
          To the extent the law allows, neither party is liable for indirect or consequential loss,
          nor for loss of profits, revenue, goodwill, business opportunity, anticipated savings or
          data.
        </p>
        <p>
          Our total aggregate liability arising out of or relating to this agreement is limited to
          the amounts you paid us for the service in the 12 months before the event giving rise to
          the claim.
        </p>
        <p>
          Nothing in these terms limits liability that cannot lawfully be limited, including for
          death or personal injury caused by negligence, or for fraud.
        </p>
      </LegalSectionBlock>

      <LegalSectionBlock id="indemnity" num={14} title="Indemnity">
        <p>
          You will defend and indemnify us against claims, damages, penalties and reasonable costs
          arising from:
        </p>
        <ul>
          <li>The content of messages you send and your choice of who to send them to.</li>
          <li>Your breach of the acceptable use or email conduct sections above.</li>
          <li>
            A regulatory action or complaint concerning personal data you put into the service, or
            your basis for contacting someone.
          </li>
          <li>Your infringement of a third party’s rights.</li>
        </ul>
        <p>
          We supply the instrument. You decide who to contact and what to say, and that decision
          carries its own responsibility.
        </p>
      </LegalSectionBlock>

      <LegalSectionBlock id="termination" num={15} title="Termination">
        <ul>
          <li>You may cancel at any time, effective at the end of your paid period.</li>
          <li>
            We may terminate for material breach that is not cured within 14 days of notice, or
            immediately where the breach is incapable of cure or the law requires it.
          </li>
          <li>
            After termination you will have 30 days to export your data. After that we delete it,
            and copies age out of backups on the usual rotation.
          </li>
          <li>
            Suppression and unsubscribe records may be retained beyond that, because deleting them
            would risk contacting people who have opted out.
          </li>
          <li>
            Sections on your data, our intellectual property, confidentiality, disclaimers,
            liability, indemnity and general terms survive termination.
          </li>
        </ul>
      </LegalSectionBlock>

      <LegalSectionBlock id="changes" num={16} title="Changes">
        <p>
          We may change the service, and we may update these terms. For material changes to these
          terms we will give reasonable notice before they take effect. Continuing to use the
          service after that means you accept the updated terms. If you do not, cancel before they
          take effect.
        </p>
      </LegalSectionBlock>

      <LegalSectionBlock id="general" num={17} title="General">
        <ul>
          <li>
            <strong>Governing law.</strong> These terms are governed by the laws of{' '}
            <Pending>jurisdiction</Pending>, and the courts of{' '}
            <Pending>jurisdiction</Pending> have exclusive jurisdiction over disputes.
          </li>
          <li>
            <strong>Entire agreement.</strong> These terms and the Privacy Policy are the whole
            agreement between us on this subject and replace earlier discussions.
          </li>
          <li>
            <strong>Severability.</strong> If a provision is unenforceable, the rest continues in
            force.
          </li>
          <li>
            <strong>No waiver.</strong> Not enforcing a right on one occasion does not waive it.
          </li>
          <li>
            <strong>Assignment.</strong> You may not assign this agreement without our consent. We
            may assign it as part of a merger, acquisition or sale of assets.
          </li>
          <li>
            <strong>Force majeure.</strong> Neither party is liable for delay caused by events
            beyond its reasonable control.
          </li>
          <li>
            <strong>Notices.</strong> We will send notices to your account email. You can reach us
            at <Pending>support address</Pending>.
          </li>
        </ul>
      </LegalSectionBlock>
    </LegalShell>
  )
}
