import { Link, Outlet, useLocation, useNavigate, useRouter } from "@tanstack/react-router";
import {
  LayoutDashboard,
  Inbox,
  Package,
  RefreshCcw,
  MessageSquare,
  FileEdit,
  GitCompare,
  FileCheck2,
  BarChart3,
  FileSearch,
  Radar,
  Sparkles,
  Scan,
  Gavel,
  LineChart,
  Settings,
  Search,
  Bell,
  ChevronRight,
  Command,
  X,
  Send,
  ArrowUpRight,
} from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { cn } from "@/lib/utils";
import { Toaster } from "@/components/ui/sonner";
import { ThemeToggle } from "@/components/ThemeToggle";
import { clearIdentity, getIdentity } from "@/lib/api/identity";

const workflows = [
  { slug: "submission-matching", label: "Submission Market Matching", icon: Inbox, badge: "12" },
  { slug: "package-assembly", label: "Package Assembly", icon: Package, badge: "4" },
  { slug: "agent-copilot", label: "Retail Agent Copilot", icon: MessageSquare },
  { slug: "quote-comparison", label: "Quote Comparison", icon: GitCompare },
  { slug: "binder-issuance", label: "Binder & Issuance", icon: FileCheck2, badge: "3" },
  { slug: "endorsement-processing", label: "Endorsement Processing", icon: FileEdit, badge: "4" },
  { slug: "renewal-remarketing", label: "Renewal Remarketing", icon: RefreshCcw, badge: "7" },
  { slug: "diligent-search", label: "Diligent Search", icon: FileSearch, badge: "2" },
  { slug: "appetite-intelligence", label: "Carrier Appetite Intel.", icon: Radar },
  { slug: "pipeline-reporting", label: "Pipeline & Carrier Reporting", icon: BarChart3 },
];

const foundation = [
  { slug: "extraction-core", label: "Extraction Core", icon: Scan },
  { slug: "matching-core", label: "Matching/Ranking Core", icon: Gavel },
];

const misc = [
  { to: "/app/assistant", label: "AI Assistant", icon: Sparkles },
  { to: "/app/analytics", label: "Analytics", icon: LineChart },
  { to: "/app/settings", label: "Settings", icon: Settings },
];

export function AppShell() {
  const loc = useLocation();
  const [copilotOpen, setCopilotOpen] = useState(false);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setCopilotOpen((v) => !v);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const crumbs = buildCrumbs(loc.pathname);

  return (
    <div className="min-h-screen bg-background text-foreground">
      <div className="flex min-h-screen">
        <Sidebar pathname={loc.pathname} />
        <div className="flex min-h-screen flex-1 flex-col">
          <TopBar crumbs={crumbs} onOpenCopilot={() => setCopilotOpen(true)} />
          <main className="flex-1 px-6 py-6 md:px-10 md:py-10">
            <Outlet />
          </main>
        </div>
      </div>
      <CopilotDrawer open={copilotOpen} onClose={() => setCopilotOpen(false)} />
      <Toaster position="bottom-right" />
      {!copilotOpen && (
        <button
          onClick={() => setCopilotOpen(true)}
          className="fixed bottom-6 right-6 z-40 inline-flex items-center gap-2 rounded-full bg-foreground px-4 py-3 text-sm font-medium text-background shadow-lg shadow-black/10 transition active:scale-[0.98] hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
        >
          <Sparkles className="h-4 w-4" />
          Ask Coverline AI
          <kbd className="ml-1 rounded bg-background/15 px-1.5 py-0.5 font-mono text-[10px]">
            ⌘K
          </kbd>
        </button>
      )}
    </div>
  );
}

