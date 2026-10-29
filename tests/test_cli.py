"""`git wrong-email install|uninstall|status`, run the ways it gets installed.

Like test_hook.py, each test gets a throwaway $HOME and global config, so the
real ~/.gitconfig is never touched.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="needs git")


class Home:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.hooks = path / ".config/git-wrong-email/hooks"
        self.rules = path / ".config/git-wrong-email/rules"
        self.env = {
            "PATH": os.environ["PATH"],
            "HOME": str(path),
            "GIT_CONFIG_GLOBAL": str(path / ".gitconfig"),
            "GIT_CONFIG_NOSYSTEM": "1",
        }

    def run(
        self, script: Path, *args: str, cwd: Path | None = None
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(script), *args], env=self.env, text=True, capture_output=True,
            cwd=cwd,
        )

    def config(self, key: str) -> str:
        return subprocess.run(
            ["git", "config", "--global", "--get", key],
            env=self.env, text=True, capture_output=True,
        ).stdout.strip()


@pytest.fixture
def home(tmp_path: Path) -> Home:
    path = tmp_path / "home"
    path.mkdir()
    return Home(path)


def _assert_installed(home: Home) -> None:
    assert home.config("core.hooksPath") == str(home.hooks)
    assert len(list(home.hooks.iterdir())) == 18
    assert "# git-wrong-email" in (home.hooks / "pre-push").read_text()
    assert "you@personal.example" in home.rules.read_text()


def test_install_from_a_checkout(home):
    result = home.run(REPO_ROOT / "bin/git-wrong-email", "install")
    assert result.returncode == 0, result.stderr
    _assert_installed(home)


def test_install_through_a_symlink_on_path(home, tmp_path):
    # Linking bin/git-wrong-email into ~/bin or similar: the hook is next to
    # the link's target, not next to the link.
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "git-wrong-email").symlink_to(REPO_ROOT / "bin/git-wrong-email")

    result = home.run(bin_dir / "git-wrong-email", "install")
    assert result.returncode == 0, result.stderr
    _assert_installed(home)


def test_install_from_a_homebrew_layout(home, tmp_path):
    # What the formula produces: the script and hook in the Cellar under bin/
    # and libexec/, the example under share/, and a relative link from the
    # prefix's bin/ into the Cellar.
    prefix = tmp_path / "homebrew"
    keg = prefix / "Cellar/git-wrong-email/0.1.0"
    (keg / "bin").mkdir(parents=True)
    (keg / "libexec").mkdir()
    (keg / "share/git-wrong-email").mkdir(parents=True)
    shutil.copy(REPO_ROOT / "bin/git-wrong-email", keg / "bin")
    shutil.copy(REPO_ROOT / "hook/git-wrong-email-hook", keg / "libexec")
    shutil.copy(REPO_ROOT / "examples/rules", keg / "share/git-wrong-email")
    (prefix / "bin").mkdir()
    (prefix / "bin/git-wrong-email").symlink_to(
        "../Cellar/git-wrong-email/0.1.0/bin/git-wrong-email"
    )

    result = home.run(prefix / "bin/git-wrong-email", "install")
    assert result.returncode == 0, result.stderr
    _assert_installed(home)


def test_install_keeps_existing_rules(home):
    home.rules.parent.mkdir(parents=True)
    home.rules.write_text("*  mine@example.com\n")

    assert home.run(REPO_ROOT / "bin/git-wrong-email", "install").returncode == 0
    assert home.rules.read_text() == "*  mine@example.com\n"


def test_uninstall_restores_a_hooks_path_that_was_already_set(home):
    script = REPO_ROOT / "bin/git-wrong-email"
    other = str(home.path / "husky")
    subprocess.run(
        ["git", "config", "--global", "core.hooksPath", other], env=home.env, check=True
    )

    assert home.run(script, "install").returncode == 0
    assert home.config("wrongEmail.chainTo") == other

    assert home.run(script, "uninstall").returncode == 0
    assert home.config("core.hooksPath") == other
    assert home.config("wrongEmail.chainTo") == ""
    assert not home.hooks.exists()
    assert home.rules.exists()


def test_a_hooks_path_already_pointing_at_ours_is_not_chained_to(home):
    # A dotfiles manager that renders ~/.gitconfig may set core.hooksPath to
    # our directory before `install` has created it. Recording that as
    # chainTo would make `uninstall` "restore" the path it is removing.
    subprocess.run(
        ["git", "config", "--global", "core.hooksPath", str(home.hooks)],
        env=home.env, check=True,
    )

    result = home.run(REPO_ROOT / "bin/git-wrong-email", "install")
    assert result.returncode == 0, result.stderr
    assert "chainTo" not in result.stdout
    assert home.config("wrongEmail.chainTo") == ""
    _assert_installed(home)


def test_status_reports_whether_it_is_active(home):
    script = REPO_ROOT / "bin/git-wrong-email"
    assert "active         NO" in home.run(script, "status").stdout

    home.run(script, "install")
    assert "active         yes" in home.run(script, "status").stdout


def test_status_warns_when_a_repository_overrides_the_hooks_path(home, tmp_path):
    # husky's prepare script runs `git config core.hooksPath .husky/_`, which
    # wins over the global setting and quietly turns the check off.
    script = REPO_ROOT / "bin/git-wrong-email"
    repo = tmp_path / "repo"
    subprocess.run(["git", "init", "-q", str(repo)], env=home.env, check=True)
    assert home.run(script, "install").returncode == 0

    status = home.run(script, "status", cwd=repo)
    assert status.returncode == 0
    assert "this repo" not in status.stdout

    subprocess.run(
        ["git", "config", "core.hooksPath", ".husky/_"],
        env=home.env, cwd=repo, check=True,
    )
    status = home.run(script, "status", cwd=repo)
    assert status.returncode == 0
    assert "core.hooksPath is .husky/_ -- the check does NOT run here" in status.stdout


def test_version(home):
    result = home.run(REPO_ROOT / "bin/git-wrong-email", "--version")
    assert result.returncode == 0
    assert result.stdout.startswith("git-wrong-email ")
