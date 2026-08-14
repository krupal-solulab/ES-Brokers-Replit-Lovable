import {
  Scan,
  Gavel,
  Sparkles,
  ShieldCheck,
  ArrowRight,
  CheckCircle2,
  AlertTriangle,
  Send,
  Download,
  Mail,
  Loader2,
  FileSpreadsheet,
  HardDrive,
  Calendar,
  MessageSquare,
  Receipt,
  type LucideIcon,
} from "lucide-react";
import { PageHeader } from "./AppShell";
import { Panel, Chip, Tabs, Button } from "./Workflows";
import {
  carrierPerformance,
  retailAgents,
  stateMix,
  pipelineCompleteness,
  placementCycle,
} from "./mocks";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import Nango from "@nangohq/frontend";
import {
  GOOGLE_MAIL_PROVIDER,
  GOOGLE_SHEET_PROVIDER,
  GOOGLE_DRIVE_PROVIDER,
  GOOGLE_CALENDAR_PROVIDER,
  SLACK_PROVIDER,
  QUICKBOOKS_PROVIDER,
  confirmConnection,
  createConnectSession,
  disconnectIntegration,
  listIntegrations,
} from "@/lib/api/integrations";
import { askAssistant, getAssistantOverview, type ChatMessage } from "@/lib/api/assistant";

const extractionCaps = [
  {
    title: "Email ingestion",
    desc: "Submission mailboxes are read the moment they arrive.",
    metric: "12.4k / mo",
  },
  {
    title: "OCR",
    desc: "Scanned PDFs and handwritten forms parsed into structured data.",
    metric: "99.1% char acc.",
  },
  {
    title: "ACORD extraction",
    desc: "ACORD 125 / 126 / 130 / 140 / 25 / 175 supported out of the box.",
    metric: "24 forms",
  },
  {
    title: "Loss run extraction",
    desc: "Multi-year loss runs from every major carrier reconciled into a single schema.",
    metric: "38 carriers",
  },
  {
    title: "Financials extraction",
    desc: "P&L, balance sheet, and payroll audits parsed with cross-year deltas.",
    metric: "5yr history",
  },
  {
    title: "Schedule of Values",
    desc: "Location-level TIV, occupancy, construction, protection extracted from any SOV format.",
    metric: "Excel + PDF",
  },
  {
    title: "Document classification",
    desc: "Every attachment auto-classified before parsing.",
    metric: "22 classes",
  },
  {
    title: "Cross-document validation",
    desc: "Revenue, address, TIV reconciled across every document.",
    metric: "0-conflict target",
  },
  {
    title: "Confidence scoring",
    desc: "Every field carries a confidence score and a citation to the source page.",
    metric: "Per-field",
  },
  {
    title: "Source citations",
    desc: "Click any extracted field to jump to the exact source in the document viewer.",
    metric: "Traceable",
  },
];

const matchingCaps = [
  {
    title: "Carrier appetite profiles",
    desc: "A manually-curated appetite schema per carrier — class, capacity, state, exclusions.",
  },
  {
    title: "Hard-exclusion rules",
    desc: "Instant disqualification for out-of-appetite class, state, or TIV — no scoring wasted.",
  },
  {
    title: "Soft-scoring ranking",
    desc: "Every non-excluded carrier ranked by composite fit score, explainable factor by factor.",
  },
  {
    title: "Per-carrier missing-info detection",
    desc: "Each carrier's supplemental requirements checked against what's already been extracted.",
  },
  {
    title: "AI explanations",
    desc: "Every ranking includes a plain-English rationale + citations.",
  },
  {
    title: "Human review",
    desc: "Every recommendation routes to a broker before it becomes external action.",
  },
  { title: "Decision logging", desc: "Immutable log of every AI and human decision, exportable." },
  {
    title: "Audit trail",
    desc: "Rule-level explanations, override rationales, and citations tied to each submission.",
  },
];

