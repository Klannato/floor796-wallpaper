/* toplevel_probe — tell the wallpaper when a window covers the screen.
 *
 * Wayland has no "am I occluded" query for a layer-shell client, but COSMIC
 * publishes `zcosmic_toplevel_info_v1`: every toplevel with its state array.
 * A toplevel that is maximized or fullscreen covers the output, which is exactly
 * the case where animating the wallpaper at 12 fps buys nothing.
 *
 * Workspace awareness: a maximized/fullscreen toplevel on a *different*
 * workspace does not cover the output the user is looking at. COSMIC 1.0
 * exposes toplevels only through `ext_foreign_toplevel_list_v1` (the v1
 * `toplevel` event is gone at info protocol v2+), and workspaces only through
 * `ext_workspace_manager_v1`. A toplevel's `ext_workspace_enter` hands back the
 * *same* `ext_workspace_handle_v1` object the workspace manager created, so
 * pointer identity ties a toplevel to its workspaces and the handle's `state`
 * (ACTIVE bit) says which workspace is current. A covering toplevel counts only
 * while it sits on an active workspace.
 *
 * Prints one line per change — "covered <x> <y> <w> <h>" / "clear …" — and
 * never exits unless the display goes away. The wallpaper reads that line and
 * throttles the matching output.
 *
 * Built by tools/build_probe.sh; the protocol XMLs live in app/proto/.
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <wayland-client.h>

#include "cosmic-toplevel-info-client.h"
#include "ext-workspace-client.h"
#include "ext-foreign-toplevel-list-client.h"

#define MAX_TOPLEVELS 64
#define MAX_OUTPUTS   8
#define MAX_TOPS_OUT  8
#define MAX_WORKSPACES 64
#define MAX_TOPS_WS   8

struct output {
    struct wl_output *o;
    int x, y, w, h;
    int have_geom;
    int covered;
};

struct workspace {
    struct ext_workspace_handle_v1 *h;
    char name[64];
    int active;
};

struct toplevel {
    struct zcosmic_toplevel_handle_v1 *zh;          /* cosmic handle (owns events) */
    struct ext_foreign_toplevel_handle_v1 *fh;      /* foreign handle (kept alive) */
    uint32_t state;
    int outs[MAX_TOPS_OUT];      /* indices into outs[] */
    int n_outs;
    int wss[MAX_TOPS_WS];        /* indices into wss[] */
    int n_wss;
    char title[96];
};

static struct output outs[MAX_OUTPUTS];
static int n_outs = 0;
static int last_state[MAX_OUTPUTS];
static int seen_state[MAX_OUTPUTS];

static struct workspace wss[MAX_WORKSPACES];
static int n_wss = 0;

static struct toplevel tops[MAX_TOPLEVELS];
static int n_tops = 0;

static int debug = 0;

static int find_output(struct wl_output *o);   /* defined in the outputs section */

/* ── coverage ─────────────────────────────────────────────────────────────── */

/* One line per output whose coverage changed, in layout coordinates. */
static void emit(const char *what, struct output *o) {
    printf("%s %d %d %d %d\n", what, o->x, o->y, o->w, o->h);
    fflush(stdout);
}

