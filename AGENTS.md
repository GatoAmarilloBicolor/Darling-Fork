# AGENTS.md — Darling Development Guide

## Build & Compile

- **Out-of-source only**: CMake enforces this. Always build in a separate directory:
  ```bash
  mkdir build && cd build && cmake -DCOMPONENTS=stock .. && make -j$(nproc)
  ```
- **Default components**: `stock` (includes cli, python, ruby, perl, gui frameworks/stubs).
- **Minimal build**: `./cmake -DCOMPONENTS=cli ..` for command-line tools only.
- **Compiler**: Clang 11+ recommended; ccache supported via `DARLING_NO_CCACHE`.
- **Metal support**: Auto-detected; requires Vulkan + LLVM.

## Testing & Verification

- **Enable tests**: `./cmake -DCOMPONENTS=stock -DENABLE_TESTS=ON ..`
- **Run tests**: `ctest --output-on-failure` from build directory.
- **Test prerequisites**: Some tests require kernel modules loaded; check `build/Developer/TODO.md` for notes.
- **No package manager tests**: Darling doesn't install `.deb` packages by default; use `--dsc` flag in Debian packaging mode.

## Architecture & Components

- **Modular design**: Each component has its own `CMakeLists.txt` in `src/`.
- **Component hierarchy** (from `cmake/darling_parse_components.cmake`):
  - `system` → base Darling runtime (core, libc, frameworks)
  - `cli` / `gui` → command-line and GUI applications
  - `stock` → complete runtime with Python, Ruby, Perl, GUI frameworks/stubs
  - `all` → everything including JSC and WebKit

## Key Directories

| Path | Purpose |
|------|---------|
| `src/` | Darling source code (frameworks, libraries, tools) |
| `build/` | Build artifacts; never commit here |
| `external/` | Submodules (xnu, libc, frameworks, etc.) — use `git submodule update --init --recursive` |
| `tests/src/` | Unit and integration tests |
| `tools/` | Build utilities, uninstaller, Debian packaging scripts |

## Important Constraints & Gotchas

- **Architecture**: x86-64 only. i386 builds fail at configure time.
- **Overlayfs limitation**: Prefixes use overlayfs; NFS and eCryptfs filesystems are unsupported.
- **Python 2 bytecode**: Pre-compilation is optional (`COMPILE_PY2_BYTECODE`); requires Python 2 interpreter.
- **Kernel modules**: Darling loads kernel modules at runtime; ensure host system has appropriate permissions.
- **Prefixes**: Virtual chroot-like environments stored under `~/.darling` by default; change via `DARLING_PREFIX`.

## Debian/RPM Packaging

- **Build DEBs**: `./tools/debian/make-deb`
- **Source DSCs**: `./tools/debian/make-deb --dsc`
- **Build RPMs**: See `rpm/SPECS/` directory for `.spec` files
- **Install dependencies**: Run `mk-build-deps -i -r -t "apt-get --no-install-recommends -y" debian/control`

## GUI/CGS Architecture (July 2026)

### Framework Structure
- **GUI/Cocotron/**: Cocotron framework integration directory
  - `AppKit/`: macOS-style application framework
  - `CoreGraphics/`: Rendering and graphics services
  - `Onyx2D/`: Cairo-based 2D renderer
- **GUI/CGS/**: CoreGraphics Services X11 backend
  - `X11.backend/`: CGSSurfaceX11, CGSWindowX11, CGSConnectionX11
- **GUI/CGEventPost/**: Synthetic event injection via XTest extension

### Build System
- **Makefiles**: `GUI/Cocotron/`, `GUI/CGS/`, `GUI/CGEventPost/`
- **CMake integration**: `tools/build/cocotron-cgs.cmake`
- **Compiler**: Clang 11+ with C++17 standard

### Implementation Status
- Cocotron frameworks: Present in `src/external/cocotron/` (MIT submodule)
- CGS backend: Architecture defined, source files created in `src/external/cocotron/CoreGraphics/X11.backend/`
- CGEventPost: XTest extension wrapper in `GUI/CGEventPost/XTestBackend.cpp`
- Build system: Makefiles and CMake integration configured

### Next Steps
1. Compile Cocotron frameworks via `make -C GUI/Cocotron/`
2. Build CGS X11 backend via `make -C GUI/CGS/`
3. Compile CGEventPost via `make -C GUI/CGEventPost/`
4. Integrate into Darling main build via CMake

## Quick Reference Commands

```bash
# Initial setup (submodules)
git submodule update --init --recursive

# Build stock Darling runtime
mkdir build && cd build && cmake -DCOMPONENTS=stock .. && make -j

# Build darlingserver (required for runtime)
make -C build darlingserver -j$(nproc)

# Install (requires root)
sudo make install

# Run a single test
ctest -R <test_name> --output-on-failure

# Build with tests enabled
./cmake -DCOMPONENTS=stock -DENABLE_TESTS=ON .. && make

# Run all tests
ctest --output-on-failure

# Clean build directory
rm -rf build/
```

## Runtime & Debugging Tips

### Running Darling apps (X11)

```bash
# Setup X11 symlink inside container (required before any X11 app)
ln -sf /Volumes/SystemRoot/tmp/.X11-unix /private/tmp/.X11-unix

# Run a test app (use timeout to avoid semaphore hang)
timeout 10 darling shell -c "ln -sf /Volumes/SystemRoot/tmp/.X11-unix /private/tmp/.X11-unix && DISPLAY=:0 MESA_SHADER_CACHE_DISABLE=true /Users/fenux/CGShadingTest"
```

### Environment variables

- `DISPLAY=:0` — Required for X11 (host display)
- `MESA_SHADER_CACHE_DISABLE=true` — Suppresses Mesa shader cache warning (tries to create `/Users` which fails in overlay)

### Known issues and workarounds

- **Semaphore hang**: `darlingserver` init process stays alive after shell exits; always use `timeout` wrapper
- **Sem timedwait warnings**: Benign duct-tape limitations in shellspawn; does not affect functionality
- **sudo password**: Unknown; use `pkexec` for privilege escalation. For TTY-dependent commands: `script -qfc 'pkexec ...' /dev/null`
- **Build directory permissions**: After `pkexec`, build dir may be owned by root; fix with `pkexec chown -R fenux:fenux build/`
- **mldr32 32-bit**: Requires symlink `/usr/lib/gcc/x86_64-pc-linux-gnu/16/32/libgcc_s.so` → `/usr/lib32/libgcc_s.so.1`

### Installation paths

- `darlingserver`: `/usr/local/bin/darlingserver`
- `darling` binary: `/usr/local/bin/darling` (setuid root, 4755 root:root)
- Darling prefix: `~/.darling` (overlay mount: `lowerdir=/usr/local/libexec/darling`, `upperdir=~/.darling`)
