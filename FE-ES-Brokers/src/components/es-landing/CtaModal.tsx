import { useCallback, useEffect, useRef, useState } from "react";
import { z } from "zod";
import { cn } from "@/lib/utils";
import { Button } from "./primitives";

/**
 * CTA MODAL — every "Log in" / "Run a real submission free", "Book a demo" and
 * "See a sample market plan" CTA sitewide opens a form here instead of
 * navigating. Flows follow the master prompt (SHARED FLOWS).
 *
 * `login` and `signup` are the way into the product, so they mirror the app's
 * own auth dialog field-for-field — only the styling is the landing's.
 */

type Kind = "login" | "signup" | "demo" | "sample";

/* Demo option lists and rules mirror the app's own /demo page field-for-field
   (components/coverline/DemoPage) so the two collect identical data. */
const DEMO_ROLES = [
  ["broker", "Wholesale broker"],
  ["principal", "Principal / owner"],
  ["ops", "Operations / support"],
  ["compliance", "Compliance"],
  ["other", "Other"],
] as const;

const BROKER_TYPES = [
  ["wholesale", "Wholesale broker"],
  ["mga", "MGA"],
  ["retail", "Retail agency"],
  ["carrier", "Carrier"],
] as const;

const VOLUMES = [
  ["under-50", "Under 50"],
  ["50-200", "50 – 200"],
  ["200-500", "200 – 500"],
  ["500-plus", "500+"],
] as const;

const FREE_EMAIL_DOMAINS = [
  "gmail.com",
  "yahoo.com",
  "hotmail.com",
  "outlook.com",
  "icloud.com",
  "aol.com",
];

const emailField = z
  .string()
  .trim()
  .min(1, { message: "Work email is required" })
  .email({ message: "Enter a valid work email" })
  .max(255, { message: "Email must be under 255 characters" });

const brokerageField = z
  .string()
  .trim()
  .min(1, { message: "Brokerage name is required" })
  .max(120, { message: "Brokerage name must be under 120 characters" });

/* Auth rules mirror the app's own dialog (components/coverline/AuthDialog). */
const loginSchema = z.object({
  email: emailField,
  password: z.string().min(1, { message: "Password is required" }),
});

const signupSchema = z
  .object({
    name: z.string().trim().min(2, { message: "Enter your full name" }),
    email: emailField,
    password: z
      .string()
      .min(8, { message: "At least 8 characters" })
      .refine((v) => /[a-z]/.test(v) && /[A-Z]/.test(v), {
        message: "Use upper and lowercase letters",
      })
      .refine((v) => /\d/.test(v), { message: "Include at least one number" }),
    confirmPassword: z.string().min(1, { message: "Confirm your password" }),
  })
  .refine((d) => d.password === d.confirmPassword, {
    message: "Passwords don't match",
    path: ["confirmPassword"],
  });

const demoSchema = z.object({
  name: z.string().trim().min(2, { message: "Enter your full name" }),
  email: emailField.refine(
    (v) => !FREE_EMAIL_DOMAINS.includes(v.split("@")[1]?.toLowerCase() ?? ""),
    { message: "Please use your work email address" },
  ),
  company: z.string().trim().min(2, { message: "Enter your company name" }),
  role: z.string().min(1, { message: "Select your role" }),
  brokerType: z.string().min(1, { message: "Select what best describes you" }),
  volume: z.string().min(1, { message: "Select your monthly submission volume" }),
  notes: z.string().trim().max(1000, { message: "Keep it under 1000 characters" }),
});

const sampleSchema = z.object({ email: emailField, brokerage: brokerageField });

const COPY: Record<Kind, { eyebrow: string; title: string; sub: string; cta: string; foot: string }> = {
  login: {
    eyebrow: "Log in",
    title: "Log in to Coverline.",
    sub: "Welcome back — pick up your placement queue where you left off.",
    cta: "Log in →",
    foot: "",
  },
  signup: {
    eyebrow: "Create an account",
    title: "Create your account.",
    sub: "Set up Coverline for your placement team.",
    cta: "Create account →",
    foot: "",
  },
  demo: {
    eyebrow: "Book a demo",
    title: "See Coverline on your own submissions.",
    sub: "Tell us a bit about your book. We'll tailor the walkthrough to your carrier panel and submission volume.",
    cta: "Book a demo →",
    foot: "",
  },
  sample: {
    eyebrow: "Sample market plan",
    title: "A completed market plan, on a real trucking submission.",
    sub: "The same ranked market plan your placement team would receive, with citations intact.",
    cta: "Send me the market plan →",
    foot: "One email. No sequence you can't leave.",
  },
};

