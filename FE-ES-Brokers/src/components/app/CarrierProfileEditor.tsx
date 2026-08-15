/**
 * CarrierProfileEditor — G2
 *
 * Dialog that opens when the user clicks "Edit" on a carrier row in the
 * Foundation / Matching-Ranking Core panel.  Two tabs:
 *   • Profile — view and edit all profile fields; save creates a new version.
 *   • Suggestions — pending CI suggestions (carrier_appetite_intelligence) with
 *     Approve / Dismiss actions.
 *
 * Approve triggers the CI-03 narrow metadata refresh (confidence + last_updated
 * only); the new profile version_id is shown in a success toast.
 */

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { CheckCircle2, AlertTriangle, History, Loader2, X } from "lucide-react";

import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import {
  getCarrierProfile,
  updateCarrierProfile,
  approveSuggestion,
  dismissSuggestion,
  type CarrierProfileVersion,
  type CarrierProfileUpdateIn,
} from "@/lib/api/carrierProfiles";
import { listCarrierAppetiteIntelligence } from "@/lib/api/carrierAppetiteIntelligence";

// ── Helpers ───────────────────────────────────────────────────────────────────

function confidenceBadge(c: string) {
  if (c === "high")
    return <Badge className="bg-emerald-100 text-emerald-800 border-0 text-[10px]">High</Badge>;
  if (c === "medium")
    return <Badge className="bg-amber-100 text-amber-800 border-0 text-[10px]">Medium</Badge>;
  return <Badge className="bg-red-100 text-red-800 border-0 text-[10px]">Low</Badge>;
}

function sourceBadge(s: string) {
  const labels: Record<string, string> = {
    SEED: "Seed",
    HUMAN_EDIT: "Human edit",
    CI_METADATA_REFRESH: "CI refresh",
  };
  return (
    <span className="text-[10px] text-muted-foreground rounded border border-border px-1 py-0.5">
      {labels[s] ?? s}
    </span>
  );
}

// ── Editable profile form ─────────────────────────────────────────────────────

interface ProfileFormProps {
  profile: CarrierProfileVersion;
  onSaved: () => void;
  carrierId: string;
}

