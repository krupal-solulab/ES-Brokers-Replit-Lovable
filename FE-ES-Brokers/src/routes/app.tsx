import { createFileRoute, Outlet, redirect } from "@tanstack/react-router";
import { AppShell } from "@/components/app/AppShell";
import { getIdentity } from "@/lib/api/identity";

export const Route = createFileRoute("/app")({
  beforeLoad: () => {
    // No separate /login page — the real login lives in the existing
    // AuthDialog popup on the landing page (CoverlineLanding.tsx).
    if (!getIdentity()) {
      throw redirect({ to: "/" });
    }
  },
  head: () => ({
    meta: [
      { title: "Coverline OS — Wholesale/E&S Broker AI Operating System" },
      {
        name: "description",
        content:
          "The AI operating system for wholesale & E&S brokers — submission market matching, package assembly, retail agent communication, quote comparison, binder & issuance coordination, endorsement processing, renewal remarketing, diligent search, carrier appetite intelligence, and pipeline reporting.",
      },
      { name: "robots", content: "noindex" },
    ],
  }),
  component: () => <AppShell />,
});
