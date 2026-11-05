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
git wrong-email doctor
```

`install` copies the hook, so run it again after `brew upgrade` to pick up the
new version.

Without Homebrew:

```sh
git clone https://github.com/neosergio/git-wrong-email
cd git-wrong-email
./bin/git-wrong-email install
$EDITOR ~/.config/git-wrong-email/rules
./bin/git-wrong-email doctor
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

## Setting up a new client, step by step

The rules file only *checks*. Something else has to *set* the email for the
client's repositories, and git's own `includeIf` is the simplest way. So every
new client gets both. The example uses a client called Acme, a
directory `~/work/acme/` and an address `you@acme.example`; substitute your
own.

### Once per machine

```sh
brew install neosergio/tap/git-wrong-email
git wrong-email install
git config --global user.useConfigOnly true   # never guess user@hostname
```

### 1. Pick a directory for the client

Every repository for that client lives under it:

```sh
mkdir -p ~/work/acme
```

### 2. Set the client's email for that directory

A small file holding the client's identity, and an `includeIf` in
`~/.gitconfig` that loads it only for repositories under the directory:

```sh
git config --file ~/.gitconfig-acme user.email you@acme.example
git config --global includeIf."gitdir:~/work/acme/".path ~/.gitconfig-acme
```

You can run these from anywhere; both write to files in your home directory.
Keep the trailing slash in `gitdir:~/work/acme/`. Without it, the pattern
matches no repository *inside* the directory.

### 3. Add the rule

In `~/.config/git-wrong-email/rules`, **above** the `*` line:

```
~/work/acme/     you@acme.example
~/code/          you@personal.example  you@users.noreply.github.com
*                you@personal.example  you@users.noreply.github.com
```

Do steps 2 and 3 together, with the same address. Do 2 without 3 and the
client's repositories fall through to `*` and are refused. Do 3 without 2 and
they get your global email and are refused. Either way, you are told before
anything is pushed.

### 4. An SSH key, only if the client gave you a separate account

The commit email and the SSH key are unrelated: the email is text stamped on
each commit, while the key decides *which account* you push as. If the client
added your existing GitHub account to their organization, skip this step.
If they gave you a separate account, it needs its own key, because GitHub won't
accept one key on two accounts.

```sh
ssh-keygen -t ed25519 -C "you@acme.example" -f ~/.ssh/id_ed25519_acme
```

Add the `.pub` file to that account, then give it a host alias in
`~/.ssh/config`:

```
Host *
    AddKeysToAgent yes
    UseKeychain yes          # macOS: keep the passphrase in the Keychain

Host github.com
    IdentityFile ~/.ssh/id_ed25519
    IdentitiesOnly yes

Host github.com-acme
    HostName github.com
    IdentityFile ~/.ssh/id_ed25519_acme
    IdentitiesOnly yes
```

`IdentitiesOnly yes` matters. Once the agent holds both keys, ssh offers all of
them and GitHub accepts the first it recognises, which can be the wrong
account. Check that each alias logs in as the account you expect:

```sh
ssh -T git@github.com          # Hi <personal account>!
ssh -T git@github.com-acme     # Hi <client account>!
```

### 5. Clone into the client's directory

Use the alias if you set one up, and always give the destination:

```sh
git clone git@github.com-acme:acme/app.git ~/work/acme/app
```

Cloning somewhere else is exactly the mistake the check catches: a client
repository under `~/code/` would be refused for having the client's email.

### 6. Verify

```sh
git wrong-email doctor
```

```
identity a new repository would get
  ok    ~/work/acme/          you@acme.example  (from ~/.gitconfig-acme)
  ok    ~/code/               you@personal.example  (from ~/.gitconfig)
  ok    * (anywhere else)     you@personal.example  (from ~/.gitconfig)
```

Inside a single repository, `git config --show-origin user.email` shows which
file the email came from.

For the next client, repeat steps 1–6 with their directory and address.

## Doctor

`git wrong-email doctor` cross-checks everything above and exits 1 if anything
is off, giving the command that fixes it:

- **install**: `core.hooksPath` really points at the hooks.
- **rules**: no rule is unreachable, whether it is placed after `*` or inside a
  broader directory listed earlier. It also notes a directory that doesn't
  exist yet.
- **identity**: for every directory a rule or a `gitdir:` `includeIf` names,
  the email a *new* repository there would get, and whether the rules accept
  it. This catches a rule with no `includeIf`, an `includeIf` with no rule, an
  `includeIf` without a trailing slash, and one that points at a missing
  file.
- **repositories**: for repositories already cloned directly inside a rule's
  directory, the email git actually uses there, including a per-repository
  `user.email`. It also flags a repository whose own `core.hooksPath` switches
  the check off.
- **environment**: `GIT_AUTHOR_EMAIL` and similar overrides in the current
  shell, and whether `user.useConfigOnly` is set.

```
$ git wrong-email doctor
...
identity a new repository would get
  FAIL  ~/work/acme/          a repository here would commit as you@personal.example (from ~/.gitconfig),
        but line 1 of the rules allows only: you@acme.example
        fix: git config --file ~/.gitconfig-acme user.email you@acme.example
             git config --global includeIf."gitdir:~/work/acme/".path ~/.gitconfig-acme
```

It evaluates `gitdir:` and `gitdir/i:` conditions itself. That is exact for the
`~/dir/` and `/dir/` forms in this README, but looser than git for a lone `*`
in the middle of a pattern. Run it after any change to the rules or to
`~/.gitconfig`.

## What it checks, and when

| Hook | Checks |
|---|---|
| `pre-commit`, `pre-merge-commit` | the author and committer about to be recorded |
| `pre-push` | every commit being pushed that no remote has yet, and the tagger of every annotated tag being pushed |

The `pre-push` pass is the one that matters most, and the one most tools skip.
It re-reads the actual commits, so it still catches a bad email that got in via
`--no-verify`, via a GUI or coding agent that bypassed the commit hook, or via
a rebase or cherry-pick that rewrote someone else's commits under your name.

It also checks tags. An annotated tag records its own identity, the *tagger*,
taken from your committer settings when the tag was made. git has no pre-tag
hook, so a release tag made while `~/.gitconfig` held the wrong address is
first seen when it is pushed, including when it rides along with
`--follow-tags` or `--tags`. Lightweight tags have no tagger and pass.

History a remote already has is deliberately not judged: it's public already,
and blocking a push over commits nobody can fix any more just teaches you to
pass `--no-verify`. So a merge commit authored by `noreply@github.com` coming
back down from the forge won't block your next push.

## Escapes

Carrying a collaborator's commits in one repository:

```sh
git config --add wrongEmail.allowedAuthor someone@example.com
```

That allows them as an **author** only. It also allows them as the tagger of a
tag you push for them, such as an upstream release tag in a fork. The committer
is always you, and has no escape.

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
git wrong-email doctor      # cross-check rules, includeIf and cloned repositories
git wrong-email uninstall   # removes the hooks, restores core.hooksPath, keeps your rules
```

## Tests

```sh
pytest        # 40 tests; needs pytest and git, nothing else
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

- Verifying the account you authenticate to the remote as, not just the email.
  Cloning a client repository with `git@github.com:` instead of the client's
  SSH alias pushes as your personal account, and nothing here notices yet.

## License

MIT
