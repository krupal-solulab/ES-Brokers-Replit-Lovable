import {
  Parallax,
  WordRise,
  Button,

  Container,
  CountUp,
  Eyebrow,
  IconLabelRow,
  LoadReveal,
  Reveal,
  Section,
  Standout,
  TextLink,
} from "./primitives";
import {
  IconArrow,
  IconCheck,
  IconDocument,
  IconLock,
  IconPersonCheck,
  IconRankedBars,
  IconRefresh,
  IconSearch,
  IconShield,
  IconShieldCheck,
} from "./icons";
import { MarketPlanComponent } from "./MarketPlan";
import { CitationLink } from "./CitationPanel";
import { ScrubCompare } from "./ScrubCompare";
import { TwoColumnCompare } from "./Diagram";


/* ------------------------------- HERO ------------------------------- */

export function Hero() {
  return (
    <div id="top" className="border-b border-hairline bg-gray-050 py-20 lg:py-28">
      <Container>
        <LoadReveal delay={0}>
          <Eyebrow>Built for wholesale &amp; E&amp;S brokers</Eyebrow>
        </LoadReveal>
        <h1 className="type-display mt-5 max-w-[860px] text-[34px] leading-[40px] sm:text-[42px] sm:leading-[48px] lg:text-[42px] lg:leading-[50px] xl:text-[46px] xl:leading-[56px]">
          <WordRise
            text="Know where every submission belongs."
            delay={140}
            className="lg:whitespace-nowrap"
          />
          <WordRise
            text="Before you send it."
            delay={480}
            weightClass="font-light"
            className="lg:whitespace-nowrap"
          />
        </h1>
        <div className="mt-12 grid items-start gap-12 lg:mt-14 lg:grid-cols-2 lg:gap-16">
          <div>
            <LoadReveal delay={720}>
              <p className="type-body-l max-w-[65ch]">

                Coverline reads the retail submission, checks it against your carrier
                panel's actual appetite, ranks the markets that will write it, and tells
                you what each carrier still needs — every figure cited to the document it
                came from. Your broker decides which markets get it.
              </p>
            </LoadReveal>
            <LoadReveal delay={860}>
              <div className="mt-8 flex flex-wrap items-center gap-4">
                <Button href="#final-cta">Run a real submission free →</Button>
                <Button href="#final-cta" variant="secondary">
                  Book a demo
                </Button>
              </div>
              <p className="type-body-s mt-4 max-w-[62ch]">
                Use a submission you've already placed · 25 submissions · No credit card ·
                Your carrier panel configured for you within 5 business days
              </p>
            </LoadReveal>

            <div className="mt-10 grid gap-6 border-t border-hairline pt-8 sm:grid-cols-2">
              <LoadReveal delay={1000}>
                <IconLabelRow icon={IconShield} title="Every hard exclusion names its rule">
                  No carrier removed without the rule that removed it
                </IconLabelRow>
              </LoadReveal>
              <LoadReveal delay={1060}>
                <IconLabelRow icon={IconPersonCheck} title="100% broker-approved actions">
                  Nothing reaches a carrier or a retail agent without explicit approval
                </IconLabelRow>
              </LoadReveal>
            </div>
          </div>

          <LoadReveal delay={1140}>
            <Parallax distance={44}>
              <MarketPlanComponent variant="compact" />
            </Parallax>
          </LoadReveal>
        </div>
      </Container>
    </div>
  );
}


/* --------------------------- 01 PROOF BAND --------------------------- */

const PROOF = [
  { value: 22, suffix: "", label: "Wholesale and E&S broker teams running Coverline in production" },
  { value: 6500, suffix: "+", label: "Submissions matched to date" },
  { value: 5, suffix: " business days", label: "Time to a live carrier panel" },
];

