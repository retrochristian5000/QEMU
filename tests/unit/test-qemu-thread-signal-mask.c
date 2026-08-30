/*
 * QEMU POSIX thread signal-mask tests
 *
 * This work is licensed under the terms of the GNU GPL, version 2 or later.
 * See the COPYING file in the top-level directory.
 */

#include "qemu/osdep.h"
#include "qemu/thread.h"

typedef struct ThreadSignalMask {
    sigset_t mask;
} ThreadSignalMask;

static void *capture_thread_signal_mask(void *opaque)
{
    ThreadSignalMask *state = opaque;
    int ret;

    ret = pthread_sigmask(SIG_SETMASK, NULL, &state->mask);
    g_assert_cmpint(ret, ==, 0);
    return NULL;
}

static void test_darwin_thread_signal_mask(void)
{
    ThreadSignalMask state = { 0 };
    QemuThread thread;
    sigset_t bus_set;
    sigset_t original_mask;
    sigset_t current_mask;
    int ret;

    sigemptyset(&bus_set);
    sigaddset(&bus_set, SIGBUS);

    ret = pthread_sigmask(SIG_BLOCK, &bus_set, &original_mask);
    g_assert_cmpint(ret, ==, 0);

    qemu_thread_create(&thread, "signal-mask-test",
                       capture_thread_signal_mask, &state,
                       QEMU_THREAD_JOINABLE);
    qemu_thread_join(&thread);

    ret = pthread_sigmask(SIG_SETMASK, NULL, &current_mask);
    g_assert_cmpint(ret, ==, 0);
    g_assert_cmpint(sigismember(&current_mask, SIGBUS), ==, 1);

    ret = pthread_sigmask(SIG_SETMASK, &original_mask, NULL);
    g_assert_cmpint(ret, ==, 0);

    g_assert_cmpint(sigismember(&state.mask, SIGSEGV), ==, 0);
    g_assert_cmpint(sigismember(&state.mask, SIGFPE), ==, 0);
    g_assert_cmpint(sigismember(&state.mask, SIGILL), ==, 0);
    g_assert_cmpint(sigismember(&state.mask, SIGBUS), ==, 0);
    g_assert_cmpint(sigismember(&state.mask, SIGTERM), ==, 1);
}

int main(int argc, char **argv)
{
    g_test_init(&argc, &argv, NULL);
    g_test_add_func("/qemu-thread/darwin/signal-mask",
                    test_darwin_thread_signal_mask);
    return g_test_run();
}
