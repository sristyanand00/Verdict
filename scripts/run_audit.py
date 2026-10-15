#!/usr/bin/env python3
"""
RUN_AUDIT.PY KYA HAI?

Ye ek master script hai jo:
1. Audit run karta hai (1,534 queries)
2. Results ko analyze karta hai
3. Pretty reports print karta hai

USAGE:
    python scripts/run_audit.py

TIME: Takes 10-30 minutes (depends on CPU speed)
"""

import json
import sys
from pathlib import Path

# ============ PATH SETUP ============
# Add project root so imports work
# (taaki verdict module milh jaye)
sys.path.insert(0, str(Path(__file__).parent.parent))

from verdict.audit.audit import run_audit
from verdict.audit.taxonomy import summarize_errors, categorize_error


def analyze_results(audit_json: Path):
    """
    AUDIT RESULTS KO ANALYZE KARO
    
    KYA KAREGA:
    1. audit.json load karo
    2. Errors categorize karo
    3. Pretty report print karo
    
    EXAMPLE OUTPUT:
        AUDIT SUMMARY
        ============
        Total queries: 1534
        ✓ ok: 1510 (98.4%)
        ✗ error: 10 (0.7%)
        ⏱ timeout: 2 (0.1%)
        ...
    """
    
    # ============ STEP 1: Load audit results ============
    if not audit_json.exists():
        print(f"❌ Audit results not found: {audit_json}")
        return

    print(f"\n📊 Loading audit results from {audit_json}...")
    with open(audit_json, encoding="utf-8") as f:
        results = json.load(f)
    print(f"✓ Loaded {len(results)} results\n")

    # ============ STEP 2: Categorize errors ============
    print("=" * 70)
    print("ERROR TAXONOMY (Detailed breakdown)")
    print("=" * 70)
    error_counts = summarize_errors(results)
    
    # Print each error type with count and percentage
    for error_type, count in sorted(error_counts.items()):
        pct = 100 * count / len(results)
        bar = "█" * int(pct / 2)  # Visual bar
        print(f"  {error_type:20s}  {count:4d}  ({pct:5.1f}%)  {bar}")

    # ============ STEP 3: Breakdown by difficulty ============
    print("\n" + "=" * 70)
    print("BREAKDOWN BY DIFFICULTY")
    print("=" * 70)
    
    # Group results by difficulty
    by_difficulty = {}
    for result in results:
        diff = result["difficulty"]
        if diff not in by_difficulty:
            # Initialize counters for this difficulty
            by_difficulty[diff] = {
                "total": 0,
                "ok": 0,
                "error": 0,
                "timeout": 0,
                "blocked": 0,
                "crashed": 0,
            }
        by_difficulty[diff]["total"] += 1
        by_difficulty[diff][result["status"]] += 1

    # Print for each difficulty level
    for diff in ["simple", "moderate", "challenging"]:
        if diff in by_difficulty:
            stats = by_difficulty[diff]
            ok_pct = 100 * stats["ok"] / stats["total"]
            
            print(f"\n  {diff.upper()}:")
            print(f"    Total:    {stats['total']:4d}")
            print(f"    ✓ OK:     {stats['ok']:4d}  ({ok_pct:5.1f}%)")
            print(f"    ✗ Error:  {stats['error']:4d}")
            print(f"    ⏱ Timeout:{stats['timeout']:4d}")
            print(f"    🛑 Blocked:{stats['blocked']:4d}")
            print(f"    💥 Crashed:{stats['crashed']:4d}")

    # ============ STEP 4: Find problematic queries ============
    print("\n" + "=" * 70)
    print("PROBLEM QUERIES (First 10 failures)")
    print("=" * 70)
    
    # Filter results where status != ok
    problems = [r for r in results if r["status"] != "ok"]
    
    # Print first 10 problems
    for i, result in enumerate(problems[:10]):
        print(f"\n  [{i+1}] Question {result['question_id']} (db: {result['db_id']}, {result['difficulty']})")
        print(f"      Status: {result['status']}")
        if result["error_msg"]:
            # Only first 100 chars (taaki readable rahe)
            msg = result["error_msg"][:100]
            print(f"      Error:  {msg}")
        print(f"      Time:   {result['elapsed_ms']:.0f}ms")

    # Summary of all problems
    if len(problems) > 10:
        print(f"\n  ... and {len(problems) - 10} more problems")
    
    print(f"\n  TOTAL PROBLEMS: {len(problems)}/{len(results)}")
    print("=" * 70)


if __name__ == "__main__":
    """
    MAIN EXECUTION
    
    Ye block run hota hai jab script directly chalaye:
        python scripts/run_audit.py
    
    Nahi run hota jab import karo:
        from scripts.run_audit import analyze_results
    """
    
    from verdict import config

    # ============ PRINT HEADER ============
    print("\n" + "🚀 " * 20)
    print("VERDICT AUDIT - BENCHMARK GOLD QUERY VERIFICATION")
    print("🚀 " * 20)
    print("\nThis will run 1,534 gold queries from BIRD.")
    print("Expect 5-30 minutes depending on CPU speed.\n")

    # ============ RUN AUDIT ============
    audit_json = config.results_root() / "audit.json"
    print("Step 1: Running audit...")
    print("-" * 70)
    run_audit(output_json=audit_json)

    # ============ ANALYZE RESULTS ============
    print("Step 2: Analyzing results...")
    print("-" * 70)
    analyze_results(audit_json)

    print("\n✅ Audit complete!")
    print(f"   Results saved to: {audit_json}")
    print("   Next: Run the training pipeline using these verified gold answers.\n")