export function ProofBand() {
  return (
    <Section tone="white" hairline={false}>
      <Reveal>
        <Eyebrow>Already in production</Eyebrow>
      </Reveal>
      <div className="mt-8 grid gap-10 sm:grid-cols-3">
        {PROOF.map((s, i) => (
          <Reveal key={s.label} delay={i * 80}>
            <p className="type-display text-[44px] leading-[48px] lg:text-[56px] lg:leading-[60px]">
              <CountUp value={s.value} suffix={s.suffix} duration={700} />
            </p>
            <p className="type-body-s mt-3 max-w-[34ch]">{s.label}</p>
          </Reveal>
        ))}
      </div>

      <Reveal delay={120}>
        <p className="type-body-l mt-12 max-w-[65ch]">
          Wholesale and E&amp;S placement teams run their retail submissions through
          Coverline today. Not pilots — production placement.
        </p>
      </Reveal>

      <Reveal delay={160}>
        <div className="mt-10 border-t border-hairline pt-8">
          <p className="type-body-s">
            Customer proof: Amwins · Burns &amp; Wilcox · RT Specialty · CRC · Burns &amp;
            Wilcox Canada
          </p>
          <p className="type-body-s mt-3 max-w-[80ch]">
            Placement advisory: John Goodloe, former Chief Underwriting Officer, Brokerage
            E&amp;S — Ategrity Specialty · Devin Claypool, Chief Underwriting Officer —
            Eirion Risk Underwriters
          </p>
          <div className="mt-5">
            <TextLink href="#results">See the results →</TextLink>
          </div>
        </div>
      </Reveal>

      <Reveal delay={200}>
        <div className="mt-8 flex flex-wrap items-center gap-x-6 gap-y-3 border-y border-hairline py-5">
          {[
            [IconShieldCheck, "SOC 2 Type I certified"],
            [IconLock, "Read-only across every agency management system"],
            [IconShield, "Your data is never used to train models"],
            [IconPersonCheck, "Broker approval required on every action"],
          ].map(([Icon, text], i) => {
            const I = Icon as typeof IconShield;
            return (
              <span key={i} className="inline-flex items-center gap-2">
                <I size={18} className="text-navy-900" />
                <span className="text-[14px] text-navy-700">{text as string}</span>
              </span>
            );
          })}
          <TextLink href="/security">Security details →</TextLink>
        </div>
      </Reveal>
    </Section>
  );
}

/* ---------------------------- 02 PROBLEM ---------------------------- */

export function Problem() {
  return (
    <Section id="problem" tone="gray">
      <Reveal>
        <Eyebrow>01 / The problem</Eyebrow>
        <h2 className="type-h2 mt-4 max-w-[22ch]">
          Your best placement people spend their day on market research.
        </h2>
      </Reveal>
      <Reveal delay={60}>
        <div className="type-body-l mt-7 max-w-[65ch] space-y-6">
          <p>
            A submission lands. Someone opens fifteen documents. Then they open appetite
            guides, check exclusions, check state eligibility, check capacity, and try to
            remember which carrier tightened up on that class last quarter. They pick eight
            to twelve markets, send it, and three carriers come back asking for information
            that could have been requested on day one.
          </p>
          <p>Then the account renews and the whole thing happens again.</p>
        </div>
      </Reveal>

      <Reveal delay={120}>
        <div className="mt-12 max-w-[760px] rounded-[10px] border border-hairline bg-background p-8 shadow-tier1 lg:p-10">
          <p className="type-display">
            <CountUp value={10} /> days
          </p>
          <p className="type-body-l mt-4 max-w-[52ch]">
            from retail submission received to markets engaged. Most of that wasn't
            underwriting judgment. It was looking things up.
          </p>
        </div>
      </Reveal>

      <Reveal delay={200}>
        <p className="type-body-l mt-10 max-w-[65ch] font-semibold text-navy-900">
          Coverline exists so the bottleneck stops being how long it takes to look
          something up.
        </p>
        <div className="mt-8 flex flex-wrap items-center gap-6">
          <Button href="#final-cta">Run a real submission free →</Button>
          <TextLink href="#market-plan">Or see a sample market plan first →</TextLink>
        </div>
      </Reveal>
    </Section>
  );
}

/* -------------------------- 03 HOW IT WORKS -------------------------- */

const STEPS = [
  {
    n: "01",
    icon: IconDocument,
    title: "Read",
    body: "Monitors your submission inbox and reads applications, loss runs, financials, schedules and supplementals as they arrive. No portal for your retail agents to learn.",
  },
  {
    n: "02",
    icon: IconShield,
    title: "Eliminate",
    body: "Removes every carrier that cannot write the risk — class, territory, licensing, capacity, stated restriction — and names the rule that fired on each one.",
  },
  {
    n: "03",
    icon: IconRankedBars,
    title: "Rank",
    body: "Scores every remaining market against your configured appetite profile and shows the contributing factors behind each position.",
  },
  {
    n: "04",
    icon: IconPersonCheck,
    title: "Decide",
    body: "Your broker promotes, demotes, reinstates or overrides any carrier. Every override is logged with the reason captured.",
  },
];

