import { createFileRoute } from "@tanstack/react-router";
import { AnalyticsPage } from "@/components/app/Foundation";

export const Route = createFileRoute("/app/analytics")({
  component: AnalyticsPage,
});
