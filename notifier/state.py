"""Remembers, per account, its X user id and the newest post already seen.

Saved as a small JSON file between runs, so each run only asks X for
posts newer than the last one. That keeps the API bill near zero.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class AccountState:
    user_id: str | None = None
    last_seen_id: str | None = None


State = dict[str, AccountState]


def load_state(path: Path) -> State:
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {username: AccountState(**values) for username, values in raw.items()}


def save_state(path: Path, state: State) -> None:
    data = {username: asdict(account) for username, account in sorted(state.items())}
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
