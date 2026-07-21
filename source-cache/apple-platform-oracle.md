# Apple Platform Oracle

Source: Xcode toolchain (16+), Apple HIG, WWDC sessions (2019-2026), Swift Evolution proposals, Apple Developer Documentation.
Also: "The Swift Programming Language" (Apple), UIKit/AppKit/SwiftUI framework contracts, Instruments documentation.

This is how the Apple platform enforces its contracts — at the language level (Swift), the framework level
(UIKit/SwiftUI), the OS level (iOS/macOS/tvOS/watchOS), and the toolchain level (Xcode).

---

## Part 1: Xcode — The Toolchain as Contract Enforcer

Xcode is not just an IDE. It's a contract enforcement engine. Every warning, every build error, every
Instruments trace is Xcode telling you "you violated a platform contract." The skill is learning to
hear what it's telling you.

### 1.1 Build System — What Xcode Actually Does

Xcode's build system is not a black box. It's a pipeline:

```
Source → Swift Compiler → LLVM IR → Machine Code → Linker → Binary → Code Sign → Package → Deploy
         (swiftc)         (llc)      (ld)                     (codesign)    (xcodebuild)
```

**Invariant:** Every build configuration (Debug/Release) is a reproducible function from source + settings → binary.

**Xcode-specific knowledge extraction:**

| Setting | What it enforces | Violation symptom |
|---|---|---|
| `SWIFT_OPTIMIZATION_LEVEL` (`-Onone`, `-O`, `-Osize`) | Debuggability vs. performance tradeoff | `-Onone` for release = slow binary. `-O` for debug = unreadable backtraces. |
| `ENABLE_TESTABILITY` | `@testable import` only works in Debug | Tests fail to build: "Module not compiled for testing" |
| `SWIFT_ACTIVE_COMPILATION_CONDITIONS` | `#if DEBUG` gates at compile time | Dead code shipped to production, or debug code missing |
| `GCC_TREAT_WARNINGS_AS_ERRORS` | No suppressed warnings | "It's just a warning" → becomes a crash in the field |
| `VALID_ARCHS` + `EXCLUDED_ARCHS` | Which chips this binary runs on | "Undefined symbols for architecture arm64" |
| `ENABLE_MODULE_VERIFIER` | Module interface stability | Binary incompatibility after framework update |

**What to learn from each project's build settings:**
1. Open `.xcodeproj/project.pbxproj` — it's a text file. Every build setting is visible.
2. `xcodebuild -showBuildSettings` — dumps the resolved settings for a target (after `.xcconfig` inheritance).
3. Build settings inheritance order: `.xcconfig` → Target → Project → Default. Understanding this chain tells you why a setting has the value it does.

### 1.2 Schemes — What Xcode Thinks You're Building

A scheme is an action plan: Build, Test, Run, Profile, Analyze, Archive. Each action has:
- Build configuration (Debug/Release)
- Executable
- Arguments passed at launch
- Environment variables
- Diagnostics (Address Sanitizer, Thread Sanitizer, Memory Management, Logging)

**Invariant:** A scheme MUST specify which build configuration each action uses. Mismatched configurations = bugs that appear only in release builds.

**What to extract from existing schemes:**
- `xcodebuild -list` — all targets, schemes, and configurations
- `xcodebuild -showBuildSettings -scheme <name>` — per-scheme settings
- The scheme file: `<project>.xcodeproj/xcshareddata/xcschemes/<name>.xcscheme` — XML, human-readable

### 1.3 Code Signing — The Trust Chain

Apple's code signing is a cryptographic chain of trust:

```
Developer Certificate ← Apple CA (intermediate) ← Apple Root CA
           ↓
Provisioning Profile (app ID + device list + entitlements + certificate)
           ↓
Signed Binary (embedded-application-signature in Mach-O)
           ↓
Gatekeeper / AMFI verifies the chain at launch
```

**Invariant:** ∀launch: the binary's signature chain is valid, the provisioning profile includes this device, and the entitlements match the profile.

