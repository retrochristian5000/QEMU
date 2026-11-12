#!/bin/sh
set -eu

case "$0" in
    */*) whp_entry_dir=${0%/*}; [ -n "$whp_entry_dir" ] || whp_entry_dir=/ ;;
    *) whp_entry_dir=. ;;
esac
SOURCE_DIR=$(CDPATH= cd -- "$whp_entry_dir/../.." && pwd)
unset whp_entry_dir
mode=${WHP_SOURCE_UPDATE:-auto}
detail=${WHP_SOURCE_UPDATE_VERBOSE:-0}

# The updater is callable before managed tools and independently of build.sh.
# Keep its diagnostic control strict, dependency-free, and stderr-only.
case "$detail" in
    0|1) ;;
    *)
        printf 'error: WHP_SOURCE_UPDATE_VERBOSE must be 0 or 1: %s\n' "$detail" >&2
        exit 1
        ;;
esac
whp_update_detail()
{
    [ "$detail" = 1 ] || return 0
    printf 'WHP source update detail: %s\n' "$1" >&2
}

case "$mode" in
    auto|0|1) ;;
    *)
        printf 'error: WHP_SOURCE_UPDATE must be auto, 0, or 1: %s\n' "$mode" >&2
        exit 1
        ;;
esac

[ "$mode" != 0 ] || {
    whp_update_detail 'source refresh disabled (WHP_SOURCE_UPDATE=0)'
    exit 0
}
whp_update_detail "mode=$mode; requested detail=$detail"

# 'retained' remains authoritative until HEAD is checked against upstream
# after a successful fast-forward (including a no-op merge).
update_outcome=retained

warn_or_fail()
{
    message=$1
    if [ "$mode" = 1 ]; then
        printf 'error: %s\n' "$message" >&2
        exit 1
    fi
    printf 'warning: %s; continuing with the current checkout\n' "$message" >&2
    return 0
}

# Many local shells export CI=false or CI=0.  A nonempty string is
# not proof of CI; reserve the automatic-update skip for enabled CI flags.
if [ "$mode" = auto ]; then
    case "${CI:-}" in
        ''|0|false|FALSE|False|no|NO) ;;
        *)
            printf '%s\n' 'WHP source update: skipped under CI' >&2
            exit 0
            ;;
    esac
fi

# build.sh selects a single Git seed before entering this updater. When run
# directly for diagnostics, retain the historical PATH-based Git fallback.
WHP_UPDATE_GIT=${WHP_GIT_SEED:-git}
if ! command -v "$WHP_UPDATE_GIT" >/dev/null 2>&1; then
    warn_or_fail 'git is unavailable, so source refresh cannot run'
    exit 0
fi

if ! "$WHP_UPDATE_GIT" -C "$SOURCE_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    warn_or_fail 'source tree is not a Git worktree'
    exit 0
fi
whp_update_detail "validated Git seed: $WHP_UPDATE_GIT"

branch=$("$WHP_UPDATE_GIT" -C "$SOURCE_DIR" symbolic-ref --quiet --short HEAD 2>/dev/null || true)
upstream_ref=$("$WHP_UPDATE_GIT" -C "$SOURCE_DIR" rev-parse --symbolic-full-name '@{upstream}' 2>/dev/null || true)
remote=
merge_ref=
if [ -n "$branch" ]; then
    remote=$("$WHP_UPDATE_GIT" -C "$SOURCE_DIR" config --get "branch.$branch.remote" 2>/dev/null || true)
    merge_ref=$("$WHP_UPDATE_GIT" -C "$SOURCE_DIR" config --get "branch.$branch.merge" 2>/dev/null || true)
fi
whp_update_detail "branch=${branch:-<detached>}; upstream=${upstream_ref:-<unconfigured>}; remote=${remote:-<none>}; ref=${merge_ref:-<none>}"

root_dirty=0
"$WHP_UPDATE_GIT" -C "$SOURCE_DIR" diff --quiet --ignore-submodules=all -- || root_dirty=1
"$WHP_UPDATE_GIT" -C "$SOURCE_DIR" diff --cached --quiet --ignore-submodules=all -- || root_dirty=1

if [ "$root_dirty" = 1 ]; then
    warn_or_fail 'tracked QEMU source changes prevent a safe fast-forward update'
elif [ -z "$branch" ]; then
    warn_or_fail 'QEMU checkout is detached, so there is no branch to fast-forward'
elif [ -z "$upstream_ref" ] || [ -z "$remote" ] || [ -z "$merge_ref" ]; then
    warn_or_fail "QEMU branch '$branch' has no complete configured upstream"
else
    printf 'WHP source update: %s <- %s\n' "$branch" "$upstream_ref" >&2

    # Query only the configured upstream ref. A no-op build transfers only the
    # remote ref advertisement instead of running a full fetch negotiation.
    if [ "$remote" = "." ]; then
        remote_oid=$("$WHP_UPDATE_GIT" -C "$SOURCE_DIR" rev-parse "$merge_ref^{commit}" 2>/dev/null || true)
    else
        remote_line=$("$WHP_UPDATE_GIT" -C "$SOURCE_DIR" ls-remote "$remote" "$merge_ref" 2>/dev/null || true)
        # Git advertises "<oid><TAB><ref>"; keep only its first field.
        # This runs before the sed seed is guaranteed to exist.
        remote_oid=${remote_line%%[[:space:]]*}
        unset remote_line
    fi

    if [ -z "$remote_oid" ]; then
        warn_or_fail "could not resolve upstream ref '$merge_ref' from '$remote'"
    else
        upstream_oid=$("$WHP_UPDATE_GIT" -C "$SOURCE_DIR" rev-parse "$upstream_ref^{commit}" 2>/dev/null || true)
        whp_update_detail "advertised upstream commit=$remote_oid; local tracking commit=${upstream_oid:-<missing>}"

        if [ "$remote_oid" != "$upstream_oid" ]; then
            if [ "$remote" != "." ]; then
                printf '%s\n' 'WHP source update: fetching configured branch only (no tags or submodules)' >&2
                if ! "$WHP_UPDATE_GIT" -C "$SOURCE_DIR" fetch --no-tags --no-recurse-submodules \
                    "$remote" "$merge_ref:$upstream_ref"; then
                    warn_or_fail "targeted fetch from '$remote' failed"
                    upstream_oid=
                else
                    upstream_oid=$("$WHP_UPDATE_GIT" -C "$SOURCE_DIR" rev-parse "$upstream_ref^{commit}" 2>/dev/null || true)
                fi
            else
                upstream_oid=$remote_oid
            fi
        else
            printf '%s\n' 'WHP source update: upstream ref unchanged; object fetch skipped' >&2
        fi

        if [ -n "$upstream_oid" ]; then
            before_head=$("$WHP_UPDATE_GIT" -C "$SOURCE_DIR" rev-parse HEAD 2>/dev/null || true)
            if [ -z "$before_head" ]; then
                warn_or_fail 'cannot determine local HEAD before fast-forward'
            elif "$WHP_UPDATE_GIT" -C "$SOURCE_DIR" merge --ff-only "$upstream_ref" >/dev/null; then
                after_head=$("$WHP_UPDATE_GIT" -C "$SOURCE_DIR" rev-parse HEAD 2>/dev/null || true)
                if [ -z "$after_head" ]; then
                    warn_or_fail 'cannot verify local HEAD after fast-forward'
                elif [ "$before_head" != "$after_head" ]; then
                    update_outcome=updated
                elif [ "$after_head" = "$upstream_oid" ]; then
                    update_outcome=current
                else
                    # merge --ff-only accepted the existing local branch;
                    # it may be ahead of upstream, not exactly equal to it.
                    update_outcome=local-ahead
                fi
                whp_update_detail "HEAD before=$before_head; HEAD after=${after_head:-<unknown>}; result=$update_outcome"
            else
                warn_or_fail "fast-forward update from '$upstream_ref' failed"
            fi
        fi
        unset upstream_oid
    fi
    unset remote_oid
fi

# Do not materialize every QEMU submodule here. The WHP dependency helpers
# initialize only the pinned sources they actually consume, normally with
# --depth 1 and gitlink verification. This keeps a routine source refresh from
# downloading firmware/toolchains unrelated to the selected build.
#
# URL synchronization is local and cheap, so keep it global to make later lazy
# initialization honor any .gitmodules URL changes from the refreshed QEMU tree.
if [ -f "$SOURCE_DIR/.gitmodules" ]; then
    "$WHP_UPDATE_GIT" -C "$SOURCE_DIR" submodule sync --recursive >/dev/null
fi

# DTC is reconciled by build.sh after the selected Python and Git bootstrap.
# Keep this early updater limited to the parent QEMU revision and gitlink
# metadata: it may fast-forward/re-exec before those tools even exist.

case "$update_outcome" in
    updated)
        printf 'WHP source update: fast-forwarded %s; pinned submodules remain lazy\n' "$branch" >&2
        ;;
    current)
        printf '%s\n' 'WHP source update: QEMU current; pinned submodules remain lazy' >&2
        ;;
    local-ahead)
        printf 'WHP source update: local %s is ahead of %s; checkout preserved; pinned submodules remain lazy\n' \
            "$branch" "$upstream_ref" >&2
        ;;
    retained)
        printf '%s\n' 'WHP source update: retained checkout (refresh unverified); pinned submodules remain lazy' >&2
        ;;
esac