export function ExtractionCore() {
  return (
    <div className="mx-auto max-w-[1400px] animate-in fade-in-0 duration-500">
      <PageHeader
        eyebrow="Foundation · Shared platform capability"
        title="Extraction Core"
        description="One AI extraction platform reused by every Coverline workflow — from submissions to endorsements to renewals. Shared with the MGA vertical."
        actions={
          <>
            <span className="inline-flex items-center gap-1 rounded-full border border-border bg-background px-2 py-1 text-[11px]">
              <Scan className="h-3 w-3 text-accent" />
              Used by 8 workflows
            </span>
          </>
        }
      />

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]">
        <Panel title="What it does">
          <p className="text-sm text-ink-soft">
            Extraction Core reads the messy inputs of the E&S world — retail-agent emails, ACORD
            forms, SOVs, loss runs, financials, carrier quote/declination emails, bind confirmations
            — and turns them into a consistent, cited data model that every downstream workflow can
            trust.
          </p>
          <div className="mt-4 grid gap-3">
            <MiniStat label="Documents processed / mo" value="47,820" />
            <MiniStat label="Median extraction latency" value="18s" />
            <MiniStat label="Field-level confidence ≥ 95%" value="94.2%" />
            <MiniStat label="Human corrections applied" value="1.8% of fields" />
          </div>
        </Panel>

        <Panel title="Capabilities">
          <ul className="grid gap-3 sm:grid-cols-2">
            {extractionCaps.map((c) => (
              <li key={c.title} className="rounded-xl border border-border p-4">
                <div className="flex items-start justify-between gap-3">
                  <div className="font-medium">{c.title}</div>
                  <span className="rounded-full bg-secondary px-2 py-0.5 text-[10px] font-mono">
                    {c.metric}
                  </span>
                </div>
                <p className="mt-1 text-[12px] text-muted-foreground">{c.desc}</p>
              </li>
            ))}
          </ul>
        </Panel>
      </div>

      <div className="mt-5">
        <Panel title="Reused by">
          <div className="flex flex-wrap gap-2">
            {[
              "Market Matching",
              "Package Assembly",
              "Agent Copilot",
              "Quote Comparison",
              "Binder & Issuance",
              "Endorsement Processing",
              "Renewal Remarketing",
              "Diligent Search",
            ].map((w) => (
              <span
                key={w}
                className="rounded-full border border-border bg-secondary px-3 py-1 text-xs"
              >
                {w}
              </span>
            ))}
          </div>
        </Panel>
      </div>
    </div>
  );
}

function MiniStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between rounded-lg border border-border p-3">
      <span className="text-xs text-muted-foreground">{label}</span>
      <span className="font-serif text-lg">{value}</span>
    </div>
  );
}

export function MatchingRankingCore() {
  return (
    <div className="mx-auto max-w-[1400px] animate-in fade-in-0 duration-500">
      <PageHeader
        eyebrow="Foundation · Shared platform capability"
        title="Matching/Ranking Core"
        description="The carrier-panel ranking engine, appetite-profile schema, and audit spine every Coverline wholesale/E&S workflow shares."
        actions={
          <span className="inline-flex items-center gap-1 rounded-full border border-border bg-background px-2 py-1 text-[11px]">
            <Gavel className="h-3 w-3 text-accent" />
            Used by every workflow
          </span>
        }
      />

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]">
        <Panel title="Capabilities">
          <ul className="grid gap-3 sm:grid-cols-2">
            {matchingCaps.map((c) => (
              <li key={c.title} className="rounded-xl border border-border p-4">
                <div className="flex items-center gap-2">
                  <ShieldCheck className="h-4 w-4 text-accent" />
                  <div className="font-medium">{c.title}</div>
                </div>
                <p className="mt-1 text-[12px] text-muted-foreground">{c.desc}</p>
              </li>
            ))}
          </ul>
        </Panel>
        <Panel title="Carrier appetite profiles" subtitle="Manually-curated · broker-tunable">
          <ul className="divide-y divide-border">
            {[
              {
                rule: "Kinsale — cold storage / refrigerated warehousing",
                version: "v3.2",
                eval: "2,148",
              },
              {
                rule: "James River — liquor liability, hospitality",
                version: "v2.8",
                eval: "1,984",
              },
              { rule: "Markel — contractor excess", version: "v1.6", eval: "2,110" },
              { rule: "Palomar Specialty — cold storage excluded", version: "v1.0", eval: "412" },
              { rule: "Ategrity — habitational / senior care", version: "v2.1", eval: "1,206" },
              {
                rule: "Berkley Specialty — senior care professional liab.",
                version: "v4.0",
                eval: "1,842",
              },
            ].map((r) => (
              <li key={r.rule} className="flex items-center gap-3 py-3 text-sm">
                <div className="flex-1">
                  <div className="font-medium">{r.rule}</div>
                  <div className="text-[11px] text-muted-foreground">
                    {r.eval} evaluations · {r.version}
                  </div>
                </div>
                <button className="rounded-md border border-border px-2 py-1 text-[11px] transition-colors hover:bg-secondary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2">
                  Edit
                </button>
              </li>
            ))}
          </ul>
        </Panel>
      </div>
    </div>
  );
}

