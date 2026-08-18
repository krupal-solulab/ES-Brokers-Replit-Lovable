"""Connector interface + mock (fixtures) and live (Nango REST proxy) implementations."""

from __future__ import annotations

import base64
import hashlib
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from email.header import decode_header
from email.message import EmailMessage as MimeEmailMessage
from typing import Any, Protocol

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from core.admin.settings_override import get_effective_setting
from core.common.dtos import Ctx, RawBundle, RawDocument
from core.common.enums import DocumentKind
from core.config import Settings, get_settings
from core.ingestion.document_text import extract_text
from fixtures.loader import _classify  # reuse the same filename -> DocumentKind inference


@dataclass
class EmailMessage:
    id: str
    submission_ref: str
    subject: str
    body: str
    attachments: list[str] = field(default_factory=list)


@dataclass
class FileBlob:
    filename: str
    content: str
    kind: DocumentKind = DocumentKind.OTHER


@dataclass
class SentRef:
    to: str
    subject: str
    thread_id: str | None = None


class ConnectorService(Protocol):
    async def fetch_inbox(
        self, ctx: Ctx, since_cursor: str | None = None
    ) -> list[EmailMessage]: ...
    async def get_attachments(self, ctx: Ctx, message_id: str) -> list[FileBlob]: ...
    async def send_email(self, ctx: Ctx, message: dict[str, Any]) -> SentRef: ...
    async def to_raw_bundle(self, ctx: Ctx, message_id: str) -> RawBundle: ...
    async def append_rows(
        self, ctx: Ctx, sheet_id: str, rows: list[list[Any]], *,
        tab: str, header: list[str] | None = None,
    ) -> None: ...
    async def read_range(
        self, ctx: Ctx, sheet_id: str, range_: str, *, tab: str
    ) -> list[list[Any]]: ...
    async def put_file(
        self, ctx: Ctx, folder_id: str, filename: str, content: bytes, mime_type: str
    ) -> str: ...
    async def create_event(
        self, ctx: Ctx, event_id: str, *, summary: str, description: str,
        start_date: str, end_date: str,
    ) -> str: ...
    async def create_event(
        self, ctx: Ctx, *, summary: str, description: str, start_date: str, end_date: str,
    ) -> str: ...
    async def upload_file(self, ctx: Ctx, *, filename: str, content: str) -> str: ...
    async def send_slack_message(self, ctx: Ctx, *, channel: str, text: str) -> str: ...


class ConnectorNotConnectedError(Exception):
    """Raised by the live connector when a tenant has no active Nango connection for a
    provider yet — the caller (a router) should translate this into a 428 asking the
    user to connect the integration first, not a 500."""

    def __init__(self, provider: str) -> None:
        self.provider = provider
        super().__init__(f"no active connection for provider '{provider}'")


