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
import re
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger(__name__)

#: Total attempts per :meth:`BaseAdapter.run` (1 initial try + 2 retries).
MAX_ATTEMPTS = 3

#: Base delay in seconds; retry attempt N sleeps ``backoff_base * 2**N``.
DEFAULT_BACKOFF_BASE = 0.2

#: HTTP statuses worth retrying (timeouts, rate limits).
TRANSIENT_STATUSES = frozenset({408, 425, 429})

#: Queue/job ids that are safe to append to a poll URL path (no ``/``, ``?``,
#: ``#`` or whitespace, so a tampered cache entry cannot rewrite the request).
_JOB_ID_RE = re.compile(r"[A-Za-z0-9._-]+")


def _usable_job_id(candidate: Any) -> str | None:
    """Return ``candidate`` if it is safe to append to a poll URL path."""
    if isinstance(candidate, str) and _JOB_ID_RE.fullmatch(candidate):
        return candidate
    return None


class AdapterError(Exception):
    """Non-retryable adapter failure (bad request, failed job, timeout)."""


class TransientError(AdapterError):
    """Retryable failure (server error, rate limit)."""


class HttpStatusError(AdapterError):
    """Non-retryable failure carrying the HTTP status code structurally.

    Callers that need to branch on a specific status (e.g. the stale-job
    recovery path treating 404/410 as "job gone") must use ``exc.status``
    rather than matching the message text, which is not a stable contract.
    """

    def __init__(self, message: str, *, status: int) -> None:
        super().__init__(message)
        self.status = status


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