function ProfileForm({ profile, onSaved, carrierId }: ProfileFormProps) {
  const qc = useQueryClient();
  const [form, setForm] = useState<CarrierProfileUpdateIn>({
    carrier_name: profile.carrier_name,
    class_codes_accepted: profile.class_codes_accepted,
    class_codes_excluded: profile.class_codes_excluded,
    states_licensed: profile.states_licensed,
    premium_band: profile.premium_band,
    submission_requirements: profile.submission_requirements,
    severity_ceiling: profile.severity_ceiling,
    appetite_confidence: profile.appetite_confidence,
    appetite_last_updated: profile.appetite_last_updated,
    historical_hit_rate_this_class: profile.historical_hit_rate_this_class,
    lines_written: profile.lines_written,
    notes: profile.notes,
    form_metadata: profile.form_metadata,
    gap_policy: profile.gap_policy,
  });

  const save = useMutation({
    mutationFn: () => updateCarrierProfile(carrierId, form),
    onSuccess: (newVersion) => {
      toast.success(`New version saved — ${newVersion.version_id.slice(0, 8)}…`);
      qc.invalidateQueries({ queryKey: ["carrier-profiles"] });
      qc.invalidateQueries({ queryKey: ["carrier-profile", carrierId] });
      onSaved();
    },
    onError: () => toast.error("Save failed — check your permissions and try again."),
  });

  function setStr(key: keyof CarrierProfileUpdateIn) {
    return (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
      setForm((f) => ({ ...f, [key]: e.target.value }));
  }

  function setCSV(key: "class_codes_accepted" | "class_codes_excluded" | "states_licensed" | "lines_written") {
    return (e: React.ChangeEvent<HTMLTextAreaElement>) =>
      setForm((f) => ({
        ...f,
        [key]: e.target.value
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean),
      }));
  }

  return (
    <div className="space-y-4 pt-1">
      {/* Version provenance */}
      <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
        <History className="h-3 w-3" />
        <span>Current version: {profile.version_id.slice(0, 8)}…</span>
        {sourceBadge(profile.source)}
        {profile.created_at && (
          <span>{new Date(profile.created_at).toLocaleDateString()}</span>
        )}
      </div>

      {/* Carrier name */}
      <div className="space-y-1">
        <Label htmlFor="carrier_name" className="text-xs font-medium">
          Carrier name
        </Label>
        <Input
          id="carrier_name"
          value={form.carrier_name}
          onChange={setStr("carrier_name")}
          className="text-sm"
        />
      </div>

      {/* Appetite confidence */}
      <div className="space-y-1">
        <Label className="text-xs font-medium">Appetite confidence</Label>
        <div className="flex gap-2">
          {(["high", "medium", "low"] as const).map((c) => (
            <button
              key={c}
              onClick={() => setForm((f) => ({ ...f, appetite_confidence: c }))}
              className={`rounded-md border px-3 py-1 text-xs capitalize transition-colors ${
                form.appetite_confidence === c
                  ? "border-foreground bg-foreground text-background"
                  : "border-border hover:bg-secondary"
              }`}
            >
              {c}
            </button>
          ))}
        </div>
      </div>

      {/* Class codes accepted */}
      <div className="space-y-1">
        <Label className="text-xs font-medium">
          Class codes accepted <span className="text-muted-foreground">(comma-separated)</span>
        </Label>
        <Textarea
          value={form.class_codes_accepted.join(", ")}
          onChange={setCSV("class_codes_accepted")}
          rows={2}
          className="text-sm font-mono"
        />
      </div>

      {/* Class codes excluded */}
      <div className="space-y-1">
        <Label className="text-xs font-medium">
          Class codes excluded <span className="text-muted-foreground">(comma-separated)</span>
        </Label>
        <Textarea
          value={form.class_codes_excluded.join(", ")}
          onChange={setCSV("class_codes_excluded")}
          rows={2}
          className="text-sm font-mono"
        />
      </div>

      {/* States licensed */}
      <div className="space-y-1">
        <Label className="text-xs font-medium">
          States licensed <span className="text-muted-foreground">(comma-separated)</span>
        </Label>
        <Textarea
          value={form.states_licensed.join(", ")}
          onChange={setCSV("states_licensed")}
          rows={2}
          className="text-sm font-mono"
        />
      </div>

      {/* Premium band */}
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1">
          <Label className="text-xs font-medium">Premium min ($)</Label>
          <Input
            type="number"
            value={form.premium_band.min}
            onChange={(e) =>
              setForm((f) => ({
                ...f,
                premium_band: { ...f.premium_band, min: parseFloat(e.target.value) || 0 },
              }))
            }
            className="text-sm"
          />
        </div>
        <div className="space-y-1">
          <Label className="text-xs font-medium">Premium max ($)</Label>
          <Input
            type="number"
            value={form.premium_band.max}
            onChange={(e) =>
              setForm((f) => ({
                ...f,
                premium_band: { ...f.premium_band, max: parseFloat(e.target.value) || 0 },
              }))
            }
            className="text-sm"
          />
        </div>
      </div>

      {/* Notes */}
      <div className="space-y-1">
        <Label className="text-xs font-medium">Notes</Label>
        <Textarea
          value={form.notes ?? ""}
          onChange={setStr("notes")}
          rows={3}
          className="text-sm"
          placeholder="Broker-visible appetite notes…"
        />
      </div>

      {/* Hit rate */}
      <div className="space-y-1">
        <Label className="text-xs font-medium">
          Historical hit rate{" "}
          <span className="text-muted-foreground">(0–1)</span>
        </Label>
        <Input
          type="number"
          step="0.01"
          min={0}
          max={1}
          value={form.historical_hit_rate_this_class}
          onChange={(e) =>
            setForm((f) => ({
              ...f,
              historical_hit_rate_this_class: parseFloat(e.target.value) || 0,
            }))
          }
          className="text-sm"
        />
      </div>

      <Button
        onClick={() => save.mutate()}
        disabled={save.isPending}
        className="w-full"
        size="sm"
      >
        {save.isPending && <Loader2 className="mr-2 h-3 w-3 animate-spin" />}
        Save — creates new version
      </Button>
    </div>
  );
}

// ── Suggestion inbox ──────────────────────────────────────────────────────────

interface SuggestionInboxProps {
  carrierId: string;
}