class MockConnectorService:
    """Serves emails + attachments from the offline ``Workflow_<n>`` fixtures. Enables
    building the whole pipeline without a live mailbox."""

    def __init__(self, workflow_n: int = 1) -> None:
        self._workflow_n = workflow_n
        self._sent: list[SentRef] = []
        self._sheet_rows: dict[tuple[str, str], list[list[Any]]] = {}
        self._files: list[tuple[str, str, bytes, str]] = []  # (folder_id, filename, content, mime)
        self._events: dict[str, dict[str, str]] = {}  # event_id -> {summary, description, start_date, end_date}
        self._calendar_events: list[dict[str, str]] = []
        self._drive_files: dict[str, str] = {}  # filename -> content
        self._slack_messages: list[dict[str, str]] = []

    def _load(self, ctx: Ctx) -> dict[str, Any]:
        from fixtures import load_workflow  # local import avoids cycle at module load

        loaded = load_workflow(
            self._workflow_n, tenant_id=ctx.tenant_id, vertical=ctx.vertical
        )
        return {ls.submission.external_ref or ls.submission.id: ls for ls in loaded}

    async def fetch_inbox(
        self, ctx: Ctx, since_cursor: str | None = None
    ) -> list[EmailMessage]:
        messages: list[EmailMessage] = []
        for ref, ls in self._load(ctx).items():
            email_doc = next((d for d in ls.documents if d.kind is DocumentKind.EMAIL), None)
            attachments = [d.filename for d in ls.documents if d.kind is not DocumentKind.EMAIL]
            messages.append(
                EmailMessage(
                    id=ref,
                    submission_ref=ref,
                    subject=ls.submission.subject or ref,
                    body=(email_doc.content if email_doc else "") or "",
                    attachments=attachments,
                )
            )
        return messages

    async def get_attachments(self, ctx: Ctx, message_id: str) -> list[FileBlob]:
        ls = self._load(ctx).get(message_id)
        if ls is None:
            return []
        return [
            FileBlob(filename=d.filename, content=d.content or "", kind=d.kind)
            for d in ls.documents
            if d.kind is not DocumentKind.EMAIL
        ]

    async def to_raw_bundle(self, ctx: Ctx, message_id: str) -> RawBundle:
        ls = self._load(ctx).get(message_id)
        if ls is None:
            raise KeyError(f"no fixture submission '{message_id}' for Workflow_{self._workflow_n}")
        email_doc = next((d for d in ls.documents if d.kind is DocumentKind.EMAIL), None)
        documents = [
            RawDocument(kind=d.kind, filename=d.filename, content=d.content or "", uri=d.uri)
            for d in ls.documents
        ]
        return RawBundle(
            submission_id=message_id,
            email_subject=ls.submission.subject or message_id,
            email_body=(email_doc.content if email_doc else None),
            documents=documents,
        )

    async def send_email(self, ctx: Ctx, message: dict[str, Any]) -> SentRef:
        """Records a send (offline). MUST only be called from a human action — never
        from the ingestion path (no auto-send)."""
        ref = SentRef(
            to=message.get("to", ""),
            subject=message.get("subject", ""),
            thread_id=message.get("thread_id"),
        )
        self._sent.append(ref)
        return ref

    async def append_rows(
        self, ctx: Ctx, sheet_id: str, rows: list[list[Any]], *,
        tab: str, header: list[str] | None = None,
    ) -> None:
        """Records rows in memory (offline), keyed per (sheet_id, tab) so mock tests
        can assert per-workflow tab isolation the same way live tabs are isolated.
        Enables tests to assert write-back happened without a live Sheets account."""
        key = (sheet_id, tab)
        if header is not None and key not in self._sheet_rows:
            self._sheet_rows[key] = [list(header)]
        self._sheet_rows.setdefault(key, []).extend(rows)

    async def read_range(
        self, ctx: Ctx, sheet_id: str, range_: str, *, tab: str
    ) -> list[list[Any]]:
        return list(self._sheet_rows.get((sheet_id, tab), []))

    async def put_file(
        self, ctx: Ctx, folder_id: str, filename: str, content: bytes, mime_type: str
    ) -> str:
        """Records the upload in memory (offline). Enables tests to assert a Drive
        upload happened without a live Drive account."""
        self._files.append((folder_id, filename, content, mime_type))
        return f"mock-file-{len(self._files)}"

    async def create_event(
        self, ctx: Ctx, event_id: str, *, summary: str, description: str,
        start_date: str, end_date: str,
    ) -> str:
        """Records the event in memory (offline), keyed by the caller's deterministic
        ``event_id`` — a repeat call with the same id overwrites in place, mirroring
        the live path's upsert semantics so mock-mode tests can assert idempotency."""
        self._events[event_id] = {
            "summary": summary, "description": description,
            "start_date": start_date, "end_date": end_date,
        }
        return event_id

    async def create_event(
        self, ctx: Ctx, *, summary: str, description: str, start_date: str, end_date: str,
    ) -> str:
        """Records the event in memory (offline) so mock tests can assert a
        reminder was created without a live Calendar account — same
        in-memory-recording precedent as ``append_rows`` above."""
        event_id = f"mock-event-{len(self._calendar_events) + 1}"
        self._calendar_events.append({
            "id": event_id, "summary": summary, "description": description,
            "start_date": start_date, "end_date": end_date,
        })
        return event_id

    async def upload_file(self, ctx: Ctx, *, filename: str, content: str) -> str:
        """Records the file in memory (offline) — same in-memory-recording
        precedent as ``append_rows``/``create_event`` above."""
        self._drive_files[filename] = content
        return f"mock-file-{filename}"

    async def send_slack_message(self, ctx: Ctx, *, channel: str, text: str) -> str:
        """Records the message in memory (offline) — same in-memory-recording
        precedent as ``append_rows``/``create_event``/``upload_file`` above."""
        message_id = f"mock-slack-{len(self._slack_messages) + 1}"
        self._slack_messages.append({"id": message_id, "channel": channel, "text": text})
        return message_id


