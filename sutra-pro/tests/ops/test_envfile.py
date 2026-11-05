"""The `.env` template and its safe creation (GAP-OPS-1, gaps G03/G09)."""
import os
import stat

import pytest

from sutra_app.config import ENV_NAMES, Settings, read_env_file
from sutra_app.ops import envfile


def test_the_template_names_every_variable_as_a_comment():
    text = envfile.render_template()
    names = [line.lstrip("# ").split("=")[0] for line in text.splitlines() if line.startswith("# ") and "=" in line]
    for name in ("J2_OVERRIDE_KEY", "J2_SMTP_HOST", "J2_SMTP_PORT", "J2_SMTP_USER", "J2_SMTP_PASSWORD", "J2_SMTP_FROM"):
        assert name in names
    for field, name in ENV_NAMES.items():
        assert (name in names) == (field not in ("token", "env_file")), name        # SUTRA_TOKEN and SUTRA_ENV_FILE are not offered
    assert read_env_file_text(text) == {}                                        # nothing is live: a fresh file sets nothing
    assert "process environment only" in text


def read_env_file_text(text):
    pairs = {}
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            pairs[key] = value
    return pairs


def test_a_given_override_key_is_the_only_live_line():
    assert read_env_file_text(envfile.render_template(override_key="k-123")) == {"J2_OVERRIDE_KEY": "k-123"}


def test_create_writes_a_private_file_and_a_generated_key_is_read_by_the_settings(tmp_path):
    path = tmp_path / "sub" / ".env"
    assert envfile.create(path, generate_override_key=True) == path
    assert stat.S_IMODE(path.stat().st_mode) == 0o600 and envfile.mode_problem(path) is None
    key = read_env_file(path)["J2_OVERRIDE_KEY"]
    assert len(key) >= 24
    settings = Settings.load({}, data_dir=tmp_path / "d", env_file=path)
    assert settings.override_key.get_secret_value() == key
    other = tmp_path / "other.env"
    envfile.create(other, generate_override_key=True)
    assert read_env_file(other)["J2_OVERRIDE_KEY"] != key                       # fresh every time


def test_create_without_the_flag_leaves_the_key_unset(tmp_path):
    path = envfile.create(tmp_path / ".env")
    assert "J2_OVERRIDE_KEY" not in read_env_file(path)
    assert Settings.load({}, data_dir=tmp_path / "d", env_file=path).override_key is None


def test_create_never_overwrites_a_file_and_never_follows_a_link(tmp_path):
    path = tmp_path / ".env"
    path.write_text("MINE=1\n")
    with pytest.raises(FileExistsError):
        envfile.create(path, generate_override_key=True)
    assert path.read_text() == "MINE=1\n"
    target = tmp_path / "target"
    target.write_text("keep")
    link = tmp_path / "link.env"
    os.symlink(target, link)
    with pytest.raises(OSError):
        envfile.create(link)
    assert target.read_text() == "keep"


def test_mode_problem_names_a_readable_file_and_ignores_a_missing_one(tmp_path):
    path = tmp_path / ".env"
    path.write_text("A=1\n")
    path.chmod(0o644)
    assert "644" in envfile.mode_problem(path)
    path.chmod(0o600)
    assert envfile.mode_problem(path) is None and envfile.mode_problem(tmp_path / "none") is None
