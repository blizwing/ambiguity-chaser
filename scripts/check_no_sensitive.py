"""
Pre-commit guard: scans the lines a commit would ADD for things that must
not reach this public repo (see CLAUDE.md, "No PII or secrets in git").

Flags:
  - ticket keys like ABC-1234 (ticket keys identify a project)
  - API-key-looking strings (sk-..., long hex, long mixed base64 tokens)

Known-safe matches go in ALLOWED_TICKET_PREFIXES / ALLOWED_TOKENS below, or
a line can carry the marker `check-no-sensitive: ignore`.

Install (local only; hooks are not pushed to GitHub). Append to the existing
.git/hooks/pre-commit, after its private/ check, rather than replacing it:

    python scripts/check_no_sensitive.py || exit 1

Run by hand against what is staged:  python scripts/check_no_sensitive.py
Exit code 0 = clean, 1 = findings (commit blocked).
"""

import re
import subprocess
import sys

TICKET_RE = re.compile(r"\b([A-Z]{2,10})-(\d{2,6})\b")
SK_RE = re.compile(r"\bsk-[A-Za-z0-9_-]{16,}")
HEX_RE = re.compile(r"\b[0-9a-fA-F]{32,}\b")
B64_RE = re.compile(r"[A-Za-z0-9+_=-]{40,}")

# Letter prefixes that look like ticket keys but are standards/names. P1/P2/P3
# have no dash-digits-of-2+ so they never match; listed for the record.
ALLOWED_TICKET_PREFIXES = {
    "SHA", "UTF", "ISO", "MD", "RFC", "HTTP", "TLS", "AES", "RSA", "GPT",
    "PEP", "CVE", "UTC", "TCP", "UDP", "IPV", "ASCII", "P",
}
# Exact strings that are fine even though they match a pattern.
ALLOWED_TOKENS = {"ABC-1234", "TC-001", "TC-005", "laya_finetune_typed_decisions_2xT4_kaggle", "SHA-256", "SHA-1", "SHA-512", "UTF-8", "UTF-16", "UTF-32"}
IGNORE_MARKER = "check-no-sensitive: ignore"
# 40 hex chars is a git commit SHA, common in notes; not treated as a secret.
GIT_SHA_LEN = 40


def staged_additions():
    """Yields (path, line_number, text) for each added line in the staged diff."""
    diff = subprocess.run(
        ["git", "diff", "--cached", "--unified=0", "--no-color", "--diff-filter=AM"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", check=True,
    ).stdout
    path, lineno = None, 0
    for raw in diff.splitlines():
        if raw.startswith("+++ "):
            path = raw[4:].removeprefix("b/")
        elif raw.startswith("@@"):
            m = re.search(r"\+(\d+)", raw)
            lineno = int(m.group(1)) if m else 0
        elif raw.startswith("+") and not raw.startswith("+++"):
            yield path, lineno, raw[1:]
            lineno += 1


def findings_in_line(text: str):
    """Returns (kind, matched_text) pairs for one added line."""
    if IGNORE_MARKER in text:
        return []
    found = []
    for m in TICKET_RE.finditer(text):
        if m.group(0) in ALLOWED_TOKENS or m.group(1) in ALLOWED_TICKET_PREFIXES:
            continue
        found.append(("ticket key", m.group(0)))
    for m in SK_RE.finditer(text):
        found.append(("API key (sk-...)", m.group(0)))
    for m in HEX_RE.finditer(text):
        if len(m.group(0)) != GIT_SHA_LEN:
            found.append(("long hex token", m.group(0)))
    for m in B64_RE.finditer(text):
        tok = m.group(0)
        if tok in ALLOWED_TOKENS:
            continue
        # Mixed letters and digits, so long plain words/underscore names pass.
        if re.search(r"[A-Za-z]", tok) and re.search(r"\d", tok) and not HEX_RE.fullmatch(tok):
            found.append(("long base64-like token", tok))
    return found


def redact(tok: str) -> str:
    # Never echo a full suspected secret into terminal scrollback/logs.
    return tok if len(tok) <= 12 else tok[:6] + "..." + tok[-3:]


def main() -> int:
    problems = []
    for path, lineno, text in staged_additions():
        for kind, tok in findings_in_line(text):
            problems.append(f"  {path}:{lineno}: {kind}: {redact(tok)}")
    if not problems:
        return 0
    print("BLOCKED: possible sensitive content in staged additions:", file=sys.stderr)
    print("\n".join(problems), file=sys.stderr)
    print(
        "Remove it, or if it is a known-safe match add it to the allowlist in "
        "scripts/check_no_sensitive.py (or mark the line with "
        f"'{IGNORE_MARKER}').",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
