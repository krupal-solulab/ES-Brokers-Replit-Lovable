import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";
import { CountUp, StatePill, useInView, usePrefersReducedMotion } from "./primitives";
import { CitationLink } from "./CitationPanel";
import { IconChevron, IconCheck, IconFlag, IconCross, IconRefresh } from "./icons";

/* Single shared data source for every market-plan rendering on the site. */

export type SubmissionField = { label: string; value: string; source: string };

export const submission = {
  account: "Riverbend Logistics LLC",
  effective: "03/01/2026",
  classLine: "Trucking, long haul · SIC 4213",
  fields: [
    { label: "Power units", value: "42", source: "ACORD 127 — Vehicle Schedule" },
    { label: "Radius", value: "Over 500 miles", source: "ACORD 127 — Radius of Operation" },
    { label: "Scheduled equipment", value: "$7.4M", source: "Equipment schedule p.1" },
    { label: "Revenue", value: "$9.2M", source: "Financials p.3" },
    { label: "5-yr incurred losses", value: "$2.07M / 31 claims", source: "Loss Run p.2" },
    { label: "5-yr earned premium", value: "$3.05M", source: "Loss Run p.1" },
    { label: "Loss ratio", value: "68%", source: "Calculated: $2.07M ÷ $3.05M" },
  ] satisfies SubmissionField[],
};

type Carrier = {
  rank: string;
  name: string;
  score: number;
  confirms: string[];
  flags: string[];
  why: string;
};

export const carriers: Carrier[] = [
  {
    rank: "01",
    name: "Carrier A",
    score: 94,
    confirms: [
      "Class in appetite",
      "Territory eligible",
      "$25M capacity available",
      "Loss ratio within 75% maximum",
    ],
    flags: ["Needs: current driver schedule"],
    why: "long-haul appetite · preferred territory · capacity available",
  },
  {
    rank: "02",
    name: "Carrier B",
    score: 87,
    confirms: ["Class in appetite", "Territory eligible"],
    flags: [
      "Loss ratio 68% — above 60% preferred, within 70% maximum",
      "Needs: current driver schedule, updated equipment schedule",
    ],
    why: "class fit · loss history inside maximum · no referral required",
  },
  {
    rank: "03",
    name: "Carrier C",
    score: 76,
    confirms: ["Class in appetite", "Territory eligible"],
    flags: ["Referral required — radius over 500 miles", "Needs: MVR summary"],
    why: "class fit · radius above auto-bind threshold",
  },
];

export const excluded = [
  { name: "Carrier D", reason: "Hard exclusion — long-haul radius over 500 miles" },
  { name: "Carrier E", reason: "Hard exclusion — not licensed in filed state" },
  { name: "Carrier F", reason: "Hard exclusion — 5-yr loss ratio above 65% maximum" },
];

export const notEligible = excluded.map((e) => `${e.name} — ${e.reason}`);

const APPETITE_TOOLTIP =
  "Appetite fit is a rules-based score against your configured carrier profiles. It is not a probability of quote.";

export function AppetiteFitLabel({ className }: { className?: string }) {
  return (
    <abbr
      title={APPETITE_TOOLTIP}
      className={cn("cursor-help no-underline decoration-dotted", className)}
    >
      appetite fit
    </abbr>
  );
}

/* --------------------- demo playback state machine --------------------- */

type Phase = "idle" | "reading" | "eliminating" | "ranking" | "done";

/** unsorted starting order — the FLIP reorder must be visible, not pre-sorted */
const START_ORDER = ["02", "03", "01"];
const RANKED_ORDER = ["01", "02", "03"];

