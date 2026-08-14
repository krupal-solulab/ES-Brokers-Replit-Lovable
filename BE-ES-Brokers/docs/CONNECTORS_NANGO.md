# Connectors — Gmail / Sheets / Drive / Calendar / Slack / QuickBooks via Nango

All external Google/Gmail access goes through **Nango**. Workflow code never imports Google SDKs directly — it calls the shared `ConnectorService` (in `core/ingestion`). This keeps auth, tokens, and rate-limits in one place and swappable.

## What we use it for
| Capability | Provider (Nango integration) | Used by |
|---|---|---|
| Read submission mailbox + **fetch attachments** | `google-mail` | Ingestion → Submission Triage, Renewal, Endorsement, Claims |
| **Send** broker/agent emails (on human approve) | `google-mail` | Broker/Agent Communication, requests, notices |
| Detect **replies** (for no-response follow-up) | `google-mail` | Broker/Agent Communication |
| **Sheets** bulk export (one shared spreadsheet, one tab per workflow) | `google-sheet` | All 10 MGA workflows — **implemented** |
| **Drive** bulk upload (one generated PDF per workflow export) | `google-drive` | All 10 MGA workflows — **implemented** |
| **Calendar** bulk export (one all-day event per open obligation/due-date/renewal) | `google-calendar` | Bind Issuance, Bordereau Reporting, Renewal Management — **implemented** |
| **Slack** — connect/disconnect only, no read/write wiring yet | `slack` | — |
| **QuickBooks** — connect/disconnect only, no read/write wiring yet | `quickbooks` | — |

## Model
- **One Nango `Connection` per tenant per provider.** We store the Nango `connectionId` on our `Connection` table (tenant-scoped). Tokens live in Nango, not our DB.
- The FE "Integrations" section triggers the Nango OAuth flow; the backend just uses the resulting connection.

## `ConnectorService` interface (in `core/ingestion`)
```ts
interface ConnectorService {
  // Gmail
  fetchInbox(conn, sinceCursor?): Promise<EmailMsg[]>;      // new submission emails
  getAttachments(conn, messageId): Promise<FileBlob[]>;     // → documents module
  sendEmail(conn, { to, subject, body, threadId? }): Promise<SentRef>; // only after human approve
  getThreadReplies(conn, threadId): Promise<EmailMsg[]>;    // reply detection
  // Sheets — implemented
  appendRows(ctx, sheetId, rows, { tab, header? }): Promise<void>;  // bulk export
  readRange(ctx, sheetId, range, { tab }): Promise<Row[]>;
  // Drive — implemented
  putFile(ctx, folderId, filename, content, mimeType): Promise<fileId>;
  // Calendar — implemented (Bind Issuance / Bordereau Reporting / Renewal Management only)
  createEvent(ctx, eventId, { summary, description, startDate, endDate }): Promise<eventId>;
}
```
Under the hood each method calls the Nango SDK / proxy for the right integration. Swap providers later without touching workflows.

### Sheets export & Drive upload — all 10 MGA workflows, manual bulk actions only

Every MGA workflow (Bind Issuance, Bordereau Reporting, Renewal Management,
Submission Triage, Broker Copilot, Endorsement Processing, Quoting & Rating,
Appetite Governance, Portfolio & Book, Claims Intake) exposes the same two
page-level actions:
```
POST /api/mga/<workflow>/export-sheet   → <Service>.export_all_to_sheet(session, ctx)
POST /api/mga/<workflow>/export-drive   → <Service>.export_all_to_drive(session, ctx)
```
Both are **manual, button-triggered only** — a tenant clicks the button on the
workflow's page. **Neither ever fires automatically on approve/escalate/send.**
This replaced an earlier design (Sheets auto-writing one row per approval, Drive
uploading one PDF per item on a per-item button) — that design is gone; `act()`
across all 10 workflows has zero Sheets/Drive side effects now.

**What gets exported: every item currently in that workflow's list, regardless of
review status** (pending, approved, escalated, blocked, sent, ...) — a full bulk
dump each time, not filtered to approved-only. Each workflow builds its export rows
from its own `list_rows` (or `list_drafts` for Broker Copilot — see below) — the
same row schema already used to render that workflow's list screen, not a
per-item detail fetch (avoids N+1 queries on a bulk action).

**Sheets**: one `try_append_rows` call per click with every row at once, into that
workflow's own named tab (`"Bind Issuance"`, `"Bordereau Reporting"`, `"Renewal
Management"`, `"Submission Triage"`, `"Broker Copilot"`, `"Endorsement
Processing"`, `"Quoting & Rating"`, `"Appetite Governance"`, `"Portfolio & Book"`,
`"Claims Intake"`) within **one shared spreadsheet** — never a shared default tab,
auto-created (with a header row) the first time that workflow's tab is written.
Target sheet is per-tenant, not env config: `Connection.sheet_id` on the
`google-sheet` row, set via `PATCH /api/core/integrations/connections/google-sheet/sheet-id`
— resolved by `core.ingestion.resolve_sheet_id`. An unset sheet id or unconnected
Sheets integration is a normal, audited skip (`core.ingestion.try_append_rows`),
never a failure of the click itself.

