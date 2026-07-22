# oracle/networking-research — TCP and network design invariants

Source: Jacobson (1988), Clark (1982), RFC 1122, Saltzer-Reed-Clark (1984)
Date pulled: 2026-07-21
Trust level: textbook-formal (HIGH) for Jacobson, textbook-research (MEDIUM) for Clark/RFC

---

## INV-NET-016: TCP Self-Clocking — Conservation of Packets (Jacobson 1988)

**Core Invariant:**
```
∀ TCP connection in steady state:
  new_packets_injected ≤ packets_acknowledged
  A new segment is transmitted ONLY when an ACK arrives acknowledging a previously unacknowledged segment.
  ACK stream paces the sender to the bottleneck rate (self-clocking).

Invariant: cwnd segments in flight, each ACK triggers transmission of one new segment,
thus the sender never exceeds the rate at which the bottleneck can drain.
```

**Source:** Jacobson, V. "Congestion Avoidance and Control." ACM SIGCOMM 1988, pp. 314-329.
Original paper: http://ee.lbl.gov/papers/congavoid.pdf

Jacobson's 1988 paper introduced the **conservation of packets** principle: in equilibrium, a new packet should not be injected into the network until an old packet has left. TCP implements this via **self-clocking**: returning ACKs act as a clock, each ACK triggering the sender to transmit (at most) one new segment. This automatically paces the sender to the bottleneck link rate.

The paper identifies three ways conservation fails:
1. The sender injects a new packet before an old one has exited → fixed by better RTT/RTO estimator
2. The connection never reaches equilibrium → fixed by **slow-start** (cwnd starts at 1 MSS, exponential growth)
3. Equilibrium unreachable due to path/resource limits → fixed by **congestion avoidance** (AIMD: additive increase, multiplicative decrease)

The self-clocking property is the fundamental invariant: each ACK triggers exactly one new transmission in steady state. This is what gives TCP its stability — the sender cannot outrun the ACK stream.

**Counterexample:** A sender that transmits 10 segments on receiving 1 ACK. This breaks self-clocking and can cause congestion collapse (as seen in 1986 Internet collapse: LBL-to-Berkeley throughput dropped from 32 Kbps to ~40 bps when implementations broke this invariant).

---

## INV-NET-034: Silly Window Syndrome — Receiver-Side Avoidance (Clark 1982, RFC 1122)

**Core Invariant:**
```
∀ TCP receiver:
  do NOT advertise window increment δ unless:
  δ ≥ min(MSS, receiver_buffer/2)

Equivalently: suppress window updates for tiny increments.
The receiver waits until it can advertise at least one full-sized segment
(or half the buffer, whichever is smaller) before sending a window update.
```

**Source:** Clark, D.D. "Window and Acknowledgment Strategy in TCP." RFC 813, July 1982.
RFC 1122, Section 4.2.2.14 (SWS discussion) and Section 4.2.3.3 ("When to Send a Window Update").
https://datatracker.ietf.org/doc/html/rfc1122

Silly Window Syndrome (SWS) is a stable pattern of small incremental window movements resulting in extremely poor TCP performance. It occurs when the receiving application reads data very slowly (e.g., 1 byte at a time), freeing only small amounts of buffer space. A naive receiver advertises each tiny window increment, the sender transmits a tiny segment, which refills the buffer, and the cycle repeats.

**Clark's solution (receiver-side):** The receiver suppresses window updates until it can advertise at least min(MSS, buffer/2) of available space. This breaks the SWS cycle. Combined with Nagle's algorithm (sender-side: don't send tiny segments), SWS is prevented on both ends.

RFC 1122 formalized this:
- Section 4.2.3.3: "A TCP SHOULD implement the receiver-side SWS avoidance algorithm." The receiver must not send a window update for a small window increase.
- Section 4.2.3.4: Sender-side SWS avoidance (Nagle's algorithm).

**Counterexample:** A receiver application reads 1 byte from a full buffer. The receiver immediately advertises a 1-byte window. The sender transmits 1 byte with 40 bytes of headers (4,000% overhead). The buffer fills again. This cycle repeats indefinitely, causing near-zero throughput.

---

## INV-NET-045: End-to-End Encryption Invariant (Saltzer, Reed, Clark 1984)

**Core Invariant:**
```
∀ communication between parties A and B:
  confidentiality_guarantee(exists) ⇔ encryption_occurs_at(A, B)
  ¬∃ confidentiality from network_level_encryption(link_encryption)

∀ system_sensitive_data:
  must(encrypt_at(application_layer))
  ¬trust(network_core_encryption)

Network-level encryption protects against external eavesdroppers
but does NOT imply end-to-end confidentiality if intermediate nodes are compromised.
```

**Source:** Saltzer, J.H., Reed, D.P., and Clark, D.D. "End-to-End Arguments in System Design." ACM Transactions on Computer Systems, Vol. 2, No. 4, November 1984, pp. 277-288.
Full text: https://web.mit.edu/Saltzer/www/publications/endtoend/endtoend.txt

The end-to-end argument states that functions placed at low levels of a system may be redundant or of little value when compared with the cost of providing them at that low level. **Encryption (security)** is one of the paper's canonical examples:

1. The communication subsystem must be trusted to manage encryption keys securely — but the application already has to manage keys for authentication.
2. Data is in the clear and vulnerable as it passes from the network layer into the target host and up to the application.
3. The application must still verify message authenticity itself — network-level encryption doesn't replace application-level integrity.

The invariant: **network-level (link) encryption protects against external eavesdroppers but does not imply end-to-end confidentiality if intermediate nodes are compromised.** Only application-level encryption can guarantee that data is never exposed outside the application's trust boundary.

**Counterexample:** A system using TLS between load balancer and backend, but plaintext between client and load balancer. Network-level encryption exists on one hop, but data is exposed on another. This is not end-to-end encrypted — the load balancer sees plaintext. True end-to-end encryption requires the client to encrypt, the intended recipient to decrypt, and no intermediate node to see plaintext.