function Sidebar({ pathname }: { pathname: string }) {
  return (
    <aside className="hidden w-72 shrink-0 border-r border-border bg-background lg:block">
      <div className="flex h-16 items-center gap-2 border-b border-border px-6">
        <Link to="/" className="font-serif text-xl leading-none">
          Coverline<span className="text-accent">.</span>
        </Link>
        <span className="ml-auto rounded-full border border-border bg-secondary px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
          Wholesale/E&S OS
        </span>
      </div>
      <div className="px-3 py-4">
        <NavItem to="/app" icon={LayoutDashboard} label="Dashboard" active={pathname === "/app"} />
        <SectionLabel>Workflows</SectionLabel>
        {workflows.map((w) => (
          <NavItem
            key={w.slug}
            to={`/app/workflows/${w.slug}`}
            icon={w.icon}
            label={w.label}
            badge={w.badge}
            active={pathname === `/app/workflows/${w.slug}`}
          />
        ))}
        <SectionLabel>Foundation</SectionLabel>
        {foundation.map((f) => (
          <NavItem
            key={f.slug}
            to={`/app/foundation/${f.slug}`}
            icon={f.icon}
            label={f.label}
            active={pathname === `/app/foundation/${f.slug}`}
          />
        ))}
        {misc.map((m) => (
          <NavItem key={m.to} to={m.to} icon={m.icon} label={m.label} active={pathname === m.to} />
        ))}
      </div>
      <div className="mx-3 mt-6 rounded-xl border border-border bg-secondary/60 p-4">
        <div className="flex items-center gap-2 text-xs font-medium text-foreground">
          <Sparkles className="h-3.5 w-3.5 text-accent" />
          AI usage this month
        </div>
        <div className="mt-3 text-2xl font-serif tracking-tight">1,284</div>
        <div className="text-[11px] text-muted-foreground">
          decisions logged · 96.4% audit-clean
        </div>
        <div className="mt-3 h-1.5 w-full overflow-hidden rounded-full bg-background">
          <div className="h-full w-[64%] bg-accent transition-[width] duration-700 ease-out" />
        </div>
      </div>
    </aside>
  );
}

function SectionLabel({ children }: { children: ReactNode }) {
  return (
    <div className="mt-5 px-3 pb-1 text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
      {children}
    </div>
  );
}

function NavItem({
  to,
  icon: Icon,
  label,
  badge,
  active,
}: {
  to: string;
  icon: any;
  label: string;
  badge?: string;
  active?: boolean;
}) {
  return (
    <Link
      to={to}
      className={cn(
        "group my-0.5 flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm text-ink-soft transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
        active ? "bg-foreground text-background" : "hover:bg-secondary hover:text-foreground",
      )}
    >
      <Icon
        className={cn(
          "h-4 w-4 shrink-0",
          active ? "text-background" : "text-muted-foreground group-hover:text-foreground",
        )}
      />
      <span className="truncate">{label}</span>
      {badge && (
        <span
          className={cn(
            "ml-auto rounded-full px-1.5 py-0.5 text-[10px] font-medium",
            active ? "bg-background/15 text-background" : "bg-secondary text-foreground",
          )}
        >
          {badge}
        </span>
      )}
    </Link>
  );
}

