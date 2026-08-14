import type { ElementType, ReactNode } from "react";
import { cn } from "@/lib/utils";
import { useInView } from "./primitives";

/**
 * DiagramFlow — connected-node flow with orthogonal SVG connectors that draw in
 * (stroke-dashoffset) before their labels fade in.
 */
export type FlowNode = { label: ReactNode; bold?: boolean; icon?: ElementType };

export function DiagramFlow({
  title,
  nodes,
  closer,
  accent = "blue",
  className,
}: {
  title?: ReactNode;
  nodes: FlowNode[];
  closer?: ReactNode;
  accent?: "blue" | "navy";
  className?: string;
}) {
  const { ref, inView } = useInView<HTMLDivElement>(0.3);
  const stroke = accent === "blue" ? "var(--blue-500)" : "var(--navy-400)";

  return (
    <div ref={ref} className={cn("relative", className)}>
      {title ? <p className="type-eyebrow mb-6">{title}</p> : null}
      <ol className="relative space-y-0">
        {nodes.map((n, i) => (
          <li key={i} className="relative flex gap-4">
            {/* connector rail: node marker + orthogonal connector with arrowhead */}
            <div className="relative flex w-6 shrink-0 flex-col items-center">
              <svg width="24" height="24" viewBox="0 0 24 24" aria-hidden className="mt-2">
                <rect
                  x="6.5"
                  y="6.5"
                  width="11"
                  height="11"
                  fill="none"
                  stroke={stroke}
                  strokeWidth="1.5"
                  style={{
                    opacity: inView ? 1 : 0,
                    transition: `opacity 300ms var(--ease-standard) ${i * 60}ms`,
                  }}
                />
                <rect
                  x="10"
                  y="10"
                  width="4"
                  height="4"
                  fill={stroke}
                  style={{
                    opacity: inView ? 1 : 0,
                    transition: `opacity 300ms var(--ease-standard) ${i * 60 + 120}ms`,
                  }}
                />
              </svg>
              {i < nodes.length - 1 ? (
                <svg
                  className="w-6 flex-1"
                  viewBox="0 0 24 48"
                  preserveAspectRatio="none"
                  aria-hidden
                >
                  {/* orthogonal (right-angle) connector — never curved */}
                  <path
                    d="M12 0 V16 H19 V32 H12 V44"
                    stroke={stroke}
                    strokeWidth="1.5"
                    fill="none"
                    vectorEffect="non-scaling-stroke"
                    strokeDasharray="120"
                    strokeDashoffset={inView ? 0 : 120}
                    style={{
                      transition: `stroke-dashoffset 600ms var(--ease-standard) ${i * 60}ms`,
                    }}
                  />
                  <path
                    d="M8 40 L12 46 L16 40"
                    stroke={stroke}
                    strokeWidth="1.5"
                    fill="none"
                    vectorEffect="non-scaling-stroke"
                    style={{
                      opacity: inView ? 1 : 0,
                      transition: `opacity 200ms var(--ease-standard) ${600 + i * 60}ms`,
                    }}
                  />
                </svg>
              ) : null}
            </div>
            {/* node body */}
            <div
              className={cn("reveal min-w-0 flex-1 pb-5 last:pb-0", inView && "reveal-in")}
              style={{ transitionDelay: `${300 + i * 60}ms` }}
            >
              <div
                className={cn(
                  "rounded-[10px] border px-4 py-3 text-[15px] leading-6",
                  n.bold
                    ? "border-navy-900/15 bg-background font-semibold text-navy-900 shadow-tier1"
                    : "border-hairline bg-transparent text-navy-700",
                )}
              >
                {n.icon ? (
                  <n.icon size={18} className="mr-2 inline-block align-[-3px] text-navy-900" />
                ) : null}
                {n.label}
              </div>
            </div>
          </li>
        ))}
      </ol>

      {closer ? (
        <p
          className={cn(
            "reveal mt-6 border-t border-hairline pt-5 text-[16px] font-bold text-navy-900",
            inView && "reveal-in",
          )}
          style={{ transitionDelay: `${300 + nodes.length * 60}ms` }}
        >
          {closer}
        </p>
      ) : null}
    </div>
  );
}

/** TwoColumnCompare — hairline-divided comparison, rows stagger in on scroll. */
export function TwoColumnCompare({
  left,
  right,
  rows,
  className,
}: {
  left: string;
  right: string;
  rows: Array<[ReactNode, ReactNode]>;
  className?: string;
}) {
  const { ref, inView } = useInView<HTMLDivElement>(0.2);
  return (
    <div ref={ref} className={cn("border-t border-hairline", className)}>
      <div className="grid grid-cols-2 gap-6 border-b border-hairline py-4">
        <p className="type-eyebrow">{left}</p>
        <p className="type-eyebrow text-navy-900">{right}</p>
      </div>
      {rows.map(([a, b], i) => (
        <div
          key={i}
          className={cn(
            "reveal grid grid-cols-2 gap-6 border-b border-hairline py-4",
            inView && "reveal-in",
          )}
          style={{ transitionDelay: `${i * 40}ms` }}
        >
          <p className="text-[15px] leading-6 text-navy-400">{a}</p>
          <p className="text-[15px] leading-6 font-semibold text-navy-900">{b}</p>
        </div>
      ))}
    </div>
  );
}
