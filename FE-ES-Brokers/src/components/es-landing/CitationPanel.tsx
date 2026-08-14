import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { cn } from "@/lib/utils";
import { IconCitation, IconCross } from "./icons";

/**
 * SIGNATURE INTERACTIVE MOMENT #4 — one citation interaction for the whole site.
 * Clicking any citation opens a real panel (right-side slide-in on desktop,
 * bottom sheet on mobile) rendering a mocked source-document preview with the
 * cited field highlighted. Esc / click-outside / X close it and focus returns
 * to the citation that opened it.
 */

type DocPreview = {
  title: string;
  page: string;
  lines: Array<{ label: string; value: string; hit?: boolean }>;
  note?: string;
};

const DOCS: Record<string, DocPreview> = {
  "ACORD 127 — Vehicle Schedule": {
    title: "ACORD 127 — Commercial Auto Section",
    page: "Vehicle Schedule · p.1",
    lines: [
      { label: "Named insured", value: "Riverbend Logistics LLC" },
      { label: "Vehicle type", value: "Tractor / trailer, long haul" },
      { label: "Power units", value: "42", hit: true },
      { label: "Trailers", value: "58" },
      { label: "Garaging state", value: "TX" },
    ],
  },
  "ACORD 127 — Radius of Operation": {
    title: "ACORD 127 — Commercial Auto Section",
    page: "Radius of Operation · p.1",
    lines: [
      { label: "Local (0–50 mi)", value: "0%" },
      { label: "Intermediate (51–200 mi)", value: "15%" },
      { label: "Long haul (over 500 mi)", value: "Over 500 miles", hit: true },
    ],
  },
  "Equipment schedule p.1": {
    title: "Equipment schedule",
    page: "p.1",
    lines: [
      { label: "Tractors (18 units)", value: "$4,120,000" },
      { label: "Trailers (58 units)", value: "$2,610,000" },
      { label: "Ancillary equipment", value: "$670,000" },
      { label: "Scheduled equipment total", value: "$7.4M", hit: true },
    ],
  },
  "Financials p.3": {
    title: "Financial statement",
    page: "p.3 — Statement of operations",
    lines: [
      { label: "Gross revenue", value: "$9.2M", hit: true },
      { label: "Operating expenses", value: "$8.1M" },
      { label: "Fiscal year end", value: "12/31/2025" },
    ],
  },
  "Loss Run p.2": {
    title: "Carrier loss run",
    page: "p.2 — Incurred summary, 5 years",
    lines: [
      { label: "Open claims", value: "6" },
      { label: "Closed claims", value: "25" },
      { label: "Total claims", value: "31", hit: true },
      { label: "5-yr incurred", value: "$2.07M", hit: true },
    ],
  },
  "Loss Run p.1": {
    title: "Carrier loss run",
    page: "p.1 — Premium summary, 5 years",
    lines: [
      { label: "Policy periods", value: "03/2021 – 03/2026" },
      { label: "5-yr earned premium", value: "$3.05M", hit: true },
    ],
  },
  "Calculated: $2.07M ÷ $3.05M": {
    title: "Derived figure",
    page: "Calculated · Loss Run p.1–2",
    lines: [
      { label: "5-yr incurred losses", value: "$2.07M" },
      { label: "5-yr earned premium", value: "$3.05M" },
      { label: "Loss ratio", value: "68%", hit: true },
    ],
    note: "Derived figures show their arithmetic. Coverline separates what a document says from what a broker concludes.",
  },
  "Calculated · Loss Run p.1–2": {
    title: "Derived figure",
    page: "Calculated · Loss Run p.1–2",
    lines: [
      { label: "5-yr incurred losses", value: "$2.07M" },
      { label: "5-yr earned premium", value: "$3.05M" },
      { label: "Loss ratio", value: "68%", hit: true },
    ],
    note: "Derived figures show their arithmetic. Coverline separates what a document says from what a broker concludes.",
  },
  "Financials · p.3": {
    title: "Financial statement",
    page: "p.3 — Statement of operations",
    lines: [
      { label: "Gross revenue", value: "$9.2M", hit: true },
      { label: "Operating expenses", value: "$8.1M" },
    ],
  },
  "Equipment schedule · p.1": {
    title: "Equipment schedule",
    page: "p.1",
    lines: [
      { label: "Tractors (18 units)", value: "$4,120,000" },
      { label: "Trailers (58 units)", value: "$2,610,000" },
      { label: "Scheduled equipment total", value: "$7.4M", hit: true },
    ],
  },
};

type Ctx = { open: (source: string, value: string, el?: HTMLElement | null) => void };
const CitationCtx = createContext<Ctx | null>(null);

export function useCitation() {
  return useContext(CitationCtx);
}