def _b64url_to_bytes(data: str) -> bytes:
    """Gmail's base64url, un-padded -> raw bytes."""
    if not data:
        return b""
    padded = data + "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii"))


def _decode_gmail_base64(data: str) -> str:
    """Text-only resolver, used for the email body (always plain text/HTML from
    Gmail, never a file attachment). Binary content is re-encoded as plain base64
    text rather than corrupted or guessed."""
    raw = _b64url_to_bytes(data)
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return base64.b64encode(raw).decode("ascii")


def _resolve_attachment_content(filename: str, raw: bytes) -> str:
    """Real PDF/DOCX/XLSX text/form-field extraction first (document_text.py);
    falls back to the same utf-8-or-base64 behavior as the email body when
    extraction finds nothing (unsupported format, corrupt file, scanned/image-only
    PDF — never fabricated, never crashes on a bad real-world attachment)."""
    extracted = extract_text(filename, raw)
    if extracted is not None:
        return extracted
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return base64.b64encode(raw).decode("ascii")


def _find_mime_part(payload: dict[str, Any], mime_type: str) -> dict[str, Any] | None:
    if payload.get("mimeType") == mime_type:
        return payload
    for part in payload.get("parts") or []:
        found = _find_mime_part(part, mime_type)
        if found is not None:
            return found
    return None


def _iter_leaf_parts(payload: dict[str, Any]) -> list[dict[str, Any]]:
    parts = payload.get("parts")
    if not parts:
        return [payload]
    leaves: list[dict[str, Any]] = []
    for part in parts:
        leaves.extend(_iter_leaf_parts(part))
    return leaves