**Key files to inspect:**
- `*.provisionprofile` — ASN.1 encoded. `security cms -D -i <profile>` decodes it. Shows: app ID, team ID, devices (UDID list), entitlements, expiration, certificate chain.
- `Entitlements.plist` — what the app claims it needs. Must match provisioning profile or launch fails.
- `CodeResources` inside the bundle — hashes of every file. Modified file = invalid signature.

### 1.4 Instruments — The Runtime Truth

Instruments is a time-based profiler that hooks into the kernel's tracing infrastructure (DTrace on older systems, Signpost + os_log on modern). It shows what the system ACTUALLY did, not what you THINK it did.

| Instrument | What it measures | When to use |
|---|---|---|
| **Time Profiler** | CPU usage by thread, call tree | "Why is this slow?" — shows where time is actually spent |
| **Allocations** | Heap allocations, retain/release, reference counts | "Why is memory growing?" — shows every allocation, every backtrace |
| **Leaks** | Unreachable memory (no references, not freed) | "Why is memory unbounded?" — leaks are allocations with no remaining pointers |
| **VM Tracker** | Virtual memory regions (dirty, clean, swapped) | "How much memory does this actually use?" |
| **Network** | All HTTP/WebSocket/BSD socket traffic | "What is this actually sending over the wire?" |
| **File Activity** | All file I/O (open, read, write, close, fsync) | "What files is this touching?" |
| **Energy Log** | CPU wake-ups, GPU usage, network, location | "Why does the battery drain?" |
| **os_signpost** | Your own instrumentation points | "When does this phase start and end?" |

**Invariant:** Every Instruments trace is evidence. "I think the leak is in X" → Instruments shows allocations with backtraces → the backtrace IS the bug location. No speculation, just data.

**How to extract knowledge from Instruments:**
1. Run the allocation or leak trace
2. Look at the heaviest stack trace — that's the code path allocating the most memory
3. Look at the retain/release balance: retain count > release count = leak
4. Signpost your own code: `os_signpost(.begin, log: log, name: "Phase")` → `os_signpost(.end, log: log, name: "Phase")` — Instruments shows your phases on its timeline

### 1.5 Swift Package Manager — The Dependency Contract

SPM enforces a strict dependency model that CocoaPods and Carthage don't:

**Invariant:** ∀dependency: exact version is recorded in `Package.resolved`. Any change to `Package.resolved` changes the dependency graph. CI and developer machines must agree on `Package.resolved`.

| SPM concept | What it enforces | Violation |
|---|---|---|
| `Package.resolved` (lockfile) | Exact versions for reproducibility | "It works on my machine" — different resolved version |
| `upToNextMajor(from: "2.0.0")` | 2.0.0 ≤ version < 3.0.0 | Major bump breaks API → must be explicit |
| `exact("1.2.3")` | Pinned to exact version | No automatic updates |
| `branch("main")` | Latest commit on branch | Non-reproducible — use only in dev |
| Package manifest (`Package.swift`) | Declares products, targets, dependencies | Circular dependency = build error |

### 1.6 XCTest — The Testing Contract

**Invariant:** ∀test: setUp() runs before, tearDown() runs after. Tests are isolated — one test's state must not leak into another.

**XCTest-specific invariants:**
- `XCTAssert` family: 21 assertion types. Each one fails with a specific message.
- Performance tests: `measure { }` — runs the block 10 times, reports mean + standard deviation. A baseline is stored; deviation from baseline = regression.
- `XCTSkip` — skip a test with a reason. Better than commenting out.
- `XCTExpectFailure` — expected failure. The test passes if it fails. For known bugs with radar numbers.
- UI tests (`XCUIApplication`) — launch the app, tap buttons, read labels. Runs on a separate process. Slow but end-to-end.
- `xcodebuild test` — runs tests from command line. Output in `.xcresult` format. Parseable via `xcresulttool`.

---

## Part 2: Swift — The Language Contract

### 2.1 Memory Management — ARC

Swift uses Automatic Reference Counting, not garbage collection. Every object has a retain count.
When the count reaches zero, the object is deallocated. This is DETERMINISTIC — you know exactly when
memory is freed.

