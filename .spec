# Darling GUI Support — Technical Specification

**Research date**: July 2026
**Sources**: darlinghq/darling repo (live clone), ~15 satellite repos, issue #937, NUIKit/CGSInternal, NUIKit/GraphicsServices, darling_parse_components.cmake, dev-stubs/CoreGraphics

---

## 0. Corrections to prior analysis (DeepWiki)

DeepWiki indexed only `darlinghq/darling` and read `src/frameworks/CMakeLists.txt`. It concluded "most GUI frameworks are stubs" and proposed creating Cairo/Poppler/Pango/GNUstep wrappers from scratch.

**What already exists (confirmed via live repo inspection):**

| What DeepWiki proposed creating | Exists as repo | Actual state in build |
|---|---|---|
| GNUstep AppKit/Foundation | darling-appkit-gui (fork of gnustep/libs-gui, 7828 commits, LGPL-2.1) | **NOT wired into build** — not in .gitmodules. Abandoned. |
| CoreGraphics over Cairo | darling-cocotron contains Onyx2D (Cairo backend, "O2") | **ACTIVE** — the only path, via src/external/cocotron |
| Cocotron for AppKit | darling-cocotron (3282 commits, MIT) | **ACTIVE** — the ONLY AppKit in the build |
| QuartzCore | inside darling-cocotron | **ACTIVE** — built by cocotron submodule |
| Qt-based AppKit | darling-appkit (4 commits, GPL-3.0) | **DEAD** — removed from .gitmodules. Contains QWindowSubclass.mm, QNSEventDispatcher.cpp (Qt experiment). Not wired in. |
| Foundation | src/external/foundation (separate submodule) | **ACTIVE** — not a "mix of three origins" |

**Consequence**: The spec "clone GNUstep and write wrappers" would recreate abandoned work. The only active path is **darling-cocotron** (MIT license, the path the FAQ official points to).

---

## 1. Real graphics stack architecture

```
Application .app (Mach-O binary, compiled for Apple ABI)
    │  expects: same ObjC selectors, same ivar layout, same exported symbols
    ▼
AppKit (darling-cocotron/AppKit/)
    │  depends on: Foundation, CoreGraphics, QuartzCore, HIToolbox/Carbon
    ▼
CoreGraphics (darling-cocotron/CoreGraphics/)
    │  rendering backend: Onyx2D → Cairo (already a build dependency)
    ▼
CGS (CoreGraphics Services / "SkyLight")
    │  PRIVATE API that talks to the window server:
    │  windows, surfaces, input events
    │  THIS IS THE MISSING LINK — no implementation exists
    ▼
Window server backend: X11 (via XInput2) / Wayland (in development)
    │
    ▼
Mesa/OpenGL (already works) · Vulkan via Indium/Iridium (Metal, in progress)
```

**Key insight**: The bottleneck is not the Objective-C frameworks themselves but the CGS/window-server layer that connects them to X11/Wayland. Without this layer, even a 100%-complete AppKit cannot paint a single pixel.

---

## 2. ABI compatibility constraint (not just API)

Darling executes pre-compiled Apple binaries. These depend on:

