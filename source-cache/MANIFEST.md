# Source-Cache Extraction Manifest
## Always check this before assuming something is extracted

| File | Lines | Status | What's missing |
|---|---|---|---|
| compiler-invariants-oracle.md | 603 | NOT_EXTRACTED | 33 INV- sections (DFA, LR parsing, type checking, SSA, dataflow, optimization, register allocation, instruction selection) — Dragon Book, Cooper & Torczon, Appel, Muchnick |
| runtime-monitoring-oracle.md | 310 | UNEXTRACTED | Meyer, Lamport, Alpern-Schneider, Leveson, SRE — 40 axioms claimed but not linked to this source |
| saip-oracle.md | 410 | UNEXTRACTED | Quality attribute scenarios from Bass, Clements, Kazman (SAIP 4th ed) |
| tapl-oracle.md | 289 | PARTIAL | 2/8 sections extracted. Missing: Lambda Calculus, Simple Types, Subtyping, Recursive Types, Type Inference, Featherweight Calculi |
| postgresql.md | 44 | UNEXTRACTED | Error severity tiers, WAL invariants, MVCC rules from 30 years of production |
| sqlite-testing.md | 44 | UNEXTRACTED | I/O error injection, coverage-guided testing from the most-tested codebase |
| gvisor.md | 26 | UNEXTRACTED | 7-layer sandbox model vs orbit's 1-layer containment |
| pty.md | 63 | UNEXTRACTED | PTY lifecycle invariants, POSIX terminal rules |

## How to update
After running extraction, update the manifest file and run:
```bash
python3 -c "
import json, os, re
# Re-run the manifest generation script
"
```
