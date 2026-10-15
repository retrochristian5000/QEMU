# WHP QEMU Fork AI Rules

## Development Rules
- Always advance and commit the parent-repository gitlinks after working on submodules; pushing the child repository alone does not complete the task.
- Never generate branches
- Never create or commit Superpowers planning/spec artifacts in this repository; keep planning outside the repo

## Required Gitlink Synchronization
- First commit and push the actual changes in the submodule repository on its existing intended branch, then read that branch's new **remote HEAD SHA**. Do not mistake an unpushed local commit or an outdated checkout for the latest commit.
- Within the same work round, advance every **known** parent repository that records a gitlink to the changed submodule, not just the repository currently being edited. LLVM is a shared toolchain: QEMU's `toolchains/llvm-project` is one consumer, not a reason to assume other consumers do not exist. Discover additional consumer relationships from verified repository configuration and trees; do not invent them.
- For each verified consumer, update the actual gitlink tree entry to the intended latest pushed submodule commit, preserving Git mode `160000`. Commit and push the parent repository on its existing branch. A submodule checkout, `git submodule update --remote`, or a changed `.gitmodules` entry alone is **not** a committed gitlink update.
- After a submodule changes, do not deliberately leave its known consumer pinned to an older revision simply because it is used by other projects or because full integration tests have not run. Update the gitlink and separately state the test/validation status. If there is a confirmed incompatibility or the parent push is blocked, record the exact blocker and old/new SHA; never report propagation as complete.
- Independently re-read each remote parent branch's Git tree after pushing and verify that the `160000` gitlink SHA equals the intended remote child HEAD. Report the child SHA, parent commit, affected consumers, and any consumers not yet verified or advanced.
- Follow the Permission Rules for both submodule and ordinary files; never alter unrelated submodule pins as collateral changes. Preserve the no-new-branches rule throughout propagation.

## Permission Rules
- Never change a tracked file's mode or executable bit unless the user explicitly authorizes that specific permission change. Editing contents is not permission to change modes.
- Before modifying or replacing any tracked file, read its mode from the current branch's Git tree (for example, `git ls-tree HEAD -- path/to/file`). Do not infer permissions from filenames or extensions.
- Preserve the exact original Git tree mode when writing each changed file. For GitHub/Git API blob-and-tree edits, supply the existing mode explicitly (typically `100644` for nonexecutables, `100755` for executables, and `160000` for submodule gitlinks). Never blanket-apply `100644` to edited scripts.
- Do not use a file-update tool that may silently reset a file's mode unless it is known to preserve the original mode. Use a mode-preserving update method instead.
- Before committing or pushing, compare modes of every touched path with the base commit using `git diff --summary`, `git diff --raw`, or the equivalent Git tree entries. Reject and correct unintended mode changes before publishing.
- After pushing, independently check the remote branch tree: every touched file must retain its original mode unless an explicitly approved mode change was part of the request.
- If an unauthorized mode change slips through, restore the original mode immediately in the same round, push the correction, and verify it. Never leave an executable build entry or bootstrap script accidentally nonexecutable.
- Do not alter other paths' permissions as a side effect of a content-only change. In particular, preserve executable modes on `build.sh` and bootstrap scripts.

## Code Search Rules
- Resolve the repository boundary before searching. A submodule is a separate repository; do not expect parent-repository code search to traverse it.
- If an exact repository path is known, fetch/read that file directly before running a broad code search.
- For code content, search the narrowest relevant repository using symbols, identifiers, compiler diagnostics, or distinctive code fragments. Do not use issue/PR search for source-code discovery.
- For history questions, use commit/history search. For discussions, use issue/PR search. Do not substitute either for code search.
- Resolve submodule repository URLs from .gitmodules before searching a submodule. Never guess which upstream or fork owns the code.
- Prefer repository-native search for code. Use general web search only for external documentation, upstream evidence, or when the repository host cannot be searched directly.
- When a search returns no result, verify repository, branch/default-branch coverage, path, and submodule boundary before broadening the query.
- Avoid repeating an identical failed search. Change the scope, identifier, path, repository, or search method.
