#!/bin/bash
#
# darling-brew-stubs.sh — Install macOS tool stubs/wrappers for Homebrew on Darling
# Run with: pkexec bash /tmp/darling-brew-stubs.sh
#
# These stubs go into the overlay upperdir (~/.darling/usr/bin/) so they shadow
# the Mach-O binaries in lowerdir that may not work inside the container.
#

set -euo pipefail

STUB_DIR="${HOME}/usr/bin"
mkdir -p "$STUB_DIR" 2>/dev/null || true

echo "=== Installing brew stubs to $STUB_DIR ==="

# --- curl: use host Linux curl ---
cat > "$STUB_DIR/curl" << 'CURL_EOF'
#!/bin/bash
# curl wrapper: delegate to host Linux curl via overlay mount
# The Mach-O curl inside Darling may not resolve SSL certs or DNS properly.
exec /Volumes/SystemRoot/usr/bin/curl "$@"
CURL_EOF
chmod +x "$STUB_DIR/curl"
echo "[OK] curl"

# --- install_name_tool: no-op (Darling doesn't use dyld install names the same way) ---
cat > "$STUB_DIR/install_name_tool" << 'EOF'
#!/bin/bash
# install_name_tool stub for Darling
# On macOS this modifies Mach-O load commands. In Darling, dyld handles
# this transparently. Just exit successfully.
# Silently accept all args — brew just wants exit 0.
exit 0
EOF
chmod +x "$STUB_DIR/install_name_tool"
echo "[OK] install_name_tool"

# --- otool: minimal stub using readelf for -L, no-op for rest ---
cat > "$STUB_DIR/otool" << 'EOF'
#!/bin/bash
# otool stub for Darling — provides -L (list dylib deps) via readelf
# brew uses: otool -L <file>
OUTPUT=""
EXIT_CODE=0

while [ $# -gt 0 ]; do
    case "$1" in
        -L|-l|-h|-t|-d|-s|-S|-m|-p|-I)
            FLAG="$1"
            shift
            FILE="$1"
            shift
            ;;
        *)
            shift
            ;;
    esac
done

if [ -z "${FILE:-}" ]; then
    echo "otool: no input file" >&2
    exit 1
fi

if [ ! -f "$FILE" ]; then
    echo "otool: file '$FILE' not found" >&2
    exit 1
fi

case "${FLAG:--L}" in
    -L)
        # Show shared library dependencies using readelf
        if command -v readelf &>/dev/null; then
            readelf -d "$FILE" 2>/dev/null | grep NEEDED | awk '{print "    " $NF " (compatibility version 0.0.0, current version 0.0.0)"}'
        elif command -v objdump &>/dev/null; then
            objdump -x "$FILE" 2>/dev/null | grep "NEEDED" | awk '{print $NF}' | while read lib; do
                echo "    $lib (compatibility version 0.0.0, current version 0.0.0)"
            done
        else
            # Fallback: use ldd-style
            echo "    /usr/lib/libSystem.B.dylib (compatibility version 0.0.0, current version 0.0.0)"
        fi
        ;;
    -h)
        # Mach-O header — return a minimal fake header
        echo "Mach-O universal binary with 1 architecture"
        echo "Mach-O 64-bit executable x86_64"
        ;;
    *)
        # For -l, -t, -d, etc: return empty (not critical for brew)
        ;;
esac

exit $EXIT_CODE
EOF
chmod +x "$STUB_DIR/otool"
echo "[OK] otool"

# --- sw_vers: spoof macOS 26.0 (Tahoe) ---
cat > "$STUB_DIR/sw_vers" << 'EOF'
#!/bin/bash
# sw_vers stub — report macOS Tahoe 26.0 for Homebrew compatibility
PRODUCT="macOS"
VERSION="26.0"
BUILD="25A362"
VERSION_NAME="Tahoe"

show_version() { echo "$VERSION"; }
show_build()   { echo "$BUILD"; }
show_name()    { echo "$PRODUCTName:		$PRODUCT"; echo "ProductVersion:		$VERSION"; echo "BuildVersion:		$BUILD"; }

