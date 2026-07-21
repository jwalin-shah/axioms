# oracle/pfpl
Source: Practical Foundations for Programming Languages, 2nd Edition, Robert Harper (Cambridge University Press, 2016)
Date pulled: 2026-07-21
URL: https://www.cs.cmu.edu/~rwh/pfpl/

## Structural Dynamics (Transition Semantics)

### INV-PFPL-001: Preservation (Subject Reduction)
**Core Invariant:**
```
If Γ ⊢ e : τ and e ⟼ e' then Γ ⊢ e' : τ
```
**Source:** PFPL Chapter 4 (Statics and Dynamics), Safety Theorem
**Counterexample:** A well-typed expression that evaluates to a value of a different type (e.g., an Int under a Bool context) would break preservation.

### INV-PFPL-002: Progress (Canonical Forms)
**Core Invariant:**
```
If · ⊢ e : τ then either e is a value v of type τ or ∃e' such that e ⟼ e'
```
**Source:** PFPL Chapter 4 (Statics and Dynamics), Safety Theorem
**Counterexample:** A well-typed term that is stuck (neither a value nor able to step) would violate progress. Example: a typecase on a value that doesn't match any branch without a default.

### INV-PFPL-003: Type Safety (Progress + Preservation)
**Core Invariant:**
```
∀e, τ: (· ⊢ e : τ) ⇒ ((∃v: e val ∧ ⊢ v : τ) ∨ (∃e': e ⟼ e' ∧ · ⊢ e' : τ))
```
**Source:** PFPL Chapter 4, Safety Theorem (Theorem 4.1)
**Counterexample:** A term that type-checks but after some number of reduction steps reaches an ill-typed state. Example: an ill-formed typecase reaching a dead branch.

### INV-PFPL-004: Structural Dynamics Determinism (Deterministic Languages)
**Core Invariant:**
```
If e ⟼ e₁ and e ⟼ e₂ then e₁ ≡ e₂
```
**Source:** PFPL Chapter 4, Structural Dynamics
**Counterexample:** A language where `(1+2)*(3+4)` could evaluate to either `3*(3+4)` or `(1+2)*7` depending on the order of evaluation (i.e., nondeterministic evaluation of subexpressions).

### INV-PFPL-005: Substitution Principle
**Core Invariant:**
```
If Γ ⊢ e : τ and Γ, x:τ ⊢ e' : τ' then Γ ⊢ [e/x]e' : τ'
```
**Source:** PFPL Chapter 3, Hypothetical Judgments
**Counterexample:** Substituting a term of type τ into a context expecting a different type would violate the substitution lemma. Example: substituting a Bool into a position typed as Int.

### INV-PFPL-006: Weakening (Structural Property)
**Core Invariant:**
```
If Γ ⊢ e : τ then Γ, x:τ' ⊢ e : τ for any x ∉ dom(Γ)
```
**Source:** PFPL Chapter 3, Structural Properties of Judgments
**Counterexample:** Adding an assumption that changes the meaning of an expression (e.g., shadowing a free variable would change typing) would violate weakening.

### INV-PFPL-007: Mode Correctness for Judgments
**Core Invariant:**
```
Every inference rule must have a mode assignment such that:
∀(premises): each premise's outputs are among the inputs of the conclusion
∀(parameters): bound variables appear only in positions that respect their mode
```
**Source:** PFPL Chapter 2, Inductive Definitions
**Counterexample:** A rule with a premise that introduces a variable not determined by the conclusion's inputs, making the rule uncomputable.

## Inductive Definitions

### INV-PFPL-008: Rule Induction Principle
**Core Invariant:**
```
If Φ is closed under all rules of an inductive definition, then every judgment
J in that definition satisfies Φ(J). Equivalently: the least fixed point of the
rule operator is the set of all derivable judgments.
```
**Source:** PFPL Chapter 2, Inductive Definitions
**Counterexample:** A property that holds for all axioms and is preserved by all rules but fails for a derivable judgment — this would indicate the inductive definition is not the *least* fixed point.