export function HowItWorks() {
  return (
    <Section id="how-it-works" tone="white">
      <Reveal>
        <Eyebrow>02 / How it works</Eyebrow>
        <h2 className="type-h2 mt-4 max-w-[24ch]">
          Coverline does the research. Your broker picks the markets.
        </h2>
      </Reveal>

      <Reveal delay={80}>
        <Standout className="mt-8 max-w-[70ch]">
          <p className="type-body-l">
            Coverline never sends a submission to a carrier, emails a retail agent, or
            binds anything without explicit broker approval. It prepares the market plan.
            Your licensed broker decides, and remains the broker of record on every
            account.
          </p>
        </Standout>
      </Reveal>

      {/* 03a — scroll-scrubbed on desktop, swipeable on mobile */}
      <div className="mt-16">
        <ScrubCompare />
      </div>

      <Reveal>
        <p className="type-body mt-10 max-w-[65ch]">
          The ranked market plan takes minutes. The three days is everything after — your
          broker reviewing markets, packages going out, and the decisions that should stay
          with a person staying with a person.
        </p>
      </Reveal>

      {/* 03b */}
      <div className="relative mt-24">
        <span
          aria-hidden
          className="absolute top-0 bottom-0 left-[31px] w-px bg-hairline-strong lg:top-[52px] lg:right-16 lg:bottom-auto lg:left-16 lg:h-px lg:w-auto"
        />
        <div className="grid gap-10 lg:grid-cols-4 lg:gap-8">
          {STEPS.map((s, i) => (
            <Reveal key={s.n} delay={i * 80}>
              <div className="relative flex gap-5 lg:block">
                <span className="relative z-10 block bg-background text-[48px] leading-none font-light text-hairline-strong lg:mb-6 lg:text-[64px]">
                  {s.n}
                </span>
                <div className="lg:pr-6">
                  <div className="flex items-center gap-3">
                    <s.icon size={22} className="text-navy-900" />
                    <h3 className="type-h3">{s.title}</h3>
                  </div>
                  <p className="type-body mt-3">{s.body}</p>
                </div>
              </div>
            </Reveal>
          ))}
        </div>
      </div>

      {/* 03c */}
      <div className="mt-24 max-w-[900px]">
        <TwoColumnCompare
          left="Generic AI"
          right="Coverline"
          rows={[
            ["Summarises the submission", "Structures the risk, cited to source"],
            ["Generic market knowledge", "Your carrier panel"],
            ["Similarity matching", "Your appetite rules"],
            ["A one-off answer", "A placement record that persists"],
            ["No audit trail", "Every score, override and action logged"],
          ]}
        />
        <Reveal>
          <p className="type-body mt-8 max-w-[65ch] italic">
            Coverline is the operating layer around placement — not a chatbot sitting
            beside it.
          </p>
          <div className="mt-6">
            <TextLink href="#market-plan">Watch the 2-minute walkthrough →</TextLink>
          </div>
        </Reveal>
      </div>
    </Section>
  );
}

/* ------------------- 04 THE RANKED MARKET PLAN ------------------- */

const STATES = [
  {
    icon: IconArrow,
    title: "Hard exclusion",
    body: "The carrier does not write this risk. Class, territory, licensing, capacity or a stated restriction rules it out. Coverline removes it and names the rule that fired.",
  },
  {
    icon: IconSearch,
    title: "Conditional fit",
    body: "The carrier may write it with a referral, additional information, or a specific structure. Coverline flags exactly what stands between you and a quote.",
  },
  {
    icon: IconCheck,
    title: "Strong fit",
    body: "Class, territory, size, capacity and loss history align. Coverline scores it and shows the contributing factors.",
  },
];

