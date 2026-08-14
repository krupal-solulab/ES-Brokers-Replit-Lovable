import { createFileRoute } from "@tanstack/react-router";
import { DemoPage } from "@/components/coverline/DemoPage";

export const Route = createFileRoute("/demo")({
  head: () => ({
    meta: [
      { title: "Book a demo — Coverline" },
      {
        name: "description",
        content:
          "See Coverline match your own submissions against your carrier panel — book a walkthrough tailored to your book.",
      },
    ],
  }),
  component: DemoPage,
});
