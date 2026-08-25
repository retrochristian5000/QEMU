#!/usr/bin/env bash
set -euo pipefail

root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
profile="$root/scripts/bootstrap-win9x-clang.sh"
triple_names="$root/toolchains/llvm-project/llvm/include/llvm/TargetParser/TripleName.def"
config="$root/scripts/whp-config/config.py"
prepare_sources="$root/scripts/whp-build/prepare-sources.bash"

[[ -f "$profile" ]] || {
    printf 'error: Win9x LLVM bootstrap is missing: %s\n' "$profile" >&2
    exit 1
}
[[ -f "$triple_names" ]] || {
    printf 'error: LLVM triple table is missing: %s\n' "$triple_names" >&2
    exit 1
}

grep -Fq 'WIN9X_TARGET="${WIN9X_TOOLCHAIN_TARGET:-i386-pc-win9x}"' "$profile"
grep -Fq -- '-DLLD_ENABLE_BACKENDS=ELF;COFF' "$profile"
# The generated wrapper must preserve this variable for expansion when the
# wrapper runs, so the generator source contains an escaped dollar sign.
grep -Fq -- '--target="\$WIN9X_TARGET"' "$profile"
grep -Fq -- '-march=i386' "$profile"
grep -Fq '/machine:x86' "$profile"
grep -Fq '/subsystem:windows,4.0' "$profile"
grep -Fq '/nodefaultlib' "$profile"
grep -Fq 'TRIPLE_OS_ALIAS(Win32, "win9x")' "$triple_names"
grep -Fq "Option('BOOTSTRAP_WIN9X_TOOLCHAIN', 'Windows 9x cross-tools'" "$config"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
source_dir="$tmp/source"
build_dir="$tmp/build"
fake_bin="$tmp/bin"
marker="$tmp/win9x-bootstrap-ran"
git_log="$tmp/git.log"
mkdir -p "$source_dir/scripts" "$source_dir/.git" "$fake_bin"

cat >"$source_dir/scripts/bootstrap-win9x-clang.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "${I386_LLVM_SUBMODULE_PATH:-}" >"$WIN9X_TEST_MARKER"
EOF
chmod +x "$source_dir/scripts/bootstrap-win9x-clang.sh"

cat >"$fake_bin/git" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$*" >>"$WIN9X_GIT_LOG"
EOF
chmod +x "$fake_bin/git"

export SOURCE_DIR="$source_dir"
export BUILD_DIR="$build_dir"
export HOST_OS=Linux
export MACOS_VERIFY_TOOLCHAIN=0
export QEMU_HOST_LTO=0
export BUILD_OPENBIOS=0
export BOOTSTRAP_POWERPC_TOOLCHAIN=0
export BUILD_SEABIOS=0
export BOOTSTRAP_I386_TOOLCHAIN=0
export I386_LLVM_SUBMODULE_PATH=toolchains/llvm-project
export WHP_BUILD_BASH=/bin/bash
export MAKE_CMD=make
export JOBS=1
export WIN9X_TEST_MARKER="$marker"
export WIN9X_GIT_LOG="$git_log"
export PATH="$fake_bin:$PATH"

source "$prepare_sources"

BOOTSTRAP_WIN9X_TOOLCHAIN=0
whp_prepare_sources
[[ ! -e "$marker" ]] || {
    printf 'error: disabled Win9x cross-tools unexpectedly ran bootstrap\n' >&2
    exit 1
}

BOOTSTRAP_WIN9X_TOOLCHAIN=1
whp_prepare_sources
[[ -f "$marker" ]] || {
    printf 'error: enabled Win9x cross-tools did not run bootstrap\n' >&2
    exit 1
}
grep -Fxq 'toolchains/llvm-project' "$marker"
grep -Fq 'submodule sync -- toolchains/llvm-project' "$git_log"
grep -Fq 'submodule update --init -- toolchains/llvm-project' "$git_log"

printf 'Win9x LLVM target and menu wiring look correct\n'
