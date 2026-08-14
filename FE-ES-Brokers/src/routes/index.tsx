import { createFileRoute, useNavigate } from "@tanstack/react-router";

import { login } from "@/lib/api/auth";

import { CaseStudies } from "@/components/es-landing/CaseStudy";
import { Header } from "@/components/es-landing/Header";
import { CitationProvider } from "@/components/es-landing/CitationPanel";
import { CtaModal } from "@/components/es-landing/CtaModal";
import { Footer } from "@/components/es-landing/Footer";
import {
  Hero,
  ProofBand,
  Problem,
  HowItWorks,
  MarketPlanSection,
  YourPanel,
} from "@/components/es-landing/SectionsTop";
import {
  PlacementBand,
  Trial,
  Pricing,
  Results,
  FinalCta,
  Faq,
} from "@/components/es-landing/SectionsBottom";

const TITLE = "Coverline — Know where every submission belongs";
const DESC =
  "Coverline reads the retail submission, checks it against your carrier panel's actual appetite, ranks the markets that will write it, and tells you what each carrier still needs.";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: TITLE },
      { name: "description", content: DESC },
      { property: "og:title", content: TITLE },
      { property: "og:description", content: DESC },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
      { name: "twitter:title", content: TITLE },
      { name: "twitter:description", content: DESC },
    ],
  }),
  component: Index,
});

function Index() {
  const navigate = useNavigate();

  /**
   * The marketing CTAs keep their own forms and copy; only the destination is
   * ours. Log in and Create an account are the way into the product, so both
   * run the same email -> role lookup the app's auth dialog uses and drop the
   * visitor into /app once the success state has been shown. "Book a demo" and
   * the sample market plan have no backend yet — they stay client-side, exactly
   * like the app's own /demo form.
   */
  const handleCta = async (
    kind: "login" | "signup" | "demo" | "sample",
    values: { email: string },
  ) => {
    if (kind !== "login" && kind !== "signup") return;
    await login(values.email);
    window.setTimeout(() => navigate({ to: "/app" }), 900);
  };

  return (
    <CitationProvider>
      {/* `landing-root` scopes the marketing design system (Manrope, navy/blue
          palette, light-only surfaces) to this page — see src/styles.css. The
          product UI under /app keeps its own tokens untouched. */}
      <div className="landing-root bg-background">
        <Header />
        <main>
          <Hero />
          <ProofBand />
          <Problem />
          <HowItWorks />
          <MarketPlanSection />
          <YourPanel />
          <PlacementBand />
          <Trial />
          <Pricing />
          <Results />
          <CaseStudies />
          <FinalCta />
          <Faq />
        </main>
        <Footer />
        <CtaModal onSubmit={handleCta} />
      </div>
    </CitationProvider>
  );
}
