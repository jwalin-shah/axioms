# Compiler Invariants Oracle

Sources:
- Aho, Lam, Sethi, Ullman "Compilers: Principles, Techniques, and Tools" (Dragon Book, 2nd ed, Addison-Wesley, 2006)
- Cooper & Torczon "Engineering a Compiler" (2nd ed, Morgan Kaufmann, 2011)
- Appel "Modern Compiler Implementation in C/Java/ML" (Tiger Book, Cambridge University Press, 1998)
- Muchnick "Advanced Compiler Design and Implementation" (Morgan Kaufmann, 1997)

This is how you PROVE that a compiler transformation is correct. Every invariant is a
predicate that must hold at a specific point in the compilation pipeline. Break one, and
the output program may compute the wrong answer, crash, or loop forever.

---

## Phase 1: Lexical Analysis (Scanning)

### INV-LEX-001: DFA Determinism
**Core Invariant:**
```
∀ regex R: ∃ DFA D such that L(R) = L(D)
∀ state q of D, ∀ character c: |δ(q, c)| ≤ 1 (determinism)
```

**Source:** Dragon Book, Chapters 3.6-3.7 (Thompson construction + subset construction); Cooper & Torczon, Chapter 2.4.

**What this means:** Every regular expression can be compiled to a DFA. The DFA has exactly zero or one transition per (state, character) pair. No ambiguity at the state-machine level.

**Prompt injection:** "You are a lexer correctness verifier. Prove that the generated DFA accepts exactly the language of the source regex. For every state and character, there is at most one transition. The DFA must halt on every input in at most |input| steps."

**Verification:**
- Exhaustive test: for all strings up to length N over alphabet Σ, regex match result == DFA simulation result
- DFA construction test: for every state q and character c, δ(q, c) is in States ∪ {error}
- Property: minimize(DFA) has fewer or equal states than the original DFA
- Property: the minimized DFA is unique up to state renaming

---

### INV-LEX-002: Longest-Match (Maximal Munch)
**Core Invariant:**
```
∀ input string w, ∀ token patterns {p₁, ..., pₙ}:
  lex(w) = the token t such that:
    (1) w = prefix·w' and prefix ∈ L(p_t)
    (2) ¬∃ longer prefix': |prefix'| > |prefix| ∧ prefix' ∈ L(p_j) for some j
```

**Source:** Dragon Book, Chapter 3.8; Cooper & Torczon, Chapter 2.5.

**What this means:** The lexer always consumes the longest possible prefix that matches any token pattern. "for" is a keyword, not identifier "f" followed by identifier "or". This is the rule that makes lexers deterministic in practice.

**Prompt injection:** "You are a longest-match invariant checker. For any input, verify the lexer consumed the maximum-length token prefix possible. Given two competing patterns, the longer match wins. Given equal-length matches, the higher-priority pattern wins. Never leave characters that could have been consumed as part of a valid token."

**Verification:**
- For every token boundary in a test corpus, there is no longer match starting at the same position
- Fuzz test: generate random valid token sequences, concatenate, verify lexer reconstructs them
- Priority test: for ambiguous inputs (e.g., "<<" as two less-than or one left-shift), the lexer respects pattern priority when matches are equal-length

---

### INV-LEX-003: Lexer Halt
**Core Invariant:**
```
∀ input string w of length n: lex(w) halts in O(n) character reads
∀ position i in w: the DFA advances at most once per character consumed
```

**Source:** Dragon Book, Chapter 3.4 (DFA simulation); Cooper & Torczon, Chapter 2.6.

**What this means:** Lexing is linear time. No backtracking. No exponential blowup. Each character is read once.

**Prompt injection:** "You are a termination and complexity verifier. Prove the lexer processes each character exactly once. The number of DFA transitions taken equals the length of the input plus the number of tokens produced. There is no loop that consumes zero characters."

**Verification:**
- Instrument the lexer to count character reads; verify reads = |input|
- Test on adversarial inputs (e.g., 10MB of continuous letters as one identifier)
- Measure: wall-clock time must be linear in input size (regression test)

---

## Phase 2: Syntax Analysis (Parsing)

### INV-PARSE-001: Language Recognition Correctness
**Core Invariant:**
```
∀ input string w: w ∈ L(G) ⇔ parse(w) returns a valid parse tree / AST
∀ input string w: w ∉ L(G) ⇔ parse(w) returns an error (no false positives, no false negatives)
```

**Source:** Dragon Book, Chapter 4.2 (CFG definition, ambiguity, parse trees); Cooper & Torczon, Chapter 3.2.

**What this means:** The parser is a decision procedure for context-free language membership. It accepts iff the string is in the language. It rejects otherwise (with a useful error).

**Prompt injection:** "You are a parser correctness verifier. For a given grammar G, prove the parser is sound (every accepted string is in L(G)) and complete (every string in L(G) is accepted). For LR parsers, verify the parsing table entries are correct per the construction algorithm. Shift/reduce and reduce/reduce conflicts must be resolved by the stated disambiguation rules, not left to undefined behavior."

**Verification:**
- Soundness: for every accepted input, reconstruct a rightmost derivation; verify each step matches the grammar
- Completeness: generate random strings in L(G) via grammar-driven generation; verify parser accepts all
- Negative test: mutate accepted strings to produce strings outside L(G); verify parser rejects all
- LR table invariant: for any state i and symbol a, at most one entry in action[i, a]

---

### INV-PARSE-002: Parse Tree Uniqueness for Unambiguous Grammars
**Core Invariant:**
```
∀ unambiguous grammar G, ∀ w ∈ L(G):
  ∃! parse tree T such that yield(T) = w ∧ root(T) = S
```

**Source:** Dragon Book, Chapter 4.2-4.3; Cooper & Torczon, Chapter 3.3.

**What this means:** An unambiguous grammar maps each sentence to exactly one structural representation. No string can be parsed two different ways. This is a property of the grammar, enforced by the parser (LR parsers guarantee this for deterministic languages).

**Prompt injection:** "You are a parse-uniqueness verifier. For an LR(1) grammar, every input has exactly one valid parse. The reconstructed derivation is a witness. If two derivations produce the same string, the grammar is ambiguous — flag it. Verify that disambiguation rules (precedence, associativity) resolve all known ambiguities deterministically."