function TopBar({
  crumbs,
  onOpenCopilot,
}: {
  crumbs: { label: string; to?: string }[];
  onOpenCopilot: () => void;
}) {
  const navigate = useNavigate();
  const identity = getIdentity();
  const initials = (identity?.name ?? identity?.email ?? "?")
    .split(/[.\s@]/)
    .filter(Boolean)
    .slice(0, 2)
    .map((s) => s[0]?.toUpperCase())
    .join("");

  async function handleLogout() {
    clearIdentity();
    await navigate({ to: "/" });
  }

  return (
    <header className="sticky top-0 z-20 flex h-16 items-center gap-4 border-b border-border bg-background/85 px-6 backdrop-blur md:px-10">
      <nav className="flex items-center gap-1.5 text-sm text-muted-foreground">
        {crumbs.map((c, i) => (
          <span key={i} className="flex items-center gap-1.5">
            {i > 0 && <ChevronRight className="h-3.5 w-3.5" />}
            {c.to ? (
              <Link to={c.to} className="hover:text-foreground">
                {c.label}
              </Link>
            ) : (
              <span className="text-foreground">{c.label}</span>
            )}
          </span>
        ))}
      </nav>
      <div className="ml-auto flex items-center gap-3">
        <button
          onClick={onOpenCopilot}
          className="hidden items-center gap-2 rounded-lg border border-border bg-secondary/60 px-3 py-1.5 text-xs text-muted-foreground transition-colors hover:bg-secondary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 md:inline-flex"
        >
          <Search className="h-3.5 w-3.5" />
          Search or ask Coverline AI…
          <kbd className="ml-6 rounded bg-background px-1.5 py-0.5 font-mono text-[10px]">
            <Command className="mr-0.5 inline h-2.5 w-2.5" />K
          </kbd>
        </button>
        <ThemeToggle />
        {/* for future notification system, currently disabled */}
        {/* <button
          className="relative rounded-lg border border-border p-2 transition-colors hover:bg-secondary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
          aria-label="Notifications"
        >
          <Bell className="h-4 w-4" />
          <span className="absolute -right-0.5 -top-0.5 h-2 w-2 rounded-full bg-accent" />
        </button> */}
        <div className="flex items-center gap-2 rounded-full border border-border bg-secondary/60 px-1 py-1 pr-2">
          <div className="grid h-7 w-7 place-items-center rounded-full bg-foreground font-serif text-xs text-background">
            {initials || "?"}
          </div>
          <div className="text-xs leading-tight">
            <div className="font-medium">
              {identity?.name ?? identity?.email ?? "Not logged in"}
            </div>
            <div className="text-[10px] text-muted-foreground">
              {identity ? `${identity.role} · ${identity.email}` : "—"}
            </div>
          </div>
          <button
            onClick={handleLogout}
            className="ml-1 rounded-full px-2 py-1 text-[10px] text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
          >
            Log out
          </button>
        </div>
      </div>
    </header>
  );
}

function buildCrumbs(pathname: string): { label: string; to?: string }[] {
  const parts = pathname.split("/").filter(Boolean);
  if (parts[0] !== "app") return [{ label: "Coverline" }];
  const crumbs: { label: string; to?: string }[] = [{ label: "Coverline OS", to: "/app" }];
  if (parts.length === 1) crumbs.push({ label: "Dashboard" });
  if (parts[1] === "workflows") {
    crumbs.push({ label: "Workflows", to: "/app" });
    const w = workflows.find((x) => x.slug === parts[2]);
    if (w) crumbs.push({ label: w.label });
  }
  if (parts[1] === "foundation") {
    crumbs.push({ label: "Foundation" });
    const f = foundation.find((x) => x.slug === parts[2]);
    if (f) crumbs.push({ label: f.label });
  }
  if (parts[1] === "assistant") crumbs.push({ label: "AI Assistant" });
  if (parts[1] === "analytics") crumbs.push({ label: "Analytics" });
  if (parts[1] === "settings") crumbs.push({ label: "Settings" });
  return crumbs;
}

