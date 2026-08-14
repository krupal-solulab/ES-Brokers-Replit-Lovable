import type React from "react";
import { createFileRoute, notFound } from "@tanstack/react-router";
import { ExtractionCore, MatchingRankingCore } from "@/components/app/Foundation";

const map: Record<string, React.ComponentType> = {
  "extraction-core": ExtractionCore,
  "matching-core": MatchingRankingCore,
};

export const Route = createFileRoute("/app/foundation/$slug")({
  component: FoundationRoute,
});

function FoundationRoute() {
  const { slug } = Route.useParams();
  const Comp = map[slug];
  if (!Comp) throw notFound();
  return <Comp />;
}
