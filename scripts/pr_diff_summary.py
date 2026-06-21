#!/usr/bin/env python3
"""PR Diff Summary Bot — NasTech/NasWebUI upstream-sync analyser.

Posts a structured GitHub PR comment that separates:
  * Real logic changes (added/removed behaviour, new tests, config shifts)
  * Pure brand noise (Hermes -> NasWebUI renames, comment updates, whitespace)

Usage:
    python3 scripts/pr_diff_summary.py <base_sha> <head_sha> <pr_number> <repo>

Environment:
    GH_TOKEN — GitHub token with pull-requests:write permission
"""
import json
import os
import re
import subprocess
import sys
import urllib.request
import urllib.error


BRANDING_PATTERNS = [
    r"\bhermes\b",
    r"\bHermes\b",
    r"\bHERMES\b",
    r"\bNasMusicUI\b",
    r"\bnasmusicui\b",
]

BRAND_RE = re.compile("|".join(BRANDING_PATTERNS), re.IGNORECASE)


def run(cmd: list[str]) -> str:
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    return result.stdout


def classify_diff_lines(diff: str) -> dict:
    """Split diff into logic-change lines vs pure branding noise."""
    logic_added: list[str] = []
    logic_removed: list[str] = []
    brand_lines: int = 0
    current_file = ""
    file_sections: dict[str, list[str]] = {}
    current_logic: list[str] = []

    for line in diff.splitlines():
        if line.startswith("diff --git"):
            if current_file and current_logic:
                file_sections[current_file] = current_logic[:]
            current_file = line.split(" b/")[-1] if " b/" in line else line
            current_logic = []
            continue
        if line.startswith("+++") or line.startswith("---") or line.startswith("@@"):
            continue
        if not line or line[0] not in ("+", "-"):
            continue

        sign = line[0]
        content = line[1:]

        if BRAND_RE.search(content) and not content.strip().startswith("#"):
            brand_lines += 1
            continue

        if content.strip() in ("", "---", "+++"):
            continue

        if sign == "+":
            logic_added.append(content.rstrip())
            current_logic.append(line)
        elif sign == "-":
            logic_removed.append(content.rstrip())
            current_logic.append(line)

    if current_file and current_logic:
        file_sections[current_file] = current_logic

    return {
        "added": logic_added,
        "removed": logic_removed,
        "brand_lines": brand_lines,
        "files": file_sections,
    }


def summarise_files(file_sections: dict[str, list[str]]) -> str:
    """Build a compact per-file summary."""
    if not file_sections:
        return "_No logic-change files detected._"
    lines = []
    for fname, changes in sorted(file_sections.items()):
        added = sum(1 for c in changes if c.startswith("+"))
        removed = sum(1 for c in changes if c.startswith("-"))
        if added + removed == 0:
            continue
        emoji = "📄"
        if fname.endswith(".py"):
            emoji = "🐍"
        elif fname.endswith(".js"):
            emoji = "⚡"
        elif fname.endswith(".yml") or fname.endswith(".yaml"):
            emoji = "⚙️"
        elif "test" in fname.lower():
            emoji = "🧪"
        elif fname.endswith(".md"):
            emoji = "📝"
        lines.append(f"| {emoji} `{fname}` | +{added} | -{removed} |")
    return "\n".join(lines) if lines else "_No logic-change files detected._"


def build_comment(base_sha: str, head_sha: str, analysis: dict) -> str:
    added_count = len(analysis["added"])
    removed_count = len(analysis["removed"])
    brand_count = analysis["brand_lines"]
    file_table = summarise_files(analysis["files"])

    signal_lines = []
    seen: set[str] = set()
    for line in analysis["added"][:120]:
        stripped = line.strip()
        if not stripped or stripped in seen:
            continue
        seen.add(stripped)
        if any(kw in stripped.lower() for kw in (
            "def ", "class ", "async def ", "return ", "raise ", "import ",
            "function ", "const ", "let ", "var ", "export ",
        )):
            signal_lines.append(f"  `+ {stripped[:120]}`")
        if len(signal_lines) >= 20:
            break

    snippet_block = "\n".join(signal_lines) if signal_lines else "  _No significant code additions detected._"

    verdict = ""
    if added_count + removed_count == 0 and brand_count > 0:
        verdict = "✅ **Pure brand noise** — only branding renames, no logic changes."
    elif added_count + removed_count < 20:
        verdict = "🟡 **Minor changes** — small logic delta, likely safe to merge after review."
    else:
        verdict = "🔴 **Significant logic changes** — review carefully before merging."

    return f"""### 🤖 NasTech Upstream Sync — Diff Analysis

{verdict}

| Metric | Count |
|--------|-------|
| Logic lines added | `+{added_count}` |
| Logic lines removed | `-{removed_count}` |
| Brand-noise lines filtered | `{brand_count}` |
| Commits | `{base_sha[:8]}` → `{head_sha[:8]}` |

---

#### Changed files (logic only)

| File | Added | Removed |
|------|-------|---------|
{file_table}

---

#### Signal — notable additions (first 20)

{snippet_block}

---

> 🏷️ **NasWebUI** by [NasTech AI](https://github.com/nastech-ai) — auto-generated by `pr-diff-summary.yml`
> Review diff carefully: upstream logic changes may need NasTech-specific adaptation before merging.
"""


def post_comment(repo: str, pr_number: str, body: str, token: str) -> None:
    url = f"https://api.github.com/repos/{repo}/issues/{pr_number}/comments"
    payload = json.dumps({"body": body}).encode()
    req = urllib.request.Request(
        url, data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            resp = json.loads(r.read())
            print(f"Comment posted: {resp.get('html_url','')}")
    except urllib.error.HTTPError as e:
        print(f"GitHub API error {e.code}: {e.read().decode()}")
        sys.exit(1)


def main() -> None:
    if len(sys.argv) < 5:
        print("Usage: pr_diff_summary.py <base_sha> <head_sha> <pr_number> <repo>")
        sys.exit(1)

    base_sha, head_sha, pr_number, repo = sys.argv[1:5]
    token = os.environ.get("GH_TOKEN", "")
    if not token:
        print("ERROR: GH_TOKEN environment variable not set")
        sys.exit(1)

    print(f"Analysing diff {base_sha[:8]}..{head_sha[:8]} for PR #{pr_number}")
    diff = run(["git", "diff", base_sha, head_sha])
    if not diff:
        print("No diff found — nothing to analyse")
        body = (
            "### 🤖 NasTech Upstream Sync — Diff Analysis\n\n"
            "✅ **No diff** — upstream and main are identical after branding.\n\n"
            "> 🏷️ **NasWebUI** by [NasTech AI](https://github.com/nastech-ai)"
        )
        post_comment(repo, pr_number, body, token)
        return

    analysis = classify_diff_lines(diff)
    body = build_comment(base_sha, head_sha, analysis)
    print(body)
    post_comment(repo, pr_number, body, token)


if __name__ == "__main__":
    main()
