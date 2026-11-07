#!/bin/sh
# Build the toplevel probe: generated protocol code + a small C program.
# Everything lands in vendor/bin, so the repo stays source-only.
set -e
ROOT=$(cd "$(dirname "$0")/.." && pwd)
GEN="$ROOT/vendor/proto"
mkdir -p "$GEN" "$ROOT/vendor/bin"
XML="$ROOT/app/proto/cosmic-toplevel-info-unstable-v1.xml"
wayland-scanner client-header "$XML" "$GEN/cosmic-toplevel-info-client.h"
wayland-scanner private-code  "$XML" "$GEN/cosmic-toplevel-info-protocol.c"
gcc -O2 -Wall -I"$GEN" -o "$ROOT/vendor/bin/toplevel_probe" \
    "$ROOT/app/toplevel_probe.c" "$ROOT/app/proto_stubs.c" \
    "$GEN/cosmic-toplevel-info-protocol.c" \
    $(pkg-config --cflags --libs wayland-client)
echo "built $ROOT/vendor/bin/toplevel_probe"
