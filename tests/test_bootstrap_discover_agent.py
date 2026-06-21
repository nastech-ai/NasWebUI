"""Tests for `discover_agent_dir` shebang-based fallback.

When the standard candidate paths (`~/.nastech/NasTech-Agent`, `~/NasTech-Agent`,
`<webui-parent>/NasTech-Agent`, `NASWEBUI_AGENT_DIR`) don't match, bootstrap
should fall back to introspecting the `nastech` console-script's shebang —
that's a reliable pointer to the install root because the installer writes the
venv-relative interpreter path there.
"""

from __future__ import annotations

import textwrap

import bootstrap


def _make_agent_install(tmp_path, *, with_run_agent: bool = True):
    """Build a fake NasTech-Agent install with venv/bin/python3 + run_agent.py."""
    install = tmp_path / "agent"
    venv_python = install / "venv" / "bin" / "python3"
    venv_python.parent.mkdir(parents=True)
    venv_python.write_text("", encoding="utf-8")
    if with_run_agent:
        (install / "run_agent.py").write_text("", encoding="utf-8")
    return install, venv_python


def _make_nastech_cli(tmp_path, shebang_target: str | None):
    """Write a `nastech` console-script with the given shebang interpreter."""
    bin_dir = tmp_path / "user-bin"
    bin_dir.mkdir()
    nastech = bin_dir / "nastech"
    if shebang_target is None:
        nastech.write_text("not a script", encoding="utf-8")
    else:
        nastech.write_text(
            textwrap.dedent(
                f"""\
                #!{shebang_target}
                from nastech_cli.main import main
                main()
                """
            ),
            encoding="utf-8",
        )
    return nastech


def _isolate_discover_agent_dir(monkeypatch, tmp_path, nastech_path):
    """Point `which("nastech")` at our fake CLI and clear all standard candidates."""
    monkeypatch.setattr(bootstrap.shutil, "which", lambda name: str(nastech_path) if name == "nastech" else None)
    monkeypatch.setenv("NASTECH_HOME", str(tmp_path / "no-such-nastech-home"))
    monkeypatch.delenv("NASWEBUI_AGENT_DIR", raising=False)
    # Force REPO_ROOT.parent to a dir that won't accidentally contain a
    # `NasTech-Agent` sibling on the dev machine running these tests.
    monkeypatch.setattr(bootstrap, "REPO_ROOT", tmp_path / "isolated-repo-root")
    # Pin Path.home() to a directory with no `.nastech/NasTech-Agent` or
    # `NasTech-Agent` so the hard-coded `Path.home() / ".nastech" / "NasTech-Agent"`
    # / `Path.home() / "NasTech-Agent"` candidates in `discover_agent_dir()`
    # cannot pick up the dev machine's real install. Stage-313 absorbed
    # this in-stage after the original test file isolated only env vars
    # and REPO_ROOT, missing the Path.home() leakage.
    monkeypatch.setattr(bootstrap.Path, "home", classmethod(lambda cls: tmp_path / "isolated-home"))


def test_discovers_agent_dir_from_naswebui_shebang(monkeypatch, tmp_path):
    """Happy path: nastech shebang → walk up parents → find run_agent.py → return install."""
    install, venv_python = _make_agent_install(tmp_path)
    nastech = _make_nastech_cli(tmp_path, str(venv_python))
    _isolate_discover_agent_dir(monkeypatch, tmp_path, nastech)
    monkeypatch.chdir(tmp_path)  # make Path.home() candidates won't match install

    assert bootstrap.discover_agent_dir() == install.resolve()


def test_returns_none_when_naswebui_not_on_path(monkeypatch, tmp_path):
    _make_agent_install(tmp_path)  # install exists, but no `nastech` CLI to point at it
    _isolate_discover_agent_dir(monkeypatch, tmp_path, nastech_path=tmp_path / "missing")
    monkeypatch.setattr(bootstrap.shutil, "which", lambda name: None)

    assert bootstrap.discover_agent_dir() is None


def test_returns_none_when_naswebui_has_no_shebang(monkeypatch, tmp_path):
    """A `nastech` file without a #! line gives us nothing to introspect."""
    _make_agent_install(tmp_path)
    nastech = _make_nastech_cli(tmp_path, shebang_target=None)
    _isolate_discover_agent_dir(monkeypatch, tmp_path, nastech)

    assert bootstrap.discover_agent_dir() is None


def test_returns_none_when_shebang_interpreter_does_not_walk_to_run_agent(monkeypatch, tmp_path):
    """Shebang points at a system Python — no parent of /usr/bin/python3 has run_agent.py."""
    nastech = _make_nastech_cli(tmp_path, "/usr/bin/python3")
    _isolate_discover_agent_dir(monkeypatch, tmp_path, nastech)

    assert bootstrap.discover_agent_dir() is None


def test_explicit_candidate_takes_precedence_over_shebang(monkeypatch, tmp_path):
    """NASWEBUI_AGENT_DIR and the standard layout still win when present."""
    explicit_install = tmp_path / "explicit"
    (explicit_install).mkdir()
    (explicit_install / "run_agent.py").write_text("", encoding="utf-8")

    # Also set up a nastech-shebang install at a different location — this should NOT win.
    other_install, venv_python = _make_agent_install(tmp_path)
    nastech = _make_nastech_cli(tmp_path, str(venv_python))
    _isolate_discover_agent_dir(monkeypatch, tmp_path, nastech)
    monkeypatch.setenv("NASWEBUI_AGENT_DIR", str(explicit_install))

    assert bootstrap.discover_agent_dir() == explicit_install.resolve()
