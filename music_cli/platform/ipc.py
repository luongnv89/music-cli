"""IPC abstraction for cross-platform client-server communication.

This module provides abstract interfaces and implementations for
Inter-Process Communication between the daemon and CLI client.

On Unix systems (Linux/macOS): Uses Unix domain sockets
On Windows: Uses TCP localhost connections
"""

from __future__ import annotations

import asyncio
import logging
import socket
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from pathlib import Path

logger = logging.getLogger(__name__)

# Type alias for client handler
ClientHandler = Callable[[asyncio.StreamReader, asyncio.StreamWriter], Awaitable[None]]

# Default TCP port for Windows IPC (memorable: music -> 44556)
DEFAULT_TCP_PORT = 44556
DEFAULT_TCP_HOST = "127.0.0.1"

# Buffer and size limits
SOCKET_BUFFER_SIZE = 4096
MAX_RESPONSE_SIZE = 10 * 1024 * 1024  # 10MB limit


class IPCServer(ABC):
    """Abstract IPC server interface.

    Provides a unified interface for starting a server that accepts
    client connections, regardless of the underlying transport mechanism.
    """

    def __init__(self) -> None:
        self._server: asyncio.Server | None = None

    @abstractmethod
    async def start(
        self,
        handler: ClientHandler,
        address: str | Path,
    ) -> None:
        """Start the IPC server.

        Args:
            handler: Async function to handle client connections.
                     Receives (reader, writer) streams.
            address: Server address (socket path or TCP address string).
        """

    async def serve_forever(self) -> None:
        """Serve requests until stopped."""
        if self._server:
            async with self._server:
                await self._server.serve_forever()

    async def stop(self) -> None:
        """Stop the IPC server."""
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    @abstractmethod
    def cleanup_stale(self, address: str | Path) -> None:
        """Clean up stale server resources (socket files, etc.)."""

    @abstractmethod
    def get_address_display(self, address: str | Path) -> str:
        """Get human-readable address for logging."""

    @property
    def server(self) -> asyncio.Server | None:
        """Get underlying asyncio server."""
        return self._server


class IPCClient(ABC):
    """Abstract IPC client interface.

    Provides a unified interface for connecting to the daemon server
    and sending commands, regardless of the underlying transport mechanism.
    """

    @abstractmethod
    def connect(self, address: str | Path, timeout: float) -> socket.socket:
        """Connect to IPC server.

        Args:
            address: Server address (socket path or TCP address string).
            timeout: Connection timeout in seconds.

        Returns:
            Connected socket.

        Raises:
            ConnectionError: If connection fails.
        """

    @abstractmethod
    def get_address_display(self, address: str | Path) -> str:
        """Get human-readable address for error messages."""


class UnixIPCServer(IPCServer):
    """Unix domain socket IPC server.

    Used on Linux and macOS for efficient local communication.
    """

    async def start(
        self,
        handler: ClientHandler,
        address: str | Path,
    ) -> None:
        """Start Unix socket server.

        Args:
            handler: Async function to handle client connections.
            address: Path to the Unix socket file.
        """
        socket_path = Path(address)

        # Clean up stale socket
        self.cleanup_stale(socket_path)

        self._server = await asyncio.start_unix_server(
            handler,
            path=str(socket_path),
        )

        # Set restrictive permissions (owner-only access)
        socket_path.chmod(0o600)

        logger.info(f"Unix socket server started at {socket_path}")

    async def stop(self) -> None:
        """Stop Unix socket server and clean up socket file."""
        # Get socket path before stopping server
        socket_path: Path | None = None
        if self._server and self._server.sockets:
            for sock in self._server.sockets:
                try:
                    path = sock.getsockname()
                    if isinstance(path, str):
                        socket_path = Path(path)
                        break
                except (OSError, AttributeError):
                    pass

        await super().stop()

        # Clean up socket file
        if socket_path and socket_path.exists():
            try:
                socket_path.unlink()
            except OSError:
                pass

    def cleanup_stale(self, address: str | Path) -> None:
        """Remove stale socket file."""
        socket_path = Path(address)
        if socket_path.exists():
            try:
                socket_path.unlink()
            except OSError as e:
                logger.warning(f"Could not remove stale socket: {e}")

    def get_address_display(self, address: str | Path) -> str:
        """Get human-readable address for logging."""
        return str(address)


