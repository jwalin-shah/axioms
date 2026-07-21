# oracle/http2-quic
Sources: RFC 8999 (QUIC Invariants), RFC 9000 (QUIC Transport), RFC 9001 (QUIC+TLS), RFC 9113 (HTTP/2), RFC 9114 (HTTP/3)
Date pulled: 2026-07-21

## Contents
1. HTTP/2 Stream Multiplexing (RFC 9113 Section 5)
2. HTTP/2 Flow Control (RFC 9113 Section 5.2)
3. QUIC Packet Number Monotonicity (RFC 9000 Section 12.3)
4. QUIC Version-Independent Invariants (RFC 8999)
5. QUIC Connection Migration (RFC 9000 Section 9)
6. QUIC Loss Detection and Congestion Control (RFC 9000, RFC 9002)
7. HTTP/3 Stream Types and Unidirectional Stream Guarantees (RFC 9114)
8. QUIC Cryptographic Handshake (RFC 9001)

---

## 1. HTTP/2 Stream Multiplexing

### INV-H2-STR-001: Stream ID Parity Assignment
**Core Invariant:**
```
∀stream s:
  (s.initiated_by_client ⇒ s.id MOD 2 = 1)
  ∧ (s.initiated_by_server ⇒ s.id MOD 2 = 0)
```
**Source:** RFC 9113 Section 5.1.1
**Counterexample:** A client-initiated stream with even ID or a server-push stream with odd ID.

### INV-H2-STR-002: Monotonic Stream ID Ordering
**Core Invariant:**
```
∀endpoint E, ∀streams S = {s_1, s_2, ..., s_n} opened by E in order:
  s_1.id < s_2.id < ... < s_n.id
  (stream identifiers MUST be numerically greater than all previously opened or reserved streams)
```
**Source:** RFC 9113 Section 5.1.1
**Counterexample:** Opening stream 5 after stream 3 (both client-initiated), then opening stream 3 would cause PROTOCOL_ERROR.

### INV-H2-STR-003: No Stream ID Reuse
**Core Invariant:**
```
∀connection C:
  stream_id is used at most once across the entire lifetime of C
```
**Source:** RFC 9113 Section 5.1.1
**Counterexample:** Exhausting stream IDs on a long-lived connection; at that point, client must open a new connection or GOAWAY.

### INV-H2-STR-004: Stream ID Skip Implicit Close
**Core Invariant:**
```
∀stream s opened by endpoint E with numeric gap:
  (∀id' where s.id < id' < next_used_id and id' could have been opened by peer):
    state(id') = CLOSED
```
**Source:** RFC 9113 Section 5.1.1
**Counterexample:** Receiving a HEADERS frame on a previously-skipped stream ID after a higher one was used.

### INV-H2-STR-005: Stream State Machine Transitions
**Core Invariant:**
```
∀stream s:
  valid_transitions(s) ⊆:
    IDLE → {OPEN, RESERVED_LOCAL, RESERVED_REMOTE, CLOSED}
    OPEN → {HALF_CLOSED_LOCAL, HALF_CLOSED_REMOTE, CLOSED}
    HALF_CLOSED_LOCAL → {HALF_CLOSED_REMOTE, CLOSED}
    HALF_CLOSED_REMOTE → {CLOSED}
    RESERVED_{LOCAL,REMOTE} → {HALF_CLOSED_REMOTE, CLOSED}
```
**Source:** RFC 9113 Section 5.1, Stream State Machine
**Counterexample:** Sending a HEADERS frame on a stream in HALF_CLOSED_REMOTE state (STREAM_CLOSED error).

