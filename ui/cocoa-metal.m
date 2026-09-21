/*
 * Optional Metal acceleration for the QEMU Cocoa display
 *
 * This file deliberately uses runtime lookup rather than a hard Metal
 * framework dependency.  Macs without Metal keep using cocoa.m unchanged.
 */

#include "qemu/osdep.h"

#import <Cocoa/Cocoa.h>
#import <QuartzCore/QuartzCore.h>
#import <objc/runtime.h>
#include <dlfcn.h>
#include <math.h>

#include "ui/console.h"
#include "ui/cocoa-metal.h"
#include "ui/cocoa-metal-dirty.h"

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

typedef struct CocoaConsole CocoaConsole;

@protocol QEMUMetalLayerRuntime <NSObject>
+ (id)layer;
- (void)setDevice:(id)device;
- (void)setPixelFormat:(NSUInteger)pixelFormat;
- (void)setFramebufferOnly:(BOOL)framebufferOnly;
- (void)setDrawableSize:(CGSize)size;
- (id)nextDrawable;
@end

@protocol QEMUMetalDeviceRuntime <NSObject>
- (id)newCommandQueue;
- (id)newTextureWithDescriptor:(id)descriptor;
@end

@protocol QEMUMetalTextureRuntime <NSObject>
- (id)device;
- (NSUInteger)width;
- (NSUInteger)height;
- (NSUInteger)pixelFormat;
- (void)replaceRegion:(QEMUMetalRegion)region
          mipmapLevel:(NSUInteger)level
            withBytes:(const void *)bytes
          bytesPerRow:(NSUInteger)bytesPerRow;
@end

@protocol QEMUMetalTextureDescriptorRuntime <NSObject>
+ (id)texture2DDescriptorWithPixelFormat:(NSUInteger)pixelFormat
                                   width:(NSUInteger)width
                                  height:(NSUInteger)height
                               mipmapped:(BOOL)mipmapped;
- (void)setStorageMode:(NSUInteger)storageMode;
@end

@protocol QEMUMetalDrawableRuntime <NSObject>
- (id)texture;
@end

@protocol QEMUMetalCommandQueueRuntime <NSObject>
- (id)commandBuffer;
@end

@protocol QEMUMetalCommandBufferRuntime <NSObject>
- (id)blitCommandEncoder;
- (void)presentDrawable:(id)drawable;
- (void)commit;
@end

@protocol QEMUMetalBlitEncoderRuntime <NSObject>
- (void)copyFromTexture:(id)sourceTexture
            sourceSlice:(NSUInteger)sourceSlice
            sourceLevel:(NSUInteger)sourceLevel
           sourceOrigin:(QEMUMetalOrigin)sourceOrigin
             sourceSize:(QEMUMetalSize)sourceSize
              toTexture:(id)destinationTexture
       destinationSlice:(NSUInteger)destinationSlice
       destinationLevel:(NSUInteger)destinationLevel
      destinationOrigin:(QEMUMetalOrigin)destinationOrigin;
- (void)endEncoding;
@end

typedef id (*QEMUMetalCreateSystemDefaultDevice)(void);
typedef id (*QEMUCocoaInitIMP)(id, SEL, NSRect, CocoaConsole *);
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

    /*
     * On arm64e, dyld returns code symbols from dlsym() already signed with
     * the default C function-pointer schema.  Keep the value typed and let
     * Clang preserve that authentication when storing and calling it.
     */
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

static bool cocoa_metal_dirty_rect_from_nsrect(
    NSRect rect, int width, int height, QEMUCocoaMetalDirtyRect *dirty)
{
    int x0 = (int)floor(NSMinX(rect));
    int y0 = (int)floor(NSMinY(rect));
    int x1 = (int)ceil(NSMaxX(rect));
    int y1 = (int)ceil(NSMaxY(rect));

    return qemu_cocoa_metal_dirty_rect(width, height,
                                       x0, y0, x1, y1, dirty);
}

@interface QEMUCocoaMetalState : NSObject
{
    CALayer *metalLayer;
    id<QEMUMetalDeviceRuntime> metalDevice;
    id<QEMUMetalCommandQueueRuntime> metalQueue;
    id<QEMUMetalTextureRuntime> metalTexture;
    id<QEMUMetalTextureRuntime> nativeTexture;
    NSUInteger nativeTextureWidth;
    NSUInteger nativeTextureHeight;
    Ivar pixmanImageIvar;
    pixman_image_t *textureImage;
    int textureWidth;
    int textureHeight;
}
- (id)initWithView:(NSView *)view;
- (bool)canUseNativeTexture:(id<QEMUMetalTextureRuntime>)texture
                      width:(uint32_t)width
                     height:(uint32_t)height;
- (void)setNativeTexture:(id<QEMUMetalTextureRuntime>)texture
                   width:(uint32_t)width
                  height:(uint32_t)height;
- (void)clearNativeTexture;
- (bool)drawView:(NSView *)view dirtyRect:(NSRect)dirtyRect;
@end

