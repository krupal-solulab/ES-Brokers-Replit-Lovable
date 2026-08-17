---
name: Live PDF extraction dependencies
description: Why live Gmail submissions can silently lose all extracted fields, and how to install Python packages in this workspace.
---

- Live attachment text extraction (pypdf / python-docx / openpyxl) is declared in BE-ES-Brokers/pyproject.toml but the runtime env is the root `.pythonlibs`; deps declared there are NOT automatically installed. If pypdf is missing, `extract_text()` used to swallow the ImportError → attachments stored as base64 → zero extracted fields → Market Matching reports "no carrier matched" with a healthy panel. Now ImportError propagates loudly (document_text.py).
- **How to install packages here:** the packaged Python installer can fail with a nix-store permission error; `uv pip install --prefix .pythonlibs <pkgs>` from the workspace root works (UV_PROJECT_ENVIRONMENT=.pythonlibs).
- Backend serves on port **4000** (start.sh), not 8000. Stub auth: headers `x-tenant-id: demo-es`, `x-user-id`, `x-role`. Re-run a live submission with `POST /api/es/market-matching/run` body `{"submission_ref":"<gmail message id>"}` — no dedupe, it re-fetches Gmail and creates a new review item.
