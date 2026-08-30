/*
 * QEMU Darwin POSIX thread tests
 *
 * This work is licensed under the terms of the GNU GPL, version 2 or later.
 * See the COPYING file in the top-level directory.
 */

#include "qemu/osdep.h"
#include "qemu/thread.h"

typedef struct ThreadSignalMask {
    sigset_t mask;
} ThreadSignalMask;

typedef struct HostThreadId {
    int64_t id;
} HostThreadId;

static void *capture_thread_signal_mask(void *opaque)
{
    ThreadSignalMask *state = opaque;
    int ret;

    ret = pthread_sigmask(SIG_SETMASK, NULL, &state->mask);
    g_assert_cmpint(ret, ==, 0);
    return NULL;
}

static void *capture_host_thread_id(void *opaque)
{
    HostThreadId *state = opaque;

    state->id = qemu_get_host_thread_id();
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

static void test_darwin_host_thread_id(void)
{
    HostThreadId child = { 0 };
    QemuThread thread;
    int64_t main_id = qemu_get_host_thread_id();

    qemu_thread_create(&thread, "thread-id-test",
                       capture_host_thread_id, &child,
                       QEMU_THREAD_JOINABLE);
    qemu_thread_join(&thread);

    g_assert_cmpint(main_id, >, 0);
    g_assert_cmpint(child.id, >, 0);
    g_assert_cmpint(child.id, !=, main_id);
}

static int64_t monotonic_ns(void)
{
    struct timespec ts;
    int ret;

    ret = clock_gettime(CLOCK_MONOTONIC, &ts);
    g_assert_cmpint(ret, ==, 0);
    return (int64_t)ts.tv_sec * 1000000000LL + ts.tv_nsec;
}

static void assert_timed_wait_elapsed(int64_t start_ns, int64_t end_ns)
{
    int64_t elapsed_ns = end_ns - start_ns;

    /* Leave ample room for timer coalescing and loaded CI runners. */
    g_assert_cmpint(elapsed_ns, >=, 1000000LL);
    g_assert_cmpint(elapsed_ns, <, 5000000000LL);
}

static void test_darwin_cond_timedwait(void)
{
    QemuMutex mutex;
    QemuCond cond;
    int64_t start_ns;
    int64_t end_ns;
    bool signaled;

    qemu_mutex_init(&mutex);
    qemu_cond_init(&cond);
    qemu_mutex_lock(&mutex);

    start_ns = monotonic_ns();
    signaled = qemu_cond_timedwait(&cond, &mutex, 20);
    end_ns = monotonic_ns();

    qemu_mutex_unlock(&mutex);
    qemu_cond_destroy(&cond);
    qemu_mutex_destroy(&mutex);

    g_assert_false(signaled);
    assert_timed_wait_elapsed(start_ns, end_ns);
}

static void test_darwin_sem_timedwait(void)
{
    QemuSemaphore sem;
    int64_t start_ns;
    int64_t end_ns;
    int ret;

    qemu_sem_init(&sem, 0);

    start_ns = monotonic_ns();
    ret = qemu_sem_timedwait(&sem, 20);
    end_ns = monotonic_ns();

    qemu_sem_destroy(&sem);

    g_assert_cmpint(ret, ==, -1);
    assert_timed_wait_elapsed(start_ns, end_ns);
}

int main(int argc, char **argv)
{
    g_test_init(&argc, &argv, NULL);
    g_test_add_func("/qemu-thread/darwin/signal-mask",
                    test_darwin_thread_signal_mask);
    g_test_add_func("/qemu-thread/darwin/host-thread-id",
                    test_darwin_host_thread_id);
    g_test_add_func("/qemu-thread/darwin/cond-timedwait",
                    test_darwin_cond_timedwait);
    g_test_add_func("/qemu-thread/darwin/sem-timedwait",
                    test_darwin_sem_timedwait);
    return g_test_run();
}
