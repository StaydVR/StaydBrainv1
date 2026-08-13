from __future__ import annotations

import ast
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKIP = {".git", ".agent-brain", "__pycache__"}
secret_patterns = [
    re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(rb"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    re.compile(rb"\bgh[pousr]_[A-Za-z0-9]{30,}\b"),
]
failures: list[str] = []
for path in ROOT.rglob("*"):
    if not path.is_file() or any(part in SKIP for part in path.parts) or path.suffix in {".sqlite3", ".pyc"}:
        continue
    data = path.read_bytes()
    if any(pattern.search(data) for pattern in secret_patterns):
        failures.append(f"secret-like content: {path.relative_to(ROOT)}")
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