**Verification:**
- For LR table: no reduce/reduce conflicts (ensures uniqueness of reduction)
- For precedence-resolved shift/reduce conflicts: verify the resolution matches the declared precedence table
- Property test: parse(s) == parse(s) under serialization/deserialization round-trip

---

### INV-PARSE-003: LR Shift/Reduce Determinism
**Core Invariant:**
```
∀ LR(1) parsing table action[state, lookahead]:
  |action[state, lookahead]| ≤ 1  (at most one shift or reduce, never both)
∀ state with a reduce item A → α· {x}: no other action for that state and lookahead x
```

**Source:** Dragon Book, Chapter 4.5-4.7 (LR parsing algorithms); Cooper & Torczon, Chapter 3.5.

**What this means:** The LR parsing table encodes a deterministic pushdown automaton. Every (state, lookahead) pair maps to at most one action. This is the definition of LR(1) — no conflicts remain after using one token of lookahead.

**Prompt injection:** "You are an LR table invariant checker. Walk every entry of every state. For SLR(1), LALR(1), and canonical LR(1) tables, prove correctness: shift entries derive from transition(goto) entries in the LR automaton, reduce entries derive from item-set membership. Verify that the driver algorithm using the table correctly simulates the characteristic finite-state machine of the grammar."

**Verification:**
- Enumerate every (state, symbol) pair; assert at most one action
- For canonical LR(1): LR items in each state must agree on the core (first component)
- For LALR(1) merging: verify no reduce/reduce conflicts are introduced by merge
- Property: if a state contains both A → α· and B → β·aγ, action[state, a] = shift (shift/reduce resolved by lookahead)

---

### INV-PARSE-004: FIRST/FOLLOW Fixed Point
**Core Invariant:**
```
∀ grammar symbol X:
  FIRST(X) = {a | X ⇒* aα} ∪ {ε if X ⇒* ε}   (least fixed point)
  FOLLOW(A) = {a | S ⇒* αAaβ} ∪ {$ if S ⇒* αA} (least fixed point)
  Nullable(X) ⇔ X ⇒* ε                         (least fixed point)
```

**Source:** Dragon Book, Chapter 4.4; Cooper & Torczon, Chapter 3.4.

**What this means:** FIRST, FOLLOW, and Nullable are computed as least fixed points of monotone equations over finite sets. The algorithm iterates to convergence — and it always converges because the lattice is finite and the functions are monotone.

**Prompt injection:** "You are a grammar analysis verifier. Compute FIRST, FOLLOW, and Nullable from the defining equations as least fixed points. Verify each computed set against the definition: every member must be derivable, and every derivable terminal/eof must be a member. The fixed-point iteration terminates when no set grows — this is provably at most O(|N| × |T|) iterations for a grammar with nonterminals N and terminals T."

**Verification:**
- For each terminal a in FIRST(X): verify there exists a derivation X ⇒* a...
- For ε in FIRST(X): verify X ⇒* ε
- For each terminal a in FOLLOW(A): verify there exists a sentential form ...Aa...
- Property: the sets only grow during iteration (monotonicity)
- Termination: within |N| rounds, no set grows (fixed point reached)

---

## Phase 3: Semantic Analysis (Type Checking)

### INV-SEM-001: Type Preservation Under Evaluation
**Core Invariant:**
```
∀ expression e, ∀ typing environment Γ:
  Γ ⊢ e : T  ⇒  eval(e) produces a value of type T ∨ diverges ∨ raises a defined exception
  (No "method not found," "cannot add int and string," or nil-deref from well-typed code)
```

**Source:** Appel, Chapter 5 (Semantic Analysis, type-checking visitor); Dragon Book, Chapter 6.3 (type checking).

**What this means:** The type checker is a static proof that certain runtime errors cannot occur. A well-typed expression never produces a "type error" at runtime. This is Pierce's Progress and Preservation in the compiler context.

**Prompt injection:** "You are a type-safety verifier. Walk the type-checking visitor. For every AST node kind, there is exactly one typing rule. Prove: if the type checker accepts a program, then executing that program cannot produce a type error (method-not-found, field-not-found, operator type mismatch). The type checker must reject any program that could produce such an error. Counterexample: find a program that passes the type checker but produces a type error at runtime."

**Verification:**
- Fuzz test: generate random well-typed ASTs; compile and run; verify no type-error panics
- Negative test: for each typing rule, generate a violation; verify type checker rejects
- Structural induction: prove by cases on AST nodes that type-check(node) == T implies eval(node) produces T
- For Go specifically: `go vet`, `golangci-lint` with type-check rules

---

### INV-SEM-002: Symbol Resolution (Declaration Before Use)
**Core Invariant:**
```
∀ identifier use at program point p in scope S:
  ∃! declaration D such that D is the innermost declaration of that identifier visible at p
  ∧ D is lexically before p (or in a mutually recursive group with p)
```

**Source:** Dragon Book, Chapter 6.2 (symbol tables); Appel, Chapter 5; Cooper & Torczon, Chapter 4.

**What this means:** Every use of a name resolves to exactly one declaration. No undefined variables. No ambiguous references. The most-closely-nested scope wins (lexical scoping).

**Prompt injection:** "You are a symbol resolution verifier. Walk every identifier use in the AST. Each use must resolve to exactly one declaration. The resolution follows lexical scoping rules: inner scopes shadow outer scopes. Verify that the symbol table correctly implements this with a stack of scopes (enter/exit) and a hash map per scope. After type-checking, there must be zero 'unresolved identifier' errors."

**Verification:**
- For every identifier node: binding is not null and is the innermost declaration in scope
- Shadow test: declare x in outer scope, redeclare in inner scope; inner uses resolve to inner declaration
- Undefined test: use an undefined identifier; type checker must produce error (not crash)
- Recursive test: mutually recursive functions must be able to refer to each other

---

