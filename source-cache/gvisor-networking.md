# oracle/gvisor-networking — Netstack: TCP/IP implementation, packet processing
Source: https://gvisor.dev/docs/architecture_guide/networking/
Secondary: https://gvisor.dev/docs/architecture_guide/security/ (raw: https://raw.githubusercontent.com/google/gvisor/master/g3doc/architecture_guide/security.md)
Date pulled: 2026-07-21

## Extracted Invariants

### INV-NET-001: Sentry cannot open host sockets — single AF_PACKET socket
**Core Invariant:**
```
∀ socket s created by sentry process:
  s.type = AF_PACKET
  ∧ s is the socket the sentry was initialized with
  ∧ sentry does not call socket(), accept(), or connect() syscalls on the host

Exception: when --network=host is enabled, hostinet bypasses this entirely
```
**Source:** Networking guide: "The sentry, which for security cannot open host sockets of its own, is initialized with a single AF_PACKET socket."
Security model: "The calls do not include the creation of new sockets (unless host networking mode is enabled)" and "The Sentry is not permitted to open new files, create new sockets or do many other interesting things on the host."
**Counterexample:** If the sentry opens a second socket (e.g., a TCP socket to the host), an attacker who compromises the sentry could exfiltrate data or establish a C2 channel bypassing network policy. This is exactly the sandbox-escape vector gVisor is designed to prevent.
**Why this matters for bridge/orbit:** orbit's ShellExecutor runs `exec.CommandContext` which gives bash full access to create any socket type. This is a direct violation of the INV-NET-001 principle. If we jail the executor process, it must be prohibited from calling socket(2).

### INV-NET-002: All non-loopback traffic must transit the AF_PACKET socket
**Core Invariant:**
```
∀ packet p ingressed by or egressed from the sandbox:
  is_loopback(p) ∨ traversed(p, single_AF_PACKET_socket)
```
**Source:** Networking guide: "gVisor ingresses and egresses all non-loopback traffic across that socket."
**Counterexample:** If a file descriptor for a connected TCP socket is passed into the sandbox via SCM_RIGHTS (or any other FD-passing mechanism), traffic can bypass the AF_PACKET socket. The sandbox's network policy (iptables, network policy) cannot see or control that traffic.
**Why this matters for bridge/orbit:** orbit's ShellContext passes no FDs, so this is less directly applicable. But bridge's gRPC streaming could theoretically receive FDs if the transport supports them — ensure gRPC config disables FD passing.

### INV-NET-003: Address/route mirroring — sentry routing table ≡ VETH device config
**Core Invariant:**
```
∀ address a on virtual network device in sentry's netns:
  a ∈ sentry_internal_routing_table
∀ route r on virtual network device in sentry's netns:
  r ∈ sentry_internal_routing_table

The converse is NOT guaranteed: sentry may have internal-only routes
for virtual networks not exposed on the VETH.
```
**Source:** Networking guide: "gVisor scrapes addresses, routes, and the like from those devices and configures the sentry to use those same addresses and routes."
**Counterexample:** If a new IP address is added to the VETH device after sentry startup (e.g., by a CNI plugin adding a secondary IP), the sentry won't see it. Applications in the sandbox cannot bind to or receive traffic for that address. This is a startup-time snapshot, not a live mirror.
**Why this matters for bridge/orbit:** Not directly applicable — orbit doesn't have its own network stack. Relevant if orbit ever spawns sandboxed workers with their own network namespaces.

### INV-NET-004: No system call pass-through — sentry reimplements every syscall
**Core Invariant:**
```
∀ syscall σ that the application invokes:
  handler(σ) ∈ sentry_implementation
  ∧ handler(σ) ∉ {direct_host_passthrough}

Consequence: if a kernel feature has no sentry implementation, it is UNAVAILABLE
to the sandboxed application.
```
**Source:** Security model: "No system call is passed through directly to the host. Every supported call has an independent implementation in the Sentry, that is unlikely to suffer from identical vulnerabilities that may appear in the host."
**Counterexample:** If a passthrough were permitted (as in ptrace-based sandboxes), a TOCTOU race could allow a malicious application to craft arguments that exploit a kernel bug after the sandbox has approved the syscall. gVisor avoids this by never letting the application's arguments reach the host kernel directly.
**Why this matters for bridge/orbit:** orbit's ShellExecutor passes commands directly to bash, which then invokes syscalls on the host with NO intermediation. This is the fundamental security gap gVisor's architecture eliminates.

