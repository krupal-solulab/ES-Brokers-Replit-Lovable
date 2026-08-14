import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ElementType,
  type ReactNode,
} from "react";
import { cn } from "@/lib/utils";
import { IconChevron } from "./icons";

/* ---------------- motion utilities ---------------- */

export function usePrefersReducedMotion() {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    setReduced(mq.matches);
    const on = () => setReduced(mq.matches);
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);
  return reduced;
}

export function useInView<T extends HTMLElement>(
  threshold = 0.2,
  rootMargin = "0px 0px -10% 0px",
) {
  const ref = useRef<T | null>(null);
  const [inView, setInView] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (typeof IntersectionObserver === "undefined") {
      setInView(true);
      return;
    }
    const io = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (e.isIntersecting) {
            setInView(true);
            io.disconnect();
          }
        }
      },
      { threshold, rootMargin },
    );
    io.observe(el);
    return () => io.disconnect();
  }, [threshold, rootMargin]);
  return { ref, inView };
}

/**
 * Scroll progress of an element across the viewport, 0 → 1.
 * Drives Apple-style scroll-linked parallax / fade-out effects.
 */
export function useViewportProgress<T extends HTMLElement>() {
  const ref = useRef<T | null>(null);
  const [p, setP] = useState(0);
  useEffect(() => {
    let raf = 0;
    const measure = () => {
      raf = 0;
      const el = ref.current;
      if (!el) return;
      const r = el.getBoundingClientRect();
      const vh = window.innerHeight || 1;
      const raw = (vh - r.top) / (vh + r.height);
      setP(Math.min(1, Math.max(0, raw)));
    };
    const on = () => {
      if (!raf) raf = requestAnimationFrame(measure);
    };
    measure();
    window.addEventListener("scroll", on, { passive: true });
    window.addEventListener("resize", on);
    return () => {
      if (raf) cancelAnimationFrame(raf);
      window.removeEventListener("scroll", on);
      window.removeEventListener("resize", on);
    };
  }, []);
  return { ref, progress: p };
}

/** Subtle scroll-linked vertical drift. */
export function Parallax({
  children,
  distance = 40,
  className,
}: {
  children: ReactNode;
  distance?: number;
  className?: string;
}) {
  const reduced = usePrefersReducedMotion();
  const { ref, progress } = useViewportProgress<HTMLDivElement>();
  const y = reduced ? 0 : (0.5 - progress) * distance;
  return (
    <div
      ref={ref}
      className={className}
      style={{ transform: `translate3d(0, ${y.toFixed(2)}px, 0)`, willChange: "transform" }}
    >
      {children}
    </div>
  );
}

/** Word-by-word headline entrance (load-triggered). */
export function WordRise({
  text,
  className,
  delay = 0,
  step = 55,
  weightClass,
}: {
  text: string;
  className?: string;
  delay?: number;
  step?: number;
  weightClass?: string;
}) {
  const [shown, setShown] = useState(false);
  useEffect(() => {
    const t = window.setTimeout(() => setShown(true), delay);
    return () => window.clearTimeout(t);
  }, [delay]);
  const words = text.split(" ");
  return (
    <span className={cn("block", className)}>
      {words.map((w, i) => (
        <span key={`${w}-${i}`} className="inline-block overflow-hidden align-bottom">
          <span
            className={cn("word-rise", shown && "word-rise-in", weightClass)}
            style={{ transitionDelay: `${i * step}ms` }}
          >
            {w}
          </span>
          {i < words.length - 1 ? <span>&nbsp;</span> : null}
        </span>
      ))}
    </span>
  );
}

export function Reveal({
  children,
  delay = 0,
  as: Tag = "div",
  className,
  threshold = 0.15,
}: {
  children: ReactNode;
  delay?: number;
  as?: ElementType;
  className?: string;
  threshold?: number;
}) {
  const { ref, inView } = useInView<HTMLDivElement>(threshold);
  return (
    <Tag
      ref={ref}
      className={cn("reveal", inView && "reveal-in", className)}
      style={{ transitionDelay: `${delay}ms` }}
    >
      {children}
    </Tag>
  );
}


/** Load-triggered (above the fold) sequenced entrance. */
export function LoadReveal({
  children,
  delay = 0,
  as: Tag = "div",
  className,
}: {
  children: ReactNode;
  delay?: number;
  as?: ElementType;
  className?: string;
}) {
  const [shown, setShown] = useState(false);
  useEffect(() => {
    const t = window.setTimeout(() => setShown(true), delay);
    return () => window.clearTimeout(t);
  }, [delay]);
  return (
    <Tag className={cn("reveal", shown && "reveal-in", className)}>{children}</Tag>
  );
}

