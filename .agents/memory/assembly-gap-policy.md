---
name: Assembly gap_policy wiring
description: How the PA-03 gap_policy field is threaded from the DB profile into assemble_package().
---

## What changed in G2

Removed `_CARRIER_POLICY_OVERRIDES` dict from assembly.py.
`_resolve_policy(gap_policy: dict | None, requirement_type: str)` now takes the carrier's DB
`gap_policy` dict directly, falling back to `_DEFAULT_POLICY = "block"` when None or missing key.

## Threading pattern

`PackageAssemblyPipeline` stores:
- `self._gap_policy: dict[str, str] | None = None`
- `self._profile_version_id: str | None = None`

Both are set by the router (which has session) BEFORE calling `pipeline.run(...)`:
```python
profile = await CarrierProfileService.get_latest(session, ctx.tenant_id, carrier_id)
pipeline._gap_policy = dict(profile.gap_policy) if profile else None
pipeline._profile_version_id = profile.version_id if profile else None
```

`decide()` passes `gap_policy=self._gap_policy` to both assemble_package call sites (live + fixture).
`package()` adds `"profile_version_id": self._profile_version_id` to the payload dict.

**Why:** `decide()` has no session in its signature (WorkflowPipeline Protocol). Same injection
pattern used for `self._is_live`. The router is the only callsite with a session available.

## NOTE: router wiring for gap_policy not yet done

The carrier_profiles router was created but the PACKAGE ASSEMBLY router does NOT yet set
`pipeline._gap_policy`. That requires updating `package_assembly/router.py` to load the profile
and inject it. Currently `_gap_policy` defaults to None → falls back to "block" (same as before G2).
This is a follow-up task.
