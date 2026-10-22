Muon Meson quality lane
=======================

Muon is used only as an optional Meson linter/formatter. It must not become
the QEMU build driver, replace the native LLVM toolchain, or override the
existing Meson syntax and configure-warning CI gates.

The ``Muon Meson lint and cleanup`` GitHub Actions workflow runs on Meson
definition changes and can also be launched manually. It bootstraps an
**exact pinned upstream Muon revision**, separate from QEMU's toolchains,
and audits tracked ``meson.build``, ``meson_options.txt``, and
``meson.options`` files with ``muon check`` and ``muon fmt -q``.

Parsing errors fail CI. Legacy formatting drift is reported but does not
block unrelated code: wholesale normalization of inherited QEMU source is
not an acceptable side effect of adding the formatter.

For automated cleanup, run the workflow manually with ``mode=cleanup``
and choose ``scope=file`` (default, ``path=meson.build``) or explicitly
``scope=all``. The temporary checkout is formatted using ``muon fmt -i``.
Only tracked Meson definitions are eligible; the generated diff is checked
with Meson's own parser, a second Muon check, and ``git diff --check``.
The resulting ``muon-meson-cleanup.patch`` is published as a workflow
artifact for review. **It is not pushed or committed automatically**.
Apply reviewed patches manually to avoid silent, large formatting churn.
The workflow has only ``contents: read`` permission.
