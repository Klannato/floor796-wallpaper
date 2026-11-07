/* toplevel_probe — tell the wallpaper when a window covers the screen.
 *
 * Wayland has no "am I occluded" query for a layer-shell client, but COSMIC
 * exposes zcosmic_toplevel_info_v1: every toplevel and its state array. A
 * toplevel that is maximized or fullscreen covers the output, which is exactly
 * the case where animating the wallpaper at 12 fps buys nothing.
 *
 * Prints one line per change — "covered 1" / "covered 0" — and never exits
 * unless the display goes away. The wallpaper reads that line and throttles.
 *
 * Built by tools/build_probe.sh; the protocol XML lives in app/proto/.
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <wayland-client.h>

#include "cosmic-toplevel-info-client.h"

#define MAX_TOPLEVELS 64

static struct toplevel { struct zcosmic_toplevel_handle_v1 *h; uint32_t state; } tops[MAX_TOPLEVELS];
static int n_tops = 0;
static int last_covered = -1;

static void report(int covered) {
    if (covered == last_covered) return;
    last_covered = covered;
    printf("covered %d\n", covered);
    fflush(stdout);
}

static void recompute(void) {
    int covered = 0;
    for (int i = 0; i < n_tops; i++) {
        if (!tops[i].h) continue;
        /* 0 = maximized, 3 = fullscreen */
        if (tops[i].state & (1u << 0) || tops[i].state & (1u << 3)) covered = 1;
    }
    report(covered);
}

static void on_state(void *data, struct zcosmic_toplevel_handle_v1 *h, struct wl_array *state) {
    (void)h;
    struct toplevel *t = data;
    t->state = 0;
    uint32_t *p;
    wl_array_for_each(p, state) { if (*p < 32) t->state |= 1u << *p; }
    if (getenv("F796_PROBE_DEBUG"))
        fprintf(stderr, "debug: toplevel state=0x%x\n", t->state);
    recompute();
}

static void on_closed(void *data, struct zcosmic_toplevel_handle_v1 *h) {
    struct toplevel *t = data;
    zcosmic_toplevel_handle_v1_destroy(h);
    /* Free the slot in place. Never compact the array: each handle's listener
     * data points at &tops[i], so swapping entries makes surviving toplevels
     * write their state into the wrong slot — which leaves a phantom
     * "covered" that never clears. */
    t->h = NULL;
    t->state = 0;
    recompute();
}

static void on_done(void *d, struct zcosmic_toplevel_handle_v1 *h) { (void)d; (void)h; }
static void on_title(void *d, struct zcosmic_toplevel_handle_v1 *h, const char *t) { (void)d; (void)h; (void)t; }
static void on_app_id(void *d, struct zcosmic_toplevel_handle_v1 *h, const char *a) { (void)d; (void)h; (void)a; }
static void on_output_enter(void *d, struct zcosmic_toplevel_handle_v1 *h, struct wl_output *o) { (void)d; (void)h; (void)o; }
static void on_output_leave(void *d, struct zcosmic_toplevel_handle_v1 *h, struct wl_output *o) { (void)d; (void)h; (void)o; }
static void on_ws_enter(void *d, struct zcosmic_toplevel_handle_v1 *h, struct zcosmic_workspace_handle_v2 *w) { (void)d; (void)h; (void)w; }
static void on_ws_leave(void *d, struct zcosmic_toplevel_handle_v1 *h, struct zcosmic_workspace_handle_v2 *w) { (void)d; (void)h; (void)w; }

static const struct zcosmic_toplevel_handle_v1_listener handle_listener = {
    .closed = on_closed,
    .done = on_done,
    .title = on_title,
    .app_id = on_app_id,
    .output_enter = on_output_enter,
    .output_leave = on_output_leave,
    .workspace_enter = on_ws_enter,
    .workspace_leave = on_ws_leave,
    .state = on_state,
};

static void on_toplevel(void *data, struct zcosmic_toplevel_info_v1 *info,
                        struct zcosmic_toplevel_handle_v1 *handle) {
    (void)data; (void)info;
    int slot = -1;
    for (int i = 0; i < n_tops; i++) {
        if (!tops[i].h) { slot = i; break; }     /* reuse a freed slot */
    }
    if (slot < 0) {
        if (n_tops >= MAX_TOPLEVELS) return;
        slot = n_tops++;
    }
    tops[slot].h = handle;
    tops[slot].state = 0;
    zcosmic_toplevel_handle_v1_add_listener(handle, &handle_listener, &tops[slot]);
}

static void on_info_done(void *d, struct zcosmic_toplevel_info_v1 *i) { (void)d; (void)i; }
static void on_finished(void *d, struct zcosmic_toplevel_info_v1 *i) { (void)d; (void)i; }

static const struct zcosmic_toplevel_info_v1_listener info_listener = {
    .toplevel = on_toplevel,
    .finished = on_finished,
    .done = on_info_done,      /* opcode 2 exists since v2 — must not be NULL */
};

static void on_global(void *data, struct wl_registry *reg, uint32_t name,
                      const char *iface, uint32_t version) {
    (void)version;
    if (strcmp(iface, zcosmic_toplevel_info_v1_interface.name) == 0) {
        struct zcosmic_toplevel_info_v1 **info = data;
        *info = wl_registry_bind(reg, name, &zcosmic_toplevel_info_v1_interface, 1);
        zcosmic_toplevel_info_v1_add_listener(*info, &info_listener, data);
    }
}

static void on_global_remove(void *d, struct wl_registry *r, uint32_t n) { (void)d; (void)r; (void)n; }
static const struct wl_registry_listener reg_listener = { on_global, on_global_remove };

int main(void) {
    struct wl_display *dpy = wl_display_connect(NULL);
    if (!dpy) { fprintf(stderr, "toplevel_probe: no display\n"); return 1; }
    struct zcosmic_toplevel_info_v1 *info = NULL;
    struct wl_registry *reg = wl_display_get_registry(dpy);
    wl_registry_add_listener(reg, &reg_listener, &info);
    wl_display_roundtrip(dpy);
    if (!info) { fprintf(stderr, "toplevel_probe: protocol not offered\n"); return 2; }
    /* First roundtrip: toplevels. Second: their states. Recompute from what
     * actually arrived instead of assuming "clear", which used to make the
     * wallpaper flap covered->clear on startup. */
    wl_display_roundtrip(dpy);
    recompute();
    while (wl_display_dispatch(dpy) != -1) { }
    return 0;
}