/* ============================================================
   AI Assistant · full-page copilot
   ============================================================ */

interface AssistantTurn extends ChatMessage {
  citations?: { label: string; itemId: string }[];
}

function buildGreeting(pendingCounts: Record<string, number>): string {
  const entries = Object.entries(pendingCounts);
  if (entries.length === 0) {
    return "Your queue is clear right now — ask me about any submission, carrier, or workflow and I'll pull the real data.";
  }
  const parts = entries.map(([label, count]) => `${count} in ${label}`);
  return `You have items awaiting review — ${parts.join(", ")}. What would you like to work on?`;
}

function buildSuggestedPrompts(recent: { workflow: string; ref: string }[]): string[] {
  if (recent.length === 0) {
    return [
      "What's pending across my pipeline right now?",
      "Which workflows have items awaiting review?",
    ];
  }
  return recent.map((r) => `Summarize ${r.ref} in ${r.workflow} and tell me what's next`);
}

export function AssistantPage() {
  const [input, setInput] = useState("");
  const [turns, setTurns] = useState<AssistantTurn[]>([]);

  const overviewQuery = useQuery({
    queryKey: ["assistant-overview"],
    queryFn: getAssistantOverview,
  });

  const chatMutation = useMutation({
    mutationFn: (vars: { message: string; history: ChatMessage[] }) =>
      askAssistant(vars.message, vars.history),
    onError: (err) => {
      toast.error(err instanceof Error ? err.message : "The assistant couldn't answer that.");
    },
  });

  function send(text: string) {
    const message = text.trim();
    if (!message || chatMutation.isPending) return;
    const history: ChatMessage[] = turns.map(({ role, content }) => ({ role, content }));
    setTurns((prev) => [...prev, { role: "user", content: message }]);
    setInput("");
    chatMutation.mutate(
      { message, history },
      {
        onSuccess: (res) => {
          setTurns((prev) => [
            ...prev,
            { role: "assistant", content: res.text, citations: res.citations },
          ]);
        },
      },
    );
  }

  const pendingCounts = overviewQuery.data?.pendingCounts ?? {};
  const recent = overviewQuery.data?.recent ?? [];
  const suggested = buildSuggestedPrompts(recent);

  return (
    <div className="mx-auto max-w-[1200px] animate-in fade-in-0 duration-500">
      <PageHeader
        eyebrow="Global AI"
        title="Coverline AI Assistant"
        description="One assistant with full context on your placement book — every submission, quote, and decision cited to the source."
      />
      <div className="grid gap-5 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <Panel className="min-h-[520px]">
          <div className="space-y-4 text-sm">
            <div className="rounded-xl border border-border bg-secondary/40 p-4">
              <div className="mb-1 flex items-center gap-2 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
                <Sparkles className="h-3 w-3 text-accent" /> Coverline AI
              </div>
              <p>
                {overviewQuery.isLoading ? "Loading your pipeline…" : buildGreeting(pendingCounts)}
              </p>
            </div>

            {turns.map((t, i) =>
              t.role === "user" ? (
                <div key={i} className="flex justify-end">
                  <div className="max-w-[75%] rounded-xl border border-accent/25 bg-accent/5 p-3">
                    {t.content}
                  </div>
                </div>
              ) : (
                <div key={i} className="rounded-xl border border-border bg-secondary/40 p-4">
                  <div className="mb-1 flex items-center gap-2 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
                    <Sparkles className="h-3 w-3 text-accent" /> Coverline AI
                  </div>
                  <p className="whitespace-pre-wrap">{t.content}</p>
                  {t.citations && t.citations.length > 0 && (
                    <div className="mt-3 text-[10px] text-muted-foreground">
                      Cited: {t.citations.map((c) => c.label).join(" · ")}
                    </div>
                  )}
                </div>
              ),
            )}

            {chatMutation.isPending && (
              <div className="flex items-center gap-2 rounded-xl border border-border bg-secondary/40 p-4 text-muted-foreground">
                <Loader2 className="h-3.5 w-3.5 animate-spin" /> Thinking…
              </div>
            )}
          </div>
          <div className="mt-6 rounded-xl border border-border p-2 transition-[box-shadow] focus-within:ring-2 focus-within:ring-ring">
            <textarea
              rows={3}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  send(input);
                }
              }}
              placeholder="Ask about a submission, carrier panel, retail agent, or the pipeline…"
              className="w-full resize-none bg-transparent p-2 text-sm outline-none"
              disabled={chatMutation.isPending}
            />
            <div className="flex items-center gap-2 border-t border-border pt-2">
              <div className="ml-auto">
                <button
                  onClick={() => send(input)}
                  disabled={chatMutation.isPending || !input.trim()}
                  className="inline-flex items-center gap-2 rounded-md bg-foreground px-3 py-1.5 text-sm text-background transition active:scale-[0.98] hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50"
                >
                  Send <Send className="h-3.5 w-3.5" />
                </button>
              </div>
            </div>
          </div>
        </Panel>

        <Panel title="Suggested prompts">
          <ul className="space-y-2">
            {suggested.map((s) => (
              <li key={s}>
                <button
                  onClick={() => send(s)}
                  disabled={chatMutation.isPending}
                  className="group flex w-full items-start gap-2 rounded-lg border border-border p-3 text-left text-sm transition-colors hover:border-foreground/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50"
                >
                  <Sparkles className="mt-0.5 h-3.5 w-3.5 shrink-0 text-accent" />
                  <span className="flex-1">{s}</span>
                  <ArrowRight className="h-3.5 w-3.5 shrink-0 opacity-0 transition group-hover:opacity-100" />
                </button>
              </li>
            ))}
          </ul>
        </Panel>
      </div>
    </div>
  );
}

