# Darling GUI Implementation — Work Log

## Phase 0: Reconnaissance (Completed)

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

## Phase 1: CGS/Window-Server Backend (Completed)

### Changes Made

#### 1. CGSWindowX11.h/m (NEW)
- Added Display*, Window, CGRect, isVisible ivars
- Implemented: initWithRegion, orderWindow, moveTo, setRegion, getRect
- Implemented: setProperty (WM_NAME), getProperty
- Implemented: createSurface, nativeWindow, invalidate (XDestroyWindow)

#### 2. CGSSurfaceX11.h/m (NEW)
- Added Display*, Window, CGRect, Pixmap ivars
- Implemented: initWithWindow, setDisplay, setXWindow
- Implemented: setBounds (XCreatePixmap), nativeWindow, invalidate (XFreePixmap)

#### 3. CGSConnectionX11.h/m (UPDATED)
- Added mach_port_t _eventPort, CFMachPortRef _cfEventPort
- Implemented: _cgsEventTypeForXEvent (maps X11 events → CGSEventType)
- Implemented: _fillEventRecord:fromXEvent (fills CGSEventRecord from XEvent)
- Implemented: _postEventRecord (posts to Mach port)
- Implemented: processXEvent with event posting
- Implemented: newWindow: (XCreateWindow + CGSWindowX11 creation)
- Implemented: _doGetScreenInformation (XRRScreenResources)

#### 4. CGS.m (UPDATED)
- Added: CGSGetEventPort (mach_port_allocate)
- Added: CGSSetWindowOpacity, CGSSetWindowAlpha, CGSSetWindowLevel stubs
- Added: CGSGetBackgroundEventMask, CGSSetBackgroundEventMask stubs
- Added: CGSEventIsAppUnresponsive, CGSEventSetAppIsUnresponsiveNotificationTimeout stubs
- Added: CGSIsSecureEventInputSet, CGSSetSecureEventInput stubs

### Event Chain (Issue #937)
```
X11 Event → CGSConnectionX11 processXEvent → _fillEventRecord → _postEventRecord
    → Mach port → CGEventCreateNextEvent → CGEventRef → EventRef → NSEvent
```

### Still TODO
- XInput2 integration (replace legacy X11 input)
- Window-to-CGSWindow mapping in event handling
- CGEventPost implementation (currently empty)
- CGEventTapPostEvent implementation (currently empty)

## Next Steps

### Phase 2: CoreGraphics/Onyx2D
- Verify Onyx2D compiles against current Cairo
- Check if any Quartz2D functions are missing

### Phase 3: AppKit Classes
- Review NSApplication.m, NSWindow.m, NSView.m in cocotron
- Implement missing classes

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
