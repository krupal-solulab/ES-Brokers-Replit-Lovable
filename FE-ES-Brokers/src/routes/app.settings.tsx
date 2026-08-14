import { createFileRoute } from "@tanstack/react-router";
import { SettingsPage } from "@/components/app/Foundation";

export const Route = createFileRoute("/app/settings")({
  component: SettingsPage,
});
