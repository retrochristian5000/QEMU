/*
 * Optional Metal acceleration for the QEMU Cocoa display
 *
 * This file deliberately uses runtime lookup rather than a hard Metal
 * framework dependency.  Macs without Metal keep using cocoa.m unchanged.
 */

#include "qemu/osdep.h"

#import <Cocoa/Cocoa.h>
#import <QuartzCore/QuartzCore.h>
#import <objc/message.h>
#import <objc/runtime.h>
#include <dlfcn.h>

#define QEMU_METAL_PIXEL_FORMAT_BGRA8_UNORM 80
#define QEMU_METAL_STORAGE_MODE_SHARED 0

typedef struct QEMUMetalOrigin {
    NSUInteger x;
    NSUInteger y;
    NSUInteger z;
} QEMUMetalOrigin;

typedef struct QEMUMetalSize {
    NSUInteger width;
    NSUInteger height;
    NSUInteger depth;
} QEMUMetalSize;

typedef struct QEMUMetalRegion {
    QEMUMetalOrigin origin;
    QEMUMetalSize size;
} QEMUMetalRegion;

typedef id (*QEMUMetalCreateSystemDefaultDevice)(void);
typedef id (*QEMUCocoaInitIMP)(id, SEL, NSRect, void *);
typedef void (*QEMUCocoaDrawIMP)(id, SEL, NSRect);

static void *metal_handle;
static QEMUMetalCreateSystemDefaultDevice metal_create_default_device;
static QEMUCocoaInitIMP cocoa_init_imp;
static QEMUCocoaDrawIMP cocoa_draw_imp;
static char metal_state_key;

static bool cocoa_metal_load(void)
{
    if (metal_create_default_device) {
        return true;
    }

    if (!metal_handle) {
        metal_handle = dlopen("/System/Library/Frameworks/Metal.framework/Metal",
                             RTLD_LAZY | RTLD_LOCAL);
    }
    if (!metal_handle) {
        return false;
    }

    metal_create_default_device =
        (QEMUMetalCreateSystemDefaultDevice)dlsym(
            metal_handle, "MTLCreateSystemDefaultDevice");
    if (!metal_create_default_device) {
        dlclose(metal_handle);
        metal_handle = NULL;
        return false;
    }

    return true;
}

static id cocoa_msg_id(id object, const char *selector)
{
    return ((id (*)(id, SEL))objc_msgSend)(object, sel_registerName(selector));
}

@interface QEMUCocoaMetalState : NSObject
{
    CALayer *metalLayer;
    id metalDevice;
    id metalQueue;
    id metalTexture;
    Ivar pixmanImageIvar;
    int textureWidth;
    int textureHeight;
}
- (id)initWithView:(NSView *)view;
- (bool)drawView:(NSView *)view;
@end

@implementation QEMUCocoaMetalState

- (id)initWithView:(NSView *)view
{
    Class layerClass;
    id layer;
    id device;

    self = [super init];
    if (!self) {
        return nil;
    }

    pixmanImageIvar = class_getInstanceVariable([view class], "pixman_image");
    if (!pixmanImageIvar || !cocoa_metal_load()) {
        [self release];
        return nil;
    }

    layerClass = NSClassFromString(@"CAMetalLayer");
    if (!layerClass) {
        [self release];
        return nil;
    }

    device = metal_create_default_device();
    if (!device) {
        [self release];
        return nil;
    }

    metalDevice = [device retain];
    metalQueue = cocoa_msg_id(metalDevice, "newCommandQueue");
    if (!metalQueue) {
        [self release];
        return nil;
    }

    layer = cocoa_msg_id((id)layerClass, "layer");
    if (!layer) {
        [self release];
        return nil;
    }

    metalLayer = [(CALayer *)layer retain];
    ((void (*)(id, SEL, id))objc_msgSend)(
        layer, sel_registerName("setDevice:"), metalDevice);
    ((void (*)(id, SEL, NSUInteger))objc_msgSend)(
        layer, sel_registerName("setPixelFormat:"),
        QEMU_METAL_PIXEL_FORMAT_BGRA8_UNORM);
    ((void (*)(id, SEL, BOOL))objc_msgSend)(
        layer, sel_registerName("setFramebufferOnly:"), NO);

    [metalLayer setOpaque:YES];
    [metalLayer setFrame:[view bounds]];
    [metalLayer setAutoresizingMask:kCALayerWidthSizable |
                                    kCALayerHeightSizable];
    [metalLayer setMagnificationFilter:kCAFilterNearest];
    [metalLayer setMinificationFilter:kCAFilterNearest];
    [[view layer] insertSublayer:metalLayer atIndex:0];

    return self;
}

