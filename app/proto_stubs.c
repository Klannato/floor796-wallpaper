/* Interface stubs for the object arguments cosmic-toplevel-info mentions.
 *
 * The generated code refers to interfaces it never uses — the toplevel's
 * workspace and foreign-toplevel arguments — and libwayland needs those symbols
 * at link time. They are never bound, never listened to and carry no requests,
 * so an empty interface is enough. (We bind the info protocol at v2, which
 * predates the workspace events entirely.)
 */
#include <wayland-client.h>

static const struct wl_interface empty = { "", 0, 0, NULL, 0, NULL };

const struct wl_interface ext_foreign_toplevel_handle_v1_interface =
    { "ext_foreign_toplevel_handle_v1", 1, 0, NULL, 0, NULL };
const struct wl_interface zcosmic_workspace_handle_v1_interface =
    { "zcosmic_workspace_handle_v1", 1, 0, NULL, 0, NULL };
const struct wl_interface zcosmic_workspace_handle_v2_interface =
    { "zcosmic_workspace_handle_v2", 1, 0, NULL, 0, NULL };
const struct wl_interface ext_workspace_handle_v1_interface =
    { "ext_workspace_handle_v1", 1, 0, NULL, 0, NULL };

/* silence -Wunused */
void *_toplevel_probe_stubs(void) { return (void *)&empty; }
