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
#define MAX_OUTPUTS   8
#define MAX_TOPS_OUT  8

struct output {
    struct wl_output *o;
    int x, y, w, h;
    int have_geom;
    int covered;
};

static struct output outs[MAX_OUTPUTS];
static int n_outs = 0;
static int last_state[MAX_OUTPUTS];
static int seen_state[MAX_OUTPUTS];
static int debug = 0;

static struct toplevel {
    struct zcosmic_toplevel_handle_v1 *h;
    uint32_t state;
    int outs[MAX_TOPS_OUT];      /* indices into outs[] */
    int n_outs;
    char title[96];
} tops[MAX_TOPLEVELS];
static int n_tops = 0;

/* One line per output whose coverage changed, in layout coordinates, so the
 * wallpaper can throttle the covered monitor and leave the visible one alone. */
static void emit(const char *what, struct output *o) {
    printf("%s %d %d %d %d\n", what, o->x, o->y, o->w, o->h);
    fflush(stdout);
}

static void recompute(void) {
    for (int i = 0; i < n_outs; i++) outs[i].covered = 0;

    for (int i = 0; i < n_tops; i++) {
        if (!tops[i].h) continue;
        int maximized = tops[i].state & (1u << 0);
        int fullscreen = tops[i].state & (1u << 3);
        if (!maximized && !fullscreen) continue;
        for (int k = 0; k < tops[i].n_outs; k++) {
            int idx = tops[i].outs[k];
            if (idx >= 0 && idx < n_outs) outs[idx].covered = 1;
        }
    }

    for (int i = 0; i < n_outs; i++) {
        if (!outs[i].have_geom) continue;
        int want = outs[i].covered;
        if (!seen_state[i] || last_state[i] != want) {
            seen_state[i] = 1;
            last_state[i] = want;
            emit(want ? "covered" : "clear", &outs[i]);
        }
    }
}

static void on_state(void *data, struct zcosmic_toplevel_handle_v1 *h, struct wl_array *state) {
    (void)h;
    struct toplevel *t = data;
    t->state = 0;
    uint32_t *p;
    wl_array_for_each(p, state) { if (*p < 32) t->state |= 1u << *p; }
    if (debug) {
        fprintf(stderr, "debug: [%s] state=0x%x outs=", t->title, t->state);
        for (int k = 0; k < t->n_outs; k++) fprintf(stderr, "%d,", t->outs[k]);
        fprintf(stderr, "\n");
    }
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
    t->n_outs = 0;
    recompute();
}

static void on_done(void *d, struct zcosmic_toplevel_handle_v1 *h) { (void)d; (void)h; }
static void on_title(void *d, struct zcosmic_toplevel_handle_v1 *h, const char *t) {
    (void)h;
    struct toplevel *tp = d;
    snprintf(tp->title, sizeof tp->title, "%s", t ? t : "");
}
static void on_app_id(void *d, struct zcosmic_toplevel_handle_v1 *h, const char *a) { (void)d; (void)h; (void)a; }
static int output_index(struct wl_output *o) {
    for (int i = 0; i < n_outs; i++) if (outs[i].o == o) return i;
    if (n_outs >= MAX_OUTPUTS) return -1;
    outs[n_outs].o = o;
    outs[n_outs].have_geom = 0;
    outs[n_outs].covered = 0;
    return n_outs++;
}

static void on_output_enter(void *d, struct zcosmic_toplevel_handle_v1 *h, struct wl_output *o) {
    (void)h;
    struct toplevel *t = d;
    int idx = output_index(o);
    if (debug) fprintf(stderr, "debug: toplevel entered output idx %d\n", idx);
    if (idx < 0) return;
    for (int k = 0; k < t->n_outs; k++) if (t->outs[k] == idx) return;
    if (t->n_outs < MAX_TOPS_OUT) t->outs[t->n_outs++] = idx;
    recompute();
}

static void on_output_leave(void *d, struct zcosmic_toplevel_handle_v1 *h, struct wl_output *o) {
    (void)h;
    struct toplevel *t = d;
    int idx = output_index(o);
    for (int k = 0; k < t->n_outs; k++) {
        if (t->outs[k] == idx) { t->outs[k] = t->outs[--t->n_outs]; break; }
    }
    recompute();
}
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
    tops[slot].n_outs = 0;
    zcosmic_toplevel_handle_v1_add_listener(handle, &handle_listener, &tops[slot]);
}

