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
#include <dispatch/dispatch.h>
#include <math.h>

#include "ui/console.h"
#include "ui/cocoa-metal.h"
#include "ui/cocoa-metal-dirty.h"
#include "ui/cocoa-metal-tsan.h"

#define QEMU_METAL_PIXEL_FORMAT_BGRA8_UNORM 80
#define QEMU_METAL_STORAGE_MODE_SHARED 0
#define QEMU_METAL_COMMAND_BUFFER_STATUS_COMPLETED 4

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
- (CGSize)drawableSize;
- (void)setColorspace:(CGColorSpaceRef)colorspace;
- (id)nextDrawable;
- (void)setAllowsNextDrawableTimeout:(BOOL)allow;
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
- (NSUInteger)sampleCount;
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
- (void)addCompletedHandler:(void (^)(id<QEMUMetalCommandBufferRuntime>))handler;
- (NSUInteger)status;
- (void)commit;
@end

@protocol QEMUMetalBlitEncoderRuntime <NSObject>
- (void)copyFromTexture:(id)sourceTexture
            sourceSlice:(NSUInteger)sourceSlice
            sourceLevel:(NSUInteger)sourceLevel
              toTexture:(id)destinationTexture
       destinationSlice:(NSUInteger)destinationSlice
       destinationLevel:(NSUInteger)destinationLevel
             sliceCount:(NSUInteger)sliceCount
             levelCount:(NSUInteger)levelCount;
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
    BOOL hasPresentedFrame;
    BOOL presentationPending;
    /* Main-queue state; one upload texture must not be rewritten in flight. */
    BOOL frameInFlight;
    BOOL redrawDeferred;
    NSRect deferredDirtyRects[8];
    NSUInteger deferredDirtyCount;
    uint64_t surfaceGeneration;
    BOOL drawableRetryUsed;
    BOOL drawableRetryScheduled;
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
    CGColorSpaceRef colorspace;

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

    /* MTLCreateSystemDefaultDevice returns an owned device reference. */
    metalDevice = device;
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
    if ([layer respondsToSelector:@selector(setAllowsNextDrawableTimeout:)]) {
        [layer setAllowsNextDrawableTimeout:YES];
    }

    /* Match the sRGB Pixman/Core Graphics output on wide-gamut displays. */
    colorspace = CGColorSpaceCreateWithName(kCGColorSpaceSRGB);
    if (colorspace) {
        if ([layer respondsToSelector:@selector(setColorspace:)]) {
            [layer setColorspace:colorspace];
        }
        CGColorSpaceRelease(colorspace);
    }

    [metalLayer setOpaque:YES];
    [metalLayer setFrame:[view bounds]];
    [metalLayer setAutoresizingMask:kCALayerWidthSizable |
                                    kCALayerHeightSizable];
    [metalLayer setMagnificationFilter:kCAFilterNearest];
    [metalLayer setMinificationFilter:kCAFilterNearest];
    /*
     * Insert scanout behind QemuCocoaView's brightness overlay, leaving
     * native AppleGFX and Pixman textures intact and the host cursor above.
     */
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
    if ([texture pixelFormat] != QEMU_METAL_PIXEL_FORMAT_BGRA8_UNORM ||
        [texture sampleCount] != 1) {
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
    surfaceGeneration++;
    hasPresentedFrame = NO;
    deferredDirtyCount = 0;
    redrawDeferred = NO;
    presentationPending = YES;
    drawableRetryUsed = NO;
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

    /*
     * Metal performs this copy on the calling CPU thread, but its framework
     * is not built with TSan. Describe only the actual pixel reads.
     */
    qemu_cocoa_metal_tsan_read_rows(bytes, (size_t)dirty.width * 4,
                                  (size_t)stride, (size_t)dirty.height);

    [metalTexture replaceRegion:region
                       mipmapLevel:0
                         withBytes:bytes
                       bytesPerRow:(NSUInteger)stride];
}

/*
 * A failed acquisition can consume the last AppKit dirty notification even
 * when the guest has stopped drawing. Retry once, without a busy loop.
 */
- (void)retryDrawableForView:(NSView *)view
{
    if (drawableRetryUsed || drawableRetryScheduled) {
        return;
    }

    drawableRetryUsed = YES;
    drawableRetryScheduled = YES;
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, 16 * NSEC_PER_MSEC),
                   dispatch_get_main_queue(), ^{
        drawableRetryScheduled = NO;
        NSWindow *window = [view window];

        if (window &&
            ([window occlusionState] & NSWindowOcclusionStateVisible)) {
            [view setNeedsDisplay:YES];
        }
    });
}

