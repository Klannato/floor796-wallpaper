#!/bin/sh
# Build the toplevel probe: generated protocol code + a small C program.
# Everything lands in vendor/bin, so the repo stays source-only.
set -e
ROOT=$(cd "$(dirname "$0")/.." && pwd)
GEN="$ROOT/vendor/proto"
mkdir -p "$GEN" "$ROOT/vendor/bin"
P="$ROOT/app/proto"

# The probe speaks three protocols: zcosmic_toplevel_info_v1 (toplevel state),
# ext_workspace_v1 (workspace membership + active bit), and
# ext_foreign_toplevel_list_v1 (the only way COSMIC 1.0 exposes toplevels).
wayland-scanner client-header "$P/cosmic-toplevel-info-unstable-v1.xml" "$GEN/cosmic-toplevel-info-client.h"
wayland-scanner private-code  "$P/cosmic-toplevel-info-unstable-v1.xml" "$GEN/cosmic-toplevel-info-protocol.c"
wayland-scanner client-header "$P/ext-workspace-v1.xml" "$GEN/ext-workspace-client.h"
wayland-scanner private-code  "$P/ext-workspace-v1.xml" "$GEN/ext-workspace-protocol.c"
wayland-scanner client-header "$P/ext-foreign-toplevel-list-v1.xml" "$GEN/ext-foreign-toplevel-list-client.h"
wayland-scanner private-code  "$P/ext-foreign-toplevel-list-v1.xml" "$GEN/ext-foreign-toplevel-list-protocol.c"

gcc -O2 -Wall -I"$GEN" -o "$ROOT/vendor/bin/toplevel_probe" \
    "$ROOT/app/toplevel_probe.c" "$ROOT/app/proto_stubs.c" \
    "$GEN/cosmic-toplevel-info-protocol.c" \
    "$GEN/ext-workspace-protocol.c" \
    "$GEN/ext-foreign-toplevel-list-protocol.c" \
    $(pkg-config --cflags --libs wayland-client)
echo "built $ROOT/vendor/bin/toplevel_probe"