class UnixIPCClient(IPCClient):
    """Unix domain socket IPC client.

    Used on Linux and macOS for efficient local communication.
    """

    def connect(self, address: str | Path, timeout: float) -> socket.socket:
        """Connect via Unix socket.

        Args:
            address: Path to the Unix socket file.
            timeout: Connection timeout in seconds.

        Returns:
            Connected socket.

        Raises:
            ConnectionError: If connection fails.
        """
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            sock.settimeout(timeout)
            sock.connect(str(address))
            return sock
        except FileNotFoundError as e:
            sock.close()
            raise ConnectionError("Daemon not running (socket not found)") from e
        except ConnectionRefusedError as e:
            sock.close()
            raise ConnectionError("Daemon not running (connection refused)") from e
        except TimeoutError as e:
            sock.close()
            raise ConnectionError("Daemon not responding (timeout)") from e
        except OSError as e:
            sock.close()
            raise ConnectionError(f"Connection failed: {e}") from e

    def get_address_display(self, address: str | Path) -> str:
        """Get human-readable address for error messages."""
        return f"unix://{address}"


class TCPIPCServer(IPCServer):
    """TCP localhost IPC server.

    Used on Windows where Unix domain sockets are not available
    in Python's asyncio implementation.
    """

    def __init__(self, port: int = DEFAULT_TCP_PORT, host: str = DEFAULT_TCP_HOST) -> None:
        super().__init__()
        self.port = port
        self.host = host

    async def start(
        self,
        handler: ClientHandler,
        address: str | Path,
    ) -> None:
        """Start TCP server on localhost.

        Args:
            handler: Async function to handle client connections.
            address: Ignored for TCP (uses configured port).
        """
        self._server = await asyncio.start_server(
            handler,
            host=self.host,
            port=self.port,
        )

        logger.info(f"TCP server started on {self.host}:{self.port}")

    def cleanup_stale(self, address: str | Path) -> None:
        """TCP sockets clean up automatically - no action needed."""
        pass

    def get_address_display(self, address: str | Path) -> str:
        """Get human-readable address for logging."""
        return f"tcp://{self.host}:{self.port}"


class TCPIPCClient(IPCClient):
    """TCP localhost IPC client.

    Used on Windows where Unix domain sockets are not available.
    """

    def __init__(self, port: int = DEFAULT_TCP_PORT, host: str = DEFAULT_TCP_HOST) -> None:
        self.port = port
        self.host = host

    def connect(self, address: str | Path, timeout: float) -> socket.socket:
        """Connect via TCP to localhost.

        Args:
            address: Ignored for TCP (uses configured port).
            timeout: Connection timeout in seconds.

        Returns:
            Connected socket.

        Raises:
            ConnectionError: If connection fails.
        """
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.settimeout(timeout)
            sock.connect((self.host, self.port))
            return sock
        except ConnectionRefusedError as e:
            sock.close()
            raise ConnectionError("Daemon not running (connection refused)") from e
        except TimeoutError as e:
            sock.close()
            raise ConnectionError("Daemon not responding (timeout)") from e
        except OSError as e:
            sock.close()
            raise ConnectionError(f"Connection failed: {e}") from e

    def get_address_display(self, address: str | Path) -> str:
        """Get human-readable address for error messages."""
        return f"tcp://{self.host}:{self.port}"


__all__ = [
    "IPCServer",
    "IPCClient",
    "UnixIPCServer",
    "UnixIPCClient",
    "TCPIPCServer",
    "TCPIPCClient",
    "ClientHandler",
    "DEFAULT_TCP_PORT",
    "DEFAULT_TCP_HOST",
]