- (void)dealloc
{
    [metalTexture release];
    [metalLayer release];
    [metalQueue release];
    [metalDevice release];
    [super dealloc];
}

- (pixman_image_t *)pixmanImageForView:(NSView *)view
{
    ptrdiff_t offset;

    if (!pixmanImageIvar) {
        return NULL;
    }

    offset = ivar_getOffset(pixmanImageIvar);
    return *(pixman_image_t **)((uint8_t *)(void *)view + offset);
}

- (bool)drawView:(NSView *)view
{
    Class descriptorClass;
    id descriptor;
    id drawable;
    id drawableTexture;
    id commandBuffer;
    id encoder;
    pixman_image_t *image = [self pixmanImageForView:view];
    pixman_format_code_t format;
    int width;
    int height;
    int stride;
    QEMUMetalOrigin origin = { 0, 0, 0 };
    QEMUMetalSize size;
    QEMUMetalRegion region;

    if (!image) {
        [metalLayer setHidden:YES];
        return false;
    }

    format = pixman_image_get_format(image);
    if (format != PIXMAN_x8r8g8b8 && format != PIXMAN_a8r8g8b8) {
        [metalLayer setHidden:YES];
        return false;
    }

    width = pixman_image_get_width(image);
    height = pixman_image_get_height(image);
    stride = pixman_image_get_stride(image);
    if (width <= 0 || height <= 0 || stride < width * 4) {
        [metalLayer setHidden:YES];
        return false;
    }

    if (!metalTexture || textureWidth != width || textureHeight != height) {
        descriptorClass = NSClassFromString(@"MTLTextureDescriptor");
        if (!descriptorClass) {
            [metalLayer setHidden:YES];
            return false;
        }

        descriptor =
            ((id (*)(id, SEL, NSUInteger, NSUInteger, NSUInteger, BOOL))
             objc_msgSend)(
                (id)descriptorClass,
                sel_registerName(
                    "texture2DDescriptorWithPixelFormat:width:height:mipmapped:"),
                QEMU_METAL_PIXEL_FORMAT_BGRA8_UNORM,
                (NSUInteger)width, (NSUInteger)height, NO);
        if (!descriptor) {
            [metalLayer setHidden:YES];
            return false;
        }

        ((void (*)(id, SEL, NSUInteger))objc_msgSend)(
            descriptor, sel_registerName("setStorageMode:"),
            QEMU_METAL_STORAGE_MODE_SHARED);

        [metalTexture release];
        metalTexture = ((id (*)(id, SEL, id))objc_msgSend)(
            metalDevice, sel_registerName("newTextureWithDescriptor:"),
            descriptor);
        if (!metalTexture) {
            textureWidth = 0;
            textureHeight = 0;
            [metalLayer setHidden:YES];
            return false;
        }
        textureWidth = width;
        textureHeight = height;
    }

    size = (QEMUMetalSize){ (NSUInteger)width, (NSUInteger)height, 1 };
    region = (QEMUMetalRegion){ origin, size };
    ((void (*)(id, SEL, QEMUMetalRegion, NSUInteger, const void *, NSUInteger))
     objc_msgSend)(
        metalTexture,
        sel_registerName("replaceRegion:mipmapLevel:withBytes:bytesPerRow:"),
        region, 0, pixman_image_get_data(image), (NSUInteger)stride);

    ((void (*)(id, SEL, CGSize))objc_msgSend)(
        (id)metalLayer, sel_registerName("setDrawableSize:"),
        CGSizeMake(width, height));

    drawable = cocoa_msg_id((id)metalLayer, "nextDrawable");
    if (!drawable) {
        [metalLayer setHidden:YES];
        return false;
    }

    drawableTexture = cocoa_msg_id(drawable, "texture");
    commandBuffer = cocoa_msg_id(metalQueue, "commandBuffer");
    if (!drawableTexture || !commandBuffer) {
        [metalLayer setHidden:YES];
        return false;
    }

    encoder = cocoa_msg_id(commandBuffer, "blitCommandEncoder");
    if (!encoder) {
        [metalLayer setHidden:YES];
        return false;
    }

    ((void (*)(id, SEL, id, NSUInteger, NSUInteger,
               QEMUMetalOrigin, QEMUMetalSize, id, NSUInteger, NSUInteger,
               QEMUMetalOrigin))objc_msgSend)(
        encoder,
        sel_registerName(
            "copyFromTexture:sourceSlice:sourceLevel:sourceOrigin:sourceSize:toTexture:destinationSlice:destinationLevel:destinationOrigin:"),
        metalTexture, 0, 0, origin, size,
        drawableTexture, 0, 0, origin);
    ((void (*)(id, SEL))objc_msgSend)(
        encoder, sel_registerName("endEncoding"));
    ((void (*)(id, SEL, id))objc_msgSend)(
        commandBuffer, sel_registerName("presentDrawable:"), drawable);
    ((void (*)(id, SEL))objc_msgSend)(
        commandBuffer, sel_registerName("commit"));

    [metalLayer setHidden:NO];
    return true;
}

