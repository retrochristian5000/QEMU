#!/bin/sh
#
# This code is licensed under the GPL version 2 or later.  See
# the COPYING file in the top-level directory.

substat=".git-submodule-status"

command=$1
shift
maybe_modules="$@"

test -z "$maybe_modules" && exit 0

# This helper runs as its own process. Prevent inherited Git repository
# overrides from redirecting validation and status calls to the parent tree.
# -C alone does not clear GIT_WORK_TREE or GIT_DIR.
unset GIT_DIR GIT_WORK_TREE GIT_COMMON_DIR GIT_INDEX_FILE
unset GIT_OBJECT_DIRECTORY GIT_ALTERNATE_OBJECT_DIRECTORIES
unset GIT_PREFIX GIT_NAMESPACE

# Meson wraps such as subprojects/dtc are not QEMU Git submodules.
# Reject them before touching the submodule status ledger or any gitlink.
for m in $maybe_modules; do
    case "$m" in
        subprojects/*)
            printf "%s: refusing Meson-owned source '%s'; use its Meson wrap instead\n" "$0" "$m" >&2
            exit 1
            ;;
    esac
done

test -z "$GIT" && GIT=$(command -v git)

cd "$(dirname "$0")/.."

# Use the same non-rewinding source guard as the WHP host bootstraps.
. ./scripts/whp-build/shell-functions.sh

# Preserve the historical GIT='wrapper git' interface for this QEMU helper.
whp_legacy_git() {
    # Intentional splitting of the caller's Git command and optional wrapper.
    $GIT "$@"
}

no_git_error=
if ! test -e ".git"; then
    no_git_error='no git checkout exists'
elif test -z "$GIT"; then
    no_git_error='git binary not found'
fi

is_git() {
    test -z "$no_git_error"
}

update_error() {
    printf '%s: %s\n' "$0" "$*"
    echo
    printf "Unable to automatically checkout GIT submodules '%s'.\n" "$modules"
    echo "If you require use of an alternative GIT binary (for example to"
    echo "enable use of a transparent proxy), please disable automatic"
    echo "GIT submodule checkout with:"
    echo
    echo " $ ./configure --disable-download"
    echo
    echo "and then manually update submodules prior to running make, with:"
    echo
    printf " $ GIT='tsocks git' scripts/git-submodule.sh update %s\n" "$modules"
    echo
    exit 1
}

validate_error() {
    if is_git && test "$1" = "validate"; then
        echo "GIT submodules checkout is out of date, and submodules"
        echo "configured for validate only. Please run"
        printf '  scripts/git-submodule.sh update %s\n' "$maybe_modules"
        echo "from the source directory or call configure with"
        echo "  --enable-download"
    fi
    exit 1
}

check_updated() {
    # The ledger records checkout status, not a fixed SHA requirement.
    # Accept the recorded commit or a proven descendant; a different SHA
    # by itself is not evidence that an initialized checkout is unusable.
    module=$1
    test ! -L "$module" && test -e "$module/.git" || return 1
    entry=$(whp_legacy_git ls-tree HEAD -- "$module") || return 1
    set -- $entry
    test "${1:-}" = 160000 && test "${2:-}" = commit || return 1
    pin=$3
    current=$(whp_legacy_git -C "$module" rev-parse --verify HEAD) || return 1

    # Refuse a submodule checkout resolving to an unrelated Git worktree.
    top=$(whp_legacy_git -C "$module" rev-parse --show-toplevel) || return 1
    actual=$(CDPATH= cd -- "$module" && pwd -P) || return 1
    physical_top=$(CDPATH= cd -- "$top" && pwd -P) || return 1
    # Treat case-only aliases on case-insensitive filesystems as the same
    # worktree, but never accept an unrelated directory.
    # Reuse the shared identity test so unsupported -ef is not confused with
    # an ordinary mismatch. This retains its exact-path fast path.
    whp_same_directory "$actual" "$physical_top" || return 1

    test "$current" = "$pin" && return 0
    whp_legacy_git -C "$module" merge-base --is-ancestor "$pin" "$current"
}

if is_git; then
    # Read-only status and validation must not create or rewrite the ledger.
    modules=""
    for m in $maybe_modules
    do
        $GIT submodule status $m 1> /dev/null 2>&1
        if test $? = 0
        then
            modules="$modules $m"
            # The ledger is observational and never an ancestry authority.
        else
            printf 'warn: ignoring non-existent submodule %s\n' "$m"
        fi
    done
else
    modules=$maybe_modules
fi

case "$command" in
status|validate)
    for module in $modules; do
        if is_git; then
            check_updated $module || validate_error "$command"
        elif ! (set xyz "$module"/* && test -e "$2"); then
            # The directory does not exist or it contains no files
            printf '%s: sources not available for %s and %s\n' "$0" "$module" "$no_git_error"
            validate_error "$command"
        fi
    done
    ;;

update)
    is_git || {
        printf '%s: unexpectedly called with submodules but %s\n' "$0" "$no_git_error"
        exit 1
    }

    # A plain 'submodule update --init' can rewind a newer detached checkout.
    # The shared helper instead fast-forwards stale pins and preserves proven
    # descendants, including remote tips selected with 'update --remote'.
    for module in $modules; do
        whp_git_submodule_prepare "$(pwd -P)" "$module" whp_legacy_git ||
            update_error "failed to prepare module $module"
        check_updated "$module" || update_error "invalid history for module $module"
    done

    (if test -f "$substat"; then
         while IFS= read -r REPLY; do
             for module in $modules; do
                 case $REPLY in
                     *" $module"|*" $module "*) continue 2 ;;
                 esac
             done
             printf '%s\n' "$REPLY"
         done < "$substat"
     fi
     $GIT submodule status $modules
    ) > "$substat.new" || {
        rm -f "$substat.new"
        update_error "failed to save git submodule status"
    }
    mv -f "$substat.new" "$substat" || update_error "failed to install status ledger"
    ;;
esac

exit 0