export function MarketPlanSection() {
  return (
    <Section id="market-plan" tone="gray050">
      <Reveal>
        <Eyebrow>03 / The output</Eyebrow>
        <h2 className="type-h2 mt-4">One submission. Your best markets, ranked.</h2>
        <p className="type-body-l mt-6 max-w-[65ch]">
          This is what your placement team receives. Not a summary and not a shortlist
          someone assembled from memory — a ranked market plan with the rule behind every
          exclusion, the factors behind every score, and every extracted figure traceable
          to the document it came from.
        </p>
      </Reveal>

      <div className="mt-14">
        <MarketPlanComponent variant="full" />
      </div>

      <Reveal>
        <p className="type-body mt-12 max-w-[70ch]">
          Every arrow is a live link. Click any figure and the source document opens at the
          exact page and section it came from. Coverline separates what a document says
          from what a broker concludes. Extracted facts carry a citation. Derived figures
          show their arithmetic. Every carrier removed names the rule that removed it — so
          nothing disappears from your panel without a reason you can check.
        </p>
      </Reveal>

      <div className="mt-16 grid gap-10 lg:grid-cols-3">
        {STATES.map((s, i) => (
          <Reveal key={s.title} delay={i * 80}>
            <IconLabelRow icon={s.icon} title={s.title}>
              {s.body}
            </IconLabelRow>
          </Reveal>
        ))}
      </div>
      <Reveal>
        <p className="type-body mt-10 max-w-[65ch]">
          Hard exclusions are kept separate from scoring on purpose. A carrier that cannot
          write the risk should never appear as a low-scoring option your team wastes an
          afternoon on.
        </p>
        <div className="mt-8 flex flex-wrap items-center gap-6">
          <Button href="#final-cta">Run a real submission free →</Button>
          <span className="type-body-s">Run one you've already placed and compare.</span>
          <Button href="#final-cta" variant="resource">
            See a sample market plan
          </Button>
        </div>
      </Reveal>
    </Section>
  );
}

/* --------------------- 05 YOUR PANEL & EVIDENCE --------------------- */

const MAINTAINS = [
  ["Classes written", IconDocument],
  ["Classes excluded", IconShield],
  ["Licensed states", IconShieldCheck],
  ["Limits and capacity", IconRankedBars],
  ["TIV and revenue bands", IconRankedBars],
  ["Preferred risk characteristics", IconCheck],
  ["Loss thresholds", IconSearch],
  ["Referral triggers", IconRefresh],
  ["Submission requirements", IconDocument],
  ["Special restrictions", IconShield],
] as const;

const CONTROLS = [
  ["Add, remove and prioritise carriers", IconRankedBars],
  ["Edit any appetite rule", IconDocument],
  ["Set preferred and restricted markets", IconShield],
  ["Set minimum submission requirements", IconCheck],
  ["Override any ranking", IconPersonCheck],
  ["Record why you overrode it", IconRefresh],
] as const;

