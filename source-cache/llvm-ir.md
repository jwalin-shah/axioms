# oracle/llvm-ir
Source: https://llvm.org/docs/LangRef.html
Date pulled: 2026-07-21

## SSA Form Guarantees

### INV-LLVM-SSA-001: Definition Dominates All Uses
**Core Invariant:**
```
∀instruction I, ∀value %x used by I:
  def(%x) dominates I in the control flow graph (dominators(DT, I) contains def(%x))
```
**Source:** LLVM LangRef, Well-Formedness section
**Counterexample:** Using a value before its definition in a predecessor block, or using a phi value that the entry block's predecessors do not provide.

### INV-LLVM-SSA-002: Single Static Assignment
**Core Invariant:**
```
∀function F, ∀SSA value v (register or unnamed temporary):
  v is assigned exactly once in F's IR
  unnamed temporaries numbered sequentially per-function counter, starting at 0
```
**Source:** LLVM LangRef, Introduction
**Counterexample:** Assigning the same register %r1 twice in the same function would violate SSA.

### INV-LLVM-SSA-003: No Phi Nodes in Entry Block
**Core Invariant:**
```
∀function F:
  predecessors(entry_block(F)) = ∅
  phi_nodes(entry_block(F)) = ∅
```
**Source:** LLVM LangRef, Phi node instruction
**Counterexample:** A phi node in the entry block would refer to non-existent predecessors.

### INV-LLVM-SSA-004: Verifier Enforcement
**Core Invariant:**
```
∀valid Module M:
  verifyModule(M) = true  (parser runs verifier after parsing; optimizer runs verifier before bitcode emit)
```
**Source:** LLVM LangRef, Well-Formedness
**Counterexample:** A malformed module that passes the verifier would silently produce incorrect codegen.

---

## Type System

### INV-LLVM-TYPE-001: First-Class Type Restriction
**Core Invariant:**
```
∀instruction I that produces a value:
  result_type(I) ∈ {integer, floating-point, pointer, vector, struct, array, ...}
  result_type(I) ≠ FunctionType (function types are NOT first-class)
```
**Source:** LLVM LangRef, Type System
**Counterexample:** Returning a function type value directly from an instruction (functions are only addressable via pointers).

### INV-LLVM-TYPE-002: Void Type Restriction
**Core Invariant:**
```
∀use of void type v:
  v appears only as function return or ret operand with no value
  v is never the result of a non-terminator instruction
```
**Source:** LLVM LangRef, Void Type
**Counterexample:** Using void as a stored or loaded type.

### INV-LLVM-TYPE-003: Literal vs Identified Type Uniquing
**Core Invariant:**
```
∀literal type T1, T2:
  structurally_equal(T1, T2) ⇒ T1 = T2  (literal types are uniqued structurally)
∀identified type T1, T2:
  T1.name ≠ T2.name ⇒ T1 ≠ T2  (identified types are never uniqued)
```
**Source:** LLVM LangRef, Type System
**Counterexample:** Two structurally identical identified types with different names being treated as equivalent would break type safety.

### INV-LLVM-TYPE-004: Pointer and Vector Type Well-Formedness
**Core Invariant:**
```
∀PointerType P: element_type(P) is a first-class TYPE (not void or function directly)
∀VectorType V: element_type(V) is a first-class or integer TYPE
     ∧ vector_length(V) is a power of 2 or 1 for scalable vectors
```
**Source:** LLVM LangRef, Pointer Type, Vector Type
**Counterexample:** A vector of void type, or a vector with non-power-of-2 fixed length (e.g., <7 x i32> without explicit support).

---

## Control Flow Graph Well-Formedness

### INV-LLVM-CFG-001: Every Block Must Terminate
**Core Invariant:**
```
∀BasicBlock B in function F:
  last_instruction(B) ∈ TerminatorInstructions
  TerminatorInstructions = {ret, br, switch, indirectbr, invoke, callbr, resume, catchswitch, catchret, cleanupret, unreachable}
```
**Source:** LLVM LangRef, Terminator Instructions
**Counterexample:** A basic block that falls through to the next block without a terminator (assembly parser would reject).

