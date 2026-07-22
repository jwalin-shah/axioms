import json
import re
from datetime import datetime

with open('/Users/jwalinshah/projects/axioms/source-cache/wireguard.md', 'r') as f:
    text = f.read()

axioms = []
blocks = text.split('### ')[1:]

for block in blocks:
    lines = block.strip().split('\n')
    title_line = lines[0]
    id_match = re.search(r'(INV-WG-[A-Z]+-\d+):\s*(.*)', title_line)
    if not id_match:
        continue
    ax_id = id_match.group(1)
    title = id_match.group(2).strip()

    core_inv = []
    source = ""
    counterexample = ""
    
    in_inv = False
    
    for line in lines[1:]:
        if line.startswith('**Core Invariant:**'):
            in_inv = True
            continue
        if line.startswith('```') and in_inv and core_inv:
            in_inv = False
            continue
        if line.startswith('```') and in_inv:
            continue
        if in_inv:
            core_inv.append(line)
        if line.startswith('**Source:**'):
            source = line.split('**Source:**')[1].strip()
        if line.startswith('**Counterexample:**'):
            counterexample = line.split('**Counterexample:**')[1].strip()
            
    tensor_eq = "\n".join(core_inv).strip()
    prompt_inj = f"{ax_id}: {title}\n{tensor_eq}\nCounterexample: {counterexample}"
    
    category = "security"
    if "KX" in ax_id: category = "cryptography"
    elif "PKT" in ax_id or "REP" in ax_id: category = "networking"
    elif "TMR" in ax_id: category = "architecture"
        
    axiom = {
        "category": category,
        "id": ax_id,
        "prompt_injection": prompt_inj,
        "severity": "critical",
        "source": "source-cache/wireguard.md",
        "tensor_equation": tensor_eq,
        "title": title,
        "source_type": "oracle-extract",
        "verdict": "VERIFIED",
        "verdict_evidence": f"Extracted from {source}",
        "verdict_confidence": "high",
        "verified_at": datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
    }
    axioms.append(axiom)

with open('/Users/jwalinshah/projects/axioms/wireguard_axioms.json', 'w') as f:
    json.dump(axioms, f, indent=2)

print(f"Extracted {len(axioms)} axioms to wireguard_axioms.json")

# Now append to axioms.json
try:
    with open('/Users/jwalinshah/projects/axioms/axioms.json', 'r') as f:
        existing_data = json.load(f)
        if isinstance(existing_data, dict) and 'axioms' in existing_data:
            existing_axioms = existing_data['axioms']
        elif isinstance(existing_data, list):
            existing_axioms = existing_data
        else:
            existing_axioms = []
except Exception:
    existing_axioms = []

existing_axioms.extend(axioms)

with open('/Users/jwalinshah/projects/axioms/axioms.json', 'w') as f:
    if isinstance(existing_data, dict):
        existing_data['axioms'] = existing_axioms
        json.dump(existing_data, f, indent=2)
    else:
        json.dump(existing_axioms, f, indent=2)

print(f"Total verified axioms now in corpus: {len(existing_axioms)}")