- **Same ObjC symbol names** with same ivar layout (`-[NSView drawRect:]`, etc.)
- **Same struct sizes** in public headers (`NSRect`, `NSPoint` must match Apple's memory layout)
- **Same runtime behavior** — Darling uses libobjc2/runtime; verify compatibility with Apple's runtime semantics for blocks, @synchronized, exceptions
- **Stub generator** (`darling-stub-gen` + `class-dump`) extracts exact Apple signatures from real Mac binaries before any implementation. Documented at docs.darlinghq.org/contributing/generating-stubs

**Rule**: Cannot "eyeball" an AppKit implementation from public Apple docs. Must start from generated stubs or existing Cocotron code, and validate against real binaries.

---

## 3. Licensing matrix

| Component | License | Notes |
|---|---|---|
| darling (global) | GPLv3 | umbrella license |
| Darwin/XNU Apple components | APSL 2.0 | FSF considers APSL 2.0 incompatible with GPL; friction documented in issue #542. Don't reopen unless necessary. |
| darling-cocotron | MIT | **lowest legal friction** |
| GNUstep (gui, base, Opal, QuartzCore) | LGPL 2.1+ | allows dynamic linking with proprietary apps |
| Cairo | LGPL 2.1 / MPL 1.1 (dual) | already an official build dependency |
| Poppler (PDFKit) | GPL | compatible with GPLv3 global |

**Conclusion**: For AppKit/Foundation/CoreGraphics, Cocotron (MIT) is the path of least legal friction AND the officially active path.

---

## 4. Build system and component model

### Component hierarchy (from darling_parse_components.cmake)

```
stock (default) → cli python ruby perl dev_gui_common dev_gui_frameworks_common
                  dev_gui_stubs_common gui_frameworks gui_stubs

gui → system dev_gui_common iokitd
gui_frameworks → gui dev_gui_frameworks_common
gui_stubs → gui dev_gui_stubs_common
```

When `COMPONENT_gui` is ON:
- `src/external/cocotron` is built (AppKit, CoreGraphics, CoreText, QuartzCore)
- `src/frameworks/OpenGL`, `src/frameworks/ImageIO` are built
- `dev-stubs/AppKit`, `dev-stubs/CoreGraphics`, etc. are NOT installed (replaced by real implementations)

When `COMPONENT_gui` is OFF:
- Only stubs from `src/frameworks/dev-stubs/` are installed

### Build commands

```bash
GIT_CLONE_PROTECTION_ACTIVE=false git clone --recursive https://github.com/darlinghq/darling.git
cd darling && mkdir build && cd build
cmake ..          # defaults to "stock" component (includes gui)
make -j$(nproc)
sudo make install
```

Requirements: Linux x86_64, kernel >=5.0, Clang >=11, >=4GB RAM, up to 16GB disk.

### CGS stubs already exist

`src/frameworks/dev-stubs/CoreGraphics/src/main.m` contains 61 CGS function stubs (all returning void/logging "STUB"). These are the symbols that must be implemented with real logic:

```
CGSMainConnectionID, CGSFindWindowAndOwner, CGSGetCurrentCursorLocation,
CGSCurrentInputPointerPosition, CGSGetDisplayList, CGSGetCurrentDisplayMode,
CGSCopyDisplayInfoDictionary, CGSRegisterNotifyProc, CGSRemoveNotifyProc,
CGSSetWindowTransformAtPlacement, CGSGetWindowTransformAtPlacement,
CGSSetWindowBackgroundBlurRadius, CGSSetGlobalHotKeyOperatingMode,
CGSGetGlobalHotKeyOperatingMode, CGSGetSymbolicHotKeyValuesAndStates,
CGSInputButtonState, CGSAcceleratorForDisplayNumber, CGSDisplayStatusQuery,
CGSServerOperationState, CGSSetDenyWindowServerConnections,
CGSSessionCopyAllSessionProperties, CGSSessionReleaseSessionID, ...
```

---

## 5. Issue #937 — Official design spec (LubosD, Feb 2021)

**Status**: Open, no assignee, no linked branches. Zero implementation since written.

### Architecture decisions from #937

1. **AppKit must call CGS* APIs** — backends from `cocotron/AppKit/*.backend` must be removed
2. **New backends go in `cocotron/CoreGraphics/*.backend`** implementing CGS interfaces
3. **X11 backend must use XInput2** for input events

### Event lifecycle (from #937, with call stacks)

```
X11/Wayland event
    │
    ▼
CGSEventRecord (posted to CGSGetEventPort() Mach port)
    │  CGSDecodeEventRecord()
    ▼
CGEventRef (CGEventCreateNextEvent → CGEventCreateFromDataAndSource)
    │
    ▼
EventRef (Carbon/HIToolbox converts CGEventRef → EventRef, internal queue)
    │
    ▼
CGSEventRecord (_GetEventPlatformEventRecord())
    │
    ▼
NSEvent (-[NSEvent _initWithCGSEvent:eventRef:])
    │
    ▼
-[NSApplication nextEventMatchingMask:untilDate:inMode:dequeue:]
```

### Reference implementations

- **CGSInternal** (NUIKit/CGSInternal, 229★): Reversed CGS API declarations — CGSEvent.h, CGSConnection.h, CGSWindow.h, CGSSurface.h, CGSRegion.h, etc. Use as function signature reference.
- **GraphicsServices** (NUIKit/GraphicsServices, 30★, MIT): Reimplementation of OS X event pump. Reference implementation for the CGS event flow. 15 commits, C + Objective-C.

---

## 6. Phased work plan

### Phase 0 — Reconnaissance (MANDATORY before any code)

1. **Clone and check last commit dates** of darling-cocotron, darling-appkit-gui, darling-appkit, darling-coregraphics, darling-coreanimation — confirm which are alive vs dead
2. **Initialize the cocotron submodule** and inspect its actual directory structure:
   ```bash
   git submodule update --init src/external/cocotron
   ls src/external/cocotron/AppKit/
   ls src/external/cocotron/CoreGraphics/
   ```
3. **Read issue #937 completely** including all comments from LubosD
4. **Search open issues/PRs** labeled GUI, AppKit, CoreGraphics, windowserver — avoid duplicating work in progress
5. **Open a Discussion** on GitHub or ask in Discord before large architectural work — small coordinated project with history of rejecting unaligned reinventions

### Phase 1 — CGS/Window-Server backend (the real prerequisite)

**Why first**: Without this, no window appears on screen regardless of AppKit completeness.

**ACTUAL STATE** (confirmed by live repo inspection):
- `cocotron/CoreGraphics/X11.backend/` already exists with:
  - `CGSConnectionX11.m` (381 lines): XOpenDisplay, CFSocket+CFRunLoop, XRandR, XKB keyboard layout — BUT `processXEvent:` has empty case bodies, no XInput2 (TODO comment), `newWindow:` is empty
  - `CGSWindowX11.m` (empty — just header + import)
  - `CGSSurfaceX11.m` (empty — just header + import)
  - `X11KeySymToUCS.m` (36KB, complete key mapping)
  - `CarbonKeys.h` (carbonToX11 key mapping table)
  - `CMakeLists.txt` (wired into build, depends on X11, XRandR, Xcursor, fontconfig, xkbfile)

1. **Study the CGS API surface** — read NUIKit/CGSInternal headers (CGSEvent.h, CGSConnection.h, CGSWindow.h, CGSSurface.h)
2. **Study the reference implementation** — read NUIKit/GraphicsServices (especially GraphicsServices/GSApp.c, the event port handling at line 92)
3. **Study existing Cocotron backends** — check what `cocotron/AppKit/*.backend` currently does (these are the ones #937 says to eliminate and replace)
4. **Implement CGSWindowX11** — XCreateWindow, XDestroyWindow, orderWindow, moveTo, setRegion, nativeWindow, createSurface
5. **Implement CGSSurfaceX11** — X composite surfaces, setBounds, nativeWindow
6. **Implement CGSConnectionX11 event handling** — fill CGSEventRecord from XEvent in processXEvent:, post to CGSGetEventPort() Mach port
7. **Implement CGSConnectionX11 newWindow:** — create X11 windows via CGSWindowX11
8. **Test**: Build cocotron, run the TextEditor example (`cocotron/examples/TextEditor/`), verify window appears and events flow

### Phase 2 — CoreGraphics rendering

1. **Verify Onyx2D status** — check if darling-cocotron/Onyx2D compiles against current Cairo. This is the existing Cairo backend, historically called "O2"
2. **If Onyx2D works**: extend it for any missing Quartz2D functions
3. **If Onyx2D is broken**: fork and fix, or evaluate darling-coregraphics (Opal fork) as alternative
4. **Cairo is already a build dependency** (`libcairo2-dev` in build instructions) — no packaging friction

### Phase 3 — AppKit/Foundation classes

**Depends on**: Phase 1 (events must flow) + Phase 2 (drawing must work)

1. **Continue on darling-cocotron** unless Phase 0 reveals a more advanced path
2. **Priority classes** (most apps touch these first):
   - NSApplication (message loop, event dispatch)
   - NSWindow (window lifecycle, CGS window mapping)
   - NSView (drawing, hit testing, event dispatch)
   - NSResponder (event chain)
   - NSEvent (event wrapping)
3. **Check existing partial implementations**: darling-appkit had NSApplication.mm, NSResponder.mm, NSWindow.mm, NSView.mm, NSEvent.mm — review before writing from scratch (even though darling-appkit is dead, the code might have useful patterns)
4. **Validate**: Run a real .app inside a DPREFIX (`~/.darling`) and compare behavior with macOS

### Phase 4 — Second-tier frameworks

**Only after AppKit can show a window** — most depend on AppKit:

- PDFKit over Poppler (correct idea from DeepWiki, but depends on AppKit per its own CMakeLists.txt — cannot do before Phase 3)
- CoreText over Pango+HarfBuzz or directly over FreeType (check if Cocotron already has something; don't reimplement before checking)
- CoreData (already in darling-cocotron)

### Phase 5 — GPU/Metal (independent branch)

- **Indium** (Metal→Vulkan) and **Iridium** (Metal AIR→SPIR-V shaders) were running basic Metal samples in 2023
- **Verify**: Does Iridium still compile against modern LLVM? Last public report said it was broken against LLVM 15
- If broken: self-contained high-value task to fix
- Metal submodule already exists: `src/external/metal`

---

## 7. Realistic expectations

From the repo README (current): "most GUI applications will not run at the moment"
From the FAQ: "we have experimental basic support for simple graphical applications"

This is a multi-year effort with incremental contributions. The last progress report (blog.darlinghq.org, Q2 2023) was followed by years of silence.

**Recommendation**: Take a single bounded task (e.g., implement one CGS event type in the X11 backend, or port one NSControl class) and validate by running a real .app in a DPREFIX.

---

## 8. Source references

- darlinghq/darling — issue #937 (CGS design spec by LubosD), issue #542 (APSL/GPL friction)
- darlinghq/darling-cocotron — 3282 commits, MIT, the active AppKit/CG/CT/QC implementation
- darlinghq/darling-appkit — 4 commits, GPL-3.0, DEAD (Qt experiment, not in build)
- darlinghq/darling-appkit-gui — 7828 commits, LGPL-2.1, DEAD (GNUstep fork, not in build)
- NUIKit/CGSInternal — 229★, reversed CGS API declarations
- NUIKit/GraphicsServices — 30★, MIT, reference event pump implementation
- docs.darlinghq.org — build-instructions, generating-stubs, updating-sources
- darlinghq.org FAQ — confirms Cocotron as active GUI path
- blog.darlinghq.org — progress report Q2 2023
- darling_parse_components.cmake — component dependency graph
- src/frameworks/dev-stubs/CoreGraphics/src/main.m — 61 CGS stub functions
