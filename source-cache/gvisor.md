# oracle/gvisor — sandbox safety invariants

Source: gVisor source (pkg/sentry/), gVisor architecture guide, OpenCVE database
Date pulled: 2026-07-20

## Critical Finding for orbit sandbox

gVisor has 7 defense layers. Our sandbox has 1 (path containment). The gap:

| Layer | gVisor | orbit sandbox |
|---|---|---|
| L1: Syscall interception | seccomp (kernel) ❌ not possible in Go | None |
| L2: Syscall emulation | Sentry reimplements all syscalls | `exec.CommandContext` for Shell |
| L3: Sentry confinement | seccomp allowlist (~53 syscalls) | None — Shell runs bash with full access |
| L4: Filesystem isolation | gofer FD donation + O_NOFOLLOW | `filepath.Clean` + `filepath.Rel` (user-space only) |
| L5: Network isolation | netstack (Go userspace TCP/IP) | None |
| L6: Linux isolation | user_ns + mount_ns + pivot_root | None |
| L7: Resource bounding | cgroups, rlimits | 30s ShellContext timeout only |

## What we can adopt

1. **O_NOFOLLOW enforcement** — our resolve() should reject symlinks, not resolve through them. gVisor enforces O_NOFOLLOW via seccomp. We can enforce it via `filepath.EvalSymlinks` → reject if resolved path ≠ cleaned path.

2. **Shell confinement** — `Shell()` runs bash with no restrictions. We should at minimum: clear env vars, set `HOME=/tmp`, add `--norc --noprofile`. Or replace Shell entirely with a restricted Go-native executor.

3. **Zero CVEs with sandbox escape** — gVisor has never had a confirmed sandbox escape CVE. The two-layer model works.

## CVEs — what invariant was violated

| CVE | Invariant Broken | Class |
|---|---|---|
| CVE-2018-16359 | seccomp allowlist had renameat | Escape (potential) |
| CVE-2018-19333 | refcount(shm) = attached processes | InternalEsc |
| CVE-2024-10026 | entropy(seed) ≥ 128 bits | HostLeak |
| CVE-2024-10603 | uniformly_random(ephemeral_port) | HostLeak |
| CVE-2025-2713 | capabilities = minimal from t=0 | HostLeak |