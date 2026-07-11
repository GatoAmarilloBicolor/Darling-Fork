# Darling GUI Implementation — Work Log

## Phase 0: Reconnaissance [COMPLETED]

### Findings
- **Active AppKit path**: Only `src/external/cocotron` (darling-cocotron, MIT, 3282 commits)
- **darling-appkit** (Qt-based): DEAD — 4 commits, removed from .gitmodules
- **darling-appkit-gui** (GNUstep fork): DEAD — 7828 commits, not wired into build
- **Foundation**: Separate submodule at `src/external/foundation`
- **Metal**: Separate submodule at `src/external/metal`
- **darlingserver**: IPC submodule at `src/external/darlingserver`

### X11 Backend Status (before changes)
- `CGSConnectionX11.m`: 381 lines, XOpenDisplay + CFSocket + XRandR + XKB
  - BUT: `processXEvent:` had empty case bodies
  - No XInput2 (TODO comment)
  - `newWindow:` was empty
- `CGSWindowX11.m`: Empty (just header + import)
- `CGSSurfaceX11.m`: Empty (just header + import)

---

## Phase 1: CGS/Window-Server Backend [IN PROGRESS]

### 1a. X11 Backend Implementation [COMPLETED]

Implemented the full CGS window/surface/event layer for X11.

#### Files created/modified

**CGSWindowX11.h/m** (NEW, ~220 lines):
- Header: Display*, Window, CGRect, isVisible ivars
- initWithRegion: — XCreateWindow with proper event masks
- orderWindow:relativeTo: — XRaiseWindow / XLowerWindow / XRestackWindows
- moveTo: — XMoveResizeWindow
- setRegion: — store region, resize
- nativeWindow — return X11 Window handle
- createSurface — create CGSSurfaceX11
- invalidate — XDestroyWindow cleanup
- setProperty:getProperty: — XStoreName / XFetchName (WM_NAME only)

**CGSSurfaceX11.h/m** (NEW, ~90 lines):
- Header: Display*, Window, CGRect, Pixmap ivars
- initWithWindow — associate with parent window
- setBounds — XCreatePixmap for new size
- nativeWindow — return Pixmap handle
- invalidate — XFreePixmap cleanup

**CGSConnectionX11.h/m** (UPDATED, ~260 lines added):
- Removed CFSocket/CFRunLoop ivars (dual-CFSocket fix, see 1c below)
- Added _cgsEventTypeForXEvent: — maps X11 events to CGSEventType constants
- Added _fillEventRecord:fromXEvent: — fills CGSEventRecord from XEvent (Key, Button, Motion, Enter, Focus, Configure)
- Added _postEventRecord: — sends Mach message to _eventPort
- Added processXEvent: — calls _fillEventRecord + _postEventRecord + handles XKB/RR extension events
- Added newWindow: — XCreateWindow + WM_DELETE_WINDOW protocol + CGSWindowX11 creation
- Added createScreens — XRandR screen enumeration
- Added createKeyboardLayout — XKB keyboard layout to UCKeyboardLayout

**CGS.m** (UPDATED, ~80 lines added):
- Added CGSGetEventPort — mach_port_allocate (placeholder, needs fix)
- Added CGSSetWindowOpacity/Alpha/Level stubs — return kCGSErrorSuccess
- Added CGSGetBackgroundEventMask/CGSSetBackgroundEventMask stubs
- Added CGSEventIsAppUnresponsive/CGSEventSetAppIsUnresponsiveNotificationTimeout stubs
- Added CGSIsSecureEventInputSet/CGSSetSecureEventInput stubs

#### Commits
- cocotron: `c2e693d1 Phase 1: Implement X11 backend CGS window/surface/event handling`
- darling main: submodule reference update

### 1b. Build Verification [COMPLETED — BLOCKED]

Attempted `make X11_cgbackend`. Result: FAILS on upstream dependencies.

**Root cause**: `framework-include/CoreFoundation/*.h` are all dangling symlinks pointing to `../../submodules/swift-corelibs-foundation/CoreFoundation/Base.subproj/`. The `submodules/` directory does not exist — swift-corelibs-foundation submodule was never initialized.

This causes `fatal error: 'CoreFoundation/CFBase.h' file not found` for every target that includes Foundation headers (libtrace, libdispatch, libxpc). X11_cgbackend depends on libdispatch, so it cannot link.

