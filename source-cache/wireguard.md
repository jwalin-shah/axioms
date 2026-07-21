# oracle/wireguard
Sources: https://www.wireguard.com/protocol/, WireGuard Technical Whitepaper (Donenfeld, NDSS 2017), Formal Verification Papers (Tamarin + CryptoVerif proofs)
Date pulled: 2026-07-21

## Contents
1. Key Exchange and Handshake State Machine
2. Packet Structure and Message Types
3. Replay Protection
4. Security Properties (Formally Verified)
5. Timer and Session Management

---

## 1. Key Exchange and Handshake State Machine

### INV-WG-KX-001: Noise IKpsk2 Protocol Invariant
**Core Invariant:**
```
∀WireGuard session S:
  handshake follows Noise_IKpsk2_25519_ChaChaPoly_BLAKE2s pattern
  4 DH operations: es (E_i, S_r), ss (S_i, S_r), ee (E_i, E_r), se (S_i, E_r)
```
**Source:** WireGuard Protocol Whitepaper Section 4
**Counterexample:** A handshake missing one of the four DH operations would lose authentication or forward secrecy properties.

### INV-WG-KX-002: Initiator Must Send First Data
**Core Invariant:**
```
∀WireGuard session S:
  responder receives HandshakeInitiation → sends HandshakeResponse
  initiator receives HandshakeResponse → sends first TransportData (key confirmation)
  responder MUST NOT send TransportData until receiving first TransportData from initiator
```
**Source:** WireGuard Protocol Whitepaper Section 4
**Counterexample:** A responder sending a data packet before the initiator's key confirmation, breaking forward secrecy.

### INV-WG-KX-003: Perfect Forward Secrecy per Rekey
**Core Invariant:**
```
∀rekey event:
  new ephemeral key pair (e'_i, e'_r) is generated
  new session keys derived via fresh DH(ee'), DH(es'), DH(se')
  old session keys are discarded (current → previous, new → current, previous-previous zeroed)
```
**Source:** WireGuard Protocol Whitepaper Section 5
**Counterexample:** Reusing the same ephemeral key pair across rekey events would allow past session key recovery if the static key is compromised.

### INV-WG-KX-004: Handshake Message Ordering
**Core Invariant:**
```
∀handshake H:
  sequence: HandshakeInitiation → HandshakeResponse → TransportData
  CookieReply may be sent at any point in response to invalid mac2
```
**Source:** WireGuard Protocol Whitepaper Section 4
**Counterexample:** A HandshakeResponse arriving before a HandshakeInitiation was sent.

### INV-WG-KX-005: Handshake Nonce Uniqueness
**Core Invariant:**
```
∀AEAD encryption within a single handshake message:
  nonce = 0 for all handshake encryptions
  associated_data = transcript_hash (H_i or H_r) ensures separation
  ⇒ same-nonce-different-AD is safe
```
**Source:** WireGuard Protocol Whitepaper Section 4
**Counterexample:** Encrypting two different fields under nonce=0 with the same associated data (nonce would repeat).

---

## 2. Packet Structure and Message Types

### INV-WG-PKT-001: Type Identifier Uniqueness
**Core Invariant:**
```
∀packet p:
  p.type ∈ {0x01, 0x02, 0x03, 0x04}
  0x01 = HandshakeInitiation | 0x02 = HandshakeResponse
  0x03 = CookieReply         | 0x04 = TransportData
```
**Source:** WireGuard Protocol Whitepaper Section 3
**Counterexample:** A packet with type byte = 0x05 being processed instead of silently dropped.

### INV-WG-PKT-002: Reserved Bytes Invariant
**Core Invariant:**
```
∀WireGuard message m:
  m.reserved = 0x000000 (3 zero bytes following type byte)
```
**Source:** WireGuard Protocol Whitepaper Section 3
**Counterexample:** Processing a packet with non-zero reserved bytes, enabling protocol ossification.

