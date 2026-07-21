# oracle/pty — terminal PTY invariants

Source: POSIX termios, Go's pty libraries, mintmux source
Date: 2026-07-21

## Core Invariants

### 1. PTY lifecycle
```
∀pty: master_opened → slave_opened → child_forked → child_execs_shell → master_closed → slave_closed
```
Orbit sandbox Shell() and mintmux pane lifecycle depend on this ordering.

### 2. Signal propagation
```
∀signal: kernel delivers to foreground process group
SIGWINCH → on resize. SIGHUP → on master close. SIGINT → on ^C.
Kernel-enforced. No userspace validation needed.
```

### 3. Raw vs cooked mode
```
∀raw: all_bytes_passthrough
∀cooked: kernel_line_buffers_until_newline
```
mintmux uses raw mode for pane I/O. Shell/PTY tests use raw for direct byte control.

### 4. Process group / session
```
∀pg: SIGHUP to all members on leader exit
kernel_enforced. No Go code can violate this.
```

### 5. EIO on master close
```
∀slave_read: master_closed → read_returns_EIO
```
Critical for mintmux: when a pane closes, reading from the slave must detect EIO.

### 6. Resize handling (TIOCSWINSZ)
```
∀resize: master_emits_SIGWINCH → foreground_process_group_receives
Mintmux resizes panes via TIOCSWINSZ ioctl on the master fd.
```

### 7. Flow control
```
∀flow: XOFF_received → master_stops_writing. XON → master_resumes.
Rare in terminal emulators. mintmux manages this at the buffer level instead.

### 8. Escape sequences (ANSI/VT100)
```
∀escape: CSI → params → final_byte
∀unterminated: ignore_after_timeout
Stateful parser. State: Ground → Escape → CSI_Entry → CSI_Param → CSI_Intermediate → CSI_Ignore.
```

## mintmux test patterns

### TestAX_LuaWakeupNoPanic (AX-047)
Per-waiter `sync.Once` prevents double-close of wakeup channels.
∀waiter: wakeup_channel_closed_exactly_once.
32 waiters × 1024 concurrent events. Tests dispatchOne close path.

### TestT_PaneLifecycle (AX-005)
Spawn command, drain events, Close twice. Second Close must be no-op.
∀pane: Close(); Close() → no panic. Uses sync.Once.

### TestAX_PaneSendCloseNoPanic (AX-035)
Send to closed pane channel must not panic.
∀pane: Close → Out_chan_receives_no_more → send_to_closed_is_noop_or_error.

## Go enforcement
- `sync.Once` for idempotent close (already in mintmux + orbit)
- `syscall.TIOCSWINSZ` for resize
- `golang.org/x/term` for raw mode
- `os.StartProcess` + `syscall.Setsid` for session creation
- `syscall.Wait4` for child process reaping