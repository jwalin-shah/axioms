# Axioms

Universal engineering invariants extracted from battle-tested production systems (TCP, PostgreSQL, Redis, Linux, TLS, etc.) and formal textbooks (CLRS, TAPL, PFPL, etc.).

See PRINCIPLES.md for the pattern matching table.
See axioms.json for the 2214 corpus invariants (2208 VERIFIED).
See source-cache/ for the cached source texts.

## Structure
- axioms.json — 2214 invariants, 2208 VERIFIED, 5 DISPUTED, 1 UNCERTAIN
- PRINCIPLES.md — pattern matching table and 8 lessons
- source-cache/ — 50+ cached source files from RFCs, textbooks, kernel docs (incl. go-memory-model.md)
- guidance/ — 68 vacuous axioms with enforcement mechanisms
- books/ — staged formal invariants (Go Memory Model promoted into axioms.json as GOMEM-001..036)
- runs/ — verdict files from verification runs
- MANIFEST.md — what's extracted vs what's on disk
