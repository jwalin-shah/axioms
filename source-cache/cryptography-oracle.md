# oracle/cryptography — Cryptographic design invariants

Source: Bellare-Rogaway (2006), Cramer-Shoup (1998), Shoup (2004)
Date pulled: 2026-07-21
Trust level: textbook-formal (HIGH)

---

## INV-CRYPTO-006: PRP/PRF Switching Lemma — Birthday Bound

**Core Invariant:**
```
∀ block cipher E with block size n bits, ∀ adversary A making q queries:
  Adv^{prp-prf}_E(A) ≤ q(q-1) / 2^{n+1}

For n = 128 (AES): security degrades at q ≈ 2^64 blocks.
Conservative bound: rotate keys before q = 2^48 blocks encrypted under a single key.
```

**Source:** Bellare, M. and Rogaway, P. "Code-Based Game-Playing Proofs and the Security of Triple Encryption." EUROCRYPT 2006. IACR ePrint 2004/331.
https://eprint.iacr.org/2004/331.pdf

The PRP/PRF switching lemma formalizes the indistinguishability gap between a random permutation (PRP — a block cipher) and a random function (PRF). The adversary's distinguishing advantage is bounded by q(q-1)/2^{n+1}, the birthday bound. When q ≈ 2^{n/2} ≈ 2^64 for AES-128, the bound becomes non-negligible. This is why per-key query limits exist: a single AES-128 key must not encrypt more than ~2^64 blocks. GCM with random nonces adds an additional constraint: at most 2^32 invocations per key to avoid nonce collision within the birthday bound.

**Counterexample:** Encrypting 2^64 + 1 blocks under a single AES-128 key. At this point the PRP/PRF switching lemma no longer guarantees indistinguishability — the block cipher behaves distinguishably from a random function, leaking information about plaintext relationships.

**Practical enforcement:**
- Track block counter per key
- Force key rotation before 2^48 blocks (conservative, leaves 16-bit safety margin)
- For GCM: enforce q ≤ 2^32 invocations per key

---

## INV-CRYPTO-008: KEM/DEM Composition — IND-CCA2 Requirement

**Core Invariant:**
```
∀ hybrid encryption scheme (KEM, DEM):
  KEM is IND-CCA2 secure
  ∧ DEM is one-time IND-CCA2 secure
  ⇒ hybrid PKE is IND-CCA2 secure

Additional binding requirement:
  AEAD associated data MUST include KEM ciphertext
  (prevents re-encryption attacks where attacker swaps DEM ciphertexts under same KEM key)
```

**Source:** Cramer, R. and Shoup, V. "Design and Analysis of Practical Public-Key Encryption Schemes Secure against Adaptive Chosen Ciphertext Attack." SIAM Journal on Computing, 2003. Shoup, V. "ISO 18033-2: An Emerging Standard for Public-Key Encryption." 2004.

The KEM (Key Encapsulation Mechanism) generates an ephemeral symmetric key k and encrypts it under the recipient's public key. The DEM (Data Encapsulation Mechanism) encrypts the actual message using k. The composition theorem states: IND-CCA2 KEM + one-time IND-CCA2 DEM = IND-CCA2 hybrid PKE.

The critical practical requirement is BINDING: the DEM encryption must bind to the KEM ciphertext. This means the AEAD associated data in the DEM step must include the KEM ciphertext bytes. Without this binding, an attacker can take a valid KEM ciphertext C0, decrypt C1 under the same k, replace it with a different C1', and submit (C0, C1') — a re-encryption attack.

**Counterexample:** A KEM/DEM implementation that encrypts C1 = AES-GCM(k, nonce, plaintext, ad="") — no binding to C0. Attacker intercepts (C0, C1), decrypts C1 using the same k (which they don't know, but the DEM's one-time security is broken if k is reused), replaces C1 with a chosen C1'. Without binding, the recipient cannot detect the substitution.

**Enforcement:**
- KEM shared secret k must flow directly into DEM encryption, never stored/logged/derived
- k must be zeroized after use
- Fresh KEM encapsulation per encryption call
- AEAD associated data MUST include KEM ciphertext for binding
- Encrypt-then-cache-k is BROKEN

---

## INV-CRYPTO-009: Authenticate Before Decrypt — Padding Oracle Prevention

**Core Invariant:**
```
∀ ciphertext C:
  verify_auth_tag(C) = true BEFORE decrypt(C)
  If auth fails → emit GENERIC_ERROR (no distinction between padding/MAC/format failures)

Equivalently: use AEAD modes (AES-GCM, ChaCha20-Poly1305) which enforce this ordering.
For non-AEAD: encrypt-then-MAC where MAC verification happens first.
```

**Source:** Vaudenay, S. "Security Flaws Induced by CBC Padding — Applications to SSL, IPSEC, WTLS..." EUROCRYPT 2002. Springer LNCS 2332, pp. 534-545.
https://link.springer.com/content/pdf/10.1007/3-540-46035-7_35.pdf

The padding oracle attack exploits systems that decrypt first, then check padding, then check MAC — revealing different error messages (or timing differences) for "invalid padding" vs "invalid MAC." An attacker can iteratively modify ciphertext bytes and observe error responses to decrypt the message without knowing the key.

The fix is universal: authenticate BEFORE decrypting. If authentication fails, emit a single generic error. This eliminates the oracle entirely — the attacker learns nothing from the error response because it's always the same. AEAD modes (AES-GCM, ChaCha20-Poly1305) handle this correctly by construction. For non-AEAD modes: encrypt-then-MAC with MAC verification before decryption.

**Counterexample:** TLS CBC mode before 1.2: decrypt → check padding → check MAC. Each step reveals different errors. The Lucky13 attack (2013) exploited timing differences in these checks. Fix: TLS 1.2+ with GCM, or encrypt-then-MAC extension (RFC 7366).

**Note on source attribution:** Originally attributed to Schneier's "Applied Cryptography" but the canonical academic source is Vaudenay (2002). Schneier discusses the principle but Vaudenay provides the formal attack and proof. The axiom is correct; the original source field `schneier` should be updated to reference Vaudenay (2002).