### INV-SEM-003: Type Unification (Structural Type Equality)
**Core Invariant:**
```
∀ types T₁, T₂:
  compatible(T₁, T₂) ⇔
    T₁ = T₂ (base types equal)
    ∨ T₁ = [N]T₁' ∧ T₂ = [M]T₂' ∧ compatible(T₁', T₂') (array structural equality)
    ∨ T₁ = record{fᵢ: Sᵢ} ∧ T₂ = record{gⱼ: Tⱼ} ∧ ∀fᵢ: ∃!gⱼ with same name ∧ compatible(Sᵢ, Tⱼ)
    ∨ T₁ = T₁' → S₁ ∧ T₂ = T₂' → S₂ ∧ compatible(T₁', T₂') ∧ compatible(S₁, S₂)
    ∨ T₁ <: T₂ ∨ T₂ <: T₁ (subtype polymorphic unification)
```

**Source:** Appel, Chapter 5; Dragon Book, Chapter 6.3; Pierce TAPL (2002) for subtyping.

**What this means:** Type compatibility is defined recursively by structural induction. Two types are compatible if they have the same structure. For languages with subtyping, a subtype is compatible wherever its supertype is expected.

**Prompt injection:** "You are a type-unification verifier. Verify the type checker's unification algorithm. For recursive types, the unification must terminate (occurs check). For nominal type systems, name equality suffices. For structural type systems, check the full recursive structure. Unification failure must produce an error message naming both types and the location."

**Verification:**
- Unit test: for each type constructor (array, record, function, reference), test equal pairs and unequal pairs
- Recursive type test: verify occurs-check prevents infinite unification (e.g., X = X → int)
- Subtyping test: if S <: T, then compatible(S, T) is true; if incompatible, compatible returns false
- Round-trip: unify(T, T) must return success for all types T

---

### INV-SEM-004: Expression Type Inference (Bottom-Up)
**Core Invariant:**
```
∀ operator op with signature f: (T₁, ..., Tₙ) → T_result:
  ∀ operands e₁:t₁, ..., eₙ:tₙ:
    if compatible(tᵢ, Tᵢ) for all i:
      type(op(e₁, ..., eₙ)) = T_result
    else:
      type error
```

**Source:** Dragon Book, Chapter 6.3-6.4 (type expressions, type checking of expressions); Appel, Chapter 5.

**What this means:** Expression types are computed bottom-up. Each operator has a type signature. The result type is determined by the operator and the (possibly coerced) operand types.

**Prompt injection:** "You are an expression-type checker. Walk the AST bottom-up. For every expression node, verify the inferred type against the operator's signature. If an operand type is incompatible with the operator's expected operand type, reject with a precise error. If coercion rules exist, verify they are applied correctly and deterministically."

**Verification:**
- For each binary operator: test all (type(left), type(right)) combinations; verify correct result type or error
- Overload resolution: if operator is overloaded, test that the most-specific applicable overload is chosen
- Coercion: verify that implicit coercions are only applied when explicitly allowed (e.g., int → float)
- No coercion: verify that a type mismatch with no valid coercion produces an error

---

## Phase 4: Intermediate Representations

### INV-IR-001: AST-to-IR Preservation of Semantics
**Core Invariant:**
```
∀ program P, ∀ input i:
  eval_AST(P, i) = eval_IR(translate(P), i)
  (The IR faithfully represents the original program's semantics)
```

**Source:** Dragon Book, Chapter 6.4-6.6 (three-address code); Appel, Chapter 7 (translation to IR trees); Cooper & Torczon, Chapter 5.

**What this means:** Translation from AST to IR must preserve the meaning of the program. The IR may be lower-level but it computes the same result. This is the first semantic-preservation invariant in the compilation pipeline.

**Prompt injection:** "You are an IR correctness verifier. For a set of test programs, evaluate the AST interpreter and the IR interpreter on the same inputs. They must produce identical results. Verify that the IR linearization of expressions respects operator precedence and evaluation order. Temporary names must be unique (SSA property or virtual register property). Every high-level construct must have a deterministic IR translation."

**Verification:**
- Differential test: run AST interpreter vs IR interpreter on random programs; results must match
- IR validation: every temporary is defined exactly once before use (in basic-block-local scope)
- Expression tree test: flatten(a + b * c) must compute b*c first, then a+result
- Control flow: if-then-else and while must translate to correct basic-block CFG edges

---

### INV-IR-002: Basic Block Partition
**Core Invariant:**
```
∀ CFG (V, E, entry, exit):
  V is partitioned into basic blocks B₁, ..., Bₖ such that:
    ∀ block B: B = [i₁, i₂, ..., iₙ] where:
      (1) Only iₙ may be a branch/jump (last instruction)
      (2) Only i₁ may be a branch target (first instruction, reached only via label)
      (3) No other instruction in B is a branch or branch target
      (4) ∀ edge (Bᵢ, Bⱼ) ∈ E: the last instruction of Bᵢ can transfer to the first instruction of Bⱼ
```

**Source:** Dragon Book, Chapter 8.4 (basic blocks and flow graphs); Appel, Chapter 8 (basic blocks and traces); Muchnick, Chapter 7.

**What this means:** A basic block is a maximal straight-line sequence of instructions. Execution enters at the top and exits at the bottom. No jumps in, no jumps out, except at boundaries. This is the fundamental unit of local optimization.

**Prompt injection:** "You are a basic block invariant checker. Partition every IR sequence into maximal straight-line code segments. Verify: no internal labels (all labels are at block start), no internal jumps (all branches are at block end), no fall-through ambiguity (each block has at most one fall-through successor). The CFG edge condition must hold: for every edge, the source's last instruction can branch to the target's first instruction."

**Verification:**
- For every instruction at position k in a block: if k < n, instruction k is not a branch, jump, or label target
- For every label: it starts a basic block
- For every branch: it ends a basic block
- CFG completeness: every instruction is in exactly one basic block
- Edge validation: every cfg edge corresponds to a possible control transfer

---

### INV-IR-003: Dominator Tree Correctness
**Core Invariant:**
```
∀ CFG with entry node r:
  DOM(n) = {m | every path from r to n includes m}
  ∀ n ≠ r: r ∈ DOM(n)  (entry dominates every node)
  ∀ n: n ∈ DOM(n)      (reflexivity)
  ∀ n ≠ r: |IDOM(n)| = 1  (every non-entry node has exactly one immediate dominator)
  The dominator relation forms a rooted tree with r as root
```

