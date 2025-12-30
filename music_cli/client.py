"""Client for communicating with the music-cli daemon."""

import json
import logging
import socket
from typing import Any

from .config import get_config

logger = logging.getLogger(__name__)

# Constants
SOCKET_BUFFER_SIZE = 4096
MAX_RESPONSE_SIZE = 10 * 1024 * 1024  # 10MB limit
DEFAULT_TIMEOUT = 10.0
AI_TIMEOUT = 300.0  # 5 minutes for AI generation


class DaemonClient:
    """Client for sending commands to the daemon."""

    def __init__(self):
        self.config = get_config()
        self.socket_path = str(self.config.socket_path)

    def send_command(
        self, command: str, args: dict | None = None, timeout: float | None = None
    ) -> dict[str, Any]:
        """Send a command to the daemon and get response.

        Args:
            command: Command name (play, stop, pause, resume, status, etc.)
            args: Command arguments
            timeout: Socket timeout in seconds (default: 10s, AI commands: 300s)

        Returns:
            Response dictionary from daemon

        Raises:
            ConnectionError: If daemon is not running
        """
        if args is None:
            args = {}

        # Use longer timeout for AI commands
        if timeout is None:
            if command == "play" and args.get("mode") == "ai":
                timeout = AI_TIMEOUT
            else:
                timeout = DEFAULT_TIMEOUT

        request = {
            "command": command,
            "args": args,
        }

        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            sock.settimeout(timeout)
            sock.connect(self.socket_path)

            sock.sendall(json.dumps(request).encode())

            # Receive response with size limit
            response_data = b""
            while len(response_data) < MAX_RESPONSE_SIZE:
                chunk = sock.recv(SOCKET_BUFFER_SIZE)
                if not chunk:
                    break
                response_data += chunk

            if len(response_data) >= MAX_RESPONSE_SIZE:
                logger.warning("Response from daemon exceeded size limit")
                return {"error": "Response too large from daemon"}

            if response_data:
                return json.loads(response_data.decode())
            else:
                return {"error": "Empty response from daemon"}

        except FileNotFoundError as e:
            raise ConnectionError("Daemon not running (socket not found)") from e
        except ConnectionRefusedError as e:
            raise ConnectionError("Daemon not running (connection refused)") from e
        except socket.timeout as e:
            raise ConnectionError("Daemon not responding (timeout)") from e
        except json.JSONDecodeError as e:
            logger.warning(f"Invalid JSON response from daemon: {e}")
            return {"error": "Invalid response from daemon"}
        finally:
            sock.close()

    def ping(self) -> bool:
        """Check if daemon is running and responsive."""
        try:
            response = self.send_command("ping")
            return response.get("status") == "ok"
        except ConnectionError:
            return False

    def play(
        self,
        mode: str = "radio",
        source: str | None = None,
        mood: str | None = None,
        auto: bool = False,
        duration: int = 30,
        index: int | None = None,
    ) -> dict:
        """Start playback.

        Args:
            mode: Playback mode (local, radio, ai, context, history)
            source: Source path/URL/name
            mood: Mood tag (happy, sad, focus, etc.)
            auto: Enable auto-play for local files
            duration: Duration for AI generation (seconds)
            index: History entry index (for mode=history)
        """
        args = {"mode": mode, "auto": auto}
        if source:
            args["source"] = source
        if mood:
            args["mood"] = mood
        if duration:
            args["duration"] = duration
        if index:
            args["index"] = index
        return self.send_command("play", args)

    def stop(self) -> dict:
        """Stop playback."""
        return self.send_command("stop")

    def pause(self) -> dict:
        """Pause playback."""
        return self.send_command("pause")

    def resume(self) -> dict:
        """Resume playback."""
        return self.send_command("resume")

    def status(self) -> dict:
        """Get current status."""
        return self.send_command("status")

    def next_track(self) -> dict:
        """Skip to next track (auto-play mode)."""
        return self.send_command("next")

    def set_volume(self, level: int) -> dict:
        """Set volume level (0-100)."""
        return self.send_command("volume", {"level": level})

    def get_volume(self) -> int:
        """Get current volume level."""
        response = self.send_command("volume")
        return response.get("volume", 80)

    def list_radios(self) -> list[dict]:
        """List available radio stations."""
        response = self.send_command("list_radios")
        return response.get("stations", [])

    def list_history(self, limit: int = 20) -> list[dict]:
        """List playback history."""
        response = self.send_command("list_history", {"limit": limit})
        return response.get("history", [])


def get_client() -> DaemonClient:
    """Get a daemon client instance."""
    return DaemonClient()
