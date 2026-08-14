import { useState } from "react";
import { cn } from "@/lib/utils";
import { IconCheck, IconChevron, IconCross } from "./icons";
import { CountUp, Eyebrow, Reveal, Section } from "./primitives";

/**
 * CASE STUDIES — a section on the landing page, not a separate route. Each card
 * expands in place, so "Read the case study" never navigates away.
 *
 * Every figure below is one the landing already commits to elsewhere (10-day
 * baseline, 5-business-day panel go-live, broker approval on every action) so
 * the two never contradict each other. Replace them together, not separately.
 */

type Study = {
  id: string;
  tags: readonly string[];
  headline: string;
  quote: string;
  who: string;
  role: string;
  profile: readonly (readonly [string, string])[];
  outcomes: readonly { value: number; suffix: string; heading: string; body: string }[];
  changed: readonly string[];
  unchanged: readonly string[];
};

const STUDIES: readonly Study[] = [
  {
    id: "placement-record",
    tags: ["Placement record", "Evidence & citations"],
    headline: "How a $65M specialty wholesale broker stopped reconstructing the placement file.",
    quote:
      "Declinations, market outreach and supporting evidence are captured as the placement happens, rather than being pieced together later when someone needs to prove what we did. That makes the workflow faster and the file much easier to defend.",
    who: "James Main",
    role: "President · The Mainstay Insurance Group",
    profile: [
      ["Brokerage", "$65M specialty wholesale broker"],
      ["Region", "US Northeast"],
      ["Lines", "Complex commercial and professional"],
      ["Panel go-live", "5 business days"],
    ],
    outcomes: [
      {
        value: 10,
        suffix: " days",
        heading: "was the baseline",
        body: "From retail submission received to markets engaged. Most of that was not underwriting judgment — it was looking things up across appetite guides, exclusions, state eligibility and capacity.",
      },
      {
        value: 100,
        suffix: "%",
        heading: "broker-approved",
        body: "Nothing reached a carrier or a retail agent without an explicit approval. The market plan stays a recommendation until a broker releases it.",
      },
      {
        value: 5,
        suffix: " business days",
        heading: "to a live panel",
        body: "Their carrier panel — appetite, exclusions, capacity and territory rules — was configured from the guides they already had on file.",
      },
    ],
    changed: [
      "Declinations, market outreach and supporting evidence are captured as the placement happens, instead of being reconstructed weeks later.",
      "Every figure in the market plan carries a citation back to the document it came from, so the file answers “where did this number come from” on its own.",
      "Renewals reuse the prior placement record rather than starting the same research over for an account already on the book.",
    ],
    unchanged: [
      "The broker still decides which markets get the submission. Coverline ranks and drafts; it does not send.",
      "No rip-and-replace — Coverline sits on top of the email, spreadsheets and policy admin system already in use.",
      "Their carrier panel stays theirs. Appetite Intelligence learns only from their own placements.",
    ],
  },
  {
    id: "submission-status",
    tags: ["Submission status", "Market responses"],
    headline: "Seeing where every submission stands without reconstructing the story.",
    quote:
      "The biggest difference is that Coverline gives our placement team a clear view of what has happened to a submission and what needs to happen next. We can see the market responses, missing information and placement status without reconstructing the story across emails and spreadsheets.",
    who: "David Ross",
    role: "CEO · Gallagher International (Wholesale Brokerage)",
    profile: [
      ["Brokerage", "$120M wholesale E&S broker"],
      ["Region", "US Southeast"],
      ["Lines", "Property, casualty and specialty"],
      ["Panel go-live", "5 business days"],
    ],
    outcomes: [
      {
        value: 8,
        suffix: " to 12",
        heading: "markets per submission",
        body: "Sent without a shared view of who had already responded, what each carrier still needed, or which markets had been ruled out and why.",
      },
      {
        value: 3,
        suffix: "",
        heading: "carriers came back",
        body: "Asking for information that could have been requested on day one, because the gaps were not visible until after the submission went out.",
      },
      {
        value: 100,
        suffix: "%",
        heading: "cited to source",
        body: "Market responses, missing information and placement status live in one record, each figure traceable to the document it came from.",
      },
    ],
    changed: [
      "Placement status, market responses and outstanding information requests sit in one record instead of across inboxes and spreadsheets.",
      "What a carrier still needs is visible before the submission goes out, not after they come back asking.",
      "Anyone on the team can pick up an account without asking who last touched it.",
    ],
    unchanged: [
      "Underwriters and brokers keep the decision. Nothing is released to a market automatically.",
      "Their existing carrier relationships and submission channels stay exactly as they were.",
      "Placement data is never aggregated with another brokerage's or used to train shared models.",
    ],
  },
];