**Invariant:**
```
∀reference R to object O: O's retain count ≥ number of strong references to O
∀retain cycle: A ↔ B where A retains B and B retains A → neither is freed → leak
```

**Enforcement:**
- Strong references (default): increment retain count
- Weak references (`weak var`): do NOT increment retain count, become nil when object is deallocated
- Unowned references (`unowned`): do NOT increment, crash if accessed after deallocation (use only when lifetime is guaranteed)
- Closures capture strong by default — use `[weak self]` in closures that outlive `self`
- Memory graph debugger: Xcode → Debug Memory Graph → shows all objects, all references, retain cycles highlighted
- `leaks` command-line tool: same as Instruments Leaks, from terminal

### 2.2 Concurrency — Swift 5.5+ async/await, actors, MainActor

Swift's concurrency model is built on three primitives:

**Invariant:**
```
∀@MainActor function f: f executes on the main thread
∀Actor A: at most one task executes on A at any time (mutual exclusion by construction)
∀Task T: T can be cancelled → T.checkCancellation() or Task.isCancelled
```

**Enforcement:**
- `@MainActor` — compiler-enforced. Calling a MainActor function from a background context requires `await`. Compiler rejects direct calls.
- Actors — like a class but with a serial executor. All access is async. The compiler prevents data races by making actor state access go through the actor's executor.
- `Sendable` — a protocol that marks types safe to pass across concurrency domains. Value types (structs, enums) are Sendable by default. Classes must be explicitly marked `@unchecked Sendable` or made immutable.
- Task cancellation is cooperative. The child task must check `Task.isCancelled` or call `Task.checkCancellation()`. Cancellation doesn't force-stop — it requests.
- `Task.detached` — creates a task NOT in the current actor's context. No priority inheritance. Use when you explicitly want separation.

### 2.3 Protocols — The Interface Contract

Swift protocols are more powerful than Go interfaces. They support:
- **Requirements:** methods, properties, initializers, subscripts
- **Associated types:** protocol-level generics. `protocol Collection { associatedtype Element }`
- **Self requirements:** `func ==(lhs: Self, rhs: Self) -> Bool` — only same-type comparisons
- **Conditional conformance:** `extension Array: Equatable where Element: Equatable {}`
- **Protocol composition:** `typealias Codable = Encodable & Decodable`
- **Opaque return types:** `func makeView() -> some View` — the concrete type is hidden, the protocol is visible