### INV-WG-PKT-003: Handshake Initiation Structure
**Core Invariant:**
```
∀HandshakeInitiation msg:
  msg.len = 148 bytes (1 + 3 + 4 + 32 + 48 + 28 + 16 + 16)
  fields: type(1) + reserved(3) + sender(4) + ephemeral(32) + encrypted_static(48) + encrypted_timestamp(28) + mac1(16) + mac2(16)
```
**Source:** WireGuard Protocol Whitepaper Section 3.1
**Counterexample:** A HandshakeInitiation with a truncated or padded field (would fail AEAD decryption).

### INV-WG-PKT-004: Handshake Response Structure
**Core Invariant:**
```
∀HandshakeResponse msg:
  msg.len = 92 bytes (1 + 3 + 4 + 4 + 32 + 16 + 16 + 16)
  fields: type(1) + reserved(3) + sender(4) + receiver(4) + ephemeral(32) + encrypted_empty(16) + mac1(16) + mac2(16)
```
**Source:** WireGuard Protocol Whitepaper Section 3.2
**Counterexample:** A HandshakeResponse with a non-empty encrypted payload (must be exactly 16 bytes: 0 bytes data + 16-byte AEAD tag).

### INV-WG-PKT-005: Transport Data Structure
**Core Invariant:**
```
∀TransportData msg:
  msg.len ≥ 32 bytes (1 + 3 + 4 + 8 + 16 min)
  fields: type(1) + reserved(3) + receiver(4) + counter(8) + encrypted_packet(variable + 16)
  counter is 8-byte little-endian nonce
```
**Source:** WireGuard Protocol Whitepaper Section 3.4
**Counterexample:** A TransportData message with a counter that decreases relative to the last message in the same session.

### INV-WG-PKT-006: Cookie Reply Structure
**Core Invariant:**
```
∀CookieReply msg:
  msg.len = 64 bytes (1 + 3 + 4 + 24 + 32)
  fields: type(1) + reserved(3) + receiver(4) + nonce(24) + encrypted_cookie(32)
```
**Source:** WireGuard Protocol Whitepaper Section 3.3
**Counterexample:** A CookieReply with invalid XChaCha20 nonce length (must be 24 bytes for XChaCha20).

### INV-WG-PKT-007: Cryptographic Primitive Fixity
**Core Invariant:**
```
∀WireGuard session:
  DH = Curve25519
  HASH = BLAKE2s (32-byte output)
  AEAD = ChaCha20Poly1305
  XAEAD = XChaCha20Poly1305
  KDF = HKDF-BLAKE2s
  MAC = Keyed-BLAKE2s
```
**Source:** WireGuard Protocol Whitepaper Section 2
**Counterexample:** Mixing SHA-256 for hashing and AES-GCM for AEAD would be non-WireGuard and break interoperability.

---

## 3. Replay Protection

### INV-WG-REP-001: Transport Counter Monotonicity
**Core Invariant:**
```
∀session S, ∀TransportData packet p:
  p.counter > max_received_counter(S)
  OR p.counter within sliding window AND not already received
```
**Source:** WireGuard Protocol Whitepaper Section 5.2
**Counterexample:** Accepting a TransportData packet with counter=5 after already receiving counter=5, enabling replay.

### INV-WG-REP-002: Sliding Window Rejection
**Core Invariant:**
```
∀received TransportData with counter c:
  if c < (max_counter - window_size): discard (outside window)
  if c ∈ received_bitmap: discard (duplicate)
  else: accept, update bitmap
  (algorithm per RFC 2401 Appendix C / RFC 6479)
```
**Source:** WireGuard Protocol Whitepaper Section 5.2
**Counterexample:** Accepting a packet with counter value far below the maximum (replay of old packet).

### INV-WG-REP-003: Handshake Timestamp Replay
**Core Invariant:**
```
∀HandshakeInitiation:
  responder caches (S_r_pub, S_i_pub, timestamp) tuples
  duplicate timestamp for same (S_r_pub, S_i_pub) → reject
```
**Source:** WireGuard Protocol Whitepaper Section 5.2
**Counterexample:** Replaying a captured HandshakeInitiation with the same timestamp. Without this check, an attacker could force repeated key exchanges.

