# oracle/postgresql — coding conventions for 30-year reliability

Source: PostgreSQL source conventions, Developer FAQ, WAL docs
Date pulled: 2026-07-20

## Error Severity Tiers (Directly Portable to Go)

| PostgreSQL | Go Equivalent | When |
|---|---|---|
| `PANIC` — shuts down cluster | `panic()` | Data corruption, continuing would destroy everything |
| `FATAL` — terminates backend | `log.Fatal()` / `os.Exit(1)` | Process cannot continue |
| `ERROR` — aborts transaction | returned `error` | Operation failed, state is clean |
| `WARNING` — logged, continues | `log.Warn()` | Anomaly but operation can proceed |

## Error Message Structure

| Element | Style | Example |
|---|---|---|
| Primary | Telegram style, lowercase, no period | `could not open file: permission denied` |
| Detail | Complete sentence, capitalized | `The file was created by user root.` |
| Hint | Complete sentence, suggestion | `Run chown on the data directory.` |

## Tense Rule
- **"could not"** — retriable (disk full, network timeout)
- **"cannot"** — permanent (type mismatch, invalid input)

## Assertion Rules
1. Assert what you KNOW, not what you hope
2. Never assert user-supplied data
3. Asserts compile out in production (`--enable-cassert` → build tags)

## Lock Ordering (Prevents Deadlocks)
1. Always acquire locks in consistent order across all code paths
2. Take most restrictive lock up front — don't upgrade
3. Never hold locks across I/O

## WAL Invariants
- Log before data (data never reaches disk before WAL)
- Monotonic LSNs (append-only, never overwrite)
- CRC on every record (detect corruption at read time)
- Idempotent REDO (replay N times = replay once)
- Full page writes after checkpoint (protects against torn pages)

## Commit Checklist (10 items, fully portable)
1. Does it apply cleanly to HEAD?
2. Does it include tests and docs?
3. Does it implement what it claims?
4. Does it follow coding guidelines?
5. Are there crashes or assertion failures?
6. Does it slow down simple tests?
7. Are there compiler/linter warnings?
8. Does it work cross-platform?
9. Are comments sufficient and accurate?
10. Does the architecture cohere with existing features?