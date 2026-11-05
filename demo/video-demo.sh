#!/bin/sh
# Demo for the git-wrong-email video: every step of the walkthrough, plus the
# ways it catches a wrong email, run one command at a time.
#
#   ./demo/video-demo.sh               press Enter to run each command
#   DEMO_AUTO=1 ./demo/video-demo.sh   no pauses; reports any step whose
#                                      outcome differs from the expected one
#   DEMO_KEEP=1 ...                    keep the sandbox afterwards
#
# Everything happens in a throwaway $HOME, so your real ~/.gitconfig, SSH keys
# and client names never appear on screen. Nothing touches the network:
# "GitHub" is a few bare repositories in the sandbox, and the git@github.com
# and git@github.com-acme URLs are mapped to them with url.insteadOf in a
# system config the viewer never sees.
#
# Needs git and `git wrong-email` on PATH (brew install neosergio/tap/git-wrong-email).

# shellcheck disable=SC2088 # literal ~ is wanted: in rules, and on screen
set -u

PERSONAL=tu@personal.example
CLIENT=tu@acme.example

# Physical path: the hook compares `git rev-parse --show-toplevel`, which is
# physical, against rules expanded from $HOME. /tmp is a symlink on macOS.
# Short, because it shows up in a few messages on screen.
SANDBOX=$(cd "$(mktemp -d /tmp/demo.XXXX)" && pwd -P)
export HOME="$SANDBOX/home"
export GIT_CONFIG_GLOBAL="$HOME/.gitconfig"
export GIT_CONFIG_SYSTEM="$SANDBOX/system-gitconfig"
export GIT_PAGER=cat PAGER=cat
unset GIT_CONFIG_NOSYSTEM GIT_AUTHOR_EMAIL GIT_COMMITTER_EMAIL \
    GIT_AUTHOR_NAME GIT_COMMITTER_NAME EMAIL XDG_CONFIG_HOME
mkdir -p "$HOME" "$SANDBOX/github/acme" "$SANDBOX/github/tu"

cleanup() {
    if [ "${DEMO_KEEP:-0}" = 1 ]; then
        echo "sandbox kept: $SANDBOX"
    else
        rm -rf "$SANDBOX"
    fi
}
trap cleanup EXIT
trap 'exit 130' INT

cat >"$GIT_CONFIG_SYSTEM" <<EOF
[init]
	defaultBranch = main
[advice]
	detachedHead = false
[url "$SANDBOX/github/"]
	insteadOf = git@github.com-acme:
	insteadOf = git@github.com:
EOF

if ! command -v git-wrong-email >/dev/null 2>&1; then
    echo "git-wrong-email is not on PATH: brew install neosergio/tap/git-wrong-email" >&2
    exit 1
fi

# --- presentation -----------------------------------------------------------

auto=${DEMO_AUTO:-0}
surprises=0

pause() { [ "$auto" = 1 ] || read -r _ </dev/tty; }

