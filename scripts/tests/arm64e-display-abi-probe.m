/*
 * ARM64e host ABI probe for QEMU display callback boundaries.
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#import <objc/runtime.h>

#include <Block.h>
#include <dispatch/dispatch.h>
#include <dlfcn.h>
#include <stdio.h>
#include <unistd.h>

#if !defined(__PTRAUTH__)
#error "This probe must be compiled for a pointer-authenticated ABI"
#endif

typedef int (*WHPUnaryFunction)(int);

typedef struct WHPFunctionOps {
    WHPUnaryFunction invoke;
} WHPFunctionOps;

static int whp_add_one(int value)
{
    return value + 1;
}

__attribute__((noinline))
static int whp_call_ops(const WHPFunctionOps *ops, int value)
{
    return ops->invoke(value);
}

typedef int (^WHPUnaryBlock)(int);

__attribute__((noinline))
static int whp_call_block(WHPUnaryBlock block, int value)
{
    return block(value);
}

typedef struct WHPDispatchContext {
    dispatch_semaphore_t done;
    int value;
} WHPDispatchContext;

static void whp_dispatch_callback(void *opaque)
{
    WHPDispatchContext *ctx = opaque;

    ctx->value++;
    dispatch_semaphore_signal(ctx->done);
}

__attribute__((objc_root_class))
@interface WHPDisplayABIProbe
- (int)value;
@end

@implementation WHPDisplayABIProbe

- (int)value
{
    return 7;
}

@end

typedef int (*WHPValueIMP)(id, SEL);

static int whp_replacement_value(id self, SEL selector)
{
    (void)self;
    (void)selector;
    return 9;
}

static int whp_probe_c_function_pointer(void)
{
    static const WHPFunctionOps ops = {
        .invoke = whp_add_one,
    };

    return whp_call_ops(&ops, 41) == 42 ? 0 : 1;
}

static int whp_probe_dlsym(void)
{
    typedef pid_t (*WHPGetPidFunction)(void);
    WHPGetPidFunction dynamic_getpid =
        (WHPGetPidFunction)dlsym(RTLD_DEFAULT, "getpid");

    if (!dynamic_getpid) {
        return 1;
    }
    return dynamic_getpid() == getpid() ? 0 : 1;
}

static int whp_probe_block(void)
{
    WHPUnaryBlock block = Block_copy(^int(int value) {
        return value + 1;
    });
    int result = whp_call_block(block, 41);

    Block_release(block);
    return result == 42 ? 0 : 1;
}

static int whp_probe_dispatch(void)
{
    WHPDispatchContext ctx = {
        .done = dispatch_semaphore_create(0),
        .value = 41,
    };

    dispatch_async_f(dispatch_get_global_queue(DISPATCH_QUEUE_PRIORITY_DEFAULT, 0),
                     &ctx, whp_dispatch_callback);
    if (dispatch_semaphore_wait(ctx.done,
                                dispatch_time(DISPATCH_TIME_NOW,
                                              5 * NSEC_PER_SEC)) != 0) {
        return 1;
    }
    return ctx.value == 42 ? 0 : 1;
}

static int whp_probe_objc_imp(void)
{
    Class cls = objc_getClass("WHPDisplayABIProbe");
    SEL selector = sel_registerName("value");
    Method method;
    const char *types;
    WHPValueIMP original;
    IMP previous;
    id object;

    if (!cls) {
        return 1;
    }

    method = class_getInstanceMethod(cls, selector);
    if (!method) {
        return 1;
    }

    types = method_getTypeEncoding(method);
    original = (WHPValueIMP)method_getImplementation(method);
    if (!original) {
        return 1;
    }

    object = class_createInstance(cls, 0);
    if (!object) {
        return 1;
    }

    if (original(object, selector) != 7 || [object value] != 7) {
        object_dispose(object);
        return 1;
    }

    previous = class_replaceMethod(cls, selector, (IMP)whp_replacement_value,
                                   types);
    if (!previous || [object value] != 9) {
        object_dispose(object);
        return 1;
    }

    class_replaceMethod(cls, selector, previous, types);
    if ([object value] != 7) {
        object_dispose(object);
        return 1;
    }

    object_dispose(object);
    return 0;
}

int main(void)
{
    if (whp_probe_c_function_pointer()) {
        fputs("ARM64e C function-pointer ABI probe failed\n", stderr);
        return 1;
    }
    if (whp_probe_dlsym()) {
        fputs("ARM64e dlsym function-pointer ABI probe failed\n", stderr);
        return 2;
    }
    if (whp_probe_block()) {
        fputs("ARM64e block invocation ABI probe failed\n", stderr);
        return 3;
    }
    if (whp_probe_dispatch()) {
        fputs("ARM64e libdispatch callback ABI probe failed\n", stderr);
        return 4;
    }
    if (whp_probe_objc_imp()) {
        fputs("ARM64e Objective-C IMP ABI probe failed\n", stderr);
        return 5;
    }

    puts("ARM64e display callback ABI probe passed");
    return 0;
}