**Drive**: one PDF per click (`core/ingestion/pdf_export.py::render_bulk_summary_pdf`
— one page per item, same fields as that workflow's Sheets row), uploaded via one
`try_put_file` call. No MGA workflow has a persisted source document to push
instead — Bind Issuance/Bordereau/most others are pure structured-data pipelines
(no file, ever); Renewal/Submission Triage/Endorsement's source PDFs are fetched
from Gmail at intake but discarded right after extraction, never persisted — so a
generated summary is the only thing there is to upload. Target folder is
per-tenant: `Connection.folder_id` on the `google-drive` row, set via
`PATCH /api/core/integrations/connections/google-drive/folder-id` (mirrors the
Sheets `sheet-id` route, including URL-or-bare-ID acceptance via
`extract_folder_id`). Unlike Sheets' `sheet_id`, an unset `folder_id` is **not** a
skip condition — uploads land in the tenant's Drive root, a valid default. An
unconnected Drive integration is a normal, audited skip
(`core.ingestion.try_put_file`), never a failure of the click itself.

**`broker_copilot` naming exception**: this workflow's list method is
`list_drafts`, not `list_rows` (pre-existing, unrelated to this feature) — its
`export_all_to_sheet`/`export_all_to_drive` call `list_drafts()` explicitly rather
than the codebase pretending every workflow shares one method name.

### Calendar export — Bind Issuance, Bordereau Reporting, Renewal Management only

Unlike Sheets/Drive, Calendar is **scoped to 3 workflows, not all 10**, and is a
**per-item action, not a page-level bulk action** — every other workflow's data
either has no forward-looking deadline concept at all (Submission Triage,
Quoting & Rating, Claims Intake), or what looks like a date field isn't one
(Appetite Governance's/Portfolio & Book's `dateRange` is a data-coverage
reporting gap, not a deadline; Endorsement Processing's `effectiveDate` is a
past write-back timestamp; Broker Copilot's `deadlineRef` is derived display
text, not a source-of-truth date). Each of the 3 scoped workflows' own PRD
specifies a reminder/alert requirement without naming a mechanism (never
"calendar," always "reminder"/"persistent task"/"proactive alert") — Calendar is
the implementation this app chose for that requirement:
```
POST /api/mga/bind-issuance/{submission_id}/obligations/{obligation_index}/add-to-calendar
    → BindIssuanceService.add_obligation_to_calendar   (one obligation on one bind order)
POST /api/mga/bordereau-reporting/{submission_id}/add-to-calendar
    → BordereauService.add_to_calendar                 (one bordereau)
POST /api/mga/renewal-management/{submission_id}/add-to-calendar
    → RenewalService.add_to_calendar                   (one renewal)
```
Manual, button-triggered — same convention as Sheets/Drive — never fires from
`act()`. But unlike Sheets/Drive's one-page-level-button-covers-everything
model, Calendar has **no bulk export**: each item gets its own button (Bind
Issuance: one button **per open obligation**, since a single bind order can
have several — the FE's obligations list renders one `PerItemCalendarButton`
per open line item, not one per bind order). Always targets the tenant's
**primary** calendar (`"primary"`, a documented Google literal — no per-tenant
`calendar_id` config, unlike Sheets' `sheet_id`/Drive's `folder_id`).
- **Bind Issuance**: one event per **open** post-bind obligation clicked (MBI-07/
  FR-8), dated at the obligation's own due date. `PostBindObligation.due_date`
  is a relative offset (`"+30d"`, set at decision time — never an absolute
  date, since nothing upstream fixes a bind-approval timestamp) — resolved
  against the bind's own evaluation timestamp (`detail.activity[0].at`) at
  click time. A completed obligation has no button (nothing left to remind
  anyone about).
- **Bordereau Reporting**: one event for the clicked bordereau (BR-05/FR-7),
  dated at its own `dueDate` (already a real, parseable calendar date from the
  engine — no offset resolution needed here, unlike Bind Issuance).
- **Renewal Management**: one event for the clicked renewal (FR-1's
  60-90-day-before-expiration reminder window), dated at `today +
  daysToExpiration` — computed fresh at click time rather than trusting
  `RenewalRow.received` (an arbitrary, not-guaranteed-ISO email date), since
  `daysToExpiration` already means "days from now until expiration" at any
  point it's read.

Idempotent by design, not by accident: each event's id is deterministic
(`f"{workflow-slug}-{item-id}[-obligation-{n}]"`), so a repeat click on the same
item updates that item's existing event instead of creating a duplicate.
`create_event` does a **GET-then-upsert**, not an insert-and-catch-409 — Google's
own API docs state collision detection on a duplicate client-supplied event id
is **not guaranteed** at insert time, so a naive insert/catch-409 pattern isn't
reliable. Same pattern as Nango's own `add-attendee` reference action.

The deterministic id itself is never sent to Google verbatim — Google's
`events.insert`/`.update` `id` field only accepts base32hex (lowercase `a`-`v`
and digits `0`-`9`, no hyphens), which a human-readable id like
`"bind-issuance-{uuid}-obligation-0"` violates outright (this shipped as a real
400 in testing before being caught). `_calendar_safe_event_id` SHA-1-hashes the
raw id and re-encodes it as lowercase base32hex before every Calendar call —
deterministic (same raw id always maps to the same safe id, so the
GET-then-upsert idempotency still works), just never human-readable on the
Google side.

Mechanics confirmed against the real APIs up front, to avoid guessing wrong (the
Sheets path was originally guessed wrong by analogy to Gmail's path shape and
404'd in production before being fixed and locked down with exact-match tests):
- **Sheets** (`LiveNangoConnectorService`): `values.append` does **not**
  auto-create a missing tab (400s) — `_sheet_titles` checks existence via
  `spreadsheets.get?fields=sheets.properties.title` (metadata-only), `_ensure_tab`
  creates it via `spreadsheets.batchUpdate` (`addSheet`) then writes the header via
  `values.update` (never `.append`, which always inserts after the last row).
  Every range is single-quoted around the tab name (`'Bind Issuance'!A1`) via
  `_quoted_range` — required by A1 notation for any name containing a space.
- **Drive** (`LiveNangoConnectorService.put_file`): uploads use a **different
  host path** than metadata-only calls — `upload/drive/v3/files`, not
  `drive/v3/files`. Two simple calls, not a hand-rolled `multipart/related` body
  — matching Nango's own reference `upload-document` action: (1) `POST
  drive/v3/files` with `{name, parents: [folderId]}` (parents omitted when no
  folder id is set) → returns a file id; (2) `PATCH
  upload/drive/v3/files/{id}?uploadType=media` with the raw binary body and
  `Content-Type` set to the real MIME type. Required OAuth scope: `drive.file`
  (sufficient since every file pushed is one this app just generated).
- **Calendar** (`LiveNangoConnectorService.create_event`): unlike Sheets, the
  proxy path keeps Google's own path **verbatim, `calendar` segment included** —
  `proxy/calendar/v3/calendars/primary/events` (confirmed against Nango's own
  `google-calendar` action templates, not guessed by analogy — the mistake that
  broke Sheets' path). All-day events use `start.date`/`end.date`
  (`yyyy-mm-dd`); Google's `end.date` is **exclusive**, so a single-day event
  needs `end.date = start_date + 1 day` (`create_event` adds this itself — every
  caller passes the same inclusive start/end date it means literally). Required
  OAuth scope: `calendar.events`.

## Ingestion flow (async)
```
Nango webhook / poll (google-mail) ─► jobs queue
  worker: fetchInbox → new email? → getAttachments → documents.save()
        → create Submission → enqueue extraction job
Failure → error queue (visible), never dropped.
```

## Hard rules
- **No auto-send.** `sendEmail` is only ever called from a human-triggered action (approve & send). There must be **no code path** that sends without a preceding user action (esp. non-renewal notices).
- **Nango only.** No `googleapis` calls inside workflows or the decision cores.
- **Tenant-scoped.** Every connector call carries the tenant's connection; never a global credential.

## Env
```
NANGO_SECRET_KEY=...
NANGO_HOST=https://api.nango.dev        # or self-hosted
NANGO_INTEGRATION_MAIL=google-mail
NANGO_INTEGRATION_SHEET=google-sheet
NANGO_INTEGRATION_DRIVE=google-drive
NANGO_INTEGRATION_CALENDAR=google-calendar
NANGO_INTEGRATION_SLACK=slack
NANGO_INTEGRATION_QUICKBOOKS=quickbooks
```
Slack/QuickBooks values must match the unique integration key configured for each in the Nango dashboard.
For local dev without live Google, run `ConnectorService` in **mock mode** backed by the fixtures (see DATA_AND_FIXTURES.md) so ingestion works offline.

## Build offline → go live (per workflow, no code change)
Ingestion is the **only** thing that differs between test-data and live. Everything after it (extraction → rules → decision → LLM → review → audit) is identical. So each workflow ships in two steps:

1. **Prove on fixtures** — `CONNECTORS_MODE=mock`. `ConnectorService` serves emails + attachments from `Workflow_<N>/test_dataset`. Build the pipeline and pass the eval against `Validation_Rules_Test_Dataset.md`.
2. **Flip to live** — `CONNECTORS_MODE=live` + connect the tenant's Gmail via Nango. The **same pipeline** now runs on real broker mail. **No workflow code changes** — only the env flag + a Nango connection.

```
mock:  fixtures ──► [ extract → rules → decide → draft → review → audit ]
live:  Nango Gmail ─►[ ......... identical ......... ]
```
Because the two paths share one `ConnectorService` interface, "works on test data" → "works on live mail" is a config switch, not a rewrite. Do this workflow-by-workflow: prove Submission Triage on `Workflow_1`, then take *that* workflow live before moving on.