### INV-H2-STR-006: Frame Type Permissions Per State
**Core Invariant:**
```
∀frame f received on stream s in state st:
  allowed_frame_type(f, st) = {
    DATA      → {OPEN, HALF_CLOSED_REMOTE}
    HEADERS   → {IDLE, OPEN, HALF_CLOSED_REMOTE}
    PRIORITY  → any state including CLOSED
    RST_STREAM → {OPEN, HALF_CLOSED_LOCAL, HALF_CLOSED_REMOTE}
    ...
  }
```
**Source:** RFC 9113 Section 5.1
**Counterexample:** Receiving a DATA frame after receiving END_STREAM (state: HALF_CLOSED_LOCAL) triggers stream error STREAM_CLOSED.

### INV-H2-STR-007: Stream Concurrency Limit
**Core Invariant:**
```
∀connection C:
  |active_streams(C)| ≤ SETTINGS_MAX_CONCURRENT_STREAMS
  where active_streams = streams in {OPEN, HALF_CLOSED(REMOTE|LOCAL)}
```
**Source:** RFC 9113 Section 5.1.2
**Counterexample:** Opening more streams than the peer advertised in SETTINGS_MAX_CONCURRENT_STREAMS.

### INV-H2-STR-008: RST_STREAM Loop Prevention
**Core Invariant:**
```
∀endpoint E:
  E MUST NOT send RST_STREAM in response to an RST_STREAM
```
**Source:** RFC 9113 Section 5.3
**Counterexample:** Echoing an RST_STREAM back to the sender, creating a reset loop.

---

## 2. HTTP/2 Flow Control

### INV-H2-FLOW-001: Window-Based Credit Semantics
**Core Invariant:**
```
∀connection C, ∀stream s in C:
  bytes_sent(s) ≤ window(s) + Σ(WINDOW_UPDATE increments for s)
  bytes_sent_total(C) ≤ connection_window + Σ(WINDOW_UPDATE for C)
```
**Source:** RFC 9113 Section 5.2
**Counterexample:** Sending more DATA bytes than the peer's advertised window.

### INV-H2-FLOW-002: Only DATA Frames Are Flow-Controlled
**Core Invariant:**
```
∀non-DATA frame f:
  f is not subject to flow control
```
**Source:** RFC 9113 Section 5.2
**Counterexample:** A SETTINGS or HEADERS frame being blocked by a closed flow-control window.

### INV-H2-FLOW-003: Two-Level Flow Control
**Core Invariant:**
```
∀DATA frame f:
  bytes(consumed(f)) ≤ min(stream_window(s(f)), connection_window(C))
```
**Source:** RFC 9113 Section 5.2
**Counterexample:** A stream with adequate stream-level window but exhausted connection-level window sending data.

### INV-H2-FLOW-004: Initial Window Invariant
**Core Invariant:**
```
∀new stream s, ∀new connection C:
  initial_window(s) = initial_window(C) = 65535 octets
```
**Source:** RFC 9113 Section 5.2.1
**Counterexample:** A fresh stream starting with a window smaller than the default (unless SETTINGS changes it before stream creation).

---

## 3. QUIC Packet Number Monotonicity

### INV-QUIC-PN-001: Strictly Increasing Packet Numbers
**Core Invariant:**
```
∀connection C, ∀packet_number_space pns ∈ {Initial, Handshake, ApplicationData}:
  pkts(pns) = sorted by packet_number ascending
  ∀i < j: pkt_i.pn < pkt_j.pn
  packet_numbers are NEVER reused in the same space within a connection
```
**Source:** RFC 9000 Section 12.3
**Counterexample:** Retransmitting the same data with the same packet number would create ambiguity (the reason QUIC separates transmission from delivery sequence numbers).

### INV-QUIC-PN-002: Packet Number Space Isolation
**Core Invariant:**
```
∀connection C:
  packet_numbers in Initial space, Handshake space, and ApplicationData space are independent
  retransmission boundaries do NOT cross spaces
```
**Source:** RFC 9000 Section 12.3
**Counterexample:** An ACK for the Initial space being applied to ApplicationData space packets.

