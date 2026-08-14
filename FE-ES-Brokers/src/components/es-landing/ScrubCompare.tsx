import { useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";
import { usePrefersReducedMotion } from "./primitives";
import { IconArrow } from "./icons";

/**
 * SIGNATURE INTERACTIVE MOMENT #2 — Today vs. Coverline.
 * Desktop: the section pins in the viewport and the sequence is scroll-scrubbed
 * (progress maps 1:1 to scroll position inside the section, no scroll-jacking).
 * Mobile: a swipeable segmented control between the two paths.
 */

const TODAY = [
  "Retail submission lands with 15 documents",
  "Placement specialist opens each one",
  "Keys the exposure into a spreadsheet",
  "Opens the appetite guide for each carrier",
  "Checks exclusions, state licensing, capacity",
  "Tries to remember who tightened up last quarter",
  "Picks 8–12 markets from memory",
  "Sends it",
  "Three carriers come back asking for what was missing",
  "Repackage and resend",
];

const COVERLINE: Array<[string, boolean]> = [
  ["Retail submission lands with 15 documents", false],
  ["Coverline reads all of them", true],
  ["Extracts every field, cited to source", true],
  ["Removes every carrier that can't write it, naming the rule", true],
  ["Scores and ranks the rest against your panel", true],
  ["Names what each carrier still needs, up front", true],
  ["Broker reviews the ranked plan and selects markets", false],
  ["Carrier-specific packages assembled", true],
];

function Path({
  title,
  steps,
  shown,
  accent,
  days,
  closer,
  dim = false,
}: {
  title: string;
  steps: Array<[string, boolean]>;
  shown: number;
  accent: "navy" | "blue";
  days: number;
  closer: string;
  dim?: boolean;
}) {
  const stroke = accent === "blue" ? "var(--blue-500)" : "var(--navy-400)";
  return (
    <div
      className={cn(
        "transition-all duration-500 ease-[var(--ease-standard)]",
        dim ? "scale-[0.97] opacity-35" : "scale-100 opacity-100",
      )}
    >
      <div className="mb-5 flex items-baseline justify-between gap-4">
        <p className="type-eyebrow">{title}</p>
        <p className="font-mono text-[13px] text-navy-400 tabular-nums">
          <span className="text-[20px] font-bold text-navy-900">{days}</span> days
        </p>
      </div>
      <ol className="space-y-0">
        {steps.map(([label, bold], i) => {
          const on = i < shown;
          return (
            <li key={label} className="relative flex gap-4">
              <div className="flex w-6 shrink-0 flex-col items-center">
                <svg width="24" height="24" viewBox="0 0 24 24" aria-hidden className="mt-2">
                  <rect
                    x="6.5"
                    y="6.5"
                    width="11"
                    height="11"
                    fill="none"
                    stroke={stroke}
                    strokeWidth="1.5"
                    style={{ opacity: on ? 1 : 0, transition: "opacity 200ms var(--ease-standard)" }}
                  />
                  <rect
                    x="10"
                    y="10"
                    width="4"
                    height="4"
                    fill={stroke}
                    style={{ opacity: on ? 1 : 0, transition: "opacity 200ms var(--ease-standard)" }}
                  />
                </svg>
                {i < steps.length - 1 ? (
                  <svg className="w-6 flex-1" viewBox="0 0 24 48" preserveAspectRatio="none" aria-hidden>
                    <path
                      d="M12 0 V16 H19 V32 H12 V44"
                      stroke={stroke}
                      strokeWidth="1.5"
                      fill="none"
                      vectorEffect="non-scaling-stroke"
                      strokeDasharray="120"
                      strokeDashoffset={on ? 0 : 120}
                      style={{ transition: "stroke-dashoffset 400ms var(--ease-standard)" }}
                    />
                    <path
                      d="M8 40 L12 46 L16 40"
                      stroke={stroke}
                      strokeWidth="1.5"
                      fill="none"
                      vectorEffect="non-scaling-stroke"
                      style={{ opacity: on ? 1 : 0, transition: "opacity 200ms var(--ease-standard) 200ms" }}
                    />
                  </svg>
                ) : null}
              </div>
              <div
                className="min-w-0 flex-1 pb-4 last:pb-0"
                style={{
                  opacity: on ? 1 : 0,
                  transform: on ? "none" : "translateY(8px)",
                  transition:
                    "opacity 300ms var(--ease-standard) 150ms, transform 300ms var(--ease-standard) 150ms",
                }}
              >
                <div
                  className={cn(
                    "rounded-[10px] border px-4 py-3 text-[15px] leading-6",
                    bold
                      ? "border-hairline bg-background font-semibold text-navy-900 shadow-tier1"
                      : "border-hairline bg-transparent text-navy-700",
                  )}
                >
                  {label}
                </div>
              </div>
            </li>
          );
        })}
      </ol>
      <p
        className="mt-5 border-t border-hairline pt-5 text-[16px] font-bold text-navy-900"
        style={{
          opacity: shown >= steps.length ? 1 : 0,
          transition: "opacity 300ms var(--ease-standard)",
        }}
      >
        {closer}
      </p>
    </div>
  );
}

export function ScrubCompare() {
  const reduced = usePrefersReducedMotion();
  const sectionRef = useRef<HTMLDivElement>(null);
  const [progress, setProgress] = useState(0);
  const [mobileTab, setMobileTab] = useState<"today" | "coverline">("today");
  const touchX = useRef<number | null>(null);

  useEffect(() => {
    if (reduced) {
      setProgress(1);
      return;
    }
    const el = sectionRef.current;
    if (!el) return;
    let raf = 0;
    const update = () => {
      raf = 0;
      const rect = el.getBoundingClientRect();
      const total = rect.height - window.innerHeight;
      if (total <= 0) {
        setProgress(1);
        return;
      }
      const p = Math.min(1, Math.max(0, -rect.top / total));
      setProgress(p);
    };
    const onScroll = () => {
      if (!raf) raf = requestAnimationFrame(update);
    };
    update();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    return () => {
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
      if (raf) cancelAnimationFrame(raf);
    };
  }, [reduced]);

  // 0 → 0.55 builds "Today"; 0.55 → 1 recedes it and builds "With Coverline".
  const todayP = Math.min(1, progress / 0.55);
  const covP = Math.max(0, (progress - 0.5) / 0.45);
  const todayShown = Math.round(todayP * TODAY.length);
  const covShown = Math.round(Math.min(1, covP) * COVERLINE.length);
  const todayDays = Math.round(todayP * 10);
  const covDays = Math.round(Math.min(1, covP) * 3);
  const recede = progress > 0.58;

  const todaySteps: Array<[string, boolean]> = TODAY.map((t) => [t, false]);

  return (
    <>
      {/* desktop: scroll-scrubbed, pinned */}
      <div ref={sectionRef} className="relative hidden h-[280vh] lg:block">
        <div className="sticky top-[72px] flex min-h-[calc(100vh-72px)] flex-col justify-center py-10">
          <div className="mb-6 flex items-center gap-4">
            <div className="h-px flex-1 bg-hairline">
              <div
                className="h-px origin-left bg-blue-500"
                style={{ transform: `scaleX(${progress})` }}
              />
            </div>
            <p className="type-eyebrow shrink-0">
              Scroll to compare · {Math.round(progress * 100)}%
            </p>
          </div>
          <div className="grid grid-cols-2 items-start gap-16">
            <Path
              title="Today"
              accent="navy"
              steps={todaySteps}
              shown={todayShown}
              days={todayDays}
              dim={recede}
              closer="Ten days to markets engaged. And that's one submission."
            />
            <Path
              title="With Coverline"
              accent="blue"
              steps={COVERLINE}
              shown={covShown}
              days={covDays}
              closer="Three days to markets engaged. On every submission, not just the clean ones."
            />
          </div>
        </div>
      </div>

      {/* mobile: swipeable segmented control */}
      <div
        className="lg:hidden"
        onTouchStart={(e) => {
          touchX.current = e.touches[0]?.clientX ?? null;
        }}
        onTouchEnd={(e) => {
          const start = touchX.current;
          const end = e.changedTouches[0]?.clientX;
          if (start == null || end == null) return;
          if (end - start < -40) setMobileTab("coverline");
          if (end - start > 40) setMobileTab("today");
          touchX.current = null;
        }}
      >
        <div className="flex gap-1 rounded-[10px] bg-gray-100 p-1">
          {(
            [
              ["today", "Today"],
              ["coverline", "With Coverline"],
            ] as const
          ).map(([k, label]) => (
            <button
              key={k}
              type="button"
              onClick={() => setMobileTab(k)}
              aria-pressed={mobileTab === k}
              className={cn(
                "min-h-[44px] flex-1 rounded-[10px] px-3 text-[14px] font-semibold transition-colors duration-150",
                mobileTab === k ? "bg-background text-navy-900 shadow-tier1" : "text-navy-400",
              )}
            >
              {label}
            </button>
          ))}
        </div>
        <p className="type-body-s mt-3 flex items-center gap-2">
          <IconArrow size={16} /> Swipe between the two paths
        </p>
        <div className="mt-6">
          {mobileTab === "today" ? (
            <Path
              title="Today"
              accent="navy"
              steps={todaySteps}
              shown={TODAY.length}
              days={10}
              closer="Ten days to markets engaged. And that's one submission."
            />
          ) : (
            <Path
              title="With Coverline"
              accent="blue"
              steps={COVERLINE}
              shown={COVERLINE.length}
              days={3}
              closer="Three days to markets engaged. On every submission, not just the clean ones."
            />
          )}
        </div>
      </div>
    </>
  );
}
