"""Runs the real deploy/auto-update.sh against local git repos.

GitHub's test status, systemd, runuser and the bot's Python are replaced
by small stub scripts that log what they were asked to do.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "deploy" / "auto-update.sh"
UNIT = "telegram-tweet-notification"

pytestmark = pytest.mark.skipif(shutil.which("git") is None or shutil.which("bash") is None,
                                reason="needs git and bash")

GIT_ENV = {
    "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@t", "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
}


def write_exe(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/usr/bin/env bash\n" + body)
    path.chmod(0o755)


class Setup:
    def __init__(self, tmp: Path):
        self.tmp = tmp
        self.log = tmp / "calls.log"
        self.ci = tmp / "ci.json"
        self.origin = tmp / "origin.git"
        self.dev = tmp / "dev"          # where "you" commit and push
        self.app = tmp / "app"          # the server's checkout
        self.env_file = tmp / "bot.env"
        self.state = tmp / "state"
        self.units = tmp / "units"
        for d in (self.state, self.units):
            d.mkdir()
        self.env_file.write_text("X_BEARER_TOKEN=x\n")

        self.git("init", "--bare", "-b", "main", str(self.origin), cwd=tmp)
        self.git("clone", str(self.origin), str(self.dev), cwd=tmp)
        self.commit({
            "notifier/__init__.py": "",
            "notifier/main.py": "OK = True\n",
            "notifier/check.py": "",
            "requirements.txt": "requests\n",
            f"deploy/{UNIT}.service": "[Service]\n",
            f"deploy/{UNIT}.timer": "[Timer]\n",
        }, "first")
        self.git("clone", str(self.origin), str(self.app), cwd=tmp)
        self._make_stubs()
        self.set_ci("success")

    def git(self, *args, cwd=None):
        return subprocess.run(["git", *args], cwd=cwd or self.dev, check=True,
                              capture_output=True, text=True, env={**os.environ, **GIT_ENV}).stdout.strip()

    def commit(self, files: dict[str, str], message: str) -> str:
        for name, content in files.items():
            path = self.dev / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        self.git("add", "-A")
        self.git("commit", "-m", message)
        self.git("push", "-q", "origin", "main")
        return self.git("rev-parse", "HEAD")

    def _make_stubs(self):
        bin_dir = self.tmp / "bin"
        log = self.log
        write_exe(bin_dir / "runuser", 'shift 3\nexec "$@"\n')          # drop "-u user --"
        write_exe(bin_dir / "systemctl", f'echo "systemctl $*" >> {log}\n')
        write_exe(bin_dir / "curl", f'[ -f {self.ci} ] && cat {self.ci} || exit 22\n')
        write_exe(self.app / ".venv" / "bin" / "python", f'''
if [ "$1" = "-c" ]; then exec {sys.executable} "$@"; fi
echo "python $*" >> {log}
''')
        self.path = f"{bin_dir}:{os.environ['PATH']}"

    def set_ci(self, state: str | None):
        if state is None:
            self.ci.unlink(missing_ok=True)
            return
        runs = {
            "success": [{"status": "completed", "conclusion": "success"}],
            "failure": [{"status": "completed", "conclusion": "failure"}],
            "pending": [{"status": "in_progress", "conclusion": None}],
            "none": [],
        }[state]
        self.ci.write_text(json.dumps({"check_runs": runs}))

    def run(self) -> subprocess.CompletedProcess:
        env = {**os.environ, **GIT_ENV, "PATH": self.path, "APP_DIR": str(self.app),
               "APP_USER": "nobody", "ENV_FILE": str(self.env_file),
               "STATE_DIR": str(self.state), "UNIT_DIR": str(self.units)}
        return subprocess.run(["bash", str(SCRIPT)], env=env, capture_output=True, text=True)

    @property
    def head(self) -> str:
        return self.git("rev-parse", "HEAD", cwd=self.app)

    @property
    def calls(self) -> str:
        return self.log.read_text() if self.log.exists() else ""

    def notices(self) -> list[str]:
        return [line for line in self.calls.splitlines() if "--notify" in line]


@pytest.fixture
def s(tmp_path):
    return Setup(tmp_path)


def test_up_to_date_does_nothing(s):
    result = s.run()
    assert result.returncode == 0, result.stderr
    assert s.calls == ""


def test_new_commit_with_passing_tests_is_deployed_and_announced(s):
    new = s.commit({"notifier/main.py": "OK = 2\n"}, "Tweak layout")
    assert s.run().returncode == 0
    assert s.head == new
    assert "Bot updated to" in s.notices()[0] and "Tweak layout" in s.notices()[0]
    assert "pip" not in s.calls  # requirements unchanged: no reinstall


def test_waits_while_tests_are_running(s):
    s.set_ci("pending")
    before = s.head
    s.commit({"notifier/main.py": "OK = 2\n"}, "wip")
    assert s.run().returncode == 0
    assert s.head == before and s.notices() == []


def test_waits_if_github_is_unreachable(s):
    s.set_ci(None)
    before = s.head
    s.commit({"notifier/main.py": "OK = 2\n"}, "x")
    s.run()
    assert s.head == before


def test_failing_tests_are_not_deployed_and_announced_once(s):
    s.set_ci("failure")
    before = s.head
    s.commit({"notifier/main.py": "OK = 2\n"}, "Broken change")
    s.run()
    s.run()
    assert s.head == before
    assert len(s.notices()) == 1 and "failed its GitHub tests" in s.notices()[0]


def test_broken_code_is_rolled_back_and_announced_once(s):
    before = s.head
    s.commit({"notifier/main.py": "this is not python(\n"}, "Oops")
    assert s.run().returncode == 1
    assert s.head == before
    s.run()
    assert len(s.notices()) == 1 and "rolled back" in s.notices()[0]


def test_next_good_commit_deploys_after_a_skipped_one(s):
    s.set_ci("failure")
    s.commit({"notifier/main.py": "OK = 2\n"}, "bad")
    s.run()
    s.set_ci("success")
    good = s.commit({"notifier/main.py": "OK = 3\n"}, "fix")
    s.run()
    assert s.head == good


def test_new_requirements_are_installed(s):
    s.commit({"requirements.txt": "requests\nnewpkg\n"}, "Add package")
    s.run()
    assert "python -m pip install -q -r" in s.calls


def test_changed_timer_is_applied(s):
    s.commit({f"deploy/{UNIT}.timer": "[Timer]\nOnCalendar=minutely\n"}, "Every minute")
    s.run()
    assert "minutely" in (s.units / f"{UNIT}.timer").read_text()
    assert "systemctl daemon-reload" in s.calls
    assert f"systemctl restart {UNIT}.timer" in s.calls


def test_installer_change_asks_to_rerun_install(s):
    s.commit({"deploy/install.sh": "echo new\n"}, "Installer change")
    s.run()
    assert "Bot updated to" in s.notices()[0]
    assert "Run once on the server: sudo" in s.calls  # second line of the same notice


def test_tests_can_be_skipped_for_private_repos(s):
    s.env_file.write_text("AUTO_UPDATE_REQUIRE_TESTS=false\n")
    s.set_ci(None)
    new = s.commit({"notifier/main.py": "OK = 2\n"}, "private")
    s.run()
    assert s.head == new
