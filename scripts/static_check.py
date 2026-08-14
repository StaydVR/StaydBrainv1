from __future__ import annotations

import ast
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKIP = {".git", ".agent-brain", ".venv", "__pycache__", "build", "dist", "agent_brain.egg-info"}
secret_patterns = [
    re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(rb"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    re.compile(rb"\bgh[pousr]_[A-Za-z0-9]{30,}\b"),
]
release_content_suffixes = {".md", ".json", ".toml", ".yml", ".yaml", ".txt"}
release_privacy_patterns = [
    ("local user path", re.compile(rb"(?:/Users/|[A-Za-z]:\\Users\\)[A-Za-z0-9._-]+")),
    ("generic credential", re.compile(rb"(?i)(?:api[_-]?key|secret|token|password)\s*[:=]\s*['\"]?[A-Za-z0-9_./+\-=]{12,}")),
    ("bearer token", re.compile(rb"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{16,}")),
    ("jwt", re.compile(rb"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")),
    ("credentialed database url", re.compile(rb"(?i)\b(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?)://[^\s:@/]+:[^\s@/]+@")),
    ("ssn", re.compile(rb"\b\d{3}-\d{2}-\d{4}\b")),
    ("phone", re.compile(rb"(?<!\d)(?:\+?1[-. ]?)?\(?\d{3}\)?[-. ]\d{3}[-. ]\d{4}(?!\d)")),
]
email_pattern = re.compile(rb"\b[A-Z0-9._%+-]+@([A-Z0-9.-]+\.[A-Z]{2,})\b", re.I)
failures: list[str] = []
for path in ROOT.rglob("*"):
    if not path.is_file() or any(part in SKIP for part in path.parts) or path.suffix in {".sqlite3", ".pyc"}:
        continue
    data = path.read_bytes()
    if any(pattern.search(data) for pattern in secret_patterns):
        failures.append(f"secret-like content: {path.relative_to(ROOT)}")
    if path.suffix.lower() in release_content_suffixes:
        for label, pattern in release_privacy_patterns:
            if pattern.search(data):
                failures.append(f"{label} in release content: {path.relative_to(ROOT)}")
        for match in email_pattern.finditer(data):
            domain = match.group(1).lower()
            if domain not in {b"example.com", b"example.org", b"example.net"}:
                failures.append(f"email in release content: {path.relative_to(ROOT)}")
    if path.suffix == ".py":
        text = data.decode("utf-8")
        tree = ast.parse(text, filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {"eval", "exec"}:
                failures.append(f"dynamic code execution: {path.relative_to(ROOT)}:{node.lineno}")
            if isinstance(node, ast.Call):
                for keyword in node.keywords:
                    if keyword.arg == "shell" and isinstance(keyword.value, ast.Constant) and keyword.value.value is True:
                        failures.append(f"shell execution: {path.relative_to(ROOT)}:{node.lineno}")
if failures:
    raise SystemExit("\n".join(failures))
print("static checks passed")