@implementation QEMUCocoaMetalState

- (id)initWithView:(NSView *)view
{
    Class<QEMUMetalLayerRuntime> layerClass;
    id<QEMUMetalLayerRuntime> layer;
    id<QEMUMetalDeviceRuntime> device;

    self = [super init];
    if (!self) {
        return nil;
    }

    pixmanImageIvar = class_getInstanceVariable([view class], "pixman_image");
    if (!pixmanImageIvar || !cocoa_metal_load()) {
        [self release];
        return nil;
    }

    layerClass = (Class<QEMUMetalLayerRuntime>)
        NSClassFromString(@"CAMetalLayer");
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
    metalQueue = [metalDevice newCommandQueue];
    if (!metalQueue) {
        [self release];
        return nil;
    }

    layer = [layerClass layer];
    if (!layer) {
        [self release];
        return nil;
    }

    metalLayer = [(CALayer *)layer retain];
    [layer setDevice:metalDevice];
    [layer setPixelFormat:QEMU_METAL_PIXEL_FORMAT_BGRA8_UNORM];
    [layer setFramebufferOnly:NO];

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
    [nativeTexture release];
    [metalTexture release];
    [metalLayer release];
    [metalQueue release];
    [metalDevice release];
    [super dealloc];
}

- (bool)canUseNativeTexture:(id<QEMUMetalTextureRuntime>)texture
                      width:(uint32_t)width
                     height:(uint32_t)height
{
    if (!texture || [texture device] != metalDevice) {
        return false;
    }
    if ([texture pixelFormat] != QEMU_METAL_PIXEL_FORMAT_BGRA8_UNORM) {
        return false;
    }
    return [texture width] == width && [texture height] == height;
}

- (void)setNativeTexture:(id<QEMUMetalTextureRuntime>)texture
                   width:(uint32_t)width
                  height:(uint32_t)height
{
    if (![self canUseNativeTexture:texture width:width height:height]) {
        [self clearNativeTexture];
        return;
    }

    if (nativeTexture != texture) {
        [texture retain];
        [nativeTexture release];
        nativeTexture = texture;
    }
    nativeTextureWidth = width;
    nativeTextureHeight = height;

    /*
     * The upload texture is now stale while AppleGFX is drawing directly into
     * nativeTexture.  Force one complete Pixman upload if we later fall back.
     */
    textureImage = NULL;
}

