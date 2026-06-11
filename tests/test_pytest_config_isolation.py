"""Regression coverage for pytest isolation of NasTech config paths."""
import os
from pathlib import Path


def test_pytest_overrides_inherited_nasmusicui_config_path():
    """A live-agent NASTECH_CONFIG_PATH must never leak into WebUI tests.

    NasTech agents commonly run with NASTECH_CONFIG_PATH pointing at the real
    ~/.nastech/config.yaml. The test harness must replace it with the isolated
    test home before product modules are imported, otherwise provider/onboarding
    tests can mutate the user's real config.
    """
    test_state_dir = Path(os.environ["NASMUSICUI_TEST_STATE_DIR"])
    assert Path(os.environ["NASTECH_CONFIG_PATH"]) == test_state_dir / "config.yaml"