export function YourPanel() {
  return (
    <Section id="your-panel" tone="white">
      <Reveal>
        <Eyebrow>04 / Your panel</Eyebrow>
        <h2 className="type-h2 mt-4 max-w-[24ch]">
          Your panel. Their appetite. Your rules. Nothing you can't check.
        </h2>
        <p className="type-body-l mt-6 max-w-[65ch]">
          Two questions decide whether a placement team trusts a ranking: whose appetite
          produced it, and can the underlying figures be traced back to a document. Both
          have the same answer — yours, and yes.
        </p>
      </Reveal>

      <div className="mt-14 grid gap-12 lg:grid-cols-2 lg:gap-16">
        <div>
          <p className="type-eyebrow">What Coverline maintains per carrier</p>
          <div className="mt-6 grid gap-4 sm:grid-cols-2">
            {MAINTAINS.map(([label, Icon], i) => (
              <Reveal key={label} delay={i * 60}>
                <IconLabelRow icon={Icon} title={label} />
              </Reveal>
            ))}
          </div>
        </div>
        <div>
          <p className="type-eyebrow">What you control</p>
          <div className="mt-6 grid gap-4 sm:grid-cols-2">
            {CONTROLS.map(([label, Icon], i) => (
              <Reveal key={label} delay={i * 60}>
                <IconLabelRow icon={Icon} title={label} />
              </Reveal>
            ))}
          </div>
        </div>
      </div>

      <Reveal>
        <Standout className="mt-16 max-w-[70ch]">
          <h3 className="type-h3">When a carrier tightens on Tuesday, your panel changes on Tuesday.</h3>
          <p className="type-body">
            Your placement lead edits appetite rules directly. No ticket, no support queue,
            no waiting on a vendor sprint. Changes take effect on the next submission, and
            every change is versioned, attributed and timestamped.
          </p>
          <p className="type-body">
            We build your panel with you from your appetite guides and your last 12 months
            of placements. We hand over control so you're never dependent on us to run your
            own panel.
          </p>
        </Standout>
      </Reveal>

      <Reveal>
        <p className="type-body mt-12 max-w-[70ch]">
          Appetite fit is a rules-based score measuring how closely the risk matches that
          carrier's configured appetite — class, territory, size, capacity and loss
          history. It is not a probability of quote. Whether a carrier quotes depends on
          their underwriter, their capacity that week, and the market. Coverline tells you
          where the risk belongs, not what the carrier will do with it.
        </p>
      </Reveal>

      <CitationDemo />

      <Reveal>
        <Standout className="mt-16 max-w-[70ch]">
          <h3 className="type-h3">Where we're weakest, twice over.</h3>
          <p className="type-body">
            <strong className="font-semibold text-navy-900">Documents:</strong> handwritten
            and low-quality scanned loss runs from smaller carriers. Rather than produce a
            confident wrong number, Coverline flags these for your team to correct in
            place. We'd rather show you four flagged fields than silently populate one
            wrong loss ratio.
          </p>
          <p className="type-body">
            <strong className="font-semibold text-navy-900">Appetite:</strong> a carrier can
            tighten on a Tuesday and tell the market on a Friday. Your panel is only as
            current as what you and your account team put into it. That's why every
            override is logged, and why Carrier Appetite Intelligence aggregates your own
            declination reasons and quote patterns to surface evidenced shifts — but a
            profile no one has updated is a profile that will be wrong eventually.
          </p>
          <p className="type-body">
            Appetite Intelligence needs your own placement history to work from. It
            surfaces a shift when your evidence supports one, not on day one. Expect it to
            be quiet for the first few months. That's the design.
          </p>
        </Standout>
      </Reveal>

      <Reveal>
        <p className="type-body mt-12 max-w-[70ch]">
          Coverline's ranking draws only on the extracted, cited data and the appetite
          rules you configured. It does not use outside knowledge about the risk, the
          insured, or what a carrier "usually" does. If a claim can't be traced to a source
          document or a rule you set, it doesn't appear in the market plan.
        </p>
        <div className="mt-8">
          <Button href="#final-cta">Run a real submission free →</Button>
        </div>
      </Reveal>
    </Section>
  );
}

const CITES = [
  ["Loss ratio 68%", "Calculated · Loss Run p.1–2"],
  ["Revenue $9.2M", "Financials · p.3"],
  ["Scheduled equipment $7.4M", "Equipment schedule · p.1"],
  ["Power units 42", "ACORD 127 — Vehicle Schedule"],
] as const;

const THREE_STATE = [
  {
    icon: IconCheck,
    state: "Confirmed",
    when: "Found, source unambiguous",
    what: "Populated with a citation to page and section. One click to the original.",
  },
  {
    icon: IconSearch,
    state: "Needs review",
    when: "Found but low confidence, or two documents disagree",
    what: "Flagged amber, both sources shown side by side. Never silently resolved.",
  },
  {
    icon: IconArrow,
    state: "Not found",
    when: "Not present in the documents provided",
    what: "Left blank and added to the per-carrier missing-information list. Coverline does not infer, estimate, or guess a value it cannot cite.",
  },
];

function CitationDemo() {
  return (
    <div className="mt-16">
      <div className="grid gap-4 sm:grid-cols-2 lg:max-w-[860px]">
        {CITES.map(([value, source], i) => (
          <Reveal key={value} delay={i * 60}>
            <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 border-b border-hairline py-3">
              <span className="font-mono text-[14px] font-medium text-navy-900 tabular-nums">
                {value}
              </span>
              <CitationLink value={value} source={source} />
            </div>

          </Reveal>
        ))}
      </div>

      <div className="mt-12 border-t border-hairline lg:max-w-[980px]">
        {THREE_STATE.map((r, i) => (
          <Reveal key={r.state} delay={i * 60}>
            <div className="grid gap-2 border-b border-hairline py-5 lg:grid-cols-[200px_260px_1fr] lg:gap-8">
              <p className="flex items-center gap-2 text-[15px] font-semibold text-navy-900">
                <r.icon size={18} />
                {r.state}
              </p>
              <p className="type-body-s">{r.when}</p>
              <p className="type-body">{r.what}</p>
            </div>
          </Reveal>
        ))}
      </div>
    </div>
  );
}