static void on_info_done(void *d, struct zcosmic_toplevel_info_v1 *i) { (void)d; (void)i; }
static void on_finished(void *d, struct zcosmic_toplevel_info_v1 *i) { (void)d; (void)i; }

static const struct zcosmic_toplevel_info_v1_listener info_listener = {
    .toplevel = on_toplevel,
    .finished = on_finished,
    .done = on_info_done,      /* opcode 2 exists since v2 — must not be NULL */
};

static void out_geometry(void *d, struct wl_output *o, int32_t x, int32_t y,
                         int32_t pw, int32_t ph, int32_t sub,
                         const char *make, const char *model, int32_t tr) {
    (void)o; (void)pw; (void)ph; (void)sub; (void)make; (void)model; (void)tr;
    struct output *out = d;
    out->x = x; out->y = y;
    if (debug) fprintf(stderr, "debug: output at %d,%d\n", x, y);
    recompute();
}

static void out_mode(void *d, struct wl_output *o, uint32_t f, int32_t w,
                     int32_t h, int32_t r) {
    (void)o; (void)r;
    struct output *out = d;
    /* Only the CURRENT mode describes the output; the rest are modes it offers,
     * and taking the last one reported 4096x2160 for a 1080p panel. */
    if (!(f & WL_OUTPUT_MODE_CURRENT)) return;
    if (out->w != w || out->h != h) {
        out->w = w; out->h = h;
        out->have_geom = 1;
        recompute();
    }
}
static void out_done(void *d, struct wl_output *o) { (void)d; (void)o; }
static void out_scale(void *d, struct wl_output *o, int32_t s) { (void)d; (void)o; (void)s; }
static void out_name(void *d, struct wl_output *o, const char *n) { (void)d; (void)o; (void)n; }
static void out_desc(void *d, struct wl_output *o, const char *n) { (void)d; (void)o; (void)n; }

static const struct wl_output_listener output_listener = {
    .geometry = out_geometry, .mode = out_mode, .done = out_done,
    .scale = out_scale, .name = out_name, .description = out_desc,
};

static uint32_t info_name = 0;
static int have_info_global = 0;

static void on_global(void *data, struct wl_registry *reg, uint32_t name,
                      const char *iface, uint32_t version) {
    (void)data;
    if (strcmp(iface, zcosmic_toplevel_info_v1_interface.name) == 0) {
        /* Only remember it here. Binding the manager inside the first roundtrip
         * makes it announce toplevels before the wl_outputs are bound, and the
         * compositor never re-sends output_enter — every window then looks like
         * it is on no output at all. Bind it after the outputs instead. */
        info_name = name;
        have_info_global = 1;
    } else if (strcmp(iface, "wl_output") == 0) {
        int idx = output_index(NULL);            /* reserve the slot */
        if (idx < 0) return;
        uint32_t v = version < 4 ? version : 4;
        struct wl_output *o = wl_registry_bind(reg, name, &wl_output_interface, v);
        outs[idx].o = o;
        wl_output_add_listener(o, &output_listener, &outs[idx]);
    }
}

static void on_global_remove(void *d, struct wl_registry *r, uint32_t n) { (void)d; (void)r; (void)n; }
static const struct wl_registry_listener reg_listener = { on_global, on_global_remove };

int main(void) {
    debug = getenv("F796_PROBE_DEBUG") != NULL;
    struct wl_display *dpy = wl_display_connect(NULL);
    if (!dpy) { fprintf(stderr, "toplevel_probe: no display\n"); return 1; }
    struct wl_registry *reg = wl_display_get_registry(dpy);
    wl_registry_add_listener(reg, &reg_listener, NULL);
    wl_display_roundtrip(dpy);            /* outputs bound, manager remembered */
    if (!have_info_global) {
        fprintf(stderr, "toplevel_probe: protocol not offered\n");
        return 2;
    }
    /* Now that every output is known, bind the manager: it replays the toplevel
     * list, this time with output_enter for each window. */
    struct zcosmic_toplevel_info_v1 *info =
        wl_registry_bind(reg, info_name, &zcosmic_toplevel_info_v1_interface, 1);
    zcosmic_toplevel_info_v1_add_listener(info, &info_listener, NULL);
    wl_display_roundtrip(dpy);            /* toplevels + states + outputs */
    recompute();
    while (wl_display_dispatch(dpy) != -1) { }
    return 0;
}
