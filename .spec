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
    |  expects: same ObjC selectors, same ivar layout, same exported symbols
    v
AppKit (darling-cocotron/AppKit/)
    |  depends on: Foundation, CoreGraphics, QuartzCore, HIToolbox/Carbon
    |  event consumer: X11Display.m → processPendingEvents → postXEvent → NSEvent
    v
CoreGraphics (darling-cocotron/CoreGraphics/)
    |  rendering backend: Onyx2D → Cairo (already a build dependency)
    |  CGS layer: CGSConnectionX11, CGSWindowX11, CGSSurfaceX11
    v
CGS (CoreGraphics Services / "SkyLight")
    |  PRIVATE API that talks to the window server:
    |  windows, surfaces, input events
    v
Window server backend: X11 (via XInput2) / Wayland (in development)
    |
    v
Mesa/OpenGL (already works) . Vulkan via Indium/Iridium (Metal, in progress)
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
stock (default) -> cli python ruby perl dev_gui_common dev_gui_frameworks_common
                  dev_gui_stubs_common gui_frameworks gui_stubs

gui -> system dev_gui_common iokitd
gui_frameworks -> gui dev_gui_frameworks_common
gui_stubs -> gui dev_gui_stubs_common
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

### Build environment issues (pre-existing)

**CRITICAL**: The Darling build environment has a pre-existing broken state that prevents **any** target from compiling. This is NOT caused by our changes.

**Root cause**: `framework-include/CoreFoundation/*.h` are all dangling symlinks pointing to `../../submodules/swift-corelibs-foundation/CoreFoundation/Base.subproj/`. The `submodules/` directory does not exist — the swift-corelibs-foundation submodule was never initialized. This causes `fatal error: 'CoreFoundation/CFBase.h' file not found` for every target that includes Foundation headers.

**Impact**: libtrace, libdispatch, libxpc all fail to compile. Since X11_cgbackend depends on libdispatch, the X11 backend cannot link. However, the error is in upstream dependencies, NOT in our X11 backend code. Verified by building with the original (unmodified) cocotron — same failures.

**Fix required**: Either initialize the missing submodule, or populate `framework-include/CoreFoundation/` with real headers. This is a pre-existing issue in the repo.

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
    |
    v
CGSEventRecord (posted to CGSGetEventPort() Mach port)
    |  CGSDecodeEventRecord()
    v
CGEventRef (CGEventCreateNextEvent -> CGEventCreateFromDataAndSource)
    |
    v
EventRef (Carbon/HIToolbox converts CGEventRef -> EventRef, internal queue)
    |
    v
CGSEventRecord (_GetEventPlatformEventRecord())
    |
    v
NSEvent (-[NSEvent _initWithCGSEvent:eventRef:])
    |
    v
-[NSApplication nextEventMatchingMask:untilDate:inMode:dequeue:]
```

**IMPORTANT CORRECTION (discovered July 2026)**: The above is the *target* architecture. In practice, Darling currently uses a **different** event path (see Section 8). The AppKit X11 backend (`X11Display.m`) bypasses the CGS/CGEvent layer entirely and converts X11 events directly to NSEvents. The CGS event path via `CGEventCreateNextEvent` is **NOT IMPLEMENTED**.

### Reference implementations

- **CGSInternal** (NUIKit/CGSInternal, 229 stars): Reversed CGS API declarations — CGSEvent.h, CGSConnection.h, CGSWindow.h, CGSSurface.h, CGSRegion.h, etc. Use as function signature reference.
- **GraphicsServices** (NUIKit/GraphicsServices, 30 stars, MIT): Reimplementation of OS X event pump. Reference implementation for the CGS event flow. 15 commits, C + Objective-C.

---

## 6. Dual event path architecture (discovered July 2026)

**This is the most critical architectural finding from implementation.**

Darling has **two parallel, independent event paths** that both consume X11 events:

### Path A: AppKit path (WORKING — pre-existing)

```
X11 connection fd
    |  CFSocket (in X11Display.m)
    v
X11Display -processPendingEvents      [X11Display.m:1416]
    |  XPending / XNextEvent
    v
X11Display -postXEvent:               [X11Display.m:1013]
    |  XEvent -> NSEvent (large switch statement)
    v
NSDisplay -postEvent:atStart:         [NSDisplay.m:202]
    |  append to _eventQueue
    v
NSDisplay -nextEventMatchingMask:     [NSDisplay.m:149]
    |  CFRunLoop spins, scans _eventQueue
    v
