import { Container } from "./primitives";
import { Logo } from "./Logo";

const GROUPS: Array<[string, string[]]> = [
  ["Product", ["Placement workflows", "Pricing", "Integrations", "Security", "For MGAs"]],
  ["Company", ["About", "Careers", "Contact", "LinkedIn"]],
  ["Resources", ["Case study", "Sample market plan", "Security overview", "ROI model"]],
  ["Legal", ["Terms", "Privacy", "Sub-processors", "DPA"]],
];

/**
 * Real destinations for the footer links that have somewhere to go. Everything
 * else falls back to "#top" — "Sample market plan" is deliberately left alone,
 * since CtaModal already claims that label and opens its form.
 */
const HREFS: Record<string, string> = {
  "Case study": "#case-studies",
};

export function Footer() {
  return (
    <footer className="bg-panel pt-16 pb-24 lg:pt-24 lg:pb-12">
      <Container>
        <div className="grid gap-12 lg:grid-cols-[1.4fr_repeat(4,1fr)]">
          <Logo onDark withTagline />
          {GROUPS.map(([title, items]) => (
            <div key={title}>
              <p className="type-eyebrow text-[color:color-mix(in_oklab,white_58%,transparent)]">
                {title}
              </p>
              <ul className="mt-4 space-y-3">
                {items.map((i) => (
                  <li key={i}>
                    <a
                      href={HREFS[i] ?? "#top"}
                      className="text-[14px] text-[color:color-mix(in_oklab,white_78%,transparent)] underline-offset-4 transition-colors duration-150 hover:text-white hover:underline"
                    >
                      {i}
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
        <div className="mt-16 border-t border-[color:color-mix(in_oklab,white_12%,transparent)] pt-6">
          <p className="text-[13px] text-[color:color-mix(in_oklab,white_62%,transparent)]">
            © 2026 Coverline, a SoluLab product. All rights reserved. · SOC 2 Type I
            certified.
          </p>
        </div>
      </Container>
    </footer>
  );
}
