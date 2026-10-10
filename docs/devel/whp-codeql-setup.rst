WHP QEMU CodeQL scanning policy
=============================

Status: GitHub CodeQL default setup is the active scanning mechanism for
this repository. Do not restore the previous advanced-setup workflow while
default setup remains enabled.

Why the advanced workflow was retired
-------------------------------------

On October 10, 2026, the .github/workflows/codeql.yml file existed alongside
GitHub's automatically generated default-setup workflow. GitHub rejected the
advanced workflow's SARIF upload after completing analysis, with the error::

   CodeQL analyses from advanced configurations cannot be processed
   when the default setup is enabled

The advanced workflow used a four-language matrix (Actions, C/C++, Python,
Rust), and was repeatedly scheduled and subsequently cancelled or failed.
Default setup was independently running the same four languages: Actions,
Python and Rust completed successfully in the audited run; C/C++ was still
running when inspected. Re-running the advanced workflow cannot fix this
configuration conflict.

The original advanced workflow is retained in Git history. Removing its
workflow file avoids duplicate runs and rejected submissions without
changing QEMU's compiler, source files, or bootstrap dependency graph.

Verification
------------

* Inspect the repository's Actions tab for generated runs named
  "Push on master" (the default-setup workflow).
* Under Settings > Advanced Security > Code scanning, verify that CodeQL
  analysis is still configured for default setup and includes Actions,
  C/C++, Python, and Rust.
* In the default-setup run, verify that each language's Perform CodeQL
  Analysis job succeeds; an in-progress C/C++ job is not evidence of
  successful C/C++ scanning.
* Confirm new pushes no longer start the old CodeQL Advanced workflow.
  Historic failed runs remain part of GitHub Actions history.
* QEMU CodeQL results concern the checked-out QEMU sources. Pinned LLVM,
  OpenBIOS, and other submodules must be assessed in their own repositories
  unless their source is explicitly included in a scan.

Evidence at time of audit:

* Advanced setup run (rejected SARIF):
  https://github.com/retrochristian5000/QEMU/actions/runs/38090116435
* Default setup run (three languages completed, C/C++ in progress):
  https://github.com/retrochristian5000/QEMU/actions/runs/38090116533

Changing setup later
--------------------

Use only one CodeQL setup at a time. If a manual C/C++ build is needed
for higher-fidelity scanning of QEMU's generated sources, first disable
default setup in GitHub repository security settings, then restore and
maintain an advanced workflow with a verified build step. A workflow-only
change cannot disable the repository's default setup.

See GitHub Docs on the default/advanced conflict:
https://docs.github.com/en/code-security/reference/code-scanning/troubleshoot-analysis-errors/results-different-than-expected
