/*
 * Standalone Cocoa device catalog
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#include "qemu/osdep.h"
#import <Cocoa/Cocoa.h>
#include "ui/cocoa-device-help.h"

@interface QemuDeviceHelpController : NSObject <NSWindowDelegate>
@end

@implementation QemuDeviceHelpController
- (void)windowWillClose:(NSNotification *)notification
{
    (void)notification;
    [NSApp stopModal];
}
@end

static void device_help_menu(NSWindow *window)
{
    NSMenu *main = [[[NSMenu alloc] init] autorelease];
    NSMenuItem *appItem = [[[NSMenuItem alloc] init] autorelease];
    NSMenu *app = [[[NSMenu alloc] initWithTitle:@"QEMU"] autorelease];
    NSMenuItem *editItem = [[[NSMenuItem alloc] init] autorelease];
    NSMenu *edit = [[[NSMenu alloc] initWithTitle:@"Edit"] autorelease];
    NSMenuItem *find, *close;

    [appItem setSubmenu:app];
    [main addItem:appItem];
    close = [app addItemWithTitle:@"Quit QEMU" action:@selector(performClose:)
                     keyEquivalent:@"q"];
    [close setTarget:window];
    [editItem setTitle:@"Edit"];
    [editItem setSubmenu:edit];
    [main addItem:editItem];
    [edit addItemWithTitle:@"Copy" action:@selector(copy:)
             keyEquivalent:@"c"];
    [edit addItemWithTitle:@"Select All" action:@selector(selectAll:)
             keyEquivalent:@"a"];
    find = [edit addItemWithTitle:@"Find…" action:@selector(performFindPanelAction:)
                   keyEquivalent:@"f"];
    [find setTag:NSTextFinderActionShowFindInterface];
    [edit addItem:[NSMenuItem separatorItem]];
    close = [edit addItemWithTitle:@"Close Window"
                            action:@selector(performClose:)
                     keyEquivalent:@"w"];
    [close setTarget:window];
    [NSApp setMainMenu:main];
}

bool cocoa_device_help_show(const char *catalog)
{
    @autoreleasepool {
        NSWindow *window;
        NSScrollView *scroll;
        NSTextView *text;
        QemuDeviceHelpController *controller;
        NSString *contents;
        NSScreen *screen;
        NSRect visible, frame;

        if (![NSThread isMainThread]) {
            return false;
        }

        [NSApplication sharedApplication];
        screen = [NSScreen mainScreen];
        contents = [NSString stringWithUTF8String:catalog];
        if (!screen || !contents ||
            ![NSApp setActivationPolicy:NSApplicationActivationPolicyRegular]) {
            return false;
        }

        visible = [screen visibleFrame];
        frame = NSMakeRect(0, 0, MIN(900, visible.size.width),
                                MIN(620, visible.size.height));
        window = [[NSWindow alloc]
            initWithContentRect:frame
                      styleMask:NSWindowStyleMaskTitled |
                                NSWindowStyleMaskClosable |
                                NSWindowStyleMaskResizable
                        backing:NSBackingStoreBuffered defer:NO];
        if (!window) {
            return false;
        }
        [window setReleasedWhenClosed:NO];
        [window setTitle:@"QEMU Device Catalog"];
        [window setContentMinSize:NSMakeSize(MIN(420, frame.size.width),
                                             MIN(280, frame.size.height))];

        scroll = [[NSScrollView alloc] initWithFrame:frame];
        [scroll setAutoresizingMask:NSViewWidthSizable | NSViewHeightSizable];
        [scroll setHasVerticalScroller:YES];
        [scroll setAutohidesScrollers:YES];

        NSSize contentSize = [scroll contentSize];
        text = [[NSTextView alloc] initWithFrame:
            NSMakeRect(0, 0, contentSize.width, contentSize.height)];
        [text setMinSize:NSMakeSize(0, contentSize.height)];
        [text setEditable:NO];
        [text setSelectable:YES];
        [text setRichText:NO];
        [text setFont:[NSFont userFixedPitchFontOfSize:12]];
        [text setTextContainerInset:NSMakeSize(12, 8)];
        [text setVerticallyResizable:YES];
        [text setHorizontallyResizable:NO];
        [text setAutoresizingMask:NSViewWidthSizable];
        [text setMaxSize:NSMakeSize(CGFLOAT_MAX, CGFLOAT_MAX)];
        [[text textContainer] setContainerSize:
            NSMakeSize([scroll contentSize].width, CGFLOAT_MAX)];
        [[text textContainer] setWidthTracksTextView:YES];
        [text setUsesFindBar:YES];
        [text setString:contents];
        [scroll setDocumentView:text];
        [text sizeToFit];
        [text scrollRangeToVisible:NSMakeRange(0, 0)];
        [window setContentView:scroll];
        [window makeFirstResponder:text];

        controller = [[QemuDeviceHelpController alloc] init];
        [window setDelegate:controller];
        device_help_menu(window);
        [NSApp finishLaunching];
        [window center];
        [window makeKeyAndOrderFront:nil];
        [[NSRunningApplication currentApplication] activateWithOptions:0];
        [NSApp runModalForWindow:window];

        [window setDelegate:nil];
        [window orderOut:nil];
        [NSApp setMainMenu:nil];
        [controller release];
        [window release];
        [scroll release];
        [text release];
        return true;
    }
}