export function CitationProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<{ source: string; value: string } | null>(null);
  const returnTo = useRef<HTMLElement | null>(null);

  const open = useCallback((source: string, value: string, el?: HTMLElement | null) => {
    returnTo.current = el ?? (document.activeElement as HTMLElement | null);
    setState({ source, value });
  }, []);

  const close = useCallback(() => {
    setState(null);
    const el = returnTo.current;
    if (el) window.setTimeout(() => el.focus({ preventScroll: true }), 0);
  }, []);

  useEffect(() => {
    if (!state) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [state, close]);

  const doc = state ? DOCS[state.source] : undefined;

  return (
    <CitationCtx.Provider value={{ open }}>
      {children}
      {state ? (
        <div className="fixed inset-0 z-[70] flex items-end justify-end lg:items-stretch">
          <button
            type="button"
            aria-label="Close source document"
            onClick={close}
            className="absolute inset-0 bg-[color:color-mix(in_oklab,var(--navy-950)_45%,transparent)]"
          />
          <div
            role="dialog"
            aria-modal="true"
            aria-label="Source document"
            className="relative flex max-h-[78vh] w-full translate-y-0 flex-col overflow-hidden rounded-t-[14px] bg-background shadow-tier2 duration-[320ms] ease-[var(--ease-standard)] animate-in slide-in-from-bottom lg:h-full lg:max-h-none lg:w-[420px] lg:rounded-none lg:slide-in-from-right lg:slide-in-from-bottom-0"
          >
            <div className="flex items-start justify-between gap-4 bg-panel px-6 py-5 shadow-[inset_0_1px_0_rgba(255,255,255,0.04)]">
              <div>
                <p className="type-eyebrow text-[color:color-mix(in_oklab,white_58%,transparent)]">
                  Source document
                </p>
                <p className="mt-1 text-[16px] font-semibold text-white">
                  {doc?.title ?? state.source}
                </p>
                <p className="mt-1 font-mono text-[12px] text-[color:color-mix(in_oklab,white_66%,transparent)]">
                  {doc?.page ?? state.source}
                </p>
              </div>
              <button
                type="button"
                onClick={close}
                aria-label="Close"
                className="-mr-2 flex size-11 shrink-0 items-center justify-center text-white"
              >
                <IconCross size={20} />
              </button>
            </div>

            <div className="flex-1 overflow-auto p-6">
              <p className="type-body-s">
                Cited for: <span className="font-mono text-navy-900">{state.value}</span>
              </p>

              {/* mocked page preview */}
              <div className="mt-4 rounded-[10px] border border-hairline bg-gray-050 p-5 shadow-tier1">
                <p className="type-eyebrow">{doc?.page ?? state.source}</p>
                <div className="mt-4 space-y-px">
                  {(doc?.lines ?? []).map((l) => (
                    <div
                      key={l.label}
                      className={cn(
                        "flex items-baseline justify-between gap-4 rounded-[4px] px-2 py-2 font-mono text-[13px]",
                        l.hit
                          ? "bg-[color:color-mix(in_oklab,var(--blue-500)_10%,transparent)] text-navy-900 ring-1 ring-blue-500"
                          : "text-navy-400",
                      )}
                    >
                      <span>{l.label}</span>
                      <span className="tabular-nums">{l.value}</span>
                    </div>
                  ))}
                </div>
                <div className="mt-5 space-y-2" aria-hidden>
                  {[92, 78, 86].map((w, i) => (
                    <span
                      key={i}
                      className="block h-1.5 rounded-[1px] bg-hairline"
                      style={{ width: `${w}%` }}
                    />
                  ))}
                </div>
              </div>

              <p className="type-body-s mt-5">
                {doc?.note ??
                  "The source opens at the exact page and section the figure was extracted from."}
              </p>
            </div>
          </div>
        </div>
      ) : null}
    </CitationCtx.Provider>
  );
}

export function CitationLink({
  value,
  source,
  label,
  disabled = false,
  className,
}: {
  value: string;
  source: string;
  label?: string;
  disabled?: boolean;
  className?: string;
}) {
  const ctx = useCitation();
  const ref = useRef<HTMLButtonElement>(null);
  return (
    <button
      ref={ref}
      type="button"
      disabled={disabled}
      onClick={() => ctx?.open(source, value, ref.current)}
      className={cn(
        "group inline-flex min-h-[24px] items-center gap-1.5 text-left font-mono text-[13px] text-navy-400 transition-colors duration-150",
        disabled ? "cursor-default opacity-60" : "hover:text-blue-500",
        className,
      )}
    >
      <IconCitation size={14} className="shrink-0" />
      <span className="relative">
        {label ?? source}
        <span
          className={cn(
            "absolute right-0 -bottom-0.5 left-0 h-px origin-left scale-x-0 bg-blue-500 transition-transform duration-150 ease-[var(--ease-standard)]",
            !disabled && "group-hover:scale-x-100",
          )}
        />
      </span>
      <span className="sr-only">— open source for {value}</span>
    </button>
  );
}
