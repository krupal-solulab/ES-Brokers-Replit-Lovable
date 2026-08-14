import { createFileRoute } from "@tanstack/react-router";
import { AssistantPage } from "@/components/app/Foundation";

export const Route = createFileRoute("/app/assistant")({
  component: AssistantPage,
});
