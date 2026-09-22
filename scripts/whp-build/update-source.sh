#!/bin/sh
set -eu

SOURCE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
mode=${WHP_SOURCE_UPDATE:-auto}

case "$mode" in
    auto|0|1) ;;
    *)
        printf 'error: WHP_SOURCE_UPDATE must be auto, 0, or 1: %s\n' "$mode" >&2
        exit 1
        ;;
esac

[ "$mode" != 0 ] || exit 0

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

if [ "$mode" = auto ] && [ -n "${CI:-}" ]; then
    printf '%s\n' 'WHP source update: skipped under CI' >&2
    exit 0
fi

if ! command -v git >/dev/null 2>&1; then
    warn_or_fail 'git is unavailable, so source refresh cannot run'
    exit 0
fi

if ! git -C "$SOURCE_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    warn_or_fail 'source tree is not a Git worktree'
    exit 0
fi

branch=$(git -C "$SOURCE_DIR" symbolic-ref --quiet --short HEAD 2>/dev/null || true)
upstream=$(git -C "$SOURCE_DIR" rev-parse --abbrev-ref --symbolic-full-name     '@{upstream}' 2>/dev/null || true)

root_dirty=0
git -C "$SOURCE_DIR" diff --quiet --ignore-submodules=all -- || root_dirty=1
git -C "$SOURCE_DIR" diff --cached --quiet --ignore-submodules=all -- || root_dirty=1

if [ "$root_dirty" = 1 ]; then
    warn_or_fail 'tracked QEMU source changes prevent a safe fast-forward pull'
elif [ -z "$branch" ]; then
    warn_or_fail 'QEMU checkout is detached, so there is no branch to fast-forward'
elif [ -z "$upstream" ]; then
    warn_or_fail "QEMU branch '$branch' has no configured upstream"
else
    printf 'WHP source update: %s <- %s\n' "$branch" "$upstream" >&2
    if ! git -C "$SOURCE_DIR" pull --ff-only --recurse-submodules=no; then
        warn_or_fail "fast-forward pull from '$upstream' failed"
    fi
fi

# QEMU records exact submodule revisions in the superproject.  Keep those
# gitlinks authoritative: synchronize URLs, then materialize the newest pinned
# revisions supplied by the refreshed QEMU commit.  Do not use --remote here;
# branch-tip submodule updates would make the build non-reproducible and break
# the WHP gitlink validation used by the toolchain/firmware bootstraps.
if [ ! -f "$SOURCE_DIR/.gitmodules" ]; then
    exit 0
fi

dirty_submodules=$(
    git -C "$SOURCE_DIR" submodule foreach --quiet --recursive '
        if ! git diff --quiet --ignore-submodules=all -- ||
           ! git diff --cached --quiet --ignore-submodules=all --; then
            printf "%s\n" "$displaypath"
        fi
    ' 2>/dev/null || true
)

if [ -n "$dirty_submodules" ]; then
    printf '%s\n' 'warning: tracked submodule changes prevent a safe submodule refresh:' >&2
    printf '%s\n' "$dirty_submodules" >&2
    if [ "$mode" = 1 ]; then
        exit 1
    fi
    printf '%s\n' 'warning: keeping current submodule worktrees' >&2
    exit 0
fi

git -C "$SOURCE_DIR" submodule sync --recursive
if ! git -C "$SOURCE_DIR" submodule update --init --recursive; then
    warn_or_fail 'pinned submodule update failed'
    exit 0
fi

printf '%s\n' 'WHP source update: QEMU and pinned submodules are current' >&2
