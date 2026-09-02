"""Tests for credential and secret-file handling."""

import stat

import pytest
from pytest import fixture

from rt_tools import credentials
from rt_tools.credentials import (
    PASSWORD_FILE_ENV_VAR,
    SECRET_DIR_MODE,
    SECRET_FILE_MODE,
    fetch_password,
    load_cookies,
    read_secret_file,
    resolve_password_file,
    save_cookies,
)


@fixture
def secret_file(tmp_path):
    """Return a well-formed password file with mode 0600."""
    path = tmp_path / "password"
    path.write_text("s3cret\n")
    path.chmod(0o600)
    return path


@fixture
def no_candidates(tmp_path, monkeypatch):
    """Remove the default password file locations from the resolution order."""
    monkeypatch.delenv(PASSWORD_FILE_ENV_VAR, raising=False)
    monkeypatch.setattr(credentials, "PASSWORD_FILE_CANDIDATES", (tmp_path / "absent",))


# fetch_password: full resolution order


def test_fetch_password_prefers_explicit_file(secret_file, monkeypatch):
    """An explicit password file wins over every other source."""
    monkeypatch.setattr(credentials, "keychain_available", lambda: True)
    monkeypatch.setattr(
        credentials, "fetch_password_from_keychain", lambda user: "from-keychain"
    )
    assert fetch_password("someuser", secret_file) == "s3cret"


def test_fetch_password_falls_back_to_keychain(no_candidates, monkeypatch):
    """With no secret file present, the macOS keychain is consulted."""
    monkeypatch.setattr(credentials, "keychain_available", lambda: True)
    monkeypatch.setattr(
        credentials, "fetch_password_from_keychain", lambda user: f"kc-{user}"
    )
    assert fetch_password("someuser") == "kc-someuser"


def test_fetch_password_exits_without_any_source(no_candidates, monkeypatch):
    """On a host with no secret file and no keychain, fail rather than prompt."""
    monkeypatch.setattr(credentials, "keychain_available", lambda: False)
    with pytest.raises(SystemExit):
        fetch_password("someuser")


# resolve_password_file


def test_resolve_password_file_uses_env_var(secret_file, no_candidates, monkeypatch):
    """$RT_PASSWORD_FILE is used when no explicit file is given."""
    monkeypatch.setenv(PASSWORD_FILE_ENV_VAR, str(secret_file))
    assert resolve_password_file() == secret_file


def test_resolve_password_file_uses_candidates(secret_file, monkeypatch):
    """Default ~/.secrets locations are the third source in the order."""
    monkeypatch.delenv(PASSWORD_FILE_ENV_VAR, raising=False)
    monkeypatch.setattr(
        credentials,
        "PASSWORD_FILE_CANDIDATES",
        (secret_file.parent / "absent", secret_file),
    )
    assert resolve_password_file() == secret_file


def test_resolve_password_file_returns_none_when_absent(no_candidates):
    """Falling through to the keychain is signalled by None, not an error."""
    assert resolve_password_file() is None


def test_resolve_password_file_exits_on_missing_explicit_file(tmp_path):
    """A requested file that does not exist is an error, not a fallback."""
    with pytest.raises(SystemExit):
        resolve_password_file(tmp_path / "absent")


def test_resolve_password_file_expands_tilde(monkeypatch, tmp_path):
    """A leading ~ in the environment variable is expanded."""
    home_secret = tmp_path / "password"
    home_secret.write_text("s3cret\n")
    home_secret.chmod(0o600)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv(PASSWORD_FILE_ENV_VAR, "~/password")
    assert resolve_password_file() == home_secret


# read_secret_file and permission enforcement


def test_read_secret_file_strips_newline(secret_file):
    """The trailing newline a text editor adds is not part of the secret."""
    assert read_secret_file(secret_file) == "s3cret"


def test_read_secret_file_reads_only_first_line(secret_file):
    """Trailing comment or blank lines are ignored."""
    secret_file.write_text("s3cret\n# comment\n")
    secret_file.chmod(0o600)
    assert read_secret_file(secret_file) == "s3cret"


def test_read_secret_file_accepts_mode_400(secret_file):
    """A read-only secret file is acceptable."""
    secret_file.chmod(0o400)
    assert read_secret_file(secret_file) == "s3cret"


@pytest.mark.parametrize("mode", [0o640, 0o604, 0o644, 0o660, 0o777])
def test_read_secret_file_rejects_open_modes(secret_file, mode):
    """Any group or other permission bit disqualifies a secret file."""
    secret_file.chmod(mode)
    with pytest.raises(SystemExit):
        read_secret_file(secret_file)


def test_read_secret_file_rejects_empty_file(secret_file):
    """An empty secret file is a configuration error, not an empty password."""
    secret_file.write_text("")
    secret_file.chmod(0o600)
    with pytest.raises(SystemExit):
        read_secret_file(secret_file)


# Cookie file handling


def test_load_cookies_missing_file_returns_empty_jar(tmp_path):
    """A missing cookie file yields an empty jar rather than an error."""
    jar = load_cookies(tmp_path / "cookies.txt")
    assert len(jar) == 0


def test_load_cookies_tightens_open_permissions(tmp_path):
    """A cookie file left readable by others is tightened on load."""
    path = tmp_path / "cookies.txt"
    save_cookies(load_cookies(path))
    path.chmod(0o644)
    load_cookies(path)
    assert stat.S_IMODE(path.stat().st_mode) == SECRET_FILE_MODE


def test_save_cookies_creates_private_dir_and_file(tmp_path):
    """Cookies land in a 0700 directory as a 0600 file."""
    path = tmp_path / "rt-tools" / "cookies.txt"
    save_cookies(load_cookies(path))
    assert stat.S_IMODE(path.parent.stat().st_mode) == SECRET_DIR_MODE
    assert stat.S_IMODE(path.stat().st_mode) == SECRET_FILE_MODE


def test_save_cookies_never_exposes_file_to_others(tmp_path, monkeypatch):
    """The file is private from creation, not tightened after the fact."""
    path = tmp_path / "cookies.txt"
    jar = load_cookies(path)
    observed = []
    original_save = jar.save

    def recording_save(*args, **kwargs):
        observed.append(stat.S_IMODE(path.stat().st_mode))
        return original_save(*args, **kwargs)

    monkeypatch.setattr(jar, "save", recording_save)
    save_cookies(jar)
    assert observed == [SECRET_FILE_MODE]
