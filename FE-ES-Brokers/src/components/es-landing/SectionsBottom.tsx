import { useLayoutEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";
import {
  Accordion,
  AccordionItem,
  Button,
  CountUp,
  Eyebrow,
  IconLabelRow,
  Reveal,
  Section,
  Standout,
  TextLink,
  useInView,
} from "./primitives";
import {
  IconCheck,
  IconClock,
  IconDocument,
  IconLayers,
  IconPersonCheck,
  IconRankedBars,
  IconRefresh,
  IconSearch,
  IconShield,
} from "./icons";
import { DiagramFlow } from "./Diagram";

/* ------------------------ PLACEMENT BAND ------------------------ */

const WORKFLOWS = [
  ["01 Submission Market Matching", "Read, extract and rank every submission against your carrier panel's appetite."],
  ["02 Submission Package Assembly", "Assemble a carrier-specific package from your market selection."],
  ["03 Retail Agent Communication", "Draft status updates, missing-information requests, no-market notices and quote summaries."],
  ["04 Quote Comparison & Recommendation", "Normalise carrier terms, classify subjectivity materiality, recommend."],
  ["05 Binder & Policy Issuance Coordination", "Draft the bind request, track subjectivity clearance, and reconcile the issued policy against what was agreed."],
  ["06 Endorsement & Mid-Term Change Processing", "Classify change requests by materiality, recheck appetite, and reconcile multi-part requests item by item."],
  ["07 Renewal Remarketing", "Detect exposure and loss changes plus incumbent responsiveness, produce a graduated remarket recommendation."],
] as const;

export function PlacementBand() {
  const [open, setOpen] = useState(false);
  return (
    <Section id="placement" tone="gray">
      <Reveal>
        <Eyebrow>The full placement record</Eyebrow>
        <h3 className="type-h3 mt-4 text-[26px] leading-[34px]">
          The diligent search file nobody wants to assemble.
        </h3>
        <div className="type-body-l mt-6 max-w-[65ch] space-y-6">
          <p>
            Every surplus lines placement needs one, in the form the filing state requires,
            with declination evidence that holds up. It recurs on every account, the
            requirements differ state by state, and the person assembling it is usually
            reconstructing carrier responses from an inbox weeks after the fact.
          </p>
          <p>
            Coverline builds it from evidence it already holds. Every carrier your broker
            approached, every declination and the reason given, every date — already logged
            against the placement record as it happened, not reconstructed afterwards.
          </p>
          <p>
            Coverline does not make a legal determination that a diligent search has been
            satisfied. That judgment stays with your licensed broker, as it must. What
            Coverline does is make sure the evidence is there when your broker makes it.
          </p>
        </div>
      </Reveal>

      <div className="mt-8">
        <button
          type="button"
          aria-expanded={open}
          onClick={() => setOpen((o) => !o)}
          className="min-h-[44px] text-[15px] font-medium text-blue-500 underline-offset-4 hover:underline"
        >
          See the full placement lifecycle →
        </button>
      </div>

      <div
        className="grid transition-all duration-[250ms] ease-[var(--ease-standard)]"
        style={{ gridTemplateRows: open ? "1fr" : "0fr", opacity: open ? 1 : 0 }}
      >
        <div className="overflow-hidden">
          <div className="pt-10">
            <p className="type-h3">Ten connected workflows on one placement record. All live.</p>
            {open ? (
              <div className="mt-8 grid gap-10 lg:grid-cols-2">
                <DiagramFlow
                  nodes={WORKFLOWS.map(([t, d]) => ({
                    label: (
                      <span>
                        <span className="font-semibold text-navy-900">{t}</span> — {d}
                      </span>
                    ),
                  }))}
                />
                <div className="self-end rounded-[10px] border border-hairline bg-background p-8 shadow-tier1">
                  <p className="type-eyebrow">Running underneath all of it</p>
                  <div className="mt-5 space-y-4">
                    <IconLabelRow icon={IconDocument} title="08 Diligent Search & Compliance Documentation" />
                    <IconLabelRow icon={IconRefresh} title="09 Carrier Appetite Intelligence" />
                    <IconLabelRow icon={IconRankedBars} title="10 Pipeline & Carrier Performance Reporting" />
                  </div>
                </div>
              </div>
            ) : null}
            <p className="type-body mt-8 max-w-[65ch]">
              One placement record. Every step connected. Your data and decisions compound
              instead of living in five different tools.
            </p>
          </div>
        </div>
      </div>
    </Section>
  );
}

/* --------------------------- 06 TRIAL --------------------------- */

const TRIAL_STEPS = [
  [IconDocument, "01 Forward a real retail submission", "However it arrived. No reformatting, no portal, no change to what your agents send you."],
  [IconLayers, "02 Send us your carrier appetite guides", "Carrier PDFs, an internal spreadsheet, a broker's notes — whatever you have. Messy is fine."],
  [IconRankedBars, "03 We build your panel and walk you through it", "15–25 carrier profiles, built before your session, not left for you to configure. You review it and change anything you disagree with."],
  [IconRefresh, "04 Coverline reads, ranks and flags what's missing per carrier", "On your own submission, against your own panel."],
  [IconSearch, "05 You compare the result against your own placement", "Where did Coverline reach the same markets you did? Where did it differ — and was it wrong, or did it catch something? The exceptions are the most valuable output of the trial, in both directions."],
] as const;

const TIMELINE = [
  ["Day 1", "You forward a submission and send your appetite guides. That is everything we need."],
  ["Days 2–4", "Our team builds your carrier panel from your guides and your last 12 months of placements."],
  ["Day 5", "A 20-minute handover session. We walk you through your panel, you correct what you disagree with, and we run your submission live on the call."],
] as const;

const INCLUDED = [
  "14 days, starting the day your panel goes live — not the day you sign up",
  "Up to 25 of your own submissions — these count against nothing",
  "All ten placement workflows, no feature gating",
  "Carrier panel built by our team",
  "Full ranked market plans with citations",
  "Draft retail agent communications",
  "Data deleted on request, with a certificate",
];

const NOT_REQUIRED = [
  "No credit card",
  "No contract or commitment",
  "No agency management system integration",
  "No engineering time from your side",
  "No change to how your retail agents submit",
];

function Timeline() {
  const { ref, inView } = useInView<HTMLDivElement>(0.3);
  return (
    <div ref={ref} className="relative mt-16">
      <div className="absolute top-[11px] right-0 left-0 hidden h-px bg-hairline-strong lg:block">
        <div
          className="h-px origin-left bg-blue-500 transition-transform duration-500 ease-[var(--ease-standard)]"
          style={{ transform: `scaleX(${inView ? 1 : 0})` }}
        />
      </div>
      <div className="grid gap-10 lg:grid-cols-3 lg:gap-8">
        {TIMELINE.map(([day, body], i) => (
          <div key={day} className="relative">
            <IconClock
              size={22}
              className={cn(
                "relative z-10 bg-gray-100 text-navy-900 transition-all duration-300 ease-[var(--ease-standard)]",
                inView ? "scale-100 opacity-100" : "scale-75 opacity-0",
              )}
              style={{ transitionDelay: `${i * 180}ms` }}
            />
            <p className="mt-4 text-[16px] font-semibold text-navy-900">{day}</p>
            <p className="type-body mt-2 max-w-[42ch]">{body}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

export function Trial() {
  return (
    <Section id="trial" tone="gray">
      <Reveal>
        <Eyebrow>05 / The trial</Eyebrow>
        <h2 className="type-h2 mt-4">Run a submission you've already placed.</h2>
        <p className="type-body-l mt-6 max-w-[65ch]">
          The fastest way to evaluate Coverline is to give it an account you know the
          answer to. Run it, and compare Coverline's ranked markets against where it
          actually bound — and where it didn't.
        </p>
      </Reveal>

      <div className="mt-14 grid gap-8 lg:grid-cols-2">
        {TRIAL_STEPS.map(([Icon, title, body], i) => (
          <Reveal key={title} delay={i * 80}>
            <IconLabelRow icon={Icon} title={title}>
              {body}
            </IconLabelRow>
          </Reveal>
        ))}
      </div>

      <Timeline />

      <div className="mt-16 grid gap-12 lg:grid-cols-2">
        <div>
          <p className="type-eyebrow">Included</p>
          <div className="mt-6 space-y-4">
            {INCLUDED.map((t, i) => (
              <Reveal key={t} delay={i * 50}>
                <IconLabelRow icon={IconCheck} title={t} />
              </Reveal>
            ))}
          </div>
        </div>
        <div>
          <p className="type-eyebrow">Not required</p>
          <div className="mt-6 space-y-4">
            {NOT_REQUIRED.map((t, i) => (
              <Reveal key={t} delay={i * 50}>
                <IconLabelRow icon={IconCheck} title={t} />
              </Reveal>
            ))}
          </div>
        </div>
      </div>

      <Reveal>
        <Standout className="mt-16 max-w-[70ch]">
          <h3 className="type-h3">What this will cost your team.</h3>
          <p className="type-body">
            The handover session is 20 minutes. Comparing Coverline's rankings against
            placements you already made is roughly a couple of hours of your placement
            lead's time across the trial. We'd rather say so than have you discover it in
            week two.
          </p>
          <p className="type-body">
            The fourteen days are yours, not ours. The clock starts when your panel goes
            live, so setup time doesn't eat your evaluation.
          </p>
        </Standout>
      </Reveal>

      <Reveal>
        <p className="type-body mt-12 max-w-[65ch]">
          If you continue, your panel carries straight over — you don't start again. If you
          don't, we delete your data and issue a certificate of deletion. There is no
          auto-billing and no card on file to charge.
        </p>
        <div className="mt-8 flex flex-wrap items-center gap-4">
          <Button href="#final-cta">Run a real submission free →</Button>
          <Button href="#final-cta" variant="secondary">
            Book a demo
          </Button>
        </div>
      </Reveal>
    </Section>
  );
}

/* -------------------------- 07 PRICING -------------------------- */

const PLAN_POINTS = [
  "Unlimited read-only seats for accounting, compliance and leadership",
  "No per-submission charges. A fair-use allowance applies, set high enough that no customer has reached it",
  "Carrier panel configuration and onboarding included",
  "Full audit trail and export",
  "Live in 5 business days",
];

const SEATS = [
  ["3 seats", "$1,497/mo", "$14,970/yr"],
  ["6 seats", "$2,994/mo", "$29,940/yr"],
  ["10 seats", "$4,990/mo", "$49,900/yr"],
] as const;

const BUILT_FOR = [
  "Wholesale brokers and E&S brokers placing binding and brokerage business",
  "3–40 placement users",
  "150+ retail submissions a month across new business and renewals",
  "A carrier panel you maintain — not a generic market database",
  "Email, spreadsheets and an agency management system",
];

const INTEGRATIONS = [
  ["Applied Epic", "Read-only"],
  ["Vertafore AIM", "Read-only"],
  ["Nexsure", "Read-only"],
  ["ImageRight", "Read-only"],
  ["Novidea", "Read-only"],
  ["Salesforce / HubSpot", "Read-only"],
  ["Email — Microsoft 365, Google Workspace", "Reads submissions, drafts replies in your inbox"],
] as const;

export function Pricing() {
  /* SIGNATURE INTERACTIVE MOMENT #5 — Monthly / Annual toggle, defaults to Monthly. */
  const [annual, setAnnual] = useState(false);
  return (
    <Section id="pricing" tone="white">
      <Reveal>
        <Eyebrow>06 / Pricing &amp; fit</Eyebrow>
        <h2 className="type-h2 mt-4 max-w-[26ch]">
          Published pricing. You shouldn't need a call to find out what it costs.
        </h2>
      </Reveal>

      <div className="mt-14 grid gap-12 lg:grid-cols-2 lg:gap-16">
        <Reveal>
          <div className="rounded-[10px] border border-hairline bg-background p-8 shadow-tier1 lg:p-10">
            <div className="flex flex-wrap items-center gap-3">
              <div className="inline-flex rounded-[10px] bg-gray-100 p-1" role="group" aria-label="Billing period">
                {(
                  [
                    [false, "Monthly"],
                    [true, "Annual"],
                  ] as const
                ).map(([v, label]) => (
                  <button
                    key={label}
                    type="button"
                    aria-pressed={annual === v}
                    onClick={() => setAnnual(v)}
                    className={cn(
                      "min-h-[44px] rounded-[10px] px-4 text-[14px] font-semibold transition-all duration-200 ease-[var(--ease-standard)]",
                      annual === v ? "bg-background text-navy-900 shadow-tier1" : "text-navy-400",
                    )}
                  >
                    {label}
                  </button>
                ))}
              </div>
              <span
                className={cn(
                  "inline-flex items-center gap-1.5 rounded-[4px] bg-success-tint px-2 py-1 text-[11px] font-semibold tracking-wide text-success-text transition-all duration-200 ease-[var(--ease-standard)]",
                  annual ? "scale-100 opacity-100" : "pointer-events-none scale-95 opacity-0",
                )}
              >
                <span className="size-1 rounded-[1px] bg-current" aria-hidden />2 months free
              </span>
            </div>

            <p className="type-display mt-6">
              <CountUp
                key={annual ? "yr" : "mo"}
                value={annual ? 4990 : 499}
                prefix="$"
                duration={250}
                start
              />
            </p>
            <p className="type-body-s mt-2">
              per placement user / {annual ? "year" : "month"}
            </p>
            <p className="type-body mt-6 font-semibold text-navy-900">
              All ten placement workflows. No feature gating.
            </p>
            <div className="mt-6 space-y-4">
              {PLAN_POINTS.map((p) => (
                <IconLabelRow key={p} icon={IconCheck} title={p} />
              ))}
            </div>

            <div className="mt-8 border-t border-hairline">
              {SEATS.map(([seats, mo, yr], i) => (
                <Reveal key={seats} delay={i * 50}>
                  <div className="flex items-baseline justify-between gap-4 border-b border-hairline py-3">
                    <span className="text-[15px] font-medium text-navy-900">{seats}</span>
                    <span
                      key={annual ? "y" : "m"}
                      className="font-mono text-[15px] text-navy-900 tabular-nums transition-opacity duration-[250ms] ease-[var(--ease-standard)]"
                    >
                      {annual ? yr : mo}
                    </span>
                  </div>
                </Reveal>
              ))}
            </div>

            <div className="mt-8">
              <Button href="#final-cta">Run a real submission free →</Button>
            </div>
            <p className="type-body-s mt-5">
              No setup fee. No per-document fees. No minimum book size. No overage billing.
            </p>
          </div>
        </Reveal>


        <Reveal delay={80}>
          <p className="type-eyebrow">Built for</p>
          <div className="mt-6 space-y-4">
            {BUILT_FOR.map((b) => (
              <IconLabelRow key={b} icon={IconCheck} title={b} />
            ))}
          </div>

          <div className="mt-10 rounded-[10px] border border-hairline bg-background p-8 shadow-tier1">
            <p className="type-eyebrow">Classes we've built for</p>
            <p className="type-h3 mt-3">
              Property · Commercial auto and transportation · Construction
            </p>
          </div>
          <p className="type-body mt-6 max-w-[62ch] italic">
            Validated carrier appetite profiles and extraction accuracy across these three
            today. Other classes are in development. If you place something else, ask us —
            we'd rather tell you we're not ready than have you find out in week three.
          </p>
        </Reveal>
      </div>

      <Reveal>
        <div className="mt-16 grid gap-8 border-y border-hairline py-10 sm:grid-cols-3">
          <div>
            <p className="type-h2">
              <CountUp value={1.28} decimals={2} duration={700} />
            </p>
            <p className="type-body-s mt-2">FTE of placement capacity recovered</p>
          </div>
          <div>
            <p className="type-h2">
              <CountUp value={120000} prefix="$" duration={700} />
            </p>
            <p className="type-body-s mt-2">in recovered capacity</p>
          </div>
          <div>
            <p className="type-h2">
              <CountUp value={4} decimals={1} suffix="×" duration={700} />
            </p>
            <p className="type-body-s mt-2">return</p>
          </div>
        </div>
        <p className="type-body-s mt-4">
          At starting assumptions on a 2,400-submission book.{" "}
          <TextLink href="/roi">See the full model →</TextLink>
        </p>
      </Reveal>

      <div className="mt-14">
        <Accordion>
          <AccordionItem id="integrations" question="Integrations">
            <p>
              Start without integration. Coverline reads submissions from the inbox you
              already use. No IT project, no procurement cycle, no policy admin system
              required to get started.
            </p>
            <div className="mt-6 border-t border-hairline">
              {INTEGRATIONS.map(([name, mode]) => (
                <div
                  key={name}
                  className="flex flex-wrap items-baseline justify-between gap-4 border-b border-hairline py-3"
                >
                  <span className="text-[15px] font-medium text-navy-900">{name}</span>
                  <span className="type-body-s">{mode}</span>
                </div>
              ))}
            </div>
            <p className="mt-6">
              Coverline is read-only across every agency management system. It never writes
              to your book of record. Your team remains the only thing that updates your
              systems — which means Coverline clears IT review without a data-integrity
              assessment.
            </p>
          </AccordionItem>
          <AccordionItem id="fit" question="Where Coverline isn't the right fit">
            <div className="space-y-4">
              {[
                "Retail agencies placing business rather than brokering it into surplus markets",
                "Carriers and MGAs underwriting on their own paper — Coverline's MGA product is built for that, this one isn't",
                "Classes outside property, commercial auto and transportation, and construction, until we've built and validated the appetite profiles",
                "Teams without a defined carrier panel — Coverline ranks your markets; it can't tell you which markets to have",
              ].map((t) => (
                <IconLabelRow key={t} icon={IconShield} title={t} />
              ))}
            </div>
          </AccordionItem>
        </Accordion>
      </div>

      <Reveal>
        <p className="type-body mt-10 max-w-[70ch]">
          Multi-division and multi-branch segregation, SSO/SAML/SCIM, dedicated
          environment, custom SLA, sandbox for panel testing.{" "}
          <TextLink href="#final-cta">Book a demo →</TextLink>
        </p>
      </Reveal>
    </Section>
  );
}

/* -------------------------- 08 RESULTS -------------------------- */

const TILES = [
  ["$120M wholesale E&S broker", "US Southeast · Property, casualty and specialty placements"],
  ["$65M specialty wholesale broker", "US Northeast · Complex commercial and professional lines"],
  ["$18M regional E&S broker", "US Southwest · Construction, transportation and hard-to-place risks"],
] as const;

const QUOTES = [
  [
    "The biggest difference is that Coverline gives our placement team a clear view of what has happened to a submission and what needs to happen next. We can see the market responses, missing information and placement status without reconstructing the story across emails and spreadsheets.",
    "David Ross, CEO, Gallagher International (Wholesale Brokerage)",
  ],
  [
    "Declinations, market outreach and supporting evidence are captured as the placement happens, rather than being pieced together later when someone needs to prove what we did. That makes the workflow faster and the file much easier to defend.",
    "James Main, President, The Mainstay Insurance Group",
  ],
] as const;

export function Results() {
  /* SIGNATURE INTERACTIVE MOMENT #6 — tiles lift on hover; the $65M tile
     cross-highlights the case study card, since it is the same customer. */
  const [hovered, setHovered] = useState<string | null>(null);
  const caseLinked = hovered === "$65M specialty wholesale broker";
  return (

    <Section id="results" tone="gray050">
      <Reveal>
        <Eyebrow>07 / Results</Eyebrow>
        <h2 className="type-h2 mt-4">
          What <CountUp value={22} duration={400} /> placement teams are getting out of it.
        </h2>
      </Reveal>

      <div className="mt-12 grid gap-10 lg:grid-cols-2 lg:gap-16">
        <Reveal>
          <p className="type-body-s">
            Amwins · Burns &amp; Wilcox · RT Specialty · CRC · Burns &amp; Wilcox Canada
          </p>
          <p className="type-body mt-6 max-w-[52ch]">
            Coverline runs inside individual placement divisions and branches, not
            group-wide.
          </p>
        </Reveal>
        <Reveal delay={80}>
          <p className="type-body max-w-[62ch]">
            Your panel is yours alone. Appetite Intelligence learns only from your own
            placements. Your carrier profiles, declination history and placement outcomes
            are never aggregated with another brokerage's, never used to train models, and
            never visible outside your tenancy — including to other Coverline customers.
          </p>
        </Reveal>
      </div>

      <div className="mt-16 grid gap-8 lg:grid-cols-3">
        {TILES.map(([title, sub], i) => (
          <Reveal key={title} delay={i * 80}>
            <div
              onMouseEnter={() => setHovered(title)}
              onMouseLeave={() => setHovered(null)}
              className="rounded-[10px] border border-hairline bg-background p-6 shadow-tier1 transition-all duration-150 ease-[var(--ease-standard)] hover:-translate-y-0.5 hover:shadow-tier2"
            >
              <p className="type-h3">{title}</p>
              <p className="type-body-s mt-2">{sub}</p>
            </div>
          </Reveal>
        ))}
      </div>

      <Reveal>
        <a
          href="#case-studies"
          className={cn(
            "mt-16 block max-w-[760px] rounded-[10px] border bg-background p-8 shadow-tier1 transition-all duration-150 ease-[var(--ease-standard)] hover:-translate-y-0.5 hover:shadow-tier2 lg:p-10",
            caseLinked
              ? "-translate-y-0.5 border-blue-500 shadow-tier2"
              : "border-hairline",
          )}
        >

          <h3 className="type-h3 max-w-[30ch]">
            How a $65M specialty wholesale broker stopped reconstructing the placement file
          </h3>
          <p className="type-body mt-4 max-w-[65ch]">
            Declinations, market outreach and supporting evidence were pieced together
            weeks after the fact, whenever someone needed to prove what had been done.
            Here's what changed in the first 90 days, and what didn't.
          </p>
          <p className="type-body-s mt-4">Approved for production release.</p>
          <span className="mt-5 inline-block text-[15px] font-medium text-blue-500">
            Read the case study →
          </span>
        </a>
      </Reveal>

      <div className="mt-16 grid gap-8 lg:grid-cols-2">
        {QUOTES.map(([quote, who], i) => (
          <Reveal key={who} delay={i * 100}>
            <figure className="relative overflow-hidden rounded-[10px] border border-hairline bg-background p-8 shadow-tier1 transition-all duration-150 ease-[var(--ease-standard)] hover:-translate-y-0.5 hover:shadow-tier2 lg:p-10">
              <span
                aria-hidden
                className="pointer-events-none absolute -top-8 right-4 text-[160px] leading-none font-light text-hairline-strong"
              >
                &rdquo;
              </span>
              <blockquote className="type-body relative">{quote}</blockquote>
              <figcaption className="type-body-s relative mt-6">— {who}</figcaption>
            </figure>
          </Reveal>
        ))}
      </div>

      <div className="mt-20 grid gap-12 lg:grid-cols-2">
        <div>
          <p className="type-eyebrow">Insurance leadership</p>
          <div className="mt-6 space-y-6">
            <Reveal>
              <IconLabelRow icon={IconPersonCheck} title="John Goodloe — Strategic Insurance Advisor">
                Former Chief Underwriting Officer, Brokerage E&amp;S — Ategrity Specialty.
              </IconLabelRow>
            </Reveal>
            <Reveal delay={60}>
              <IconLabelRow icon={IconPersonCheck} title="Devin Claypool — Insurance Advisor">
                Chief Underwriting Officer — Eirion Risk Underwriters. Former Division
                President, Environmental — Intact Insurance Specialty Solutions.
              </IconLabelRow>
            </Reveal>
          </div>
        </div>
        <div>
          <p className="type-eyebrow">Engineering &amp; AI leadership</p>
          <div className="mt-6 space-y-6">
            <Reveal delay={120}>
              <IconLabelRow icon={IconLayers} title="Chintan Shah — Founder">
                Financial technology at Goldman Sachs. Georgia Tech. A decade building
                systems where auditability and compliance are the requirement, not a
                feature.
              </IconLabelRow>
            </Reveal>
            <Reveal delay={180}>
              <IconLabelRow icon={IconLayers}>
                Coverline is a product of SoluLab, a 250-person AI and engineering firm —
                which is why the platform launched with the full workflow suite rather than
                a single tool.{" "}
                <TextLink href="#top">LinkedIn →</TextLink>
              </IconLabelRow>
            </Reveal>
          </div>
        </div>
      </div>
    </Section>
  );
}

/* ------------------------- 09 FINAL CTA ------------------------- */

const REVERSAL = [
  "No credit card",
  "No commitment or contract",
  "Use a submission you've already placed",
  "Read-only across every system",
  "Broker approval required on every action",
  "Data deleted on request, with a certificate",
];

export function FinalCta() {
  return (
    <section id="final-cta" className="scroll-mt-24 bg-panel py-20 lg:py-32">
      <div className="mx-auto w-full max-w-[1280px] px-5 lg:px-16">
        <Reveal>
          <Eyebrow onDark>08 / Get started</Eyebrow>
          <h2 className="type-h2 mt-4 text-white">
            From submission to markets in three days.
          </h2>
        </Reveal>
        <Reveal delay={120}>
          <p className="type-body-l mt-6 max-w-[65ch] text-[color:color-mix(in_oklab,white_80%,transparent)]">
            Forward a submission you've already placed and send us your appetite guides.
            Within five business days you'll see your own carrier panel ranked against your
            own account — and you can compare the result against where it actually bound.
          </p>
        </Reveal>

        <div className="mt-10 grid gap-4 sm:grid-cols-2 lg:max-w-[900px] lg:grid-cols-3">
          {REVERSAL.map((t, i) => (
            <Reveal key={t} delay={240 + i * 50}>
              <span className="flex items-start gap-3 text-[14px] text-[color:color-mix(in_oklab,white_84%,transparent)]">
                <IconCheck size={18} className="mt-0.5 shrink-0 text-blue-500" />
                {t}
              </span>
            </Reveal>
          ))}
        </div>

        <Reveal delay={600}>
          <div className="mt-12 flex flex-wrap items-center gap-4">
            <Button variant="primaryBlue">Run a real submission free →</Button>
            <Button variant="secondaryDark">Book a demo</Button>
          </div>
        </Reveal>
      </div>
    </section>
  );
}

/* ----------------------------- FAQ ----------------------------- */

const FAQ_TABS = [
  {
    id: "market-matching",
    label: "Market matching",
    items: [
      ["How does Coverline know which carriers are a fit?", "Coverline maintains a structured appetite profile for every carrier on your panel — classes written and excluded, licensed states, limits and capacity, size bands, loss thresholds, referral triggers and submission requirements. Every ranking is those rules applied to the submission, not a model guessing at similarity."],
      ["What does a 94% appetite fit actually mean?", "It's a rules-based score measuring how closely the risk matches that carrier's configured appetite. It is not a probability of quote — Coverline tells you where the risk belongs, not what the carrier will do with it."],
      ["How are hard exclusions different from fit scoring?", "A hard exclusion is binary: the carrier does not write this risk, so it's removed and Coverline names the rule that fired. Scoring applies only to what remains."],
      ["Can I override a ranking?", "Always. Promote, demote or reinstate any carrier on any submission, with the reason logged — and those reasons feed Carrier Appetite Intelligence."],
      ["Can I configure my own panel?", "Completely. Add or remove carriers, edit any rule, set preferred and restricted markets. Changes take effect on the next submission without contacting support."],
    ],
  },
  {
    id: "documents",
    label: "Documents & accuracy",
    items: [
      ["What happens with a poor-quality scan or a handwritten supplemental?", "Coverline doesn't guess. Any field it can't read confidently is flagged for your team to correct in place — one click, no re-keying the rest, and corrections apply immediately to the ranking."],
      ["Which classes do you support?", "Property, commercial auto and transportation, and construction, with validated appetite profiles and extraction accuracy across all three. Others are in development — ask, and we'll tell you honestly."],
    ],
  },
  {
    id: "control",
    label: "Control, security & compliance",
    items: [
      ["Does the AI act on its own?", "No. Coverline reads, ranks and drafts. Your broker reviews, decides and sends. There is no autonomous mode."],
      ["Who is the broker of record?", "You are, without qualification. Coverline does not place business, does not bind, and does not replace broker judgment or your E&O obligations."],
      ["Does Coverline write back to my agency management system?", "No. Every integration is read-only. Your book of record is updated only by your team — which removes the IT approval hurdle entirely."],
      ["Is my data used to train models?", "No. Your submissions, panel, appetite configuration and placement outcomes are never used to train models, ours or our providers', and are never shared across customers."],
      ["Does Coverline support surplus lines compliance?", "Coverline determines the diligent search requirements applicable per state, captures declination evidence from your actual carrier responses, and generates the supporting documentation. It does not make a legal determination that a diligent search has been satisfied — that judgment stays with your licensed broker."],
      ["Can I export my data if I leave?", "Yes. Placement records, panel configuration, appetite profiles and audit logs export at any time in standard formats."],
    ],
  },
  {
    id: "setup",
    label: "Setup & commercial",
    items: [
      ["Do my retail agents need to use Coverline?", "No. It works from the submission they already send, in the format they already send it. Nothing changes for them."],
      ["How long is setup?", "Five business days to a live carrier panel. Send your appetite guides; we build the panel before your session."],
      ["What does it cost?", "$499 per placement user per month, all ten workflows, unlimited read-only seats, onboarding included. Two months free annually."],
      ["Is there a limit on how many submissions we can run?", "No per-submission and no per-document charges. A fair-use allowance applies and no customer has reached it. Processing never stops mid-month."],
      ["Who builds Coverline, and who am I contracting with?", "Coverline is a product of SoluLab, a 250-person AI and engineering firm, built with underwriting leadership from our insurance advisors. Your MSA and DPA are with SoluLab. It has a dedicated product team and roadmap — and the engineering base behind it is why a ten-workflow platform exists at this stage rather than a single tool."],
      ["Where is our data, and who can access it?", "Hosting is in the US, Canada or EU region you choose. Access is limited to named personnel under contract, and every location with access is named in our published sub-processor and personnel-access list, versioned with advance notice of changes."],
      ["How is Coverline different from other placement AI tools?", "Two structural differences. Published pricing and a self-serve trial mean you evaluate it on a submission you've already placed, rather than through an enterprise implementation cycle. And it runs on your carrier panel and your appetite rules — not a generic market database, and not similarity matching over someone else's data."],
    ],
  },
] as const;

export function Faq() {
  /* SIGNATURE INTERACTIVE MOMENT #7 — sliding tab indicator + live filter. */
  const [tab, setTab] = useState<string>(FAQ_TABS[0].id);
  const [query, setQuery] = useState("");
  const tabRefs = useRef(new Map<string, HTMLButtonElement>());
  const [indicator, setIndicator] = useState({ left: 0, width: 0 });

  useLayoutEffect(() => {
    const el = tabRefs.current.get(tab);
    if (el) setIndicator({ left: el.offsetLeft, width: el.offsetWidth });
  }, [tab]);

  const q = query.trim().toLowerCase();
  const current = FAQ_TABS.find((t) => t.id === tab) ?? FAQ_TABS[0];
  const results = q
    ? FAQ_TABS.flatMap((t) =>
        t.items
          .filter(([question]) => question.toLowerCase().includes(q))
          .map(([question, answer]) => [t.id, question, answer] as const),
      )
    : current.items.map(([question, answer]) => [current.id, question, answer] as const);

  return (
    <Section tone="white">
      <Reveal>
        <Eyebrow>Questions</Eyebrow>
      </Reveal>

      <div className="mt-8 max-w-[860px]">
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search questions"
          aria-label="Search questions"
          className="min-h-[52px] w-full rounded-[10px] border border-hairline-strong bg-background px-4 text-[15px] text-navy-900 transition-colors duration-150 placeholder:text-navy-400 focus:border-blue-500 focus:outline-none"
        />
      </div>

      <div
        className={cn(
          "relative mt-6 flex flex-wrap gap-2 transition-opacity duration-200",
          q && "pointer-events-none opacity-40",
        )}
        role="tablist"
        aria-label="FAQ categories"
      >
        <span
          aria-hidden
          className="absolute bottom-0 h-[2px] bg-blue-500 transition-all duration-200 ease-[var(--ease-standard)]"
          style={{ left: indicator.left, width: indicator.width }}
        />
        {FAQ_TABS.map((t) => (
          <button
            key={t.id}
            ref={(el) => {
              if (el) tabRefs.current.set(t.id, el);
              else tabRefs.current.delete(t.id);
            }}
            role="tab"
            aria-selected={tab === t.id}
            onClick={() => setTab(t.id)}
            className={cn(
              "min-h-[44px] rounded-[4px] px-4 text-[14px] font-semibold transition-colors duration-150",
              tab === t.id ? "text-navy-900" : "text-navy-400 hover:text-navy-700",
            )}
          >
            {t.label}
          </button>
        ))}
      </div>

      {q ? (
        <p className="type-body-s mt-4">
          {results.length} question{results.length === 1 ? "" : "s"} match “{query.trim()}”
          across all categories.
        </p>
      ) : null}

      <div
        key={q ? `search-${q}` : current.id}
        className="mt-8 max-w-[860px] duration-200 animate-in fade-in"
      >
        <Accordion>
          {results.map(([group, question, answer], i) => (
            <AccordionItem key={`${group}-${question}`} id={`${group}-${i}`} question={question}>
              {answer}
            </AccordionItem>
          ))}
        </Accordion>
      </div>
    </Section>
  );
}

