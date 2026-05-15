"""
Merchant normalizer + category mapper for Finsight V1.

Resolution order (first hit wins):
  1. Named-merchant regex table.
  2. Masked-counterparty UPI rule (UPI-XXXXX####-).
  3. UPI handle pattern -> person name + "P2P Transfer".
  4. UPI no-handle truncated pattern -> person name + "P2P Transfer".
  5. NEFT / RTGS sender -> "Transfer".
  6. Cleaned-and-titlecased fallback -> "Uncategorized".
"""
import re

# (regex, canonical_merchant, category)
MERCHANT_PATTERNS: list[tuple[str, str, str]] = [
    # --- Food / quick-commerce ---
    (r"swiggyinstamart",                      "Swiggy Instamart",            "Groceries"),
    (r"swiggy",                               "Swiggy",                      "Food"),
    (r"zomato",                               "Zomato",                      "Food"),
    (r"zepto",                                "Zepto",                       "Groceries"),
    (r"blinkit|grofers",                      "Blinkit",                     "Groceries"),
    (r"bigbasket",                            "BigBasket",                   "Groceries"),
    (r"dmart|d[-\s]?mart|avenue\s*super",     "DMart",                       "Groceries"),
    # --- E-commerce ---
    (r"amazon\s*pay|amzn",                    "Amazon Pay",                  "Shopping"),
    (r"amazon",                               "Amazon",                      "Shopping"),
    (r"flipkart|fkrt",                        "Flipkart",                    "Shopping"),
    (r"myntra",                               "Myntra",                      "Shopping"),
    # --- Travel ---
    (r"indigoairline|indigo\s*air|\bindigo\b","IndiGo",                      "Travel"),
    (r"\birctc\b",                            "IRCTC",                       "Travel"),
    (r"uber\s*india|\buber\b",                "Uber",                        "Travel"),
    (r"\bolacabs\b|\bola\s*cabs\b",           "Ola",                         "Travel"),
    (r"makemytrip|\bmmt\b",                   "MakeMyTrip",                  "Travel"),
    # --- Entertainment / subscriptions ---
    (r"netflix",                              "Netflix",                     "Entertainment"),
    (r"hotstar|disney\s*\+\s*hotstar",        "Hotstar",                     "Entertainment"),
    (r"spotify",                              "Spotify",                     "Entertainment"),
    (r"quick\s*tv|paytm-?83855917",           "QuickTV",                     "Entertainment"),
    # --- Wallet add-money (specific first, then truncated fallback) ---
    (r"mbkwalletadd|one\s*mobikwik\s*systems.*mbkwallet", "MobiKwik Wallet", "Transfer"),
    (r"mbkprepaid",                           "MobiKwik Prepaid",            "Transfer"),
    (r"\bonemobikwik\b",                      "MobiKwik Wallet",             "Transfer"),
    # --- CRED bill payment (liability settlement, not a spend) ---
    (r"cred\.club|payment\s*on\s*cred|paidoncred|paidviacred|paid\s*via\s*cred", "CRED", "Bill Payment"),
    # --- NBFC / lending (debits) ---
    (r"bajaj\s*finance|bflautopay|bajajfinance", "Bajaj Finance",            "Loans/EMI"),
    (r"navi\s*limited|navilimited",           "Navi",                        "Loans/EMI"),
    # --- Loan disbursement (credits) ---
    (r"muthoot\s*finance|muthootfinance|rtgs\s*cr.*muthoot", "Muthoot Finance", "Income"),
    # --- Investments ---
    (r"icc?l\s*mutual\s*funds?|mfautopay|sip\s*registration", "Mutual Fund SIP", "Investments"),
    (r"zerodha|kite\s*broking",               "Zerodha",                     "Investments"),
    (r"groww",                                "Groww",                       "Investments"),
    # --- Salary ---
    (r"chitlangia.*infotech|chitlangiainfotech", "Chitlangia Infotech (Salary)", "Income"),
    (r"finalsalary|final\s*salary",           "Salary",                      "Income"),
    # --- Cash / branch ops ---
    (r"cash\s*deposit|cashdeposit",           "Cash Deposit",                "Transfer"),
    # --- Bank charges ---
    (r"debit\s*card\s*annual\s*fee|amc\s*fee","Bank Charge - Annual Fee",    "Bank Charges"),
    (r"sms\s*charge|sms\s*alerts",            "SMS Charge",                  "Bank Charges"),
    (r"\bgst\b|\bigst\b|\bcgst\b",            "GST",                         "Bank Charges"),
]

