#!/bin/sh
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
script_name=${0##*/}
bash_name=${script_name%.sh}.bash
bash_runner=${WHP_BUILD_BASH:-}
if [ -z "$bash_runner" ]; then
    bash_runner=$(command -v bash 2>/dev/null || true)
fi
if [ -z "$bash_runner" ]; then
    printf 'error: GNU Bash is required for %s\n' "$script_name" >&2
    exit 1
fi

# The Bash implementation publishes exactly one installed toolchain prefix on
# stdout. Validate that producer/consumer handoff here instead of allowing an
# empty or partial prefix to become /bin/clang, /bin/llvm-ar, or /bin/ld64.lld
# in build.sh after a bootstrap-side failure.
native_llvm_dir=$(
    "$bash_runner" "$script_dir/$bash_name" "$@"
) || exit $?
if [ -z "$native_llvm_dir" ] || [ ! -d "$native_llvm_dir" ]; then
    printf 'error: native LLVM bootstrap returned an invalid prefix: %s\n' \
        "${native_llvm_dir:-<empty>}" >&2
    exit 1
fi
for tool in clang clang++ llvm-ar llvm-ranlib llvm-nm llvm-objcopy llvm-readelf; do
    if [ ! -x "$native_llvm_dir/bin/$tool" ]; then
        printf 'error: native LLVM bootstrap did not provide %s: %s\n' \
            "$tool" "$native_llvm_dir/bin/$tool" >&2
        exit 1
    fi
done
if [ "$(uname -s)" = Darwin ]; then
    if [ ! -x "$native_llvm_dir/bin/ld64.lld" ]; then
        printf 'error: native LLVM bootstrap did not provide ld64.lld: %s\n' \
            "$native_llvm_dir/bin/ld64.lld" >&2
        exit 1
    fi
    if [ ! -f "$native_llvm_dir/lib/libLTO.dylib" ]; then
        printf 'error: native LLVM bootstrap did not provide libLTO.dylib: %s\n' \
            "$native_llvm_dir/lib/libLTO.dylib" >&2
        exit 1
    fi
fi

printf '%s\n' "$native_llvm_dir"
