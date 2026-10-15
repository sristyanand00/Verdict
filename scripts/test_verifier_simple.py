#!/usr/bin/env python3
"""
VERIFIER KA SIMPLE TEST

Ye script:
1. BIRD se first question load karta hai
2. Gold SQL run karta hai
3. Dummy candidate SQL run karta hai
4. Dono ko compare karta hai
5. Result batata hai

MATLAB:
Suppose BIRD mein likha hai:
  Question: "How many schools are there?"
  Gold SQL: "SELECT COUNT(*) FROM schools"

Hum:
  1. Gold SQL run karte hain -> 1000 schools
  2. Candidate SQL likha: "SELECT COUNT(*) FROM schools"  (same)
  3. Compare karte hain -> MATCH! ✓ Correct

Agar candidate tha "SELECT COUNT(*) FROM employees" -> NO MATCH! ✗ Wrong
"""

import sys
from pathlib import Path

# Project root ko path mein add karo
sys.path.insert(0, str(Path(__file__).parent.parent))

from verdict.data.loaders import load_bird_dev
from verdict.verifier.pool import execute_isolated
from verdict.verifier.compare import compare_results


def test_one_question(question_index: int = 0):
    """
    Ek question ko test karo
    
    Args:
        question_index: Kaun sa question (0 = first)
    
    Flow:
    1. Load BIRD
    2. Specific question uthao
    3. Gold SQL run karo
    4. Candidate SQL run karo (we'll use same or slightly modified)
    5. Compare karo
    6. Print results
    """
    
    print("=" * 80)
    print("VERIFIER TEST - STEP BY STEP")
    print("=" * 80)
    
    # ============ STEP 1: LOAD BIRD ============
    print("\n📂 STEP 1: Loading BIRD...")
    try:
        tasks = load_bird_dev()
        print(f"   ✓ Loaded {len(tasks)} questions from BIRD")
    except FileNotFoundError as e:
        print(f"   ✗ ERROR: {e}")
        print(f"   Please download BIRD: .\\scripts\\fetch_bird.ps1")
        return

    # ============ STEP 2: GET FIRST QUESTION ============
    print(f"\n📋 STEP 2: Getting question #{question_index}...")
    task = tasks[question_index]
    
    print(f"   Question ID: {task.question_id}")
    print(f"   Database: {task.db_id}")
    print(f"   Difficulty: {task.difficulty}")
    print(f"   Question: {task.question}")
    print(f"   Database file: {task.db_path}")
    print(f"\n   Gold SQL:")
    print(f"   ----------")
    print(f"   {task.gold_sql}")

    # ============ STEP 3: EXECUTE GOLD SQL ============
    print(f"\n🔄 STEP 3: Executing GOLD SQL...")
    print(f"   (Running in isolated process with 5s timeout)")
    
    gold_result = execute_isolated(
        sql=task.gold_sql,
        db_path=task.db_path,
        timeout_s=5.0,
    )
    
    print(f"   Status: {gold_result.status}")
    print(f"   Rows: {len(gold_result.rows)}")
    print(f"   Columns: {gold_result.columns}")
    print(f"   Time: {gold_result.elapsed_ms:.1f}ms")
    
    if gold_result.error:
        print(f"   Error: {gold_result.error}")
    
    if gold_result.rows:
        print(f"\n   Sample results (first 3 rows):")
        for i, row in enumerate(gold_result.rows[:3]):
            print(f"      {row}")
        if len(gold_result.rows) > 3:
            print(f"      ... and {len(gold_result.rows) - 3} more rows")

    # ============ STEP 4: CREATE CANDIDATE SQL ============
    print(f"\n✏️  STEP 4: Creating CANDIDATE SQL...")
    
    # For testing, we'll try 3 scenarios:
    scenarios = [
        ("CORRECT", task.gold_sql),  # Exact same = should match
        ("WRONG", f"SELECT {task.gold_sql.split('SELECT')[1].split('FROM')[0].strip()} FROM {task.db_id}"),  # Modified
        ("DIFFERENT", "SELECT 1 AS dummy"),  # Completely different
    ]
    
    print(f"   Testing {len(scenarios)} scenarios...\n")
    
    for scenario_name, candidate_sql in scenarios:
        print(f"   [{scenario_name}] Candidate SQL:")
        print(f"   {candidate_sql[:70]}")
        
        # ============ STEP 5a: EXECUTE CANDIDATE SQL ============
        print(f"   Executing...")
        candidate_result = execute_isolated(
            sql=candidate_sql,
            db_path=task.db_path,
            timeout_s=5.0,
        )
        
        print(f"   Status: {candidate_result.status}")
        print(f"   Rows: {len(candidate_result.rows)}")
        
        if candidate_result.error:
            print(f"   Error: {candidate_result.error}")
        
        # ============ STEP 5b: COMPARE RESULTS ============
        print(f"   Comparing...")
        
        if gold_result.status != "ok":
            print(f"   ⚠️  Gold query failed! Skipping comparison.")
            verification_result = None
        else:
            verification_result = compare_results(
                candidate_result,
                gold_result,
                task.gold_sql,
            )
        
        # ============ STEP 6: PRINT VERDICT ============
        print(f"\n   📊 VERDICT:")
        if verification_result is None:
            print(f"      Status: INVALID (gold failed)")
        else:
            verdict = verification_result.verdict
            reason = verification_result.reason
            
            if verdict == "correct":
                print(f"      ✅ CORRECT")
            elif verdict == "wrong":
                print(f"      ❌ WRONG")
            else:
                print(f"      ⚠️  INVALID")
            
            print(f"      Reason: {reason}")
        print()
    
    print("=" * 80)
    print("TEST COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    """
    USAGE:
    
    python scripts/test_verifier_simple.py
    # Tests first question (index 0)
    
    python scripts/test_verifier_simple.py
    # Can also pass question index:
    # python scripts/test_verifier_simple.py 5
    """
    
    import sys
    
    question_idx = 0
    if len(sys.argv) > 1:
        try:
            question_idx = int(sys.argv[1])
        except ValueError:
            print(f"Usage: python {sys.argv[0]} [question_index]")
            sys.exit(1)
    
    test_one_question(question_idx)
