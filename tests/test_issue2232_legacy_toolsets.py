"""Regression coverage for issue #2232 legacy CLI toolset aliases."""

from unittest import mock


def test_normalize_cli_toolsets_expands_legacy_nasmusicui_alias():
    from api.config import _normalize_cli_toolsets

    assert _normalize_cli_toolsets(["nastech", "web"]) == [
        "nastech-cli",
        "nastech-api-server",
        "web",
    ]


def test_normalize_cli_toolsets_deduplicates_expanded_aliases():
    from api.config import _normalize_cli_toolsets

    assert _normalize_cli_toolsets(["nastech", "nastech-cli", "nastech-api-server"]) == [
        "nastech-cli",
        "nastech-api-server",
    ]


def test_resolve_cli_toolsets_fallback_expands_legacy_nasmusicui_alias():
    import api.config as config

    cfg = {"platform_toolsets": {"cli": ["nastech", "web"]}}
    with mock.patch("builtins.__import__", side_effect=ImportError("no nastech cli")):
        assert config._resolve_cli_toolsets(cfg) == ["nastech-cli", "nastech-api-server", "web"]