here() {
    case $PWD in
    "$HOME") echo "~" ;;
    "$HOME"/*) echo "~/${PWD#"$HOME"/}" ;;
    *) echo "$PWD" ;;
    esac
}

# A section banner; a natural cut point when editing.
part() {
    if [ "$auto" = 1 ]; then echo; else
        printf '\n\033[2m[enter: %s]\033[0m' "$1"
        pause
        clear
    fi
    printf '\033[1;35m== %s ==\033[0m\n' "$1"
}

# A line of narration, dimmed, for the presenter rather than the viewer.
say() { printf '\n\033[2m# %s\033[0m' "$*"; }

# Show a command, wait for Enter, run it in this shell (so cd sticks), and
# check its outcome: "ok" (default) expects success, "fail" a refusal.
run() {
    printf '\n\033[1;34m%s\033[0m \033[1;32m$\033[0m %s' "$(here)" "$1"
    pause
    [ "$auto" = 1 ] && echo
    eval "$1"
    rc=$?
    want=${2:-ok}
    if { [ "$want" = ok ] && [ $rc -ne 0 ]; } || { [ "$want" = fail ] && [ $rc -eq 0 ]; }; then
        surprises=$((surprises + 1))
        printf '\033[1;31m!! expected %s, got exit %s\033[0m\n' "$want" "$rc"
    fi
    return 0
}

# Set-up the viewer does not need to watch.
quietly() { "$@" >/dev/null 2>&1; }
nohooks() { git -c core.hooksPath=/dev/null "$@"; }

rules() { # write the rules file; the demo then shows it with cat
    printf '%s\n' "$@" >"$HOME/.config/git-wrong-email/rules"
}

# --- 1. the problem -----------------------------------------------------------

cd "$HOME" || exit 1
part "1. El problema"
quietly git config --global user.name "Tu Nombre"
quietly git config --global user.email "$PERSONAL"

say "Mi config global: mi correo personal. Todo bien."
run 'cat ~/.gitconfig'
run 'mkdir -p ~/code/notas && cd ~/code/notas && git init -q'
run 'git config user.email'
say "Un cliente grafico 'sincroniza' mi perfil del trabajo y reescribe el global..."
run "git config --global user.email $CLIENT"
run 'echo hola > README.md && git add . && git commit -qm "primer commit"'
say "Nadie me aviso. Mi repo personal tiene el correo del cliente:"
run "git log --format='%h  %ae  %s'"
run "git config --global user.email $PERSONAL"
say "Lo arreglo... pero el commit ya quedo. includeIf no lo habria evitado."

# --- 2. install ---------------------------------------------------------------

part "2. Instalar git-wrong-email"
run 'cd ~'
run 'git wrong-email install'
run 'git config --global user.useConfigOnly true'
rules "~/code/   $PERSONAL" \
    "*         $PERSONAL"
say "Las reglas: carpeta -> correos permitidos. La primera que coincide gana."
run 'cat ~/.config/git-wrong-email/rules'
run 'git wrong-email status'

# --- 3. a new client ----------------------------------------------------------

part "3. Un cliente nuevo, paso a paso"
# The client's repository, already on "GitHub".
quietly git init -q "$SANDBOX/seed"
(cd "$SANDBOX/seed" && echo app >README.md && nohooks add . &&
    nohooks -c user.email="$CLIENT" commit -qm "initial") >/dev/null 2>&1
quietly git clone -q --bare "$SANDBOX/seed" "$SANDBOX/github/acme/app.git"
rm -rf "$SANDBOX/seed"

say "Paso 1: una carpeta para el cliente"
run 'mkdir -p ~/work/acme'
say "Paso 2: el correo del cliente, solo para esa carpeta"
run "git config --file ~/.gitconfig-acme user.email $CLIENT"
run 'git config --global includeIf."gitdir:~/work/acme/".path ~/.gitconfig-acme'
run 'cat ~/.gitconfig'
say "Paso 3: la regla, ARRIBA del *"
rules "~/work/acme/  $CLIENT" \
    "~/code/       $PERSONAL" \
    "*             $PERSONAL"
run 'cat ~/.config/git-wrong-email/rules'
say "Paso 4: llave SSH, solo si el cliente te dio otra cuenta"
mkdir -p "$HOME/.ssh"
cat >"$HOME/.ssh/config" <<'EOF'
Host *
    AddKeysToAgent yes
    UseKeychain yes

Host github.com
    IdentityFile ~/.ssh/id_ed25519
    IdentitiesOnly yes

Host github.com-acme
    HostName github.com
    IdentityFile ~/.ssh/id_ed25519_acme
    IdentitiesOnly yes
EOF
run 'cat ~/.ssh/config'
say "(fuera de la demo: ssh -T git@github.com-acme  ->  Hi <cuenta del cliente>!)"
say "Paso 5: clonar con el alias, y SIEMPRE dando el destino"
run 'git clone -q git@github.com-acme:acme/app.git ~/work/acme/app'
say "Paso 6: verificar"
run 'cd ~/work/acme/app && git config --show-origin user.email'
run 'git wrong-email doctor'

# --- 4. breaking it on purpose -----------------------------------------------

part "4a. Romperlo: la regla debajo del *"
rules "~/code/       $PERSONAL" \
    "*             $PERSONAL" \
    "~/work/acme/  $CLIENT"
run 'cat ~/.config/git-wrong-email/rules'
run 'git wrong-email doctor' fail
rules "~/work/acme/  $CLIENT" \
    "~/code/       $PERSONAL" \
    "*             $PERSONAL"
say "La subo arriba del * y listo."

part "4b. Romperlo: la regla sin includeIf"
run 'git config --global --remove-section includeIf.gitdir:~/work/acme/'
run 'echo cambio >> README.md && git commit -qam "cambio"' fail
run 'git wrong-email doctor' fail
say "doctor me da el comando exacto:"
run 'git config --global includeIf."gitdir:~/work/acme/".path ~/.gitconfig-acme'
run 'git commit -qam "cambio"'

part "4c. Romperlo: un cliente grafico reescribe el global"
run "git config --global user.email $CLIENT"
run 'cd ~/code/notas && echo mas >> README.md && git commit -qam "mas notas"' fail
run 'git wrong-email doctor' fail
run "git config --global user.email $PERSONAL"
say "Esta vez nada llego a la historia."

part "4d. Romperlo: --no-verify, o una herramienta que se salta el hook"
quietly git init -q --bare "$SANDBOX/github/tu/blog.git"
run 'mkdir -p ~/code/blog && cd ~/code/blog && git init -q'
run 'git remote add origin git@github.com:tu/blog.git'
run 'echo "# blog" > README.md && git add . && git commit -qm "inicio" && git push -q -u origin main'
run "echo post >> README.md && git -c user.email=$CLIENT commit --no-verify -qam 'post'"
say "El commit paso. El push no:"
run 'git push -q' fail
run 'git commit --amend --no-edit --reset-author -q && git push -q'

part "4e. Romperlo: un tag con el correo equivocado"
say "Esto me paso de verdad con la v0.2.0."
run "GIT_COMMITTER_EMAIL=$CLIENT git tag -a v1.0 -m 'v1.0'"
run "git cat-file -p v1.0 | grep tagger"
run 'git push -q --follow-tags' fail
run "git tag -d v1.0 && git tag -a v1.0 -m 'v1.0' && git push -q --follow-tags"

# --- 5. escapes ---------------------------------------------------------------

part "5. Excepciones"
say "Commits de un colaborador: se aceptan como autor, nunca como committer."
run 'git config --add wrongEmail.allowedAuthor colega@example.com'
run 'GIT_AUTHOR_EMAIL=colega@example.com git commit -q --allow-empty -m "fix del colega"'
run "git log -1 --format='author=%ae  committer=%ce  %s'"
say "Y a proposito: git commit --no-verify / git push --no-verify"

part "6. Todo en orden"
run 'cd ~ && git wrong-email doctor'

echo
if [ "$surprises" = 0 ]; then
    printf '\033[1;32mdemo complete\033[0m\n'
else
    printf '\033[1;31m%s step(s) did not behave as expected\033[0m\n' "$surprises"
    exit 1
fi