/* ============================================================
   Analytics
   ============================================================ */

const ANALYTICS_FUNNEL = [
  { stage: "Submissions", count: 274 },
  { stage: "Matched ≥1 market", count: 241 },
  { stage: "Packaged", count: 198 },
  { stage: "Quoted", count: 156 },
  { stage: "Bound", count: 104 },
];

const CLASS_MIX: [string, number][] = [
  ["Habitational", 26],
  ["Contractors / excess", 21],
  ["Hospitality / liquor liab.", 17],
  ["Vacant property", 12],
  ["Environmental", 10],
  ["Other E&S", 14],
];

const ANALYTICS_PERIODS = ["Trailing 30 days", "Trailing 90 days", "Trailing 12 months", "YTD"];

const LOW_VOLUME_NOTE =
  "Low-volume annotation: cuts below 10 submissions/mo are flagged, not silently averaged in — same discipline as Pipeline & Carrier Reporting.";

function analyticsCompleteness(rows: typeof pipelineCompleteness) {
  return Math.round(rows.reduce((sum, r) => sum + r.completePct, 0) / rows.length);
}

function FilterSelect({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: string[];
}) {
  return (
    <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
      {label}
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="rounded-md border border-border bg-background px-2 py-1 text-xs text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
      >
        {options.map((o) => (
          <option key={o} value={o}>
            {o}
          </option>
        ))}
      </select>
    </label>
  );
}

