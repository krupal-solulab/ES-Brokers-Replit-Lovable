import type { ReactNode } from "react";
import { useInView } from "@/hooks/use-in-view";

/**
 * Scroll-reveal primitive: fades + translates its children up once they
 * enter the viewport. No-ops (renders visible immediately) under
 * prefers-reduced-motion via useInView. `delay` is in ms, for staggering
 * siblings (e.g. a grid of cards) without a separate stagger library.
 */
export function Reveal({
  children,
  className = "",
  delay = 0,
  as: Tag = "div",
}: {
  children: ReactNode;
  className?: string;
  delay?: number;
  as?: "div" | "li" | "section";
}) {
  const [ref, inView] = useInView<HTMLDivElement>();
  return (
    <Tag
      ref={ref as never}
      className={`transition-[opacity,transform] duration-700 ease-out ${inView ? "translate-y-0 opacity-100" : "translate-y-4 opacity-0"} ${className}`}
      style={{ transitionDelay: inView ? `${delay}ms` : "0ms" }}
    >
      {children}
    </Tag>
  );
}
