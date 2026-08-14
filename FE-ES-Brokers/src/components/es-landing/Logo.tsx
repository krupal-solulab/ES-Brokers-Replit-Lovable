import { useId } from "react";
import { cn } from "@/lib/utils";

/**
 * Coverline lockup: ONE single <text> element renders the whole wordmark.
 * The Brand Blue middle arm of the final "E" is the same text drawn again and
 * clipped to the arm's band, so the letters can never drift apart.
 */
export function Logo({
  className,
  onDark = false,
  withTagline = false,
}: {
  className?: string;
  onDark?: boolean;
  withTagline?: boolean;
}) {
  const id = useId().replace(/[:]/g, "");
  const clipId = `cl-e-${id}`;
  const ink = onDark ? "#FFFFFF" : "var(--navy-900)";

  return (
    <span className={cn("inline-flex flex-col gap-1.5", className)}>
      <svg
        viewBox="0 0 260 32"
        width={150}
        height={19}
        role="img"
        aria-label="Coverline"
        className="block"
      >
        <defs>
          <clipPath id={clipId}>
            {/* band over the middle arm of the final E only */}
            <rect x="228" y="12.5" width="32" height="4.4" />
          </clipPath>
        </defs>
        <text
          x="0"
          y="24"
          textLength="256"
          lengthAdjust="spacingAndGlyphs"
          fontFamily="Manrope, sans-serif"
          fontSize="26"
          fontWeight="700"
          letterSpacing="1.5"
          fill={ink}
        >
          COVERLINE
        </text>
        <text
          x="0"
          y="24"
          textLength="256"
          lengthAdjust="spacingAndGlyphs"
          fontFamily="Manrope, sans-serif"
          fontSize="26"
          fontWeight="700"
          letterSpacing="1.5"
          fill="var(--blue-500)"
          clipPath={`url(#${clipId})`}
          aria-hidden="true"
        >
          COVERLINE
        </text>
      </svg>
      {withTagline ? (
        <span
          className={cn(
            "type-eyebrow",
            onDark && "text-[color:color-mix(in_oklab,white_58%,transparent)]",
          )}
        >
          Coverage. Workflow. Decisions.
        </span>
      ) : null}
    </span>
  );
}