export function AnalyticsPage() {
  const [period, setPeriod] = useState(ANALYTICS_PERIODS[0]);
  const [carrierFilter, setCarrierFilter] = useState("All carriers");
  const [stateFilter, setStateFilter] = useState("All states");
  const [classFilter, setClassFilter] = useState("All classes");

  const overall = analyticsCompleteness(pipelineCompleteness);
  const worst = [...pipelineCompleteness]
    .filter((w) => w.gap)
    .sort((a, b) => a.completePct - b.completePct)[0];

  const filteredCarriers =
    carrierFilter === "All carriers"
      ? carrierPerformance
      : carrierPerformance.filter((c) => c.carrier === carrierFilter);
  const filteredStates =
    stateFilter === "All states" ? stateMix : stateMix.filter((s) => s.state === stateFilter);
  const filteredClasses =
    classFilter === "All classes" ? CLASS_MIX : CLASS_MIX.filter(([n]) => n === classFilter);

  const funnelMax = ANALYTICS_FUNNEL[0].count;
  const carrierPremiumMax = Math.max(
    ...carrierPerformance.map((c) => parseFloat(c.premium.replace(/[^0-9.]/g, ""))),
  );
  const stateMax = Math.max(...stateMix.map((s) => s.premium));

  return (
    <div className="mx-auto max-w-[1400px] animate-in fade-in-0 duration-500">
      <PageHeader
        eyebrow="Analytics"
        title="Book analytics"
        description="Real-time cuts across premium, hit ratio, placement cycle, carrier mix, and geography."
        actions={
          <button className="inline-flex items-center gap-2 rounded-lg border border-border bg-background px-3 py-1.5 text-sm transition-colors hover:bg-secondary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2">
            <Download className="h-4 w-4" />
            Export
          </button>
        }
      />

      <div className="mb-5 flex flex-wrap items-center gap-3 rounded-xl border border-border bg-secondary/40 p-4 text-sm">
        <Tabs tabs={ANALYTICS_PERIODS} value={period} onChange={setPeriod} />
        <FilterSelect
          label="Carrier"
          value={carrierFilter}
          onChange={setCarrierFilter}
          options={["All carriers", ...carrierPerformance.map((c) => c.carrier)]}
        />
        <FilterSelect
          label="State"
          value={stateFilter}
          onChange={setStateFilter}
          options={["All states", ...stateMix.map((s) => s.state)]}
        />
        <FilterSelect
          label="Class"
          value={classFilter}
          onChange={setClassFilter}
          options={["All classes", ...CLASS_MIX.map(([n]) => n)]}
        />
        <div className="ml-auto text-[11px] text-muted-foreground">
          Illustrative sample data — filters narrow the cuts below; {period} is a label only (no
          per-period dataset to recompute from).
        </div>
      </div>

      <div
        className={`mb-5 flex items-start gap-2 rounded-xl border-2 p-3 text-sm ${overall === 100 ? "border-success/40 bg-success/5" : "border-warn/40 bg-warn/5"}`}
      >
        {overall === 100 ? (
          <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-success" />
        ) : (
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-warn" />
        )}
        <div className="flex flex-wrap items-center gap-2">
          <b>Data completeness</b>
          <Chip tone={overall === 100 ? "success" : "warn"}>{overall}%</Chip>
          <span>across all six source workflows.</span>
          {worst && (
            <span>
              {worst.workflow} has the largest gap — {worst.gap}.
            </span>
          )}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        {[
          { l: "Bound YTD", v: "$48.2M" },
          { l: "Hit ratio", v: "38.4%" },
          { l: "Placement cycle", v: "6.4d" },
          { l: "Retention", v: "92%" },
          { l: "PIF", v: "2,148" },
        ].map((k) => (
          <div key={k.l} className="rounded-xl border border-border bg-background p-4">
            <div className="text-[11px] uppercase tracking-wider text-muted-foreground">{k.l}</div>
            <div className="mt-2 font-serif text-3xl leading-none">{k.v}</div>
          </div>
        ))}
      </div>

      <div className="mt-6 grid gap-5 lg:grid-cols-3">
        <Panel title="Placement cycle trend · rolling 12 mo" className="lg:col-span-2">
          <svg viewBox="0 0 600 220" className="h-56 w-full">
            <polyline
              fill="none"
              stroke="var(--color-accent)"
              strokeWidth="2.5"
              points="0,90 50,92 100,85 150,88 200,78 250,72 300,68 350,65 400,60 450,55 500,52 550,48 600,45"
            />
            <line x1="0" y1="200" x2="600" y2="200" stroke="var(--color-border)" />
            <line
              x1="0"
              y1="50"
              x2="600"
              y2="50"
              stroke="var(--color-border)"
              strokeDasharray="4 4"
            />
            <text x="4" y="48" fontSize="10" fill="var(--color-muted-foreground)">
              Target 2–3 days
            </text>
          </svg>
          <div className="mt-2 text-[11px] text-muted-foreground">
            Raw {placementCycle.raw}d · excludes {placementCycle.avgBrokerAgentDelay}d avg
            broker/agent delay · target {placementCycle.target}.
          </div>
        </Panel>
        <Panel title="Class mix">
          <ul className="space-y-2 text-sm">
            {filteredClasses.map(([n, v]) => (
              <li key={n} className="flex items-center gap-3">
                <div className="w-32 text-xs">{n}</div>
                <div className="h-2 flex-1 overflow-hidden rounded-full bg-secondary">
                  <div
                    className="h-full bg-foreground transition-[width] duration-700 ease-out"
                    style={{ width: `${v * 2.5}%` }}
                  />
                </div>
                <div className="w-8 text-right font-mono text-xs">{v}%</div>
              </li>
            ))}
          </ul>
        </Panel>
      </div>

      <div className="mt-6 grid gap-5 lg:grid-cols-2">
        <Panel title="Carrier mix" subtitle="Premium share by carrier">
          <div className="space-y-2">
            {filteredCarriers.map((c) => {
              const value = parseFloat(c.premium.replace(/[^0-9.]/g, ""));
              return (
                <div key={c.carrier} className="flex items-center gap-3 text-xs">
                  <div className="w-36 truncate">{c.carrier}</div>
                  <div className="h-2 flex-1 overflow-hidden rounded-full bg-secondary">
                    <div
                      className="h-full bg-accent transition-[width] duration-700 ease-out"
                      style={{ width: `${(value / carrierPremiumMax) * 100}%` }}
                    />
                  </div>
                  <div className="w-14 text-right font-mono">{c.premium}</div>
                </div>
              );
            })}
          </div>
          <div className="mt-3 text-[10px] text-muted-foreground">{LOW_VOLUME_NOTE}</div>
        </Panel>
        <Panel title="Geography" subtitle="Premium by state · $M">
          <div className="space-y-2">
            {filteredStates.map((s) => (
              <div key={s.state} className="flex items-center gap-3 text-xs">
                <div className="w-8">{s.state}</div>
                <div className="h-2 flex-1 overflow-hidden rounded-full bg-secondary">
                  <div
                    className="h-full bg-foreground transition-[width] duration-700 ease-out"
                    style={{ width: `${(s.premium / stateMax) * 100}%` }}
                  />
                </div>
                <div className="w-12 text-right font-mono">${s.premium.toFixed(1)}M</div>
              </div>
            ))}
          </div>
          <div className="mt-3 text-[10px] text-muted-foreground">{LOW_VOLUME_NOTE}</div>
        </Panel>
      </div>

      <div className="mt-6 grid gap-5 lg:grid-cols-3">
        <Panel
          title="Submission → bound funnel"
          className="lg:col-span-2"
          subtitle={`${period} · 104 of 274 submissions bound (38.0%)`}
        >
          <div className="space-y-3 pt-2">
            {ANALYTICS_FUNNEL.map((f) => (
              <div key={f.stage} className="flex items-center gap-3 text-sm">
                <div className="w-40 shrink-0 text-xs text-muted-foreground">{f.stage}</div>
                <div className="h-6 flex-1 overflow-hidden rounded-md bg-secondary">
                  <div
                    className="flex h-full items-center justify-end bg-accent px-2 text-[10px] font-mono text-accent-foreground transition-[width] duration-700 ease-out"
                    style={{ width: `${(f.count / funnelMax) * 100}%` }}
                  >
                    {f.count}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </Panel>
        <Panel title="Remarketing value">
          <div className="space-y-3 text-sm">
            <div className="rounded-lg border border-border p-3">
              <div className="text-[11px] uppercase tracking-wider text-muted-foreground">
                Accounts remarketed, {period}
              </div>
              <div className="mt-1 font-serif text-2xl">18</div>
            </div>
            <div className="rounded-lg border border-border p-3">
              <div className="text-[11px] uppercase tracking-wider text-muted-foreground">
                Premium improvement captured
              </div>
              <div className="mt-1 font-serif text-2xl">$212k</div>
              <div className="text-[11px] text-muted-foreground">
                vs. incumbent's initial renewal indication
              </div>
            </div>
            <div className="rounded-lg border border-border p-3">
              <div className="text-[11px] uppercase tracking-wider text-muted-foreground">
                Retention on remarketed accounts
              </div>
              <div className="mt-1 font-serif text-2xl">78%</div>
              <div className="text-[11px] text-muted-foreground">
                Moved to a new market but stayed on the book
              </div>
            </div>
          </div>
        </Panel>
      </div>

      <div className="mt-6 grid gap-5 lg:grid-cols-2">
        <Panel title="Carrier hit-rate comparison">
          <table className="w-full text-sm">
            <thead className="text-[11px] uppercase tracking-wider text-muted-foreground">
              <tr>
                <th className="py-2 text-left">Carrier</th>
                <th className="py-2 text-right">Submissions</th>
                <th className="py-2 text-right">Quoted</th>
                <th className="py-2 text-right">Bound</th>
                <th className="py-2 text-right">Hit ratio</th>
                <th className="py-2 text-right">Avg turnaround</th>
                <th className="py-2 text-right">Premium</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {filteredCarriers.map((c) => (
                <tr key={c.carrier} className="transition-colors hover:bg-secondary/40">
                  <td className="py-2.5 font-medium">{c.carrier}</td>
                  <td className="py-2.5 text-right tabular-nums">{c.submissions}</td>
                  <td className="py-2.5 text-right tabular-nums">{c.quoted}</td>
                  <td className="py-2.5 text-right tabular-nums">{c.bound}</td>
                  <td className="py-2.5 text-right font-mono">{c.hitRate}</td>
                  <td className="py-2.5 text-right font-mono">{c.avgTurnaround}</td>
                  <td className="py-2.5 text-right font-mono">{c.premium}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>
        <Panel title="Agency performance">
          <table className="w-full text-sm">
            <thead className="text-[11px] uppercase tracking-wider text-muted-foreground">
              <tr>
                <th className="py-2 text-left">Agency</th>
                <th className="py-2 text-right">Submissions</th>
                <th className="py-2 text-right">Packaged</th>
                <th className="py-2 text-right">Bound</th>
                <th className="py-2 text-right">Hit ratio</th>
                <th className="py-2 text-right">Avg response time</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {retailAgents.map((a) => (
                <tr key={a.agency} className="transition-colors hover:bg-secondary/40">
                  <td className="py-2.5 font-medium">{a.agency}</td>
                  <td className="py-2.5 text-right tabular-nums">{a.submissions}</td>
                  <td className="py-2.5 text-right tabular-nums">{a.packaged}</td>
                  <td className="py-2.5 text-right tabular-nums">{a.bound}</td>
                  <td className="py-2.5 text-right font-mono">{a.hitRate}</td>
                  <td className="py-2.5 text-right font-mono">{a.avgResponseTime}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>
      </div>
    </div>
  );
}

/* ============================================================
   Settings
   ============================================================ */

export function SettingsPage() {
  return (
    <div className="mx-auto max-w-[900px] animate-in fade-in-0 duration-500">
      <PageHeader eyebrow="Settings" title="Workspace settings" />
      <div className="space-y-5">
        <Panel title="Organization">
          <div className="grid gap-3 text-sm md:grid-cols-2">
            <Field label="Organization name" value="Meridian Specialty Wholesale" />
            <Field label="Surplus lines license #" value="SL-55648" />
            <Field label="Jurisdictions" value="FL · TX · GA · NC · CO · VA · PA · NY · CA · LA" />
            <Field label="Carrier panel" value="42 markets across E&S / specialty lines" />
          </div>
        </Panel>
        <IntegrationsPanel />
        <Panel title="Team">
          <ul className="divide-y divide-border text-sm">
            {[
              ["Sam Delgado", "Sr. Wholesale Broker", "Admin"],
              ["Marcus Webb", "Wholesale Broker", "Editor"],
              ["Elena Cho", "Junior Broker", "Editor"],
              ["Renee Park", "Compliance", "Viewer"],
            ].map((r) => (
              <li key={r[0]} className="flex items-center gap-3 py-3">
                <div className="grid h-8 w-8 place-items-center rounded-full bg-foreground text-xs text-background">
                  {r[0]
                    .split(" ")
                    .map((n) => n[0])
                    .join("")}
                </div>
                <div className="flex-1">
                  <div className="font-medium">{r[0]}</div>
                  <div className="text-[11px] text-muted-foreground">{r[1]}</div>
                </div>
                <span className="rounded-full border border-border bg-secondary px-2 py-0.5 text-[10px]">
                  {r[2]}
                </span>
              </li>
            ))}
          </ul>
        </Panel>
        <Panel title="Notifications">
          <div className="space-y-2 text-sm">
            {[
              "New submissions from priority retail agents",
              "Remarket reviews due in 30 days",
              "AI recommendation confidence below 80%",
              "Diligent search evidence missing",
              "Override submitted",
            ].map((n) => (
              <label
                key={n}
                className="flex items-center justify-between rounded-lg border border-border p-3"
              >
                <span>{n}</span>
                <input type="checkbox" defaultChecked className="accent-accent" />
              </label>
            ))}
          </div>
        </Panel>
      </div>
    </div>
  );
}

interface IntegrationDef {
  provider: string;
  label: string;
  description: string;
  icon: LucideIcon;
}

// Gmail is the only one actually read from today. Sheets/Drive/Calendar/
// Slack/QuickBooks are real connect/disconnect targets (real Nango OAuth,
// real stored connection status) but nothing in the app reads or writes
// through them yet — see docs/CONNECTORS_NANGO.md.
const INTEGRATIONS: IntegrationDef[] = [
  {
    provider: GOOGLE_MAIL_PROVIDER,
    label: "Gmail",
    description: "Real inbox access for Submission Market Matching",
    icon: Mail,
  },
  {
    provider: GOOGLE_SHEET_PROVIDER,
    label: "Google Sheets",
    description: "Connect/disconnect only for now — no data is read or written yet",
    icon: FileSpreadsheet,
  },
  {
    provider: GOOGLE_DRIVE_PROVIDER,
    label: "Google Drive",
    description: "Connect/disconnect only for now — no data is read or written yet",
    icon: HardDrive,
  },
  {
    provider: GOOGLE_CALENDAR_PROVIDER,
    label: "Google Calendar",
    description: "Connect/disconnect only for now — no data is read or written yet",
    icon: Calendar,
  },
  {
    provider: SLACK_PROVIDER,
    label: "Slack",
    description: "Connect/disconnect only for now — no data is read or written yet",
    icon: MessageSquare,
  },
  {
    provider: QUICKBOOKS_PROVIDER,
    label: "QuickBooks",
    description: "Connect/disconnect only for now — no data is read or written yet",
    icon: Receipt,
  },
];

/** Real "Connect" flow for any of the above — POST /api/core/integrations/connect-session
 * mints a Nango Connect UI session token scoped to one provider, the popup handles Google
 * OAuth, and on success we save the resulting connectionId via
 * POST /api/core/integrations/connections. See docs/CONNECTORS_NANGO.md in the backend repo. */
function IntegrationsPanel() {
  return (
    <Panel title="Integrations">
      <div className="space-y-3">
        {INTEGRATIONS.map((def) => (
          <IntegrationRow key={def.provider} {...def} />
        ))}
      </div>
    </Panel>
  );
}

function IntegrationRow({ provider, label, description, icon: Icon }: IntegrationDef) {
  const queryClient = useQueryClient();
  const integrationsQuery = useQuery({
    queryKey: ["integrations"],
    queryFn: listIntegrations,
  });
  const connected =
    (integrationsQuery.data?.find((i) => i.provider === provider)?.status ?? "disconnected") ===
    "connected";

  const connectMutation = useMutation({
    mutationFn: async () => {
      const session = await createConnectSession(provider);
      await new Promise<void>((resolve, reject) => {
        const nango = new Nango({});
        const connectUI = nango.openConnectUI({
          sessionToken: session.session_token,
          onEvent: (event) => {
            if (event.type === "connect") {
              confirmConnection(event.payload.providerConfigKey, event.payload.connectionId)
                .then(() => resolve())
                .catch((err: unknown) =>
                  reject(err instanceof Error ? err : new Error("Failed to save connection")),
                );
            } else if (event.type === "close") {
              resolve();
            } else if (event.type === "error") {
              reject(new Error(event.payload.errorMessage));
            }
          },
        });
        connectUI.open();
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["integrations"] });
      toast.success(`${label} connected`);
    },
    onError: (err: unknown) =>
      toast.error(err instanceof Error ? err.message : `Failed to connect ${label}`),
  });

  const disconnectMutation = useMutation({
    mutationFn: () => disconnectIntegration(provider),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["integrations"] });
      toast.success(`${label} disconnected`);
    },
    onError: (err: unknown) =>
      toast.error(err instanceof Error ? err.message : `Failed to disconnect ${label}`),
  });

  return (
    <div className="flex items-center justify-between rounded-lg border border-border p-3 text-sm">
      <div className="flex items-center gap-3">
        <Icon className="h-4 w-4 text-muted-foreground" />
        <div>
          <div className="font-medium">{label}</div>
          <div className="text-[11px] text-muted-foreground">{description}</div>
        </div>
      </div>
      <div className="flex items-center gap-2">
        <span
          className={`rounded-full border px-2 py-0.5 text-[10px] ${
            connected
              ? "border-emerald-600/30 bg-emerald-600/10 text-emerald-700"
              : "border-border bg-secondary text-muted-foreground"
          }`}
        >
          {connected ? "Connected" : "Not connected"}
        </span>
        {connected ? (
          <Button
            variant="secondary"
            disabled={disconnectMutation.isPending}
            onClick={() => disconnectMutation.mutate()}
          >
            Disconnect
          </Button>
        ) : (
          <Button
            variant="primary"
            disabled={connectMutation.isPending}
            onClick={() => connectMutation.mutate()}
          >
            Connect {label}
          </Button>
        )}
      </div>
    </div>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-border p-3">
      <div className="text-[11px] uppercase tracking-wider text-muted-foreground">{label}</div>
      <div className="mt-1 text-sm">{value}</div>
    </div>
  );
}
