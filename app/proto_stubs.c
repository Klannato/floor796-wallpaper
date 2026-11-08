/* Interface stubs for object arguments cosmic-toplevel-info mentions.
 *
 * The toplevel-info protocol's *deprecated* `workspace_enter`/`workspace_leave`
 * events (info protocol v1) reference `zcosmic_workspace_handle_v1`, which
 * COSMIC 1.0 no longer creates — it now uses `ext_workspace_handle_v1` (from
 * ext-workspace, linked for real) via the v3 `ext_workspace_enter` events. The
 * generated cosmic protocol code still names the old type at link time, so this
 * empty interface satisfies it. It is never bound, never listened to and carries
 * no requests.
 */
#include <wayland-client.h>

const struct wl_interface zcosmic_workspace_handle_v1_interface =
    { "zcosmic_workspace_handle_v1", 1, 0, NULL, 0, NULL };
