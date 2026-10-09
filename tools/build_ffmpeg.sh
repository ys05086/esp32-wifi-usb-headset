#!/bin/sh
# A minimal LGPL FFmpeg for the AAC comparison: raw PCM in, AAC in an ADTS stream out, and back, over pipes.
# Nothing GPL or nonfree is enabled; configure prints the license and this script refuses anything but LGPL.
#
#   tools/build_ffmpeg.sh OUT_DIR [--cross]
#
# --cross builds the Windows ffmpeg.exe on Linux with mingw-w64 (the workflow); without it the host compiler is
# used (e.g. MSYS2 UCRT64 on Windows). OUT_DIR receives ffmpeg.exe, its license texts, BUILD.txt (version,
# source hash, configure line) and the exact source tarball, which the LGPL asks to ship alongside.
set -eu
VERSION=7.1.1
SHA256=733984395e0dbbe5c046abda2dc49a5544e7e0e1e2366bba849222ae9e3a03b1
OUT=$(mkdir -p "$1" && cd "$1" && pwd)
CROSS=${2:-}
WORK=$(mktemp -d)
TARBALL=ffmpeg-$VERSION.tar.xz

cd "$WORK"
curl -sSLf -o "$TARBALL" "https://ffmpeg.org/releases/$TARBALL"
echo "$SHA256  $TARBALL" | sha256sum -c -
tar -xf "$TARBALL"
cd "ffmpeg-$VERSION"

set -- \
  --disable-everything --disable-autodetect --disable-network --disable-doc --disable-debug \
  --disable-x86asm --enable-small \
  --disable-ffplay --disable-ffprobe --enable-ffmpeg \
  --disable-avdevice --disable-swscale --enable-swresample \
  --enable-protocol=pipe,file \
  --enable-demuxer=pcm_s16le,aac --enable-muxer=pcm_s16le,adts \
  --enable-decoder=pcm_s16le,aac --enable-encoder=pcm_s16le,aac --enable-parser=aac \
  --enable-filter=aresample,aformat,anull,atrim,abuffer,abuffersink \
  --extra-ldflags=-static
if [ "$CROSS" = "--cross" ]; then
  set -- "$@" --enable-cross-compile --arch=x86_64 --target-os=mingw32 --cross-prefix=x86_64-w64-mingw32-
fi
./configure "$@" > configure.log
grep -q '^License: LGPL version 2.1 or later' configure.log || { tail -5 configure.log; echo "not LGPL 2.1+" >&2; exit 1; }
make -j"$(nproc)" ffmpeg.exe > make.log 2>&1 || { tail -40 make.log; exit 1; }

cp ffmpeg.exe COPYING.LGPLv2.1 LICENSE.md "$OUT/"
mkdir -p "$OUT/source"
cp "../$TARBALL" "$OUT/source/"
{
  echo "FFmpeg $VERSION, built for ESP32 Audio Bridge's AAC comparison (LGPL version 2.1 or later)."
  echo "Source: source/$TARBALL (sha256 $SHA256), unmodified, from https://ffmpeg.org/releases/$TARBALL"
  echo "Build script: tools/build_ffmpeg.sh in https://github.com/ys05086/esp32-wifi-usb-headset"
  echo "configure $*"
  echo "You may replace ffmpeg.exe with your own build of FFmpeg; the app runs it as a separate program."
} > "$OUT/BUILD.txt"
rm -rf "$WORK"
ls -l "$OUT"
