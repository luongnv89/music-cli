"""Regression tests for the standalone installer."""

from pathlib import Path


def test_installer_upgrades_existing_music_cli_install() -> None:
    """The installer must not leave an older package in an existing venv."""
    installer = Path(__file__).parents[1] / "install.sh"
    script = installer.read_text()

    # Assert on the key upgrade behaviour rather than an exact command
    # string, so a semantically-equivalent flag reorder does not fail it.
    assert '"$venv_python" -m pip install' in script
    assert "--upgrade" in script
    assert '"$pkg"' in script
