#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Verify GLib atomic integer reads are used only for appropriate counters.

The optional runtime probe exercises the trace dropped-event CAS protocol
under concurrent increments, using GLib rather than mocking atomic functions.
"""

import argparse
import os
from pathlib import Path
import shlex
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]


def verify_source():
    trace = (ROOT / "trace/simple.c").read_text(encoding="utf-8")
    dbus = (ROOT / "ui/dbus-listener.c").read_text(encoding="utf-8")
    qtree = (ROOT / "util/qtree.c").read_text(encoding="utf-8")
    compat = (ROOT / "meson.build").read_text(encoding="utf-8")

    assert "glib_req_ver = '>=2.66.0'" in compat
    assert "static gint trace_idx;" in trace
    assert "static gint dropped_events;" in trace
    assert "static volatile gint trace_idx;" not in trace
    assert "static volatile gint dropped_events;" not in trace

    writeout = trace.split("static gpointer writeout_thread(", 1)[1].split(
        "void trace_record_write_u64(", 1
    )[0]
    first_read = "dropped_count = g_atomic_int_get(&dropped_events);"
    cas = "while (!g_atomic_int_compare_and_exchange(&dropped_events,"
    assert writeout.count(first_read) == 2
    assert writeout.index(first_read) < writeout.index("if (dropped_count)") < writeout.index(cas)
    assert writeout.index(cas) < writeout.rindex(first_read)
    assert "g_atomic_int_inc(&dropped_events);" in trace
    assert "g_atomic_int_get(&trace_idx)" in trace
    assert "g_atomic_int_compare_and_exchange(&trace_idx," in trace

    # Atomic get is not a substitute for condition-variable coordination.
    assert "g_mutex_lock(&trace_lock);" in trace
    assert "g_cond_wait(&trace_available_cond, &trace_lock);" in trace
    assert "g_cond_signal(&trace_available_cond);" in trace

    for name in ("display", "cursor"):
        member = f"ddl->{name}_serial_to_discard"
        assert f"g_atomic_int_set(&{member}, serial);" in dbus
        assert f"g_atomic_int_get(&{member});" in dbus

    # A refcount decrement must make the destruction decision atomically.
    assert "g_atomic_int_inc(&tree->ref_count);" in qtree
    assert "g_atomic_int_dec_and_test(&tree->ref_count)" in qtree


def verify_runtime():
    test_c = r"""
#include <glib.h>

#define WORKERS 4
#define ITERATIONS 30000

static gint dropped;
static gint finished;

static gpointer producer(gpointer unused)
{
    int i;
    (void)unused;
    for (i = 0; i < ITERATIONS; ++i) {
        g_atomic_int_inc(&dropped);
    }
    g_atomic_int_inc(&finished);
    return NULL;
}

int main(void)
{
    GThread *threads[WORKERS];
    gint drained = 0;
    int i;

    for (i = 0; i < WORKERS; ++i) {
        threads[i] = g_thread_new("producer", producer, NULL);
    }
    while (g_atomic_int_get(&finished) != WORKERS ||
           g_atomic_int_get(&dropped) != 0) {
        gint observed = g_atomic_int_get(&dropped);
        if (observed == 0) {
            g_thread_yield();
            continue;
        }
        while (!g_atomic_int_compare_and_exchange(&dropped, observed, 0)) {
            observed = g_atomic_int_get(&dropped);
        }
        drained += observed;
    }
    for (i = 0; i < WORKERS; ++i) {
        g_thread_join(threads[i]);
    }
    return drained == WORKERS * ITERATIONS ? 0 : 1;
}
"""
    flags = shlex.split(subprocess.check_output(
        ["pkg-config", "--cflags", "glib-2.0"], text=True))
    libs = shlex.split(subprocess.check_output(
        ["pkg-config", "--libs", "glib-2.0"], text=True))
    cc = shlex.split(os.environ.get("CC", "cc"))
    with tempfile.TemporaryDirectory(prefix="whp-glib-atomic-") as d:
        source = Path(d) / "atomic.c"
        binary = Path(d) / "atomic"
        source.write_text(test_c, encoding="utf-8")
        subprocess.run(
            [*cc, "-std=gnu11", "-Wall", "-Wextra", "-Werror",
             *flags, str(source), "-o", str(binary), *libs],
            check=True,
        )
        subprocess.run([str(binary)], check=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", action="store_true")
    args = parser.parse_args()
    verify_source()
    if args.runtime:
        verify_runtime()
    print("GLib atomic counter/trace semantics verified")
