# WHP QEMU Fork AI Rules

## Development Rules
- Always update the submodules after working on them
- Never generate branches
- Never create or commit Superpowers planning/spec artifacts in this repository; keep planning outside the repo

## Code Search Rules
- Resolve the repository boundary before searching. A submodule is a separate repository; do not expect parent-repository code search to traverse it.
- If an exact repository path is known, fetch/read that file directly before running a broad code search.
- For code content, search the narrowest relevant repository using symbols, identifiers, compiler diagnostics, or distinctive code fragments. Do not use issue/PR search for source-code discovery.
- For history questions, use commit/history search. For discussions, use issue/PR search. Do not substitute either for code search.
- Resolve submodule repository URLs from .gitmodules before searching a submodule. Never guess which upstream or fork owns the code.
- Prefer repository-native search for code. Use general web search only for external documentation, upstream evidence, or when the repository host cannot be searched directly.
- When a search returns no result, verify repository, branch/default-branch coverage, path, and submodule boundary before broadening the query.
- Avoid repeating an identical failed search. Change the scope, identifier, path, repository, or search method.