def _decode_header_value(value: str) -> str:
    """Gmail header values (Subject, From, ...) can be RFC 2047 MIME-encoded for
    non-ASCII characters (e.g. em dashes: ``=?UTF-8?B?...?=``) — decode each
    encoded-word so callers see readable text instead of garbled bytes."""
    parts = decode_header(value)
    decoded = []
    for text, charset in parts:
        if isinstance(text, bytes):
            decoded.append(text.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(text)
    return "".join(decoded)


def _extract_body(payload: dict[str, Any]) -> str:
    plain = _find_mime_part(payload, "text/plain")
    if plain is not None:
        return _decode_gmail_base64(plain.get("body", {}).get("data", ""))
    html = _find_mime_part(payload, "text/html")
    if html is not None:
        raw_html = _decode_gmail_base64(html.get("body", {}).get("data", ""))
        return re.sub(r"<[^>]+>", "", raw_html)
    return _decode_gmail_base64(payload.get("body", {}).get("data", ""))


def _calendar_safe_event_id(raw_id: str) -> str:
    """Google's ``events.insert``/``events.update`` ``id`` field only accepts
    base32hex characters (lowercase ``a``-``v`` and digits ``0``-``9`` — no
    hyphens, no letters ``w``-``z``, per Google's own API reference) and must be
    5-1024 characters, unique per calendar. Callers build human-readable ids like
    ``"bind-issuance-{uuid}-obligation-0"`` (hyphens, mixed alphabet) — hashing
    with SHA-1 and re-encoding as base32 (lowercased, trailing ``=`` padding
    stripped) satisfies the constraint deterministically, so the SAME raw id
    always maps to the SAME safe id (required for the GET-then-upsert idempotency
    pattern in ``create_event`` to actually find and update the existing event
    on a repeat call, rather than silently drifting to a new id each time)."""
    digest = hashlib.sha1(raw_id.encode("utf-8")).digest()  # noqa: S324 (not security-sensitive, just a stable id map)
    return base64.b32hexencode(digest).decode("ascii").lower().rstrip("=")


class LiveNangoConnectorService:
    """Live path: proxies Gmail calls through Nango for the tenant's connected mailbox
    (docs/CONNECTORS_NANGO.md). Every call resolves the tenant's ``Connection`` row
    (google-mail) first and raises ``ConnectorNotConnectedError`` if none exists."""

    def __init__(self, settings: Settings, session: AsyncSession | None = None) -> None:
        self._settings = settings  # NANGO_HOST / NANGO_SECRET_KEY / integrations
        self._session = session
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._settings.nango_host,
                headers={"Authorization": f"Bearer {self._settings.nango_secret_key}"},
                timeout=30.0,
            )
        return self._client

    async def _proxy_headers(self, ctx: Ctx, provider: str | None = None) -> dict[str, str]:
        provider = provider or self._settings.nango_integration_mail
        if self._session is None:
            raise ConnectorNotConnectedError(provider)
        from core.integrations.repository import get_connection  # avoids import-time cycle

        conn = await get_connection(self._session, ctx.tenant_id, provider)
        if conn is None or conn.status != "connected" or not conn.nango_connection_id:
            raise ConnectorNotConnectedError(provider)
        return {"Connection-Id": conn.nango_connection_id, "Provider-Config-Key": provider}

    async def fetch_inbox(
        self, ctx: Ctx, since_cursor: str | None = None
    ) -> list[EmailMessage]:
        client = self._get_client()
        headers = await self._proxy_headers(ctx)
        query = since_cursor or get_effective_setting(
            ctx.tenant_id, "nango_inbox_query", self._settings.nango_inbox_query
        )
        resp = await client.get(
            "/proxy/gmail/v1/users/me/messages", headers=headers, params={"q": query}
        )
        resp.raise_for_status()
        ids = [m["id"] for m in resp.json().get("messages", [])]

        # Metadata-only per message — real inboxes can be large, so body/attachments are
        # left blank here and fetched later (via to_raw_bundle) only for the one message
        # actually chosen, not for every message in the picker list.
        messages: list[EmailMessage] = []
        for message_id in ids:
            meta = await client.get(
                f"/proxy/gmail/v1/users/me/messages/{message_id}",
                headers=headers,
                params={"format": "metadata", "metadataHeaders": ["Subject", "From"]},
            )
            meta.raise_for_status()
            msg_headers = meta.json().get("payload", {}).get("headers", [])
            raw_subject = next(
                (h["value"] for h in msg_headers if h["name"] == "Subject"), message_id
            )
            subject = _decode_header_value(raw_subject)
            messages.append(
                EmailMessage(
                    id=message_id, submission_ref=message_id, subject=subject, body="",
                )
            )
        return messages

    async def get_attachments(self, ctx: Ctx, message_id: str) -> list[FileBlob]:
        client = self._get_client()
        headers = await self._proxy_headers(ctx)
        resp = await client.get(
            f"/proxy/gmail/v1/users/me/messages/{message_id}",
            headers=headers,
            params={"format": "full"},
        )
        resp.raise_for_status()
        payload = resp.json().get("payload", {})

        blobs: list[FileBlob] = []
        for part in _iter_leaf_parts(payload):
            filename = part.get("filename") or ""
            attachment_id = part.get("body", {}).get("attachmentId")
            if not filename or not attachment_id:
                continue
            att = await client.get(
                f"/proxy/gmail/v1/users/me/messages/{message_id}/attachments/{attachment_id}",
                headers=headers,
            )
            att.raise_for_status()
            raw = _b64url_to_bytes(att.json().get("data", ""))
            content = _resolve_attachment_content(filename, raw)
            blobs.append(FileBlob(filename=filename, content=content, kind=_classify(filename)))
        return blobs

    async def to_raw_bundle(self, ctx: Ctx, message_id: str) -> RawBundle:
        client = self._get_client()
        headers = await self._proxy_headers(ctx)
        resp = await client.get(
            f"/proxy/gmail/v1/users/me/messages/{message_id}",
            headers=headers,
            params={"format": "full"},
        )
        resp.raise_for_status()
        payload = resp.json().get("payload", {})

        body = _extract_body(payload)
        msg_headers = payload.get("headers", [])
        raw_subject = next((h["value"] for h in msg_headers if h["name"] == "Subject"), message_id)
        subject = _decode_header_value(raw_subject)
        raw_from = next((h["value"] for h in msg_headers if h["name"] == "From"), "")
        sender = _decode_header_value(raw_from) if raw_from else None
        attachments = await self.get_attachments(ctx, message_id)
        documents = [
            RawDocument(kind=a.kind, filename=a.filename, content=a.content) for a in attachments
        ]
        return RawBundle(
            submission_id=message_id, email_subject=subject, email_from=sender,
            email_body=body, documents=documents,
        )

    async def fetch_email_as_text(self, ctx: Ctx, message_id: str) -> str:
        """Real message, reconstructed as plain ``From/Subject/Date + body`` text
        — the exact shape ``quote_comparison/quote_parser.py`` already expects
        (built to parse this from the Workflow_13 fixture files, with no
        fixture-specific dependency beyond that shape). Deliberately NOT Gmail's
        raw RFC822 export (``format=raw``) — that carries MIME boundary/
        Content-Type noise the parser's header/body split was never built to
        ignore; reusing the same clean header-list + ``_extract_body`` split
        already used elsewhere in this class avoids that."""
        client = self._get_client()
        headers = await self._proxy_headers(ctx)
        resp = await client.get(
            f"/proxy/gmail/v1/users/me/messages/{message_id}",
            headers=headers,
            params={"format": "full"},
        )
        resp.raise_for_status()
        payload = resp.json().get("payload", {})
        msg_headers = payload.get("headers", [])

        def _header(name: str) -> str:
            raw = next(
                (h["value"] for h in msg_headers if h["name"].lower() == name.lower()), ""
            )
            return _decode_header_value(raw)

        body = _extract_body(payload)
        return (
            f"From: {_header('From')}\n"
            f"Subject: {_header('Subject')}\n"
            f"Date: {_header('Date')}\n\n"
            f"{body}"
        )

    async def send_email(self, ctx: Ctx, message: dict[str, Any]) -> SentRef:
        """Sends a real email via Gmail (Nango proxy). MUST only be called from a
        human-triggered action — never from the ingestion path (no auto-send)."""
        client = self._get_client()
        headers = await self._proxy_headers(ctx)

        mime = MimeEmailMessage()
        mime["To"] = message.get("to", "")
        mime["Subject"] = message.get("subject", "")
        thread_id = message.get("thread_id")
        if thread_id:
            mime["In-Reply-To"] = thread_id
        mime.set_content(message.get("body", ""))
        raw = base64.urlsafe_b64encode(mime.as_bytes()).decode("ascii")

        body: dict[str, Any] = {"raw": raw}
        if thread_id:
            body["threadId"] = thread_id
        resp = await client.post(
            "/proxy/gmail/v1/users/me/messages/send", headers=headers, json=body
        )
        resp.raise_for_status()
        sent = resp.json()
        return SentRef(
            to=message.get("to", ""),
            subject=message.get("subject", ""),
            thread_id=sent.get("threadId"),
        )

    @staticmethod
    def _quoted_range(tab: str, range_: str) -> str:
        """A1-notation requires single-quoting a sheet/tab name that contains a
        space or special char (Google's own docs: 'My Custom Sheet'!A:A) — the
        unquoted form is itself a 400 ("unable to parse range"), so every range
        this class builds goes through here rather than risking a call site that
        forgets to quote."""
        return f"'{tab}'!{range_}"

    async def _sheet_titles(self, ctx: Ctx, sheet_id: str) -> set[str]:
        """Cheap metadata-only existence check — fields= restricts the response to
        just tab titles, no grid/cell data (per the Sheets API docs)."""
        client = self._get_client()
        headers = await self._proxy_headers(ctx, self._settings.nango_integration_sheet)
        resp = await client.get(
            f"/proxy/v4/spreadsheets/{sheet_id}",
            headers=headers,
            params={"fields": "sheets.properties.title"},
        )
        resp.raise_for_status()
        return {
            s["properties"]["title"] for s in resp.json().get("sheets", []) if "properties" in s
        }

    async def _ensure_tab(
        self, ctx: Ctx, sheet_id: str, tab: str, header: list[str]
    ) -> None:
        """Creates ``tab`` (a named sheet within the spreadsheet) and writes its
        header row, but only the first time — ``values.append`` never auto-creates
        a missing tab (it 400s), so this must run before the first append. The
        header uses ``values.update`` (overwrite), never ``.append`` (which always
        inserts after the last row and would misplace/duplicate a header)."""
        if tab in await self._sheet_titles(ctx, sheet_id):
            return
        client = self._get_client()
        headers = await self._proxy_headers(ctx, self._settings.nango_integration_sheet)
        create_resp = await client.post(
            f"/proxy/v4/spreadsheets/{sheet_id}:batchUpdate",
            headers=headers,
            json={"requests": [{"addSheet": {"properties": {"title": tab}}}]},
        )
        create_resp.raise_for_status()

        last_col = chr(ord("A") + len(header) - 1) if header else "A"
        header_range = self._quoted_range(tab, f"A1:{last_col}1")
        header_resp = await client.put(
            f"/proxy/v4/spreadsheets/{sheet_id}/values/{header_range}",
            headers=headers,
            params={"valueInputOption": "USER_ENTERED"},
            json={"values": [header]},
        )
        header_resp.raise_for_status()

    async def append_rows(
        self, ctx: Ctx, sheet_id: str, rows: list[list[Any]], *,
        tab: str, header: list[str] | None = None,
    ) -> None:
        """Appends rows to a tenant's Sheets write-back target (Nango proxy). Fallback
        used when there's no PAS integration — docs/CONNECTORS_NANGO.md. Path must
        match the real Sheets API exactly (``v4/spreadsheets/...`` — no ``sheets/``
        prefix, unlike Gmail's ``gmail/v1/...``): Nango's proxy forwards the path
        verbatim onto ``sheets.googleapis.com``, it doesn't rewrite provider names.
        If ``header`` is given, ``_ensure_tab`` creates the tab + writes the header
        on the tab's first-ever write only (its own existence check decides that)."""
        if header is not None:
            await self._ensure_tab(ctx, sheet_id, tab, header)
        client = self._get_client()
        headers = await self._proxy_headers(ctx, self._settings.nango_integration_sheet)
        append_range = self._quoted_range(tab, "A1")
        resp = await client.post(
            f"/proxy/v4/spreadsheets/{sheet_id}/values/{append_range}:append",
            headers=headers,
            params={"valueInputOption": "USER_ENTERED"},
            json={"values": rows},
        )
        resp.raise_for_status()

    async def read_range(
        self, ctx: Ctx, sheet_id: str, range_: str, *, tab: str
    ) -> list[list[Any]]:
        client = self._get_client()
        headers = await self._proxy_headers(ctx, self._settings.nango_integration_sheet)
        quoted = self._quoted_range(tab, range_)
        resp = await client.get(
            f"/proxy/v4/spreadsheets/{sheet_id}/values/{quoted}", headers=headers,
        )
        resp.raise_for_status()
        return list(resp.json().get("values", []))

    async def put_file(
        self, ctx: Ctx, folder_id: str, filename: str, content: bytes, mime_type: str
    ) -> str:
        """Uploads a file to the tenant's Drive (Nango proxy) — two-call pattern
        (create metadata, then attach content), matching Nango's own official
        google-drive integration template rather than hand-rolling a
        ``multipart/related`` body through the generic proxy, which has no
        documented support and which that template itself avoids. Uploads use a
        DIFFERENT host path than metadata-only calls (``upload/drive/v3/files``,
        not ``drive/v3/files``) — confirmed against Google's own API docs, the
        same class of mistake that broke Sheets' path earlier."""
        client = self._get_client()
        headers = await self._proxy_headers(ctx, self._settings.nango_integration_drive)

        metadata: dict[str, Any] = {"name": filename}
        if folder_id:
            metadata["parents"] = [folder_id]
        create_resp = await client.post(
            "/proxy/drive/v3/files", headers=headers, json=metadata,
        )
        create_resp.raise_for_status()
        file_id = create_resp.json()["id"]

        upload_resp = await client.patch(
            f"/proxy/upload/drive/v3/files/{file_id}",
            headers={**headers, "Content-Type": mime_type},
            params={"uploadType": "media"},
            content=content,
        )
        upload_resp.raise_for_status()
        return str(file_id)

    async def create_event(
        self, ctx: Ctx, event_id: str, *, summary: str, description: str,
        start_date: str, end_date: str,
    ) -> str:
        """Creates (or updates, if ``event_id`` already exists) an all-day event on the
        tenant's primary Google Calendar (Nango proxy). Path keeps Google's own
        ``calendar/v3/...`` segment verbatim (unlike Sheets, which drops ``sheets/``) —
        confirmed against Google's own API reference and Nango's own google-calendar
        action templates, not guessed by analogy (the mistake that broke Sheets'
        path earlier). ``start_date``/``end_date`` are both inclusive calendar dates
        from the caller's point of view (``yyyy-mm-dd``) — Google's ``end.date`` is
        *exclusive*, so this method adds one day to ``end_date`` before sending.

        Google does not guarantee duplicate-``id`` collisions are caught at insert
        time (its own docs: "we cannot guarantee that ID collisions will be detected
        at event creation time") — so a naive insert-then-catch-409 isn't reliable.
        Instead this does a GET-then-upsert: check whether ``event_id`` already
        exists on the calendar, PATCH it if so, POST (insert) if not — the same
        pattern Nango's own ``add-attendee`` action template uses."""
        client = self._get_client()
        headers = await self._proxy_headers(ctx, self._settings.nango_integration_calendar)
        safe_id = _calendar_safe_event_id(event_id)
        base = f"/proxy/calendar/v3/calendars/primary/events/{safe_id}"

        end_exclusive = (date.fromisoformat(end_date) + timedelta(days=1)).isoformat()
        body = {
            "summary": summary,
            "description": description,
            "start": {"date": start_date},
            "end": {"date": end_exclusive},
        }

        existing = await client.get(base, headers=headers)
        if existing.status_code == 404:
            resp = await client.post(
                "/proxy/calendar/v3/calendars/primary/events",
                headers=headers,
                json={"id": safe_id, **body},
            )
        else:
            existing.raise_for_status()
            resp = await client.patch(base, headers=headers, json=body)
        resp.raise_for_status()
        return str(resp.json()["id"])
    async def create_event(
        self, ctx: Ctx, *, summary: str, description: str, start_date: str, end_date: str,
    ) -> str:
        """Creates a real all-day event on the tenant's connected Google Calendar
        (Nango proxy). All-day events use a bare ``date`` (YYYY-MM-DD), never
        ``dateTime`` — per the Calendar API's own distinction, this is a
        reminder/marker day, not a timed meeting. ``end.date`` is exclusive per
        that same API (a single-day event's end date is the day AFTER
        ``start_date``), which callers must already account for."""
        client = self._get_client()
        headers = await self._proxy_headers(ctx, self._settings.nango_integration_calendar)
        resp = await client.post(
            "/proxy/calendar/v3/calendars/primary/events",
            headers=headers,
            json={
                "summary": summary,
                "description": description,
                "start": {"date": start_date},
                "end": {"date": end_date},
            },
        )
        resp.raise_for_status()
        return str(resp.json().get("id", ""))

    async def upload_file(self, ctx: Ctx, *, filename: str, content: str) -> str:
        """Creates a real file on the tenant's connected Google Drive (Nango
        proxy), two calls per the Drive API's own convention (same
        create-then-write shape ``_ensure_tab``/``append_rows`` already use for
        Sheets): metadata-only create for the name, then a media upload for the
        content — simpler than constructing a multipart/related body by hand
        for a plain-text archive copy, which is all this ever needs to be."""
        client = self._get_client()
        headers = await self._proxy_headers(ctx, self._settings.nango_integration_drive)
        create_resp = await client.post(
            "/proxy/drive/v3/files", headers=headers, json={"name": filename},
        )
        create_resp.raise_for_status()
        file_id = str(create_resp.json().get("id", ""))

        upload_resp = await client.patch(
            f"/proxy/upload/drive/v3/files/{file_id}",
            headers={**headers, "Content-Type": "text/plain"},
            params={"uploadType": "media"},
            content=content.encode("utf-8"),
        )
        upload_resp.raise_for_status()
        return file_id

    async def send_slack_message(self, ctx: Ctx, *, channel: str, text: str) -> str:
        """Posts a real message via Slack's Web API (Nango proxy) —
        ``chat.postMessage``, matching the real API path exactly
        (``/api/chat.postMessage``, per Slack's own docs) the same way every
        other connector method here pins its provider's real path."""
        client = self._get_client()
        headers = await self._proxy_headers(ctx, self._settings.nango_integration_slack)
        resp = await client.post(
            "/proxy/api/chat.postMessage", headers=headers,
            json={"channel": channel, "text": text},
        )
        resp.raise_for_status()
        return str(resp.json().get("ts", ""))


