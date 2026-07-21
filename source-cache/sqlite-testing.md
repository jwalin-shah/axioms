# oracle/sqlite-testing — testing methodology catalog

Source: sqlite.org/testing.html, TH3, SQLite source (assert.h, test_journal.c)
Date pulled: 2026-07-20

## Highest-ROI Techniques for Go Packages

### 1. I/O Error Injection Sweep (Trivial, Very High ROI)
```go
type faultingWriter struct {
    n, failAt int
    wrapped   io.Writer
}
func (w *faultingWriter) Write(p []byte) (int, error) {
    if w.n == w.failAt { return 0, errors.New("injected fault") }
    w.n++
    return w.wrapped.Write(p)
}
```
Sweep failAt from 0 upward. Catches every missing error check.

### 2. Journal-Test Pattern (Ordering Assertion)
Interpose on storage interface, assert: "every Write to primary was preceded by Write+Sync to journal."
This is how SQLite proves crash recovery. Same pattern works for dispatch/spawn pipeline.

### 3. Four-Level Assertion Typology
| Level | Meaning | Go Pattern |
|---|---|---|
| `invariant(X)` | Proven — panic in debug | build-tag panic |
| `always(X)` | Believed — graceful fallback in release | return bool, caller handles |
| `boundary(X)` | Known to vary — coverage marker | `testcase(b bool)` |
| `corrupt(X)` | Pre-condition — may be false for bad input | defensive check |

### 4. Bug-to-Test Regression
Every bug gets a test BEFORE the fix. Test must fail on unfixed code.

### 5. Resource Leak Detection
```go
before := runtime.NumGoroutine()
// test
after := runtime.NumGoroutine()
if after > before { t.Errorf("leaked %d goroutines", after-before) }
```

### 6. Cross-Implementation Differential Testing
Run identical inputs through two implementations, diff outputs. Catches logic bugs that pass all other tests.

## Scale Context
- SQLite core: 155.8 KSLOC
- Test code: 92,053 KSLOC
- Ratio: 590:1 test-to-code
- Branch coverage: 100% (not line — every conditional both ways)
- Assertion density: 4.3% of lines contain an assertion