**Verified**: Built with original (unmodified) cocotron — identical failures. Our code is NOT the cause.

### 1c. Dual-CFSocket Bug Discovery [COMPLETED]

**Problem discovered**: Both `CGSConnectionX11` and `X11Display` (AppKit) create a CFSocket on the same X11 connection file descriptor and register it with the main CFRunLoop. When X11 data arrives, both callbacks fire and both call XPending/XNextEvent, competing for events. This is a race condition.

**Root cause**: Our Phase 1a implementation added a CFSocket to CGSConnectionX11 for event processing. But X11Display.m (pre-existing AppKit code) already has its own CFSocket on the same fd for the same purpose.

**Solution**: Remove CFSocket from CGSConnectionX11. X11Display is the legitimate X11 event consumer. CGSConnectionX11 should only provide window/surface management. The CGS event path (CGSEventRecord -> Mach port -> CGEventCreateNextEvent) remains for future use when the window server replacement is complete.

**Status**: Header already updated (CGSConnectionX11.h cleaned up). Implementation update pending.

### 1d. Two Parallel Event Paths [DISCOVERED]

**Path A (AppKit — WORKING, pre-existing)**:
```
X11 fd -> CFSocket -> X11Display.processPendingEvents -> postXEvent
       -> NSEvent -> NSDisplay._eventQueue -> NSApplication.run -> sendEvent
```

**Path B (CGS — NON-FUNCTIONAL)**:
```
X11 fd -> CFSocket -> CGSConnectionX11.processPendingEvents -> processXEvent
       -> _fillEventRecord -> _postEventRecord -> Mach port
       -> CGEventCreateNextEvent (NOT IMPLEMENTED)
```

**Key insight**: Path A already works for normal input events. Path B is the target architecture per issue #937, but CGEventCreateNextEvent does not exist yet.

**For Phase 1**: We don't need Path B to work yet. Path A delivers all input events. Path B is for the future window server replacement.

### 1e. CGEventPost Plan [PLANNED]

**Who calls CGEventPost**:
- OpenJDK CRobot.m: `CGEventPost(kCGSessionEventTap, event)` for Java Robot mouse/keyboard
- pyobjc: Python->ObjC bridge for Quartz framework

**Implementation strategy**: Use XTest extension to inject synthetic X11 events that flow through Path A (X11Display -> NSEvent -> NSApplication).

- `CGEventCreateMouseEvent` -> `XTestFakeButtonEvent` / `XTestFakeMotionEvent`
- `CGEventCreateKeyboardEvent` -> `XTestFakeKeyEvent`
- `CGEventCreateScrollWheelEvent` -> `XTestFakeButtonEvent` (button 4/5)

Key conversion tables already exist:
- `carbonToX11[]` in CarbonKeys.h: Carbon virtual key -> X11 keycode
- `x11ToCarbon[]` in X11KeySymToUCS.h: X11 keycode -> Carbon virtual key

### 1f. CGSGetEventPort Fix [PENDING]

Current implementation creates a NEW Mach port each time. Should return the connection's existing `_eventPort`. This is needed for future CGEventCreateNextEvent integration.

---

## Remaining TODO

| Priority | Task | Depends on |
|---|---|---|
| HIGH | Remove CFSocket from CGSConnectionX11.m | — |
| HIGH | Implement CGEventPost via XTest | 1c fix |
| HIGH | Implement CGEventTap registration list | CGEventPost |
| HIGH | Fix CGSGetEventPort to return connection port | 1c fix |
| MEDIUM | Verify Onyx2D/Cairo rendering | Build fix |
| MEDIUM | AppKit event loop integration | CGEventPost |
| LOW | XInput2 input events | CGEventPost |
| LOW | Wayland backend | X11 complete |

---

## Testing

To test after build:
```bash
# Build Darling with GUI component
cd build && cmake .. && make -j$(nproc)

# Test with a simple .app
darlingprefix ~/.darling
darling shell
cd /path/to/Test.app
./Test.app/Contents/MacOS/Test
```

## References
- Issue #937: CGS design spec by LubosD
- NUIKit/CGSInternal: Reversed CGS API declarations
- NUIKit/GraphicsServices: Reference event pump implementation
- X11Display.m: Pre-existing AppKit X11 event handling (1545 lines)
- CGEventObjC.m: CGEvent/CGEventSource/CGEventTap implementation (370 lines)
