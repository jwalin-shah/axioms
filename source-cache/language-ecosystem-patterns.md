# Language Ecosystem Patterns Oracle

Source: Go stdlib (net/http, io, context, database/sql, testing), Rust std (std::io, std::ops, tokio),
Python stdlib (asyncio, pathlib, dataclasses, contextlib), Swift stdlib (Sequence, Combine, AsyncSequence),
C/POSIX (errno, FILE*, pthreads), and the design documents that shaped them.

This is the CRAFT of each language's standard library — not the API docs (those exist), but the DESIGN
PRINCIPLES that the stdlib authors used. The invariants are universal. The enforcement pattern varies by
language. One oracle, five languages, one set of principles.

---

## 1. Small Interfaces — "One Job, Done Well"

**Principle:** The most powerful abstractions are single-method. A single-method interface composes
infinitely — you can wrap it, chain it, buffer it, encrypt it, compress it. A multi-method interface
locks you into the implementation's assumptions.

**Invariant:**
```
∀abstraction A: |interface(A)| = 1 → A composes with any other abstraction
∀composition C: C = A ∘ B → interface(C) = interface(A) = interface(B) = 1 method
```

**Enforcement by language:**

| Language | Single-method pattern | Example |
|---|---|---|
| Go | `io.Reader` (1 method: `Read([]byte) (int, error)`) | `gzip.NewReader(reader)`, `bufio.NewReader(reader)`, `io.LimitReader(reader, n)` — all compose |
| Rust | `Read` trait (1 required method: `read(&mut self, buf: &mut [u8]) -> Result<usize>`) | `BufReader<R>`, `GzDecoder<R>`, `Take<R>` — all wrap any `Read` |
| Python | `__iter__` protocol (1 method: `__next__`) | `for x in thing:` — works with lists, generators, files, itertools chains |
| Swift | `Sequence` protocol (1 required method: `makeIterator()`) | `for x in sequence` — works with arrays, dictionaries, ranges, custom types |
| C | Function pointer (`int (*read)(void*, char*, int)`) | `FILE*` wraps fd, buffer, mode. `fread`/`fwrite` compose over any stream. |

**Why this works everywhere:** A single-method interface captures the ESSENCE of the abstraction. Reading is "give me bytes." Iteration is "give me the next thing." Everything else (buffering, compression, encryption, limiting) is a wrapper around the essence.

**orbit applications:**
- `pkg/tokenrouter` — `Acquire(ctx) (string, error)` — the essence of "get a key." Could wrap with rate limiting, circuit breaking, caching — all as single-method wrappers.
- `pkg/circuitbreaker` — `Call(fn func() error) error` — the essence of "execute with protection." Wraps any function.
- `pkg/luaengine` — `RunRule(script, payload) (Result, error)` — the essence of "evaluate in sandbox."

---

## 2. Error as Value — "Errors Are Not Exceptions"

**Principle:** Errors are data, not control flow. The caller must explicitly handle every error path.
The compiler (or linter) should verify that no error is silently ignored.

**Invariant:**
```
∀function f that can fail: f's return type encodes the failure mode
∀caller of f: the caller MUST handle the error case (compiler-enforced or linter-enforced)
∀error: an error is a value that carries: what happened, where, and why (context)
```

**Enforcement by language:**

| Language | Error mechanism | Compiler enforcement |
|---|---|---|
| Go | `(T, error)` return tuple | `errcheck` linter catches ignored errors. Convention: `if err != nil { return err }` |
| Rust | `Result<T, E>` enum | Compiler REJECTS unhandled `Result`. `?` operator propagates. `#[must_use]` on Result. |
| Python | Exceptions with `raise from` chain | Runtime. `except:` (bare) is a bug. `except Exception as e: raise NewError(...) from e` preserves the chain. |
| Swift | `throws(ErrorType)` typed throws (Swift 6+) | Compiler enforces: `try` is required. `try?` converts to nil (information loss). `do/catch` for handling. |
| C | Return codes + `errno` | Nothing. `-Wall -Werror` catches some. `__attribute__((warn_unused_result))` (GCC/Clang). |

**Invariant across all languages:**
```
∀error: context is preserved. fmt.Errorf("context: %w", err) (Go) = anyhow::Context (Rust) = raise NewError(...) from e (Python)
```

**orbit applications:**
- Every orbit package wraps errors: `fmt.Errorf("tokenrouter.Acquire: %w", err)`. The error chain is the evidence.
- `pkg/dispatch` — HTTP errors are classified (P0/P1/P2) based on status code. The classification IS the error type.
- `pkg/sandbox` — Shell errors are wrapped with the command, exit code, and stderr. The error value carries everything needed for debugging.

---

## 3. Resource Cleanup — "Acquire and Release Are Paired"

**Principle:** Every resource acquisition must be paired with a release. The language should enforce this
at the scope level — when the scope exits, the resource is released. No "remember to close" — the language
does it for you.

**Invariant:**
```
∀resource R: acquire(R) → (use(R) → release(R)) ∨ (error → release(R))
∀scope exit: all resources acquired in the scope are released
∀release: release is infallible (must not itself fail, or must not mask the original error)
```

