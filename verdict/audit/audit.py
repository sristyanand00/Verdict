"""
AUDIT KYA HOTA HAI?

Suppose tum ne 100 exams liye hain. Ab tum professor haan.
Tum har exam check karte ho:
- Sahi jawab likha hai?
- Ya answer sheet khali hai?
- Ya student ne gibberish likha hai?

BIRD audit same hota hai:
- 1,534 gold SQL questions hain
- Har SQL run karte ho
- Check karte ho: success? timeout? error?
- Results track karte ho

Ye results bad mein training ke time use aate hain.
"""

import json
import time
from dataclasses import dataclass, asdict
from pathlib import Path

from verdict import config
from verdict.data.loaders import load_bird_dev
from verdict.verifier.pool import execute_isolated


@dataclass
class AuditResult:
    """
    Ek audit result iska matlab:
    "Question ID 5 ko maine run kiya, ye result aaya"
    
    FIELDS samjho:
    - question_id: Kaun sa question tha (0-1533)
    - db_id: Kaun sa database (california_schools, etc)
    - difficulty: Kitna hard tha (simple/moderate/challenging)
    - status: Kya hua? 
        * "ok" = SQL ran successfully
        * "error" = SQL syntax error ya kuch galat
        * "timeout" = Query 5 seconds se zyada le gya
        * "blocked" = Hum ne block kar diya (security)
        * "crashed" = Verifier mein bug tha
    - error_msg: Error message (agar koi error tha)
    - elapsed_ms: Kitne milliseconds lage (1000ms = 1 second)
    """
    
    question_id: int
    db_id: str
    difficulty: str
    status: str  # "ok", "error", "timeout", "blocked", "crashed"
    error_msg: str | None = None
    elapsed_ms: float = 0.0


def run_audit(
    dev_json: Path | None = None,
    output_json: Path | None = None,
    timeout_s: float = 5.0,
) -> dict:
    """
    MAIN AUDIT FUNCTION
    
    KYA KAREGA:
    1. BIRD dev.json load karega (1,534 questions)
    2. Har SQL question ko run karega
    3. Results record karega
    4. Summary print karega
    5. Sab results JSON file mein save karega
    
    ARGUMENTS:
    - dev_json: dev.json ka path
    - output_json: Jahan results save karne hain
    - timeout_s: Har query ke liye kitne seconds intezaar karna hai (5 = default)
    
    RETURNS:
    - Dictionary with counts (ok: 1500, error: 20, etc)
    
    EXAMPLE:
        from verdict.audit.audit import run_audit
        
        counts = run_audit()
        # Ye 1,534 queries run karega
        # Results ko results/audit.json mein save karega
        # Screen par summary print karega
    """
    
    # ============ STEP 1: Paths set karo ============
    if dev_json is None:
        dev_json = config.dev_json()  # Default: datasets/dev.json
    if output_json is None:
        output_json = config.results_root() / "audit.json"  # Default: results/audit.json

    # ============ STEP 2: All tasks load karo ============
    print(f"📂 Loading BIRD from {dev_json}...")
    tasks = load_bird_dev(dev_json)  # Loader use karo
    
    # Count karo har difficulty mein kitne questions hain
    simple_count = sum(1 for t in tasks if t.difficulty == 'simple')
    moderate_count = sum(1 for t in tasks if t.difficulty == 'moderate')
    challenging_count = sum(1 for t in tasks if t.difficulty == 'challenging')
    
    print(f"✓ Loaded {len(tasks)} tasks")
    print(f"  - Simple: {simple_count}")
    print(f"  - Moderate: {moderate_count}")
    print(f"  - Challenging: {challenging_count}")

    # ============ STEP 3: Initialize results tracking ============
    results = []  # List jisme sab audit results store honge
    start_time = time.time()  # Start time record karo (speed track karne ke liye)
    
    # Counter for different statuses
    counts = {"ok": 0, "error": 0, "timeout": 0, "blocked": 0, "crashed": 0}

    # ============ STEP 4: RUN AUDIT - Loop mein har task process karo ============
    print(f"\n🔄 Running {len(tasks)} gold queries...")
    print(f"⏱️  (Timeout: {timeout_s}s per query)")
    print("   (This may take 10-30 minutes...)\n")
    
    for i, task in enumerate(tasks):
        # Progress print karo har 100 queries pe
        if (i + 1) % 100 == 0:
            elapsed = time.time() - start_time
            remaining_approx = (elapsed / (i + 1)) * (len(tasks) - i - 1)
            print(f"  ✓ {i + 1}/{len(tasks)} queries ({elapsed:.0f}s elapsed, ~{remaining_approx:.0f}s remaining)")

        # ============ STEP 4a: Execute query ============
        # execute_isolated = ek alag process mein query run karna
        # Taaki agar query hang ho to poori audit hang na ho jaye
        exec_result = execute_isolated(
            sql=task.gold_sql,  # Gold SQL jo BIRD ne likha tha
            db_path=task.db_path,  # Database file ka path
            timeout_s=timeout_s,  # 5 seconds intezaar karo phir stop karo
        )

        # ============ STEP 4b: Record result ============
        audit_result = AuditResult(
            question_id=task.question_id,
            db_id=task.db_id,
            difficulty=task.difficulty,
            status=exec_result.status,  # ok / error / timeout / blocked / crashed
            error_msg=exec_result.error,  # Error message (agar koi tha)
            elapsed_ms=exec_result.elapsed_ms,  # Time laga (milliseconds mein)
        )
        results.append(audit_result)  # List mein add karo
        counts[exec_result.status] += 1  # Counter update karo

    # ============ STEP 5: Save results to JSON ============
    output_json.parent.mkdir(parents=True, exist_ok=True)  # Folder create karo agar nahi hai
    
    # Convert dataclass objects to dictionaries (taaki JSON mein save ho sake)
    results_dict = [asdict(r) for r in results]
    
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(results_dict, f, indent=2)  # indent=2 = pretty print (readable)
    
    print(f"\n✅ Saved {len(results)} results to {output_json}")

    # ============ STEP 6: Print summary ============
    total_time = time.time() - start_time
    print(f"\n{'='*70}")
    print(f"AUDIT SUMMARY ({total_time:.1f}s total)")
    print(f"{'='*70}")
    print(f"Total queries:     {len(results)}")
    print(f"  ✓ ok            {counts['ok']:>4}  ({100*counts['ok']/len(results):>5.1f}%)")
    print(f"  ✗ error         {counts['error']:>4}  ({100*counts['error']/len(results):>5.1f}%)")
    print(f"  ⏱ timeout       {counts['timeout']:>4}  ({100*counts['timeout']/len(results):>5.1f}%)")
    print(f"  🛑 blocked      {counts['blocked']:>4}  ({100*counts['blocked']/len(results):>5.1f}%)")
    print(f"  💥 crashed      {counts['crashed']:>4}  ({100*counts['crashed']/len(results):>5.1f}%)")
    print(f"{'='*70}\n")

    return counts


if __name__ == "__main__":
    # Agar directly Python file run ho to ye execute hoga
    # python verdict/audit/audit.py
    run_audit()