@end

static id cocoa_metal_init(id self, SEL selector, NSRect frame, void *console)
{
    id view;
    QEMUCocoaMetalState *state;

    view = cocoa_init_imp(self, selector, frame, console);
    if (!view) {
        return nil;
    }

    state = [[QEMUCocoaMetalState alloc] initWithView:view];
    if (state) {
        objc_setAssociatedObject(view, &metal_state_key, state,
                                 OBJC_ASSOCIATION_RETAIN_NONATOMIC);
        [state release];
    }

    return view;
}

static void cocoa_metal_draw(id self, SEL selector, NSRect rect)
{
    QEMUCocoaMetalState *state =
        objc_getAssociatedObject(self, &metal_state_key);

    if (state && [state drawView:self]) {
        return;
    }

    cocoa_draw_imp(self, selector, rect);
}

@interface QEMUCocoaMetalInstaller : NSObject
@end

@implementation QEMUCocoaMetalInstaller

+ (void)load
{
    Class viewClass = NSClassFromString(@"QemuCocoaView");
    SEL initSelector = sel_registerName("initWithFrame:console:");
    SEL drawSelector = @selector(drawRect:);
    Method initMethod;
    Method drawMethod;

    if (!viewClass) {
        return;
    }

    initMethod = class_getInstanceMethod(viewClass, initSelector);
    drawMethod = class_getInstanceMethod(viewClass, drawSelector);
    if (!initMethod || !drawMethod) {
        return;
    }

    cocoa_init_imp = (QEMUCocoaInitIMP)method_getImplementation(initMethod);
    cocoa_draw_imp = (QEMUCocoaDrawIMP)method_getImplementation(drawMethod);

    class_replaceMethod(viewClass, initSelector, (IMP)cocoa_metal_init,
                        method_getTypeEncoding(initMethod));
    class_replaceMethod(viewClass, drawSelector, (IMP)cocoa_metal_draw,
                        method_getTypeEncoding(drawMethod));
}

@end