export function CountUp({
  value,
  duration = 700,
  prefix = "",
  suffix = "",
  decimals = 0,
  className,
  start,
}: {
  value: number;
  duration?: number;
  prefix?: string;
  suffix?: string;
  decimals?: number;
  className?: string;
  /** external trigger; when omitted the element observes itself */
  start?: boolean;
}) {
  const reduced = usePrefersReducedMotion();
  const { ref, inView } = useInView<HTMLSpanElement>(0.5);
  const [n, setN] = useState(0);
  const active = start === undefined ? inView : start;

  useEffect(() => {
    if (!active) return;
    if (reduced) {
      setN(value);
      return;
    }
    let raf = 0;
    const t0 = performance.now();
    const tick = (t: number) => {
      const p = Math.min(1, (t - t0) / duration);
      const eased = 1 - Math.pow(1 - p, 3);
      setN(value * eased);
      if (p < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [active, value, duration, reduced]);

  const shown = n.toLocaleString("en-US", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });

  return (
    <span ref={ref} className={cn("tnum", className)}>
      {prefix}
      {shown}
      {suffix}
    </span>
  );
}

/* ---------------- layout ---------------- */

export function Container({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("mx-auto w-full max-w-[1280px] px-5 lg:px-16", className)}>
      {children}
    </div>
  );
}

export function Section({
  id,
  children,
  className,
  tone = "white",
  hairline = true,
}: {
  id?: string;
  children: ReactNode;
  className?: string;
  tone?: "white" | "gray" | "gray050" | "dark";
  hairline?: boolean;
}) {
  const bg =
    tone === "dark"
      ? "bg-panel"
      : tone === "gray"
        ? "bg-gray-100"
        : tone === "gray050"
          ? "bg-gray-050"
          : "bg-background";
  return (
    <section
      id={id}
      className={cn(
        "scroll-mt-24 py-20 lg:py-40",
        bg,
        hairline && tone !== "dark" && "border-t border-hairline",
        className,
      )}
    >
      <Container>{children}</Container>
    </section>
  );
}

export function Eyebrow({
  children,
  onDark = false,
  className,
}: {
  children: ReactNode;
  onDark?: boolean;
  className?: string;
}) {
  return (
    <p
      className={cn(
        "type-eyebrow",
        onDark && "text-[color:color-mix(in_oklab,white_62%,transparent)]",
        className,
      )}
    >
      {children}
    </p>
  );
}

/* ---------------- buttons ---------------- */

type BtnProps = {
  children: ReactNode;
  href?: string;
  variant?: "primary" | "primaryBlue" | "secondary" | "secondaryDark" | "resource";
  className?: string;
  onClick?: () => void;
  type?: "button" | "submit";
  disabled?: boolean;
};

export function Button({
  children,
  href,
  variant = "primary",
  className,
  onClick,
  type = "button",
  disabled,
}: BtnProps) {
  const base =
    "inline-flex min-h-[52px] items-center justify-center rounded-[10px] px-7 text-[15px] font-600 font-semibold transition-all duration-150 ease-[var(--ease-standard)]";
  const styles: Record<string, string> = {
    primary:
      "bg-cta text-white hover:bg-cta-hover hover:-translate-y-px hover:shadow-tier1",
    primaryBlue:
      "bg-blue-fill text-white hover:-translate-y-px hover:shadow-tier2 hover:brightness-95",
    secondary:
      "border-[1.5px] border-navy-900 text-navy-900 hover:bg-gray-100 hover:-translate-y-px",
    secondaryDark:
      "border-[1.5px] border-[color:color-mix(in_oklab,white_45%,transparent)] text-white hover:bg-[color:color-mix(in_oklab,white_10%,transparent)] hover:-translate-y-px",
    resource:
      "min-h-[52px] px-0 text-navy-700 hover:underline underline-offset-4",
  };
  const cls = cn(base, styles[variant], disabled && "pointer-events-none opacity-60", className);
  const magnetic = variant === "primary" || variant === "primaryBlue";
  const mag = useMagnetic(magnetic);

  if (href) {
    return (
      <a href={href} className={cls} {...mag}>
        {children}
      </a>
    );
  }
  return (
    <button type={type} onClick={onClick} disabled={disabled} className={cls} {...mag}>
      {children}
    </button>
  );
}

/**
 * SIGNATURE INTERACTIVE MOMENT #8 — magnetic primary buttons.
 * Desktop pointer devices only; a max ~6px spring-eased pull toward the cursor,
 * released back to center on mouse-leave. Absent (not broken) on touch.
 */
function useMagnetic(enabled: boolean) {
  const ref = useRef<HTMLElement | null>(null);
  const reduced = usePrefersReducedMotion();
  const [fine, setFine] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined") return;
    setFine(window.matchMedia("(pointer: fine)").matches);
  }, []);

  if (!enabled || !fine || reduced) return {};

  return {
    ref: ref as never,
    onMouseMove: (e: { currentTarget: HTMLElement; clientX: number; clientY: number }) => {
      const el = e.currentTarget;
      const r = el.getBoundingClientRect();
      const dx = ((e.clientX - (r.left + r.width / 2)) / (r.width / 2)) * 6;
      const dy = ((e.clientY - (r.top + r.height / 2)) / (r.height / 2)) * 6;
      el.style.transition = "transform 120ms var(--ease-standard)";
      el.style.transform = `translate(${dx.toFixed(2)}px, ${dy.toFixed(2)}px)`;
    },
    onMouseLeave: (e: { currentTarget: HTMLElement }) => {
      const el = e.currentTarget;
      el.style.transition = "transform 300ms var(--ease-standard)";
      el.style.transform = "";
    },
  };
}


