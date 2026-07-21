# oracle/tls13
Source: RFC 8446
Date pulled: 2026-07-21

## Contents
1. Handshake State Machine (RFC 8446 Sections 2, 4)
2. Key Derivation Schedule (RFC 8446 Section 7.1)
3. Cryptographic Guarantees (RFC 8446 Sections E.1, C)
4. Record Protocol (RFC 8446 Section 5)
5. HelloRetryRequest Invariants (RFC 8446 Section 4.1.2)

---

## 1. Handshake State Machine

### INV-TLS13-HS-001: Message Ordering Invariant
**Core Invariant:**
```
∀TLS 1.3 handshake H:
  H.messages occur in the order defined in Section 4.4.1:
    Phase 1 (Key Exchange): ClientHello → ServerHello
    Phase 2 (Server Parameters): EncryptedExtensions [CertificateRequest]
    Phase 3 (Authentication): [Certificate] [CertificateVerify] Finished
  peer receiving message in unexpected order → abort with "unexpected_message" alert
```
**Source:** RFC 8446 Section 4.4.1, Section 2
**Counterexample:** A server sending Certificate before EncryptedExtensions would break the expected order and MUST be rejected.

### INV-TLS13-HS-002: Post-Handshake Message Restriction
**Core Invariant:**
```
∀post-handshake connection state:
  only {NewSessionTicket, PostHandshakeAuth, KeyUpdate} messages are permitted
```
**Source:** RFC 8446 Section 4.6
**Counterexample:** A server sending a CertificateRequest long after the handshake and expecting a Certificate from a client that did not advertise post-handshake auth.

### INV-TLS13-HS-003: Renegotiation Prohibition
**Core Invariant:**
```
∀server that negotiated TLS 1.3:
  receiving another ClientHello on the same connection → MUST terminate with "unexpected_message"
```
**Source:** RFC 8446 Section 4.6
**Counterexample:** A TLS 1.2 style renegotiation attempt on a TLS 1.3 connection.

### INV-TLS13-HS-004: Encryption Layer Invariant
**Core Invariant:**
```
∀handshake message m:
  m after ServerHello → encrypted with [sender]_handshake_traffic_secret
  m after server Finished → encrypted with [sender]_application_traffic_secret_N
  Application data before Finished → forbidden (except 0-RTT, Section 2.3)
```
**Source:** RFC 8446 Section 2, Section 4
**Counterexample:** An application data record being sent before the server Finished message (leaks plaintext).

### INV-TLS13-HS-005: Three-Phase Handshake
**Core Invariant:**
```
∀TLS 1.3 full handshake:
  1. Key Exchange:     ClientHello + ServerHello (establishes shared key)
  2. Server Parameters: EncryptedExtensions + optional CertificateRequest
  3. Authentication:   Certificate + CertificateVerify + Finished (server then client)
```
**Source:** RFC 8446 Section 2
**Counterexample:** Skipping the ServerHello and going directly to authentication (no shared key material).

### INV-TLS13-HS-006: Finished Message Authentication
**Core Invariant:**
```
∀handshake:
  Finished = HMAC(handshake_derived_key, transcript_hash(all_previous_handshake_messages))
  client waits for server Finished before sending application data
  server waits for client Finished before sending application data
```
**Source:** RFC 8446 Section 4.4.4
**Counterexample:** Accepting a Finished message whose MAC was computed over a different transcript (cut-and-paste attack).

---

## 2. Key Derivation Schedule

### INV-TLS13-KDF-001: One-Way State Transitions
**Core Invariant:**
```
∀key schedule states S_i, S_j:
  S_i → S_j (via HKDF-Extract)
  irreversible: no transition back from S_j to S_i
  Stage ordering: 0 → EarlySecret → HandshakeSecret → MasterSecret
```
**Source:** RFC 8446 Section 7.1
**Counterexample:** Deriving EarlySecret from HandshakeSecret (backwards extraction would break forward secrecy).

### INV-TLS13-KDF-002: HKDF-Extract Chain
**Core Invariant:**
```
Early_Secret     = HKDF-Extract(salt=0,       IKM=PSK)
Handshake_Secret = HKDF-Extract(salt=Derived_Early_Secret, IKM=(EC)DHE)
Master_Secret    = HKDF-Extract(salt=Derived_Handshake_Secret, IKM=0)
```
**Source:** RFC 8446 Section 7.1
**Counterexample:** Skipping the (EC)DHE mixing in the Handshake Secret derivation would lose forward secrecy.

### INV-TLS13-KDF-003: Label Uniqueness for Domain Separation
**Core Invariant:**
```
∀Derive-Secret calls producing distinct secrets:
  each uses a unique label:
    "tls13 derived"       — state transition chaining
    "tls13 c e traffic"   — client early traffic
    "tls13 c hs traffic"  — client handshake traffic
    "tls13 s hs traffic"  — server handshake traffic
    "tls13 c ap traffic"  — client app traffic
    "tls13 s ap traffic"  — server app traffic
    "tls13 exp master"    — exporter master secret
    "tls13 res master"    — resumption master secret
    "tls13 e exp master"  — early exporter master secret
```
**Source:** RFC 8446 Section 7.1, Section 4.6.1
**Counterexample:** Two different secrets derived with the same label (would produce identical keying material, violating domain separation).