const STORAGE_KEY = "coverline.cta.draft";

export function openCtaModal(kind: Kind) {
  window.dispatchEvent(new CustomEvent("coverline:cta", { detail: kind }));
}

function detectKind(text: string): Kind | null {
  const t = text.toLowerCase();
  if (t.includes("sample market plan")) return "sample";
  if (t.includes("book a demo")) return "demo";
  if (t.includes("log in") || t.includes("run a real submission")) return "login";
  return null;
}

/**
 * `onSubmit` lets the host page send a validated submission to a real backend
 * before the success state renders. The form UI, copy and flows stay exactly as
 * designed; only where the data goes is the host's concern. Throwing from it
 * surfaces the message on the email field and keeps the form open.
 */
export function CtaModal({
  onSubmit,
}: {
  onSubmit?: (
    kind: Kind,
    values: {
      email: string;
      password: string;
      name: string;
      brokerage: string;
      company: string;
      role: string;
      brokerType: string;
      volume: string;
      notes: string;
    },
  ) => Promise<void>;
} = {}) {
  const [kind, setKind] = useState<Kind | null>(null);
  const [done, setDone] = useState(false);
  const [sending, setSending] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [name, setName] = useState("");
  const [brokerage, setBrokerage] = useState("");
  const [company, setCompany] = useState("");
  const [role, setRole] = useState("");
  const [brokerType, setBrokerType] = useState("");
  const [volume, setVolume] = useState("");
  const [notes, setNotes] = useState("");
  /* Honeypot — real users never see or fill this. Any value means a bot. */
  const [website, setWebsite] = useState("");
  const panelRef = useRef<HTMLDivElement | null>(null);
  const firstFieldRef = useRef<HTMLInputElement | null>(null);

  /* restore partially-completed state */
  useEffect(() => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return;
      const d = JSON.parse(raw) as Record<string, unknown>;
      if (typeof d['email'] === "string") setEmail(d['email']);
      if (typeof d['brokerage'] === "string") setBrokerage(d['brokerage']);
      if (typeof d['company'] === "string") setCompany(d['company']);
      if (typeof d['role'] === "string") setRole(d['role']);
      if (typeof d['name'] === "string") setName(d['name']);
    } catch {
      /* ignore */
    }
  }, []);

  /* Never persist a password — only the marketing fields are worth restoring. */
  useEffect(() => {
    if (!kind || done) return;
    try {
      localStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({ email, brokerage, company, role, name }),
      );
    } catch {
      /* ignore */
    }
  }, [kind, done, email, brokerage, company, role, name]);

  const open = useCallback((k: Kind) => {
    setKind(k);
    setDone(false);
    setErrors({});
  }, []);

  /* intercept every CTA on the page */
  useEffect(() => {
    const onEvent = (e: Event) => open((e as CustomEvent).detail as Kind);
    window.addEventListener("coverline:cta", onEvent);

    const onClick = (e: MouseEvent) => {
      const target = e.target as HTMLElement | null;
      const el = target?.closest("a,button") as HTMLElement | null;
      if (!el || panelRef.current?.contains(el)) return;
      const k = detectKind(el.textContent ?? "");
      if (!k) return;
      e.preventDefault();
      e.stopPropagation();
      open(k);
    };
    document.addEventListener("click", onClick, true);
    return () => {
      window.removeEventListener("coverline:cta", onEvent);
      document.removeEventListener("click", onClick, true);
    };
  }, [open]);

  useEffect(() => {
    if (!kind) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setKind(null);
    };
    document.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const id = window.setTimeout(() => firstFieldRef.current?.focus(), 60);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
      window.clearTimeout(id);
    };
  }, [kind]);

  if (!kind) return null;
  const copy = COPY[kind];
  const isAuth = kind === "login" || kind === "signup";

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    let result;
    if (kind === "login") result = loginSchema.safeParse({ email, password });
    else if (kind === "signup")
      result = signupSchema.safeParse({ name, email, password, confirmPassword });
    else if (kind === "demo") {
      if (website) return; // honeypot tripped — silently drop
      result = demoSchema.safeParse({ name, email, company, role, brokerType, volume, notes });
    } else result = sampleSchema.safeParse({ email, brokerage });

    if (!result.success) {
      const next: Record<string, string> = {};
      for (const issue of result.error.issues) next[String(issue.path[0])] = issue.message;
      setErrors(next);
      return;
    }
    setErrors({});

    if (onSubmit) {
      setSending(true);
      try {
        await onSubmit(kind, {
          email,
          password,
          name,
          brokerage,
          company,
          role,
          brokerType,
          volume,
          notes,
        });
      } catch (err) {
        // The email is what the backend keys off, so a rejection belongs there.
        setErrors({ email: err instanceof Error ? err.message : "Something went wrong." });
        return;
      } finally {
        setSending(false);
      }
    }

    setDone(true);
    try {
      localStorage.removeItem(STORAGE_KEY);
    } catch {
      /* ignore */
    }
  };

  return (
    <div
      className="fixed inset-0 z-[120] flex items-end justify-center overflow-y-auto bg-[color:color-mix(in_oklab,#0A1B3D_55%,transparent)] p-0 sm:items-center sm:p-6"
      role="dialog"
      aria-modal="true"
      aria-label={copy.title}
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) setKind(null);
      }}
    >
      <div
        ref={panelRef}
        className="relative max-h-[92vh] w-full max-w-[560px] overflow-y-auto rounded-t-[14px] border border-hairline bg-background p-6 shadow-tier2 sm:rounded-[14px] sm:p-9"
      >
        <button
          type="button"
          onClick={() => setKind(null)}
          aria-label="Close"
          className="absolute top-4 right-4 min-h-[40px] min-w-[40px] text-[14px] font-medium text-navy-700 hover:text-navy-900"
        >
          Close
        </button>

        {done ? (
          <div>
            <p className="type-eyebrow">Confirmed</p>
            {kind === "login" || kind === "signup" ? (
              <>
                <h2 className="type-h3 mt-4">
                  {kind === "login" ? "You're in." : "Account created."}
                </h2>
                <p className="type-body mt-4">
                  Taking you to your placement queue…
                </p>
              </>
            ) : kind === "demo" ? (
              <>
                <h2 className="type-h3 mt-4">Thanks — we'll be in touch.</h2>
                <p className="type-body mt-4">
                  Someone from our team will reach out within one business day to schedule a
                  walkthrough of Submission Market Matching on your own book.
                </p>
              </>
            ) : (
              <>
                <h2 className="type-h3 mt-4">On its way.</h2>
                <p className="type-body mt-4">
                  The completed market plan is heading to {email}. One email. No sequence
                  you can't leave.
                </p>
              </>
            )}
            {/* Auth redirects on its own — a Done button would just race it. */}
            {kind === "login" || kind === "signup" ? null : (
              <div className="mt-8">
                <Button onClick={() => setKind(null)}>Done</Button>
              </div>
            )}
          </div>
        ) : (
          <form onSubmit={submit} noValidate>
            <p className="type-eyebrow">{copy.eyebrow}</p>
            <h2 className="type-h3 mt-4 pr-16">{copy.title}</h2>
            <p className="type-body-s mt-3">{copy.sub}</p>

            <div className="mt-7 grid gap-5">
              {kind === "signup" || kind === "demo" ? (
                <Field label="Full name" error={errors['name']}>
                  <input
                    type="text"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    maxLength={120}
                    autoComplete="name"
                    placeholder="Sam Delgado"
                    className={inputCls(!!errors['name'])}
                  />
                </Field>
              ) : null}

              <Field label="Work email" error={errors['email']}>
                <input
                  ref={firstFieldRef}
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  maxLength={255}
                  autoComplete="email"
                  placeholder="you@brokerage.com"
                  className={inputCls(!!errors['email'])}
                />
              </Field>

              {isAuth ? (
                <>
                  <Field
                    label="Password"
                    error={errors['password']}
                    action={
                      kind === "login" ? (
                        <a
                          href="#final-cta"
                          className="text-[13px] font-medium text-blue-500 hover:underline"
                        >
                          Forgot password?
                        </a>
                      ) : undefined
                    }
                  >
                    <input
                      type="password"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      autoComplete={kind === "login" ? "current-password" : "new-password"}
                      placeholder="••••••••"
                      className={inputCls(!!errors['password'])}
                    />
                  </Field>

                  {kind === "signup" ? (
                    <Field label="Confirm password" error={errors['confirmPassword']}>
                      <input
                        type="password"
                        value={confirmPassword}
                        onChange={(e) => setConfirmPassword(e.target.value)}
                        autoComplete="new-password"
                        placeholder="••••••••"
                        className={inputCls(!!errors['confirmPassword'])}
                      />
                    </Field>
                  ) : null}
                </>
              ) : kind === "demo" ? (
                <Field label="Company" error={errors['company']}>
                  <input
                    type="text"
                    value={company}
                    onChange={(e) => setCompany(e.target.value)}
                    maxLength={120}
                    autoComplete="organization"
                    placeholder="Meridian Specialty Wholesale"
                    className={inputCls(!!errors['company'])}
                  />
                </Field>
              ) : (
                <Field label="Brokerage name" error={errors['brokerage']}>
                  <input
                    type="text"
                    value={brokerage}
                    onChange={(e) => setBrokerage(e.target.value)}
                    maxLength={120}
                    autoComplete="organization"
                    placeholder="Your firm"
                    className={inputCls(!!errors['brokerage'])}
                  />
                </Field>
              )}

              {kind === "demo" ? (
                <>
                  <div className="grid gap-5 sm:grid-cols-3">
                    <Field label="Your role" error={errors['role']}>
                      <Select
                        value={role}
                        onChange={setRole}
                        placeholder="Select role"
                        options={DEMO_ROLES}
                        error={!!errors['role']}
                      />
                    </Field>
                    <Field label="You are a" error={errors['brokerType']}>
                      <Select
                        value={brokerType}
                        onChange={setBrokerType}
                        placeholder="Select type"
                        options={BROKER_TYPES}
                        error={!!errors['brokerType']}
                      />
                    </Field>
                    <Field label="Submissions / mo" error={errors['volume']}>
                      <Select
                        value={volume}
                        onChange={setVolume}
                        placeholder="Select volume"
                        options={VOLUMES}
                        error={!!errors['volume']}
                      />
                    </Field>
                  </div>

                  <Field
                    label="Anything specific you want to see? (optional)"
                    error={errors['notes']}
                  >
                    <textarea
                      value={notes}
                      onChange={(e) => setNotes(e.target.value)}
                      maxLength={1000}
                      rows={3}
                      placeholder="E.g. how carrier ranking works for habitational risk…"
                      className={cn(inputCls(!!errors['notes']), "h-auto py-3")}
                    />
                  </Field>

                  <input
                    type="text"
                    value={website}
                    onChange={(e) => setWebsite(e.target.value)}
                    tabIndex={-1}
                    autoComplete="off"
                    aria-hidden
                    className="absolute left-[-9999px] h-px w-px opacity-0"
                  />
                </>
              ) : null}
            </div>

            <div className="mt-8 flex flex-wrap items-center gap-4">
              <Button type="submit" disabled={sending}>
                {sending ? "Working…" : copy.cta}
              </Button>
              {copy.foot ? <span className="type-body-s">{copy.foot}</span> : null}
            </div>

            {isAuth ? (
              <p className="type-body-s mt-6 border-t border-hairline pt-6">
                {kind === "login" ? "New to Coverline? " : "Already have an account? "}
                <button
                  type="button"
                  onClick={() => open(kind === "login" ? "signup" : "login")}
                  className="cursor-pointer font-semibold text-navy-900 underline-offset-4 hover:underline"
                >
                  {kind === "login" ? "Create an account" : "Log in"}
                </button>
              </p>
            ) : null}
          </form>
        )}
      </div>
    </div>
  );
}

function inputCls(error: boolean) {
  return cn(
    "h-[48px] w-full rounded-[10px] border bg-background px-3 text-[15px] text-navy-900 outline-none transition-colors duration-150 focus:border-navy-900",
    error ? "border-[color:var(--danger-text)]" : "border-hairline",
  );
}

function Select({
  value,
  onChange,
  placeholder,
  options,
  error,
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder: string;
  options: readonly (readonly [string, string])[];
  error: boolean;
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className={inputCls(error)}
    >
      <option value="">{placeholder}</option>
      {options.map(([v, label]) => (
        <option key={v} value={v}>
          {label}
        </option>
      ))}
    </select>
  );
}

function Field({
  label,
  error,
  action,
  children,
}: {
  label: string;
  error?: string | undefined;
  /** Optional control rendered opposite the label, e.g. "Forgot password?". */
  action?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className="mb-2 flex items-baseline justify-between gap-3">
        <span className="text-[13px] font-semibold text-navy-900">{label}</span>
        {action}
      </span>
      {children}
      {error ? (
        <span className="mt-1.5 block text-[13px] text-[color:var(--danger-text)]">{error}</span>
      ) : null}
    </label>
  );
}
