# oracle/rustonomicon
Source: The Rustonomicon (https://doc.rust-lang.org/nomicon/)
Date pulled: 2026-07-21

## Safety Invariant

### INV-RUST-001: The Rust Safety Invariant
**Core Invariant:**
```
For every value of type T that is accessible in safe code:
- The value must be in a valid-initialized state for type T
- The value must not be in a state where safe operations on T could cause undefined behavior
- All &T references must point to immutable memory (absent UnsafeCell)
- All &mut T references have exclusive (unique) access
```
**Source:** Rustonomicon, "Meet Safe and Unsafe" (https://doc.rust-lang.org/nomicon/meet-safe-and-unsafe.html)
**Counterexample:** Creating a `&mut T` that aliases another `&mut T` or `&T` — the borrow checker prevents this statically, but unsafe code that does it via pointer casting violates the safety invariant.

### INV-RUST-002: The Rust Validity Invariant
**Core Invariant:**
```
For every value of type T at runtime, regardless of code origin (safe or unsafe):
- The value must satisfy the bit-level validity requirements of type T
- References must be non-null and properly aligned
- bool values must be 0 or 1
- enum discriminants must be valid variants
- char values must be in [0x0, 0xD7FF] ∪ [0xE000, 0x10FFFF]
- Function pointers must be non-null
```
**Source:** Rustonomicon, "Unsafe Operations", Ralf Jung's type safety writeups
**Counterexample:** Creating a `bool` with value `3` — this violates the validity invariant and constitutes immediate undefined behavior, even if never read as a boolean.

### INV-RUST-003: Safety vs Validity Boundary
**Core Invariant:**
```
safe code ⟹ safety_invariant(value, type) holds
all code   ⟹ validity_invariant(value, type) holds
unsafe code must guarantee safety_invariant to safe callers
∀operations: if validity_invariant violated → UB (no conditions)
∀operations: if safety_invariant violated → UB only when operation assumes it
```
**Source:** Rustonomicon, "Safe and Unsafe" chapters
**Counterexample:** An unsafe function that returns a dangling pointer to safe code. The safe code calls a safe method on it — the safety invariant is violated by the unsafe function, causing UB in the safe caller.

## Aliasing Rules (Stacked Borrows / Tree Borrows)

### INV-RUST-004: Stacked Borrows Stack Invariant
**Core Invariant:**
```
∀location L in memory:
  L has a stack S of permissions/tags
  S.top is the most recent borrow
  ⊢ Grants(permission(t, S), access_type) iff tag t may access L for access_type
  access_type ∈ {Read, Write}
  permissions(t) ∈ {Unique, SharedRW, SharedRO, Disabled}
```
**Source:** Stacked Borrows paper, Ralf Jung (https://plv.mpi-sws.org/rustbelt/stacked-borrows/)
**Counterexample:** Two `&mut` references to overlapping memory where one is still live — the stack will have both tags, but write access through the inner one should disable the outer one, causing UB if the outer one is then used.

### INV-RUST-005: Stacked Borrows Write Rule
**Core Invariant:**
```
Write(L, tag t):
  (grants_found, item) = FindGranting(S[L], AccessWrite, t)
  if ¬grants_found: UB
  if item.permission = Unique:
    pop S[L] until item is at the top
  if item.permission = SharedRW:
    pop items above item that are also SharedRW
  if any popped item has active_call_id ≠ ⊥: UB
```
**Source:** Stacked Borrows formal appendix, Rule (write)
**Counterexample:** Writing through a mutable reference after an aliasing `&` reference (without UnsafeCell) has been created — the SharedRO item above will be popped/disabled, but if another code path holds the same tag, use-after-poison occurs.

### INV-RUST-006: Stacked Borrows Read Rule
**Core Invariant:**
```
Read(L, tag t):
  (grants_found, item) = FindGranting(S[L], AccessRead, t)
  if ¬grants_found: UB
  ∀item_above with permission = Unique:
    set item_above.permission = Disabled
  if any disabled item has active_call_id in active calls: UB
```
**Source:** Stacked Borrows formal appendix, Rule (read)
**Counterexample:** Reading through a shared reference while a mutable (unique) borrow is still active — the unique item gets disabled, but if the mutable reference is used later, UB occurs.

### INV-RUST-007: Stacked Borrows Retag Rule
**Core Invariant:**
```
Retag(reference r, kind k):
  fresh_tag t = new_unique_tag()
  if k = Mut:
    Write(mem_of(r), r.tag)   // validate old tag
    S[mem_of(r)].push(Unique(t))
  if k = Shared:
    Read(mem_of(r), r.tag)    // validate old tag
    S[mem_of(r)].push(SharedRW(t))
  if k = Shr (shared inside UnsafeCell):
    S[mem_of(r)].push(Shr(t)) // no freezing
```
**Source:** Stacked Borrows formal appendix, Rule (retag)
**Counterexample:** Retagging a mutable reference when the underlying location's stack has no granting item — the write check fails and UB occurs before the new tag is even created.

### INV-RUST-008: Tree Borrows Tree Invariant
**Core Invariant:**
```
Each owned value has a tree of borrows (not a stack).
Nodes = borrows, Edges = borrow relationships.
Two aliases conflict only if they are ancestor-related in the tree.
Sibling borrows (created independently from the same parent) do not conflict.
```
**Source:** Tree Borrows paper (https://perso.crans.org/vanille/treebor/)
**Counterexample:** Stacked Borrows would incorrectly flag as UB a pattern where two sibling mutable borrows are alternately used (e.g., writing through `x`, then through `y` returned by `x.split()`), which Tree Borrows correctly allows.

### INV-RUST-009: Provenance Semantics
**Core Invariant:**
```
∀pointer p, every access through p is valid only at the set of addresses
derived from the provenance of p.
provenance(p) = { base_address, allocation_id, size }
address(p) ∈ provenance(p)   // pointer must point within its provenance
∀pointer arithmetic: new_address = original_address + n
  if new_address ∉ provenance(original) → UB
```
**Source:** Rustonomicon, "Provenance" (https://doc.rust-lang.org/nomicon/provenance.html), RFCs on strict provenance
**Counterexample:** Taking a pointer to struct field A, offsetting past the struct boundary into field B of a different field — even if the address is valid, the provenance doesn't extend to B, making the access UB.

## Layout Guarantees

### INV-RUST-010: repr(Rust) Layout Unspecified Invariant
**Core Invariant:**
```
∀struct S with repr(Rust):
  alignment(S) = max(alignment(field_i) for all fields i)
  size(S) is a multiple of alignment(S)
  padding is added for alignment but field ordering is unspecified
  two instances of the same type have the same layout
  distinct types (even structurally identical) may differ in layout
```
**Source:** Rustonomicon, "repr(Rust)" (https://doc.rust-lang.org/nomicon/repr-rust.html)
**Counterexample:** Writing a struct's memory to disk as repr(Rust) and reading it back after a Rust compiler upgrade — the field ordering could differ, causing data corruption.

### INV-RUST-011: repr(C) Layout Guarantee
**Core Invariant:**
```
∀struct S with repr(C):
  field ordering matches declaration order (first field at lowest address)
  alignment follows C ABI rules for each field type
  size(S) = sum(sizes of fields) + padding as required by C ABI
  layout is stable across compiler versions (like C's ABI)
  enum size = max(variant_size) + tag_size + padding
```
**Source:** Rustonomicon, "repr(C)" (https://doc.rust-lang.org/nomicon/other-reprs.html)
**Counterexample:** An FFI call that passes a repr(Rust) struct to a C function expecting C-order fields — data misinterpretation and corruption.

### INV-RUST-012: Primitive Alignment Rule
**Core Invariant:**
```
∀type T:
  alignment(T) ≥ 1
  alignment(T) = 2^n for some n ≥ 0
  size(T) is a multiple of alignment(T)
  (size(T) = 0 is valid for any alignment)
```
**Source:** Rustonomicon, "repr(Rust)" (https://doc.rust-lang.org/nomicon/repr-rust.html)
**Counterexample:** An array element of size 5 with alignment 4 — the stride of the array would be 8, so indexing `arr[1]` accesses byte 8, not byte 5.

### INV-RUST-013: Null Pointer Optimization (NPO)
**Core Invariant:**
```
∀enum E with exactly one unit variant and one non-nullable pointer variant:
  size(E) = size(pointer_variant)
  tag is elided; the unit variant uses the null representation of the pointer
  ∀T: Option<&T> has same layout as &T (nullable pointer optimization)
  Box<T>, NonNull<T>, &T, &mut T are all eligible for NPO
```
**Source:** Rustonomicon, "repr(Rust)" enum layout section
**Counterexample:** `Option<Box<u8>>` should have the same size as `Box<u8>` (one machine word), not two words. A `transmute` that assumes a two-word layout would be wrong.

### INV-RUST-014: Enum Discriminant Range Invariant
**Core Invariant:**
```
∀enum E:
  discriminant(E_variant_i) is within the range of the discriminant type
  no two variants share the same discriminant (unless explicitly set to same value)
  the discriminant type is the smallest integer type that can hold all discriminants
  with repr(C) or repr(Int): discriminant type is explicitly specified
```
**Source:** Rustonomicon, "Cast and Transmute" layout discussions
**Counterexample:** Transmuting an enum with 256 variants to `u8` when the discriminant is `isize` — the memory layout may not correspond.

## Drop Flag Invariants

### INV-RUST-015: Drop Flag Correctness
**Core Invariant:**
```
∀variable x with a Drop flag:
  x.drop_flag = false  at beginning of scope
  x.drop_flag = true   after x is moved or explicitly dropped
  destructor runs iff x.drop_flag = true at scope exit
  drop flag is optimized away when no partial moves are possible
```
**Source:** Rustonomicon, "Drop Flags" (https://doc.rust-lang.org/nomicon/drop-flags.html)
**Counterexample:** A struct with two `String` fields where only one is moved — if the drop flag doesn't track which field was moved, the destructor might try to drop the already-moved field (double-free).

### INV-RUST-016: Drop Check (Dropck) Invariant
**Core Invariant:**
```
Given struct S<T> with a Drop impl:
  If the Drop impl accesses T values, then T must outlive S's drop
  Formally: ∀S<T: Drop> that accesses T: 'a must outlive S
  RFC 1238: the compiler checks that generic parameters used in Drop
  are not dropped before the Drop impl runs
```
**Source:** Rustonomicon, "Drop Check" (https://doc.rust-lang.org/nomicon/drop-check.html)
**Counterexample:** A `Vec<(T, &'a u8)>` where `T`'s drop might read from the reference `&'a u8` — if `'a` ends before the drop, the reference is dangling during drop.

### INV-RUST-017: #[may_dangle] Constraint
**Core Invariant:**
```
unsafe impl<#[may_dangle] T> Drop for S<T>:
  if PhantomData<T> is present → ownership is asserted → may_dangle is restricted
  if ¬PhantomData<T> → may_dangle allows T to be freed before S's drop
  invariant: the Drop impl does not access T's value through the dangling parameter
```
**Source:** Rustonomicon, "Drop Check" with #[may_dangle] discussion
**Counterexample:** Declaring `#[may_dangle]` on T but then calling a method on T inside the destructor — UB because T may already be dropped.

## PhantomData Variance Invariants

### INV-RUST-018: PhantomData Variance Rules
**Core Invariant:**
```
PhantomData<T>              → T is covariant     (ownership — may drop T)
PhantomData<&'a T>         → 'a covariant, T covariant  (requires T: Sync for Send+Sync)
PhantomData<&'a mut T>     → 'a covariant, T invariant
PhantomData<*const T>      → T covariant         (!Send + !Sync by default)
PhantomData<*mut T>        → T invariant          (!Send + !Sync by default)
PhantomData<fn(T)>         → T contravariant      (Send + Sync)
PhantomData<fn() -> T>     → T covariant          (Send + Sync)
PhantomData<Cell<&'a ()>>  → 'a invariant        (Send + !Sync)
```
**Source:** Rustonomicon, "PhantomData" (https://doc.rust-lang.org/nomicon/phantom-data.html)
**Counterexample:** Using `PhantomData<&'a T>` for a mutable iterator but needing T to be invariant — if `&'a mut T` should be invariant, using `PhantomData<&'a T>` would incorrectly allow a lifetime-subtyping coercion on T.

### INV-RUST-019: PhantomData Drop Check Ownership
**Core Invariant:**
```
PhantomData<T> signals ownership of T to the drop checker.
If S has PhantomData<T> and S<T> has a #[may_dangle] Drop impl,
then T is NOT may_dangle for drop-glue purposes.
Without PhantomData<T>, the compiler assumes S does not own T.
```
**Source:** Rustonomicon, "PhantomData" and "Drop Check"
**Counterexample:** A `Vec`-like type that owns `T` values but uses `PhantomData<&'a T>` instead of `PhantomData<T>` — the drop checker would allow T to be freed before the Vec's destructor runs, causing use-after-free.

## Send/Sync Invariants

### INV-RUST-020: Send Invariant
**Core Invariant:**
```
Send(T) ≜ type T can be safely transferred to another thread
unsafe trait Send {}
∀T: T is Send iff sharing mutable state with another thread without
      exclusive access would not cause data races
¬Send(T) if T contains non-Send types without synchronization
  raw_pointer: ¬Send (lint)
  UnsafeCell: ¬Sync (but may be Send)
  Rc<T>: ¬Send
  Arc<T>: Send if T: Send + Sync
```
**Source:** Rustonomicon, "Send and Sync" (https://doc.rust-lang.org/nomicon/send-and-sync.html)
**Counterexample:** Wrapping `Rc<RefCell<u32>>` in a struct and sending it to another thread — the unsynchronized reference counts will race and cause UB.

### INV-RUST-021: Sync Invariant
**Core Invariant:**
```
Sync(T) ≜ type T can be safely shared between threads
Sync(T) iff Send(&T)
unsafe trait Sync {}
∀T: &T is Send iff shared access to T does not cause data races
¬Sync(T) if T contains UnsafeCell without synchronization primitive
  Cell<T>: Send but NOT Sync
  RefCell<T>: Send but NOT Sync
  Mutex<T>: Sync if T: Send
```
**Source:** Rustonomicon, "Send and Sync" (https://doc.rust-lang.org/nomicon/send-and-sync.html)
**Counterexample:** Putting `Cell<u32>` in a `static` variable — `Cell` is not Sync, so static access could create `&Cell<u32>` on multiple threads each calling `.set()`, causing data races.

### INV-RUST-022: Auto-Derivation of Send/Sync
**Core Invariant:**
```
∀structural type S (struct, tuple, enum, union):
  Send(S) iff ∀field_i: Send(field_type_i)
  Sync(S) iff ∀field_i: Sync(field_type_i)
  (auto-derivation applies unless explicitly overridden with unsafe impl or impl !Trait)
```
**Source:** Rustonomicon, "Send and Sync" auto-trait rules
**Counterexample:** A struct containing `*mut u8` that wraps pointer data with proper synchronization — fails auto-derivation (since `*mut u8: !Send`), requiring explicit `unsafe impl Send`.

### INV-RUST-023: Interior Mutability Safety
**Core Invariant:**
```
Cell<T>:    ¬Sync — allows unsynchronized mutation via shared reference
RefCell<T>: ¬Sync — allows unsynchronized mutation via shared reference
Mutex<T>:   Sync — provides synchronized mutation via shared reference
RwLock<T>:  Sync — provides synchronized mutation via shared reference
Atomic*:    Sync — provides lock-free synchronization
UnsafeCell: ¬Sync — the raw primitive; all safe wrappers must enforce Sync manually
```
**Source:** Rustonomicon, "Send and Sync", std::cell and std::sync type constraints
**Counterexample:** A custom smart pointer using `UnsafeCell` that implements `Sync` without synchronization — shared references on different threads can mutate the same location without a happens-before relationship.

## ABI and FFI Invariants

### INV-RUST-024: ABI Compatibility Invariant
**Core Invariant:**
```
Given extern "C" fn f(args...):
  the Rust calling convention matches the C calling convention for the platform:
    - arguments are passed in the order specified by the target C ABI
    - return values follow the C ABI for the platform
    - all types used must be repr(C) or platform-C-compatible
  Variadic functions are supported only through extern "C" with c_variadic
  Panic across FFI boundary = UB (unless using catch_unwind on the Rust side)
```
**Source:** Rustonomicon, "FFI" (https://doc.rust-lang.org/nomicon/ffi.html)
**Counterexample:** A C function calling back into Rust through a function pointer that panics — the panic crosses the FFI boundary without `catch_unwind`, causing UB.

### INV-RUST-025: Type Punning Invariant
**Core Invariant:**
```
∀transmute from type A to type B:
  size(A) = size(B)  (checked at compile time)
  validity_invariant(result) must hold  (checked at runtime at the caller's discretion)
  safety_invariant(A) ⇒ safety_invariant(B) must be proven by the caller
```
**Source:** Rustonomicon, "Type Casts and Transmute"
**Counterexample:** Transmuting `u32` to `bool` — size is equal (4 bytes), but value 2 is not a valid `bool`, violating the validity invariant and causing UB.