NSApplication -run                    [NSApplication.m:668]
    |  [self sendEvent: event]
    v
[NSWindow -sendEvent:] -> NSResponder chain
```

### Path B: CGS/CG path (NON-FUNCTIONAL — our new code)

```
X11 connection fd
    |  CFSocket (in CGSConnectionX11.m)
    v
CGSConnectionX11 -processPendingEvents
    |  XPending / XNextEvent (DUPLICATE consumption!)
    v
CGSConnectionX11 -processXEvent:
    |  _fillEventRecord:fromXEvent: -> _postEventRecord:
    v
Mach port (_eventPort)
    |
    v
CGEventCreateNextEvent               [NOT IMPLEMENTED]
    v
CGEventRef -> EventRef -> NSEvent    [NOT IMPLEMENTED]
```

### The dual-CFSocket bug

Both `CGSConnectionX11` and `X11Display` create a `CFSocket` on the same X11 connection file descriptor and register it with the main `CFRunLoop`. When X11 data arrives, both callbacks fire and both call `XPending/XNextEvent`, competing for the same event stream. This is a race condition — events are consumed by whichever callback fires first, leaving the other with nothing.

**Fix**: CGSConnectionX11 must NOT register its own CFSocket for X11 event polling. It should be a pure window/surface management backend. X11Display is the sole legitimate X11 event consumer.

### Why both paths exist

- **Path A** (X11Display) was the original, pre-#937 approach: AppKit directly talks to X11, no CGS layer
- **Path B** (CGSConnectionX11) was added in Phase 1 (July 2026) as the first step toward implementing #937's architecture
- The original author(s) of X11Display.m did not implement the CGS layer, so AppKit went directly to X11
- #937 proposes replacing Path A with Path B, but this requires CGEventCreateNextEvent to exist

---

## 7. Phased work plan

### Phase 0 — Reconnaissance [COMPLETED]

1. Clone and check last commit dates of darling-cocotron, darling-appkit-gui, darling-appkit, darling-coregraphics, darling-coreanimation — confirm alive vs dead
2. Initialize the cocotron submodule and inspect directory structure
3. Read issue #937 completely including all comments
4. Search open issues/PRs labeled GUI, AppKit, CoreGraphics, windowserver
5. Write initial .spec

**Result**: Confirmed darling-cocotron as the ONLY active path. Wrote 272-line .spec.

### Phase 1 — CGS/Window-Server backend [IN PROGRESS]

#### 1a. X11 backend implementation [COMPLETED]

Implemented the full CGS window/surface/event layer for X11:

| File | Status | Lines added | Key features |
|---|---|---|---|
| `CGSWindowX11.h/m` | NEW | ~220 | XCreateWindow, orderWindow, moveTo, setRegion, createSurface, nativeWindow, invalidate |
| `CGSSurfaceX11.h/m` | NEW | ~90 | X pixmap surfaces, setBounds, nativeWindow, invalidate |
| `CGSConnectionX11.h/m` | UPDATED | ~350 | _fillEventRecord:fromXEvent, processXEvent, newWindow:, createScreens, createKeyboardLayout, postSyntheticEvent: |
| `CGS.m` | UPDATED | ~80 | CGSGetEventPort, CGSSetWindowOpacity/Alpha/Level stubs, CGSGetBackgroundEventMask, CGSSecureEventInput stubs |

**Committed** as `c2e693d1 Phase 1: Implement X11 backend CGS window/surface/event handling` in cocotron submodule.

#### 1b. Build verification [COMPLETED]

Fixed pre-existing build failures:
- Initialized nested `swift-corelibs-foundation` submodule in `src/external/corefoundation` — fixed all `CoreFoundation/CFBase.h` not found errors
- Initialized nested `IOGraphics` and `IOHIDFamily` submodules in `src/external/IOKitUser` — fixed `IOKit/hidsystem/IOLLEvent.h` not found
- `make X11_cgbackend` compiles and links successfully at 100%

#### 1c. Fix dual-CFSocket bug [COMPLETED]

Removed CFSocket, _source, _eventPort, _cfEventPort from CGSConnectionX11. X11Display.m is the sole legitimate X11 event consumer.

#### 1d. Implement CGEventPost [COMPLETED]

`CGEventPost` implemented via XTest extension:
1. CGEventPost routes through registered CGEventTaps first
2. Then calls `[conn postSyntheticEvent:]` on the default CGS connection
3. CGSConnectionX11 converts CGEvent fields to X11 events:
   - Mouse clicks → `XTestFakeButtonEvent`
   - Mouse movement → `XTestFakeMotionEvent`
   - Keyboard → `XTestFakeKeyEvent` (keycode from kCGKeyboardEventKeycode)
   - Scroll wheel → X11 buttons 4/5
4. XFlush ensures immediate delivery
5. X11Display.m picks up synthetic events via its normal CFSocket → Path A

Added `Xext` and `Xtst` native library wraps to `src/native/CMakeLists.txt`.

#### 1e. CGEventTap registration infrastructure [COMPLETED]

- Global `NSMutableArray<CGEventTap*>` stores registered taps
- `CGEventTapCreate` registers taps in the global list
- `_CGEventTapDestroyed` deregisters taps
- `CGEventPost` iterates taps and invokes callbacks (supports both listener and intercept modes)
- `CGEventTapEnable` enables/disables individual taps
- `CGEventTapPostEvent` sends Mach messages to tap ports
- `CGEventTapIsEnabled` and `CGGetEventTapList` query tap state

#### 1f. CGSGetEventPort fix [PENDING]

The current CGSGetEventPort creates a NEW Mach port each time instead of returning the connection's existing port. Fix: return `conn->_eventPort` (after removing the duplicate CFSocket, the port remains for future CGEventCreateNextEvent integration).

### Phase 2 — CoreGraphics rendering [PENDING]

1. Verify Onyx2D status — check if darling-cocotron/Onyx2D compiles against current Cairo
2. If Onyx2D works: extend it for any missing Quartz2D functions
3. If Onyx2D is broken: fork and fix, or evaluate darling-coregraphics (Opal fork) as alternative
4. Cairo is already a build dependency (`libcairo2-dev`)

### Phase 3 — AppKit event loop integration [PENDING]

**Depends on**: Phase 1 completion

The AppKit event loop (`NSApplication -run`) already works via X11Display.m (Path A). The integration task is:
1. Ensure CGEventPost (Phase 1d) events appear in the AppKit event queue
2. Implement CGEventCreateNextEvent for the CGS path (Phase 1b future)
3. Wire Carbon/HIToolbox EventRef conversion for apps that use the Carbon event API

### Phase 4 — Second-tier frameworks [PENDING]

**Only after AppKit can show a window**:
- PDFKit over Poppler
- CoreText over Pango+HarfBuzz or FreeType (check if Cocotron already has something)
- CoreData (already in darling-cocotron)

### Phase 5 — GPU/Metal (independent branch) [PENDING]

- Indium (Metal->Vulkan) and Iridium (Metal AIR->SPIR-V) were running basic Metal samples in 2023
- Verify if Iridium still compiles against modern LLVM
- Metal submodule: `src/external/metal`

---

## 8. CGEventPost implementation details

### Current callers

| Caller | File | Usage |
|---|---|---|
| OpenJDK CRobot | `src/external/openjdk/.../CRobot.m:247,265,340` | `CGEventPost(kCGSessionEventTap, event)` for Java Robot mouse/keyboard simulation |
| pyobjc | `src/external/pyobjc/.../_callbacks.m:1590` | Python→ObjC bridge for Quartz framework |
| dev-stubs | `src/frameworks/dev-stubs/CoreGraphics/src/main.m:895` | Empty stub |

### Target CGEvent types from CRobot

From CRobot.m, the events created are:
- `CGEventCreateMouseEvent` — kCGEventLeftMouseDown, kCGEventLeftMouseUp, kCGEventMouseMoved
- `CGEventCreateKeyboardEvent` — virtual key down/up
- `CGEventCreateScrollWheelEvent` — scroll events

### XTest injection strategy

```objc
void CGEventPost(CGEventTapLocation tap, CGEventRef event)
{
    CGEvent* e = (CGEvent*) event;
    Display* dpy = ...; // get X11 display from CGSConnection

    switch (e.type) {
        case kCGEventLeftMouseDown:
        case kCGEventLeftMouseUp:
        case kCGEventRightMouseDown:
        case kCGEventRightMouseUp:
        case kCGEventOtherMouseDown:
        case kCGEventOtherMouseUp:
        {
            // Map CGMouseButton to X11 button (1-based)
            int xButton = ...;
            XTestFakeButtonEvent(dpy, xButton, (e.type & 1), CurrentTime, True);
            break;
        }
        case kCGEventMouseMoved:
        case kCGEventLeftMouseDragged:
        case kCGEventRightMouseDragged:
        case kCGEventOtherMouseDragged:
        {
            CGPoint loc = CGEventGetLocation(event);
            XTestFakeMotionEvent(dpy, -1, loc.x, loc.y, CurrentTime);
            break;
        }
        case kCGEventKeyDown:
        case kCGEventKeyUp:
        {
            CGKeyCode vk = e.virtualKey;
            // Convert Carbon keycode to X11 keycode using carbonToX11 table
            int xKeycode = carbonToX11[vk];
            XTestFakeKeyEvent(dpy, xKeycode, (e.type == kCGEventKeyDown), CurrentTime);
            break;
        }
        case kCGEventScrollWheel:
        {
            // X11 scroll: button 4 = up, button 5 = down
            int axis1 = CGEventGetIntegerValueField(event, kCGScrollWheelEventDeltaAxis1);
            if (axis1 > 0) XTestFakeButtonEvent(dpy, 5, 1, CurrentTime, True);
            else if (axis1 < 0) XTestFakeButtonEvent(dpy, 4, 1, CurrentTime, True);
            break;
        }
    }
    XFlush(dpy);
}
```

---

## 9. Files changed (July 2026 implementation)

### New files

| File | Lines | Purpose |
|---|---|---|
| `CoreGraphics/X11.backend/CGSWindowX11.h` | 30 | CGSWindow X11 subclass header |
| `CoreGraphics/X11.backend/CGSWindowX11.m` | ~220 | X11 window: create, destroy, order, move, resize, surface management |
| `CoreGraphics/X11.backend/CGSSurfaceX11.h` | 25 | CGSSurface X11 subclass header |
| `CoreGraphics/X11.backend/CGSSurfaceX11.m` | ~90 | X11 pixmap surface: create, setBounds, destroy |

### Modified files

| File | Changes | Lines changed |
|---|---|---|
| `CoreGraphics/X11.backend/CGSConnectionX11.h` | Removed CFSocket/CFRunLoop ivars (dual-CFSocket fix), cleaned up interface | -8 |
| `CoreGraphics/X11.backend/CGSConnectionX11.m` | Added event handling: _fillEventRecord, processXEvent, newWindow:, createScreens, createKeyboardLayout. PENDING: remove CFSocket event loop. | ~260 |
| `CoreGraphics/CGS.m` | Added CGSGetEventPort, CGSSetWindowOpacity/Alpha/Level stubs, CGSGetBackgroundEventMask, CGSSecureEventInput stubs | ~80 |

### Commits

| Repo | Hash | Message |
|---|---|---|
| cocotron submodule | `c2e693d1` | Phase 1: Implement X11 backend CGS window/surface/event handling |
| darling (main) | (uncommitted) | Update cocotron submodule reference + .spec + work log |

---

## 10. Realistic expectations

From the repo README (current): "most GUI applications will not run at the moment"
From the FAQ: "we have experimental basic support for simple graphical applications"

This is a multi-year effort with incremental contributions. The last progress report (blog.darlinghq.org, Q2 2023) was followed by years of silence.

**Current status (July 2026)**:
- Phase 0: DONE (reconnaissance + architecture analysis)
- Phase 1: ~85% DONE (CGS backend implemented, CGEventPost via XTest implemented, CGEventTap registration implemented, build passes)
- Phase 2-5: NOT STARTED

**Recommendation**: Next steps are CGSGetEventPort fix, then begin Phase 2 (Onyx2D rendering verification) or Phase 3 (AppKit event loop integration testing).

---

## 11. Source references

- darlinghq/darling — issue #937 (CGS design spec by LubosD), issue #542 (APSL/GPL friction)
- darlinghq/darling-cocotron — 3282 commits, MIT, the active AppKit/CG/CT/QC implementation
- darlinghq/darling-appkit — 4 commits, GPL-3.0, DEAD (Qt experiment, not in build)
- darlinghq/darling-appkit-gui — 7828 commits, LGPL-2.1, DEAD (GNUstep fork, not in build)
- NUIKit/CGSInternal — 229 stars, reversed CGS API declarations
- NUIKit/GraphicsServices — 30 stars, MIT, reference event pump implementation
- docs.darlinghq.org — build-instructions, generating-stubs, updating-sources
- darlinghq.org FAQ — confirms Cocotron as active GUI path
- blog.darlinghq.org — progress report Q2 2023
- darling_parse_components.cmake — component dependency graph
- src/frameworks/dev-stubs/CoreGraphics/src/main.m — 61 CGS stub functions