/* Keep distant damage separate while the GPU owns the upload texture. */
- (void)deferDirtyRect:(NSRect)rect
{
    if (NSIsEmptyRect(rect)) {
        return;
    }

    for (NSUInteger i = 0; i < deferredDirtyCount;) {
        NSRect old = deferredDirtyRects[i];

        if (NSIntersectsRect(old, rect)) {
            rect = NSUnionRect(old, rect);
            deferredDirtyRects[i] =
                deferredDirtyRects[--deferredDirtyCount];
            i = 0;
        } else {
            i++;
        }
    }

    if (deferredDirtyCount < ARRAY_SIZE(deferredDirtyRects)) {
        deferredDirtyRects[deferredDirtyCount++] = rect;
    } else {
        /*
         * Keep memory and scheduling bounded even for pathological damage.
         * Overflow must cover all pixels; never discard a dirty region.
         */
        deferredDirtyRects[0] = NSUnionRect(deferredDirtyRects[0], rect);
    }
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
    bool uploaded = false;
    QEMUMetalOrigin origin = { 0, 0, 0 };
    QEMUMetalSize size;
    NSSize backing;
    CGSize desiredDrawableSize;
    NSWindow *window = [view window];

    /*
     * nextDrawable can stall AppKit for up to a second if Core Animation
     * cannot release a drawable. Avoid that wait and the Pixman upload when
     * the QEMU window is fully occluded; its next visible update will redraw.
     */
    if (window &&
        !([window occlusionState] & NSWindowOcclusionStateVisible)) {
        textureImage = NULL;
        presentationPending = YES;
        drawableRetryUsed = NO;
        return true;
    }

    /*
     * Do not acquire another drawable or write the shared upload texture
     * while the previous GPU blit is outstanding. Preserve the upload
     * texture and accumulate AppKit's actual damage rectangles instead.
     * Surface changes and failed GPU commands invalidate it separately.
     */
    if (frameInFlight) {
        const NSRect *rectList;
        NSInteger rectCount;

        [view getRectsBeingDrawn:&rectList count:&rectCount];
        if (rectCount > 0) {
            for (NSInteger i = 0; i < rectCount; i++) {
                [self deferDirtyRect:rectList[i]];
            }
        } else {
            [self deferDirtyRect:dirtyRect];
        }
        redrawDeferred = YES;
        presentationPending = YES;
        return true;
    }

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
        if (width <= 0 || height <= 0 || width > INT_MAX / 4 ||
            stride < width * 4) {
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
            uploaded = true;
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
                        uploaded = true;
                    }
                }
            } else {
                QEMUCocoaMetalDirtyRect dirty;

                if (cocoa_metal_dirty_rect_from_nsrect(dirtyRect, width, height,
                                                       &dirty)) {
                    [self uploadImage:image stride:stride dirty:dirty];
                    uploaded = true;
                }
            }
        }
        sourceTexture = metalTexture;
    }

    /*
     * Native producers can modify their texture without a Pixman upload.
     * Never use the upload-based no-damage shortcut for those textures.
     */
    if (nativeTexture || uploaded) {
        presentationPending = YES;
    }

    size = (QEMUMetalSize){ (NSUInteger)width, (NSUInteger)height, 1 };

    /* AppKit points and display pixels differ on Retina and external screens. */
    backing = [view convertSizeToBacking:NSMakeSize(1.0, 1.0)];
    if (isfinite(backing.width) && backing.width > 0.0 &&
        [metalLayer contentsScale] != backing.width) {
        [metalLayer setContentsScale:backing.width];
    }

    /* The guest image is already a texture: let Core Animation scale it. */
    desiredDrawableSize = CGSizeMake(width, height);
    if (!CGSizeEqualToSize([(id<QEMUMetalLayerRuntime>)metalLayer drawableSize],
                           desiredDrawableSize)) {
        [(id<QEMUMetalLayerRuntime>)metalLayer
            setDrawableSize:desiredDrawableSize];
        presentationPending = YES;
    }

    if (!presentationPending && hasPresentedFrame &&
        ![metalLayer isHidden]) {
        return true;
    }

    /* Prepare the command buffer before obtaining the scarce drawable. */
    commandBuffer = [metalQueue commandBuffer];
    if (!commandBuffer ||
        ![commandBuffer respondsToSelector:@selector(addCompletedHandler:)] ||
        ![commandBuffer respondsToSelector:@selector(status)]) {
        [metalLayer setHidden:YES];
        return false;
    }

    drawable = [(id<QEMUMetalLayerRuntime>)metalLayer nextDrawable];
    if (!drawable) {
        [self retryDrawableForView:view];
        /*
         * Drawable exhaustion is transient, not a reason to replace the
         * last Metal frame with an expensive Core Graphics fallback.
         * Retain that frame when one has already been presented.
         */
        if (hasPresentedFrame && ![metalLayer isHidden]) {
            return true;
        }
        [metalLayer setHidden:YES];
        return false;
    }

    drawableTexture = [drawable texture];
    /* A backing-store transition must never create an out-of-bounds blit. */
    if (!drawableTexture ||
        [drawableTexture width] != (NSUInteger)width ||
        [drawableTexture height] != (NSUInteger)height ||
        [drawableTexture pixelFormat] != QEMU_METAL_PIXEL_FORMAT_BGRA8_UNORM ||
        [drawableTexture sampleCount] != 1) {
        [metalLayer setHidden:YES];
        return false;
    }

    encoder = [commandBuffer blitCommandEncoder];
    if (!encoder) {
        [metalLayer setHidden:YES];
        return false;
    }

    /*
     * A newly acquired drawable has no guaranteed previous-frame content.
     * Copy the entire base level, not just this frame's dirty rectangles.
     * Prefer the whole-slice API when available, with the region API as
     * the compatibility path. Both copy exactly one slice and mip level.
     */
    if ([encoder respondsToSelector:
            @selector(copyFromTexture:sourceSlice:sourceLevel:toTexture:
                      destinationSlice:destinationLevel:sliceCount:levelCount:)]) {
        [encoder copyFromTexture:sourceTexture
                        sourceSlice:0
                        sourceLevel:0
                          toTexture:drawableTexture
                   destinationSlice:0
                   destinationLevel:0
                         sliceCount:1
                         levelCount:1];
    } else {
        [encoder copyFromTexture:sourceTexture
                        sourceSlice:0
                        sourceLevel:0
                       sourceOrigin:origin
                         sourceSize:size
                          toTexture:drawableTexture
                   destinationSlice:0
                   destinationLevel:0
                  destinationOrigin:origin];
    }
    [encoder endEncoding];
    [commandBuffer presentDrawable:drawable];
    frameInFlight = YES;
    presentationPending = NO;
    uint64_t submittedGeneration = surfaceGeneration;
    [commandBuffer addCompletedHandler:^(id<QEMUMetalCommandBufferRuntime> completed) {
        /*
         * Metal calls this on a worker thread. Do not touch AppKit or
         * presentation state until back on the main queue. The copied
         * blocks keep the view and state alive through completion.
         */
        /* MTLCommandBufferStatusCompleted is 4 in the Metal ABI. */
        BOOL succeeded = [completed status] ==
                         QEMU_METAL_COMMAND_BUFFER_STATUS_COMPLETED;
        dispatch_async(dispatch_get_main_queue(), ^{
            frameInFlight = NO;
            /*
             * A completed old-mode frame cannot establish presentation
             * validity for the new surface. Its GPU ownership has ended,
             * but only a new full redraw can present the current mode.
             */
            if (submittedGeneration != surfaceGeneration) {
                deferredDirtyCount = 0;
                redrawDeferred = NO;
                [view setNeedsDisplay:YES];
                return;
            }
            if (succeeded) {
                hasPresentedFrame = YES;
                drawableRetryUsed = NO;
            } else {
                hasPresentedFrame = NO;
                presentationPending = YES;
                textureImage = NULL;
                [self retryDrawableForView:view];
            }
            if (redrawDeferred) {
                NSUInteger count = deferredDirtyCount;

                redrawDeferred = NO;
                deferredDirtyCount = 0;
                /*
                 * A surface switch, occlusion or failed command can
                 * invalidate the upload texture independently. Keep the
                 * full-redraw path for those cases, but otherwise upload
                 * only the damage accumulated while the GPU was busy.
                 */
                if (!succeeded || (!nativeTexture && !textureImage) ||
                    !count) {
                    [view setNeedsDisplay:YES];
                } else {
                    for (NSUInteger i = 0; i < count; i++) {
                        [view setNeedsDisplayInRect:deferredDirtyRects[i]];
                    }
                }
            }
        });
    }];
    [commandBuffer commit];

    if ([metalLayer isHidden]) {
        [metalLayer setHidden:NO];
    }
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
    /*
     * CAMetalDrawable is autoreleased. Release each frame's drawable before
     * the next AppKit redraw instead of retaining it until the run-loop pool
     * drains; the CAMetalLayer drawable pool is deliberately small.
     */
    @autoreleasepool {
        QEMUCocoaMetalState *state =
            objc_getAssociatedObject(self, &metal_state_key);

        if (state && [state drawView:self dirtyRect:rect]) {
            return;
        }

        cocoa_draw_imp(self, selector, rect);
    }
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
