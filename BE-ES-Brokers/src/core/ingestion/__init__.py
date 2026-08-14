"""Ingestion — the shared ``ConnectorService`` (Nango-shaped) with a fixtures-backed
mock and a real Nango-proxy-backed live implementation, selected by
``CONNECTORS_MODE``.

Hard rules (CONNECTORS_NANGO.md): no direct Google SDKs (Gmail is only ever reached
through the Nango proxy); tenant-scoped; and **no auto-send** — ``send_email`` is
only ever invoked from a human-triggered action, never from the ingestion path.
"""

from core.ingestion.calendar_writeback import try_create_renewal_reminder
from core.ingestion.connectors import (
    ConnectorNotConnectedError,
    ConnectorService,
    EmailMessage,
    FileBlob,
    LiveNangoConnectorService,
    MockConnectorService,
    SentRef,
    build_connector_service,
)
from core.ingestion.writeback import (
    extract_folder_id,
    extract_sheet_id,
    resolve_drive_folder_id,
    resolve_sheet_id,
    try_append_rows,
    try_create_event,
    try_put_file,
)
from core.ingestion.drive_writeback import try_archive_document
from core.ingestion.slack_writeback import resolve_channel_id, try_notify_slack
from core.ingestion.writeback import extract_sheet_id, resolve_sheet_id, try_append_rows

__all__ = [
    "ConnectorNotConnectedError",
    "ConnectorService",
    "EmailMessage",
    "FileBlob",
    "LiveNangoConnectorService",
    "MockConnectorService",
    "SentRef",
    "build_connector_service",
    "extract_folder_id",
    "extract_sheet_id",
    "resolve_drive_folder_id",
    "resolve_sheet_id",
    "try_append_rows",
    "try_create_event",
    "try_put_file",
    "resolve_channel_id",
    "resolve_sheet_id",
    "try_append_rows",
    "try_archive_document",
    "try_create_renewal_reminder",
    "try_notify_slack",
]
