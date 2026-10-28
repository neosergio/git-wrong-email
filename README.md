# git-wrong-email

Refuses commits and pushes made under an email that does not belong to the
repository you are in. One POSIX shell script, no dependencies, works in every
terminal, GUI client and coding agent on the machine.

```
$ git commit -m 'fix typo'
git-wrong-email: committer email is 'you@bigclient.example', which this repository does not accept.
  Repository: /Users/you/code/my-blog
  Allowed: you@personal.example you@users.noreply.github.com
  Check: git config --show-origin user.email
```

## Why this exists

I keep work and personal projects in separate directories and let
`includeIf` in `~/.gitconfig` pick the right identity for each. That worked
until a GUI client's "keep my .gitconfig updated with my profile info" setting
rewrote the global `user.email` to a client address. Every personal repository
without a local `user.email` silently inherited it, and I found out from a
public commit history.

`includeIf` *assigns* an identity. It cannot tell you when the thing that was
supposed to assign it didn't. This checks the **result** — the address git is
about to stamp on the commit — so it catches a wrong email however it got
there: a clobbered global config, an `includeIf` that doesn't match what you
assumed, an environment override from a GUI, a repo you cloned into the wrong
directory.

Worth knowing: git's own `user.useConfigOnly = true` stops git *guessing* an
identity from `username@hostname`. Set it, it's good. But it would not have
caught any of the above, because in all of them the email was configured — just
wrong.

## Install

```sh
brew install neosergio/tap/git-wrong-email
git wrong-email install
$EDITOR ~/.config/git-wrong-email/rules
```

`install` copies the hook, so run it again after `brew upgrade` to pick up the
new version.

Without Homebrew:

```sh
git clone https://github.com/neosergio/git-wrong-email
cd git-wrong-email
./bin/git-wrong-email install
$EDITOR ~/.config/git-wrong-email/rules
```

Put `bin/` on your `PATH` (or link `bin/git-wrong-email` into it) and it also
works as a git subcommand: `git wrong-email status`.

`install` copies the hook into `~/.config/git-wrong-email/hooks` under every
client-side hook name and points `core.hooksPath` at it. That is global: every
repository on the machine is covered, including the ones you clone tomorrow.
Nothing is written into any repository.

If `core.hooksPath` was already set — husky, lefthook, your own dotfiles —
`install` records it as `wrongEmail.chainTo` and keeps running it after the
check, rather than quietly replacing it.

## Rules

`~/.config/git-wrong-email/rules`, one rule per line:

```
<directory>  <email> [<email> ...]
```

```
~/work/acme/     you@acme.example
~/work/globex/   you@globex.example
~/code/          you@personal.example  you@users.noreply.github.com
*                you@personal.example  you@users.noreply.github.com
```

The first directory that *contains* the repository wins, so specific rules go
first and `*` goes last. A repository matching no rule is refused — an
unmatched repository is one you haven't thought about yet. Trailing slashes
matter in the sense you'd hope: `~/work/acme/` does not match
`~/work/acme-notes`.

List your personal directory explicitly rather than relying on `*`. The global
default is precisely the value a GUI client rewrites when it "syncs" a profile,
so being explicit is what makes the check bite.

## What it checks, and when

| Hook | Checks |
|---|---|
| `pre-commit`, `pre-merge-commit` | the author and committer about to be recorded |
| `pre-push` | every commit being pushed that no remote has yet |

The `pre-push` pass is the one that matters most, and the one most tools skip.
It re-reads the actual commits, so it still catches a bad email that got in via
`--no-verify`, via a GUI or coding agent that bypassed the commit hook, or via
a rebase or cherry-pick that rewrote someone else's commits under your name.

History a remote already has is deliberately not judged: it's public already,
and blocking a push over commits nobody can fix any more just teaches you to
pass `--no-verify`. So a merge commit authored by `noreply@github.com` coming
back down from the forge won't block your next push.

## Escapes

Carrying a collaborator's commits in one repository:

```sh
git config --add wrongEmail.allowedAuthor someone@example.com
```

That allows them as an **author** only. The committer is always you, and has no
escape.

Deliberate one-off bypass: `git commit --no-verify`, `git push --no-verify`.
A commit that slips past the first will still be caught by the second.

## Hook chaining

`core.hooksPath` makes git ignore every repository's own `.git/hooks`
*entirely* — which is why using it for a global check normally breaks every
repo that had local hooks. That's the reason most people don't do this.

So the script is installed under all 18 client-side hook names, and after its
own checks (only three names have any) it runs the repository's hook of the
same name, passing `pre-push` its stdin along. Local hooks keep working; you
just also get the check.

```sh
git wrong-email status      # where everything is, and whether it's active
git wrong-email uninstall   # removes the hooks, restores core.hooksPath, keeps your rules
```

## Tests

```sh
pytest        # 26 tests; needs pytest and git, nothing else
```

They build a throwaway `$HOME` with its own global config and drive real git in
a temp directory, so they never touch your `~/.gitconfig`.

## Compared to the alternatives

There are a lot of partial attempts at this; none of them did all four things
above, which is why this exists.

- **`includeIf` / identity switchers** (`bgit`, `zit`, `gh-account-guard`) set
  the identity. They don't verify the result, which is the failure mode.
- **`user.useConfigOnly`** stops git guessing an unset identity. It doesn't
  catch a configured-but-wrong one.
- **`pre-commit` framework hooks** (`pre-commit-check-git-user`,
  `verify-git-email`) need a config file committed into each repository — so
  it's opt-in per repo, impossible in someone else's repo, and commit-time
  only.
- **Editor plugins** (IntelliJ Git Identity Guard, VS Code Repo Identity Guard)
  work well if you live in that editor. The VS Code one also installs hooks and
  additionally verifies the account you authenticate as, which is a good idea
  this doesn't have yet.

## Not built yet

- Verifying the account you authenticate to the remote as, not just the email
- A `doctor` that cross-checks these rules against your `includeIf` blocks

## License

MIT