**Enforcement by language:**

| Language | Mechanism | Guarantee |
|---|---|---|
| Go | `defer` | Runs at function exit. Order: LIFO. Runs even on panic. |
| Rust | `Drop` trait + RAII | Compiler-enforced. Drop runs at scope exit. `MutexGuard` unlocks on drop. `File` closes on drop. |
| Python | `with` statement + `__exit__` | `__exit__` runs on exception too. `contextlib.closing`, `contextlib.ExitStack` for dynamic cleanup. |
| Swift | `defer` (same as Go) | Runs at scope exit. Also `deinit` for class deallocation. |
| C | Manual + `goto cleanup` | No enforcement. `__attribute__((cleanup))` (GCC/Clang) for scope-based cleanup. `atexit()` for process exit. |

**Orbit applications:**
- `defer resp.Body.Close()` in `pkg/dispatch` — every HTTP response body is closed.
- `defer m.Unlock()` in `pkg/tokenrouter` — every mutex is unlocked.
- `defer os.RemoveAll(worktree)` in `pkg/sandbox` — worktrees are cleaned up.
- The invariant: `rg 'defer.*Close\|defer.*Unlock\|defer.*Remove' pkg/` should find a match for every acquire.

---

## 4. Cancellation — "The Caller Can Always Stop"

**Principle:** The caller controls the lifetime. Every long-running operation must accept a cancellation
signal. When cancelled, the operation must stop promptly and return a cancellation error.

**Invariant:**
```
∀long-running operation O: O accepts a cancellation token
∀cancellation: when the token fires, O stops within a bounded time
∀cancellation error: O returns a distinct error that identifies the cancellation (not a generic "failed")
```

**Enforcement by language:**

| Language | Cancellation mechanism | Propagation |
|---|---|---|
| Go | `context.Context` with `Done()` channel | Pass `ctx` as first parameter. Check `ctx.Err()` in loops. `select { case <-ctx.Done(): return ctx.Err() }` |
| Rust | `CancellationToken` (tokio) or `select!` with `signal` | `tokio::select! { result = future => ..., _ = cancel.cancelled() => ... }` |
| Python | `asyncio.CancelledError` | `await` on a cancelled task raises `CancelledError`. Must re-raise or handle explicitly. |
| Swift | `Task.checkCancellation()` + `Task.isCancelled` | Cooperative. Check in loops. `try Task.checkCancellation()` throws on cancel. |
| C | `sig_atomic_t` flag + `signal()` | Set a flag in the signal handler. Check the flag in the main loop. `volatile sig_atomic_t` is the only async-signal-safe type. |

**Orbit applications:**
- Every orbit function that does I/O takes `ctx context.Context` as the first parameter.
- `pkg/dispatch` — `Dispatch(ctx, spec)` — the caller can cancel the dispatch.
- `pkg/sandbox` — `ShellContext` has a 30s timeout. The context is passed to `exec.CommandContext`.
- `pkg/ggrind` — grind pipeline stages check `ctx.Done()` before processing each item.

---

## 5. Zero-Value Useful — "Ready to Use Without Construction"

**Principle:** The zero value (the value a variable gets when declared without initialization) should be
useful. A `sync.Mutex` is ready to lock without calling `NewMutex()`. A `bytes.Buffer` is ready to write
without calling `NewBuffer()`. A `struct` with sensible defaults doesn't need a constructor.

**Invariant:**
```
∀type T: T's zero value is either:
  1. Ready to use (sync.Mutex, bytes.Buffer, strings.Builder), or
  2. Explicitly invalid (database/sql.DB requires sql.Open)
```

**Enforcement by language:**

| Language | Zero-value philosophy | Example |
|---|---|---|
| Go | Zero value is useful by convention | `sync.Mutex{}`, `bytes.Buffer{}`, `strings.Builder{}`, `http.Client{}` (with defaults), `context.Background()` |
| Rust | No zero value. `Default` trait for sensible defaults. | `Vec::new()`, `HashMap::new()`. No uninitialized values. |
| Python | `None` is the sentinel. `dataclass` with defaults. | `@dataclass class Config: timeout: float = 30.0` |
| Swift | Default initializers for structs. Optionals for absence. | `var count = 0`, `var name: String? = nil` |
| C | Zero-initialized memory is `0`/`NULL`/`0.0`. | `struct Foo f = {0};` — all fields zero. `calloc` zeros memory. `malloc` does NOT. |

**Orbit applications:**
- `pkg/circuitbreaker` — `CircuitBreaker{}` is not useful (needs threshold, timeout). Constructor required: `NewCircuitBreaker(threshold, timeout)`.
- `pkg/tokenrouter` — `Router{}` is not useful (needs key pool). Constructor required: `NewRouter(config)`.
- `pkg/sandbox` — `Sandbox{}` is not useful (needs worktree root). Constructor required: `NewSandbox(root)`.
- Rule: if the zero value is not useful, provide a constructor that makes it useful. If the zero value IS useful, document it and don't provide a constructor.

