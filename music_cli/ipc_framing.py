"""Incremental JSON request framing for the music-cli daemon IPC stream."""

import asyncio
import codecs
import json

REQUEST_CHUNK_SIZE = 4096
MAX_REQUEST_SIZE = 1024 * 1024


class RequestError(ValueError):
    """An invalid, incomplete, or oversized daemon request."""


class _JSONRequestFramer:
    """Incrementally find the end of a top-level JSON object."""

    _ESCAPES = frozenset('"\\/bfnrt')
    _HEX_DIGITS = frozenset("0123456789abcdefABCDEF")

    def __init__(self) -> None:
        self._chunks: list[str] = []
        self._stack: list[str] = []
        self._started = False
        self._in_string = False
        self._escaped = False
        self._unicode_digits = 0
        self._complete = False

    def feed(self, text: str) -> bool:
        """Consume decoded text and return whether the object is complete."""
        self._chunks.append(text)

        for char in text:
            if self._complete:
                if not char.isspace():
                    raise RequestError("Invalid JSON")
                continue

            if self._in_string:
                self._consume_string_char(char)
            elif not self._started:
                self._consume_first_char(char)
            else:
                self._consume_structural_char(char)

        return self._complete

    def _consume_string_char(self, char: str) -> None:
        """Advance the string-scanning state machine by one character."""
        if self._unicode_digits:
            if char not in self._HEX_DIGITS:
                raise RequestError("Invalid JSON")
            self._unicode_digits -= 1
        elif self._escaped:
            self._consume_escape_char(char)
        elif char == "\\":
            self._escaped = True
        elif char == '"':
            self._in_string = False
        elif ord(char) < 0x20:
            raise RequestError("Invalid JSON")

    def _consume_escape_char(self, char: str) -> None:
        """Handle the character following a backslash inside a string."""
        if char == "u":
            self._unicode_digits = 4
            self._escaped = False
        elif char in self._ESCAPES:
            self._escaped = False
        else:
            raise RequestError("Invalid JSON")

    def _consume_first_char(self, char: str) -> None:
        """Accept only leading whitespace before the opening brace."""
        if char.isspace():
            return
        if char != "{":
            raise RequestError("Request must be a JSON object")
        self._started = True
        self._stack.append("}")

    def _consume_structural_char(self, char: str) -> None:
        """Track containers and strings outside of string literals."""
        if char == '"':
            self._in_string = True
        elif char in "{[":
            self._stack.append("}" if char == "{" else "]")
        elif char in "}]":
            if not self._stack or self._stack[-1] != char:
                raise RequestError("Invalid JSON")
            self._stack.pop()
            if not self._stack:
                self._complete = True

    def finish(self) -> None:
        """Reject a stream that ended before a complete object was found."""
        if not self._complete:
            raise RequestError("Incomplete JSON request")

    def text(self) -> str:
        return "".join(self._chunks)


async def read_request(
    reader: asyncio.StreamReader,
    *,
    read_timeout: float,
) -> dict | None:
    """Read one complete JSON request without relying on socket boundaries.

    ``read_timeout`` is injected by the caller so the daemon's module-level
    constant stays patchable at call time.
    """
    decoder = codecs.getincrementaldecoder("utf-8")()
    framer = _JSONRequestFramer()
    size = 0
    deadline = asyncio.get_running_loop().time() + read_timeout

    while True:
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            raise RequestError("Request timed out")
        try:
            chunk = await asyncio.wait_for(reader.read(REQUEST_CHUNK_SIZE), remaining)
        except TimeoutError as exc:
            raise RequestError("Request timed out") from exc

        if not chunk:
            try:
                text = decoder.decode(b"", final=True)
            except UnicodeDecodeError as exc:
                raise RequestError("Invalid UTF-8") from exc
            if text:
                framer.feed(text)
            if size == 0:
                return None
            framer.finish()
            break

        size += len(chunk)
        if size > MAX_REQUEST_SIZE:
            raise RequestError(f"Request too large (maximum {MAX_REQUEST_SIZE} bytes)")

        try:
            text = decoder.decode(chunk)
        except UnicodeDecodeError as exc:
            raise RequestError("Invalid UTF-8") from exc

        complete = framer.feed(text) if text else False
        # A split UTF-8 sequence may still be pending after the closing
        # brace. Read on so invalid trailing bytes are not mistaken for a
        # complete request.
        pending_utf8, _ = decoder.getstate()
        if complete and not pending_utf8:
            break

    try:
        request = json.loads(framer.text())
    except json.JSONDecodeError as exc:
        raise RequestError("Invalid JSON") from exc
    if not isinstance(request, dict):
        raise RequestError("Request must be a JSON object")
    return request