**Source:** Cooper & Torczon, Chapter 9.2 (dominance); Muchnick, Chapter 7; Dragon Book, Chapter 8.4.

**What this means:** Node m dominates node n if every path from entry to n goes through m. The immediate dominator IDOM(n) is the unique node that dominates n and is dominated by all other dominators of n. The IDOM relation forms a tree — this tree is the basis for SSA construction, loop detection, and control-dependence analysis.

**Prompt injection:** "You are a dominator invariant verifier. Compute DOM sets from the definition (intersection of all-path dominators) and from the iterative dataflow algorithm. They must agree. Every non-entry node must have exactly one immediate dominator. The IDOM edges must form a tree (no cycles, root at entry). Verify that the dominance frontier is computed correctly."

**Verification:**
- Compare: naive DOM (path enumeration) == fast DOM (Lengauer-Tarjan) for all nodes on small CFGs
- IDOM tree property: no cycles in IDOM, entry has no IDOM, all other nodes have exactly one IDOM
- Loop header identification: a loop header n has an incoming edge from a node m such that n dominates m (back edge)
- Dominance frontier: ∀ n, DF(n) = {m | n dominates a predecessor of m, but n does not strictly dominate m}

---

## Phase 5: SSA (Static Single Assignment) Form

### INV-SSA-001: Single Definition, Dominating Definition
**Core Invariant:**
```
∀ SSA-form program:
  ∀ variable v, ∀ use of v at instruction i:
    ∃! definition d of v such that d dominates i
    (d is the unique reaching definition; no ambiguity)
```

**Source:** Cytron, Ferrante, Rosen, Wegman, Zadeck "Efficiently Computing Static Single Assignment Form and the Control Dependence Graph" (ACM TOPLAS 1991); Cooper & Torczon, Chapter 9.3; Muchnick, Chapter 7.

**What this means:** SSA is the workhorse IR invariant. Every variable is assigned exactly once in the source text (statically). At a merge point, φ-functions define new variable versions. The definition that reaches a use is unique and dominates the use.

**Prompt injection:** "You are an SSA invariant verifier. Walk every variable use. Verify it has exactly one reaching definition. That definition must dominate the use in the CFG. For φ-function operands, verify that the i-th operand corresponds to the i-th CFG predecessor. No variable is defined more than once in the source (SSA names are distinct for distinct definitions)."

**Verification:**
- Single-def: scan the IR; each SSA name appears on the LHS of at most one instruction
- Dominance: for every use of v at instruction i, the definition of v dominates i
- φ-function predecessor match: φ(a, b) at block B with predecessors P₁, P₂ means a comes from P₁, b from P₂
- Semantic equivalence: program before and after SSA construction produce identical output on all inputs

---

### INV-SSA-002: Dominance Frontier and φ-Placement
**Core Invariant:**
```
∀ variable v with definitions at nodes D = {d₁, ..., dₖ}:
  A φ-function for v is placed at node n ⇔ n ∈ DF⁺(D)
  (the iterated dominance frontier of all definition sites)

Where DF⁺(D) = the fixed point of:
  DF₁ = DF(D)
  DF_{i+1} = DF(D ∪ DF_i) ∪ DF_i
```

**Source:** Cytron et al. (1991); Cooper & Torczon, Chapter 9.3; Muchnick, Chapter 7.4.

**What this means:** φ-functions are placed exactly at the iterated dominance frontier of all blocks containing definitions of the variable. This placement is both necessary (every path merging two definitions needs a φ) and sufficient (no dead φ-functions). The algorithm is constructive: it computes DF⁺ iteratively and then inserts φ-functions.

**Prompt injection:** "You are a φ-function placement verifier. Given the set of definition blocks for each variable, compute DF⁺. Verify that φ-functions are placed exactly at those nodes. Verify that no φ-function is unnecessary (every φ has at least two distinct reaching definitions along different incoming paths). Verify that no merge of definitions is missing a φ."

**Verification:**
- Completeness: for every edge (A→C, B→C) where A contains a definition of v and B contains a definition of v, C has a φ for v
- Minimality: remove any φ; if the SSA invariant (single reaching definition) still holds, the φ was dead
- DF computation: compare dominance frontier against brute-force: DF(n) = {m | ∃p∈preds(m): n dom p ∧ n does not strictly dom m}
- Idempotence: DF⁺(DF⁺(D)) = DF⁺(D)

---

### INV-SSA-003: Chordal Interference Graph (SSA Property)
**Core Invariant:**
```
∀ SSA-form program:
  The interference graph IG = (V, E) where
    V = {virtual registers / SSA names}
    E = {(u, v) | live ranges of u and v overlap}
  IG is chordal: every cycle of length ≥ 4 has a chord
```

**Source:** Hack, Grund, Goos "Register Allocation for Programs in SSA Form" (CC 2006); Pereira & Palsberg "Register Allocation via Coloring of Chordal Graphs" (APLAS 2005); Cooper & Torczon, Chapter 13.

**What this means:** SSA form induces a chordal interference graph. Chordal graphs can be colored optimally in O(|V| + |E|) time using a perfect elimination order. This makes SSA-based register allocation both faster and provably optimal (for a given spill heuristic).

**Prompt injection:** "You are a chordal graph invariant checker. Build the interference graph from the SSA program. Verify it is chordal: for every cycle of length 4 or more, there must be an edge connecting two non-adjacent vertices on the cycle. If the graph is not chordal, the program is not in strict SSA form (or live ranges were computed incorrectly)."

**Verification:**
- Brute-force chordality check for small programs: enumerate all cycles, verify chord exists
- Perfect elimination order: compute by repeatedly removing simplicial vertices; must succeed for chordal graphs
- Coloring optimality: color(IG) = ω(IG) (chromatic number equals clique number) for chordal graphs
- Counterexample test: construct a non-SSA program (multiple defs of same variable); verify its interference graph may not be chordal

---

## Phase 6: Dataflow Analysis