# "paid via mobikwik" is a payment rail, not the merchant. Strip before matching.
_RAIL_SUFFIXES = re.compile(
    r"\b(paid\s*via\s*mobikwik|paidviamobikwik|via\s*mobikwik)\b",
    re.IGNORECASE,
)

# UPI-XXXXXXX8666-SBIN0001602-... -> masked counterparty, last 4 digits preserved.
_UPI_MASKED_RX = re.compile(
    r"upi-x{4,}(\d{4})\b",
    re.IGNORECASE,
)

# Standard UPI: UPI-FIRSTNAME LASTNAME-HANDLE@BANK-...
_UPI_PERSON_RX = re.compile(
    r"upi-([A-Za-z][A-Za-z\s\.]{2,40}?)-[^@\-]*@",
    re.IGNORECASE,
)

# Truncated UPI: just UPI-NAME at end of narration, no handle following.
_UPI_PERSON_NO_HANDLE_RX = re.compile(
    r"^upi-([A-Za-z][A-Za-z\.]{2,40})\s*$",
    re.IGNORECASE,
)

# NEFT/RTGS narration sender capture.
_NEFT_RX = re.compile(
    r"(?:neft|rtgs)(?:cr|dr)?-[A-Za-z0-9]+-([A-Za-z][A-Za-z\s\&\.]{2,60}?)-",
    re.IGNORECASE,
)


def normalize_merchant(raw_text: str) -> tuple[str, str]:
    """Return (merchant_normalized, category) from a raw narration."""
    if not raw_text:
        return "Unknown", "Uncategorized"

    text = raw_text.strip()
    matchable = _RAIL_SUFFIXES.sub(" ", text)
    matchable = re.sub(r"\s+", " ", matchable).lower()

    # 1. Named-merchant table
    for pattern, name, category in MERCHANT_PATTERNS:
        if re.search(pattern, matchable, re.IGNORECASE):
            return name, category

    # 2. Masked counterparty (privacy-masked UPI receiver)
    m = _UPI_MASKED_RX.search(text)
    if m:
        return f"UPI to xx{m.group(1)}", "Transfer"

    # 3. UPI person-to-person (with handle)
    m = _UPI_PERSON_RX.search(text)
    if m:
        name = re.sub(r"\s+", " ", m.group(1)).strip().title()
        return (name[:60] or "P2P Transfer"), "P2P Transfer"

    # 4. UPI person-to-person (truncated, no handle)
    m = _UPI_PERSON_NO_HANDLE_RX.search(text)
    if m:
        name = re.sub(r"\s+", " ", m.group(1)).strip().title()
        return (name[:60] or "P2P Transfer"), "P2P Transfer"

    # 5. NEFT / RTGS sender
    m = _NEFT_RX.search(text)
    if m:
        sender = re.sub(r"\s+", " ", m.group(1)).strip().title()
        return (sender[:60] or "Bank Transfer"), "Transfer"

    # 6. Fallback: strip noise, title-case
    cleaned = re.sub(r"upi[-/]?", "", text, flags=re.IGNORECASE)
    cleaned = re.sub(r"neftcr-?|rtgscr-?|neftdr-?|rtgsdr-?", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\d{6,}", "", cleaned)
    cleaned = re.sub(r"[^A-Za-z0-9 ]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return (cleaned.title()[:60] or "Unknown"), "Uncategorized"