case "${1:--productVersion}" in
    -productVersion) show_version ;;
    -buildVersion)   show_build ;;
    -productName)    echo "$PRODUCT" ;;
    *)               show_name ;;
esac
exit 0
EOF
chmod +x "$STUB_DIR/sw_vers"
echo "[OK] sw_vers"

# --- pkgutil: no-op ---
cat > "$STUB_DIR/pkgutil" << 'EOF'
#!/bin/bash
# pkgutil stub for Darling — no macOS packages, just exit
case "${1:-}" in
    --pkgs)     echo "" ;;
    --pkgs=*)   echo "" ;;
    --vol-info) echo "/" ;;
    --pkg-info) echo "install-time: 0\ntime: 0" ;;
    *)          ;;
esac
exit 0
EOF
chmod +x "$STUB_DIR/pkgutil"
echo "[OK] pkgutil"

# --- xattr: Linux getfattr/setfattr wrapper ---
cat > "$STUB_DIR/xattr" << 'EOF'
#!/bin/bash
# xattr stub for Darling — map to Linux extended attributes
ACTION=""
FILE=""

while [ $# -gt 0 ]; do
    case "$1" in
        -l) ACTION="list"; shift ;;
        -p) ACTION="print"; shift; ATTR="$1"; shift ;;
        -w) ACTION="write"; shift; ATTR="$1"; shift ;;
        -d) ACTION="delete"; shift; ATTR="$1"; shift ;;
        -c) ACTION="clear"; shift ;;
        -r) shift ;; # recursive — skip
        -s) shift ;; # — skip
        -*) shift ;;
        *)
            if [ -z "$FILE" ]; then
                FILE="$1"
            fi
            shift
            ;;
    esac
done

if [ -z "$FILE" ]; then
    echo "xattr: no file specified" >&2
    exit 1
fi

case "$ACTION" in
    list)
        if command -v getfattr &>/dev/null && [ -f "$FILE" ]; then
            getfattr -d --only-values "$FILE" 2>/dev/null || true
        fi
        ;;
    print)
        if command -v getfattr &>/dev/null && [ -f "$FILE" ]; then
            getfattr -n "$ATTR" --only-values "$FILE" 2>/dev/null || true
        fi
        ;;
    write)
        if command -v setfattr &>/dev/null && [ -f "$FILE" ]; then
            setfattr -n "$ATTR" -v "$2" "$FILE" 2>/dev/null || true
        fi
        ;;
    delete)
        if command -v setfattr &>/dev/null && [ -f "$FILE" ]; then
            setfattr -x "$ATTR" "$FILE" 2>/dev/null || true
        fi
        ;;
    clear)
        # No-op on Linux
        ;;
    *)
        echo "xattr: no action specified" >&2
        exit 1
        ;;
esac
exit 0
EOF
chmod +x "$STUB_DIR/xattr"
echo "[OK] xattr"

# --- sysctl: wrapper to host ---
cat > "$STUB_DIR/sysctl" << 'EOF'
#!/bin/bash
# sysctl wrapper for Darling — delegate to host Linux sysctl
# Translate macOS-style sysctl names to Linux equivalents where needed
ARGS=()
for arg in "$@"; do
    case "$arg" in
        hw.ncpu) ARGS+=("hw.ncpu") ;;
        hw.memsize) ARGS+=(-a | grep MemTotal) ;;
        *) ARGS+=("$arg") ;;
    esac
done

if command -v /Volumes/SystemRoot/usr/sbin/sysctl &>/dev/null; then
    exec /Volumes/SystemRoot/usr/sbin/sysctl "${ARGS[@]}"
elif command -v /Volumes/SystemRoot/usr/bin/sysctl &>/dev/null; then
    exec /Volumes/SystemRoot/usr/bin/sysctl "${ARGS[@]}"
fi

# Fallback for brew diagnostic queries
for arg in "$@"; do
    case "$arg" in
        hw.ncpu) nproc ;;
        hw.memsize) free -b | awk '/Mem:/{print $2}' ;;
    esac
done
exit 0
EOF
chmod +x "$STUB_DIR/sysctl"
echo "[OK] sysctl"

