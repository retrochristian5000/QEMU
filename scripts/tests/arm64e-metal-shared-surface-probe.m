/*
 * ARM64e Metal shared-surface probe for the QEMU AppleGFX path.
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#import <Foundation/Foundation.h>
#import <Metal/Metal.h>

#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#if !defined(__PTRAUTH__)
#error "This probe must be compiled for a pointer-authenticated ABI"
#endif

enum {
    PROBE_WIDTH = 64,
    PROBE_HEIGHT = 64,
    PROBE_BPP = 4,
};

static NSUInteger align_up(NSUInteger value, NSUInteger alignment)
{
    return ((value + alignment - 1) / alignment) * alignment;
}

static void write_pattern(uint8_t *bytes, NSUInteger stride)
{
    for (NSUInteger y = 0; y < PROBE_HEIGHT; y++) {
        for (NSUInteger x = 0; x < PROBE_WIDTH; x++) {
            uint8_t *pixel = bytes + y * stride + x * PROBE_BPP;

            pixel[0] = (uint8_t)x;
            pixel[1] = (uint8_t)y;
            pixel[2] = (uint8_t)(x ^ y);
            pixel[3] = 0xff;
        }
    }
}

static bool check_pattern(const uint8_t *bytes, NSUInteger stride)
{
    for (NSUInteger y = 0; y < PROBE_HEIGHT; y++) {
        for (NSUInteger x = 0; x < PROBE_WIDTH; x++) {
            const uint8_t *pixel = bytes + y * stride + x * PROBE_BPP;

            if (pixel[0] != (uint8_t)x ||
                pixel[1] != (uint8_t)y ||
                pixel[2] != (uint8_t)(x ^ y) ||
                pixel[3] != 0xff) {
                return false;
            }
        }
    }
    return true;
}

static bool blit(id<MTLCommandQueue> queue,
                 id<MTLTexture> source,
                 id<MTLTexture> destination)
{
    id<MTLCommandBuffer> command_buffer = [queue commandBuffer];
    id<MTLBlitCommandEncoder> encoder = [command_buffer blitCommandEncoder];
    MTLOrigin origin = MTLOriginMake(0, 0, 0);
    MTLSize size = MTLSizeMake(PROBE_WIDTH, PROBE_HEIGHT, 1);

    if (!command_buffer || !encoder) {
        return false;
    }

    [encoder copyFromTexture:source
                 sourceSlice:0
                 sourceLevel:0
                sourceOrigin:origin
                  sourceSize:size
                   toTexture:destination
            destinationSlice:0
            destinationLevel:0
           destinationOrigin:origin];
    [encoder endEncoding];
    [command_buffer commit];
    [command_buffer waitUntilCompleted];

    return command_buffer.status == MTLCommandBufferStatusCompleted;
}

int main(void)
{
    @autoreleasepool {
        id<MTLDevice> device = MTLCreateSystemDefaultDevice();
        id<MTLCommandQueue> queue;
        id<MTLBuffer> buffer;
        id<MTLTexture> linear_texture;
        id<MTLTexture> destination;
        MTLTextureDescriptor *descriptor;
        NSUInteger alignment;
        NSUInteger stride;
        NSUInteger length;
        uint8_t destination_bytes[PROBE_WIDTH * PROBE_HEIGHT * PROBE_BPP];

        if (!device || !device.hasUnifiedMemory ||
            ![device supportsFamily:MTLGPUFamilyApple1]) {
            fputs("ARM64e Metal probe requires an Apple unified-memory GPU\n",
                  stderr);
            return 1;
        }

        alignment = [device
            minimumLinearTextureAlignmentForPixelFormat:MTLPixelFormatBGRA8Unorm];
        if (!alignment) {
            fputs("Metal returned zero linear-texture alignment\n", stderr);
            return 2;
        }

        stride = align_up(PROBE_WIDTH * PROBE_BPP, alignment);
        length = stride * PROBE_HEIGHT;

        buffer = [device newBufferWithLength:length
                                     options:MTLResourceStorageModeShared];
        if (!buffer) {
            fputs("failed to allocate shared Metal buffer\n", stderr);
            return 3;
        }

        descriptor =
            [MTLTextureDescriptor
                texture2DDescriptorWithPixelFormat:MTLPixelFormatBGRA8Unorm
                                             width:PROBE_WIDTH
                                            height:PROBE_HEIGHT
                                         mipmapped:NO];
        descriptor.storageMode = MTLStorageModeShared;
        descriptor.usage = MTLTextureUsageShaderRead | MTLTextureUsageRenderTarget;

        linear_texture = [buffer newTextureWithDescriptor:descriptor
                                                   offset:0
                                              bytesPerRow:stride];
        destination = [device newTextureWithDescriptor:descriptor];
        queue = [device newCommandQueue];

        if (!linear_texture || !destination || !queue) {
            fputs("failed to create Metal probe resources\n", stderr);
            [queue release];
            [destination release];
            [linear_texture release];
            [buffer release];
            return 4;
        }

        write_pattern(buffer.contents, stride);

        if (!blit(queue, linear_texture, destination)) {
            fputs("linear-texture to texture blit failed\n", stderr);
            return 5;
        }

        memset(destination_bytes, 0, sizeof(destination_bytes));
        [destination getBytes:destination_bytes
                  bytesPerRow:PROBE_WIDTH * PROBE_BPP
                    fromRegion:MTLRegionMake2D(0, 0, PROBE_WIDTH, PROBE_HEIGHT)
                   mipmapLevel:0];
        if (!check_pattern(destination_bytes, PROBE_WIDTH * PROBE_BPP)) {
            fputs("CPU-to-buffer-to-GPU coherence check failed\n", stderr);
            return 6;
        }

        memset(buffer.contents, 0, length);
        if (!blit(queue, destination, linear_texture)) {
            fputs("texture to linear-texture blit failed\n", stderr);
            return 7;
        }
        if (!check_pattern(buffer.contents, stride)) {
            fputs("GPU-to-buffer-to-CPU coherence check failed\n", stderr);
            return 8;
        }

        [queue release];
        [destination release];
        [linear_texture release];
        [buffer release];

        printf("ARM64e Metal shared-surface probe passed (alignment=%zu stride=%zu)\n",
               (size_t)alignment, (size_t)stride);
    }

    return 0;
}
