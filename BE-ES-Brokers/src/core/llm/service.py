"""LLMService wrapper + providers (OpenAI + mock) + citation post-validation."""

from __future__ import annotations

from typing import Protocol

from core.common.dtos import Citation, Ctx, Draft, ExtractedValue
from core.config import Settings, get_settings

# Tier → settings attribute holding the model id.
_TIER_ATTR = {
    "fast": "llm_model_fast",
    "standard": "llm_model_standard",
    "deep": "llm_model_deep",
}

_SYSTEM_PROMPT = (
    "You are an insurance operations assistant. Use ONLY the facts provided. "
    "Cite the source document for every claim. If a fact is not provided, write "
    "'not available in submitted documents' — never fabricate."
)


def _model_for_tier(settings: Settings, tier: str) -> str:
    return str(getattr(settings, _TIER_ATTR.get(tier, "llm_model_standard")))


def _facts_block(facts: list[ExtractedValue]) -> str:
    lines = []
    for f in facts:
        src = ""
        if f.citation is not None:
            src = f" [source: {f.citation.filename}"
            src += f", {f.citation.locator}]" if f.citation.locator else "]"
        lines.append(f"- {f.name}: {f.value}{src}")
    return "\n".join(lines)


class LLMProvider(Protocol):
    async def complete(self, *, model: str, system: str, user: str) -> str: ...


class MockLLMProvider:
    """Deterministic, offline provider — echoes the grounded facts. No network, no key."""

    async def complete(self, *, model: str, system: str, user: str) -> str:
        return f"[mock:{model}] Draft grounded in provided facts.\n{user}"


def _is_quota_error(exc: Exception) -> bool:
    """OpenAI insufficient_quota / 429 *billing* errors — the signals that flip
    the product-wide static-data fallback (core.data_mode reason c). A plain
    429 rate limit (retryable, not a billing problem) does NOT qualify."""
    text = str(exc)
    if (
        "insufficient_quota" in text
        or "exceeded your current quota" in text
        or "billing_hard_limit_reached" in text
    ):
        return True
    code = getattr(exc, "code", None)
    if code in ("insufficient_quota", "billing_hard_limit_reached"):
        return True
    # HTTP 402 Payment Required — unambiguous billing failure.
    return getattr(exc, "status_code", None) == 402


class OpenAIProvider:
    """Thin wrapper over the official ``openai`` async SDK. Client is created lazily so
    importing this module never requires a key."""

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        self._client: object | None = None

    def _get_client(self) -> object:
        if self._client is None:
            from openai import AsyncOpenAI

            self._client = AsyncOpenAI(api_key=self._api_key)
        return self._client

    async def complete(self, *, model: str, system: str, user: str) -> str:
        from core.data_mode import llm_quota_active, note_llm_quota_error

        # Product-wide static fallback: skip the live call entirely while the
        # quota flag is active, and set the flag (then fall back) when a live
        # call fails on billing — deterministic output, never a crash.
        if llm_quota_active():
            return await MockLLMProvider().complete(model=model, system=system, user=user)
        client = self._get_client()
        try:
            resp = await client.chat.completions.create(  # type: ignore[attr-defined]
                model=model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=0,
            )
        except Exception as exc:  # noqa: BLE001 — inspect, re-raise if not billing
            if _is_quota_error(exc):
                note_llm_quota_error()
                return await MockLLMProvider().complete(model=model, system=system, user=user)
            raise
        return resp.choices[0].message.content or ""


class LLMService:
    """Grounded drafting with model-tier routing + citation post-validation."""

    def __init__(self, provider: LLMProvider, settings: Settings | None = None) -> None:
        self._provider = provider
        self._settings = settings or get_settings()

    async def draft(
        self,
        ctx: Ctx,
        prompt: str,
        facts: list[ExtractedValue],
        *,
        tier: str = "standard",
    ) -> Draft:
        model = _model_for_tier(self._settings, tier)
        user = f"{prompt}\n\nFACTS:\n{_facts_block(facts)}"
        text = await self._provider.complete(model=model, system=_SYSTEM_PROMPT, user=user)

        # Citations are the sources of the facts we actually grounded on.
        citations = [f.citation for f in facts if f.citation is not None]
        self._validate_citations(citations, facts)
        return Draft(text=text, citations=citations)

    @staticmethod
    def _validate_citations(citations: list[Citation], facts: list[ExtractedValue]) -> None:
        """Every returned citation must trace to a provided fact — no fabricated sources."""
        allowed = {
            (f.citation.filename, f.citation.locator)
            for f in facts
            if f.citation is not None
        }
        for c in citations:
            if (c.filename, c.locator) not in allowed:
                raise ValueError(f"fabricated citation not grounded in facts: {c.filename}")


def build_llm_service(
    settings: Settings | None = None, *, tenant_id: str | None = None
) -> LLMService:
    """Factory: real OpenAI provider when a key is configured, else the mock.

    Consults ``core.data_mode``: in static data mode (effective connectors_mode
    "mock" for the tenant, or an active LLM-quota flag) NO live LLM calls are
    made — the deterministic mock provider is used, matching the fixture data
    the rest of the product serves in that mode."""
    from core.data_mode import (
        effective_connectors_mode,
        get_current_data_mode,
        llm_quota_active,
    )

    settings = settings or get_settings()
    current = get_current_data_mode()  # request-scoped, set by main.py middleware
    provider: LLMProvider
    if (
        (current is None or current.mode != "static")
        and settings.openai_api_key
        and settings.openai_api_key != "sk-..."
        and effective_connectors_mode(tenant_id) != "mock"
        and not llm_quota_active()
    ):
        provider = OpenAIProvider(settings.openai_api_key)
    else:
        provider = MockLLMProvider()
    return LLMService(provider, settings)