### INV-LLVM-CFG-002: Branch Target Intra-Function
**Core Invariant:**
```
∀terminator T with label operand L:
  function_containing(L) = function_containing(T)
```
**Source:** LLVM LangRef, br instruction
**Counterexample:** A branch instruction targeting a label from a different function.

### INV-LLVM-CFG-003: Single Entry, Single Function Entry
**Core Invariant:**
```
∀function F:
  |entry_blocks(F)| = 1
  entry_block(F) is defined by the first label in F's definition
```
**Source:** LLVM LangRef, Function Structure
**Counterexample:** A function with multiple entry points that can be jumped to directly from outside.

---

## Memory Operations (Load/Store, Volatile, Atomic)

### INV-LLVM-MEM-001: Volatile Semantics
**Core Invariant:**
```
∀volatile op v ∈ {load, store}:
  v NOT: optimized away, reordered with other volatile ops, or combined with adjacent volatile ops
  volatile accesses model memory-mapped I/O behavior
```
**Source:** LLVM LangRef, Volatile Memory Accesses
**Counterexample:** The optimizer combining two volatile stores to adjacent addresses into a single wider store.

### INV-LLVM-MEM-002: Load/Store Alignment Invariant
**Core Invariant:**
```
∀load/store with alignment parameter A:
  access_address MOD A = 0
  if A omitted: A = target_ABI_alignment(accessed_type)
```
**Source:** LLVM LangRef, Memory Access Operations
**Counterexample:** A misaligned access that the target CPU cannot handle (fault on strict-alignment architectures).

### INV-LLVM-MEM-003: Atomic Ordering Constraints
**Core Invariant:**
```
∀ordering o ∈ {monotonic, acquire, release, acq_rel, seq_cst}:
  acquire  ⇒ all subsequent memory operations by this thread happen after the atomic op
  release  ⇒ all preceding memory operations by this thread happen before the atomic op
  seq_cst  ⇒ single total order consistent with happens-before of all seq_cst ops
```
**Source:** LLVM LangRef, Atomic Instructions
**Counterexample:** Reordering an acquire load's dependent load before the acquire itself.

### INV-LLVM-MEM-004: cmpxchg Failure Ordering
**Core Invariant:**
```
∀cmpxchg(success_ordering, failure_ordering):
  failure_ordering ≠ release ∧ failure_ordering ≠ acq_rel
  failure_ordering ≤ success_ordering
```
**Source:** LLVM LangRef, cmpxchg instruction
**Counterexample:** A cmpxchg with release failure ordering, which would be semantically meaningless.

---

## Function Attribute Guarantees

### INV-LLVM-ATTR-001: readonly Function Semantics
**Core Invariant:**
```
∀call to function F with attribute "readonly":
  F.does_not_write_memory_visible_to_caller() = true
  F.may_read_memory_visible_to_caller() = true
```
**Source:** LLVM LangRef, Function Attributes
**Counterexample:** A readonly function writing to a global variable.

### INV-LLVM-ATTR-002: readnone Function Semantics
**Core Invariant:**
```
∀call to function F with attribute "readnone":
  F.does_not_read_memory_visible_to_caller() = true
  F.does_not_write_memory_visible_to_caller() = true
```
**Source:** LLVM LangRef, Function Attributes
**Counterexample:** A readnone function reading a global variable -- the optimizer would miscompile by reordering across side effects.

### INV-LLVM-ATTR-003: nounwind Function Semantics
**Core Invariant:**
```
∀call to function F with attribute "nounwind":
  unwinding does not propagate through F
  F MUST return normally or call abort/trap
```
**Source:** LLVM LangRef, Function Attributes
**Counterexample:** A nounwind function that throws an exception. The unwinder would skip cleanup handlers.

### INV-LLVM-ATTR-004: willreturn Function Semantics
**Core Invariant:**
```
∀call to function F with attribute "willreturn":
  F always terminates (does not infinite-loop, does not call noreturn)
```
**Source:** LLVM LangRef, Function Attributes
**Counterexample:** A willreturn function that enters an infinite loop on certain input.

