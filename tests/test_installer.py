"""Behaviour tests for the standalone installer.

These run ``install.sh`` against a sandboxed ``$HOME`` and ``$INSTALL_DIR``
with a stubbed Python/pip, asserting on the resulting filesystem state
rather than on the script's source text (F-TEST-003).
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

INSTALLER = Path(__file__).parents[1] / "install.sh"

FAKE_PYTHON_SHIM = """\
#!/usr/bin/env bash
# Offline stand-in for python/pip used by the installer tests.
if [ "$1" = "--version" ]; then
    echo "Python 3.11.0"
    exit 0
fi
if [ "$1" = "-c" ]; then
    echo "3.11"
    exit 0
fi
if [ "$1" = "-m" ]; then
    mod="$2"
    shift 2
    if [ "$mod" = "pip" ]; then
        exit 0
    fi
    if [ "$mod" = "venv" ]; then
        dir="$1"
        layout="${FAKE_VENV_LAYOUT:-bin}"
        if [ "$layout" != "none" ]; then
            mkdir -p "$dir/$layout"
            cp "$FAKE_PYTHON_SHIM" "$dir/$layout/python"
            chmod +x "$dir/$layout/python"
            printf '#!/usr/bin/env bash\\necho music-cli 1.0.0\\n' \\
                > "$dir/$layout/music-cli"
            printf '#!/usr/bin/env bash\\necho mc-music-cli\\n' \\
                > "$dir/$layout/mc"
            chmod +x "$dir/$layout/music-cli" "$dir/$layout/mc"
        fi
        exit 0
    fi
fi
exit 0
"""


def _resolve(path: Path) -> Path:
    return path.resolve()


@pytest.fixture()
def sandbox(tmp_path: Path):
    """A temporary HOME plus INSTALL_DIR and a stubbed python."""
    home = tmp_path / "home"
    install_dir = tmp_path / "install"
    home.mkdir()
    shim = tmp_path / "fake-python.sh"
    shim.write_text(FAKE_PYTHON_SHIM)
    shim.chmod(0o755)
    return {
        "home": home,
        "install_dir": install_dir,
        "shim": shim,
        "local_bin": home / ".local" / "bin",
    }


def _run_installer(sandbox: dict, **extra_env: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.update(
        {
            "HOME": str(sandbox["home"]),
            "INSTALL_DIR": str(sandbox["install_dir"]),
            "PYTHON": str(sandbox["shim"]),
            "SKIP_FFMPEG": "1",
            "FAKE_PYTHON_SHIM": str(sandbox["shim"]),
        }
    )
    env.update(extra_env)
    return subprocess.run(
        ["bash", str(INSTALLER)],
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


class TestFreshInstall:
    def test_links_both_commands_into_home_bin(self, sandbox) -> None:
        proc = _run_installer(sandbox)
        assert proc.returncode == 0, proc.stderr
        for cmd in ("music-cli", "mc"):
            link = sandbox["local_bin"] / cmd
            assert link.is_symlink(), f"{cmd} was not linked into ~/.local/bin"
            target = _resolve(link)
            assert target.parent.parent == _resolve(sandbox["install_dir"])

    def test_is_idempotent_across_reinstall(self, sandbox) -> None:
        first = _run_installer(sandbox)
        assert first.returncode == 0, first.stderr
        second = _run_installer(sandbox)
        assert second.returncode == 0, second.stderr
        link = sandbox["local_bin"] / "mc"
        assert link.is_symlink()
        assert _resolve(link).parent.parent == _resolve(sandbox["install_dir"])


class TestMcClobbering:
    """F-BUG-010: the installer must not delete an unrelated 'mc'."""

    def test_existing_unrelated_mc_survives_install(self, sandbox) -> None:
        existing = sandbox["local_bin"] / "mc"
        existing.parent.mkdir(parents=True)
        existing.write_text("#!/bin/sh\necho GNU Midnight Commander\n")
        existing.chmod(0o755)

        proc = _run_installer(sandbox)

        assert proc.returncode == 0, proc.stderr
        assert existing.is_file(), "unrelated mc binary was deleted"
        assert "Midnight Commander" in existing.read_text()
        assert not existing.is_symlink()
        assert "FORCE_LINK" in proc.stdout + proc.stderr
        # music-cli itself is still linked.
        assert (sandbox["local_bin"] / "music-cli").is_symlink()

    def test_force_link_overwrites_unrelated_mc(self, sandbox) -> None:
        existing = sandbox["local_bin"] / "mc"
        existing.parent.mkdir(parents=True)
        existing.write_text("unrelated tool")

        proc = _run_installer(sandbox, FORCE_LINK="1")

        assert proc.returncode == 0, proc.stderr
        assert existing.is_symlink()
        assert _resolve(existing).parent.parent == _resolve(sandbox["install_dir"])

    def test_own_symlink_from_previous_install_is_refreshed(self, sandbox) -> None:
        first = _run_installer(sandbox)
        assert first.returncode == 0, first.stderr
        stale_target = sandbox["install_dir"] / "bin" / "mc"
        link = sandbox["local_bin"] / "mc"

        second = _run_installer(sandbox)

        assert second.returncode == 0, second.stderr
        assert link.is_symlink()
        assert os.readlink(link) == str(stale_target)


class TestWindowsScriptsLayout:
    """F-BUG-009: Windows venvs use Scripts/, not bin/."""

    def test_scripts_layout_installs_successfully(self, sandbox) -> None:
        proc = _run_installer(sandbox, FAKE_VENV_LAYOUT="Scripts")

        assert proc.returncode == 0, proc.stderr
        scripts_dir = sandbox["install_dir"] / "Scripts"
        assert (scripts_dir / "python").exists()
        for cmd in ("music-cli", "mc"):
            link = sandbox["local_bin"] / cmd
            assert link.is_symlink()
            assert _resolve(link) == _resolve(scripts_dir / cmd)

    def test_missing_interpreter_fails_with_actionable_message(
        self, sandbox
    ) -> None:
        proc = _run_installer(sandbox, FAKE_VENV_LAYOUT="none")

        assert proc.returncode != 0
        combined = proc.stdout + proc.stderr
        assert "bin/" in combined or "Scripts/" in combined


def test_shellcheck_passes() -> None:
    """shellcheck install.sh must exit 0 (issue #50 acceptance)."""
    try:
        subprocess.run(["shellcheck", "--version"], capture_output=True, check=True)
    except FileNotFoundError:
        pytest.skip("shellcheck is not installed")
    proc = subprocess.run(
        ["shellcheck", str(INSTALLER)], capture_output=True, text=True, check=False
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