function useDemo(fieldCount: number, reduced: boolean) {
  const [phase, setPhase] = useState<Phase>("idle");
  const [fieldsShown, setFieldsShown] = useState(0);
  const [flash, setFlash] = useState<number | null>(null);
  const [struck, setStruck] = useState<string[]>([]);
  const [dropped, setDropped] = useState<string[]>([]);
  const [order, setOrder] = useState<string[]>(RANKED_ORDER);
  const [scoring, setScoring] = useState(false);
  const [runs, setRuns] = useState(0);
  const timers = useRef<number[]>([]);

  const clear = () => {
    timers.current.forEach((t) => window.clearTimeout(t));
    timers.current = [];
  };
  const at = (ms: number, fn: () => void) => {
    timers.current.push(window.setTimeout(fn, ms));
  };

  const settle = useCallback(() => {
    clear();
    setPhase("done");
    setFieldsShown(fieldCount);
    setFlash(null);
    setStruck(excluded.map((e) => e.name));
    setDropped(excluded.map((e) => e.name));
    setOrder(RANKED_ORDER);
    setScoring(true);
  }, [fieldCount]);

  const run = useCallback(
    (speed = 1) => {
      if (reduced) {
        settle();
        return;
      }
      clear();
      setRuns((r) => r + 1);
      setPhase("reading");
      setFieldsShown(0);
      setFlash(null);
      setStruck([]);
      setDropped([]);
      setOrder(START_ORDER);
      setScoring(false);

      const s = (ms: number) => ms * speed;
      let t = 0;

      // a. fields populate one at a time, each flashing as it is read
      for (let i = 0; i < fieldCount; i++) {
        t += s(150);
        at(t, () => {
          setFieldsShown(i + 1);
          setFlash(i);
        });
        at(t + s(400), () => setFlash((f) => (f === i ? null : f)));
      }

      // b. excluded carriers strike through, then collapse out one at a time
      t += s(450);
      at(t, () => setPhase("eliminating"));
      excluded.forEach((e, i) => {
        at(t + s(i * 150), () => setStruck((v) => [...v, e.name]));
        at(t + s(i * 150 + 300), () => setDropped((v) => [...v, e.name]));
      });
      t += s(excluded.length * 150 + 350);

      // c. scores count up while rows FLIP into rank order
      at(t, () => {
        setPhase("ranking");
        setScoring(true);
        setOrder(RANKED_ORDER);
      });
      t += s(750);

      // d. citations become active again
      at(t, () => setPhase("done"));
    },
    [fieldCount, reduced, settle],
  );

  useEffect(() => () => clear(), []);

  return { phase, fieldsShown, flash, struck, dropped, order, scoring, runs, run, settle };
}

/* ------------------------------ component ------------------------------ */