### INV-WG-REP-004: Counter as AEAD Nonce
**Core Invariant:**
```
∀TransportData p:
  AEAD_nonce(p) = 0x00000000 || little_endian(p.counter)  // 12-byte nonce
  nonce uniqueness per session ensures AEAD safety
```
**Source:** WireGuard Protocol Whitepaper Section 3.4
**Counterexample:** Reusing a nonce value for two different transport data messages under the same session key (nonce reuse breaks ChaCha20Poly1305).

### INV-WG-REP-005: mac1 for Stealth
**Core Invariant:**
```
∀incoming packet p:
  computed_mac1 = KeyedBLAKE2s(label="mac1---", key=S_r_pub, msg=header)
  p.mac1 = computed_mac1 ⇒ process
  p.mac1 ≠ computed_mac1 ⇒ silent discard (no response)
```
**Source:** WireGuard Protocol Whitepaper Section 5.4
**Counterexample:** Responding to a packet with invalid mac1 (reveals presence of WireGuard peer to network scanners).

### INV-WG-REP-006: mac2 for DoS Mitigation
**Core Invariant:**
```
∀incoming packet under load:
  computed_mac2 = KeyedBLAKE2s(label="cookie--", key=cookie, msg=header)
  p.mac2 = computed_mac2 ⇒ process
  p.mac2 ≠ computed_mac2 ⇒ respond with CookieReply
```
**Source:** WireGuard Protocol Whitepaper Section 5.4
**Counterexample:** A peer accepting handshakes without mac2 when under load (amplification attack vector).

---

## 4. Security Properties (Formally Verified)

### INV-WG-SEC-001: Key Agreement (Tamarin-proved)
**Core Invariant:**
```
∀WireGuard session without key compromise:
  both parties agree on session key K_session
  (verified in Tamarin symbolic model)
```
**Source:** WireGuard Formal Verification Paper (Tamarin proof)
**Counterexample:** A session where initiator derives K_1 and responder derives K_2 ≠ K_1 (noise protocol failure).

### INV-WG-SEC-002: Key-Compromise Impersonation (KCI) Resistance
**Core Invariant:**
```
∀session where initiator static key S_i is compromised:
  responder still authenticates to initiator
  (compromise of S_i does not allow impersonation of responder to initiator)
```
**Source:** WireGuard Formal Verification Paper
**Counterexample:** An attacker with S_i creating a valid HandshakeResponse that initiator accepts.

### INV-WG-SEC-003: Forward Secrecy (CryptoVerif-proved)
**Core Invariant:**
```
∀session S where ephemeral keys remain uncompromised:
  compromise of static keys S_i, S_r at time t > t(S) does not reveal session key K_S
```
**Source:** WireGuard Formal Verification Paper (CryptoVerif), Whitepaper Section 8
**Counterexample:** Decrypting a recorded session after obtaining the static long-term keys, without the ephemerals.

### INV-WG-SEC-004: Unknown Key-Share (UKS) Resistance
**Core Invariant:**
```
∀all keys compromised (S_i, S_r, E_i, E_r):
  attacker cannot create ambiguity about which parties share K_session
```
**Source:** WireGuard Formal Verification Paper
**Counterexample:** An attacker arranging that A and B both think they're talking to C while actually talking to each other.

### INV-WG-SEC-005: PSK-Augmented Quantum Resistance
**Core Invariant:**
```
∀session using a PSK:
  PSK ≠ ⊥ ⇒ security holds even against quantum-capable adversary that breaks Curve25519
  (as long as PSK remains secret)
```
**Source:** WireGuard Protocol Whitepaper Section 7
**Counterexample:** A post-quantum attacker recording WireGuard traffic without PSK and later breaking Curve25519 to recover session keys.

