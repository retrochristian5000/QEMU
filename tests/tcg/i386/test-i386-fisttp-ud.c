/* FISTTP must #UD on x86 CPUs that do not report SSE3.
 * Run using the 'pentium' model via Makefile.target.
 */
#define _POSIX_C_SOURCE 200809L
#include <setjmp.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>

static sigjmp_buf recovery;
static volatile sig_atomic_t saw_sigill;
static volatile int16_t result16;
static volatile int32_t result32;
static volatile int64_t result64;

static void on_sigill(int sig)
{
    (void)sig;
    saw_sigill = 1;
    siglongjmp(recovery, 1);
}

static void fisttp16(void)
{
    __asm__ volatile("fninit; fld1; fisttps %0" : "=m"(result16) : : "st");
}

static void fisttp32(void)
{
    __asm__ volatile("fninit; fld1; fisttpl %0" : "=m"(result32) : : "st");
}

static void fisttp64(void)
{
    __asm__ volatile("fninit; fld1; fisttpll %0" : "=m"(result64) : : "st");
}

static int expect_sigill(const char *name, void (*fn)(void))
{
    saw_sigill = 0;
    if (sigsetjmp(recovery, 1) == 0) {
        fn();
    }
    if (!saw_sigill) {
        printf("FAIL: %s accepted without SSE3\n", name);
        return 1;
    }
    return 0;
}

int main(void)
{
    struct sigaction sa = {0}, old;
    int ret;

    sa.sa_handler = on_sigill;
    sigemptyset(&sa.sa_mask);
    if (sigaction(SIGILL, &sa, &old) < 0) {
        perror("sigaction");
        return 1;
    }
    ret = expect_sigill("fisttps", fisttp16);
    ret |= expect_sigill("fisttpl", fisttp32);
    ret |= expect_sigill("fisttpll", fisttp64);
    sigaction(SIGILL, &old, NULL);
    return ret;
}
