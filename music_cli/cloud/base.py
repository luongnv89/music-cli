"""Shared machinery for the cloud adapter layer: retries, backoff, polling.

Both ``GMIAdapter`` and ``OpenRouterAdapter`` (issue #133, plan task P1.2)
build on :class:`BaseAdapter`, which provides the transport-agnostic core:

- :meth:`BaseAdapter.run` wraps any async operation with up to three attempts
  and exponential backoff, retrying only :class:`TransientError` failures;
  ``asyncio.CancelledError`` always propagates untouched so task cancellation
  stays immediate.
- :meth:`BaseAdapter.poll` drives async queue jobs to completion with
  *cooperative* cancellation: a caller-supplied ``should_cancel`` predicate is
  checked between polls and aborts cleanly with :class:`PollCancelledError`.
- every request carries a deterministic ``Idempotency-Key`` header derived
  from (provider, model, prompt, params), so a retried request can be
  deduplicated server-side and re-found in the on-disk cache.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger(__name__)

#: Total attempts per :meth:`BaseAdapter.run` (1 initial try + 2 retries).
MAX_ATTEMPTS = 3

#: Base delay in seconds; retry attempt N sleeps ``backoff_base * 2**N``.
DEFAULT_BACKOFF_BASE = 0.2

#: HTTP statuses worth retrying (timeouts, rate limits).
TRANSIENT_STATUSES = frozenset({408, 425, 429})


class AdapterError(Exception):
    """Non-retryable adapter failure (bad request, failed job, timeout)."""


class TransientError(AdapterError):
    """Retryable failure (server error, rate limit)."""


class PollCancelledError(AdapterError):
    """The caller's cooperative-cancellation predicate fired during polling."""


# A transport is an async callable (method, url, headers, payload) ->
# (status_code, decoded-body). Adapters accept an injected transport so tests
# can replay recorded fixtures without any network access.
Transport = Callable[[str, str, dict[str, str], dict[str, Any] | None], Awaitable[tuple[int, Any]]]


