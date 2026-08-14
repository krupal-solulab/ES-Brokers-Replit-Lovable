import { useState, type ReactNode } from "react";
import { Link } from "@tanstack/react-router";
import { Menu, X, ArrowRight, FileText, ShieldCheck, ScrollText, Check } from "lucide-react";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { ThemeToggle } from "@/components/ThemeToggle";
import { Reveal } from "./Reveal";
import { AuthDialog } from "./AuthDialog";
import { useInView } from "@/hooks/use-in-view";
import { useCountUp } from "@/hooks/use-count-up";
import { useActiveSection } from "@/hooks/use-active-section";

const nav = [
  { label: "Product", href: "#how" },
  { label: "Workflows", href: "#workflows" },
  { label: "Why E&S brokers", href: "#why" },
  { label: "Security", href: "#security" },
];
const NAV_SECTION_IDS = nav.map((n) => n.href.slice(1));

function Wordmark({ className = "" }: { className?: string }) {
  return (
    <a href="#top" className={`inline-flex items-baseline gap-[2px] font-serif ${className}`}>
      <span className="text-[1.35rem] font-600 tracking-[-0.02em] text-foreground">Coverline</span>
      <span className="translate-y-[-0.15em] text-accent text-lg leading-none">.</span>
    </a>
  );
}

function DemoLinkButton({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <Button variant="brand" asChild className={`px-5 py-2.5 h-auto ${className}`}>
      <Link to="/demo">{children}</Link>
    </Button>
  );
}

function Eyebrow({ children, num }: { children: ReactNode; num?: string }) {
  return (
    <div className="label-eyebrow flex items-center gap-3">
      {num && <span className="font-mono text-accent">{num}</span>}
      <span>{children}</span>
    </div>
  );
}