class BaseAdapter:
    """Common retry / poll / cache plumbing for the cloud adapters.

    Parameters
    ----------
    api_key:
        Provider credential; sent as a Bearer token and never logged.
    cache:
        Optional :class:`~music_cli.cloud.strategy_cache.DiskStrategyCache`.
    transport:
        Optional async transport override (recorded fixtures in tests). When
        omitted, an ``httpx.AsyncClient`` is created lazily on first request
        and owned by the adapter; close it with :meth:`aclose`.
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
        self._client: Any | None = None
        self._max_attempts = max(1, max_attempts)
        self._backoff_base = backoff_base
        self._poll_interval = poll_interval
        self._poll_timeout = poll_timeout

    # ------------------------------------------------------------------
    # transport
    # ------------------------------------------------------------------
    def _get_transport(self) -> Transport:
        """Return the injected transport, or build an owned httpx one."""
        if self._transport is not None:
            return self._transport
        try:
            import httpx
        except ImportError as exc:  # pragma: no cover - only without httpx
            raise AdapterError(
                "The 'httpx' package is not installed.\n"
                "Install it with: pip install 'coder-music-cli[gmi]'"
            ) from exc

        # Keep enough read time for a slow queue submission. The separate
        # poll timeout governs how long an accepted job may remain pending.
        client = httpx.AsyncClient(timeout=120.0)
        self._client = client

        async def transport(method, url, headers, payload):
            try:
                response = await client.request(method, url, headers=headers, json=payload)
            except httpx.TransportError as exc:
                # Network and timeout failures are retryable just like 5xx
                # responses. Include the exception type because httpx timeout
                # exceptions commonly have an empty string representation.
                raise TransientError(
                    f"{self.provider}: {type(exc).__name__} from {method} {url}"
                ) from exc
            try:
                body: Any = response.json()
            except ValueError:
                logger.warning("%s: non-JSON response from %s %s", self.provider, method, url)
                body = {}
            return response.status_code, body

        self._transport = transport
        return transport

    async def aclose(self) -> None:
        """Close the lazily-created httpx client (no-op with an injected transport)."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
            self._transport = None

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
        status, body = await self._get_transport()(method, url, headers or self._headers(), payload)
        if status >= 500 or status in TRANSIENT_STATUSES:
            raise TransientError(f"{self.provider}: HTTP {status} from {method} {url}")
        if status >= 400:
            raise HttpStatusError(
                f"{self.provider}: HTTP {status} from {method} {url}", status=status
            )
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
        terminal_status: str | tuple[str, ...] = "completed",
        failure_status: str | tuple[str, ...] = "failed",
    ) -> dict[str, Any]:
        """Poll an async job until it reaches a terminal state.

        Cancellation is cooperative: ``should_cancel`` is checked before each
        poll and a ``True`` return raises :class:`PollCancelledError` so
        callers can stop waiting cleanly. Genuine ``CancelledError`` (the
        enclosing task being cancelled) propagates untouched. Timing out
        raises :class:`AdapterError`; the job's pending cache entry (if any)
        stays valid, so a later call resumes polling it rather than
        submitting a duplicate.
        """
        terminal_statuses = (
            (terminal_status,) if isinstance(terminal_status, str) else terminal_status
        )
        failure_statuses = (failure_status,) if isinstance(failure_status, str) else failure_status
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self._poll_timeout
        while True:
            if should_cancel is not None and should_cancel():
                raise PollCancelledError(f"{self.provider}: job polling cancelled")
            body = await self._send("GET", url, headers=headers)
            status = body.get("status") if isinstance(body, dict) else None
            if status in terminal_statuses:
                return body
            if status in failure_statuses:
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
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "response_format": {"type": "json_object"},
            **(params or {}),
        }

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
        terminal_status: str | tuple[str, ...] = "completed",
        failure_status: str | tuple[str, ...] = "failed",
    ) -> dict[str, Any]:
        """Cache-aside wrapper around an async queue job: submit -> poll -> result.

        - A completed cache hit returns instantly, with no HTTP traffic.
        - A pending cache entry (journaled before the first poll) resumes
          polling the recorded job id instead of submitting a duplicate, so
          work survives a process restart. If a resumed job has vanished
          (404/410), the stale entry is discarded and a fresh job is
          submitted — a dead journal must not poison the key forever.
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
        resumed = False
        if cache is not None and key is not None:
            pending = cache.get(key)
            if pending is not None and pending.get("status") == "pending":
                candidate = _usable_job_id(pending.get("job_id"))
                if candidate is not None:
                    job_id = candidate
                    resumed = True
                    logger.info("%s: resuming queued job %s from cache", self.provider, job_id)

        def poll_url() -> str:
            return f"{submit_url.rstrip('/')}/{job_id}"

        async def submit() -> None:
            nonlocal job_id
            body = await self._send("POST", submit_url, submit_payload(idem), headers)
            job_id = body.get("request_id") or body.get("job_id") or body.get("id")
            if _usable_job_id(job_id) is None:
                raise AdapterError(f"{self.provider}: queue returned no usable job id: {body!r}")
            if cache is not None and key is not None:
                cache.put(
                    key,
                    {"status": "pending", "provider": self.provider, "job_id": job_id},
                )

        async def operation() -> dict[str, Any]:
            nonlocal job_id, resumed
            if job_id is None:
                await submit()
            try:
                return await self.poll(
                    poll_url(),
                    headers=headers,
                    terminal_status=terminal_status,
                    failure_status=failure_status,
                )
            except PollCancelledError:
                raise
            except AdapterError as exc:
                # A journaled job that has vanished (404/410) is stale: drop
                # it once and submit a fresh job instead of failing forever.
                # Branch on the structural status, never on message text —
                # a job *failure* payload may itself contain "HTTP 404".
                if resumed and isinstance(exc, HttpStatusError) and exc.status in (404, 410):
                    logger.warning(
                        "%s: resumed job %s is gone (%s); submitting a fresh job",
                        self.provider,
                        job_id,
                        exc,
                    )
                    job_id = None
                    resumed = False
                    await submit()
                    return await self.poll(
                        poll_url(),
                        headers=headers,
                        terminal_status=terminal_status,
                        failure_status=failure_status,
                    )
                raise

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
