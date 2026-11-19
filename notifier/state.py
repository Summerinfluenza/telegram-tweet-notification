"""Remembers, per account, its X user id and the newest post already seen.

Saved as a small JSON file between runs, so each run only asks X for
posts newer than the last one. That keeps the API bill near zero.

Safety:
- Writes are atomic (temp file + rename), so a crash or power cut can
  never leave a half-written file.
- A damaged file is moved aside and the bot starts fresh instead of
  failing on every run.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass
from pathlib import Path

log = logging.getLogger(__name__)


@dataclass
class AccountState:
    user_id: str | None = None
    last_seen_id: str | None = None


State = dict[str, AccountState]


def load_state(path: Path) -> State:
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return {
            username: AccountState(
                user_id=values.get("user_id"),
                last_seen_id=values.get("last_seen_id"),
            )
            for username, values in raw.items()
        }
    except (ValueError, AttributeError, TypeError):
        backup = path.with_suffix(path.suffix + ".corrupt")
        path.replace(backup)
        log.warning("State file was damaged; moved to %s and starting fresh", backup)
        return {}


def save_state(path: Path, state: State) -> None:
    data = {username: asdict(account) for username, account in sorted(state.items())}
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def prune_state(state: State, accounts: tuple[str, ...]) -> None:
    """Forget accounts that were removed from X_ACCOUNTS."""
    for username in list(state):
        if username not in accounts:
            del state[username]