function SuggestionInbox({ carrierId }: SuggestionInboxProps) {
  const qc = useQueryClient();
  const { data: items = [], isLoading } = useQuery({
    queryKey: ["ci-items-for-carrier", carrierId],
    queryFn: async () => {
      const all = await listCarrierAppetiteIntelligence();
      return all.filter(
        (item) => item.payload?.carrier_id === carrierId && item.payload?.status === "PENDING_REVIEW",
      );
    },
  });

  const approve = useMutation({
    mutationFn: (suggestionId: string) => approveSuggestion(carrierId, suggestionId),
    onSuccess: (result) => {
      toast.success(
        result.profile_version_id
          ? `Applied — new version ${result.profile_version_id.slice(0, 8)}…`
          : "Suggestion approved",
      );
      qc.invalidateQueries({ queryKey: ["ci-items-for-carrier", carrierId] });
      qc.invalidateQueries({ queryKey: ["carrier-profile", carrierId] });
      qc.invalidateQueries({ queryKey: ["carrier-profiles"] });
    },
    onError: () => toast.error("Approve failed — check your permissions."),
  });

  const dismiss = useMutation({
    mutationFn: (suggestionId: string) => dismissSuggestion(carrierId, suggestionId),
    onSuccess: () => {
      toast.success("Suggestion dismissed");
      qc.invalidateQueries({ queryKey: ["ci-items-for-carrier", carrierId] });
    },
    onError: () => toast.error("Dismiss failed."),
  });

  if (isLoading)
    return (
      <div className="flex items-center gap-2 py-8 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" />
        Loading suggestions…
      </div>
    );

  if (items.length === 0)
    return (
      <div className="flex flex-col items-center gap-2 py-10 text-sm text-muted-foreground">
        <CheckCircle2 className="h-6 w-6 text-emerald-500" />
        No pending suggestions for this carrier
      </div>
    );

  return (
    <ul className="divide-y divide-border space-y-0 pt-1">
      {items.map((item) => {
        const p = item.payload!;
        return (
          <li key={item.id} className="py-4">
            <div className="flex items-start justify-between gap-3">
              <div className="flex-1 space-y-1">
                <div className="flex items-center gap-2 text-sm font-medium">
                  <AlertTriangle className="h-3.5 w-3.5 text-amber-500 shrink-0" />
                  {p.pattern_type === "GENUINE_INCONSISTENCY"
                    ? "Genuine inconsistency detected"
                    : p.pattern_type === "CONFIRMED_CONSISTENT"
                    ? "Confirmed consistent — metadata refresh"
                    : p.pattern_type}
                </div>
                <div className="text-[11px] text-muted-foreground">
                  Class: {p.class_code}
                  {p.metadata_refresh && (
                    <>
                      {" "}
                      · Suggested confidence:{" "}
                      <span className="font-medium capitalize">
                        {p.metadata_refresh.appetite_confidence}
                      </span>
                    </>
                  )}
                </div>
                {p.suggested_action && (
                  <p className="text-[11px] text-foreground/70 italic">{p.suggested_action}</p>
                )}
                <div className="text-[10px] text-muted-foreground">
                  {p.evidence?.length ?? 0} evidence item
                  {p.evidence?.length !== 1 ? "s" : ""}
                </div>
              </div>
              <div className="flex gap-1.5 shrink-0 pt-0.5">
                <Button
                  size="sm"
                  variant="outline"
                  className="h-7 text-[11px]"
                  onClick={() => approve.mutate(p.suggestion_id)}
                  disabled={approve.isPending || dismiss.isPending}
                >
                  {approve.isPending ? <Loader2 className="h-3 w-3 animate-spin" /> : "Approve"}
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  className="h-7 text-[11px] text-muted-foreground"
                  onClick={() => dismiss.mutate(p.suggestion_id)}
                  disabled={approve.isPending || dismiss.isPending}
                >
                  <X className="h-3 w-3" />
                </Button>
              </div>
            </div>
          </li>
        );
      })}
    </ul>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

interface CarrierProfileEditorProps {
  carrierId: string | null;
  open: boolean;
  onClose: () => void;
}

export function CarrierProfileEditor({ carrierId, open, onClose }: CarrierProfileEditorProps) {
  const [tab, setTab] = useState<"profile" | "suggestions">("profile");

  const { data, isLoading } = useQuery({
    queryKey: ["carrier-profile", carrierId],
    queryFn: () => getCarrierProfile(carrierId!),
    enabled: !!carrierId && open,
  });

  const profile = data?.current ?? null;

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-xl max-h-[85vh] flex flex-col">
        <DialogHeader>
          <DialogTitle className="text-base">
            {profile ? profile.carrier_name : "Carrier Profile"}
          </DialogTitle>
          {profile && (
            <div className="flex items-center gap-2 pt-0.5">
              {confidenceBadge(profile.appetite_confidence)}
              <span className="text-[11px] text-muted-foreground">
                {profile.carrier_id}
              </span>
            </div>
          )}
        </DialogHeader>

        {/* Tab bar */}
        <div className="flex gap-0 border-b border-border -mx-6 px-6">
          {(["profile", "suggestions"] as const).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`pb-2 pr-4 text-sm capitalize transition-colors ${
                tab === t
                  ? "border-b-2 border-foreground font-medium text-foreground"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              {t}
            </button>
          ))}
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto -mx-6 px-6 pb-4">
          {isLoading && (
            <div className="flex items-center gap-2 py-8 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              Loading profile…
            </div>
          )}

          {!isLoading && !profile && (
            <div className="py-8 text-sm text-muted-foreground text-center">
              Profile not found.
            </div>
          )}

          {!isLoading && profile && tab === "profile" && carrierId && (
            <ProfileForm profile={profile} carrierId={carrierId} onSaved={onClose} />
          )}

          {!isLoading && carrierId && tab === "suggestions" && (
            <SuggestionInbox carrierId={carrierId} />
          )}
        </div>

        <DialogFooter>
          <Button variant="ghost" size="sm" onClick={onClose}>
            Close
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
