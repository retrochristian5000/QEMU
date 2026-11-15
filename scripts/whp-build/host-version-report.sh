#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
# Read-only build-host identity for comparing a developer machine with CI.
# Missing optional utilities are observations, not setup failures.
set -eu

whp_report_field()
{
    printf '%s=%s\n' "$1" "$2"
}

whp_first_line()
{
    case "$1" in
        *'
'*) printf '%s\n' "${1%%'
'*}" ;;
        *) printf '%s\n' "$1" ;;
    esac
}

whp_report_tool()
{
    tool=$1
    location=$(command -v "$tool" 2>/dev/null || true)
    case "$location" in
        /*|*/*) ;;
        *) location=unavailable ;;
    esac
    whp_report_field "tool.$tool.path" "$location"
    if [ "$location" = unavailable ]; then
        whp_report_field "tool.$tool.version" unavailable
        return 0
    fi
    case "$tool" in
        perl)
            version=$("$location" -e 'print "$^V\n"' 2>/dev/null) || version= ;;
        *)
            version=$("$location" --version 2>/dev/null) || version= ;;
    esac
    first=$(whp_first_line "$version")
    whp_report_field "tool.$tool.version" "${first:-unknown}"
}

case "$0" in
    */*) whp_source_dir=${0%/*}/../.. ;;
    *) whp_source_dir=. ;;
esac
whp_source_dir=$(CDPATH= cd -P -- "$whp_source_dir" && pwd -P) || exit 1

whp_report_field report.schema 1
whp_report_field host.kernel "$(uname -s 2>/dev/null || printf unavailable)"
whp_report_field host.release "$(uname -r 2>/dev/null || printf unavailable)"
whp_report_field host.arch "$(uname -m 2>/dev/null || printf unavailable)"
whp_report_field ci.image_os "${ImageOS:-unavailable}"
whp_report_field ci.image_version "${ImageVersion:-unavailable}"
whp_report_field ci.runner_arch "${RUNNER_ARCH:-unavailable}"
whp_report_field source.commit "$(git -C "$whp_source_dir" rev-parse HEAD 2>/dev/null || printf unavailable)"

# Source pinning is distinct from the version of the installed system tool.
for module in toolchains/llvm-project toolchains/meson toolchains/bash \
    toolchains/perl toolchains/make toolchains/autoconf toolchains/sed \
    roms/openbios; do
    record=$(git -C "$whp_source_dir" ls-tree HEAD -- "$module" 2>/dev/null || true)
    case "$record" in
        '160000 commit '*) whp_sha=${record#160000 commit }
            whp_sha=${whp_sha%%[[:space:]]*} ;;
        *) whp_sha=unavailable ;;
    esac
    whp_report_field "source.$module" "$whp_sha"
    # A developer may have checked out a different submodule commit from the
    # superproject gitlink. Do not mistake the enclosing repo's HEAD for an
    # uninitialized submodule: --show-prefix is then nonempty.
    whp_checkout=unavailable
    if [ -d "$whp_source_dir/$module" ]; then
        whp_prefix=$(git -C "$whp_source_dir/$module" rev-parse --show-prefix 2>/dev/null || printf unavailable)
        if [ -z "$whp_prefix" ]; then
            whp_checkout=$(git -C "$whp_source_dir/$module" rev-parse HEAD 2>/dev/null || printf unavailable)
        fi
    fi
    whp_report_field "checkout.$module" "$whp_checkout"
    if [ "$whp_checkout" = unavailable ]; then
        whp_report_field "submodule.$module" uninitialized
    elif [ "$whp_sha" = "$whp_checkout" ]; then
        whp_report_field "submodule.$module" match
    else
        whp_report_field "submodule.$module" drift
    fi
done

if [ "$(uname -s 2>/dev/null || true)" = Darwin ]; then
    whp_report_field apple.os_version "$(sw_vers -productVersion 2>/dev/null || printf unavailable)"
    if [ -n "${DEVELOPER_DIR:-}" ]; then
        whp_developer=$DEVELOPER_DIR
        whp_origin=DEVELOPER_DIR
    else
        whp_developer=$(xcode-select -p 2>/dev/null || printf unavailable)
        whp_origin=xcode-select
    fi
    whp_report_field apple.developer_root "$whp_developer"
    whp_report_field apple.developer_origin "$whp_origin"
    whp_report_field apple.sdk_override "${SDKROOT:-none}"
    whp_report_field apple.deployment_target "${MACOSX_DEPLOYMENT_TARGET:-auto}"
    whp_xcrun=$(command -v xcrun 2>/dev/null || true)
    if [ -n "$whp_xcrun" ]; then
        whp_sdk=$("$whp_xcrun" --sdk macosx --show-sdk-path 2>/dev/null || printf unavailable)
        whp_sdk_version=$("$whp_xcrun" --sdk macosx --show-sdk-version 2>/dev/null || printf unavailable)
        whp_clang=$("$whp_xcrun" --sdk macosx --find clang 2>/dev/null || printf unavailable)
    else
        whp_sdk=unavailable
        whp_sdk_version=unavailable
        whp_clang=unavailable
    fi
    whp_report_field apple.active_sdk "$whp_sdk"
    whp_report_field apple.active_sdk_version "$whp_sdk_version"
    whp_report_field apple.xcrun_clang "$whp_clang"
    if [ -x "$whp_clang" ]; then
        whp_clang_version=$("$whp_clang" --version 2>/dev/null || true)
        whp_report_field apple.xcrun_clang_version "$(whp_first_line "$whp_clang_version")"
    else
        whp_report_field apple.xcrun_clang_version unavailable
    fi
    if command -v xcodebuild >/dev/null 2>&1; then
        whp_xcode=$(xcodebuild -version 2>/dev/null || true)
        whp_xcode_first=$(whp_first_line "$whp_xcode")
        whp_report_field apple.xcode_version "${whp_xcode_first:-unavailable}"
    else
        whp_report_field apple.xcode_version unavailable
    fi
fi

for tool in sh bash python3 clang clang++ gcc cc c++ cmake ninja make pkg-config \
    pkgconf git brew perl xcrun; do
    # POSIX sh need not implement --version, so record its resolved path only.
    if [ "$tool" = sh ]; then
        whp_report_field tool.sh.path "$(command -v sh 2>/dev/null || printf unavailable)"
    else
        whp_report_tool "$tool"
    fi
done

# The configured command may differ from the executable found through PATH.
whp_report_field selected.CC "${CC:-auto}"
whp_report_field selected.CXX "${CXX:-auto}"
whp_report_field selected.CC_FOR_BUILD "${CC_FOR_BUILD:-auto}"
whp_report_field selected.CXX_FOR_BUILD "${CXX_FOR_BUILD:-auto}"
whp_report_field selected.PYTHON "${PYTHON:-auto}"
whp_report_field selected.WHP_BUILD_BASH "${WHP_BUILD_BASH:-auto}"
whp_report_field selected.MAKE_CMD "${MAKE_CMD:-auto}"
whp_report_field selected.NINJA_CMD "${NINJA_CMD:-auto}"
whp_report_field selected.NATIVE_LLVM_DIR "${NATIVE_LLVM_DIR:-auto}"
