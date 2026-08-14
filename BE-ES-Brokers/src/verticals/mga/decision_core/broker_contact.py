"""Parses a broker's real contact identity from an inbound email's Gmail "From" header
— the one piece of genuine sender identity this codebase has, since a real message's
body never contains a literal "From:" line the way fixture files do.

Originally implemented only inside ``renewal_management`` (as ``_broker_from_email``);
extracted here so every workflow that reads a broker/underwriting mailbox — Submission
Triage, Renewal Management, and eventually Endorsement Processing — parses the same way
once, rather than re-implementing (and potentially drifting from) the same regex three
times.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class BrokerContact:
    name: str
    agency: str
    tenure: str
    note: str
    email: str


def parse_broker_from_email(
    raw_from: str | None, fallback_from_field: str = "",
) -> BrokerContact:
    """Prefer the real Gmail "From" header (``raw_from``, from ``RawBundle.email_from``
    — the genuine sender identity, never inside a real message's body text) over an
    extracted ``email.from`` body field, which only exists for fixtures whose
    ``email.txt`` happens to contain a literal "From:" line."""
    frm = raw_from or fallback_from_field
    name = frm.split("<")[0].strip() or "—"
    agency = "—"
    email = ""
    m = re.search(r"[\w.+-]+@[\w.-]+", frm)
    if m:
        email = m.group(0)
        agency = email.split("@", 1)[1].split(".")[0].title()  # domain → rough agency label (GAP)
    return BrokerContact(name=name, agency=agency, tenure="—", note="", email=email)