### INV-DF-001: Monotone Framework Convergence
**Core Invariant:**
```
∀ dataflow analysis (L, ⊓, F) where:
  L is a finite-height semilattice with top ⊤ and bottom ⊥
  F = {f₁, ..., fₙ} are monotone transfer functions: x ⊑ y ⇒ f(x) ⊑ f(y)

Then the iterative algorithm:
  IN[n] = ⊓_{p ∈ preds(n)} OUT[p]
  OUT[n] = fₙ(IN[n])
converges to the MFP (maximal fixed point) solution in O(|V| × |L|) iterations.
```

**Source:** Dragon Book, Chapter 9.3 (iterative dataflow analysis); Muchnick, Chapter 11; Cooper & Torczon, Chapter 9.

**What this means:** Every well-formed dataflow analysis converges because the transfer functions are monotone and the lattice has finite height. The result is always a safe approximation — it may be conservative (reporting a fact as true when it's not provably true on all paths) but never unsound (missing a fact that is true).

**Prompt injection:** "You are a dataflow framework verifier. For a given analysis, verify that (1) the lattice is finite-height (no infinite ascending chains), (2) transfer functions are monotone, (3) the iterative solver terminates when a fixed point is reached. Compare the computed solution against the MOP (meet over all paths) solution for small programs: MFP ⊑ MOP always holds. If transfer functions are distributive, MFP = MOP."

**Verification:**
- Termination: instrument the solver; verify the number of iterations ≤ |L| × |V|
- Monotonicity: for every transfer function f and lattice values x ⊑ y, verify f(x) ⊑ f(y) on representative inputs
- Safe approximation: run a program with the dataflow facts; verify no fact that is "false" according to the analysis is actually "true" at runtime
- Distributivity test: if f(x ⊓ y) = f(x) ⊓ f(y) for all x, y, then verify MFP = MOP on small programs

---

### INV-DF-002: Reaching Definitions Correctness
**Core Invariant:**
```
∀ definition d of variable v:
  d ∈ RD_in(p) ⇔ ∃ path from d to p along which v is not redefined
  d ∉ RD_in(p) ⇔ ∀ paths from d to p: v is redefined before reaching p
```

**Source:** Dragon Book, Chapter 9.2; Muchnick, Chapter 11; Cooper & Torczon, Chapter 9.

**What this means:** Reaching definitions is a forward-may analysis. A definition d reaches point p if there exists some execution path where d's value is still live at p. This is the basis for constant propagation, copy propagation, and use-def chains.

**Prompt injection:** "You are a reaching-definitions verifier. Compute RD from the definition (all-paths enumeration for small programs) and from the iterative dataflow solver. Verify they agree. For every use of v at point p, the reaching definitions determine which definition(s) could provide v's value. If exactly one definition reaches, that use has a unique definition (use-def chain). If multiple reach, there is ambiguity."

**Verification:**
- Small program exhaustive: enumerate all paths; RD_in(p) = {d | d reaches p on at least one path}
- Dataflow convergence: verify the iterative solver's result matches path enumeration for programs with ≤ 100 paths
- Use-def completeness: every use of a variable has at least one reaching definition (or it's undefined → error)
- Kill/gen correctness: OUT[B] = gen[B] ∪ (IN[B] − kill[B]) faithfully models the effect of block B

---

### INV-DF-003: Liveness is the Dual of Reaching Definitions
**Core Invariant:**
```
∀ variable v, ∀ program point p:
  v is live-out at p ⇔ ∃ use of v at q reachable from p along a v-clear path
  v is dead at p ⇔ no use of v is reachable from p (or every path redefines v before any use)
```

**Source:** Dragon Book, Chapter 9.2; Appel, Chapter 10; Muchnick, Chapter 11.

**What this means:** Liveness is a backward-may analysis. A variable is live at a point if its current value might be used in the future. This drives register allocation: dead variables don't need registers. Live variables interfere.

**Prompt injection:** "You are a liveness verifier. Compute live-in/live-out from the definition (backward path enumeration) and from the dataflow solver. Verify they agree. A variable is live at a use point (use → gen). A variable is dead after its last use. The live range of v is the set of program points between v's definition and its last use along any path."

**Verification:**
- Path test: for each definition-use pair, verify v is live at all points on some path from def to use
- Dead test: after the last use of v on all paths, v must be dead
- Backwards dataflow: live_in[B] = use[B] ∪ (live_out[B] − def[B])
- Dual of RD: live variables = "which variables reach backward from uses to definitions" — the lattice is inverted

---

## Phase 7: Optimization Correctness

### INV-OPT-001: Semantics Preservation (The Prime Directive)
**Core Invariant:**
```
∀ optimization pass P, ∀ program π, ∀ input i:
  ⟦P(π)⟧(i) = ⟦π⟧(i)
  (The optimized program produces identical observable output)
```

**Source:** Muchnick, Chapter 10; Dragon Book, Chapter 9.1; Cooper & Torczon, Chapter 10.

**What this means:** No optimization may change what the program computes. Speed, size, register pressure — all secondary. The first law of optimization is "thou shalt not change the semantics." Every optimization pass must be proven correct against this invariant.

**Prompt injection:** "You are an optimization correctness verifier. For a given optimization pass, construct a proof that it preserves semantics. The proof must be staged: (1) local correctness — for a single basic block, (2) regional correctness — extended basic blocks, (3) global correctness — whole CFG with loops. Test on a corpus of programs: run before and after optimization on the same inputs, verify identical outputs. Fuzz the optimizer: random IR, apply optimization, verify round-trip equivalence."

**Verification:**
- Differential testing: for N random programs and M random inputs, verify ⟦opt(π)⟧(i) = ⟦π⟧(i)
- Regression suite: run the optimization on a fixed corpus; verify outputs unchanged
- Bisimulation: define a relation R between unoptimized and optimized states; prove it's a bisimulation
- Alive2-style: use SMT to verify pre- and post-optimization equivalence for each peephole pattern

---

### INV-OPT-002: Constant Propagation Soundness
**Core Invariant:**
```
∀ variable v at program point p:
  if constant-prop(v, p) = c (constant value c):
    then on every execution path reaching p, v has value c
  if constant-prop(v, p) = ⊤ (unknown/not-constant):
    then no claim is made (may or may not be constant)
  if constant-prop(v, p) = ⊥ (unreachable):
    then p is unreachable
```

**Source:** Muchnick, Chapter 12; Dragon Book, Chapter 9.4; Cooper & Torczon, Chapter 10.

**What this means:** Constant propagation is a must-analysis. It only claims a value is constant if the value is provably constant on all paths. The lattice is {unreachable, c₁, c₂, ..., unknown} — finite height, monotone, converging. Replacing a variable use with a constant is safe only if the analysis says it's constant at that point.

**Prompt injection:** "You are a constant-propagation verifier. For every claim that v = c at point p, verify by exhaustive path enumeration (for small programs) that every definition of v reaching p has value c. If any reaching definition has a different value or is unknown, v must not be claimed constant. Assert that replacing a variable use with a claimed-constant value does not change program output."

**Verification:**
- Soundness: for every constant claim, instrument the program; at runtime, verify v == c at that point
- Lattice properties: meet(⊥, c) = c; meet(c₁, c₂) = c₁ if c₁ == c₂ else ⊤
- SCCP (Sparse Conditional Constant Propagation): verify it finds more constants than simple constant propagation
- Negative: construct a program where v is constant but the analysis fails to detect it (precision, not soundness, gap)

---

### INV-OPT-003: Dead Code Elimination Soundness
**Core Invariant:**
```
∀ instruction i removed by DCE:
  The value computed by i is dead: no live use of i's destination exists
  ∧ i has no side effects that are observable by the program
  (Pure dead code: compute but never used. Effectful "dead" code: not really dead.)
```

**Source:** Cooper & Torczon, Chapter 10; Muchnick, Chapter 10; Dragon Book, Chapter 9.4.

**What this means:** An instruction is dead if its result is never used (along any path) and it has no side effects. Removing dead code preserves semantics because dead code, by definition, does not affect any observable output. The tricky case is effectful instructions (calls, stores) — they may appear dead but their side effects are observable.

**Prompt injection:** "You are a DCE verifier. Verify every eliminated instruction: (1) compute liveness; (2) the destination variable is dead after this instruction; (3) the instruction has no side effects (no stores, no calls, no volatile operations). If any of these fails, the elimination is unsound. Run the program before and after DCE with identical inputs; verify identical output, side effects, and IO."

**Verification:**
- Liveness check: for every eliminated instruction, its destination is dead-out in the block
- Side-effect check: eliminated instructions must not be stores, calls, or volatile ops
- If a store is eliminated because the stored location is dead (never loaded), verify the store's target is not aliased by any live pointer
- Regression: run full test suite after DCE; all outputs must be identical

---

### INV-OPT-004: Available Expressions Correctness
**Core Invariant:**
```
∀ expression e (e.g., x + y) at program point p:
  e ∈ AE_in(p) ⇔ along EVERY path from entry to p:
    (1) e was computed at some point q before p on that path
    (2) neither x nor y was redefined between q and p on that path
```

**Source:** Dragon Book, Chapter 9.2; Muchnick, Chapter 11; Cooper & Torczon, Chapter 10.

**What this means:** Available expressions is an all-paths (must) analysis. An expression is available at p if it has been computed on every path to p and its operands haven't changed. This enables global common subexpression elimination: if x+y is available, reuse the previously computed value instead of recomputing.

**Prompt injection:** "You are an available-expressions verifier. For every expression claimed available, verify on every path from entry that it was computed and its operands are unchanged. Never claim an expression is available on a path where an operand was overwritten. The available set shrinks when an operand is redefined (kill) and grows when the expression is computed (gen). Verify: AE_in(p) = ∩_{q∈preds(p)} (gen[q] ∪ (AE_in(q) − kill[q]))."

**Verification:**
- Path enumeration: for small programs, enumerate all paths; AE_in(p) = set of expressions computed on all paths without operand redefinition
- Kill/gen correctness: killing x when x is redefined; genning x+y when x+y is computed
- Substitution safety: replacing a computation with a previously-available temporary must preserve semantics
- Test: compute x+y at point A and again at point B; if available at B, eliminate the recomputation and verify output unchanged

---

### INV-OPT-005: Loop-Invariant Code Motion Correctness
**Core Invariant:**
```
∀ expression e computed inside loop L:
  e can be hoisted to L's preheader ⇔
    (1) e is loop-invariant: all operands of e are constant or defined outside L
    (2) e dominates all loop exits where e's value is live
    (3) e is in a block that dominates all exits (or guarantee execution)
```

**Source:** Muchnick, Chapter 14; Dragon Book, Chapter 10; Cooper & Torczon, Chapter 10.

**What this means:** Loop-invariant code motion (LICM) moves computations out of loops to reduce execution frequency. But you cannot hoist an expression that might not execute — hoisting a division by zero out of a loop where it's guarded by an if-statement changes semantics.

**Prompt injection:** "You are a LICM verifier. For every hoisted expression, verify: (1) operands are defined outside the loop or are constants; (2) the expression was originally executed on every iteration (dominates all exits) OR the loop is guaranteed to execute at least once (preheader dominates the first back-edge); (3) no side effect in the loop between the original position and the hoisted position could affect the result. Run before/after: identical outputs for all inputs."

**Verification:**
- Invariance: all operands of the hoisted expression are defined outside the loop body
- Dominance: the hoisted expression originally dominated all loop exits where its result is live
- Side-effect safety: no store to an operand's memory location between preheader and original site
- Regression: test loops with 0, 1, and many iterations; output must be unchanged after LICM

---

## Phase 8: Register Allocation

### INV-REG-001: Interference Graph Correctness
**Core Invariant:**
```
∀ register allocation with k available registers (R0 ... R{k-1}):
  ∀ edge (u, v) in interference graph IG:
    live ranges of virtual registers u and v overlap at some program point
    ⇒ u and v cannot be assigned the same physical register
  ∀ valid coloring col: V → {0, ..., k-1}:
    (u, v) ∈ IG ⇒ col(u) ≠ col(v)
```

**Source:** Chaitin "Register Allocation and Spilling via Graph Coloring" (PLDI 1982); Chaitin, Auslander, Chandra, Cocke, Hopkins, Markstein "Register Allocation via Coloring" (1981); Muchnick, Chapter 8; Appel, Chapter 11; Cooper & Torczon, Chapter 13.

**What this means:** Two virtual registers interfere if their live ranges overlap. They must be assigned different physical registers. The register allocation problem reduces to k-coloring the interference graph. This is NP-complete in general, but heuristics (Chaitin-Briggs, priority-based) work well in practice.

**Prompt injection:** "You are a register allocation verifier. Build the interference graph from liveness information. Verify: if two variables are simultaneously live at any program point, they must have an edge in IG and must be assigned different registers. After allocation, no physical register holds two live values simultaneously. For spilled variables, verify that every use is preceded by a reload and every definition is followed by a store."

**Verification:**
- Liveness-based IG: for every pair (u, v) live at the same point, assert (u, v) ∈ IG
- Coloring check: after allocation, for every edge (u, v), col(u) ≠ col(v)
- Simultaneous liveness: at each instruction, all allocated registers hold distinct values
- Spill integrity: if v is spilled, every use of v reads from the spill slot and every def writes to it

---

### INV-REG-002: Spill Correctness (Inserted Loads/Stores)
**Core Invariant:**
```
∀ spilled virtual register v with spill slot at [fp + offset]:
  ∀ use of v in original IR:
    in modified IR: load v_tmp ← [fp + offset]; use v_tmp
  ∀ definition of v in original IR:
    in modified IR: ... compute result into v_tmp; store [fp + offset] ← v_tmp
  After spill insertion, the program produces identical results to before
```

**Source:** Muchnick, Chapter 8; Appel, Chapter 11; Cooper & Torczon, Chapter 13.

**What this means:** Spilling replaces register accesses with memory accesses. Each use of a spilled variable becomes a load; each definition becomes a store. The program must produce the same result — just slower. The spill slot is a stack location, unique per spilled variable (or live range segment after splitting).

**Prompt injection:** "You are a spill-correctness verifier. Walk the spilled program. Every original virtual register use must have a corresponding load from the correct spill slot. Every definition must have a corresponding store. No load/store is inserted for a non-spilled register. The spill slot must be large enough for the variable's type. Run the program before and after spilling with identical inputs; verify identical outputs."

**Verification:**
- Insertion check: every use of spilled variable v has exactly one load before it (no redundant loads within a live range segment)
- Store check: every definition of v has a store after it
- Slot uniqueness: spilled variables have non-overlapping spill slots (or overlapping slots iff their live ranges don't overlap — slot reuse)
- Semantic equivalence: same inputs → same outputs before and after spilling

---

### INV-REG-003: Coalescing Correctness
**Core Invariant:**
```
∀ copy instruction u ← v (or u = v):
  if u and v do not interfere (no edge in IG):
    u and v can be coalesced: assigned the same physical register
    The copy instruction can be eliminated
  After coalescing, the program produces identical results
```

**Source:** Chaitin et al. "Register Allocation via Coloring" (1981); Appel, Chapter 11; Cooper & Torczon, Chapter 13.2.

**What this means:** A copy instruction like `t1 = t2` is redundant if both variables can share a register. Coalescing merges live ranges to eliminate copies, reducing both instruction count and register pressure. Briggs-style coalescing is conservative (only coalesce if it doesn't make the graph non-k-colorable).

**Prompt injection:** "You are a coalescing verifier. For every eliminated copy u ← v, verify that u and v did not interfere before coalescing. After coalescing, verify that all uses of u and v now refer to the same physical register. The copy instruction must be removed. The program must produce identical results. For Briggs coalescing, verify the coalesced node's degree is less than k before accepting the merge."

**Verification:**
- Non-interference: before coalescing, (u, v) ∉ IG edges
- Copy elimination: after coalescing, the copy instruction is gone from the IR
- Uniform register: all uses of u and v now refer to the same physical register
- Conservatives: Briggs rule — coalesce only if the resulting node has < k neighbors of significant degree (≥ k)
- Semantic equivalence: program output unchanged

---

### INV-REG-004: SSA-based Allocation Optimality
**Core Invariant:**
```
∀ SSA-form program with interference graph IG:
  IG is chordal (every cycle of length ≥ 4 has a chord)
  ⇒ color(IG) can be found optimally in O(|V| + |E|) using perfect elimination order
  ⇒ If IG is k-colorable, the optimal coloring uses exactly k registers with no unnecessary spilling
  ⇒ After out-of-SSA translation, register pressure may increase; but within SSA, the allocation is optimal
```

**Source:** Hack, Grund, Goos (CC 2006); Pereira & Palsberg (APLAS 2005); Cooper & Torczon, Chapter 13.4.

**What this means:** SSA form makes register allocation tractable. The interference graph is chordal, and coloring a chordal graph is polynomial. The optimal coloring found in SSA form minimizes spills for that SSA representation. After SSA destruction (φ-elimination), additional copies may increase pressure slightly, but this is bounded.

**Prompt injection:** "You are an SSA-register-allocation optimality verifier. Verify the interference graph is chordal. Verify the perfect elimination order succeeds. Verify the coloring uses ω(IG) colors (the maximum clique size, which equals the chromatic number for chordal graphs). Compare the SSA allocation result against a brute-force optimal allocation for small programs. Spill decisions must be minimal: no spill inserted unless ω(IG) > k."

**Verification:**
- Chordal check: verify interference graph is chordal (every induced cycle of length ≥ 4 has a chord)
- Optimal coloring: number of colors used = ω(IG) (max clique size) for chordal graphs
- Spill minimality: spill a variable only if ω(IG) > k; choose the variable with minimum spill cost
- Out-of-SSA overhead: measure register copies inserted by SSA destruction; verify they are bounded
- Differential: compare allocation quality against a known-good allocator (e.g., LLVM greedy)

---

## Phase 9: Instruction Selection and Scheduling

### INV-ISEL-001: Tree-Pattern Coverage Completeness
**Core Invariant:**
```
∀ IR expression tree T:
  instruction_selection(T) produces a sequence of machine instructions I₁...Iₙ such that:
    (1) Every IR node in T is covered by exactly one instruction pattern
    (2) The instruction sequence computes the same value as T
    (3) The pattern tiles are valid: each tile corresponds to a single machine instruction
```

**Source:** Dragon Book, Chapter 8.6 (tree-pattern matching); Appel, Chapter 9 (instruction selection); Muchnick, Chapter 7 (code selection).

**What this means:** Instruction selection tiles the IR tree with machine instruction patterns. Every node must be covered. No node may be uncovered. No node may be covered twice. The covering must be valid (the tiling maps to real instructions).

**Prompt injection:** "You are an instruction selection verifier. Walk the tiling of the IR tree. Every IR node must be covered by exactly one pattern. Every pattern must correspond to a valid machine instruction in the architecture description. The resulting instruction sequence, when executed, must compute the same result as the IR. For optimal tiling (dynamic programming), verify the cost of the chosen tiling is minimal among all valid tilings."

**Verification:**
- Coverage: enumerate all IR nodes in the expression; each node belongs to exactly one tile
- Valid tiles: each tile matches a machine instruction pattern (check against architecture description)
- Dynamic programming optimality: for small trees, brute-force all possible tilings; compare cost with DP result
- Semantic equivalence: run the IR interpreter and the generated machine code on random inputs; results must match

---

### INV-ISEL-002: Instruction Scheduling Dependence Preservation
**Core Invariant:**
```
∀ original IR block B = [i₁, i₂, ..., iₙ]:
  Scheduled block B' = [i'₁, i'₂, ..., i'ₙ] is a permutation of B such that:
    ∀ i, j: if i must execute before j (read-after-write, write-after-write, write-after-read):
      position(i) < position(j) in B' (dependence order preserved)
```

**Source:** Muchnick, Chapter 9; Cooper & Torczon, Chapter 12; Dragon Book, Chapter 10.

**What this means:** The scheduler reorders instructions to reduce pipeline stalls, but all data and control dependences must be respected. A read-after-write (RAW) dependence means the write must happen before the read. The scheduled program must compute the same results as the original.

**Prompt injection:** "You are an instruction scheduling verifier. Build the dependence DAG from the original instruction sequence. Verify that the scheduled sequence is a topological sort of the DAG. Every RAW (true), WAW (output), and WAR (anti) dependence must be preserved in the schedule. Run before and after scheduling; verify identical results for all inputs."

**Verification:**
- Dependence DAG: build edges for RAW, WAW, WAR; verify the schedule is a topological ordering
- Semantic equivalence: run original and scheduled code; outputs must be identical
- Latency respect: for architectures with known instruction latencies, verify the schedule respects pipeline constraints (no destination read before latency elapses, modulo register renaming)
- No false dependence from register reuse: if the allocator reuses registers, verify the schedule still respects true dependences

---

## Cross-Cutting Invariants

### INV-CROSS-001: Composition of Correct Passes
**Core Invariant:**
```
∀ sequence of correct passes P₁, P₂, ..., Pₖ (each preserving semantics individually):
  ⟦Pₖ(⋯P₂(P₁(π))⋯)⟧ = ⟦π⟧
  (Composition of semantics-preserving passes is semantics-preserving)
```

**Source:** Muchnick, Chapter 10; Dragon Book, Chapter 9.1; Cooper & Torczon, Chapter 10.

**What this means:** If each optimization pass individually preserves semantics, applying them in sequence also preserves semantics. This is transitive. The compiler pipeline is a chain of correctness proofs.

**Prompt injection:** "You are a pipeline composition verifier. For the full compilation pipeline, run the source program and the final compiled program on identical inputs. They must produce identical outputs. Insert checkpoints between passes: if a pass introduces a bug, bisect the pipeline to find it. The composition invariant holds iff every individual pass invariant holds."

**Verification:**
- End-to-end test: compile and run the full test suite; verify all outputs match the reference interpreter
- Bisection: if an end-to-end test fails, bisect between compiler passes to find the first pass that introduces the divergence
- Checkpoint: dump IR between passes; verify each pass is idempotent (applying twice = applying once)
- Round-trip: compile program P to IR, serialize IR, deserialize IR, compile to binary; verify output matches (IR serialization is semantics-preserving)

---

### INV-CROSS-002: CFG Reducibility and Loop Structure
**Core Invariant:**
```
∀ CFG G:
  G is reducible ⇔ G can be reduced to a single node by repeatedly applying T₁ and T₂ transformations
  where T₁ removes a self-loop and T₂ removes a node with a single predecessor (folding it in)
  If G is reducible: all loops are natural loops (single entry, dominated by header)
```

**Source:** Muchnick, Chapter 7; Cooper & Torczon, Chapter 9.

**What this means:** Reducible CFGs have all loops with single entries (natural loops). Structured control flow (if-then-else, while, for) produces reducible CFGs. Unreducible CFGs come from goto-based spaghetti code. Many optimizations assume reducibility.

**Prompt injection:** "You are a CFG reducibility verifier. Apply T₁/T₂ reductions to the CFG. If the graph reduces to a single node, it is reducible. Every back edge must go to a node that dominates its tail (natural loop). If an irreducible CFG is detected, the optimization passes that assume reducibility must conservatively refuse to optimize those regions."

**Verification:**
- T₁/T₂ reduction: repeatedly fold self-loops and single-predecessor nodes; graph must reduce to single node
- Natural loop: for every back edge (n → h), h must dominate n
- If a loop has multiple entries, flag as irreducible; verify optimizations don't miscompile
- Structured code test: generate random structured programs (if/while/for); verify CFG is always reducible

---

## Summary: The Compiler Invariant Test

For any compiler pass, ask:

1. **Semantics preservation:** Does the pass change program output? (If yes, the pass is wrong.)
2. **Liveness:** Are references to dead variables eliminated? (DCE, register deallocation.)
3. **Dominance:** Does every use have a dominating definition? (SSA, def-use integrity.)
4. **Interference:** Do simultaneously-live variables get different registers? (Register allocation.)
5. **Convergence:** Does the analysis terminate? (Monotone framework, finite lattice.)
6. **Typing:** Does the output IR have consistent types? (Type preservation across transformations.)
7. **Coverage:** Is every IR node handled? (Pattern matching, tiling, code generation.)

Compiler correctness is NOT "does the compiler work on my test suite?" — it's "does the compiler preserve the meaning of every valid input program?" The invariants above are the conditions under which the answer is "yes."