### INV-NET-005: Outbound packets pass through a queueing discipline before link egress
**Core Invariant:**
```
∀ outbound packet p:
  enqueued(p, qdisc) → dequeued(p, qdisc) → written(p, link_endpoint)

Default qdisc = FIFO ⇒ ∀ packets p₁, p₂ where enqueue(p₁) happens-before enqueue(p₂):
  dequeue(p₁) happens-before dequeue(p₂)
```
**Source:** Networking guide: "Outgoing packets can be processed on different goroutines...until typically reaching a queueing discipline. There another goroutine writes batches of queued packets out the link endpoint. The default qdisc is FIFO; runsc can also configure TBF for egress traffic shaping."
**Counterexample:** If a packet bypasses the qdisc (e.g., written directly to the link endpoint from a syscall goroutine), it can reorder with respect to packets already queued. For TCP, this could trigger spurious retransmissions (out-of-order delivery looks like loss). For UDP, application-level ordering guarantees would break.
**Why this matters for bridge/orbit:** Bridge's audit log dispatch (non-repudiable delivery) has an ordering guarantee — all audit events from a given session must be delivered in order. If bridge used a userspace network stack, the qdisc model would be the pattern for enforcing that ordering.

### INV-NET-006: Host networking bypasses ALL netstack isolation
**Core Invariant:**
```
network_mode = host ⇒
  ¬INV-NET-001 ∧ ¬INV-NET-002 ∧ ¬INV-NET-004

i.e., with --network=host:
  - sentry CAN open host sockets (hostinet)
  - traffic does NOT transit AF_PACKET socket
  - syscalls use native Linux networking, not sentry emulation
```
**Source:** Networking guide: "gVisor can also be run with host networking via the --network=host flag. This uses the hostinet package, which trades the security and isolation of netstack for the performance of native Linux networking."
Security model: "The calls do not include the creation of new sockets (unless host networking mode is enabled)."
**Counterexample:** Running with `--network=host` and assuming the sandbox provides network isolation — it doesn't. The application can open raw sockets, bind to privileged ports, and interact with host network interfaces directly. This is NOT a sandbox mode; it's a performance mode that explicitly disables network isolation.
**Why this matters for bridge/orbit:** orbit must never use `--network=host` for any sandboxed execution. This is a hard design constraint: if performance requires host networking, the workload is not suitable for sandboxing.

### INV-NET-007: TCP async processing ≠ other protocols inline processing
**Core Invariant:**
```
∀ incoming packet p:
  protocol(p) = TCP ⇒ handled_async(p)  // enqueued, processed by TCP's own goroutines
  protocol(p) ≠ TCP ⇒ handled_inline(p)  // processed in dispatcher goroutine

This is an architectural choice, not a correctness invariant:
TCP requires complex state machines (congestion control, retransmit timers);
other protocols (UDP, ICMP, raw IP) are stateless enough for inline dispatch.
```
**Source:** Networking guide: "TCP packets are enqueued and asynchronously handled by the TCP implementation's own goroutines. Other protocols are handled inline, and the dispatcher goroutine handles all processing up to enqueueing packets at the socket where it can be read into userspace."
**Counterexample:** If a non-TCP protocol were mistakenly handled asynchronously, it could introduce a reordering window between enqueue and processing — benign for TCP (which has sequence numbers) but potentially corrupting for protocols that assume in-order delivery (e.g., UDP-based QUIC implementations that don't do their own reorder buffering). Conversely, if TCP were handled inline, a slow receiver could head-of-line block ALL protocol processing.
**Why this matters for bridge/orbit:** bridge's gRPC dispatch processes requests on a worker pool. The TCP/inline split is a model for separating stateful, long-running operations (like session dispatch) from stateless ones (like health checks). Stateful ops should have dedicated goroutines; stateless ops can be inline.

## Architecture Notes (non-invariants)

### Supported link layers
netstack supports AF_PACKET sockets, AF_XDP sockets, shared memory, and Go channels as link layers. The invariant is that the link layer abstraction is uniform — the rest of netstack does not know which link layer is in use. This is a design property, not a proven invariant.

### API stability
"netstack's API is fairly stable, it doesn't guarantee stability and is not published with Go module-style versions." This is an explicit non-guarantee — netstack's API may change without notice.

### Goroutine model
Link endpoints spawn goroutines for ingress. Qdisc has a dedicated goroutine for egress batching. TCP has its own goroutines. There is no single "netstack event loop" — it's a concurrent, goroutine-per-concern model.

## Trust Assessment
- **Source type:** oracle-extract (gVisor project documentation, not a textbook or standard)
- **Trust level:** MEDIUM (per source trust table)
- **Verification status:** NOT VERIFIED — these are claims from gVisor's own documentation, not independently tested against the source code. The security model page is maintained by the gVisor team and represents design intent. Production behavior should be verified against actual sentry seccomp filters and netstack source.
- **Note:** The gVisor team has a strong track record (zero sandbox-escape CVEs), so their design documentation carries more weight than typical project docs. But these are still self-reported claims — verify against source before using as gate criteria.

## Cross-references
- `source-cache/gvisor.md` — broader gVisor sandbox analysis (7 defense layers, CVEs, what orbit can adopt)
- `source-cache/saltzer-schroeder-oracle.md` — INV-NET-001 is an instance of Least Privilege (S-S principle #5)
- `source-cache/linux-kernel.md` — AF_PACKET socket semantics, VETH device model
- Axiom corpus categories: sandbox, architecture, systems
