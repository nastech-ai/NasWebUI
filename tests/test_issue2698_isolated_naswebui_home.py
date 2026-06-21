"""
Tests for issue #2698: NASTECH_HOME isolated profile mode.

When NASTECH_HOME points at a specific profile directory like ~/.nastech/profiles/user1
AND isolated mode is explicitly opted into via NASWEBUI_ISOLATED_PROFILE=1, the WebUI
should pin to that single profile: list only it, reject create/switch/delete of other
profiles, and hide multi-profile UI affordances.

Note (#4586): isolated mode now requires the explicit NASWEBUI_ISOLATED_PROFILE opt-in
in addition to the profile-shaped NASTECH_HOME — the shape alone is NOT sufficient, because a
normal single-user named profile produces the same shape. The autouse fixture below enables
the flag for this whole module (it tests the isolated-mode deployment posture); the
shape-without-flag regression is covered separately in test_issue4586_*.
"""

import os
import io
import sys
import tempfile
import types
from pathlib import Path
from unittest import mock

import pytest

try:
    import api.profiles as _profiles_mod
    from api.profiles import (
        _is_isolated_profile_mode,
        clear_request_profile,
        list_profiles_api,
        create_profile_api,
        delete_profile_api,
        get_active_profile_name,
        init_profile_state,
        set_request_profile,
        switch_profile,
    )
except ImportError:
    import pytest as _pytest
    _pytest.skip("_is_isolated_profile_mode not yet implemented in api.profiles", allow_module_level=True)


@pytest.fixture(autouse=True)
def _clear_profile_cache(monkeypatch):
    """Clear the profile list cache + enable the isolated-mode opt-in for every test."""
    monkeypatch.setenv("NASWEBUI_ISOLATED_PROFILE", "1")
    _profiles_mod._LIST_PROFILES_CACHE = None
    yield
    _profiles_mod._LIST_PROFILES_CACHE = None


