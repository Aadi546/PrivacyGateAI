"""Bounded, local address-proof comparison. Never returns raw document text."""
import re

POLICY_VERSION = "address-proof-v1"
TIERS = ["Government IDs and financial activity", "Account identifiers", "Contact and billing details", "Metadata"]
LABELS = {
    "aadhaar": (0, "Aadhaar-like number"), "pan": (0, "PAN-like number"),
    "balance": (0, "Financial balance"), "transactions": (0, "Transaction history"),
    "bank_account": (1, "Bank account identifier"), "utility_account": (1, "Utility/customer identifier"),
    "phone": (2, "Phone number"), "email": (2, "Email address"),
    "usage": (2, "Utility usage / meter reading"), "billing": (2, "Billing / payment details"),
}
DATE = re.compile(r"\b(?:\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}|20\d{2}-\d{2}-\d{2})\b")
MONEY = re.compile(r"(?:\b(?:INR|USD|Rs\.?)\s*\d|[₹$]\s*\d|\b\d[\d,]*\.\d{2}\b)", re.I)
MASK = re.compile(r"[xX*•●]{2,}|(?<![A-Za-z])[xX*•●](?![A-Za-z])")


def inspect_lines(extracted):
    """Describe positive pattern evidence; required name/address are not scored."""
    lines = [line for line in extracted.get("lines", []) if line.get("text", "").strip()]
    categories = {}
    reasons = []

    def add(code):
        tier, label = LABELS[code]
        categories[code] = {"id": code, "tier": tier, "label": label,
                            "evidence": "Readable pattern detected in document text"}

    def readable_tail(text, pattern, min_digits=1):
        match = re.search(pattern + r"\s*[:#=-]?\s*(.*)$", text, re.I)
        if not match:
            return False
        tail = match[1].strip()
        # A blank heading or explicitly masked value is not readable evidence.
        return bool(tail and not MASK.search(tail) and len(re.findall(r"\d", tail)) >= min_digits)

    for index, line in enumerate(lines):
        text = line["text"]
        if readable_tail(text, r"\b(?:(?:opening|closing|available|current|account|ledger)\s+)?balance\b"):
            add("balance")
        if readable_tail(text, r"\b(?:bank\s+)?account\s*(?:number|no\.?|#)\b", 8):
            add("bank_account")
        if readable_tail(text, r"\b(?:consumer|customer|service|meter)\s*(?:id|number|no\.?|code)\b", 4):
            add("utility_account")
        if readable_tail(text, r"\b(?:units\s+consumed|consumption|usage|meter\s+reading)\b"):
            add("usage")
        if readable_tail(text, r"\b(?:amount\s+due|total\s+due|bill\s+amount|total\s+payable|payment\s+due|due\s+date)\b"):
            add("billing")
        if re.search(r"\b(?:aadhaar|aadhar|uid)\b", text, re.I) and re.search(r"(?<!\d)\d{4}[ -]?\d{4}[ -]?\d{4}(?!\d)", text):
            add("aadhaar")
        if re.search(r"\bPAN\b", text) and re.search(r"\b[A-Z]{5}\d{4}[A-Z]\b", text, re.I):
            add("pan")
        if re.search(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", text, re.I):
            add("email")
        if not re.search(r"\b(?:account|consumer|customer|service|meter)\b", text, re.I) and re.search(r"(?<!\d)(?:\+91[ -]?)?[6-9]\d{9}(?!\d)", text):
            add("phone")
        header = len(set(re.findall(r"\b(?:date|debit|credit|narration|description|amount|transaction)\b", text.lower()))) >= 2
        if header and any(DATE.search(row["text"]) and MONEY.search(DATE.sub("", row["text"])) and not MASK.search(row["text"])
                          for row in lines[index + 1:index + 9]):
            add("transactions")
    if sum(len(line["text"].strip()) for line in lines) < 20:
        reasons.append("Too little readable text for a comparison.")
    if any(char.get("precise") is False for line in lines for char in line.get("chars", [])):
        reasons.append("OCR contains uncertain character locations; readable disclosures may have been missed.")
    letters = [char for line in lines for char in line["text"] if char.isalpha()]
    if letters and sum(char.isascii() for char in letters) / len(letters) < .8:
        reasons.append("This comparison supports English text; language coverage is uncertain.")
    if any("Unsupported PDF structures" in item or "OCR could not" in item for item in extracted.get("limitations", [])):
        reasons.append("The document has extraction or hidden-content limitations.")
    if extracted.get("qr") == "detected":
        reasons.append("Possible QR contents were not inspected. A reliable privacy ranking is unavailable.")
    return {"categories": sorted(categories.values(), key=lambda item: (item["tier"], item["id"])),
            "coverage": "inconclusive" if reasons else "supported_checks_completed", "limitations": reasons}


def summarize(session_id, report, hidden, acceptance, required_details_confirmed):
    analysis = report.get("_address_disclosure", {"categories": [], "coverage": "inconclusive",
                                                  "limitations": ["Inspect this document again to enable comparison."]})
    categories = list(analysis["categories"])
    for field in hidden["findings"]:
        categories.append({"id": "metadata:" + field["id"], "tier": 3, "label": field["label"],
                           "evidence": "Supported metadata property is present"})
    counts = [sum(category["tier"] == tier for category in categories) for tier in range(4)]
    compatible = report.get("compatibility", {}).get("size_ok") is True and report.get("compatibility", {}).get("format_ok") is True
    return {"session_id": session_id, "filename": report["filename"], "categories": categories,
            "tier_counts": counts, "coverage": analysis["coverage"], "limitations": analysis["limitations"],
            "acceptance": acceptance, "required_details_confirmed": required_details_confirmed,
            "confirmed_suitable": acceptance == "accepted" and required_details_confirmed and compatible,
            "technical_compatibility": compatible,
            "signature_indicator": report.get("authentication", {}).get("signature_indicator", False)}


def compare(candidates):
    result = {"policy_version": POLICY_VERSION, "purpose": "address_proof", "candidates": candidates,
              "tiers": TIERS, "recommended_session_id": None, "differences": [],
              "limitations": "Supported readable-text and metadata patterns only. No authenticity, complete-privacy or recipient-acceptance guarantee."}
    sets = [set(item["id"] for item in candidate["categories"]) for candidate in candidates]
    labels = {item["id"]: item["label"] for candidate in candidates for item in candidate["categories"]}
    result["differences"] = [{"session_id": candidate["session_id"],
                              "unique_categories": [labels[key] for key in sorted(sets[index] - sets[1 - index])]}
                             for index, candidate in enumerate(candidates)]
    eligible = [candidate for candidate in candidates if candidate["confirmed_suitable"]]
    if not eligible:
        return {**result, "status": "no_confirmed_option", "reason": "Confirm recipient acceptance and the required name/current address before a submission recommendation can be made."}
    checked = eligible if len(eligible) == 1 else candidates
    if any(candidate["coverage"] != "supported_checks_completed" for candidate in checked):
        return {**result, "status": "inconclusive", "reason": "Coverage is uncertain. Fewer detections are not proof that a document reveals less."}
    if len(eligible) == 1:
        return {**result, "status": "only_confirmed_option", "recommended_session_id": eligible[0]["session_id"],
                "reason": "Only this document is confirmed suitable by you. It is not a privacy winner over the other document."}
    left, right = candidates
    if left["tier_counts"] == right["tier_counts"]:
        return {**result, "status": "tie", "reason": "Both documents have equal category counts under this policy. Review the differences and choose; no winner is assigned."}
    winner, other = (left, right) if left["tier_counts"] < right["tier_counts"] else (right, left)
    tier = next(index for index in range(4) if winner["tier_counts"][index] != other["tier_counts"][index])
    return {**result, "status": "recommended", "recommended_session_id": winner["session_id"],
            "reason": f"Less unnecessary disclosure under supported checks: fewer detected categories in '{TIERS[tier]}'. Both documents were confirmed suitable by you."}