export function TextLink({
  children,
  href,
  className,
  onDark = false,
}: {
  children: ReactNode;
  href: string;
  className?: string;
  onDark?: boolean;
}) {
  return (
    <a
      href={href}
      className={cn(
        "inline-flex items-center gap-1.5 text-[15px] font-medium underline-offset-4 transition-colors duration-150 hover:underline",
        onDark ? "text-white" : "text-blue-500",
        className,
      )}
    >
      {children}
    </a>
  );
}

/* ---------------- content atoms ---------------- */

export function StatePill({
  tone,
  children,
}: {
  tone: "success" | "warning" | "danger";
  children: ReactNode;
}) {
  const map = {
    success: "bg-success-tint text-success-text",
    warning: "bg-warning-tint text-warning-text",
    danger: "bg-danger-tint text-danger-text",
  } as const;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-[4px] px-2 py-1 text-[11px] font-semibold tracking-wide",
        map[tone],
      )}
    >
      <span className="size-1 rounded-[1px] bg-current" aria-hidden />
      {children}
    </span>
  );
}

export function IconLabelRow({
  icon: Icon,
  title,
  children,
  className,
}: {
  icon: ElementType;
  title?: ReactNode;
  children?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex gap-4", className)}>
      <Icon size={20} className="mt-0.5 shrink-0 text-navy-900" />
      <div className="min-w-0">
        {title ? (
          <p className="text-[16px] font-semibold text-navy-900">{title}</p>
        ) : null}
        {children ? <div className="type-body mt-1">{children}</div> : null}
      </div>
    </div>
  );
}

/** Standout block — identical treatment sitewide: left border draws in top-to-bottom. */
export function Standout({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  const { ref, inView } = useInView<HTMLDivElement>(0.25);
  return (
    <div ref={ref} className={cn("relative pl-6", className)}>
      <span
        aria-hidden
        className="absolute top-0 left-0 w-px bg-blue-500 transition-[height] duration-[400ms] ease-[var(--ease-standard)]"
        style={{ height: inView ? "100%" : "0%" }}
      />
      <div className="space-y-4">{children}</div>
    </div>
  );
}

/* ---------------- accordion ---------------- */

const AccordionCtx = createContext<{
  open: string | null;
  toggle: (id: string) => void;
} | null>(null);

export function Accordion({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  const [open, setOpen] = useState<string | null>(null);
  const toggle = useCallback(
    (id: string) => setOpen((cur) => (cur === id ? null : id)),
    [],
  );
  return (
    <AccordionCtx.Provider value={{ open, toggle }}>
      <div className={cn("divide-y divide-hairline border-y border-hairline", className)}>
        {children}
      </div>
    </AccordionCtx.Provider>
  );
}

export function AccordionItem({
  id,
  question,
  children,
}: {
  id: string;
  question: ReactNode;
  children: ReactNode;
}) {
  const ctx = useContext(AccordionCtx);
  const open = ctx?.open === id;
  return (
    <div>
      <button
        type="button"
        aria-expanded={open}
        onClick={() => ctx?.toggle(id)}
        className="flex min-h-[56px] w-full items-center justify-between gap-6 py-4 text-left"
      >
        <span className="text-[17px] font-semibold text-navy-900">{question}</span>
        <IconChevron
          size={20}
          className={cn(
            "shrink-0 text-navy-400 transition-transform duration-200 ease-[var(--ease-standard)]",
            open && "rotate-180",
          )}
        />
      </button>
      <div
        className="grid transition-all duration-[220ms] ease-[var(--ease-standard)]"
        style={{
          gridTemplateRows: open ? "1fr" : "0fr",
          opacity: open ? 1 : 0,
        }}
      >
        <div className="overflow-hidden">
          <div className="type-body max-w-[70ch] pb-6">{children}</div>
        </div>
      </div>
    </div>
  );
}