def build_connector_service(
    settings: Settings | None = None,
    *,
    workflow_n: int = 1,
    session: AsyncSession | None = None,
    tenant_id: str | None = None,
) -> ConnectorService:
    """Factory: ``CONNECTORS_MODE=mock`` -> fixtures; ``live`` -> real Nango proxy.

    ``session`` is only needed by the live path (to resolve the tenant's Connection
    row) — it's optional and ignored by MockConnectorService, so every existing
    fixture-mode call site keeps working unchanged. ``tenant_id`` is optional too —
    passing it lets an admin's ``connectors_mode`` override (AP-04) take effect;
    omitting it just falls back to the env default, exactly as before.

    Deliberately does NOT fall back to mock data when a tenant's Nango connection
    is missing: every live-only call site either (a) reads/writes one SPECIFIC real
    item a human explicitly picked (an actual Gmail message id, an actual Sheets/
    Drive/Calendar write) — substituting fixture content there would silently
    fabricate real business data under a real record — or (b) is a best-effort
    write-back that already catches ``ConnectorNotConnectedError`` itself and
    degrades gracefully (see ``core/ingestion/calendar_writeback.py`` /
    ``drive_writeback.py``). Raising here and letting each call site decide is
    the safe behavior; see ``docs/CONNECTORS_NANGO.md``.
    """
    settings = settings or get_settings()
    mode = settings.connectors_mode
    if tenant_id is not None:
        mode = get_effective_setting(tenant_id, "connectors_mode", mode)
    if mode == "live":
        return LiveNangoConnectorService(settings, session)
    return MockConnectorService(workflow_n=workflow_n)