### INV-QUIC-PN-003: Packet Number Exhaustion
**Core Invariant:**
```
∀connection C:
  max_packet_number ≥ 2^62 - 1 ⇒ sender MUST close connection without CONNECTION_CLOSE
```
**Source:** RFC 9000 Section 12.3
**Counterexample:** Wrapping around to packet number 0 after reaching 2^62-1 would break monotonicity.

### INV-QUIC-PN-004: Packet Number Encoding
**Core Invariant:**
```
∀QUIC packet p:
  p.packet_number ∈ [0, 2^62 - 1)
  encoded_length = 1, 2, or 4 bytes (truncated, with largest encoded bit indicating length)
```
**Source:** RFC 9000 Section 12.3, Section 17.1
**Counterexample:** A packet number requiring more than 4 bytes or encoded with an unsupported truncated length.

---

## 4. QUIC Version-Independent Invariants (RFC 8999)

### INV-QUIC-INV-001: Long Header Form
**Core Invariant:**
```
∀QUIC packet with long header:
  first_byte MSB = 1
  version_field = 32-bit identifier (value 0x00000000 reserved for Version Negotiation)
```
**Source:** RFC 8999 Section 4
**Counterexample:** A packet that claims to be long header but has MSB = 0, or a non-VN packet with version 0.

### INV-QUIC-INV-002: Short Header Form
**Core Invariant:**
```
∀QUIC packet with short header:
  first_byte MSB = 0
  destination_connection_id immediately follows first byte (length NOT encoded in packet)
```
**Source:** RFC 8999 Section 4
**Counterexample:** A short-header packet where the Connection ID length is ambiguous (no length field in short header).

### INV-QUIC-INV-003: Version Negotiation Packet
**Core Invariant:**
```
∀Version Negotiation packet VNP:
  VNP.HeaderForm = 1 (long header)
  VNP.Version = 0x00000000
  VNP contains list of Supported Version (32-bit each)
  VNP is NOT integrity protected
  VNP MUST copy received Source Connection ID into outgoing Destination Connection ID
```
**Source:** RFC 8999 Section 6
**Counterexample:** A VN packet with integrity protection that could be discarded by intermediaries, or one that does not swap the Connection IDs.

### INV-QUIC-INV-004: Connection ID Opaqueness
**Core Invariant:**
```
∀connection ID cid:
  cid is opaque (no version-specific semantics required for lower layers)
  length ∈ [0, 2040] bits (0-255 bytes)
  multiple CID values may be used for the same connection
```
**Source:** RFC 8999 Section 5
**Counterexample:** A load balancer parsing a Connection ID for routing and misrouting after a version upgrade.

---

## 5. QUIC Connection Migration

### INV-QUIC-MIG-001: Client-Initiated Migration Only (v1)
**Core Invariant:**
```
∀QUIC v1 connection:
  only client may initiate non-probing migration
  server does NOT send non-probing packets to a new client address until receiving a non-probing packet from that address
```
**Source:** RFC 9000 Section 9
**Counterexample:** A server proactively migrating the connection to a different client address.

### INV-QUIC-MIG-002: Path Validation Before Migration
**Core Invariant:**
```
∀new candidate path P:
  send PATH_CHALLENGE on P
  wait for valid PATH_RESPONSE with same data
  ⇒ P is validated → may migrate
```
**Source:** RFC 9000 Section 8.2
**Counterexample:** Sending non-probing application data over an unvalidated path (vulnerable to off-path injection).

### INV-QUIC-MIG-003: Congestion State Reset on Path Change
**Core Invariant:**
```
∀connection migrating from old_path to new_path:
  packets_sent_on(old_path) NOT counted in new_path congestion control
  RTT_estimator reset to initial values for new_path
  (port-only changes MAY retain congestion/RTT state)
```
**Source:** RFC 9000 Section 9.4
**Counterexample:** Retaining a congestion window calibrated for a high-RTT cellular path when migrating to a low-RTT WiFi path (potential burst).

