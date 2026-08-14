import type React from "react";
import { createFileRoute, notFound } from "@tanstack/react-router";
import {
  SubmissionMarketMatching,
  PackageAssembly,
  RetailAgentCopilot,
  QuoteComparison,
  BinderIssuance,
  EndorsementProcessing,
  RenewalRemarketing,
  DiligentSearchCompliance,
  CarrierAppetiteIntelligence,
  PipelineCarrierReporting,
} from "@/components/app/Workflows";

export type WorkflowSearch = Record<string, unknown>;

const map: Record<string, React.ComponentType<{ search: WorkflowSearch }>> = {
  "submission-matching": SubmissionMarketMatching,
  "package-assembly": PackageAssembly,
  "agent-copilot": RetailAgentCopilot,
  "quote-comparison": QuoteComparison,
  "binder-issuance": BinderIssuance,
  "endorsement-processing": EndorsementProcessing,
  "renewal-remarketing": RenewalRemarketing,
  "diligent-search": DiligentSearchCompliance,
  "appetite-intelligence": CarrierAppetiteIntelligence,
  "pipeline-reporting": PipelineCarrierReporting,
};

export const Route = createFileRoute("/app/workflows/$slug")({
  component: WorkflowRoute,
  notFoundComponent: () => (
    <div className="p-6 text-sm text-muted-foreground">Unknown workflow.</div>
  ),
});

function WorkflowRoute() {
  const { slug } = Route.useParams();
  const search = Route.useSearch() as WorkflowSearch;
  const Comp = map[slug];
  if (!Comp) throw notFound();
  return <Comp search={search} />;
}
