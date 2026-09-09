import Link from 'next/link'
import PipelineDiagram from './PipelineDiagram'

/**
 * Hero — drenched in the brand indigo (#4B4CE3), flat, no gradient.
 *
 * The composition is asymmetric on purpose: argument on the left, evidence on
 * the right. The evidence is the actual pipeline drawn to scale, which is the
 * one thing on this page a competitor can't copy without building the gate.
 *
 * The transparent navbar sits on this drench, which is why the hero owns the
 * top padding rather than the layout.
 */
export default function Hero() {
  return (
    <section className="relative overflow-hidden bg-brand-600">
      {/* Fine grid — a drafting surface, not a glow. Masked so it fades out. */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 opacity-[0.07]"
        style={{
          backgroundImage:
            'linear-gradient(to right, #fff 1px, transparent 1px), linear-gradient(to bottom, #fff 1px, transparent 1px)',
          backgroundSize: '88px 88px',
          maskImage: 'radial-gradient(ellipse 80% 80% at 20% 30%, #000 20%, transparent 78%)',
          WebkitMaskImage:
            'radial-gradient(ellipse 80% 80% at 20% 30%, #000 20%, transparent 78%)',
        }}
      />

      <div className="relative mx-auto grid max-w-7xl grid-cols-1 gap-12 px-6 pb-16 pt-24 lg:grid-cols-[1fr_1fr] lg:items-center lg:gap-16 lg:pb-20 lg:pt-28">
        {/* ── Argument ── */}
        <div className="hero-rise">
          {/* max-width lives on the text elements, not the wrapper: a `ch` bound on
              the wrapper resolves against its own 16px font, not the headline's. */}
          <h1 className="max-w-[13ch] text-[clamp(2.125rem,3.9vw,3.125rem)] font-extrabold leading-[1.06] tracking-[-0.032em] text-white">
            Finding leads is easy.
            <br />
            Knowing what <em className="pr-[0.08em]">not</em> to send is the product.
          </h1>

          <p className="mt-6 max-w-[50ch] text-[16.5px] leading-relaxed text-white/80">
            NeuraLeads pulls from ten job boards, then spends the rest of its run deciding
            what never leaves your mailbox — three-layer dedup, a company-size gate, seven
            validation providers, and ten ordered checks at the door.
          </p>

          <div className="mt-10 flex flex-wrap items-center gap-3">
            <Link
              href="/signup"
              className="rounded-lg bg-white px-6 py-3.5 text-[15px] font-semibold text-brand-700 shadow-[0_1px_0_rgba(0,0,0,0.06)] transition-transform duration-200 ease-out hover:-translate-y-0.5 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-white"
            >
              Start free trial
            </Link>
            <Link
              href="#pipeline"
              className="rounded-lg border border-white/25 px-6 py-3.5 text-[15px] font-semibold text-white transition-colors duration-200 hover:border-white/50 hover:bg-white/5 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-white"
            >
              How the gate works
            </Link>
          </div>

          <p className="mt-6 text-[13px] text-white/75">
            Self-hosted or managed. No per-seat pricing.
          </p>
        </div>

        {/* ── Evidence ── */}
        <div
          className="hero-rise lg:pt-2"
          style={{ animationDelay: '120ms' }}
        >
          <div className="mb-5 flex items-baseline justify-between border-b border-white/15 pb-3">
            <h2 className="text-[14px] font-semibold tracking-tight text-white">
              A typical overnight run
            </h2>
            <span className="text-[12px] tabular-nums text-white/70">4,000 → 30</span>
          </div>
          <PipelineDiagram tone="brand" />
        </div>
      </div>
    </section>
  )
}