### INV-LLVM-ATTR-005: convergent Function Semantics
**Core Invariant:**
```
∀call to function F with attribute "convergent":
  control_flow_of(call) must not be changed by optimization
  (F cannot be made control-dependent on additional values)
```
**Source:** LLVM LangRef, Function Attributes
**Counterexample:** An optimization hoisting a convergent call out of a GPU warp-divergent branch, breaking SIMT convergence.

### INV-LLVM-ATTR-006: speculatable Function Semantics
**Core Invariant:**
```
∀call to function F with attribute "speculatable":
  F.has_side_effects() = false
  F.does_not_depend_on_undef_or_poison_behavior() = true
```
**Source:** LLVM LangRef, Function Attributes
**Counterexample:** A speculatable function executing undefined behavior when speculated past a null check.

---

## Intrinsic Function Contracts

### INV-LLVM-INT-001: llvm.memcpy Source/Destination Validity
**Core Invariant:**
```
∀call memcpy(dst, src, len, isvolatile):
  valid_pointer_range(dst, len) ∧ valid_pointer_range(src, len)
  (isvolatile = false ∧ overlap_allowed = false) ⇒ regions_non_overlapping(dst, src, len)
```
**Source:** LLVM LangRef, Standard Intrinsics
**Counterexample:** memcpy with overlapping regions producing correct results (must use memmove for overlap).

### INV-LLVM-INT-002: llvm.memmove Overlap Safety
**Core Invariant:**
```
∀call memmove(dst, src, len, isvolatile):
  valid_pointer_range(dst, len) ∧ valid_pointer_range(src, len)
  overlap_produces_correct_result(dst, src, len)
```
**Source:** LLVM LangRef, Standard Intrinsics
**Counterexample:** memmove reversing source bytes when src begins past dst (the standard requires proper copy direction selection).

### INV-LLVM-INT-003: llvm.memset Byte Fill
**Core Invariant:**
```
∀call memset(dst, val, len, isvolatile):
  ∀i ∈ [0, len): byte_at(dst + i) = val
```
**Source:** LLVM LangRef, Standard Intrinsics
**Counterexample:** memset of 0 to a 4-byte location setting only the first byte.

### INV-LLVM-INT-004: Lifetime Start/End
**Core Invariant:**
```
∀alloca %p:
  lifetime.start(%p, size) ⇒ %p accessible
  lifetime.end(%p, size) ⇒ accessing %p is undefined behavior
```
**Source:** LLVM LangRef, Intrinsic Functions
**Counterexample:** Reading from a stack slot after lifetime.end (the optimizer may reuse that stack slot).

---

## Linkage & Global Invariants

### INV-LLVM-LINK-001: Declaration Linkage Restriction
**Core Invariant:**
```
∀global declaration D:
  linkage(D) ∈ {external, extern_weak}
```
**Source:** LLVM LangRef, Linkage Types
**Counterexample:** A global declaration with internal linkage, which would be contradictory.

### INV-LLVM-LINK-002: Common Linkage Restriction
**Core Invariant:**
```
∀global g with CommonLinkage:
  g.section = none ∧ g.initializer = zero ∧ g.constant = false
  type(g) ∉ {FunctionType, AliasType}
```
**Source:** LLVM LangRef, Common Linkage
**Counterexample:** A common linkage global marked constant with a non-zero initializer.

### INV-LLVM-LINK-003: Constant Global Invariant
**Core Invariant:**
```
∀global with attribute "constant":
  initializer(g) ≠ ⊥ (must have initializer)
  no store instruction targets g
```
**Source:** LLVM LangRef, Global Variables
**Counterexample:** Storing to a constant global triggers undefined behavior that the optimizer exploits.

### INV-LLVM-LINK-004: noalias and TBAA
**Core Invariant:**
```
∀pointers p, q where p.noalias:
  memory_accessed_through(p) does not alias any other pointer
  unless the other pointer is derived from p or TBAA rules permit overlap
```
**Source:** LLVM LangRef, Pointer Aliasing Rules
**Counterexample:** Two noalias parameters to a function pointing to overlapping memory, causing miscompilation.