function Nav({ onOpenAuth }: { onOpenAuth: (mode: "login" | "signup") => void }) {
  const [open, setOpen] = useState(false);
  const activeId = useActiveSection(NAV_SECTION_IDS);
  return (
    <header id="top" className="sticky top-0 z-40 rule-b bg-background/85 backdrop-blur">
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-5 md:px-8">
        <Wordmark />
        <nav className="hidden items-center gap-9 md:flex">
          {nav.map((n) => {
            const isActive = activeId === n.href.slice(1);
            return (
              <a
                key={n.href}
                href={n.href}
                aria-current={isActive ? "true" : undefined}
                className={`relative py-1 text-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring rounded-sm ${
                  isActive ? "text-foreground font-medium" : "text-ink-soft hover:text-foreground"
                }`}
              >
                {n.label}
                <span
                  className={`absolute -bottom-[1px] left-0 h-[1.5px] w-full bg-accent-2 transition-opacity ${
                    isActive ? "opacity-100" : "opacity-0"
                  }`}
                />
              </a>
            );
          })}
        </nav>
        <div className="hidden items-center gap-6 md:flex">
          <ThemeToggle />
          <button
            type="button"
            onClick={() => onOpenAuth("login")}
            className="cursor-pointer rounded-sm text-sm text-ink-soft transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
          >
            Log in
          </button>
          <DemoLinkButton>Book a demo</DemoLinkButton>
        </div>
        <div className="flex items-center gap-3 md:hidden">
          <ThemeToggle />
          <button
            className="cursor-pointer rounded-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
            aria-label="Toggle menu"
            aria-expanded={open}
            onClick={() => setOpen((v) => !v)}
          >
            {open ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </button>
        </div>
      </div>
      {open && (
        <div className="rule-t bg-background md:hidden">
          <div className="mx-auto flex max-w-7xl flex-col gap-1 px-5 py-4">
            {nav.map((n) => (
              <a
                key={n.href}
                href={n.href}
                onClick={() => setOpen(false)}
                className="rounded-sm py-2 text-sm text-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              >
                {n.label}
              </a>
            ))}
            <button
              type="button"
              onClick={() => {
                setOpen(false);
                onOpenAuth("login");
              }}
              className="cursor-pointer rounded-sm py-2 text-left text-sm text-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
            >
              Log in
            </button>
            <DemoLinkButton className="mt-2 w-full justify-center">Book a demo</DemoLinkButton>
          </div>
        </div>
      )}
    </header>
  );
}

function Hero() {
  return (
    <section className="relative overflow-hidden bg-[radial-gradient(ellipse_at_top_right,color-mix(in_oklch,var(--color-accent)_12%,transparent)_0%,transparent_60%)]">
      <div className="relative mx-auto max-w-7xl px-5 pb-20 pt-16 md:px-8 md:pb-28 md:pt-24">
        <Reveal>
          <Eyebrow num="00 /">Built for wholesale &amp; E&amp;S brokers</Eyebrow>
        </Reveal>
        <Reveal delay={80}>
          <h1 className="mt-6 max-w-4xl text-display font-serif text-foreground">
            The AI operating system built for{" "}
            <em className="text-accent not-italic">wholesale &amp; E&amp;S broker placement</em>.
          </h1>
        </Reveal>
        <Reveal delay={160}>
          <p className="mt-7 max-w-2xl text-lg leading-relaxed text-ink-soft md:text-xl">
            Coverline reads every retail submission, ranks it against your carrier panel, keeps
            renewals on track as they come due, and drafts every retail agent update along the way —
            with your broker approving every decision.
          </p>
        </Reveal>
        <Reveal delay={240}>
          <div className="mt-9 flex flex-wrap items-center gap-6">
            <DemoLinkButton>
              Book a demo <ArrowRight className="h-4 w-4" />
            </DemoLinkButton>
            <a
              href="#how"
              className="group inline-flex items-center gap-2 rounded-sm text-sm font-medium text-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
            >
              See how it works
              <span className="h-px w-6 bg-foreground transition-all group-hover:w-10" />
            </a>
          </div>
        </Reveal>

        {/* Trust bar */}
        <Reveal delay={320}>
          <div className="mt-16 grid gap-6 rule-t rule-b py-5 text-sm text-ink-soft md:grid-cols-3 md:divide-x md:divide-border md:gap-0">
            {[
              "Every recommendation cited to source",
              "Your broker approves every decision",
              "Built for wholesale brokers, not carriers",
            ].map((t, i) => (
              <div key={i} className="md:px-6 first:md:pl-0">
                {t}
              </div>
            ))}
          </div>
        </Reveal>
      </div>
    </section>
  );
}

// Counts up to the real length of a tier's items array on scroll-into-view —
// deliberately not used for any marketing claim, just an honest item count.
function CountBadge({ value }: { value: number }) {
  const [ref, inView] = useInView<HTMLSpanElement>();
  const n = useCountUp(value, inView, 600);
  return (
    <span ref={ref} className="font-mono text-[11px] text-ink-soft tabular-nums">
      {n.toString().padStart(2, "0")}
    </span>
  );
}

function Problem() {
  return (
    <section id="problem" className="rule-t scroll-anchor bg-secondary/60">
      <div className="mx-auto grid max-w-7xl gap-14 px-5 py-20 md:grid-cols-12 md:gap-10 md:px-8 md:py-28">
        <Reveal className="md:col-span-5">
          <Eyebrow num="01 /">The problem</Eyebrow>
          <h2 className="mt-5 text-h2 font-serif leading-[1.1]">
            Submission volume outgrew the team reading it.
          </h2>
        </Reveal>
        <Reveal delay={100} className="md:col-span-6 md:col-start-7">
          <p className="text-lg leading-relaxed text-ink-soft">
            Wholesale and E&amp;S brokers write high submission volume with lean placement teams.
            Every new submission has to be read, checked against a carrier panel whose appetite
            keeps shifting — tightening on one class, opening up on another as the book grows — and
            re-packaged separately for each carrier before a single quote comes back. Renewals
            repeat the same work every year, for every account already on the book.
          </p>

          {/* Documents in → decision out schematic */}
          <div className="mt-10 rule-t pt-8">
            <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-6">
              <div>
                <div className="label-eyebrow mb-3">Documents in</div>
                <div className="relative h-32">
                  {["ACORD 125", "Loss Run", "Financials", "Carrier response"].map((d, i) => (
                    <div
                      key={d}
                      className="absolute left-0 flex h-8 w-full items-center gap-2 rule-b bg-background pl-3 text-xs text-ink-soft"
                      style={{
                        top: `${i * 14}px`,
                        transform: `translateX(${i * 6}px)`,
                        maxWidth: `calc(100% - ${i * 6}px)`,
                      }}
                    >
                      <FileText aria-hidden="true" className="h-3.5 w-3.5 text-accent/70" />
                      {d}
                    </div>
                  ))}
                </div>
              </div>
              <ArrowRight aria-hidden="true" className="h-5 w-5 text-ink-soft" />
              <div>
                <div className="label-eyebrow mb-3 text-right">Decision out</div>
                <div className="rule-t rule-b bg-background p-4">
                  <div className="label-eyebrow text-accent">Recommendation</div>
                  <div className="mt-1 font-serif text-lg">Proceed to market</div>
                  <div className="mt-2 flex items-center gap-1.5 text-[11px] text-ink-soft">
                    <ShieldCheck aria-hidden="true" className="h-3 w-3" />
                    Pending broker approval
                  </div>
                </div>
              </div>
            </div>
          </div>
        </Reveal>
      </div>
    </section>
  );
}

const steps = [
  {
    n: "01",
    key: "Read",
    body: "Coverline reads applications, loss runs, financials, and carrier response emails as they arrive.",
    sample: (
      <div className="space-y-1.5 font-mono text-[11px] leading-relaxed">
        <div className="bg-accent/15 px-1.5 py-0.5">
          Named Insured: <span className="text-accent">Riverbend Logistics LLC</span>
        </div>
        <div>Effective: 03/01/2026</div>
        <div className="bg-accent/15 px-1.5 py-0.5">
          TIV: <span className="text-accent">$14.2M</span>
        </div>
        <div>SIC: 4213 · Trucking</div>
        <div className="bg-accent/15 px-1.5 py-0.5">
          5-yr losses: <span className="text-accent">$482k / 11 claims</span>
        </div>
      </div>
    ),
  },
  {
    n: "02",
    key: "Match",
    body: "Every submission is ranked against your carrier panel — hard exclusions, soft-scored fit — automatically.",
    sample: (
      <ul className="space-y-2 text-xs">
        <li className="flex items-center gap-2">
          <Check aria-hidden="true" className="h-3.5 w-3.5 text-success" /> 3 of 5 carriers in
          appetite
        </li>
        <li className="flex items-center gap-2">
          <Check aria-hidden="true" className="h-3.5 w-3.5 text-success" /> Radius ≤ 500 mi
        </li>
        <li className="flex items-center gap-2 text-warn">
          <span aria-hidden="true" className="inline-block h-2 w-2 bg-warn" /> Loss ratio flag: 42%
        </li>
        <li className="flex items-center gap-2">
          <Check aria-hidden="true" className="h-3.5 w-3.5 text-success" /> MVR complete
        </li>
      </ul>
    ),
  },
  {
    n: "03",
    key: "Package",
    body: "A carrier-specific package is assembled and a recommendation drafted, with every claim cited to its source document.",
    sample: (
      <div>
        <div className="font-serif text-lg leading-snug">
          Proceed to market — package for top 3 carriers.
        </div>
        <div className="mt-3 border-l-2 border-accent pl-2 text-[11px] text-ink-soft">
          Cited: Loss Run p.2, ACORD 125 §4
        </div>
      </div>
    ),
  },
  {
    n: "04",
    key: "Approve",
    body: "Your broker reviews, edits if needed, and approves. Nothing moves forward without a human decision.",
    sample: (
      <div className="flex flex-col gap-2">
        <button className="cursor-default rule-t rule-b bg-foreground py-2 text-xs font-medium text-background">
          Approve &amp; send
        </button>
        <button className="cursor-default rule-t rule-b py-2 text-xs font-medium">
          Edit draft
        </button>
        <button className="cursor-default py-2 text-xs text-ink-soft">Override with note</button>
      </div>
    ),
  },
];

function HowItWorks() {
  const [active, setActive] = useState("0");
  return (
    <section id="how" className="rule-t scroll-anchor">
      <div className="mx-auto max-w-7xl px-5 py-20 md:px-8 md:py-28">
        <Reveal className="max-w-3xl">
          <Eyebrow num="02 /">How it works</Eyebrow>
          <h2 className="mt-5 text-h2 font-serif leading-[1.05]">
            AI drafts. <span className="text-ink-soft">Your broker decides.</span>
          </h2>
        </Reveal>

        <Reveal delay={100}>
          <Tabs value={active} onValueChange={setActive} className="mt-16">
            <TabsList className="grid h-auto w-full grid-cols-2 gap-px rounded-none rule-t rule-b bg-border p-0 md:grid-cols-4">
              {steps.map((s, i) => (
                <TabsTrigger
                  key={s.n}
                  value={String(i)}
                  className="group flex h-auto flex-col items-stretch justify-start whitespace-normal rounded-none bg-background p-6 text-left ring-offset-0 transition-colors hover:bg-secondary/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-0 data-[state=active]:bg-secondary/60 data-[state=active]:shadow-none md:p-8"
                >
                  <div className="flex items-baseline justify-between">
                    <span className="font-mono text-xs text-accent group-data-[state=active]:text-accent-2">
                      {s.n}
                    </span>
                    <span className="label-eyebrow">Step</span>
                  </div>
                  <div className="mt-6 font-serif text-2xl tracking-[-0.01em] md:text-3xl">
                    {s.key}
                  </div>
                  <p className="mt-3 text-sm leading-relaxed text-ink-soft">{s.body}</p>
                </TabsTrigger>
              ))}
            </TabsList>

            {steps.map((s, i) => (
              <TabsContent
                key={s.n}
                value={String(i)}
                className="mt-4 rule-t rule-b bg-secondary/50 p-6 data-[state=active]:animate-in data-[state=active]:fade-in-0 data-[state=active]:duration-300 md:p-8"
              >
                <div className="mb-4 flex flex-wrap items-center gap-2">
                  <div className="label-eyebrow">Sample view · {s.key}</div>
                  <span className="rounded-full border border-border px-1.5 py-0.5 text-[9px] font-medium normal-case tracking-normal text-muted-foreground">
                    Illustrative
                  </span>
                </div>
                {s.sample}
              </TabsContent>
            ))}
          </Tabs>
        </Reveal>
      </div>
    </section>
  );
}

type WorkflowDetail = {
  title: string;
  blurb: string;
  inputs: string;
  outputs: string;
  whoFor: string;
};
type Tier = { label: string; tone: "now" | "next" | "later" | "cross"; items: WorkflowDetail[] };

const tiers: Tier[] = [
  {
    label: "Available now",
    tone: "now",
    items: [
      {
        title: "Submission Market Matching",
        blurb:
          "Read, extract, and rank every new submission against your carrier panel's appetite.",
        inputs:
          "Retail agent submission email + attachments (ACORD forms, SOV, loss runs, financials)",
        outputs:
          "Ranked carrier panel with fit scores, per-carrier missing-info list, and a proceed / request-info / no-market recommendation",
        whoFor: "The broker triaging new business as it lands in the inbox",
      },
    ],
  },
  {
    label: "Coming next",
    tone: "next",
    items: [
      {
        title: "Submission Package Assembly",
        blurb: "Assemble a carrier-specific package straight from your carrier selection.",
        inputs: "Carrier selection from Market Matching + the extracted document set",
        outputs:
          "A completeness-checked, carrier-specific package with an auto-filled supplemental form and drafted cover letter",
        whoFor: "The broker turning a shortlist of carriers into something ready to send",
      },
      {
        title: "Retail Agent Communication",
        blurb:
          "Draft status updates, missing-info requests, no-market notices, and quote summaries — you send.",
        inputs: "Submission status, carrier responses, and the broker's own past tone and edits",
        outputs:
          "A drafted email in the right register for the moment — approved or edited before it sends",
        whoFor: "Whoever owns the day-to-day relationship with the retail agent",
      },
      {
        title: "Quote Comparison & Recommendation",
        blurb: "Normalize carrier terms, classify subjectivity materiality, and recommend.",
        inputs: "Carrier quote and declination emails for one submission",
        outputs:
          "A normalized side-by-side comparison, materiality-classified subjectivities, and a recommended carrier to present",
        whoFor: "The broker deciding which terms to bring back to the retail agent",
      },
    ],
  },
  {
    label: "On the roadmap",
    tone: "later",
    items: [
      {
        title: "Binder & Policy Issuance Coordination",
        blurb:
          "Coordinate the bind request, track subjectivity clearance, and reconcile the carrier's confirmation and issued policy against what was agreed.",
        inputs:
          "The selected quote, subjectivity checklist, and the carrier's bind confirmation / policy documents",
        outputs:
          "A cleared-to-bind status and a reconciled issued policy — no carrier document trusted by default",
        whoFor: "The broker holding the file from selected quote to issued policy",
      },
      {
        title: "Endorsement / Mid-Term Change Processing",
        blurb:
          "Classify mid-term change requests by materiality, recheck appetite, and reconcile multi-part requests item by item.",
        inputs: "A mid-term change request against a bound policy",
        outputs:
          "A materiality classification, a re-run appetite check, and an itemized reconciliation for multi-part requests",
        whoFor: "The broker processing a change on an already-bound account",
      },
      {
        title: "Renewal Remarketing",
        blurb:
          "Detect exposure and loss changes plus incumbent responsiveness, and produce a graduated remarket recommendation.",
        inputs:
          "The prior term, the renewal submission, and the incumbent carrier's responsiveness history",
        outputs:
          "A four-state recommendation — renew as-is, monitor, competitive check, or active shop",
        whoFor: "The broker deciding whether an account needs to be shopped again",
      },
    ],
  },
  {
    label: "Cross-cutting layers",
    tone: "cross",
    items: [
      {
        title: "Diligent Search & Compliance Documentation",
        blurb:
          "Determine per-state diligent-search requirements, verify declination evidence, and generate compliant surplus-lines documentation.",
        inputs:
          "The placing state, class of business, and declination emails from admitted markets",
        outputs:
          "A per-state requirement check and a surplus-lines affidavit — generated only once every required declination has sufficient written evidence on file",
        whoFor: "Whoever owns compliance sign-off on non-admitted placements",
      },
      {
        title: "Carrier Appetite Intelligence Tracking",
        blurb:
          "Aggregate signals already logged by Quote Comparison and Renewal Remarketing, and surface well-evidenced appetite-shift suggestions.",
        inputs: "Quote and remarket outcomes already logged elsewhere in the system",
        outputs:
          "A narrow, well-evidenced set of suggested carrier-appetite updates for a human to approve",
        whoFor: "Whoever maintains the carrier panel's appetite profiles",
      },
      {
        title: "Pipeline & Carrier Performance Reporting",
        blurb:
          "Aggregate every pipeline workflow's logs into a funnel view, carrier hit-rate comparison, and remarketing value report.",
        inputs: "Logged activity from every other workflow in the suite",
        outputs:
          "A submission-to-bound funnel, carrier hit-rate comparison, and a remarketing value report",
        whoFor: "Whoever reports on the book — principals, ops, or the broker themselves",
      },
    ],
  },
];

function StatusBadge({ tone }: { tone: Tier["tone"] }) {
  const map = {
    now: { label: "Available now", cls: "border-success/30 bg-success/10 text-success" },
    next: { label: "Coming next", cls: "border-accent/30 bg-accent/10 text-accent" },
    later: { label: "Roadmap", cls: "border-accent-2/30 bg-accent-2/10 text-accent-2" },
    cross: { label: "Roadmap", cls: "border-accent-2/30 bg-accent-2/10 text-accent-2" },
  } as const;
  const { label, cls } = map[tone];
  return (
    <span className={`shrink-0 rounded-full border px-2.5 py-1 text-[11px] font-medium ${cls}`}>
      {label}
    </span>
  );
}

function Workflows() {
  return (
    <section id="workflows" className="rule-t scroll-anchor bg-secondary/60">
      <div className="mx-auto max-w-7xl px-5 py-20 md:px-8 md:py-28">
        <Reveal className="max-w-3xl">
          <Eyebrow num="03 /">Workflow suite</Eyebrow>
          <h2 className="mt-5 text-h2 font-serif leading-[1.05]">
            One workflow suite for the entire placement lifecycle.
          </h2>
          <p className="mt-5 text-lg leading-relaxed text-ink-soft">
            Not a single point tool — the operating layer for how wholesale &amp; E&amp;S brokers
            match, place, and communicate with retail agents and carriers. Click any workflow for
            what it does, what goes in and out, and who it's for.
          </p>
        </Reveal>

        <div className="mt-14 space-y-10">
          {tiers.map((tier, ti) => (
            <Reveal key={`${tier.label}-${ti}`} delay={ti * 60}>
              <div className="mb-5 flex items-baseline justify-between rule-b pb-3">
                <div className="label-eyebrow flex items-center gap-3">
                  <span
                    className={`h-1.5 w-1.5 rounded-full ${
                      tier.tone === "now"
                        ? "bg-accent"
                        : tier.tone === "next"
                          ? "bg-ink-soft"
                          : "border border-ink-soft bg-transparent"
                    }`}
                  />
                  {tier.label}
                </div>
                <CountBadge value={tier.items.length} />
              </div>

              <Accordion type="single" collapsible className="grid gap-4 md:grid-cols-3">
                {tier.items.map((item) => (
                  <AccordionItem
                    key={item.title}
                    value={item.title}
                    className={`transition-shadow hover:shadow-sm ${
                      tier.tone === "now"
                        ? "border-2 border-accent/40 bg-accent/5"
                        : tier.tone === "next"
                          ? "border border-border bg-background"
                          : "border border-dashed border-border bg-transparent text-ink-soft"
                    }`}
                  >
                    <AccordionTrigger className="items-start p-6 text-left hover:no-underline focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring [&>svg]:mt-1.5 [&>svg]:opacity-60">
                      <div>
                        <div className="mb-2">
                          <StatusBadge tone={tier.tone} />
                        </div>
                        <div className="font-serif text-xl tracking-[-0.01em]">{item.title}</div>
                        <p className="mt-3 text-sm leading-relaxed text-ink-soft">{item.blurb}</p>
                      </div>
                    </AccordionTrigger>
                    <AccordionContent className="px-6 pb-6">
                      <dl className="space-y-3 border-t border-border pt-4 text-sm">
                        <div>
                          <dt className="label-eyebrow !text-[10px] opacity-70">
                            Inputs → Outputs
                          </dt>
                          <dd className="mt-1 leading-relaxed text-foreground">
                            {item.inputs}{" "}
                            <ArrowRight aria-hidden="true" className="mx-1 inline h-3 w-3" />{" "}
                            {item.outputs}
                          </dd>
                        </div>
                        <div>
                          <dt className="label-eyebrow !text-[10px] opacity-70">Who it's for</dt>
                          <dd className="mt-1 leading-relaxed text-foreground">{item.whoFor}</dd>
                        </div>
                      </dl>
                    </AccordionContent>
                  </AccordionItem>
                ))}
              </Accordion>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  );
}

function Why() {
  const cols = [
    {
      title: "Carrier-panel-native appetite logic",
      body: "Configured around how wholesale/E&S brokers actually place risk — a curated carrier panel, hard exclusions, soft-scored ranking — not retrofitted from enterprise carrier software.",
    },
    {
      title: "The full placement lifecycle, not one point tool",
      body: "Market matching, package assembly, quote comparison, and remarketing all run on the same core, so your data and decisions compound instead of living in five different tools.",
    },
    {
      title: "Runs on what you already use",
      body: "Email, spreadsheets, and your CRM — no dedicated policy admin system required to get started.",
    },
  ];
  return (
    <section id="why" className="rule-t scroll-anchor">
      <div className="mx-auto max-w-7xl px-5 py-20 md:px-8 md:py-28">
        <Reveal className="max-w-3xl">
          <Eyebrow num="04 /">Why wholesale &amp; E&amp;S brokers choose Coverline</Eyebrow>
          <h2 className="mt-5 text-h2 font-serif leading-[1.05]">
            Built for wholesale brokers. Not adapted from a carrier platform.
          </h2>
        </Reveal>
        <div className="mt-14 grid gap-px rule-t rule-b bg-border md:grid-cols-3">
          {cols.map((c, i) => (
            <Reveal
              key={c.title}
              delay={i * 90}
              className="bg-background p-8 transition-colors hover:bg-secondary/30"
            >
              <span className="font-mono text-xs text-accent">0{i + 1}</span>
              <div className="mt-5 font-serif text-2xl leading-snug tracking-[-0.01em]">
                {c.title}
              </div>
              <p className="mt-4 text-sm leading-relaxed text-ink-soft">{c.body}</p>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  );
}

function Security() {
  const blocks = [
    {
      icon: ShieldCheck,
      title: "Human approval, always",
      body: "No recommendation reaches a retail agent or carrier, and nothing gets written back to your systems, without explicit broker approval.",
    },
    {
      icon: ScrollText,
      title: "Full audit trail",
      body: "Every decision, every override, every source document — logged and traceable.",
    },
    {
      icon: FileText,
      title: "Built with security in mind",
      body: "Data encrypted at rest and in transit, role-based access controls.",
    },
  ];
  return (
    <section id="security" className="rule-t scroll-anchor bg-secondary/60">
      <div className="mx-auto max-w-7xl px-5 py-20 md:px-8 md:py-28">
        <Reveal className="max-w-3xl">
          <div className="label-eyebrow flex items-center gap-3">
            <span className="font-mono text-accent">05 /</span>
            <span>Security &amp; trust</span>
          </div>
          <h2 className="mt-5 text-h2 font-serif leading-[1.05]">
            Your broker is always in control.
          </h2>
        </Reveal>
        {/*
          NOTE: Add specific compliance certifications only once actually
          obtained — do not state SOC 2 or similar unless true.
        */}
        <div className="mt-14 grid gap-10 md:grid-cols-3">
          {blocks.map(({ icon: Icon, title, body }, i) => (
            <Reveal key={title} delay={i * 90} className="border-t border-border pt-6">
              <Icon aria-hidden="true" className="h-5 w-5 text-accent" />
              <div className="mt-5 font-serif text-2xl leading-snug tracking-[-0.01em]">
                {title}
              </div>
              <p className="mt-3 text-sm leading-relaxed text-ink-soft">{body}</p>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  );
}

function Integrations() {
  const items = [
    {
      title: "Email",
      body: "Reads submissions and drafts every reply straight from the inbox you already use — no new mailbox to check.",
    },
    {
      title: "Spreadsheets",
      body: "Google Sheets as a lightweight record when there's no policy admin system in place yet.",
    },
    {
      title: "CRM",
      body: "Salesforce and HubSpot — retail agent and account context flows in without re-entering it.",
    },
    {
      title: "Policy admin systems",
      body: "Applied Epic, Guidewire, and Duck Creek — approved actions write back where you already keep the book of record.",
    },
  ];
  return (
    <section id="integrations" className="rule-t scroll-anchor">
      <div className="mx-auto max-w-7xl px-5 py-20 md:px-8 md:py-28">
        <Reveal className="max-w-3xl">
          <Eyebrow num="06 /">Integrations</Eyebrow>
          <h2 className="mt-5 text-h2 font-serif leading-[1.05]">
            Connects to what's already running your desk.
          </h2>
          <p className="mt-5 text-lg leading-relaxed text-ink-soft">
            No rip-and-replace. Coverline sits on top of the tools your team already opens every
            day.
          </p>
        </Reveal>
        <div className="mt-14 grid gap-px rule-t rule-b bg-border sm:grid-cols-2 md:grid-cols-4">
          {items.map((item, i) => (
            <Reveal
              key={item.title}
              delay={i * 80}
              className="bg-background p-6 transition-colors hover:bg-secondary/30"
            >
              <div className="font-serif text-lg leading-snug tracking-[-0.01em]">{item.title}</div>
              <p className="mt-3 text-sm leading-relaxed text-ink-soft">{item.body}</p>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  );
}

const faq = [
  {
    q: "Does the AI act on its own?",
    a: "No. Coverline reads documents, checks your carrier panel's appetite, and drafts a recommendation — it never sends a no-market notice, submits a package to a carrier, or writes anything to your systems without a human approving it first. Every recommendation sits in a review queue until a broker approves, edits, or overrides it, and every decision is logged with who approved it and when.",
  },
  {
    q: "How does it read documents?",
    a: "It extracts structured data from PDFs, scanned forms, Excel files, and emails using OCR and document classification tuned for insurance formats — ACORD applications, loss runs, and carrier quote or declination emails included. Every extracted field is traceable back to the exact document it came from. If a document is too degraded to read reliably, it's routed to a manual review queue instead of guessing.",
  },
  {
    q: "Do I need a dedicated policy admin system to use it?",
    a: "No. Coverline runs on the tools you're already using — email, spreadsheets, and your CRM — so you can start without a policy admin system in place. If you do have one connected, approved actions can write back there directly.",
  },
  {
    q: "What happens if my policy admin system isn't connected?",
    a: "Everything still works. Coverline still reads submissions, ranks them against your panel, and drafts recommendations — approved decisions are just recorded in a connected fallback like Google Sheets instead.",
  },
  {
    q: "Which wholesale/E&S workflows does Coverline support today?",
    a: "Submission Market Matching is available now. Submission Package Assembly, Retail Agent Communication, and Quote Comparison & Recommendation are in active development. See the full roadmap above.",
  },
];

function FAQ() {
  return (
    <section id="faq" className="rule-t scroll-anchor">
      <div className="mx-auto grid max-w-7xl gap-12 px-5 py-20 md:grid-cols-12 md:gap-10 md:px-8 md:py-28">
        <Reveal className="md:col-span-4">
          <Eyebrow num="07 /">Questions</Eyebrow>
          <h2 className="mt-5 text-h2 font-serif leading-[1.05]">Frequently asked.</h2>
        </Reveal>
        <Reveal delay={100} className="md:col-span-8">
          <Accordion type="single" collapsible className="w-full">
            {faq.map((f, i) => (
              <AccordionItem key={i} value={`item-${i}`} className="border-b border-border">
                <AccordionTrigger className="py-6 text-left font-serif text-lg tracking-[-0.01em] hover:no-underline focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring md:text-xl">
                  {f.q}
                </AccordionTrigger>
                <AccordionContent className="pb-6 text-base leading-relaxed text-ink-soft">
                  {f.a}
                </AccordionContent>
              </AccordionItem>
            ))}
          </Accordion>
        </Reveal>
      </div>
    </section>
  );
}

function FinalCTA() {
  return (
    <section id="demo-teaser" className="rule-t scroll-anchor bg-secondary/60">
      <div className="mx-auto max-w-7xl px-5 py-24 md:px-8 md:py-32">
        <Reveal className="max-w-3xl">
          <Eyebrow num="08 /">Book a demo</Eyebrow>
          <h2 className="mt-5 text-display font-serif leading-[1.02]">
            Give your placement team back their week.
          </h2>
          <p className="mt-7 max-w-2xl text-lg leading-relaxed text-ink-soft">
            See how Submission Market Matching, Package Assembly, and Retail Agent Communication run
            on your own book.
          </p>
          <div className="mt-10">
            <DemoLinkButton>
              Book a demo <ArrowRight className="h-4 w-4" />
            </DemoLinkButton>
          </div>
        </Reveal>
      </div>
    </section>
  );
}

function Footer() {
  return (
    <footer className="rule-t bg-background">
      <div className="mx-auto grid max-w-7xl gap-12 px-5 py-14 md:grid-cols-12 md:px-8">
        <div className="md:col-span-6">
          <Wordmark />
          <p className="mt-4 max-w-sm text-sm text-ink-soft">
            The AI operating system for wholesale &amp; E&amp;S broker placement.
          </p>
        </div>
        <div className="md:col-span-3">
          <div className="label-eyebrow mb-4">Product</div>
          <ul className="space-y-2 text-sm">
            <li>
              <a
                href="#workflows"
                className="rounded-sm hover:text-accent focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              >
                Workflows
              </a>
            </li>
            <li>
              <a
                href="#security"
                className="rounded-sm hover:text-accent focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              >
                Security
              </a>
            </li>
          </ul>
        </div>
        <div className="md:col-span-3">
          <div className="label-eyebrow mb-4">Company</div>
          <ul className="space-y-2 text-sm">
            <li>
              <a
                href="#why"
                className="rounded-sm hover:text-accent focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              >
                About
              </a>
            </li>
            <li>
              <Link
                to="/demo"
                className="rounded-sm hover:text-accent focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              >
                Contact
              </Link>
            </li>
          </ul>
        </div>
      </div>
      <div className="rule-t">
        <div className="mx-auto flex max-w-7xl flex-col justify-between gap-2 px-5 py-6 text-xs text-ink-soft md:flex-row md:px-8">
          <span>© 2026 Coverline. All rights reserved.</span>
          <span className="font-mono">Wholesale/E&amp;S placement · v1</span>
        </div>
      </div>
    </footer>
  );
}

export function CoverlineLanding() {
  const [authOpen, setAuthOpen] = useState(false);
  const [authMode, setAuthMode] = useState<"login" | "signup">("login");

  return (
    <div className="min-h-screen bg-background text-foreground">
      <Nav
        onOpenAuth={(mode) => {
          setAuthMode(mode);
          setAuthOpen(true);
        }}
      />
      <main>
        <Hero />
        <Problem />
        <HowItWorks />
        <Workflows />
        <Why />
        <Security />
        <Integrations />
        <FAQ />
        <FinalCTA />
      </main>
      <Footer />
      <AuthDialog
        open={authOpen}
        onOpenChange={setAuthOpen}
        mode={authMode}
        onModeChange={setAuthMode}
      />
    </div>
  );
}