### INV-PFPL-009: Well-foundedness of Inductive Definitions
**Core Invariant:**
```
∀J in an inductive definition: there exists a finite derivation tree D
such that D concludes J and all leaves of D are axioms.
Equivalently: the relation defined by the rules is well-founded under
the sub-derivation ordering.
```
**Source:** PFPL Chapter 2, Inductive Definitions
**Counterexample:** An inductive definition with infinite descending chains (e.g., a rule that dispatches to itself without consuming any structure) would violate well-foundedness.

### INV-PFPL-010: Iterated Inductive Definitions
**Core Invariant:**
```
For an inductive definition indexed by a well-founded ordering <:
if J(i) holds (where i is an index), then all premises of the rule
used to derive J(i) must have indices j < i.
```
**Source:** PFPL Chapter 2, Iterated Inductive Definitions
**Counterexample:** A type system where defining `nat` requires `pos` and defining `pos` requires `nat` without a well-founded ordering.

### INV-PFPL-011: Simultaneous Inductive Definitions
**Core Invariant:**
```
For two mutually-defined judgments P and Q, the relation (P ∪ Q)
must be the least fixed point of the combined set of rules for both.
Each rule for P may use P or Q in its premises, and vice versa.
```
**Source:** PFPL Chapter 2, Simultaneous Inductive Definitions
**Counterexample:** Mutually recursive types where the positivity condition is violated (e.g., `type T = T -> int` without a recursive type constructor).

## Type System Rules (Statics)

### INV-PFPL-012: Typing of Variables
**Core Invariant:**
```
Γ, x:τ ⊢ x : τ    (Variable rule — projection from context)
```
**Source:** PFPL Chapter 3, Statics
**Counterexample:** A variable used with a type different from its declaration in the context.

### INV-PFPL-013: Substitution Property of Typing
**Core Invariant:**
```
If Γ ⊢ e : τ and Γ, x:τ, Γ' ⊢ e' : τ'
then Γ, [e/x]Γ' ⊢ [e/x]e' : τ'
```
**Source:** PFPL Chapter 3, Substitution Lemma
**Counterexample:** A type system that allows a term to change type after substitution due to losing type information.

### INV-PFPL-014: Transitivity of Hypothetical Judgments
**Core Invariant:**
```
If Γ ⊢ e : τ and Γ, x:τ ⊢ e' : τ'
then Γ ⊢ let x = e in e' : τ'
```
**Source:** PFPL Chapter 3, Hypothetical Judgments
**Counterexample:** A binding construct that doesn't properly substitute the value and thus type-checks incorrectly.

### INV-PFPL-015: Uniqueness of Typing
**Core Invariant:**
```
If Γ ⊢ e : τ and Γ ⊢ e : τ' then τ ≡ τ'
```
**Source:** PFPL Chapter 4, Statics (in simply-typed setting)
**Counterexample:** A term that type-checks as both `Int` and `Bool` in the same context.

## Products and Sums

### INV-PFPL-016: Product Type Elimination
**Core Invariant:**
```
If Γ ⊢ e : τ₁ × τ₂ and e ⟼* ⟨e₁, e₂⟩ (values)
then e · fst ⟼* e₁ : τ₁ and e · snd ⟼* e₂ : τ₂
```
**Source:** PFPL Chapter 6, Finite Product Types
**Counterexample:** A product where projecting the first component returns a value of the wrong type.

### INV-PFPL-017: Sum Type Case Analysis
**Core Invariant:**
```
If Γ ⊢ e : τ₁ + τ₂ and e ⟼* l · e₁ then case(e; x.e₁'; y.e₂') ⟼* [e₁/x]e₁'
If Γ ⊢ e : τ₁ + τ₂ and e ⟼* r · e₂ then case(e; x.e₁'; y.e₂') ⟼* [e₂/y]e₂'
```
**Source:** PFPL Chapter 7, Finite Sum Types
**Counterexample:** Injecting a value of type `τ₁` into the left of a `τ₁ + τ₂` and having the case-expression dispatch to the right branch.

## Functions

### INV-PFPL-018: Function Application Dynamics
**Core Invariant:**
```
If Γ ⊢ e₁ : τ₂ → τ and Γ ⊢ e₂ : τ₂
and e₁ ⟼* λ(x:τ₂. e₁') and e₂ ⟼* v₂
then e₁(e₂) ⟼* [v₂/x]e₁' : τ
```
**Source:** PFPL Chapter 4, Function Types
**Counterexample:** An application that applies a function expecting τ₂ to an argument of type τ₁ where τ₁ ≠ τ₂.

