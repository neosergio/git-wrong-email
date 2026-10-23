"""The hook, exercised against real git repositories.

Each test builds a fake $HOME holding a rules file and a hooks directory, and
points git at it through an isolated global config, so nothing here reads or
writes the real ~/.gitconfig.

    pytest                       # needs pytest and git, nothing else
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOK = REPO_ROOT / "hook/git-wrong-email-hook"

PERSONAL = "you@personal.example"
PERSONAL_ALT = "you@users.noreply.github.com"
ACME = "you@acme.example"
GLOBEX = "you@globex.example"

RULES = f"""\
# comment, and a blank line, both skipped

~/work/acme/    {ACME}
~/work/globex/  {GLOBEX}
~/code/         {PERSONAL} {PERSONAL_ALT}
*               {PERSONAL} {PERSONAL_ALT}
"""

# The names the tests actually exercise; `install` ships all 18.
HOOK_NAMES = ("pre-commit", "pre-merge-commit", "pre-push", "commit-msg")

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="needs git")


class Sandbox:
    def __init__(self, home: Path) -> None:
        self.home = home
        self.hooks = home / ".config/git-wrong-email/hooks"
        self.hooks.mkdir(parents=True)
        for name in HOOK_NAMES:
            shutil.copy(HOOK, self.hooks / name)
            (self.hooks / name).chmod(0o755)

        # The default location, so path resolution is covered too.
        self.rules = home / ".config/git-wrong-email/rules"
        self.rules.write_text(RULES)

        self.global_config = home / ".gitconfig"
        self.global_config.write_text(f"[core]\n\thooksPath = {self.hooks}\n")
        self.env = {
            "PATH": os.environ["PATH"],
            "HOME": str(home),
            "GIT_CONFIG_GLOBAL": str(self.global_config),
            "GIT_CONFIG_NOSYSTEM": "1",
        }

    def git(self, cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args], cwd=cwd, env=self.env, text=True, capture_output=True, check=check
        )

    def repo(self, relative: str, email: str) -> Path:
        path = self.home / relative
        path.mkdir(parents=True)
        self.git(path, "init", "-q", "-b", "main")
        self.git(path, "config", "user.name", "Test")
        self.git(path, "config", "user.email", email)
        return path

    def commit(
        self, repo: Path, *extra: str, check: bool = False
    ) -> subprocess.CompletedProcess[str]:
        n = len(list(repo.glob("f*")))
        (repo / f"f{n}").write_text(str(n))
        self.git(repo, "add", ".")
        return self.git(repo, "commit", "-q", "-m", f"change {n}", *extra, check=check)


@pytest.fixture
def box(tmp_path: Path) -> Sandbox:
    return Sandbox(tmp_path)


def test_a_matching_email_is_accepted(box):
    repo = box.repo("code/site", PERSONAL)
    assert box.commit(repo).returncode == 0


def test_any_of_several_allowed_emails_is_accepted(box):
    repo = box.repo("code/notes", PERSONAL_ALT)
    assert box.commit(repo).returncode == 0


def test_a_work_email_in_a_personal_repo_is_refused(box):
    # The incident this exists for: a work address inherited by a personal repo
    # after something rewrote the global user.email.
    repo = box.repo("code/site", ACME)
    result = box.commit(repo)

    assert result.returncode != 0
    assert f"committer email is '{ACME}'" in result.stderr
    assert box.git(repo, "rev-list", "--all", check=False).stdout == ""


def test_a_client_directory_requires_the_client_email(box):
    repo = box.repo("work/acme/app", PERSONAL)
    assert box.commit(repo).returncode != 0

    box.git(repo, "config", "user.email", ACME)
    assert box.commit(repo).returncode == 0


def test_one_clients_email_is_not_accepted_in_anothers_directory(box):
    repo = box.repo("work/globex/api", ACME)
    assert box.commit(repo).returncode != 0


def test_repositories_outside_any_listed_directory_fall_through_to_the_star(box):
    repo = box.repo("elsewhere/tool", ACME)
    assert box.commit(repo).returncode != 0

    box.git(repo, "config", "user.email", PERSONAL)
    assert box.commit(repo).returncode == 0


def test_a_directory_prefix_does_not_match_a_longer_name(box):
    # ~/work/acme/ must not cover ~/work/acme-notes: that falls through to "*".
    repo = box.repo("work/acme-notes/x", PERSONAL)
    assert box.commit(repo).returncode == 0


def test_environment_overrides_are_checked_too(box):
    # GUI clients often pass the identity through the environment, where no
    # amount of includeIf configuration would show it.
    repo = box.repo("code/site", PERSONAL)
    box.env["GIT_AUTHOR_EMAIL"] = ACME
    result = box.commit(repo)

    assert result.returncode != 0
    assert "author email" in result.stderr


def test_a_missing_rules_file_refuses_rather_than_waving_through(box):
    repo = box.repo("code/site", PERSONAL)
    box.rules.unlink()

    result = box.commit(repo)
    assert result.returncode != 0
    assert "no rules file" in result.stderr


def test_a_repository_matching_no_rule_is_refused(box):
    box.rules.write_text(f"~/work/acme/  {ACME}\n")  # no "*" fallback
    repo = box.repo("code/site", PERSONAL)

    result = box.commit(repo)
    assert result.returncode != 0
    assert "no rule in" in result.stderr


def test_the_repository_hook_still_runs_and_can_refuse(box):
    repo = box.repo("code/site", PERSONAL)
    local = repo / ".git/hooks/pre-commit"
    local.write_text("#!/bin/sh\necho local-ran >&2\nexit 3\n")
    local.chmod(0o755)

    result = box.commit(repo)
    assert result.returncode != 0
    assert "local-ran" in result.stderr

    local.write_text("#!/bin/sh\necho local-ran >&2\nexit 0\n")
    assert box.commit(repo).returncode == 0


def test_hooks_without_checks_of_their_own_just_chain(box):
    repo = box.repo("code/site", PERSONAL)
    local = repo / ".git/hooks/commit-msg"
    local.write_text('#!/bin/sh\ngrep -q "change" "$1"\n')
    local.chmod(0o755)

    assert box.commit(repo).returncode == 0
    (repo / "g").write_text("x")
    box.git(repo, "add", ".")
    assert box.git(repo, "commit", "-q", "-m", "nope", check=False).returncode != 0


def test_an_existing_hooks_path_is_chained_to(box):
    # What `install` records when husky or lefthook already owned
    # core.hooksPath: that directory still runs, after the check.
    other = box.home / "other-hooks"
    other.mkdir()
    (other / "pre-commit").write_text("#!/bin/sh\necho other-ran >&2\nexit 0\n")
    (other / "pre-commit").chmod(0o755)

    repo = box.repo("code/site", PERSONAL)
    box.git(repo, "config", "--global", "wrongEmail.chainTo", str(other))

    result = box.commit(repo, check=True)
    assert result.returncode == 0
    assert "other-ran" in result.stderr

    # And it is still the check that decides first.
    box.git(repo, "config", "user.email", ACME)
    assert box.commit(repo).returncode != 0


def _remote(box: Sandbox, repo: Path) -> None:
    bare = box.home / "remote.git"
    box.git(box.home, "init", "-q", "--bare", str(bare))
    box.git(repo, "remote", "add", "origin", str(bare))


def test_push_refuses_a_commit_that_skipped_the_commit_hook(box):
    repo = box.repo("code/site", PERSONAL)
    _remote(box, repo)
    assert box.commit(repo).returncode == 0
    box.git(repo, "push", "-q", "origin", "main")

    box.git(repo, "config", "user.email", ACME)
    assert box.commit(repo, "--no-verify").returncode == 0
    result = box.git(repo, "push", "-q", "origin", "main", check=False)

    assert result.returncode != 0
    assert re.search(r"commit [0-9a-f]{7} committer email", result.stderr)


def test_push_ignores_history_the_remote_already_has(box):
    repo = box.repo("code/site", PERSONAL)
    _remote(box, repo)
    box.git(repo, "config", "user.email", ACME)
    box.commit(repo, "--no-verify")
    box.git(repo, "push", "-q", "--no-verify", "origin", "main")

    # The bad commit is public already; a new branch on top of it must not be
    # blocked over history nobody can fix any more.
    box.git(repo, "config", "user.email", PERSONAL)
    box.git(repo, "switch", "-q", "-c", "feature")
    assert box.commit(repo).returncode == 0
    assert box.git(repo, "push", "-q", "origin", "feature", check=False).returncode == 0


def test_push_ignores_public_history_merged_into_an_existing_branch(box):
    repo = box.repo("code/site", PERSONAL)
    _remote(box, repo)
    assert box.commit(repo).returncode == 0
    box.git(repo, "push", "-q", "origin", "main")
    box.git(repo, "switch", "-q", "-c", "feature")
    assert box.commit(repo).returncode == 0
    box.git(repo, "push", "-q", "origin", "feature")

    # A merge made on the forge lands on main with committer noreply@github.com.
    box.git(repo, "switch", "-q", "main")
    box.git(repo, "config", "user.email", "noreply@github.com")
    box.commit(repo, "--no-verify")
    box.git(repo, "push", "-q", "--no-verify", "origin", "main")

    # Merging main into the already-pushed branch brings that public commit
    # into remote_sha..local_sha; it must not block the push.
    box.git(repo, "config", "user.email", PERSONAL)
    box.git(repo, "switch", "-q", "feature")
    box.git(repo, "merge", "-q", "--no-edit", "main")
    assert box.git(repo, "push", "-q", "origin", "feature", check=False).returncode == 0

    # A new bad commit on the same branch is still refused.
    box.git(repo, "config", "user.email", ACME)
    assert box.commit(repo, "--no-verify").returncode == 0
    assert box.git(repo, "push", "-q", "origin", "feature", check=False).returncode != 0


def test_a_collaborator_may_author_but_not_commit(box):
    repo = box.repo("code/notes", PERSONAL_ALT)
    _remote(box, repo)
    box.git(repo, "config", "--add", "wrongEmail.allowedAuthor", "colleague@example.com")
    box.env["GIT_AUTHOR_EMAIL"] = "colleague@example.com"

    assert box.commit(repo).returncode == 0
    assert box.git(repo, "push", "-q", "origin", "main", check=False).returncode == 0

    box.env["GIT_COMMITTER_EMAIL"] = "colleague@example.com"
    assert box.commit(repo).returncode != 0


def test_hooks_that_run_outside_a_usable_repository_stay_quiet(box):
    # reference-transaction fires three times during `git init`, before there
    # is a git dir to ask about. A stray "fatal: not a git repository" there is
    # what makes people uninstall a global hook.
    for name in ("reference-transaction", "post-index-change"):
        shutil.copy(HOOK, box.hooks / name)
        (box.hooks / name).chmod(0o755)

    path = box.home / "code/fresh"
    path.mkdir(parents=True)
    result = box.git(path, "init", "-q", "-b", "main")

    assert result.returncode == 0
    assert result.stderr == "", result.stderr

    (path / "a").write_text("x")
    assert box.git(path, "add", "a").stderr == ""