**Invariant:** ∀protocol P: the set of requirements = the minimum contract. Protocol conformance is checked at compile time. No runtime type-checking for protocols (unlike Go's interface conversion which can panic).

### 2.4 Error Handling — Typed Throws

Swift errors are typed (Swift 6+), not opaque. `func fetch() throws(NetworkError) -> Data` tells the caller exactly what errors are possible.

**Invariant:** ∀throwing function f: f's error type is part of the interface. Callers must handle or propagate every error case.

**Enforcement:**
- `do { try f() } catch { }` — typed catch: `catch let error as NetworkError`
- `try?` — convert to nil on error. Silently drops error information. Use for best-effort operations only.
- `try!` — crash on error. Use only when error is provably impossible (e.g., decoding a bundle resource that exists at compile time).

### 2.5 Property Wrappers — The Attribute Contract

Property wrappers are compile-time transformations. `@State var count = 0` expands to a backing storage with get/set that notifies SwiftUI when the value changes.

**Invariant:** ∀property wrapper W: W.wrappedValue access goes through W's get/set. The compiler synthesizes the storage. The property wrapper's semantics are compile-time guaranteed.

---

## Part 3: Framework Contracts

### 3.1 SwiftUI — Declarative UI

SwiftUI is a declarative UI framework. You describe WHAT the view should look like for a given state,
and SwiftUI figures out HOW to render it (layout, animation, accessibility).

**Invariant:**
```
∀View V: V.body is a pure function of the view's state
∀state change: SwiftUI recomputes body and diffs the view tree
∀diff: only changed views are re-rendered (not the entire tree)
```

**Key contracts:**
- `@State` — local mutable state. When it changes, body recomputes.
- `@Binding` — two-way connection to state owned elsewhere. Parent owns, child mutates.
- `@ObservedObject` — external reference type. View recomputes when `objectWillChange` fires.
- `@StateObject` — view OWNS the object. Created once, not recreated on recomputation.
- `@Environment` — reads system values (color scheme, locale, accessibility settings).
- `@EnvironmentObject` — reads app-wide shared state. Must be injected by ancestor via `.environmentObject()`.

**Anti-patterns:**
- Side effects in `body` — `body` is called during layout, can be called many times. Network calls in `body` = N redundant calls.
- `@ObservedObject` where `@StateObject` is needed — object recreated on every view recomputation, losing state.
- Expensive computation in `body` — use `@State` + `.onAppear` or `Task { }` instead.

### 3.2 UIKit/AppKit — Imperative UI

UIKit (iOS) and AppKit (macOS) are older, imperative frameworks. Views are explicit objects with
lifecycle callbacks.

**Invariant:**
```
∀UI operation: MUST be on the main thread
∀view lifecycle: init → loadView → viewDidLoad → viewWillAppear → viewDidAppear → viewWillDisappear → viewDidDisappear → deinit
∀view: frame and bounds are in the view's superview's coordinate system
```

### 3.3 Background Tasks — The Time Budget

iOS/macOS gives background execution as a BUDGET, not a right.

**Invariant:**
```
∀background task T: T has a finite time budget. When the budget expires, T is suspended.
∀BackgroundTasks framework task: must call `setTaskCompleted()` when done.
```

### 3.4 Accessibility — The Universal Contract

Every UIKit/SwiftUI view has accessibility attributes. Screen reader (VoiceOver) uses them.

**Invariant:** ∀view: has a `accessibilityLabel`, `accessibilityHint`, and `accessibilityValue`. If VoiceOver can't navigate your app, the app is broken.

---

## Part 4: OS Contracts

### 4.1 Sandbox — The File System Contract

macOS sandbox limits filesystem access to the app's container (for App Store apps) or explicitly granted directories (via NSOpenPanel powerbox).

**Invariant:**
```
∀file access from sandboxed app: the app has an entitlement for that path OR the user explicitly granted access via powerbox
```

### 4.2 Entitlements — The Capability Contract

Every capability (camera, microphone, location, health data, network) requires:
1. An entitlement in `Entitlements.plist`
2. A usage description string in `Info.plist`
3. Runtime permission request (system dialog)

**Invariant:** ∀capability: compile-time entitlement + build-time plist string + runtime permission granted → capability available. Missing any of these three = capability denied.

### 4.3 Launch Constraints — The Launch Contract

macOS/iOS restrict what an app can do at launch:
- `launchd` manages daemons. plist in `/Library/LaunchDaemons/`.
- iOS: limited background launch modes (push notification, location change, Bluetooth event, etc.)
- macOS daemons: can run at boot, periodically, or on demand.
- `LSBackgroundOnly` — GUI-less daemon. Cannot create windows.
- Watchdog: the app must finish launching within ~20 seconds or the OS kills it.

---

## The Apple Platform Test

For any Apple-platform code, ask:
1. **Build:** Does this build the same on every machine? Is the scheme correct? Is `Package.resolved` committed?
2. **Memory:** Where's the retain cycle? (Instruments Leaks + Memory Graph)
3. **Concurrency:** Is this on the main thread? (MainActor, Thread Sanitizer)
4. **Lifecycle:** What happens if the app is backgrounded? (background task budget)
5. **Sandbox:** Does this filesystem access have an entitlement? (App Sandbox)
6. **Accessibility:** Can VoiceOver navigate this? (accessibilityLabel on every view)
7. **Signing:** Is the provisioning profile current? Is the certificate valid?
8. **Performance:** What does Instruments say? (Time Profile, Allocations, Energy Log)

The Apple platform's philosophy is: the OS enforces contracts, the compiler enforces invariants, and Instruments is the evidence. Don't guess — measure. Don't hope — prove.