### INV-QUIC-MIG-004: Preferred Address Advertisement
**Core Invariant:**
```
∀server with preferred_address transport parameter:
  (server_ip, server_port) is used for initial connection
  client MAY migrate to preferred_address after handshake completes
  server MUST continue to accept packets at the original address after advertising preferred_address
```
**Source:** RFC 9000 Section 9.6
**Counterexample:** The server abandoning the original address after the client migrates, losing in-flight packets.

---

## 6. QUIC Loss Detection and Congestion Control

### INV-QUIC-LOSS-001: No ACK Renege
**Core Invariant:**
```
∀ACK frame ack:
  once a packet number is declared ACKed, it MUST NOT be "un-acked" (reneged) later
```
**Source:** RFC 9000 Section 13.2, RFC 9002
**Counterexample:** TCP-style selective ACK reneging where a previously ACKed range is later retracted.

### INV-QUIC-LOSS-002: Separate Loss Detection Per Space
**Core Invariant:**
```
∀packet_number_space pns:
  loss_detection(pns) is independent of other spaces
  ACKs for pns only trigger retransmission within pns
```
**Source:** RFC 9000 Section 12.3
**Counterexample:** An Initial-space ACK confirming Handshake-space packet delivery (impossible due to key availability).

### INV-QUIC-LOSS-003: Congestion Window Initialization
**Core Invariant:**
```
∀connection C:
  initial_congestion_window = min(10 * max_datagram_size, max(14720, 2 * max_datagram_size))
  slow_start exits on first packet loss
  RTO re-enters slow start
```
**Source:** RFC 9002 Section 7
**Counterexample:** Starting with a congestion window of 1 MSS (TCP-style) would severely limit QUIC's initial throughput.

### INV-QUIC-LOSS-004: Non-Ack-Eliciting Packet Neutrality
**Core Invariant:**
```
∀packet p containing only ACK or CONNECTION_CLOSE frames:
  p is not counted in congestion control limits (bytes_in_flight)
```
**Source:** RFC 9000 (verified errata EID 8240)
**Counterexample:** Pure ACK packets consuming congestion window budget.

---

## 7. HTTP/3 Stream Types and Unidirectional Stream Guarantees

### INV-H3-STR-001: Single Request per Stream (Client)
**Core Invariant:**
```
∀client-initiated bidirectional stream s:
  client sends exactly one request on s
  multiple requests on s ⇒ malformed (H3_INTERNAL_ERROR or similar)
```
**Source:** RFC 9114 Section 4.1
**Counterexample:** Pipelining HTTP requests on a single HTTP/3 stream (HTTP/1.1 or HTTP/2 pipelining behavior).

### INV-H3-STR-002: Single Control Stream Per Endpoint
**Core Invariant:**
```
∀endpoint E, ∀connection C:
  |control_streams(E, C)| = 1
  control stream type = 0x00
  first frame on control stream MUST be SETTINGS
```
**Source:** RFC 9114 Section 6.2.1
**Counterexample:** A peer opening a second control stream or omitting SETTINGS as the first frame (H3_MISSING_SETTINGS error).

### INV-H3-STR-003: Control Stream Persistence
**Core Invariant:**
```
∀control stream cs:
  sender MUST NOT close cs
  receiver MUST NOT request sender to close cs
  closure of either endpoint's cs ⇒ connection error H3_CLOSED_CRITICAL_STREAM
```
**Source:** RFC 9114 Section 6.2.1
**Counterexample:** Closing the control stream and attempting to reuse the connection without the ability to send SETTINGS or GOAWAY.

### INV-H3-STR-004: Push Stream Source Restriction
**Core Invariant:**
```
∀push stream ps:
  ps.initiator = server
  client → server push stream ⇒ H3_STREAM_CREATION_ERROR
```
**Source:** RFC 9114 Section 6.2.2
**Counterexample:** A client initiating a push stream (only servers push).

### INV-H3-STR-005: Push ID Uniqueness
**Core Invariant:**
```
∀push ID pid:
  pid appears at most once in a push stream header
  pid ≤ MAX_PUSH_ID value sent by client
```
**Source:** RFC 9114 Section 4.6
**Counterexample:** A server sending a push ID that exceeds the client's MAX_PUSH_ID limit.