- (void)clearNativeTexture
{
    [nativeTexture release];
    nativeTexture = nil;
    nativeTextureWidth = 0;
    nativeTextureHeight = 0;
    textureImage = NULL;
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

- (void)uploadImage:(pixman_image_t *)image
             stride:(int)stride
              dirty:(QEMUCocoaMetalDirtyRect)dirty
{
    QEMUMetalOrigin origin = {
        (NSUInteger)dirty.x,
        (NSUInteger)dirty.y,
        0,
    };
    QEMUMetalSize size = {
        (NSUInteger)dirty.width,
        (NSUInteger)dirty.height,
        1,
    };
    QEMUMetalRegion region = { origin, size };
    const uint8_t *bytes = (const uint8_t *)pixman_image_get_data(image) +
                           (size_t)dirty.y * stride +
                           (size_t)dirty.x * 4;

    [metalTexture replaceRegion:region
                       mipmapLevel:0
                         withBytes:bytes
                       bytesPerRow:(NSUInteger)stride];
}

- (bool)drawView:(NSView *)view dirtyRect:(NSRect)dirtyRect
{
    Class<QEMUMetalTextureDescriptorRuntime> descriptorClass;
    id<QEMUMetalTextureDescriptorRuntime> descriptor;
    id<QEMUMetalDrawableRuntime> drawable;
    id<QEMUMetalTextureRuntime> drawableTexture;
    id<QEMUMetalTextureRuntime> sourceTexture;
    id<QEMUMetalCommandBufferRuntime> commandBuffer;
    id<QEMUMetalBlitEncoderRuntime> encoder;
    pixman_image_t *image = NULL;
    pixman_format_code_t format;
    int width;
    int height;
    int stride = 0;
    bool fullUpload = false;
    QEMUMetalOrigin origin = { 0, 0, 0 };
    QEMUMetalSize size;

    if (nativeTexture) {
        width = (int)nativeTextureWidth;
        height = (int)nativeTextureHeight;
        sourceTexture = nativeTexture;
    } else {
        image = [self pixmanImageForView:view];
        if (!image) {
            textureImage = NULL;
            [metalLayer setHidden:YES];
            return false;
        }

        format = pixman_image_get_format(image);
        if (format != PIXMAN_x8r8g8b8 && format != PIXMAN_a8r8g8b8) {
            textureImage = NULL;
            [metalLayer setHidden:YES];
            return false;
        }

        width = pixman_image_get_width(image);
        height = pixman_image_get_height(image);
        stride = pixman_image_get_stride(image);
        if (width <= 0 || height <= 0 || stride < width * 4) {
            textureImage = NULL;
            [metalLayer setHidden:YES];
            return false;
        }
    }

    if (!nativeTexture &&
        (!metalTexture || textureWidth != width || textureHeight != height)) {
        descriptorClass = (Class<QEMUMetalTextureDescriptorRuntime>)
            NSClassFromString(@"MTLTextureDescriptor");
        if (!descriptorClass) {
            [metalLayer setHidden:YES];
            return false;
        }

        descriptor =
            [descriptorClass
                texture2DDescriptorWithPixelFormat:
                    QEMU_METAL_PIXEL_FORMAT_BGRA8_UNORM
                                           width:(NSUInteger)width
                                          height:(NSUInteger)height
                                       mipmapped:NO];
        if (!descriptor) {
            [metalLayer setHidden:YES];
            return false;
        }

        [descriptor setStorageMode:QEMU_METAL_STORAGE_MODE_SHARED];

        [metalTexture release];
        metalTexture = [metalDevice newTextureWithDescriptor:descriptor];
        if (!metalTexture) {
            textureImage = NULL;
            textureWidth = 0;
            textureHeight = 0;
            [metalLayer setHidden:YES];
            return false;
        }
        textureWidth = width;
        textureHeight = height;
        fullUpload = true;
    }

    if (!nativeTexture) {
        if (textureImage != image) {
            textureImage = image;
            fullUpload = true;
        }

        if (fullUpload) {
            QEMUCocoaMetalDirtyRect full = { 0, 0, width, height };
            [self uploadImage:image stride:stride dirty:full];
        } else {
            const NSRect *rectList;
            NSInteger rectCount;

            [view getRectsBeingDrawn:&rectList count:&rectCount];
            if (rectCount > 0) {
                for (NSInteger i = 0; i < rectCount; i++) {
                    QEMUCocoaMetalDirtyRect dirty;

                    if (cocoa_metal_dirty_rect_from_nsrect(rectList[i], width,
                                                           height, &dirty)) {
                        [self uploadImage:image stride:stride dirty:dirty];
                    }
                }
            } else {
                QEMUCocoaMetalDirtyRect dirty;

                if (cocoa_metal_dirty_rect_from_nsrect(dirtyRect, width, height,
                                                       &dirty)) {
                    [self uploadImage:image stride:stride dirty:dirty];
                }
            }
        }
        sourceTexture = metalTexture;
    }

    size = (QEMUMetalSize){ (NSUInteger)width, (NSUInteger)height, 1 };

    [(id<QEMUMetalLayerRuntime>)metalLayer
        setDrawableSize:CGSizeMake(width, height)];

    drawable = [(id<QEMUMetalLayerRuntime>)metalLayer nextDrawable];
    if (!drawable) {
        [metalLayer setHidden:YES];
        return false;
    }

    drawableTexture = [drawable texture];
    commandBuffer = [metalQueue commandBuffer];
    if (!drawableTexture || !commandBuffer) {
        [metalLayer setHidden:YES];
        return false;
    }

    encoder = [commandBuffer blitCommandEncoder];
    if (!encoder) {
        [metalLayer setHidden:YES];
        return false;
    }

    [encoder copyFromTexture:sourceTexture
                    sourceSlice:0
                    sourceLevel:0
                   sourceOrigin:origin
                     sourceSize:size
                      toTexture:drawableTexture
               destinationSlice:0
               destinationLevel:0
              destinationOrigin:origin];
    [encoder endEncoding];
    [commandBuffer presentDrawable:drawable];
    [commandBuffer commit];

    [metalLayer setHidden:NO];
    return true;
}

@end

bool qemu_cocoa_metal_can_use_texture(void *opaque_view, void *opaque_texture,
                                      uint32_t width, uint32_t height)
{
    NSView *view = (NSView *)opaque_view;
    QEMUCocoaMetalState *state =
        objc_getAssociatedObject(view, &metal_state_key);

    return state &&
        [state canUseNativeTexture:(id<QEMUMetalTextureRuntime>)opaque_texture
                            width:width
                           height:height];
}

void qemu_cocoa_metal_set_texture(void *opaque_view, void *opaque_texture,
                                  uint32_t width, uint32_t height)
{
    NSView *view = (NSView *)opaque_view;
    QEMUCocoaMetalState *state =
        objc_getAssociatedObject(view, &metal_state_key);

    if (state) {
        [state setNativeTexture:(id<QEMUMetalTextureRuntime>)opaque_texture
                          width:width
                         height:height];
    }
}

void qemu_cocoa_metal_clear_texture(void *opaque_view)
{
    NSView *view = (NSView *)opaque_view;
    QEMUCocoaMetalState *state =
        objc_getAssociatedObject(view, &metal_state_key);

    if (state) {
        [state clearNativeTexture];
    }
}

static id cocoa_metal_init(id self, SEL selector, NSRect frame,
                           CocoaConsole *console)
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

    if (state && [state drawView:self dirtyRect:rect]) {
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