# --- codesign: no-op ---
cat > "$STUB_DIR/codesign" << 'EOF'
#!/bin/bash
# codesign stub for Darling — code signing not applicable
case "${1:-}" in
    --verify|--verify --deep)
        # Fake verification success
        ;;
    --sign)
        shift  # Skip the signing identity
        ;;
    --display)
        echo "Signature=adhoc"
        ;;
    --remove-signature)
        ;;
    -s)
        shift  # Skip -
        ;;
esac
exit 0
EOF
chmod +x "$STUB_DIR/codesign"
echo "[OK] codesign"

# --- dsymutil: no-op ---
cat > "$STUB_DIR/dsymutil" << 'EOF'
#!/bin/bash
# dsymutil stub for Darling — debug symbols not applicable
# brew calls: dsymutil <binary> (to extract dSYM)
# Just create empty dSYM directory if requested
for arg in "$@"; do
    case "$arg" in
        *.dSYM)
            mkdir -p "$arg" 2>/dev/null
            ;;
    esac
done
exit 0
EOF
chmod +x "$STUB_DIR/dsymutil"
echo "[OK] dsymutil"

# --- diskutil: minimal stub ---
cat > "$STUB_DIR/diskutil" << 'EOF'
#!/bin/bash
# diskutil stub for Darling — no disk arbitration
case "${1:-}" in
    info)
        echo "   Device Identifier:         disk0"
        echo "   Device Node:               /dev/sda"
        echo "   Whole:                     Yes"
        echo "   Part of Whole:             disk0"
        echo "   Device / Media Name:       Block Device"
        ;;
    list)
        echo "disk0"
        ;;
    eject|mount|unmount|repairDisk|verifyDisk)
        exit 0
        ;;
    apfs)
        # apfs resizeContainer etc.
        shift
        case "${1:-}" in
            resizeContainer) exit 0 ;;
            *) exit 0 ;;
        esac
        ;;
    *)
        exit 0
        ;;
esac
exit 0
EOF
chmod +x "$STUB_DIR/diskutil"
echo "[OK] diskutil"

# --- osascript: no-op ---
cat > "$STUB_DIR/osascript" << 'EOF'
#!/bin/bash
# osascript stub for Darling — AppleScript not available
# brew may call osascript to query macOS info
echo ""
exit 0
EOF
chmod +x "$STUB_DIR/osascript"
echo "[OK] osascript"

# --- xcodebuild: no-op ---
cat > "$STUB_DIR/xcodebuild" << 'EOF'
#!/bin/bash
# xcodebuild stub for Darling — no Xcode
echo "xcode-select: error: tool 'xcodebuild' not found" >&2
exit 1
EOF
chmod +x "$STUB_DIR/xcodebuild"
echo "[OK] xcodebuild"

# --- xcrun: delegate or no-op ---
cat > "$STUB_DIR/xcrun" << 'EOF'
#!/bin/bash
# xcrun stub for Darling
while [ $# -gt 0 ]; do
    case "$1" in
        --find|-f)
            shift
            TOOL="$1"
            # Try to find the tool
            case "$TOOL" in
                cc|clang|clang++)
                    exec which cc 2>/dev/null || exec which clang 2>/dev/null || exit 1
                    ;;
                metal)
                    echo "/usr/local/bin/metal" 2>/dev/null || exit 1
                    ;;
                *)
                    exec which "$TOOL" 2>/dev/null || exit 1
                    ;;
            esac
            ;;
        --log-path)
            shift  # skip log path
            ;;
        --no-cache)
            shift
            ;;
        *)
            shift
            ;;
    esac
done
exit 1
EOF
chmod +x "$STUB_DIR/xcrun"
echo "[OK] xcrun"

# --- xcode-select: set to Darling CLT path ---
rm -f "$STUB_DIR/xcode-select" 2>/dev/null || true
cat > "$STUB_DIR/xcode-select" << 'EOF'
#!/bin/bash
# xcode-select stub for Darling — report CommandLineTools location
CLT_PATH="/Library/Developer/CommandLineTools"
DARLING_CLT="/Library/Developer/DarlingCLT"

