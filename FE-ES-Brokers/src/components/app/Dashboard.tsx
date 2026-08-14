import { Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowUpRight,
  Upload,
  RefreshCcw,
  FileSearch,
  Sparkles,
  Inbox,
  Package,
  GitCompare,
  FileCheck2,
  Info,
  ShieldCheck,
  type LucideIcon,
} from "lucide-react";
import { PageHeader } from "./AppShell";
import { getDashboardOverview, type DashboardOverview } from "@/lib/api/dashboard";
import type { ReactNode } from "react";

// Real workflow label (from the backend, WORKFLOW_LABELS) -> real route slug.
const WORKFLOW_ROUTES: Record<string, string> = {
  "Market Matching": "submission-matching",
  "Package Assembly": "package-assembly",
  "Agent Communication": "agent-copilot",
  "Quote Comparison": "quote-comparison",
  "Binder Issuance": "binder-issuance",
  "Endorsement Processing": "endorsement-processing",
  "Renewal Remarketing": "renewal-remarketing",
  "Diligent Search": "diligent-search",
  "Carrier Appetite Intelligence": "appetite-intelligence",
  "Pipeline Reporting": "pipeline-reporting",
};

const WORKFLOW_TILES: { label: string; icon: LucideIcon }[] = [
  { label: "Market Matching", icon: Inbox },
  { label: "Package Assembly", icon: Package },
  { label: "Quote Comparison", icon: GitCompare },
  { label: "Binder Issuance", icon: FileCheck2 },
  { label: "Renewal Remarketing", icon: RefreshCcw },
];

function fmtMoney(n: number): string {
  if (n >= 1_000_000) return `$${(n / 1_000_000).toFixed(2)}M`;
  if (n >= 1_000) return `$${(n / 1_000).toFixed(1)}k`;
  return `$${n.toFixed(0)}`;
}