def idempotency_key(provider: str, model: str, prompt: str, params: dict | None = None) -> str:
    """Deterministic idempotency key for one logical request.

    The same (provider, model, prompt, params) tuple always yields the same
    key, so retries are safe to deduplicate server-side and a completed result
    can be located again in the on-disk strategy cache.
    """
    material = json.dumps(
        [provider, model, prompt, params or {}],
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def httpx_transport() -> Transport:
    """Build the default transport from ``httpx`` (imported lazily).

    Keeps the adapter modules importable without the ``gmi`` extra installed
    (mirrors the lazy-import pattern in ``music_cli.cli.cloud_smoke``).
    """
    try:
        import httpx
    except ImportError as exc:  # pragma: no cover - exercised only without httpx
        raise AdapterError(
            "The 'httpx' package is not installed.\n"
            "Install it with: pip install 'coder-music-cli[gmi]'"
        ) from exc

    client = httpx.AsyncClient(timeout=60.0)

    async def transport(method, url, headers, payload):
        response = await client.request(method, url, headers=headers, json=payload)
        try:
            body: Any = response.json()
        except ValueError:
            body = {}
        return response.status_code, body

    return transport


class BaseAdapter:
    """Common retry / poll / cache plumbing for the cloud adapters.

    Parameters
    ----------
    api_key:
        Provider credential; sent as a Bearer token and never logged.
    cache:
        Optional :class:`~music_cli.cloud.strategy_cache.DiskStrategyCache`.
    transport:
        Optional async transport override (recorded fixtures in tests).
    """

    provider: str = ""
    base_url: str = ""

    def __init__(
        self,
        api_key: str,
        cache: Any | None = None,
        transport: Transport | None = None,
        *,
        max_attempts: int = MAX_ATTEMPTS,
        backoff_base: float = DEFAULT_BACKOFF_BASE,
        poll_interval: float = 1.0,
        poll_timeout: float = 300.0,
    ) -> None:
        self._api_key = api_key
        self._cache = cache
        self._transport = transport
        self._max_attempts = max(1, max_attempts)
        self._backoff_base = backoff_base
        self._poll_interval = poll_interval
        self._poll_timeout = poll_timeout

    # ------------------------------------------------------------------
    # transport
    # ------------------------------------------------------------------
    def _headers(self, idem: str | None = None) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        if idem is not None:
            headers["Idempotency-Key"] = idem
        return headers

    async def _send(
        self,
        method: str,
        url: str,
        payload: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        if self._transport is None:
            self._transport = httpx_transport()
        status, body = await self._transport(method, url, headers or self._headers(), payload)
        if status >= 500 or status in TRANSIENT_STATUSES:
            raise TransientError(f"{self.provider}: HTTP {status} from {method} {url}")
        if status >= 400:
            raise AdapterError(f"{self.provider}: HTTP {status} from {method} {url}")
        return body

    # ------------------------------------------------------------------
    # retries with exponential backoff
    # ------------------------------------------------------------------
    async def run(self, operation: Callable[[], Awaitable[Any]]) -> Any:
        """Run ``operation`` with up to ``max_attempts`` attempts.

        Only :class:`TransientError` is retried, with exponential backoff
        (``backoff_base * 2**attempt``). :class:`AdapterError` and
        ``asyncio.CancelledError`` propagate immediately. When every attempt
        fails, the final :class:`TransientError` is chained for context.
        """
        last: Exception | None = None
        for attempt in range(self._max_attempts):
            try:
                return await operation()
            except asyncio.CancelledError:
                raise
            except TransientError as exc:
                last = exc
                if attempt == self._max_attempts - 1:
                    break
                delay = self._backoff_base * (2**attempt)
                logger.warning(
                    "%s: transient failure (attempt %d/%d), retrying in %.3fs: %s",
                    self.provider,
                    attempt + 1,
                    self._max_attempts,
                    delay,
                    exc,
                )
                await asyncio.sleep(delay)
        raise AdapterError(
            f"{self.provider}: operation failed after {self._max_attempts} attempts"
        ) from last

    # ------------------------------------------------------------------
    # async job polling
    # ------------------------------------------------------------------
    async def poll(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        should_cancel: Callable[[], bool] | None = None,
        terminal_status: str = "completed",
        failure_status: str = "failed",
    ) -> dict[str, Any]:
        """Poll an async job until it reaches a terminal state.

        Cancellation is cooperative: ``should_cancel`` is checked before each
        poll and a ``True`` return raises :class:`PollCancelledError` so
        callers can stop waiting cleanly. Genuine ``CancelledError`` (the
        enclosing task being cancelled) propagates untouched.
        """
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self._poll_timeout
        while True:
            if should_cancel is not None and should_cancel():
                raise PollCancelledError(f"{self.provider}: job polling cancelled")
            body = await self._send("GET", url, headers=headers)
            status = body.get("status") if isinstance(body, dict) else None
            if status == terminal_status:
                return body
            if status == failure_status:
                error = body.get("error", "unknown error") if isinstance(body, dict) else body
                raise AdapterError(f"{self.provider}: job failed: {error}")
            if loop.time() >= deadline:
                raise AdapterError(
                    f"{self.provider}: job did not finish within {self._poll_timeout:g}s"
                )
            await asyncio.sleep(self._poll_interval)

    # ------------------------------------------------------------------
    # cache-aside flows
    # ------------------------------------------------------------------
    async def chat(
        self,
        *,
        model: str,
        prompt: str,
        params: dict[str, Any] | None = None,
        url: str | None = None,
        system: str | None = None,
    ) -> dict[str, Any]:
        """One OpenAI-compatible chat completion with cache + retries."""
        cache = self._cache
        key_params = dict(params or {})
        if system is not None:
            key_params["system"] = system
        key = cache.key(model, prompt, key_params) if cache is not None else None
        if cache is not None and key is not None:
            hit = cache.get(key)
            if hit is not None and hit.get("status") == "completed":
                return hit["result"]

        idem = idempotency_key(self.provider, model, prompt, key_params)
        headers = self._headers(idem)
        messages: list[dict[str, str]] = []
        if system is not None:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        payload: dict[str, Any] = {"model": model, "messages": messages, **(params or {})}

        data = await self.run(lambda: self._send("POST", url or self.base_url, payload, headers))
        result = self._chat_text(data)
        if cache is not None and key is not None:
            cache.put(key, {"status": "completed", "result": result})
        return result

    async def submit_and_poll(
        self,
        *,
        model: str,
        prompt: str,
        params: dict[str, Any] | None = None,
        submit_url: str,
        submit_payload: Callable[[str], dict[str, Any]],
        result_of: Callable[[dict[str, Any]], dict[str, Any]],
    ) -> dict[str, Any]:
        """Cache-aside wrapper around an async queue job: submit -> poll -> result.

        - A completed cache hit returns instantly, with no HTTP traffic.
        - A pending cache entry (journaled before the first poll) resumes
          polling the recorded job id instead of submitting a duplicate, so
          work survives a process restart.
        - Every submit/poll request carries the shared ``Idempotency-Key``.
        """
        cache = self._cache
        key = cache.key(model, prompt, params) if cache is not None else None
        if cache is not None and key is not None:
            hit = cache.get(key)
            if hit is not None and hit.get("status") == "completed":
                return hit["result"]

        idem = idempotency_key(self.provider, model, prompt, params)
        headers = self._headers(idem)
        job_id: str | None = None
        if cache is not None and key is not None:
            pending = cache.get(key)
            if pending is not None and pending.get("status") == "pending":
                job_id = pending.get("job_id")
                logger.info("%s: resuming queued job %s from cache", self.provider, job_id)

        def poll_url() -> str:
            return f"{submit_url.rstrip('/')}/{job_id}"

        async def operation() -> dict[str, Any]:
            nonlocal job_id
            if job_id is None:
                body = await self._send("POST", submit_url, submit_payload(idem), headers)
                job_id = body.get("request_id") or body.get("job_id") or body.get("id")
                if not job_id:
                    raise AdapterError(f"{self.provider}: queue returned no job id: {body!r}")
                if cache is not None and key is not None:
                    cache.put(
                        key,
                        {"status": "pending", "provider": self.provider, "job_id": job_id},
                    )
            return await self.poll(poll_url(), headers=headers)

        outcome = await self.run(operation)
        result = result_of(outcome)
        if cache is not None and key is not None:
            cache.put(key, {"status": "completed", "result": result})
        return result

    # ------------------------------------------------------------------
    # response shaping
    # ------------------------------------------------------------------
    @staticmethod
    def _chat_text(data: Any) -> dict[str, Any]:
        """Extract the assistant text from a chat-completions response."""
        try:
            text = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            raise AdapterError(f"unexpected chat-completions response: {data!r}") from None
        return {"text": text}
