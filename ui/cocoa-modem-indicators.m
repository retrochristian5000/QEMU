/*
 * External modem front-panel presentation, independent of guest rendering.
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#include "qemu/osdep.h"
#import <Cocoa/Cocoa.h>
#include "qemu/atomic.h"
#include "qemu/main-loop.h"
#include "chardev/modem.h"
#include "ui/cocoa-modem-indicators.h"

#define MODEM_FLASH_US 180000

typedef struct ModemIndicatorHistory {
    unsigned rx_events;
    unsigned tx_events;
    gint64 rx_until;
    gint64 tx_until;
} ModemIndicatorHistory;

static bool inspector_enabled;

@interface QemuModemInspector : NSObject <NSWindowDelegate>
{
    NSPanel *panel;
    NSTextView *display;
    NSTextView *commandLog;
    NSButton *captureButton;
    NSTimer *timer;
    GHashTable *history;
}
- (void)show;
- (void)refresh:(NSTimer *)sender;
- (void)stop;
- (void)toggleCapture:(id)sender;
- (void)clearCapture:(id)sender;
@end

@implementation QemuModemInspector

- (id)init
{
    self = [super init];
    if (!self) {
        return nil;
    }

    NSRect frame = NSMakeRect(0, 0, 680, 480);
    panel = [[NSPanel alloc] initWithContentRect:frame
        styleMask:NSWindowStyleMaskTitled | NSWindowStyleMaskClosable |
                  NSWindowStyleMaskResizable
          backing:NSBackingStoreBuffered defer:NO];
    [panel setTitle:@"External Modem Inspector"];
    [panel setReleasedWhenClosed:NO];
    [panel setContentMinSize:NSMakeSize(520, 320)];
    [panel setDelegate:self];
    [panel setHidesOnDeactivate:NO];

    NSView *contentView = [[NSView alloc] initWithFrame:frame];
    NSRect indicatorFrame = NSMakeRect(0, frame.size.height - 164,
                                       frame.size.width, 164);
    NSScrollView *scroll =
        [[NSScrollView alloc] initWithFrame:indicatorFrame];
    [scroll setHasVerticalScroller:YES];
    [scroll setAutohidesScrollers:YES];
    [scroll setAutoresizingMask:NSViewWidthSizable | NSViewMinYMargin];
    display = [[NSTextView alloc] initWithFrame:indicatorFrame];
    [display setEditable:NO];
    [display setSelectable:YES];
    [display setVerticallyResizable:YES];
    [display setHorizontallyResizable:NO];
    [display setAutoresizingMask:NSViewWidthSizable];
    [display setTextContainerInset:NSMakeSize(12, 10)];
    [display setMaxSize:NSMakeSize(CGFLOAT_MAX, CGFLOAT_MAX)];
    [[display textContainer] setWidthTracksTextView:YES];
    [scroll setDocumentView:display];
    [contentView addSubview:scroll];
    [scroll release];

    captureButton = [[NSButton alloc]
        initWithFrame:NSMakeRect(12, frame.size.height - 194, 240, 24)];
    [captureButton setButtonType:NSButtonTypeSwitch];
    [captureButton setState:NSControlStateValueOff];
    [captureButton setTitle:@"Capture AT commands and replies"];
    [captureButton setTarget:self];
    [captureButton setAction:@selector(toggleCapture:)];
    [captureButton setAutoresizingMask:NSViewMinYMargin];
    [contentView addSubview:captureButton];

    NSButton *clear = [[NSButton alloc]
        initWithFrame:NSMakeRect(frame.size.width - 88,
                                 frame.size.height - 195, 76, 26)];
    [clear setTitle:@"Clear"];
    [clear setBezelStyle:NSBezelStyleRounded];
    [clear setTarget:self];
    [clear setAction:@selector(clearCapture:)];
    [clear setAutoresizingMask:NSViewMinXMargin | NSViewMinYMargin];
    [contentView addSubview:clear];
    [clear release];

    NSRect logFrame = NSMakeRect(0, 0, frame.size.width,
                                 frame.size.height - 200);
    NSScrollView *logScroll = [[NSScrollView alloc] initWithFrame:logFrame];
    [logScroll setHasVerticalScroller:YES];
    [logScroll setAutohidesScrollers:YES];
    [logScroll setAutoresizingMask:NSViewWidthSizable | NSViewHeightSizable];
    commandLog = [[NSTextView alloc] initWithFrame:logFrame];
    [commandLog setEditable:NO];
    [commandLog setSelectable:YES];
    [commandLog setVerticallyResizable:YES];
    [commandLog setHorizontallyResizable:NO];
    [commandLog setAutoresizingMask:NSViewWidthSizable];
    [commandLog setTextContainerInset:NSMakeSize(12, 8)];
    [commandLog setMaxSize:NSMakeSize(CGFLOAT_MAX, CGFLOAT_MAX)];
    [[commandLog textContainer] setWidthTracksTextView:YES];
    [commandLog setFont:[NSFont userFixedPitchFontOfSize:12]];
    [logScroll setDocumentView:commandLog];
    [contentView addSubview:logScroll];
    [logScroll release];
    [panel setContentView:contentView];
    [contentView release];
    history = g_hash_table_new_full(g_str_hash, g_str_equal, g_free, g_free);
    [panel center];
    return self;
}

- (void)toggleCapture:(id)sender
{
    (void)sender;
    bool enabled = [captureButton state] == NSControlStateValueOn;
    bool locked = bql_locked();

    if (!locked) {
        bql_lock();
    }
    if (qatomic_read(&inspector_enabled)) {
        qemu_modem_command_log_set_enabled(enabled);
    }
    if (!locked) {
        bql_unlock();
    }
    [self refresh:nil];
}

- (void)clearCapture:(id)sender
{
    (void)sender;
    bool locked = bql_locked();

    if (!locked) {
        bql_lock();
    }
    if (qatomic_read(&inspector_enabled)) {
        qemu_modem_command_log_clear();
    }
    if (!locked) {
        bql_unlock();
    }
    [self refresh:nil];
}

- (void)stop
{
    if ([captureButton state] == NSControlStateValueOn &&
        qatomic_read(&inspector_enabled)) {
        bool locked = bql_locked();

        if (!locked) {
            bql_lock();
        }
        if (qatomic_read(&inspector_enabled)) {
            qemu_modem_command_log_set_enabled(false);
        }
        if (!locked) {
            bql_unlock();
        }
    }
    [captureButton setState:NSControlStateValueOff];
    [commandLog setString:@""];
    [timer invalidate];
    [timer release];
    timer = nil;
    g_hash_table_remove_all(history);
}

- (void)windowWillClose:(NSNotification *)notification
{
    (void)notification;
    [self stop];
}

- (void)refresh:(NSTimer *)sender
{
    (void)sender;
    if (!qatomic_read(&inspector_enabled)) {
        [self stop];
        [panel orderOut:nil];
        return;
    }
    bool locked = bql_locked();
    if (!locked) {
        bql_lock();
    }
    GPtrArray *snapshots = qatomic_read(&inspector_enabled) ?
                           qemu_modem_indicator_snapshot() : NULL;
    if (!locked) {
        bql_unlock();
    }
    if (!snapshots) {
        [self stop];
        [panel orderOut:nil];
        return;
    }

    gint64 now = g_get_monotonic_time();
    GHashTable *next = g_hash_table_new_full(g_str_hash, g_str_equal,
                                            g_free, g_free);
    NSMutableAttributedString *content =
        [[[NSMutableAttributedString alloc] init] autorelease];
    NSFont *font = [NSFont userFixedPitchFontOfSize:13];
    NSDictionary *base = @{
        NSFontAttributeName: font,
        NSForegroundColorAttributeName: [NSColor labelColor],
    };
    static const char *const labels[] = {
        "TST", "HS", "EC", "CD", "OH", "RD", "SD", "TR", "MR",
    };
    for (guint i = 0; i < snapshots->len; i++) {
        const ModemIndicatorSnapshot *s = g_ptr_array_index(snapshots, i);
        ModemIndicatorHistory *old = g_hash_table_lookup(history, s->id);
        ModemIndicatorHistory *h = g_new0(ModemIndicatorHistory, 1);
        unsigned active = s->active;
        if (old) {
            h->rx_until = old->rx_events != s->rx_events ?
                          now + MODEM_FLASH_US : old->rx_until;
            h->tx_until = old->tx_events != s->tx_events ?
                          now + MODEM_FLASH_US : old->tx_until;
        }
        h->rx_events = s->rx_events;
        h->tx_events = s->tx_events;
        g_hash_table_insert(next, g_strdup(s->id), h);
        if (h->rx_until > now) {
            active |= MODEM_LED_RD;
        }
        if (h->tx_until > now) {
            active |= MODEM_LED_SD;
        }

        NSString *identifier = [NSString stringWithUTF8String:s->id];
        NSString *heading = [NSString stringWithFormat:
            @"AT&T Paradyne DataPort Express 3740 — %@\n",
            identifier ? identifier : @"Unnamed backend"];
        [content appendAttributedString:[[[NSAttributedString alloc]
            initWithString:heading attributes:base] autorelease]];
        for (unsigned j = 0; j < G_N_ELEMENTS(labels); j++) {
            unsigned bit = 1U << j;
            bool supported = s->supported & bit;
            bool lit = active & bit;
            NSColor *color = lit ? [NSColor systemRedColor] :
                                   [NSColor secondaryLabelColor];
            NSString *cell = [NSString stringWithFormat:@"%@ %-3s  ",
                !supported ? @"–" : lit ? @"●" : @"○", labels[j]];
            NSDictionary *attributes = @{
                NSFontAttributeName: font,
                NSForegroundColorAttributeName: color,
            };
            [content appendAttributedString:[[[NSAttributedString alloc]
                initWithString:cell attributes:attributes] autorelease]];
        }
        [content appendAttributedString:[[[NSAttributedString alloc]
            initWithString:@"\n\n" attributes:base] autorelease]];
    }
    if (!snapshots->len) {
        [content appendAttributedString:[[[NSAttributedString alloc]
            initWithString:@"No supported external modem is attached.\n"
            attributes:base] autorelease]];
    }
    [content appendAttributedString:[[[NSAttributedString alloc]
        initWithString:@"● Active   ○ Inactive   – Not emulated\n"
                       @"CD/OH: simulated line state; RD/SD: serial activity"
        attributes:base] autorelease]];
    [[display textStorage] setAttributedString:content];
    NSMutableString *transcript = [NSMutableString string];
    if ([captureButton state] == NSControlStateValueOn) {
        for (guint i = 0; i < snapshots->len; i++) {
            const ModemIndicatorSnapshot *s = g_ptr_array_index(snapshots, i);
            if (s->command_log && *s->command_log) {
                NSString *identifier = [NSString stringWithUTF8String:s->id];
                [transcript appendFormat:@"[%@]\n%s\n",
                    identifier ? identifier : @"Unnamed backend",
                    s->command_log];
            }
        }
        if (![transcript length]) {
            [transcript appendString:@"Waiting for modem commands…"];
        }
    } else {
        [transcript appendString:
            @"Capture is off. Enable it to see commands and replies.\n"
             @"Command text may contain telephone numbers; online data "
             @"is not captured. Closing this window clears the log."];
    }
    if (![[commandLog string] isEqualToString:transcript]) {
        NSRect visible = [commandLog visibleRect];
        bool follow = NSMaxY(visible) >= NSHeight([commandLog bounds]) - 8;
        NSRange selection = [commandLog selectedRange];

        [commandLog setString:transcript];
        if (follow) {
            [commandLog scrollRangeToVisible:
                NSMakeRange([transcript length], 0)];
        } else if (NSMaxRange(selection) <= [transcript length]) {
            [commandLog setSelectedRange:selection];
        }
    }
    g_hash_table_unref(history);
    history = next;
    g_ptr_array_unref(snapshots);
}

- (void)show
{
    if (!qatomic_read(&inspector_enabled)) {
        return;
    }
    if (!timer) {
        [self refresh:nil];
        if (!qatomic_read(&inspector_enabled)) {
            return;
        }
        timer = [[NSTimer scheduledTimerWithTimeInterval:0.08
            target:self selector:@selector(refresh:) userInfo:nil
            repeats:YES] retain];
    }
    [panel makeKeyAndOrderFront:nil];
}

- (void)dealloc
{
    [self stop];
    [panel setDelegate:nil];
    [panel release];
    [display release];
    [captureButton release];
    [commandLog release];
    g_hash_table_unref(history);
    [super dealloc];
}
@end

void cocoa_modem_indicators_set_enabled(bool enabled)
{
    qatomic_set(&inspector_enabled, enabled);
}

void cocoa_modem_indicators_show(void)
{
    static QemuModemInspector *inspector;

    if (!qatomic_read(&inspector_enabled)) {
        return;
    }
    if (!inspector) {
        inspector = [[QemuModemInspector alloc] init];
    }
    [inspector show];
}