function CopilotDrawer({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [msg, setMsg] = useState("");
  const prompts = [
    "Summarize submission SUB-24019",
    "Explain why Ridgeline Contractors is a marginal fit",
    "Compare the carrier quotes on Highline Hospitality",
    "Draft a retail agent email requesting missing SOV",
    "Check diligent search status for Bayou Marine Services",
    "Which carriers have the best hit ratio this quarter?",
  ];
  if (!open) return null;
  return (
    <div
      className="fixed inset-0 z-50 flex justify-end bg-black/20 animate-in fade-in-0 duration-200"
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="flex h-full w-full max-w-xl flex-col border-l border-border bg-background shadow-2xl animate-in slide-in-from-right duration-300"
      >
        <div className="flex items-center gap-2 border-b border-border px-5 py-4">
          <Sparkles className="h-4 w-4 text-accent" />
          <div className="font-serif text-lg">Coverline AI</div>
          <span className="rounded-full bg-secondary px-2 py-0.5 text-[10px] uppercase tracking-wider text-muted-foreground">
            Copilot
          </span>
          <button
            onClick={onClose}
            className="ml-auto rounded-md p-1.5 transition-colors hover:bg-secondary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
            aria-label="Close"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="flex-1 space-y-4 overflow-y-auto px-5 py-6 text-sm">
          <div className="rounded-xl border border-border bg-secondary/60 p-4">
            <div className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
              Context
            </div>
            <div className="mt-1 text-foreground">
              You have <b>12 submissions</b> awaiting review, <b>7 remarket reviews</b> due in the
              next 30 days, and <b>4 mid-term changes</b> pending approval. Two diligent-search
              records need declination evidence.
            </div>
          </div>
          <div className="rounded-xl border border-border p-4">
            <div className="mb-2 flex items-center gap-2 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
              <Sparkles className="h-3 w-3 text-accent" /> Insight
            </div>
            <p className="text-foreground">
              Marsh Southeast has increased submission volume <b>+22%</b> quarter-over-quarter with
              hit ratio holding at <b>38%</b>. Consider prioritizing their queue.
            </p>
            <div className="mt-3 flex flex-wrap gap-2 text-xs">
              <button className="rounded-md border border-border bg-secondary px-2.5 py-1.5 transition-colors hover:bg-secondary/70 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2">
                Open agent view
              </button>
              <button className="rounded-md border border-border bg-secondary px-2.5 py-1.5 transition-colors hover:bg-secondary/70 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2">
                Draft thank-you
              </button>
            </div>
          </div>
          <div>
            <div className="mb-2 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
              Try
            </div>
            <div className="flex flex-wrap gap-2">
              {prompts.map((p) => (
                <button
                  key={p}
                  onClick={() => setMsg(p)}
                  className="rounded-full border border-border bg-secondary/50 px-3 py-1.5 text-xs transition-colors hover:bg-secondary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                >
                  {p}
                </button>
              ))}
            </div>
          </div>
        </div>
        <div className="border-t border-border p-4">
          <div className="flex items-end gap-2 rounded-xl border border-border bg-background p-2 transition-[box-shadow] focus-within:ring-2 focus-within:ring-ring">
            <textarea
              value={msg}
              onChange={(e) => setMsg(e.target.value)}
              placeholder="Ask Coverline anything about your book…"
              className="max-h-32 flex-1 resize-none bg-transparent px-2 py-1.5 text-sm outline-none"
              rows={2}
            />
            <button className="grid h-9 w-9 place-items-center rounded-lg bg-foreground text-background transition active:scale-[0.98] hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2">
              <Send className="h-4 w-4" />
            </button>
          </div>
          <div className="mt-2 flex items-center justify-between text-[10px] text-muted-foreground">
            <span>Powered by Extraction Core + Decision Core · citations included</span>
            <a
              className="inline-flex items-center gap-1 rounded transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
              href="/app/assistant"
            >
              Open full assistant <ArrowUpRight className="h-3 w-3" />
            </a>
          </div>
        </div>
      </div>
    </div>
  );
}

export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow?: string;
  title: string;
  description?: string;
  actions?: ReactNode;
}) {
  return (
    <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0">
        {eyebrow && (
          <div className="mb-2 text-[10px] font-semibold uppercase tracking-[0.16em] text-accent">
            {eyebrow}
          </div>
        )}
        <h1 className="font-serif text-3xl leading-tight tracking-tight md:text-4xl">{title}</h1>
        {description && (
          <p className="mt-2 max-w-2xl text-sm text-muted-foreground">{description}</p>
        )}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function useNav() {
  return useRouter();
}