### INV-PFPL-019: Canonical Forms (Functions)
**Core Invariant:**
```
If · ⊢ v : τ₂ → τ and v is a value
then v ≡ λ(x:τ₂. e) for some x, e
```
**Source:** PFPL Chapter 4, Canonical Forms Lemma
**Counterexample:** A value of function type that is not syntactically a lambda abstraction (e.g., an integer labeled as a function type).

## Termination Theorems

### INV-PFPL-020: Termination for Simply-Typed Lambda Calculus
**Core Invariant:**
```
∀e, τ: (· ⊢ e : τ) in the simply-typed lambda calculus with natural numbers
⇒ there exists a value v such that e ⟼* v
(i.e., all well-typed terms normalize)
```
**Source:** PFPL Chapter 10, Termination Theorem (Tait's Method)
**Counterexample:** Any well-typed term in System F with recursion (fixpoint) that diverges — the property only holds for the pure simply-typed lambda calculus without general recursion, not for PCF.

### INV-PFPL-021: Hereditarily Defined Reducibility
**Core Invariant:**
```
If e : τ (well-typed), then e is reducible at type τ:
  Red(Int) = { e | e ⟼* n }
  Red(τ₁ → τ₂) = { e | e ⟼* λx.e' ∧ ∀e₁ ∈ Red(τ₁): [e₁/x]e' ∈ Red(τ₂) }
  Red(τ₁ × τ₂) = { e | e.fst ∈ Red(τ₁) ∧ e.snd ∈ Red(τ₂) }
```
**Source:** PFPL Chapter 10, Tait's Computibility Method
**Counterexample:** A term in `Red(τ₁ → τ₂)` that when applied to a reducible argument of type τ₁, produces a result not in `Red(τ₂)`.

## Contextual Semantics

### INV-PFPL-022: Decomposition (Unique Evaluation Context)
**Core Invariant:**
```
∀e (not a value): there exists a unique evaluation context E and
unique redex r such that e = E[r], where E is defined by:
  E ::= [] | E e | v E | fst E | snd E | case(E; ...) | ...
```
**Source:** PFPL Chapter 4, Contextual Dynamics
**Counterexample:** An expression that can be decomposed as two different evaluation contexts each with a different redex, giving ambiguous evaluation order.

### INV-PFPL-023: Contextual Dynamics Preservation
**Core Invariant:**
```
If e = E[r], r ⟼ r', and · ⊢ e : τ
then · ⊢ E[r'] : τ
```
**Source:** PFPL Chapter 4, Contextual Dynamics
**Counterexample:** Filling a well-typed evaluation context with a properly reduced redex produces an ill-typed expression.

## Equational Dynamics

### INV-PFPL-024: Reflexivity, Symmetry, Transitivity
**Core Invariant:**
```
e ≡ e                              (reflexivity)
If e₁ ≡ e₂ then e₂ ≡ e₁            (symmetry)
If e₁ ≡ e₂ and e₂ ≡ e₃ then e₁ ≡ e₃ (transitivity)
```
**Source:** PFPL Chapter 4, Equational Dynamics
**Counterexample:** An equational theory where a ⟼ b and b ⟼ c but a ≢ c.

### INV-PFPL-025: Stability Under Reduction Contexts
**Core Invariant:**
```
If e₁ ≡ e₂ then for any context C[·]: C[e₁] ≡ C[e₂]
(and conversely: C[e₁] ≡ C[e₂] iff ∀reduction paths: e₁, e₂ converge)
```
**Source:** PFPL Chapter 4, Equational Dynamics
**Counterexample:** Replacing a subterm with a β-equivalent term changes the overall meaning due to non-confluent reduction.

## Cost Dynamics

### INV-PFPL-026: Cost Preservation
**Core Invariant:**
```
If Γ ⊢ e : τ and e ⟼_k e' then the cost k is a non-negative integer
representing the number of primitive steps. Further, if · ⊢ e : τ
then e ⟼*_k v implies the time to fully evaluate e is k units.
```
**Source:** PFPL Chapter 4, Cost Dynamics
**Counterexample:** An infinite loop that claims to terminate in k steps (cost-monotonicity is violated).
