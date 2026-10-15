"""
TAXONOMY = Classification system

EXAMPLE:
Doctors ke paas "disease taxonomy" hota hai:
- Fever: cold, flu, malaria, corona
- Cough: allergies, asthma, TB

Similarly, SQL errors ke paas categories hoti hain:
- SQL errors: syntax_error, missing_table, missing_column
- Performance: timeout, slow_query
- Security: blocked_query
- System: crashed
"""

from enum import Enum


class AnnotationError(Enum):
    """
    ERROR TYPES jo BIRD gold queries mein ho sakte hain
    
    ENUM kya hota hai?
    - Fixed set of options
    - Har option ka unique name hota hai
    
    Example use:
        error = AnnotationError.SYNTAX_ERROR
        print(error.value)  # Output: "syntax_error"
    """

    # ============ EXECUTION FAILURES ============
    SYNTAX_ERROR = "syntax_error"  # SQL galat likha hai
    # Example: "SELECT * FORM schools"  (FORM instead of FROM)
    
    MISSING_TABLE = "missing_table"  # Table exist nahi karta
    # Example: "SELECT * FROM unknown_table"
    
    MISSING_COLUMN = "missing_column"  # Column exist nahi karta
    # Example: "SELECT unknown_col FROM schools"
    
    MISSING_DATABASE = "missing_database"  # Database file nahi mila
    # Example: Database corrupt ya deleted

    # ============ PERFORMANCE ISSUES ============
    TIMEOUT = "timeout"  # Query 5 seconds se zyada le gya
    # Usually: complex joins ya missing indexes
    
    SLOW_QUERY = "slow_query"  # Query slow hai (2-5 seconds)
    # Borderline case

    # ============ SECURITY ISSUES ============
    BLOCKED_QUERY = "blocked_query"  # Hum ne intentionally block kiya
    # Example: Query mein DELETE likha tha (unsafe)

    # ============ SYSTEM FAILURES ============
    CRASHED = "crashed"  # Verifier code mein bug tha
    # Rare, usually means something unexpected

    # ============ NO ERROR ============
    OK = "ok"  # Query successfully ran


def categorize_error(status: str, error_msg: str | None = None) -> AnnotationError:
    """
    STATUS se category decide karo
    
    STATUS kya hota hai?
    - "ok" = kaam kar gya
    - "error" = kuch galat tha (details error_msg mein)
    - "timeout" = 5 seconds se zyada lage
    - "blocked" = hum ne block kiya (security)
    - "crashed" = verifier mein bug
    
    ERROR_MSG kya hota hai?
    - SQLite ka error message (jaise "no such table")
    
    EXAMPLE:
        categorize_error("error", "no such table schools")
        # Output: AnnotationError.MISSING_TABLE
        
        categorize_error("timeout", None)
        # Output: AnnotationError.TIMEOUT
    
    LOGIC:
    1. Agar status "ok" = return OK
    2. Agar status "timeout" = return TIMEOUT
    3. Agar status "blocked" = return BLOCKED_QUERY
    4. Agar status "crashed" = return CRASHED
    5. Agar status "error" = dig deeper:
       - Error message dekho
       - Kya likha hai?
       - Accordingly categorize karo
    """
    
    # ============ DIRECT MAPPING ============
    if status == "ok":
        return AnnotationError.OK
    if status == "timeout":
        return AnnotationError.TIMEOUT
    if status == "blocked":
        return AnnotationError.BLOCKED_QUERY
    if status == "crashed":
        return AnnotationError.CRASHED

    # ============ ERROR STATUS - NEED TO READ ERROR MESSAGE ============
    if status == "error":
        # Error message ko lowercase mein convert karo (taaki comparison easy ho)
        msg = (error_msg or "").lower()
        
        # Check different error patterns
        if "syntax" in msg or "near" in msg:
            # SQLite syntax error mein "syntax" or "near" likha hota hai
            # Example: "near SELECT: syntax error"
            return AnnotationError.SYNTAX_ERROR
        
        if "no such table" in msg:
            # Table nahi mila
            # Example: "no such table schools"
            return AnnotationError.MISSING_TABLE
        
        if "no such column" in msg:
            # Column nahi mila
            # Example: "no such column unknown_col"
            return AnnotationError.MISSING_COLUMN
        
        if "unable to open" in msg or "cannot open" in msg:
            # Database file nahi mila
            # Example: "unable to open database file"
            return AnnotationError.MISSING_DATABASE

        # Agar kuch nahi match hua = fallback (default)
        return AnnotationError.SYNTAX_ERROR

    # Agar kuch aur status aaye (impossible but just in case)
    return AnnotationError.SYNTAX_ERROR


def summarize_errors(audit_results: list[dict]) -> dict:
    """
    SUMMARY BANAO = Count karo har category mein kitne errors hain
    
    INPUT:
    audit_results = List of dicts (jaise audit.json se read kiya)
    
    OUTPUT:
    Dict with categories and counts
    
    EXAMPLE:
        results = [
            {"status": "ok", "error_msg": None},
            {"status": "error", "error_msg": "no such table schools"},
            {"status": "timeout", "error_msg": None},
            {"status": "ok", "error_msg": None},
        ]
        
        summary = summarize_errors(results)
        # Output:
        # {
        #     "ok": 2,
        #     "timeout": 1,
        #     "missing_table": 1,
        # }
    """
    from collections import Counter

    categories = Counter()  # Counter = dict jo automatically count karta hai
    
    for result in audit_results:
        # Har result ko categorize karo
        cat = categorize_error(result["status"], result.get("error_msg"))
        # Uska count add karo
        categories[cat.value] += 1

    # Return as sorted dict
    return {cat: count for cat, count in sorted(categories.items())}