### INV-TLS13-KDF-004: Transcript Binding
**Core Invariant:**
```
∀Derive-Secret(secret, label, messages):
  messages = transcript_hash(all_handshake_messages up to current point)
  ∀secrets derived from the same secret but different transcripts:
    secrets are distinct (with overwhelming probability)
```
**Source:** RFC 8446 Section 7.1
**Counterexample:** A truncated transcript that omitted a handshake message (adversary could swap extensions).

### INV-TLS13-KDF-005: Cipher Suite Hash Determination
**Core Invariant:**
```
∀negotiated cipher suite CS:
  hash_algorithm(CS) ∈ {SHA-256, SHA-384}
  AES_128_GCM_SHA256     → SHA-256
  AES_256_GCM_SHA384     → SHA-384
  CHACHA20_POLY1305_SHA256 → SHA-256
  all subsequent HKDF operations use this hash
```
**Source:** RFC 8446 Section 7.1, Cipher Suite registry
**Counterexample:** Deriving keys with SHA-384 after negotiating AES_128_GCM_SHA256 (produces mismatched key sizes).

### INV-TLS13-KDF-006: Handshake/Master Secret Separation
**Core Invariant:**
```
Master_Secret = HKDF-Extract(Derived_Handshake_Secret, 0)
  (zero IKM — no new entropy)
  handshake traffic keys derived from Handshake_Secret BEFORE server Finished
  application traffic keys derived from Master_Secret AFTER handshake complete
```
**Source:** RFC 8446 Section 7.1
**Counterexample:** Deriving application traffic keys from Handshake_Secret directly — would reveal them to the handshake encryption context.

---

## 3. Cryptographic Guarantees

### INV-TLS13-CRYPTO-001: Forward Secrecy
**Core Invariant:**
```
∀full TLS 1.3 session S:
  Handshake_Secret = HKDF-Extract(Derived_Early_Secret, (EC)DHE)
  (EC)DHE is ephemeral per-session ⇒ compromise of long-term key does not reveal past session keys
```
**Source:** RFC 8446 Section 7.1, Appendix E.1
**Counterexample:** Using a static Diffie-Hellman key (TLS 1.2-style) that, when compromised, decrypts all past sessions.

### INV-TLS13-CRYPTO-002: Downgrade Detection via Server Random
**Core Invariant:**
```
∀ServerHello SH:
  SH.negotiated_version = TLS 1.2
    ⇒ SH.random[24:] = 44 4F 57 4E 47 52 44 01
  SH.negotiated_version ≤ TLS 1.1
    ⇒ SH.random[24:] = 44 4F 57 4E 47 52 44 00
  TLS 1.3 client checking:
    SH.random[24:] ∈ {DOWNGRADE_TLS12, DOWNGRRADE_TLS11}
    ⇒ abort with "illegal_parameter"
```
**Source:** RFC 8446 Section 4.1.3
**Counterexample:** A TLS 1.3 client that does not check the last 8 bytes of ServerHello.random against the downgrade sentinels would accept a downgrade to TLS 1.2 without detecting it.

### INV-TLS13-CRYPTO-003: No Static RSA Key Exchange
**Core Invariant:**
```
∀TLS 1.3 ciphersuite:
  key_exchange_method ∈ {DHE, PSK, PSK_DHE}
  static RSA encryption (RFC 5246) is NOT used
```
**Source:** RFC 8446 Section 2
**Counterexample:** A server offering TLS_RSA_WITH_AES_128_CBC_SHA (a TLS 1.2 suite without forward secrecy).

