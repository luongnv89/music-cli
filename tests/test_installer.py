"""Regression tests for the standalone installer."""

from pathlib import Path


def test_installer_upgrades_existing_music_cli_install() -> None:
    """The installer must not leave an older package in an existing venv."""
    installer = Path(__file__).parents[1] / "install.sh"
    script = installer.read_text()

    assert '"$venv_python" -m pip install --quiet --upgrade "$pkg"' in script