function fmtWhen(iso: string): string {
  const d = new Date(iso);
  const diffMs = Date.now() - d.getTime();
  const mins = Math.round(diffMs / 60_000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function prettyLevel(level: string | null): string {
  if (!level) return "—";
  return level
    .split("_")
    .map((w) => w[0] + w.slice(1).toLowerCase())
    .join(" ");
}

export function Dashboard() {
  const { data, isLoading } = useQuery<DashboardOverview>({
    queryKey: ["dashboard-overview"],
    queryFn: getDashboardOverview,
    refetchInterval: 60_000,
  });

  const wc = data?.workflowCounts ?? {};
  const hitRatio = data?.funnel.overallConversionPct;
  const gaps = data?.funnel.gaps ?? [];
  const alerts = data?.diligentSearchAlerts ?? [];

  return (
    <div className="mx-auto max-w-[1400px] animate-in fade-in-0 duration-500">
      <PageHeader
        eyebrow={new Date().toLocaleDateString(undefined, {
          weekday: "long",
          month: "long",
          day: "numeric",
          year: "numeric",
        })}
        title="Good morning."
        description="Real, live activity across your placement book — every number below comes straight from your workflows, updated on every load."
        actions={
          <>
            <QuickAction
              icon={Upload}
              label="Upload submission"
              to="/app/workflows/submission-matching"
            />
            <QuickAction
              icon={RefreshCcw}
              label="Start remarket review"
              to="/app/workflows/renewal-remarketing"
            />
            <QuickAction
              icon={FileSearch}
              label="Diligent search queue"
              to="/app/workflows/diligent-search"
            />
            <QuickAction icon={Sparkles} label="Open AI Assistant" to="/app/assistant" primary />
          </>
        }
      />

      {/* KPI grid — every value real */}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
        <Kpi
          label="Submissions today"
          value={isLoading ? "…" : String(data?.submissionsToday ?? 0)}
          sub="Market Matching"
          to="/app/workflows/submission-matching"
        />
        <Kpi
          label="Remarket reviews pending"
          value={isLoading ? "…" : String(data?.remarketPending ?? 0)}
          to="/app/workflows/renewal-remarketing"
        />
        <Kpi
          label="Mid-term changes waiting"
          value={isLoading ? "…" : String(data?.endorsementPending ?? 0)}
          to="/app/workflows/endorsement-processing"
        />
        <Kpi
          label="Quotes received today"
          value={isLoading ? "…" : String(data?.quotesReceivedToday ?? 0)}
          to="/app/workflows/quote-comparison"
        />
        <Kpi
          label="Binders confirmed"
          value={isLoading ? "…" : String(data?.bindersConfirmed ?? 0)}
          sub={
            data && data.boundPremiumMtd > 0
              ? `${fmtMoney(data.boundPremiumMtd)} this month`
              : undefined
          }
          to="/app/workflows/binder-issuance"
        />
        <Kpi
          label="Hit ratio"
          value={hitRatio != null ? `${hitRatio}%` : "insufficient data"}
          sub="submissions → bound, all-time"
          to="/app/workflows/pipeline-reporting"
        />
      </div>

      <div className="mt-8 grid gap-6 lg:grid-cols-3">
        <Card
          className="lg:col-span-2"
          title="Submission pipeline"
          subtitle="Submissions received vs. bound — last 7 days, real counts"
          href="/app/workflows/pipeline-reporting"
        >
          <PipelineChart data={data?.dailyPipeline ?? []} />
        </Card>

        <Card
          title="Carrier performance"
          subtitle="Quote rate / bind rate — real, from Pipeline Reporting"
          href="/app/workflows/pipeline-reporting"
        >
          {(data?.carrierPerformance ?? []).length === 0 ? (
            <EmptyNote text="No carrier activity recorded yet." />
          ) : (
            <ul className="space-y-3 text-sm">
              {(data?.carrierPerformance ?? []).slice(0, 5).map((c) => (
                <li key={c.carrierName} className="flex items-center justify-between gap-3">
                  <div className="min-w-0">
                    <div className="truncate font-medium">{c.carrierName}</div>
                    <div className="text-[11px] text-muted-foreground">
                      {c.submissionsApproached} approached
                      {c.lowVolumeFlag && " · small sample"}
                    </div>
                  </div>
                  <div className="text-right font-mono text-xs">
                    <div>{c.overallHitRate}% hit</div>
                    <div className="text-[10px] text-muted-foreground">{c.bindRate}% bind rate</div>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-3">
        <Card
          className="lg:col-span-2"
          title="Recent activity"
          subtitle="Every real action, across all 10 workflows"
          href="/app/assistant"
        >
          <div className="overflow-hidden rounded-lg border border-border">
            <table className="w-full text-sm">
              <thead className="bg-secondary/60 text-[11px] uppercase tracking-wider text-muted-foreground">
                <tr>
                  <Th>Workflow</Th>
                  <Th>Reference</Th>
                  <Th>Status</Th>
                  <Th>When</Th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {(data?.recentActivity ?? []).length === 0 && (
                  <tr>
                    <Td className="text-muted-foreground" colSpan={4}>
                      No activity yet — run a workflow to see it appear here.
                    </Td>
                  </tr>
                )}
                {(data?.recentActivity ?? []).map((a, i) => (
                  <tr key={i} className="transition hover:bg-secondary/40">
                    <Td className="font-medium">{a.workflow}</Td>
                    <Td className="truncate text-muted-foreground">{a.ref}</Td>
                    <Td>
                      <StatusPill status={a.status} />
                    </Td>
                    <Td className="whitespace-nowrap text-[11px] text-muted-foreground">
                      {fmtWhen(a.createdAt)}
                    </Td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>

        <Card
          title="Remarket pipeline"
          subtitle="Real trigger decisions"
          href="/app/workflows/renewal-remarketing"
        >
          {(data?.remarketPipeline ?? []).length === 0 ? (
            <EmptyNote text="No renewals under review yet." />
          ) : (
            <ul className="divide-y divide-border text-sm">
              {(data?.remarketPipeline ?? []).map((r, i) => (
                <li key={i} className="py-3">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="font-medium">{r.namedInsured ?? "—"}</div>
                      <div className="text-[11px] text-muted-foreground">
                        Incumbent {r.incumbentCarrierName || "—"}
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="text-[11px] text-accent">{prettyLevel(r.triggerLevel)}</div>
                      <div className="text-[10px] text-muted-foreground">
                        {fmtWhen(r.createdAt)}
                      </div>
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      <div className="mt-6">
        <Card title="Alerts" subtitle="Real diligent-search and data-completeness flags">
          {alerts.length === 0 && gaps.length === 0 ? (
            <div className="flex items-start gap-3 rounded-lg border border-border bg-secondary/40 p-3 text-sm">
              <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-success" />
              <div>
                <div className="font-medium">No alerts right now</div>
                <div className="text-[11px] text-muted-foreground">
                  No pending diligent-search gaps and no funnel data gaps detected.
                </div>
              </div>
            </div>
          ) : (
            <ul className="space-y-3 text-sm">
              {alerts.map((a, i) => (
                <li
                  key={`ds-${i}`}
                  className="flex items-start gap-3 rounded-lg border border-border p-3"
                >
                  <FileSearch className="mt-0.5 h-4 w-4 shrink-0 text-warn" />
                  <div>
                    <div className="font-medium">Diligent search evidence needed</div>
                    <div className="text-[11px] text-muted-foreground">
                      {a.submissionId} · {a.onFile ?? 0} on file — {a.note}
                    </div>
                  </div>
                </li>
              ))}
              {gaps.map((g, i) => (
                <li
                  key={`gap-${i}`}
                  className="flex items-start gap-3 rounded-lg border border-border p-3"
                >
                  <Info className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
                  <div>
                    <div className="font-medium">Data gap: {g.stage}</div>
                    <div className="text-[11px] text-muted-foreground">{g.reason}</div>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      <div className="mt-8 grid gap-6 md:grid-cols-2 lg:grid-cols-5">
        {WORKFLOW_TILES.map((t) => (
          <WorkflowTile
            key={t.label}
            to={`/app/workflows/${WORKFLOW_ROUTES[t.label]}`}
            icon={t.icon}
            title={t.label}
            count={`${wc[t.label] ?? 0} pending`}
          />
        ))}
      </div>
    </div>
  );
}

function QuickAction({
  icon: Icon,
  label,
  to,
  primary,
}: {
  icon: LucideIcon;
  label: string;
  to: string;
  primary?: boolean;
}) {
  return (
    <Link
      to={to}
      className={
        primary
          ? "inline-flex items-center gap-2 rounded-lg bg-foreground px-3.5 py-2 text-sm font-medium text-background transition active:scale-[0.98] hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
          : "inline-flex items-center gap-2 rounded-lg border border-border bg-background px-3.5 py-2 text-sm text-foreground transition active:scale-[0.98] hover:bg-secondary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
      }
    >
      <Icon className="h-4 w-4" />
      {label}
    </Link>
  );
}

function Kpi({
  label,
  value,
  sub,
  to,
}: {
  label: string;
  value: string;
  sub?: string;
  to: string;
}) {
  return (
    <Link
      to={to}
      className="group rounded-xl border border-border bg-background p-4 shadow-sm transition hover:border-foreground/40 hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
    >
      <div className="flex items-start justify-between">
        <div className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
          {label}
        </div>
        <ArrowUpRight className="h-3.5 w-3.5 text-muted-foreground transition group-hover:text-foreground" />
      </div>
      <div className="mt-3 font-serif text-3xl leading-none tracking-tight">{value}</div>
      {sub && <div className="mt-2 text-[11px] text-muted-foreground">{sub}</div>}
    </Link>
  );
}

function Card({
  title,
  subtitle,
  href,
  children,
  className = "",
}: {
  title: string;
  subtitle?: string;
  href?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section
      className={`rounded-2xl border border-border bg-background p-5 shadow-sm ${className}`}
    >
      <div className="mb-4 flex items-start justify-between gap-4">
        <div>
          <h3 className="font-serif text-lg leading-tight">{title}</h3>
          {subtitle && <p className="mt-0.5 text-[11px] text-muted-foreground">{subtitle}</p>}
        </div>
        {href && (
          <Link
            to={href}
            className="inline-flex items-center gap-1 rounded text-xs text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
          >
            Open <ArrowUpRight className="h-3 w-3" />
          </Link>
        )}
      </div>
      {children}
    </section>
  );
}

function Th({ children }: { children: ReactNode }) {
  return <th className="px-3 py-2 text-left font-medium">{children}</th>;
}
function Td({
  children,
  className = "",
  colSpan,
}: {
  children: ReactNode;
  className?: string;
  colSpan?: number;
}) {
  return (
    <td colSpan={colSpan} className={`px-3 py-3 align-top ${className}`}>
      {children}
    </td>
  );
}

function EmptyNote({ text }: { text: string }) {
  return <div className="py-6 text-center text-sm text-muted-foreground">{text}</div>;
}

function StatusPill({ status }: { status: string }) {
  const tone =
    status === "approved" || status === "issued" || status === "sent"
      ? "bg-success/10 text-success"
      : status === "escalated" || status === "overridden"
        ? "bg-warn/15 text-warn"
        : "bg-secondary text-muted-foreground";
  return (
    <span className={`rounded-full px-2 py-0.5 text-[10px] font-mono capitalize ${tone}`}>
      {status}
    </span>
  );
}

function PipelineChart({ data }: { data: { date: string; submissions: number; bound: number }[] }) {
  const max = Math.max(1, ...data.map((m) => Math.max(m.submissions, m.bound)));
  const totalSubs = data.reduce((sum, m) => sum + m.submissions, 0);
  const totalBound = data.reduce((sum, m) => sum + m.bound, 0);
  const conversion = totalSubs > 0 ? ((totalBound / totalSubs) * 100).toFixed(1) : null;
  return (
    <div>
      <div className="flex items-end gap-4 pt-2">
        {data.map((m) => (
          <div key={m.date} className="flex flex-1 flex-col items-center gap-2">
            <div className="relative flex h-40 w-full items-end justify-center gap-1">
              <div
                className="w-4 rounded-t bg-foreground/15 transition-[height] duration-700 ease-out"
                style={{ height: `${(m.submissions / max) * 100}%` }}
                title={`Submissions ${m.submissions}`}
              />
              <div
                className="w-4 rounded-t bg-accent transition-[height] duration-700 ease-out"
                style={{ height: `${(m.bound / max) * 100}%` }}
                title={`Bound ${m.bound}`}
              />
            </div>
            <div className="text-[11px] text-muted-foreground">
              {new Date(m.date).toLocaleDateString(undefined, { weekday: "short" })}
            </div>
          </div>
        ))}
      </div>
      <div className="mt-4 flex items-center gap-4 text-[11px] text-muted-foreground">
        <span className="inline-flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-sm bg-foreground/15" /> Submissions
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-sm bg-accent" /> Bound
        </span>
        {conversion && <span className="ml-auto">Conversion {conversion}% · trailing 7 days</span>}
      </div>
    </div>
  );
}

function WorkflowTile({
  to,
  icon: Icon,
  title,
  count,
}: {
  to: string;
  icon: LucideIcon;
  title: string;
  count: string;
}) {
  return (
    <Link
      to={to}
      className="group flex items-center gap-3 rounded-xl border border-border bg-background p-4 shadow-sm transition hover:border-foreground/40 hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
    >
      <div className="grid h-10 w-10 place-items-center rounded-lg bg-secondary transition-colors group-hover:bg-foreground group-hover:text-background">
        <Icon className="h-4 w-4" />
      </div>
      <div className="min-w-0">
        <div className="truncate text-sm font-medium">{title}</div>
        <div className="text-[11px] text-muted-foreground">{count}</div>
      </div>
      <ArrowUpRight className="ml-auto h-3.5 w-3.5 text-muted-foreground transition-colors group-hover:text-foreground" />
    </Link>
  );
}
