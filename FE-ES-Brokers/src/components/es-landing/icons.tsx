import type { SVGProps } from "react";

/**
 * The single geometric line-icon set used sitewide.
 * 1.5px stroke, no fill, square/orthogonal shape language, 24px default.
 */
type IconProps = SVGProps<SVGSVGElement> & { size?: number; title?: string };

function Base({ size = 24, title, children, ...rest }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      strokeLinecap="square"
      strokeLinejoin="miter"
      role={title ? "img" : "presentation"}
      aria-hidden={title ? undefined : true}
      {...rest}
    >
      {title ? <title>{title}</title> : null}
      {children}
    </svg>
  );
}

export const IconDocument = (p: IconProps) => (
  <Base {...p}>
    <path d="M5 3h9l5 5v13H5z" />
    <path d="M14 3v5h5" />
    <path d="M8 13h8M8 17h5" />
  </Base>
);

export const IconSearch = (p: IconProps) => (
  <Base {...p}>
    <rect x="3" y="3" width="13" height="13" />
    <path d="M16 16l5 5" />
    <path d="M7 9h5" />
  </Base>
);

export const IconShield = (p: IconProps) => (
  <Base {...p}>
    <path d="M12 3l7 3v6c0 5-3.5 7.6-7 9-3.5-1.4-7-4-7-9V6z" />
    <path d="M8.5 12h7" />
  </Base>
);

export const IconShieldCheck = (p: IconProps) => (
  <Base {...p}>
    <path d="M12 3l7 3v6c0 5-3.5 7.6-7 9-3.5-1.4-7-4-7-9V6z" />
    <path d="M9 11.5l2 2 4-4" />
  </Base>
);

export const IconRankedBars = (p: IconProps) => (
  <Base {...p}>
    <path d="M4 6h14M4 12h9M4 18h5" />
  </Base>
);

export const IconPersonCheck = (p: IconProps) => (
  <Base {...p}>
    <rect x="6" y="3" width="7" height="7" />
    <path d="M3 21v-3c0-2.2 1.8-4 4-4h5" />
    <path d="M14 17.5l2 2 4.5-4.5" />
  </Base>
);

export const IconClock = (p: IconProps) => (
  <Base {...p}>
    <rect x="3" y="3" width="18" height="18" />
    <path d="M12 7.5V12l3.5 2" />
  </Base>
);

export const IconLock = (p: IconProps) => (
  <Base {...p}>
    <rect x="4" y="10" width="16" height="11" />
    <path d="M8 10V7a4 4 0 0 1 8 0v3" />
    <path d="M12 14v3" />
  </Base>
);

export const IconCitation = (p: IconProps) => (
  <Base {...p}>
    <path d="M4 12h11" />
    <path d="M11 8l4 4-4 4" />
    <path d="M19 4v16" />
  </Base>
);

export const IconRefresh = (p: IconProps) => (
  <Base {...p}>
    <path d="M4 12a8 8 0 0 1 13.7-5.7L20 8" />
    <path d="M20 4v4h-4" />
    <path d="M20 12a8 8 0 0 1-13.7 5.7L4 16" />
    <path d="M4 20v-4h4" />
  </Base>
);

export const IconLayers = (p: IconProps) => (
  <Base {...p}>
    <path d="M12 3l8 4-8 4-8-4z" />
    <path d="M4 12l8 4 8-4" />
    <path d="M4 17l8 4 8-4" />
  </Base>
);

export const IconCheck = (p: IconProps) => (
  <Base {...p}>
    <path d="M4 12.5l5 5L20 6.5" />
  </Base>
);

export const IconFlag = (p: IconProps) => (
  <Base {...p}>
    <path d="M6 21V4h12l-3 4 3 4H6" />
  </Base>
);

export const IconCross = (p: IconProps) => (
  <Base {...p}>
    <path d="M6 6l12 12M18 6L6 18" />
  </Base>
);

export const IconCircle = (p: IconProps) => (
  <Base {...p}>
    <rect x="5" y="5" width="14" height="14" />
  </Base>
);

export const IconChevron = (p: IconProps) => (
  <Base {...p}>
    <path d="M6 9l6 6 6-6" />
  </Base>
);

export const IconArrow = (p: IconProps) => (
  <Base {...p}>
    <path d="M4 12h15" />
    <path d="M14 7l5 5-5 5" />
  </Base>
);
