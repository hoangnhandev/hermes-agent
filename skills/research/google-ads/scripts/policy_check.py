#!/usr/bin/env python3
import json
from pathlib import Path
from typing import Dict, List, Any

POLICY_RULES = {
    "disallowed_terms": [
        "guaranteed", "guarantee", "#1", "number one", "best ever",
        "free money", "get rich", "miracle", "cure", "treat", "prevent",
        "100%", "always", "never", "instant", "immediate"
    ],
    "conditional_terms": [
        "free", "no cost", "complimentary"
    ],
    "character_limits": {
        "headline": 30,
        "description": 90,
        "path": 15
    }
}


def load_restricted_terms(file_path: Path = None) -> List[str]:
    """Load restricted terms from markdown file.

    Args:
        file_path: Path to restricted-terms.md file

    Returns:
        List of restricted terms
    """
    if file_path is None:
        # Default path relative to this script
        file_path = Path(__file__).parent.parent / "references" / "restricted-terms.md"

    if not file_path.exists():
        print(f"[POLICY] Warning: {file_path} not found, using built-in rules")
        return POLICY_RULES["disallowed_terms"]

    try:
        with open(file_path, 'r') as f:
            content = f.read()

        # Parse bullet lines, but keep only real terms (drop advisory prose).
        parsed = []
        for line in content.split('\n'):
            line = line.strip()
            if not (line.startswith(('-', '*')) and len(line) > 2):
                continue
            term = line[1:].strip().lower()
            term = term.replace('**', '').replace('*', '').replace('`', '').strip()
            if not term or term.startswith('#'):
                continue
            # Skip prose: URLs, parentheticals, bracketed refs, em-dashes, or
            # long multi-word advisory sentences that aren't real terms.
            if any(m in term for m in ('http', '(', ')', '[', '—', 'e.g.')):
                continue
            if len(term) > 40 or term.count(' ') > 4:
                continue
            parsed.append(term)

        # MERGE (union, deduped) — the file is ADDITIVE only. The built-in short
        # terms (e.g. "instant", "immediate") must never be dropped, or a
        # markdown file of advisory prose would silently weaken screening.
        merged = list(dict.fromkeys(POLICY_RULES["disallowed_terms"] + parsed))
        return merged or POLICY_RULES["disallowed_terms"]

    except Exception as e:
        print(f"[POLICY] Error loading restricted terms: {e}")
        return POLICY_RULES["disallowed_terms"]


def screen_ad_copy(headlines: List[str], descriptions: List[str], restricted_terms: List[str] = None) -> Dict[str, Any]:
    """Screen ad copy against Google Ads policy rules.

    Args:
        headlines: List of headline texts
        descriptions: List of description texts
        restricted_terms: List of restricted terms (loads from file if None)

    Returns:
        Dict with passed, violations, and warnings
    """
    if restricted_terms is None:
        restricted_terms = load_restricted_terms()

    violations = []
    warnings = []

    # Combine all text for analysis
    all_text = " ".join(headlines + descriptions).lower()

    print(f"[POLICY] Screening ad copy with {len(restricted_terms)} restricted terms")

    # Check for disallowed terms
    for term in restricted_terms:
        if term in all_text:
            violations.append(f"Disallowed term: '{term}'")

    # Check for conditional terms
    for term in POLICY_RULES["conditional_terms"]:
        if term in all_text:
            warnings.append(f"Conditional term: '{term}' — verify actually free")

    # Check character limits
    for i, headline in enumerate(headlines):
        if len(headline) > POLICY_RULES["character_limits"]["headline"]:
            violations.append(f"Headline {i+1} exceeds {POLICY_RULES['character_limits']['headline']} chars ({len(headline)})")
        elif len(headline) == 0:
            violations.append(f"Headline {i+1} is empty")

    for i, description in enumerate(descriptions):
        if len(description) > POLICY_RULES["character_limits"]["description"]:
            violations.append(f"Description {i+1} exceeds {POLICY_RULES['character_limits']['description']} chars ({len(description)})")
        elif len(description) == 0:
            violations.append(f"Description {i+1} is empty")

    # Additional checks
    # Check for excessive punctuation
    for text in headlines + descriptions:
        if text.count('!') > 2:
            violations.append(f"Excessive exclamation marks in: '{text[:50]}...'")

        if text.count('?') > 2:
            violations.append(f"Excessive question marks in: '{text[:50]}...'")

    # Check for ALL CAPS (more than 3 consecutive caps)
    for text in headlines + descriptions:
        words = text.split()
        for word in words:
            if len(word) > 3 and word.isupper() and word.isalpha():
                violations.append(f"ALL CAPS word '{word}' in: '{text[:50]}...'")

    # Check for phone numbers or emails
    import re
    phone_pattern = r'\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b'
    email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'

    for text in headlines + descriptions:
        if re.search(phone_pattern, text):
            violations.append(f"Phone number in: '{text[:50]}...'")

        if re.search(email_pattern, text):
            violations.append(f"Email address in: '{text[:50]}...'")

    result = {
        "passed": len(violations) == 0,
        "violations": violations,
        "warnings": warnings,
        "summary": {
            "headlines_checked": len(headlines),
            "descriptions_checked": len(descriptions),
            "violations_found": len(violations),
            "warnings_found": len(warnings)
        }
    }

    print(f"[POLICY] Screening completed: {len(violations)} violations, {len(warnings)} warnings")

    return result


def print_policy_report(result: Dict[str, Any]):
    """Print a formatted policy screening report."""
    print("\n" + "="*60)
    print("POLICY SCREENING REPORT")
    print("="*60)

    summary = result["summary"]
    print(f"Headlines checked: {summary['headlines_checked']}")
    print(f"Descriptions checked: {summary['descriptions_checked']}")
    print(f"Violations found: {summary['violations_found']}")
    print(f"Warnings found: {summary['warnings_found']}")
    print()

    if result["violations"]:
        print("VIOLATIONS (MUST FIX):")
        for i, violation in enumerate(result["violations"], 1):
            print(f"  {i}. {violation}")
        print()

    if result["warnings"]:
        print("WARNINGS (REVIEW):")
        for i, warning in enumerate(result["warnings"], 1):
            print(f"  {i}. {warning}")
        print()

    if result["passed"]:
        print("✅ PASSED: No policy violations found")
    else:
        print("❌ FAILED: Policy violations found")

    print("="*60)


def main():
    """Test policy screening with sample data."""
    print("[POLICY] Testing policy screening")

    # Test cases
    test_cases = [
        {
            "name": "Clean copy",
            "headlines": ["Professional Plumbing Services", "Expert Plumbers Available", "Local Plumbing Company"],
            "descriptions": ["Professional plumbing services in your area. Call today for a free estimate.", "Reliable and experienced plumbers for all your needs."]
        },
        {
            "name": "Violation copy",
            "headlines": ["GUARANTEED Best Plumbing #1", "Instant Fix All Problems", "100% Satisfaction"],
            "descriptions": ["We GUARANTEE to cure all your plumbing problems instantly. Call now!", "Free money for everyone who uses our service."]
        },
        {
            "name": "Warning copy",
            "headlines": ["Free Plumbing Estimates", "Professional Service", "Local Experts"],
            "descriptions": ["We offer free estimates for all plumbing services. Contact us today.", "Quality work at competitive prices."]
        }
    ]

    for test_case in test_cases:
        print(f"\n--- Testing: {test_case['name']} ---")
        result = screen_ad_copy(test_case["headlines"], test_case["descriptions"])
        print_policy_report(result)


if __name__ == "__main__":
    main()