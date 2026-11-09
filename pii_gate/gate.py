from __future__ import annotations

import functools
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

from .detectors import Detector, default_detector
from .vault import Vault

# Strict token form, and a loose form used only for IDs the vault knows about
# (LLMs sometimes drop or swap the brackets).
TOKEN_RE = re.compile(r"⟦\s*([A-Z]+)_([A-Z2-9]{5})\s*⟧")
LOOSE_RE = re.compile(r"(?:[⟦\[(]\s*)?\b([A-Z]+)_([A-Z2-9]{5})\b(?:\s*[⟧\])])?")


class OutboundBlocked(RuntimeError):
    """A payload bound for an untrusted party still contains raw PII."""


class ProtectedCallFailed(RuntimeError):
    """The wrapped call's output could not be restored safely."""

    def __init__(self, problems: list[str]) -> None:
        super().__init__("; ".join(problems))
        self.problems = problems


@dataclass
class Restored:
    text: str
    ok: bool
    problems: list[str] = field(default_factory=list)


class Session:
    """One protect -> (untrusted call) -> restore cycle with its own encrypted vault."""

    def __init__(self, detector: Detector, vault: Vault | None = None) -> None:
        self.detector, self.vault = detector, vault or Vault()

    def protect(self, text: str) -> str:
        out, pos = [], 0
        for s in self.detector.detect(text):
            out += [text[pos:s.start], self.vault.put(s.kind, text[s.start:s.end])]
            pos = s.end
        out.append(text[pos:])
        return "".join(out)

    def protect_messages(self, messages: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
        """OpenAI/Anthropic-style [{'role','content'}] lists (string contents only)."""
        return [{**m, "content": self.protect(m["content"])} if isinstance(m.get("content"), str) else dict(m)
                for m in messages]

    def check_outbound(self, payload: str) -> None:
        stripped = TOKEN_RE.sub(" ", payload)  # token text itself (e.g. 'IBAN' in IBAN_x) is not a leak
        for original in self.vault.originals():
            if original in stripped:
                raise OutboundBlocked("vaulted value present in outbound payload")
        leftovers = self.detector.detect(stripped)
        if leftovers:
            raise OutboundBlocked(f"residual PII in outbound payload: {sorted({s.kind for s in leftovers})}")

    def restore(self, response: str) -> Restored:
        """Fails closed: unknown tokens or tokens missing from the response => ok=False."""
        problems: list[str] = []
        seen: set[str] = set()

        def sub(m: re.Match[str], strict: bool) -> str:
            canon = f"⟦{m.group(1)}_{m.group(2)}⟧"
            orig = self.vault.get(canon)
            if orig is None:
                if strict:
                    problems.append(f"unknown token {m.group(0)!r}")
                return m.group(0)
            seen.add(canon)
            return orig

        text = TOKEN_RE.sub(lambda m: sub(m, True), response)
        text = LOOSE_RE.sub(lambda m: sub(m, False), text)
        problems += [f"token {t} missing from output" for t in self.vault.tokens() if t not in seen]
        return Restored(text, not problems, problems)

    def close(self) -> None:
        self.vault.close()

    def __enter__(self) -> "Session":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


class Gate:
    def __init__(self, detector: Detector | None = None, *, ner: bool = True,
                 vault_factory: Callable[[], Vault] = Vault) -> None:
        self.detector = detector or default_detector(ner)
        self._vault_factory = vault_factory

    def session(self) -> Session:
        return Session(self.detector, self._vault_factory())

    def guard(self, fn: Callable[[str], str], *, external: bool = True,
              on_failure: str = "raise") -> Callable[[str], str]:
        """Wrap any str->str callable (LLM call, API client, ...).

        external=True runs the outbound gate before calling fn.
        on_failure: 'raise' (ProtectedCallFailed) or 'original' (return input unchanged)."""
        @functools.wraps(fn)
        def wrapper(text: str) -> str:
            with self.session() as s:
                safe = s.protect(text)
                if external:
                    s.check_outbound(safe)
                r = s.restore(fn(safe))
                if r.ok:
                    return r.text
                if on_failure == "original":
                    return text
                raise ProtectedCallFailed(r.problems)
        return wrapper