### INV-H3-STR-006: Frame Type Permissions by Stream
**Core Invariant:**
```
∀frame type ft, ∀stream type st:
  allowed(ft, st) as per RFC 9114 Table 1:
    DATA        → {request, push}
    HEADERS     → {request, push}
    SETTINGS    → {control} (first frame only)
    GOAWAY      → {control}
    MAX_PUSH_ID → {control} (client-only)
    CANCEL_PUSH → {control}
    PUSH_PROMISE → {request} (server-only, never on control stream or push stream)
```
**Source:** RFC 9114 Section 7.2, Table 1
**Counterexample:** A PUSH_PROMISE frame received on a control stream (H3_FRAME_UNEXPECTED error).

### INV-H3-STR-007: Unidirectional Stream Minimum Requirements
**Core Invariant:**
```
∀connection C:
  transport params allow ≥ 3 unidirectional streams from peer
  at least 1024 bytes of flow-control credit per unidirectional stream SHOULD be provided
```
**Source:** RFC 9114 Section 6.2
**Counterexample:** Advertising zero unidirectional stream flow-control credit, preventing the peer from opening its control stream.

### INV-H3-STR-008: Unknown Stream Type Tolerance
**Core Invariant:**
```
∀unknown unidirectional stream type unknown_typ:
  recipient MUST abort reading OR discard data silently
  unknown stream types must NOT trigger connection error
```
**Source:** RFC 9114 Section 6.2
**Counterexample:** Disconnecting when encountering an unknown stream type (future extension).

---

## 8. QUIC Cryptographic Handshake (1-RTT / 0-RTT)

### INV-QUIC-TLS-001: ALPN Selection
**Core Invariant:**
```
∀HTTP/3 over QUIC connection:
  ALPN token = "h3" selected in TLS handshake
  (HTTP/3 relies on QUIC v1 as the underlying transport)
```
**Source:** RFC 9114 Section 1
**Counterexample:** Negotiating HTTP/2 over QUIC (not a defined protocol).

### INV-QUIC-TLS-002: 0-RTT Setting Compatibility
**Core Invariant:**
```
∀0-RTT connection:
  client uses stored settings from previous session
  server MUST NOT accept 0-RTT if stored settings are incompatible with current settings
  if server accepts 0-RTT, its SETTINGS MUST NOT reduce limits violated by client 0-RTT data
  omission of previously-non-default setting after accepting 0-RTT ⇒ H3_SETTINGS_ERROR
```
**Source:** RFC 9114 Section 3.3
**Counterexample:** Accepting 0-RTT data then sending a SETTINGS frame with lower MAX_HEADER_LIST_SIZE than the client observed previously.

### INV-QUIC-TLS-003: 1-RTT SETTINGS Availability
**Core Invariant:**
```
∀1-RTT connection:
  1-RTT keys become available before SETTINGS is processed by QUIC
```
**Source:** RFC 9114 Section 3.3
**Counterexample:** Server SETTINGS arriving in a 0-RTT packet before 1-RTT keys are available (would be unreadable).

### INV-QUIC-TLS-004: Server Name Indication
**Core Invariant:**
```
∀HTTP/3 client using domain-name-identified authority:
  client MUST send SNI TLS extension
```
**Source:** RFC 9114 Section 3.1
**Counterexample:** Omitting SNI for a virtual-hosted origin (connection may be rejected).

### INV-QUIC-TLS-005: Origin Certificate Match
**Core Invariant:**
```
∀HTTP/3 connection:
  client MUST verify server certificate matches the URI's origin server
  verification failure ⇒ client MUST NOT consider server authoritative
```
**Source:** RFC 9114 Section 3.1
**Counterexample:** Accepting data from a server whose certificate does not match the origin (man-in-the-middle attack).