---

## 6. Testing as a First-Class Concern

**Principle:** The testing package is part of the standard library, not a third-party add-on. Testing is
not a separate activity — it's part of writing code. The language makes testing easy, fast, and idiomatic.

**Invariant:**
```
∀language L: L provides a testing framework in its standard library
∀test T: T is deterministic, fast (< 1s), and tests observable behavior (not implementation)
∀test: T is in the same directory or module as the code it tests (not in a separate `tests/` tree)
```

**Enforcement by language:**

| Language | Test framework | Key features |
|---|---|---|
| Go | `testing` | Table-driven tests, subtests (`t.Run`), `t.Parallel()`, `-race`, `-cover`, `t.TempDir()`, `testing/fstest` |
| Rust | `#[test]` attribute + `cargo test` | `#[should_panic]`, `#[ignore]`, `assert_eq!`, `assert_ne!`, `Result<T, E>` in tests |
| Python | `unittest` (stdlib) + `pytest` (de facto) | `pytest.mark.parametrize`, fixtures, `conftest.py`, `pytest -x --pdb` |
| Swift | `XCTest` | `XCTAssert*` family (21 assertions), `setUp()`/`tearDown()`, performance tests, UI tests, `XCTSkip` |
| C | Nothing in stdlib. `assert()` macro (debug only). | `cmocka`, `check`, `Unity` (third-party). `assert()` is removed in `NDEBUG` builds. |

**Testing invariants that hold across all languages:**
1. Arrange → Act → Assert (Given → When → Then)
2. One test = one behavior. "Test the thing" is too vague. "Test that Acquire respects the rate limit" is testable.
3. Tests are documentation. A test that says `TestAX001_OpenCircuitBlocksTraffic` documents the invariant.
4. Fast tests run on every save. Slow tests (integration, e2e) run in CI.

**Orbit applications:**
- `TestAX*` tests are table-driven Go tests. Each test proves one invariant.
- `go test -race -count=1 ./pkg/...` — runs all tests with race detector. Required before every commit.
- The 7 packages without `ax_test.go` need tests. The invariant is written but not proven.

---

## 7. Safe Concurrency — "The Language Helps, But You Still Have to Think"

**Principle:** The language can prevent data races, but it cannot prevent race conditions. A data race is
two threads accessing the same memory without synchronization. A race condition is a logic error where
the outcome depends on timing. The language prevents the first. The programmer prevents the second.

**Invariant:**
```
∀data race: the language runtime detects it at test time (race detector) or prevents it at compile time (ownership)
∀race condition: the programmer must prove that the invariant holds for all possible interleavings
```

**Enforcement by language:**

| Language | Data race prevention | Race condition help |
|---|---|---|
| Go | Race detector (`go test -race`). `sync.Mutex`, `sync/atomic`, channels. | Owicki-Gries proof obligations. TestAX gates for concurrent scenarios. |
| Rust | Type system (`Send` + `Sync` traits). Compiler rejects data races at compile time. | `Mutex<T>` wraps the data. Channels for message passing. Still need to prove the logic is correct. |
| Python | GIL prevents data races in CPython. `asyncio` for cooperative concurrency. `threading` for parallelism (with GIL). | `asyncio.Lock`, `asyncio.Queue`. Race conditions are still possible (e.g., `await` in the wrong place). |
| Swift | Actors (serial executor). `Sendable` types. Compiler rejects non-Sendable types crossing actor boundaries. | `@MainActor` for UI. Structured concurrency (`TaskGroup`). Race conditions are still possible in actor logic. |
| C | Nothing. ThreadSanitizer (TSan) at runtime. `pthread_mutex_t`, `_Atomic`. | `pthread_mutex_lock`/`unlock`. Manual. `valgrind --tool=helgrind` for lock ordering bugs. |

**Orbit applications:**
- `go test -race` is mandatory for every orbit package. The race detector finds data races.
- Owicki-Gries oracle provides the proof framework for race conditions.
- `pkg/circuitbreaker` — mutex protects state transitions. Race detector verifies no data races. TestAX gates verify no race conditions (invariant holds for all interleavings).
- `pkg/tokenrouter` — `sync.Mutex` on key rotation, `sync.Once` on key pool init. No data races. Race conditions prevented by fencing token design (future).

---

## The Cross-Language Test

For any code in any language, ask:
1. **Interface size:** Is this interface doing one job? Could it compose with others?
2. **Error handling:** Can the caller ignore this error? If so, is that correct?
3. **Resource cleanup:** Is every acquire paired with a release? Scope-based or manual?
4. **Cancellation:** Can the caller stop this operation? Within what time bound?
5. **Zero value:** Is the default value useful? Or does the constructor enforce invariants?
6. **Testing:** Is there a test that proves this works? Is it deterministic and fast?
7. **Concurrency:** If two of these run at the same time, does the invariant hold?

These principles are not Go-specific. They are not Python-specific. They are the design principles that
the authors of every standard library used. The syntax differs. The invariant is the same.