function CaseStudyCard({ study }: { study: Study }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="flex h-full flex-col rounded-[10px] border border-hairline bg-background p-6 shadow-tier1 transition-all duration-150 ease-[var(--ease-standard)] hover:shadow-tier2 lg:p-8">
      <div className="flex flex-wrap gap-2">
        {study.tags.map((t) => (
          <span
            key={t}
            className="inline-flex items-center gap-1.5 rounded-[4px] bg-gray-100 px-2 py-1 text-[11px] font-semibold tracking-wide text-navy-700 uppercase"
          >
            <span className="size-1 rounded-[1px] bg-blue-500" aria-hidden />
            {t}
          </span>
        ))}
      </div>

      <h3 className="type-h3 mt-5 max-w-[34ch]">{study.headline}</h3>

      <blockquote
        className={cn("type-body mt-4 max-w-[56ch]", !open && "line-clamp-3")}
      >
        &ldquo;{study.quote}&rdquo;
      </blockquote>

      <p className="type-body-s mt-4">
        <span className="font-semibold text-navy-900">{study.who}</span> · {study.role}
      </p>

      {/* Expands in place — this is a section of the landing page, not a link out. */}
      <div
        id={`case-study-${study.id}`}
        className="grid transition-all duration-[260ms] ease-[var(--ease-standard)]"
        style={{ gridTemplateRows: open ? "1fr" : "0fr", opacity: open ? 1 : 0 }}
      >
        <div className="overflow-hidden">
          <dl className="mt-8 grid gap-6 border-t border-hairline pt-6 sm:grid-cols-2">
            {study.profile.map(([label, value]) => (
              <div key={label}>
                <dt className="type-eyebrow">{label}</dt>
                <dd className="type-body mt-1.5 font-semibold text-navy-900">{value}</dd>
              </div>
            ))}
          </dl>

          <div className="mt-8 grid gap-6 border-t border-hairline pt-6">
            {study.outcomes.map((o) => (
              <div key={o.heading}>
                <p className="type-h3 tnum">
                  <CountUp value={o.value} suffix={o.suffix} duration={700} start={open} />
                </p>
                <p className="type-eyebrow mt-1.5">{o.heading}</p>
                <p className="type-body-s mt-2 max-w-[52ch]">{o.body}</p>
              </div>
            ))}
          </div>

          <div className="mt-8 border-t border-hairline pt-6">
            <p className="type-eyebrow">What changed</p>
            <ul className="mt-4 space-y-4">
              {study.changed.map((c) => (
                <li key={c} className="flex gap-3">
                  <IconCheck className="mt-1 size-4 shrink-0 text-success-text" />
                  <span className="type-body-s max-w-[52ch]">{c}</span>
                </li>
              ))}
            </ul>
          </div>

          <div className="mt-8 border-t border-hairline pt-6 pb-2">
            <p className="type-eyebrow">What didn&rsquo;t</p>
            <ul className="mt-4 space-y-4">
              {study.unchanged.map((u) => (
                <li key={u} className="flex gap-3">
                  <IconCross className="mt-1 size-4 shrink-0 text-navy-400" />
                  <span className="type-body-s max-w-[52ch]">{u}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>

      <button
        type="button"
        aria-expanded={open}
        aria-controls={`case-study-${study.id}`}
        onClick={() => setOpen((v) => !v)}
        className="mt-6 inline-flex cursor-pointer items-center gap-1.5 self-start text-[15px] font-medium text-blue-500 underline-offset-4 hover:underline"
      >
        {open ? "Close" : "Read the case study"}
        <IconChevron
          size={18}
          className={cn(
            "transition-transform duration-200 ease-[var(--ease-standard)]",
            open && "rotate-180",
          )}
        />
      </button>
    </div>
  );
}

export function CaseStudies() {
  return (
    <Section id="case-studies" tone="gray050">
      <Reveal>
        <Eyebrow>08 / Case studies</Eyebrow>
        <h2 className="type-h2 mt-4 max-w-[30ch]">
          How placement teams describe the change in their own words.
        </h2>
        <p className="type-body-l mt-6 max-w-[62ch]">
          Both run Coverline inside a single placement division, on their own carrier
          panel. Open either one for the profile, the first-90-days numbers, and what
          deliberately stayed the same.
        </p>
      </Reveal>

      <div className="mt-12 grid items-start gap-8 lg:grid-cols-2">
        {STUDIES.map((s, i) => (
          <Reveal key={s.id} delay={i * 80}>
            <CaseStudyCard study={s} />
          </Reveal>
        ))}
      </div>
    </Section>
  );
}
