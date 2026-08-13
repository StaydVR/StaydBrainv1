from __future__ import annotations

import re
import math
from collections import Counter
from dataclasses import dataclass

from .errors import SecurityError
from .util import sha256


SECRET_PATTERNS = (
    re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(rb"(?i)(?:api[_-]?key|secret|token|password)\s*[:=]\s*['\"]?[A-Za-z0-9_./+\-=]{12,}"),
    re.compile(rb"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    re.compile(rb"\bgh[pousr]_[A-Za-z0-9]{30,}\b"),
    re.compile(rb"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
    re.compile(rb"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{16,}"),
    re.compile(rb"(?i)\b(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?)://[^\s:@/]+:[^\s@/]+@"),
)
PII_PATTERNS = (
    ("email", re.compile(rb"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)),
    ("ssn", re.compile(rb"\b\d{3}-\d{2}-\d{4}\b")),
    ("phone", re.compile(rb"(?<!\d)(?:\+?1[-. ]?)?\(?\d{3}\)?[-. ]\d{3}[-. ]\d{4}(?!\d)")),
)
CARD_RE = re.compile(rb"(?<![A-Za-z0-9])(?:\d[ -]?){13,19}(?![A-Za-z0-9])")


@dataclass(frozen=True)
class ScanResult:
    digest: str
    size: int


def _high_entropy_secret(data: bytes) -> bool:
    # Long token-like runs only; prose and hexadecimal content hashes are excluded.
    for token in re.findall(rb"[A-Za-z0-9_+/=-]{32,}", data):
        if re.fullmatch(rb"[0-9a-fA-F]{32,}", token):
            continue
        counts = Counter(token)
        entropy = -sum((n / len(token)) * math.log2(n / len(token)) for n in counts.values())
        if entropy >= 4.3:
            return True
    return False


def _has_payment_card(data: bytes) -> bool:
    for match in CARD_RE.finditer(data):
        digits = [int(char) for char in re.sub(rb"\D", b"", match.group())]
        checksum = 0
        parity = len(digits) % 2
        for index, digit in enumerate(digits):
            if index % 2 == parity:
                digit *= 2
                if digit > 9:
                    digit -= 9
            checksum += digit
        if checksum % 10 == 0:
            return True
    return False


def scan(data: bytes, max_bytes: int) -> ScanResult:
    reasons: list[str] = []
    if len(data) > max_bytes:
        reasons.append("max_bytes_exceeded")
    if b"\x00" in data:
        reasons.append("nul_byte")
    if any(pattern.search(data) for pattern in SECRET_PATTERNS):
        reasons.append("secret_pattern")
    if _high_entropy_secret(data):
        reasons.append("high_entropy_secret")
    reasons.extend(f"pii_{name}" for name, pattern in PII_PATTERNS if pattern.search(data))
    if _has_payment_card(data):
        reasons.append("pii_credit_card")
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        reasons.append("invalid_utf8")
    if reasons:
        raise SecurityError(reasons)
    return ScanResult(sha256(data), len(data))