@pytest.fixture
def temp_nastech_home():
    """Create a temporary .nastech directory structure for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        home = Path(tmpdir) / ".nastech"
        home.mkdir()
        profiles_root = home / "profiles"
        profiles_root.mkdir()
        yield home


@pytest.fixture
def temp_single_profile():
    """Create a temporary .nastech/profiles/user1 structure for isolated mode."""
    with tempfile.TemporaryDirectory() as tmpdir:
        home = Path(tmpdir) / ".nastech"
        home.mkdir()
        profiles_root = home / "profiles"
        profiles_root.mkdir()
        user1 = profiles_root / "user1"
        user1.mkdir()
        for subdir in ["memories", "sessions", "skills", "skins", "logs", "plans", "workspace", "cron"]:
            (user1 / subdir).mkdir(exist_ok=True)
        yield user1


class TestIsolatedProfileModeDetection:
    """Test _is_isolated_profile_mode() helper."""

    def test_normal_mode_when_nastech_home_is_base(self, temp_nastech_home):
        """Normal mode when NASTECH_HOME points to base ~/.nastech."""
        with mock.patch.dict(os.environ, {"NASTECH_HOME": str(temp_nastech_home)}):
            with mock.patch("api.profiles._DEFAULT_NASTECH_HOME", temp_nastech_home):
                with mock.patch("api.profiles._INITIAL_NASTECH_HOME", str(temp_nastech_home)):
                    isolated = _is_isolated_profile_mode()
                    assert isolated is False

    def test_isolated_mode_when_nastech_home_is_profile_subdir(self, temp_single_profile):
        """Isolated mode when NASTECH_HOME points to ~/.nastech/profiles/user1."""
        assert temp_single_profile.exists()
        assert temp_single_profile.parent.name == "profiles"

        with mock.patch.dict(os.environ, {"NASTECH_HOME": str(temp_single_profile)}, clear=False):
            with mock.patch.dict(os.environ, {"NASTECH_BASE_HOME": ""}, clear=False):
                with mock.patch("api.profiles._INITIAL_NASTECH_HOME", str(temp_single_profile)):
                    isolated = _is_isolated_profile_mode()
                    assert isolated is True, f"Expected isolated mode for {temp_single_profile}"

    def test_nastech_base_home_does_not_disable_isolation(self, temp_single_profile):
        """NASTECH_BASE_HOME must not disable isolation for a profiles/<name> path."""
        base_home = temp_single_profile.parent.parent
        with mock.patch.dict(
            os.environ,
            {
                "NASTECH_HOME": str(temp_single_profile),
                "NASTECH_BASE_HOME": str(base_home),
            },
        ):
            with mock.patch("api.profiles._DEFAULT_NASTECH_HOME", base_home):
                with mock.patch("api.profiles._INITIAL_NASTECH_HOME", str(temp_single_profile)):
                    isolated = _is_isolated_profile_mode()
                    assert isolated is True


class TestListProfilesInIsolatedMode:
    """Test list_profiles_api() returns only isolated profile when in isolated mode."""

    def test_list_returns_only_isolated_profile_in_isolated_mode(self, temp_single_profile):
        """Isolated mode lists only the configured profile."""
        base_home = temp_single_profile.parent.parent
        other_profiles = base_home / "profiles"
        (other_profiles / "user2").mkdir()
        (other_profiles / "user3").mkdir()
        for prof_dir in [other_profiles / "user2", other_profiles / "user3"]:
            for subdir in ["memories", "sessions", "skills", "skins", "logs", "plans", "workspace", "cron"]:
                (prof_dir / subdir).mkdir(exist_ok=True)

        env_dict = {
            "NASTECH_HOME": str(temp_single_profile),
            "NASTECH_BASE_HOME": "",
        }
        with mock.patch.dict(os.environ, env_dict, clear=False):
            with mock.patch("api.profiles._DEFAULT_NASTECH_HOME", base_home):
                with mock.patch("api.profiles._INITIAL_NASTECH_HOME", str(temp_single_profile)):
                    with mock.patch("api.profiles._get_profile_skills_stats", return_value=(0, 0)):
                        profiles = list_profiles_api()
                        assert len(profiles) == 1
                        assert profiles[0]["name"] == "user1"


class TestProfileMutationsInIsolatedMode:
    """Test that create/delete/switch are rejected (403) in isolated mode."""

    def test_create_profile_rejected_in_isolated_mode(self, temp_single_profile):
        base_home = temp_single_profile.parent.parent
        env_dict = {
            "NASTECH_HOME": str(temp_single_profile),
            "NASTECH_BASE_HOME": "",
        }
        with mock.patch.dict(os.environ, env_dict, clear=False):
            with mock.patch("api.profiles._DEFAULT_NASTECH_HOME", base_home):
                with mock.patch("api.profiles._INITIAL_NASTECH_HOME", str(temp_single_profile)):
                    with pytest.raises(PermissionError, match=".*isolated.*|.*single.*"):
                        create_profile_api("newprofile")

    def test_delete_profile_rejected_in_isolated_mode(self, temp_single_profile):
        base_home = temp_single_profile.parent.parent
        env_dict = {
            "NASTECH_HOME": str(temp_single_profile),
            "NASTECH_BASE_HOME": "",
        }
        with mock.patch.dict(os.environ, env_dict, clear=False):
            with mock.patch("api.profiles._DEFAULT_NASTECH_HOME", base_home):
                with mock.patch("api.profiles._INITIAL_NASTECH_HOME", str(temp_single_profile)):
                    with pytest.raises(PermissionError, match=".*isolated.*|.*single.*"):
                        delete_profile_api("user1")

    def test_switch_to_different_profile_rejected(self, temp_single_profile):
        base_home = temp_single_profile.parent.parent
        env_dict = {
            "NASTECH_HOME": str(temp_single_profile),
            "NASTECH_BASE_HOME": "",
        }
        with mock.patch.dict(os.environ, env_dict, clear=False):
            with mock.patch("api.profiles._DEFAULT_NASTECH_HOME", base_home):
                with mock.patch("api.profiles._INITIAL_NASTECH_HOME", str(temp_single_profile)):
                    with pytest.raises(PermissionError, match=".*isolated.*|.*pinned.*"):
                        switch_profile("other_user")

    def test_switch_to_same_profile_idempotent(self, temp_single_profile):
        base_home = temp_single_profile.parent.parent
        env_dict = {
            "NASTECH_HOME": str(temp_single_profile),
            "NASTECH_BASE_HOME": "",
        }
        with mock.patch.dict(os.environ, env_dict, clear=False):
            with mock.patch("api.profiles._DEFAULT_NASTECH_HOME", base_home):
                with mock.patch("api.profiles._INITIAL_NASTECH_HOME", str(temp_single_profile)):
                    try:
                        switch_profile("user1")
                    except PermissionError:
                        pytest.fail("switch_profile should allow switching to the isolated profile itself")
                    except (ImportError, ValueError, RuntimeError):
                        pass


class TestNormalModePreservation:
    """Test that normal mode behavior is completely unchanged."""

    def test_normal_mode_profile_operations_work(self, temp_nastech_home):
        """Normal mode allows profile creation and deletion."""
        with mock.patch.dict(os.environ, {"NASTECH_HOME": str(temp_nastech_home)}):
            with mock.patch("api.profiles._DEFAULT_NASTECH_HOME", temp_nastech_home):
                with mock.patch("api.profiles._is_isolated_profile_mode", return_value=False):
                    try:
                        from api.profiles import create_profile_api
                        try:
                            create_profile_api("testprof1")
                        except ValueError as e:
                            assert "isolated" not in str(e).lower()
                            assert "single" not in str(e).lower()
                    except ImportError:
                        pass


def test_profiles_panel_hides_delete_controls_in_single_profile_mode():
    panels_js = (Path(__file__).resolve().parents[1] / "static" / "panels.js").read_text(encoding="utf-8")

    assert "const singleProfileMode = !!(_profilesCache && _profilesCache.single_profile_mode);" in panels_js
    assert "if (isDefault || singleProfileMode) hide(delBtn); else show(delBtn);" in panels_js