### INV-TLS13-CRYPTO-004: Key Usage Limits
**Core Invariant:**
```
∀AEAD key k:
  AES-GCM: ≤ 2^23 encrypted records
  AES-CCM: ≤ 2^23 encrypted records
  ChaCha20-Poly1305: ≤ 2^23 encrypted records (AEAD_limit according to Section 5.5)
```
**Source:** RFC 8446 Section 5.5
**Counterexample:** Encrypting 2^24 records under the same AES-GCM key (nonce collision near 2^24.5 due to GCM's birthday bound).

### INV-TLS13-CRYPTO-005: AEAD-Only Record Protection
**Core Invariant:**
```
∀TLS 1.3 record:
  encryption_algorithm ∈ AEAD_SUITES
  no support for CBC-mode MAC-then-encrypt (removed from TLS 1.3)
```
**Source:** RFC 8446 Section 5.2
**Counterexample:** A TLS 1.3 implementation supporting TLS_CBC cipher suites (Lucky13 attack vector).

---

## 4. Record Protocol

### INV-TLS13-REC-001: Content Type Encryption
**Core Invariant:**
```
∀TLSCiphertext record:
  opaque_type = 23 (application_data) for all encrypted records
  actual content_type is encrypted inside the AEAD payload
  inner content_type ∈ {22, 23, 24}  (handshake, application_data, alert)
```
**Source:** RFC 8446 Section 5.2
**Counterexample:** An intermediary seeing "alert" as the outer content type and blocking the connection; the outer content type is always 23.

### INV-TLS13-REC-002: Record Padding
**Core Invariant:**
```
∀TLSCiphertext record:
  zero_padding MAY be appended to obscure plaintext length
  padding_len + real_payload_len < 2^14 + 1
  padding bytes are zero and stripped before decryption output
```
**Source:** RFC 8446 Section 5.4
**Counterexample:** Sending padded records that leak length information due to inconsistent padding patterns.

### INV-TLS13-REC-003: Sequence Number for Nonce Construction
**Core Invariant:**
```
∀AEAD encryption with key k:
  nonce = xor(static_iv(k), write_seq_num)   // 64-bit sequence number zero-extended
  write_seq_num increments by 1 per record
  write_seq_num wraps ⇒ connection MUST close
```
**Source:** RFC 8446 Section 5.3
**Counterexample:** Reusing a nonce for two records under the same key (AEAD security violation, catastrophic for GCM).

### INV-TLS13-REC-004: Single Record Per Handshake Message
**Core Invariant:**
```
∀handshake message m:
  m MAY be fragmented across multiple records
  records for different handshake messages MUST NOT be coalesced into a single handshake struct
```
**Source:** RFC 8446 Section 5.1
**Counterexample:** Two separate handshake types (Certificate + CertificateVerify) packed into a single handshake record.

---

## 5. HelloRetryRequest Invariants

### INV-TLS13-HRR-001: HRR Detection
**Core Invariant:**
```
∀ServerHello SH:
  SH.random = SHA-256("HelloRetryRequest")
             = CF21AD74E59A6111BE1D8C021E65B891C2A211167ABB8C5E079E09E2C8A8339C
  ⇒ SH is a HelloRetryRequest, not a real ServerHello
```
**Source:** RFC 8446 Section 4.1.2
**Counterexample:** A naive implementation comparing bytes instead of the hash would miss the specific HRR pattern.

### INV-TLS13-HRR-002: Single HRR Only
**Core Invariant:**
```
∀connection C:
  |HRR_messages_in_C| ≤ 1
  receiving a second HRR (client already responded to first HRR) ⇒ abort with "unexpected_message"
```
**Source:** RFC 8446 Section 4.1.2
**Counterexample:** A server cycling through key_share groups infinitely by repeatedly sending HRR.

### INV-TLS13-HRR-003: Cipher Suite Consistency
**Core Invariant:**
```
∀connection that received HRR:
  cipher_suite(ServerHello) = cipher_suite(HelloRetryRequest)
```
**Source:** RFC 8446 Section 4.1.2
**Counterexample:** A server offering AES_128_GCM_SHA256 in HRR but returning AES_256_GCM_SHA384 in ServerHello.

### INV-TLS13-HRR-004: Second ClientHello Modifications
**Core Invariant:**
```
∀second ClientHello after HRR:
  key_share = single entry from HRR-indicated group
  early_data is removed if previously present
  cookie extension is included if HRR provided one
  pre_shared_key binder and obfuscated_ticket_age are recomputed
```
**Source:** RFC 8446 Section 4.1.2
**Counterexample:** The client sending the same key_share as the initial ClientHello (would result in no change, triggering HRR idempotency check).

### INV-TLS13-HRR-005: HRR Idempotency Check
**Core Invariant:**
```
∀initial ClientHello C1, ∀HRR:
  if C1 would equal the second ClientHello (no changes needed):
    client MUST abort with "illegal_parameter"
```
**Source:** RFC 8446 Section 4.1.2
**Counterexample:** Accepting an HRR that requires no change to the ClientHello (infinite loop between client and server).

### INV-TLS13-HRR-006: Transcript Persistence
**Core Invariant:**
```
∀handshake after HRR:
  transcript = SHA256(ClientHello1 || HelloRetryRequest || ClientHello2 || ...)
  transcript is NOT reset between ClientHello1 and ClientHello2
```
**Source:** RFC 8446 Section 4.1.2
**Counterexample:** Using only ClientHello2 for the transcript (would allow dropping key_share negotiation from transcript, undermining downgrade protection).

### INV-TLS13-HRR-007: Extension Origin Restriction
**Core Invariant:**
```
∀extension ext in HelloRetryRequest:
  ext was offered in the initial ClientHello, OR ext = "cookie"
  HRR MUST NOT introduce novel extensions
```
**Source:** RFC 8446 Section 4.1.2
**Counterexample:** An HRR that offers a new extension the client never advertised (protocol corruption).