export function MarketPlanComponent({
  variant = "full",
  className,
}: {
  variant?: "full" | "compact";
  className?: string;
}) {
  const reduced = usePrefersReducedMotion();
  const { ref, inView } = useInView<HTMLDivElement>(0.15);
  const [expanded, setExpanded] = useState<string | null>("01");
  const [tab, setTab] = useState<"ranked" | "notEligible" | "submission">("ranked");

  const shownFields = variant === "compact" ? submission.fields.slice(0, 4) : submission.fields;
  const shownCarriers = variant === "compact" ? carriers.slice(0, 2) : carriers;

  const demo = useDemo(shownFields.length, reduced);
  const { phase, run, settle } = demo;
  const autoplayed = useRef(false);

  // shortened autoplay once, the first time the component scrolls into view
  useEffect(() => {
    if (!inView || autoplayed.current) return;
    autoplayed.current = true;
    if (reduced) {
      settle();
      return;
    }
    const t = window.setTimeout(() => run(0.55), 250);
    return () => window.clearTimeout(t);
  }, [inView, reduced, run, settle]);

  /* ---- FLIP reordering of the carrier rows ---- */
  const rowRefs = useRef(new Map<string, HTMLDivElement>());
  const prevTops = useRef(new Map<string, number>());
  useLayoutEffect(() => {
    if (reduced) return;
    const moves: Array<[HTMLDivElement, number]> = [];
    rowRefs.current.forEach((el, key) => {
      const top = el.getBoundingClientRect().top;
      const prev = prevTops.current.get(key);
      if (prev !== undefined && Math.abs(prev - top) > 1) moves.push([el, prev - top]);
      prevTops.current.set(key, top);
    });
    if (!moves.length) return;
    for (const [el, dy] of moves) {
      el.style.transition = "none";
      el.style.transform = `translateY(${dy}px)`;
    }
    requestAnimationFrame(() => {
      for (const [el] of moves) {
        el.style.transition = "transform 400ms var(--ease-standard)";
        el.style.transform = "";
      }
    });
  }, [demo.order, demo.dropped, reduced]);

  const inert = phase === "reading" || phase === "eliminating" || phase === "ranking";
  const orderedCarriers = demo.order
    .map((r) => shownCarriers.find((c) => c.rank === r))
    .filter(Boolean) as Carrier[];

  const rankedPanel = (
    <div>
      {orderedCarriers.map((c) => {
        const open = expanded === c.rank;
        return (
          <div
            key={c.rank}
            ref={(el) => {
              if (el) rowRefs.current.set(c.rank, el);
              else rowRefs.current.delete(c.rank);
            }}
            className="border-b border-hairline last:border-b-0"
          >
            <button
              type="button"
              aria-expanded={open}
              onClick={() => setExpanded(open ? null : c.rank)}
              className="flex min-h-[44px] w-full items-center gap-3 py-3 text-left"
            >
              <span className="font-mono text-[13px] text-navy-400">
                {phase === "idle" || phase === "reading" ? "—" : c.rank}
              </span>
              <span className="flex-1 text-[15px] font-semibold text-navy-900">{c.name}</span>
              <StatePill tone={c.score >= 80 ? "success" : "warning"}>
                {c.score >= 80 ? "Strong fit" : "Conditional"}
              </StatePill>
              <span className="font-mono text-[22px] font-bold text-navy-900 tabular-nums">
                <CountUp
                  key={`${c.rank}-${demo.runs}`}
                  value={c.score}
                  suffix="%"
                  duration={700}
                  start={demo.scoring}
                />
              </span>
              <IconChevron
                size={18}
                className={cn(
                  "text-navy-400 transition-transform duration-200 ease-[var(--ease-standard)]",
                  open && "rotate-180",
                )}
              />
            </button>
            <div
              className="grid transition-all duration-200 ease-[var(--ease-standard)]"
              style={{ gridTemplateRows: open ? "1fr" : "0fr", opacity: open ? 1 : 0 }}
            >
              <div className="overflow-hidden">
                <div className="space-y-2 pb-4 pl-8">
                  {c.confirms.map((t) => (
                    <p key={t} className="flex items-start gap-2 font-mono text-[13px] text-navy-700">
                      <IconCheck size={14} className="mt-0.5 shrink-0 text-success-text" />
                      {t}
                    </p>
                  ))}
                  {c.flags.map((t) => (
                    <p key={t} className="flex items-start gap-2 font-mono text-[13px] text-navy-700">
                      <IconFlag size={14} className="mt-0.5 shrink-0 text-warning-text" />
                      {t}
                    </p>
                  ))}
                  <p className="font-mono text-[13px] text-navy-400">Why: {c.why}</p>
                </div>
              </div>
            </div>
          </div>
        );
      })}

      {/* candidates still being eliminated sit in the same list until they drop out */}
      {excluded
        .filter((e) => !demo.dropped.includes(e.name))
        .map((e) => (
          <div
            key={e.name}
            className="grid border-b border-hairline transition-all duration-300 ease-[var(--ease-standard)]"
            style={{ gridTemplateRows: "1fr", opacity: demo.struck.includes(e.name) ? 0.45 : 1 }}
          >
            <div className="flex min-h-[44px] items-center gap-3 overflow-hidden py-3">
              <span className="font-mono text-[13px] text-navy-400">—</span>
              <span
                className={cn(
                  "flex-1 text-[15px] font-semibold text-navy-900 transition-all duration-300",
                  demo.struck.includes(e.name) && "text-navy-400 line-through",
                )}
              >
                {e.name}
              </span>
              <span
                className="font-mono text-[12px] text-danger-text transition-opacity duration-300"
                style={{ opacity: demo.struck.includes(e.name) ? 1 : 0 }}
              >
                {e.reason}
              </span>
            </div>
          </div>
        ))}
    </div>
  );

  const notEligiblePanel = (
    <div className="space-y-2 pt-4">
      <p className="type-eyebrow">Not eligible (5 carriers)</p>
      {excluded.map((e) => {
        const here = demo.dropped.includes(e.name);
        return (
          <p
            key={e.name}
            className="flex items-start gap-2 font-mono text-[13px] text-navy-400 transition-all duration-300 ease-[var(--ease-standard)]"
            style={{ opacity: here ? 1 : 0, transform: here ? "none" : "translateY(-6px)" }}
          >
            <IconCross size={14} className="mt-0.5 shrink-0 text-danger-text" />
            {e.name} — {e.reason}
          </p>
        );
      })}
      <p className="pl-6 font-mono text-[13px] text-navy-400">(+2 more, collapsed)</p>
    </div>
  );

  const submissionPanel = (
    <dl className="divide-y divide-hairline">
      <div className="flex flex-col gap-1 py-3 sm:flex-row sm:items-baseline sm:gap-4">
        <dt className="min-w-[168px] text-[13px] font-semibold text-navy-900">Class</dt>
        <dd className="font-mono text-[13px] text-navy-700">{submission.classLine}</dd>
      </div>
      {shownFields.map((f, i) => {
        const shown = demo.fieldsShown > i;
        return (
          <div
            key={f.label}
            className={cn(
              "flex flex-col gap-1 rounded-[4px] px-1 py-3 transition-colors duration-[400ms] ease-[var(--ease-standard)] sm:flex-row sm:items-baseline sm:gap-4",
              demo.flash === i && "bg-gray-100",
            )}
            style={{
              opacity: shown ? 1 : 0,
              transform: shown ? "none" : "translateY(6px)",
              transition:
                "opacity 200ms var(--ease-standard), transform 200ms var(--ease-standard), background-color 400ms var(--ease-standard)",
            }}
          >
            <dt className="min-w-[168px] text-[13px] font-semibold text-navy-900">{f.label}</dt>
            <dd className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
              <span className="font-mono text-[14px] font-medium text-navy-900 tabular-nums">
                {f.value}
              </span>
              <CitationLink value={f.value} source={f.source} disabled={inert} />
            </dd>
          </div>
        );
      })}
    </dl>
  );

  return (
    <div className={cn("relative", className)}>
      <div
        ref={ref}
        className={cn(
          "overflow-hidden rounded-[14px] bg-background shadow-tier2 transition-all duration-500 ease-[var(--ease-standard)]",
          inView ? "scale-100 opacity-100" : "scale-[0.98] opacity-0",
        )}
      >
        {/* header */}
        <div className="sticky top-0 z-10 bg-panel px-5 py-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.04)] lg:px-6">
          <div className="flex items-center justify-between gap-4">
            <p className="type-eyebrow text-[color:color-mix(in_oklab,white_58%,transparent)]">
              Submission
            </p>
            <p className="font-mono text-[11px] tracking-wide text-[color:color-mix(in_oklab,white_66%,transparent)]">
              {phase === "reading"
                ? "reading…"
                : phase === "eliminating"
                  ? "applying appetite rules…"
                  : phase === "ranking"
                    ? "ranking…"
                    : phase === "done"
                      ? "Extracted"
                      : "Ready"}
            </p>
          </div>
          <div className="mt-1 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
            <h3 className="text-[17px] font-semibold text-white">{submission.account}</h3>
            <p className="font-mono text-[13px] text-[color:color-mix(in_oklab,white_66%,transparent)]">
              Effective {submission.effective} · 9 of 14 eligible
            </p>
          </div>
          <div className="mt-3 flex items-center gap-3">
            <button
              type="button"
              onClick={() => run(1)}
              disabled={inert}
              className={cn(
                "inline-flex min-h-[36px] items-center gap-2 rounded-[10px] border border-[color:color-mix(in_oklab,white_28%,transparent)] px-3 text-[13px] font-semibold text-white transition-all duration-150 ease-[var(--ease-standard)]",
                inert
                  ? "opacity-50"
                  : "hover:bg-[color:color-mix(in_oklab,white_12%,transparent)]",
              )}
            >
              {phase === "done" ? (
                <IconRefresh size={14} />
              ) : (
                <span aria-hidden className="text-[11px]">
                  ▶
                </span>
              )}
              {phase === "done" ? "Run again" : "Run this submission"}
            </button>
          </div>
        </div>

        {/* mobile segmented control */}
        <div className="flex gap-1 border-b border-hairline bg-gray-050 p-2 lg:hidden">
          {(
            [
              ["ranked", "Ranked markets"],
              ["notEligible", "Not eligible"],
              ["submission", "Submission"],
            ] as const
          ).map(([k, label]) => (
            <button
              key={k}
              type="button"
              onClick={() => setTab(k)}
              className={cn(
                "min-h-[44px] flex-1 rounded-[4px] px-2 text-[12px] font-semibold transition-colors duration-150",
                tab === k ? "bg-background text-navy-900 shadow-tier1" : "text-navy-400",
              )}
            >
              {label}
            </button>
          ))}
        </div>

        <div className="px-5 pt-4 pb-5 lg:px-6 lg:pb-6">
          {/* desktop */}
          <div className="hidden lg:block">
            {submissionPanel}
            <div className="mt-6">
              <p className="type-eyebrow mb-2">
                Recommended markets ({variant === "compact" ? "top 2 of 9" : "9 of 14 eligible"})
              </p>
              {rankedPanel}
            </div>
            {variant === "full" ? notEligiblePanel : null}
          </div>

          {/* mobile */}
          <div className="lg:hidden">
            {tab === "submission" ? submissionPanel : null}
            {tab === "ranked" ? rankedPanel : null}
            {tab === "notEligible" ? notEligiblePanel : null}
          </div>

          <div className="mt-6 flex flex-wrap items-center justify-between gap-4 border-t border-hairline pt-5">
            <button
              type="button"
              className="inline-flex min-h-[44px] items-center rounded-[10px] bg-cta px-5 text-[14px] font-semibold text-white transition-all duration-150 hover:bg-cta-hover"
            >
              Select markets → Build packages
            </button>
            <p className="type-body-s">Product interface. De-identified sample account.</p>
          </div>
        </div>
      </div>
    </div>
  );
}