case "${1:--print-path}" in
    -p|--print-path)
        # Check if CommandLineTools exists in the overlay
        if [ -d "$CLT_PATH" ]; then
            echo "$CLT_PATH"
        elif [ -d "$DARLING_CLT" ]; then
            echo "$DARLING_CLT"
        else
            echo "/Library/Developer/CommandLineTools"
        fi
        ;;
    -v|--version)
        echo "xcode-select version 2384."
        ;;
    -s|--switch)
        # Accept silently — we don't have multiple Xcodes
        exit 0
        ;;
    *)
        echo "Usage: xcode-select [-p|-v|-s <path>]" >&2
        exit 1
        ;;
esac
exit 0
EOF
chmod +x "$STUB_DIR/xcode-select"
echo "[OK] xcode-select"

# --- stat: improved macOS-compatible stat wrapper ---
cat > "$STUB_DIR/stat" << 'EOF'
#!/bin/bash
# stat wrapper for Darling — translate macOS stat flags to Linux stat
# brew uses: stat -f '%Su' (format strings) and stat -f '%z' etc.

OUTPUT_FMT=""
FILE=""
FMT=""

while [ $# -gt 0 ]; do
    case "$1" in
        -f)
            shift
            FMT="$1"
            shift
            ;;
        -L)
            shift  # Follow symlinks
            ;;
        -s)
            shift  # Silent mode
            ;;
        -t)
            shift  # Terse output
            ;;
        -*)
            shift
            ;;
        *)
            if [ -z "$FILE" ]; then
                FILE="$1"
            fi
            shift
            ;;
    esac
done

if [ -z "$FILE" ]; then
    exec /usr/bin/stat "$@"
fi

if [ -n "$FMT" ]; then
    # Translate macOS format specifiers to Linux
    # Common brew format: '%Su' (user), '%Sp' (permissions), '%z' (size), '%Sm' (mtime)
    LINUX_FMT="$FMT"
    LINUX_FMT="${LINUX_FMT//%Su/%U}"    # owner name
    LINUX_FMT="${LINUX_FMT//%Su/%U}"    # owner name
    LINUX_FMT="${LINUX_FMT//%Sp/%A}"    # permissions
    LINUX_FMT="${LINUX_FMT//%z/%s}"     # size
    LINUX_FMT="${LINUX_FMT//%Sm/%y}"    # mtime
    LINUX_FMT="${LINUX_FMT//%Sm/%y}"    # mtime
    LINUX_FMT="${LINUX_FMT//%SB/%y}"    # mtime
    LINUX_FMT="${LINUX_FMT//%SH/%Y}"    # birth time -> use mtime as fallback
    LINUX_FMT="${LINUX_FMT//%Sc/%y}"    # ctime
    LINUX_FMT="${LINUX_FMT//%Sg/%G}"    # group name
    LINUX_FMT="${LINUX_FMT//%Si/%i}"    # inode
    LINUX_FMT="${LINUX_FMT//%Nl/%h}"    # hard links
    LINUX_FMT="${LINUX_FMT//%d/%d}"     # device (st_dev)
    LINUX_FMT="${LINUX_FMT//%D/%d}"     # device
    LINUX_FMT="${LINUX_FMT//%i/%i}"     # inode
    LINUX_FMT="${LINUX_FMT//%p/%A}"     # permissions
    LINUX_FMT="${LINUX_FMT//%l/%h}"     # links
    LINUX_FMT="${LINUX_FMT//%a/%a}"     # access time

    # Use printf-style format with Linux stat
    exec /usr/bin/stat -c "$LINUX_FMT" "$FILE" 2>/dev/null || exec /usr/bin/stat "$FILE"
fi

# Default: just pass through to Linux stat
exec /usr/bin/stat "$FILE"
EOF
chmod +x "$STUB_DIR/stat"
echo "[OK] stat"

# --- xattr backup for /usr/sbin ---
mkdir -p "${HOME}/usr/sbin" 2>/dev/null || true
cat > "${HOME}/usr/sbin/xattr" << 'EOF'
#!/bin/bash
exec /usr/bin/xattr "$@"
EOF
chmod +x "${HOME}/usr/sbin/xattr" 2>/dev/null || true

echo ""
echo "=== All stubs installed to $STUB_DIR ==="
echo "Restart darling shell to pick up changes."
