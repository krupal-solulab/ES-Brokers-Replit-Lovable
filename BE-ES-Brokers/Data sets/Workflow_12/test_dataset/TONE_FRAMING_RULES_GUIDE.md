# Tone & Framing Rules — Retail Agent Communication Copilot

**Purpose:** same role as every other rules/interpretation guide in this
project — explains how to apply the framing constraints correctly, not
just what they are. This workflow extends the tone rules established in
the MGA Broker Communication PRD (TN-01 through TN-17) into the
wholesale/E&S context; read that document first if you haven't. This
guide focuses specifically on what's different here.

---

## What carries over unchanged from the MGA Broker Communication rules

- **RA-TN-01 (= MGA TN-01):** never imply blame, suspicion, or accusation.
- **RA-TN-02 (= MGA TN-02):** always include a specific, concrete next step.
- **RA-TN-04 (= MGA TN-04):** never fabricate rapport beyond what actual relationship data supports.
- **RA-TN-16/17 (= MGA TN-16/17):** No-Response Follow-ups assume good faith and anchor urgency to real deadlines, not internal convenience.

These transfer directly — the underlying principle (preserve the
distribution relationship, don't let internal process friction become
the retail agent's problem) is identical in spirit to the MGA broker
relationship, just with the wholesaler-to-retail-agent link instead of
MGA-to-broker.

---

## What's different, and why

### RA-TN-05 — Urgency calibration must reflect actual carrier acceptance windows, not a fixed default

**The MGA version** anchored urgency to policy effective/expiration
dates, which tend to be hard, fixed deadlines. **In wholesale/E&S**,
urgency should be anchored to each carrier's actual
`acceptance_window_days` (from the Carrier Appetite Profile schema
established in the Market Matching PRD), which varies by carrier and is
often considerably longer than an MGA renewal deadline.

**Interpretation note:** do not default to a fixed "X business days =
urgent" threshold the way the MGA version could. Trigger 05 in the
sample dataset is built specifically to test this — a follow-up sent 9
days into a 45-day acceptance window should read as calm and
low-pressure ("no urgency on our end"), not use the same escalation
language a 3-days-to-expiration MGA renewal follow-up would use. Getting
this wrong in either direction has real cost: false urgency erodes trust
over time (agents learn to ignore "urgent" emails that never actually
were), while under-communicating genuine urgency risks a real placement
lapsing.

### RA-TN-06 — No Market Found: never disclose carrier-specific declination detail without explicit compliance clearance

**This is a genuinely new framing constraint with no MGA-side
equivalent.** When Market Matching returns a zero-match result, the
draft must describe the outcome at the aggregate panel level ("reviewed
against our carrier panel," "cannabis cultivation remains tightly
restricted across most of our markets") rather than naming which
specific carriers were checked or how each one responded.

**Interpretation note:** this constraint exists because carrier-level
appetite and declination information can be commercially sensitive —
both to the carrier (whose specific risk appetite is competitively
relevant information) and to the wholesale brokerage (whose carrier
relationships depend on not being seen as a conduit for sharing one
carrier's underwriting posture with the broader market). **Do not treat
this as a default-safe assumption; it must be confirmed with the design
partner's compliance/legal function during discovery** (per the
Compliance Flag embedded directly in Trigger 03's sample data) before
this communication type is used live. Until that's resolved, the
system should default to the more conservative aggregate framing shown
in Trigger 03's expected draft, not carrier-specific disclosure.

### RA-TN-07 — No Market Found: same "our constraint, not your account" separation as MGA Non-Renewal, applied to a new-business context

This directly extends the MGA PRD's TN-08 ("this isn't a reflection of
[account]" framing) but for a different underlying situation — a
new-business placement failure rather than a renewal loss. The mechanism
is the same (explicitly separate the account's own quality from the
market-access constraint), but the emotional stakes are somewhat lower
here, since there's no existing coverage being withdrawn — frame this
as "we couldn't find a fit right now" rather than borrowing the heavier
register appropriate to an existing customer losing coverage.

### RA-TN-08 — Quote/Terms Summary must connect price to specific cause, not just present a number

**The MGA version's Quote Summary (Trigger 03 in that dataset) was
always attached to a clean risk with unremarkable pricing** — there was
no pricing-justification problem to solve. In wholesale/E&S, a bindable
quote frequently comes with a rate that's genuinely elevated relative to
a clean account, precisely because E&S exists to place the risks
admitted carriers won't touch. A quote summary that presents a high
number with no context invites the agent (and their client) to assume
the wholesaler is marking up the price rather than passing through real
market pricing.

**Interpretation note:** every Quote/Terms Summary draft where pricing
context is available (per the `quote_context` field modeled in Trigger
06's trigger data) must connect the price to the specific factor driving
it — grounded and cited to the actual loss history or risk factor, per
the same grounding requirement established everywhere else in this
project, not a generic "pricing reflects risk factors" placeholder
sentence.

### RA-TN-09 — Reframe outcomes relative to the realistic alternative, when honestly true

When a quote is objectively good news relative to the realistic
counterfactual (a genuine possibility of no market at all, given how
zero-match outcomes like Trigger 03 are a real feature of this
vertical, not a hypothetical), the draft can honestly say so ("one of
the few markets willing to write this class at all... a real, bindable
quote rather than another declination"). This is **not** spin — it's
accurate context that helps the agent understand why the number looks
the way it does — but it must remain strictly honest: only use this
framing when it's actually true that alternatives were scarce, per the
grounding requirement, never as a rhetorical softener applied by
default to every priced quote.

### RA-TN-10 — Relationship-tenure-aware explanatory depth

Extends MGA TN-04/TN-07's tenure-awareness principle: a newer retail
agent relationship (per `agent_relationship_tenure` in the trigger data)
warrants a more explanatory, patient tone on pricing/market-dynamics
communications specifically, since a longtime E&S-experienced agent
already understands why this class prices the way it does, while a
newer agent may not yet have that context. This should not change the
facts presented, only the amount of explanatory framing wrapped around
them.

---

## Summary table — rule mapping to sample dataset triggers

| Trigger | Primary rules tested |
|---|---|
| 01 | RA-TN-02 (concrete next step), inherited MGA baseline tone |
| 02 | RA-TN-01, plus correct per-carrier scoping (extends Package Assembly's PA-01 per-carrier independence into agent-facing language) |
| 03 | RA-TN-06 (carrier-disclosure boundary), RA-TN-07 (constraint vs. account separation) — hardest compliance case in the set |
| 04 | Inherited MGA baseline good-news tone, no new rules |
| 05 | RA-TN-05 (urgency calibration against real acceptance windows) |
| 06 | RA-TN-08 (price-to-cause grounding), RA-TN-09 (honest relative reframing), RA-TN-10 (tenure-aware explanatory depth) — hardest pricing-communication case in the set |
