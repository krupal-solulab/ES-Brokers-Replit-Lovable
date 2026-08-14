/**
 * Typed calls for /api/core/assistant (Backend-AI-OS, core/assistant/router.py).
 * Every answer is grounded in real, live cross-workflow data — no fixture
 * scenarios, no hardcoded submissions.
 */
import { api } from "./client";

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export interface CitationOut {
  label: string;
  itemId: string;
}

export interface ChatResponse {
  text: string;
  citations: CitationOut[];
  groundedFactCount: number;
}

interface ChatResponseWire {
  text: string;
  citations: { label: string; item_id: string }[];
  grounded_fact_count: number;
}

export async function askAssistant(message: string, history: ChatMessage[]): Promise<ChatResponse> {
  const res = await api.post<ChatResponseWire>("/api/core/assistant/chat", {
    message,
    history,
  });
  return {
    text: res.text,
    citations: res.citations.map((c) => ({ label: c.label, itemId: c.item_id })),
    groundedFactCount: res.grounded_fact_count,
  };
}

export interface OverviewRecent {
  workflow: string;
  ref: string;
}

export interface AssistantOverview {
  pendingCounts: Record<string, number>;
  recent: OverviewRecent[];
}

interface OverviewWire {
  pending_counts: Record<string, number>;
  recent: OverviewRecent[];
}

export async function getAssistantOverview(): Promise<AssistantOverview> {
  const res = await api.get<OverviewWire>("/api/core/assistant/context");
  return { pendingCounts: res.pending_counts, recent: res.recent };
}