### INV-WG-SEC-006: Identity Hiding (Responder Static)
**Core Invariant:**
```
∀WireGuard handshake:
  responder static key S_r is NEVER transmitted
  initiator static key S_i IS transmitted (encrypted, not forward secret)
```
**Source:** WireGuard Protocol Whitepaper Section 6
**Counterexample:** An observer learning the responder's static public key from the wire (would break identity hiding).

---

## 5. Timer and Session Management

### INV-WG-TMR-001: Session Key Lifetime
**Core Invariant:**
```
∀session S:
  max_age(S) = min(REJECT-AFTER-TIME, time_to_exhaust_REJECT-AFTER-MESSAGES)
  REJECT-AFTER-TIME = 180 seconds
  REJECT-AFTER-MESSAGES = 2^64 - 2^13 - 1
```
**Source:** WireGuard Protocol Whitepaper Section 5.1
**Counterexample:** A session older than 180 seconds still being accepted for encryption.

### INV-WG-TMR-002: Rekey Interval
**Core Invariant:**
```
∀active session S:
  sender initiates rekey after REKEY-AFTER-TIME = 120 seconds
  OR after REKEY-AFTER-MESSAGES = 2^64 - 2^16 - 1 messages sent
  whichever occurs first
```
**Source:** WireGuard Protocol Whitepaper Section 5.1
**Counterexample:** A session that persists without rekey for 5 minutes, reducing the window for PFS.

### INV-WG-TMR-003: Responder Rekey Stagger
**Core Invariant:**
```
∀responder:
  responder initiates rekey at REKEY-AFTER-TIME + REKEY-TIMEOUT × 2
  (= 120 + 5 × 2 = 130 seconds after session creation)
  prevents thundering herd: responder waits for initiator's rekey first
```
**Source:** WireGuard Protocol Whitepaper Section 5.1
**Counterexample:** Both ends initiating rekey simultaneously, causing duplicate handshake messages.

### INV-WG-TMR-004: Handshake Retry Backoff
**Core Invariant:**
```
∀failed handshake:
  interval between retries = 5 seconds (REKEY-TIMEOUT)
  total retry duration = 90 seconds (REKEY-ATTEMPT-TIME)
  each retry uses fresh ephemeral keys
  after REKEY-ATTEMPT-TIME: give up
```
**Source:** WireGuard Protocol Whitepaper Section 5.1
**Counterexample:** Retrying with exponentially increasing backoff (would delay reconnection after network recovery).

### INV-WG-TMR-005: No More Than One Initiation Per REKEY-TIMEOUT
**Core Invariant:**
```
∀peer P:
  rate(handshake_initiations(P)) ≤ 1 per REKEY-TIMEOUT (5 seconds)
```
**Source:** WireGuard Protocol Whitepaper Section 5.1
**Counterexample:** A peer sending handshake initiations every 100ms, overwhelming the responder.

### INV-WG-TMR-006: Three-Session Slot Invariant
**Core Invariant:**
```
∀peer P:
  P maintains at most 3 session slots: current, previous, next (unconfirmed responder)
  on new session: current → previous, next → current, previous-previous is zeroed
  after REJECT-AFTER-TIME × 3 with no new session: all zeroed
```
**Source:** WireGuard Protocol Whitepaper Section 5.1
**Counterexample:** Keeping unlimited old session slots (memory exhaustion) or keeping only one slot (disruption if rekey packet is lost).

### INV-WG-TMR-007: Keepalive Timer
**Core Invariant:**
```
∀peer P:
  P receives authenticated transport data AND nothing to send
    ⇒ P sends zero-length TransportData after KEEPALIVE-TIMEOUT (10 seconds)
  P receives no transport data for (KEEPALIVE_TIMEOUT + REKEY_TIMEOUT) seconds
    ⇒ P triggers new handshake
```
**Source:** WireGuard Protocol Whitepaper Section 5.1
**Counterexample:** A peer that received data but sends nothing for 30 seconds (the other peer may assume dead path).