static void recompute(void) {
    for (int i = 0; i < n_outs; i++) outs[i].covered = 0;

    for (int i = 0; i < n_tops; i++) {
        struct toplevel *t = &tops[i];
        if (!t->zh) continue;
        int maximized = t->state & (1u << 0);
        int fullscreen = t->state & (1u << 3);
        if (!maximized && !fullscreen) continue;

        int on_active = 0;
        for (int k = 0; k < t->n_wss; k++) {
            int ws = t->wss[k];
            if (ws >= 0 && ws < n_wss && wss[ws].active) { on_active = 1; break; }
        }
        if (!on_active) continue;

        for (int k = 0; k < t->n_outs; k++) {
            int idx = t->outs[k];
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

/* ── workspace bookkeeping ────────────────────────────────────────────────── */

static int ws_index_of(struct ext_workspace_handle_v1 *h) {
    intptr_t u = (intptr_t)ext_workspace_handle_v1_get_user_data(h);
    return (int)u - 1;   /* 0 means "not ours"; valid indices are >= 0 */
}

static void ws_name(void *d, struct ext_workspace_handle_v1 *h, const char *name) {
    (void)d;
    int idx = ws_index_of(h);
    if (idx >= 0 && idx < n_wss)
        snprintf(wss[idx].name, sizeof wss[idx].name, "%s", name ? name : "");
}

static void ws_state(void *d, struct ext_workspace_handle_v1 *h, uint32_t state) {
    (void)d;
    int idx = ws_index_of(h);
    if (idx < 0 || idx >= n_wss) return;
    int active = (state & EXT_WORKSPACE_HANDLE_V1_STATE_ACTIVE) != 0;
    if (wss[idx].active != active) {
        if (debug)
            fprintf(stderr, "debug: workspace %d (%s) active=%d\n",
                    idx, wss[idx].name, active);
        wss[idx].active = active;
        recompute();
    }
}

static void ws_removed(void *d, struct ext_workspace_handle_v1 *h) {
    (void)d;
    int idx = ws_index_of(h);
    if (idx >= 0 && idx < n_wss) {
        wss[idx].h = NULL;
        wss[idx].active = 0;
        recompute();
    }
}

static void ws_id(void *d, struct ext_workspace_handle_v1 *h, const char *id) {
    (void)d; (void)h; (void)id;
}
static void ws_coord(void *d, struct ext_workspace_handle_v1 *h,
                     struct wl_array *coords) { (void)d; (void)h; (void)coords; }
static void ws_caps(void *d, struct ext_workspace_handle_v1 *h, uint32_t c) {
    (void)d; (void)h; (void)c;
}

static const struct ext_workspace_handle_v1_listener ws_listener = {
    .id = ws_id,
    .name = ws_name,
    .coordinates = ws_coord,
    .state = ws_state,
    .capabilities = ws_caps,
    .removed = ws_removed,
};

/* ── workspace manager ────────────────────────────────────────────────────── */

static void on_wsmanager_workspace(void *d, struct ext_workspace_manager_v1 *m,
                                   struct ext_workspace_handle_v1 *h) {
    (void)d; (void)m;
    if (n_wss >= MAX_WORKSPACES) return;
    int idx = n_wss++;
    wss[idx].h = h;
    wss[idx].name[0] = '\0';
    wss[idx].active = 0;
    /* add_listener writes proxy->user_data with its `data` arg (NULL), so set
     * user_data *after* it — the ws_* callbacks look the index up from it. */
    ext_workspace_handle_v1_add_listener(h, &ws_listener, NULL);
    ext_workspace_handle_v1_set_user_data(h, (void *)(intptr_t)(idx + 1));
}

/* The group handle is created by libwayland for the new_id and discarded — we
 * track workspaces via the manager's `workspace` event and don't care which
 * output group they land in. A NULL handler would abort on the new_id. */
static void on_wsmanager_group(void *d, struct ext_workspace_manager_v1 *m,
                              struct ext_workspace_group_handle_v1 *g) {
    (void)d; (void)m; (void)g;
}

static void on_wsmanager_misc(void *d, struct ext_workspace_manager_v1 *m) {
    (void)d; (void)m;
}

static const struct ext_workspace_manager_v1_listener wsmanager_listener = {
    .workspace_group = on_wsmanager_group,
    .workspace = on_wsmanager_workspace,
    .done = on_wsmanager_misc,
    .finished = on_wsmanager_misc,
};

/* ── toplevel (cosmic) ────────────────────────────────────────────────────── */

static void top_state(void *d, struct zcosmic_toplevel_handle_v1 *h,
                      struct wl_array *state) {
    struct toplevel *t = d;
    t->state = 0;
    uint32_t *p;
    wl_array_for_each(p, state) { if (*p < 32) t->state |= 1u << *p; }
    if (debug) fprintf(stderr, "debug: [%s] state=0x%x\n", t->title, t->state);
    recompute();
}

static void top_open(void *d, struct zcosmic_toplevel_handle_v1 *h,
                     struct wl_output *o) {
    struct toplevel *t = d;
    if (t->n_outs >= MAX_TOPS_OUT) return;
    int idx = find_output(o);
    if (idx < 0) return;
    t->outs[t->n_outs++] = idx;
    recompute();
}

static void top_leave_out(void *d, struct zcosmic_toplevel_handle_v1 *h,
                          struct wl_output *o) {
    struct toplevel *t = d;
    int idx = find_output(o);
    for (int k = 0; k < t->n_outs; k++) {
        if (t->outs[k] == idx) { t->outs[k] = t->outs[--t->n_outs]; break; }
    }
    recompute();
}

static void top_ws_enter(void *d, struct zcosmic_toplevel_handle_v1 *h,
                         struct ext_workspace_handle_v1 *w) {
    struct toplevel *t = d;
    int idx = ws_index_of(w);
    if (idx < 0 || t->n_wss >= MAX_TOPS_WS) return;
    for (int k = 0; k < t->n_wss; k++) if (t->wss[k] == idx) return;
    t->wss[t->n_wss++] = idx;
    recompute();
}

static void top_ws_leave(void *d, struct zcosmic_toplevel_handle_v1 *h,
                         struct ext_workspace_handle_v1 *w) {
    struct toplevel *t = d;
    int idx = ws_index_of(w);
    for (int k = 0; k < t->n_wss; k++) {
        if (t->wss[k] == idx) { t->wss[k] = t->wss[--t->n_wss]; break; }
    }
    recompute();
}

static void top_title(void *d, struct zcosmic_toplevel_handle_v1 *h, const char *t) {
    struct toplevel *tp = d;
    snprintf(tp->title, sizeof tp->title, "%s", t ? t : "");
}
static void top_done(void *d, struct zcosmic_toplevel_handle_v1 *h) { (void)d; (void)h; }
static void top_appid(void *d, struct zcosmic_toplevel_handle_v1 *h, const char *a) { (void)d; (void)h; (void)a; }
static void top_geom(void *d, struct zcosmic_toplevel_handle_v1 *h, struct wl_output *o,
                     int32_t x, int32_t y, int32_t w, int32_t hh) {
    (void)d; (void)h; (void)o; (void)x; (void)y; (void)w; (void)hh;
}
static void top_ws_old_enter(void *d, struct zcosmic_toplevel_handle_v1 *h,
                             struct zcosmic_workspace_handle_v1 *w) { (void)d; (void)h; (void)w; }
static void top_ws_old_leave(void *d, struct zcosmic_toplevel_handle_v1 *h,
                             struct zcosmic_workspace_handle_v1 *w) { (void)d; (void)h; (void)w; }

/* Free the slot in place. Never compact tops[]: each handle/listener's data
 * pointer is &tops[i], so swapping entries makes surviving toplevels write
 * into the wrong slot. */
static void top_close(void *d, struct zcosmic_toplevel_handle_v1 *h) {
    struct toplevel *t = d;
    if (t->zh) { zcosmic_toplevel_handle_v1_destroy(t->zh); t->zh = NULL; }
    t->state = 0;
    t->n_outs = 0;
    t->n_wss = 0;
    recompute();
}

static const struct zcosmic_toplevel_handle_v1_listener top_listener = {
    .closed = top_close,
    .done = top_done,
    .title = top_title,
    .app_id = top_appid,
    .output_enter = top_open,
    .output_leave = top_leave_out,
    .workspace_enter = top_ws_old_enter,     /* deprecated — COSMIC 1.0 never sends it */
    .workspace_leave = top_ws_old_leave,
    .state = top_state,
    .geometry = top_geom,
    .ext_workspace_enter = top_ws_enter,
    .ext_workspace_leave = top_ws_leave,
};

/* ── foreign toplevel list (the only way to see toplevels at info v2+) ──── */

static struct zcosmic_toplevel_info_v1 *info_global = NULL;

static void on_foreign_toplevel(void *d, struct ext_foreign_toplevel_list_v1 *l,
                                struct ext_foreign_toplevel_handle_v1 *fh) {
    (void)d; (void)l;
    if (!info_global) return;   /* info manager not bound yet */
    int slot = -1;
    for (int i = 0; i < n_tops; i++) {
        if (!tops[i].zh) { slot = i; break; }
    }
    if (slot < 0) {
        if (n_tops >= MAX_TOPLEVELS) return;
        slot = n_tops++;
    }
    tops[slot].fh = fh;
    tops[slot].state = 0;
    tops[slot].n_outs = 0;
    tops[slot].n_wss = 0;
    /* get_cosmic_toplevel turns the foreign handle into a cosmic one whose
     * events carry outputs, workspaces and state. */
    struct zcosmic_toplevel_handle_v1 *zh =
        zcosmic_toplevel_info_v1_get_cosmic_toplevel(info_global, fh);
    tops[slot].zh = zh;
    zcosmic_toplevel_handle_v1_add_listener(zh, &top_listener, &tops[slot]);
}

static const struct ext_foreign_toplevel_list_v1_listener foreign_list_listener = {
    .toplevel = on_foreign_toplevel,
    .finished = NULL,
};

static void info_done(void *d, struct zcosmic_toplevel_info_v1 *i) {
    (void)d; (void)i;
}
static const struct zcosmic_toplevel_info_v1_listener info_listener = {
    .toplevel = NULL, .finished = NULL, .done = info_done,
};

/* ── outputs ──────────────────────────────────────────────────────────────── */

static int output_index(struct wl_output *o) {
    for (int i = 0; i < n_outs; i++) if (outs[i].o == o) return i;
    if (n_outs >= MAX_OUTPUTS) return -1;
    outs[n_outs].o = o;
    outs[n_outs].have_geom = 0;
    outs[n_outs].covered = 0;
    return n_outs++;
}

/* Pointer identity: the wl_output handed back by output_enter is the same proxy
 * the registry created, so a pointer compare maps it to our slot. */
static int find_output(struct wl_output *o) {
    for (int i = 0; i < n_outs; i++) if (outs[i].o == o) return i;
    return -1;
}

static void out_geometry(void *d, struct wl_output *o, int32_t x, int32_t y,
                         int32_t pw, int32_t ph, int32_t sub,
                         const char *make, const char *model, int32_t tr) {
    (void)o; (void)pw; (void)ph; (void)sub; (void)make; (void)model; (void)tr;
    struct output *out = d;
    out->x = x; out->y = y;
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

/* ── globals ──────────────────────────────────────────────────────────────── */

static uint32_t info_name = 0;
static uint32_t foreign_list_name = 0;
static uint32_t wsmanager_name = 0;

static void on_global(void *data, struct wl_registry *reg, uint32_t name,
                      const char *iface, uint32_t version) {
    (void)data;
    if (strcmp(iface, zcosmic_toplevel_info_v1_interface.name) == 0) {
        info_name = name;
    } else if (strcmp(iface, ext_foreign_toplevel_list_v1_interface.name) == 0) {
        foreign_list_name = name;
    } else if (strcmp(iface, ext_workspace_manager_v1_interface.name) == 0) {
        wsmanager_name = name;
    } else if (strcmp(iface, "wl_output") == 0) {
        int idx = output_index(NULL);            /* reserve the slot */
        if (idx < 0) return;
        uint32_t v = version < 4 ? version : 4;
        struct wl_output *o = wl_registry_bind(reg, name, &wl_output_interface, v);
        outs[idx].o = o;
        wl_output_add_listener(o, &output_listener, &outs[idx]);
    }
}

static void on_global_remove(void *d, struct wl_registry *r, uint32_t n) {
    (void)d; (void)r; (void)n;
}

static const struct wl_registry_listener reg_listener = { on_global, on_global_remove };

int main(void) {
    debug = getenv("F796_PROBE_DEBUG") != NULL;
    struct wl_display *dpy = wl_display_connect(NULL);
    if (!dpy) { fprintf(stderr, "toplevel_probe: no display\n"); return 1; }
    struct wl_registry *reg = wl_display_get_registry(dpy);
    wl_registry_add_listener(reg, &reg_listener, NULL);
    wl_display_roundtrip(dpy);            /* outputs bound, manager names known */

    /* Workspaces first: the toplevel's ext_workspace_enter references the same
     * ext_workspace_handle_v1 objects this manager created, so they must exist
     * before the info manager announces toplevels. */
    if (wsmanager_name) {
        struct ext_workspace_manager_v1 *m = wl_registry_bind(
            reg, wsmanager_name, &ext_workspace_manager_v1_interface, 1);
        ext_workspace_manager_v1_add_listener(m, &wsmanager_listener, NULL);
    } else {
        fprintf(stderr, "toplevel_probe: ext_workspace_manager_v1 not offered\n");
    }
    wl_display_roundtrip(dpy);            /* workspaces + names + states */

    if (!info_name || !foreign_list_name) {
        fprintf(stderr, "toplevel_probe: toplevel info / foreign list not offered\n");
        return 2;
    }

    struct zcosmic_toplevel_info_v1 *info = wl_registry_bind(
        reg, info_name, &zcosmic_toplevel_info_v1_interface, 3);
    zcosmic_toplevel_info_v1_add_listener(info, &info_listener, NULL);
    info_global = info;

    struct ext_foreign_toplevel_list_v1 *fl = wl_registry_bind(
        reg, foreign_list_name, &ext_foreign_toplevel_list_v1_interface, 1);
    ext_foreign_toplevel_list_v1_add_listener(fl, &foreign_list_listener, NULL);

    wl_display_roundtrip(dpy);            /* foreign toplevels promoted */
    wl_display_roundtrip(dpy);            /* cosmic handles: outputs + workspaces */

    recompute();
    while (wl_display_dispatch(dpy) != -1) { }
    return 0;
}
