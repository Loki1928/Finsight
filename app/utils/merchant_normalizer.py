"""
Merchant normalizer + category mapper for Finsight.

Session 19 rewrite — ~100 patterns covering common Indian merchants,
utilities, recharges, insurance, medical, government, subscriptions.

Resolution order (first hit wins):
  1. Named-merchant regex table.
  2. Masked-counterparty UPI rule (UPI-XXXXX####-).
  3. UPI handle pattern -> person name + "P2P Transfer".
  4. UPI person-to-person (truncated, no handle).
  5. NEFT / RTGS sender -> "Transfer".
  6. Cleaned-and-titlecased fallback -> "Uncategorized".
"""
import re

# (regex, canonical_merchant, category)
MERCHANT_PATTERNS: list[tuple[str, str, str]] = [
    # ── Food / delivery ──────────────────────────────────────────────
    (r"swiggyinstamart",                      "Swiggy Instamart",            "Groceries"),
    (r"swiggy",                               "Swiggy",                      "Food"),
    (r"zomato",                               "Zomato",                      "Food"),
    (r"dominos|domino",                       "Domino's",                    "Food"),
    (r"mcdonalds|mcdonald",                   "McDonald's",                  "Food"),
    (r"starbucks",                            "Starbucks",                   "Food"),
    (r"kfc\b",                                "KFC",                         "Food"),
    (r"pizzahut|pizza\s*hut",                 "Pizza Hut",                   "Food"),
    (r"burgerking|burger\s*king",             "Burger King",                 "Food"),
    (r"haldirams|haldiram",                   "Haldiram's",                  "Food"),
    (r"cafe\s*coffee\s*day|ccd\b",            "Cafe Coffee Day",             "Food"),
    (r"chaayos",                              "Chaayos",                     "Food"),

    # ── Groceries / quick-commerce ───────────────────────────────────
    (r"zepto",                                "Zepto",                       "Groceries"),
    (r"blinkit|grofers",                      "Blinkit",                     "Groceries"),
    (r"bigbasket",                            "BigBasket",                   "Groceries"),
    (r"dmart|d[-\s]?mart|avenue\s*super",     "DMart",                       "Groceries"),
    (r"jiomart",                              "JioMart",                     "Groceries"),
    (r"reliance\s*fresh|reliancefresh",       "Reliance Fresh",              "Groceries"),
    (r"more\s*supermarket|morestore",         "More Supermarket",            "Groceries"),
    (r"spencers|spencer",                     "Spencer's",                   "Groceries"),

    # ── E-commerce / shopping ────────────────────────────────────────
    (r"amazon\s*pay|amzn\s*pay",              "Amazon Pay",                  "Shopping"),
    (r"amazon|amzn",                          "Amazon",                      "Shopping"),
    (r"flipkart|fkrt",                        "Flipkart",                    "Shopping"),
    (r"myntra",                               "Myntra",                      "Shopping"),
    (r"ajio\b",                               "AJIO",                        "Shopping"),
    (r"nykaa",                                "Nykaa",                       "Shopping"),
    (r"meesho",                               "Meesho",                      "Shopping"),
    (r"croma\b",                              "Croma",                       "Shopping"),
    (r"reliancedigital|reliance\s*digital",   "Reliance Digital",            "Shopping"),

    # ── Mobile recharge / telecom ────────────────────────────────────
    (r"jiodigital|jiorecharge|jio\s*recharge|jio\s*prepaid|jio\s*postpaid|reliance\s*jio",
                                              "Jio Recharge",                "Utilities"),
    (r"airtelrecharge|airtel\s*recharge|bharti\s*airtel|airtel\s*prepaid|airtel\s*postpaid|\bairtel\b",
                                              "Airtel Recharge",             "Utilities"),
    (r"vi\s*recharge|vodafone|idea\s*recharge|vodafoneidea|\bvi\b.*recharge",
                                              "Vi Recharge",                 "Utilities"),
    (r"bsnl\s*recharge|bsnl\b",               "BSNL Recharge",               "Utilities"),
    (r"act\s*fibernet|actfibernet",           "ACT Fibernet",                "Utilities"),
    (r"jiofiber|jio\s*fiber",                 "Jio Fiber",                   "Utilities"),
    (r"airtel\s*broadband|airtel\s*xstream",  "Airtel Broadband",            "Utilities"),

    # ── Electricity / water / gas ────────────────────────────────────
    (r"electricity|bijli|discom|avvnl|jdvvnl|jvvnl|jodhpur\s*vidyut|jaipur\s*vidyut",
                                              "Electricity Bill",            "Utilities"),
    (r"rajasthan\s*rajya\s*vidyut",           "Rajasthan Electricity",       "Utilities"),
    (r"tata\s*power|tatapower",               "Tata Power",                  "Utilities"),
    (r"adani\s*electricity",                  "Adani Electricity",           "Utilities"),
    (r"bses\b",                               "BSES",                        "Utilities"),
    (r"mahanagar\s*gas|mgl\b",                "Mahanagar Gas",               "Utilities"),
    (r"indraprastha\s*gas|igl\b",             "IGL Gas",                     "Utilities"),
    (r"water\s*bill|jal\s*board|phed\b",      "Water Bill",                  "Utilities"),

    # ── Travel ───────────────────────────────────────────────────────
    (r"indigoairline|indigo\s*air|\bindigo\b.*air", "IndiGo",                "Travel"),
    (r"\birctc\b",                            "IRCTC",                       "Travel"),
    (r"uber\s*india|\buber\b",                "Uber",                        "Travel"),
    (r"\bolacabs\b|\bola\s*cabs\b",           "Ola",                         "Travel"),
    (r"makemytrip|\bmmt\b",                   "MakeMyTrip",                  "Travel"),
    (r"rapido\b",                             "Rapido",                      "Travel"),
    (r"goibibo",                              "Goibibo",                     "Travel"),
    (r"easemytrip",                           "EaseMyTrip",                  "Travel"),
    (r"redbus|red\s*bus",                     "RedBus",                      "Travel"),
    (r"cleartrip",                            "Cleartrip",                   "Travel"),
    (r"yatra\b",                              "Yatra",                       "Travel"),

    # ── Fuel ─────────────────────────────────────────────────────────
    (r"indianoil|iocl\b|indian\s*oil",        "Indian Oil",                  "Fuel"),
    (r"hp\s*petrol|hpcl\b|hindustan\s*petroleum", "HP Petrol",               "Fuel"),
    (r"bharat\s*petroleum|bpcl\b",            "Bharat Petroleum",            "Fuel"),
    (r"shell\s*petrol|shell\b.*fuel",         "Shell",                       "Fuel"),
    (r"reliance\s*petrol|nayara",             "Nayara Energy",               "Fuel"),

    # ── Subscriptions ────────────────────────────────────────────────
    (r"netflix",                              "Netflix",                     "Subscriptions"),
    (r"hotstar|disney\s*\+\s*hotstar|jiohotstar|jio\s*hotstar",
                                              "Hotstar",                     "Subscriptions"),
    (r"spotify",                              "Spotify",                     "Subscriptions"),
    (r"amazon\s*prime|prime\s*video",         "Amazon Prime",                "Subscriptions"),
    (r"youtube\s*premium|youtube\s*music",    "YouTube Premium",             "Subscriptions"),
    (r"sonyliv|sony\s*liv",                   "SonyLIV",                     "Subscriptions"),
    (r"zee5\b",                               "ZEE5",                        "Subscriptions"),
    (r"quick\s*tv|paytm-?83855917",           "QuickTV",                     "Subscriptions"),
    (r"apple\.com|itunes|icloud",             "Apple",                       "Subscriptions"),
    (r"google\s*storage|google\s*one",        "Google One",                  "Subscriptions"),
    (r"chatgpt|openai",                       "ChatGPT",                     "Subscriptions"),

    # ── Entertainment (one-time) ─────────────────────────────────────
    (r"bookmyshow|book\s*my\s*show",          "BookMyShow",                  "Entertainment"),
    (r"pvr\b|inox\b|pvrinox",                 "PVR INOX",                    "Entertainment"),

    # ── Medical / pharmacy ───────────────────────────────────────────
    (r"pharmeasy|pharm\s*easy",               "PharmEasy",                   "Medical"),
    (r"1mg\b|onemg|tata\s*1mg",               "Tata 1mg",                    "Medical"),
    (r"netmeds",                              "Netmeds",                     "Medical"),
    (r"apollo\s*pharmacy|apollopharmacy",      "Apollo Pharmacy",             "Medical"),
    (r"practo\b",                             "Practo",                      "Medical"),
    (r"hospital|clinic|diagnostic|patholog",   "Medical",                     "Medical"),

    # ── Insurance ────────────────────────────────────────────────────
    (r"lic\s*of\s*india|licindia|lic\s*premium", "LIC",                      "Insurance"),
    (r"star\s*health|starhealth",             "Star Health",                 "Insurance"),
    (r"hdfc\s*ergo|hdfcergo",                 "HDFC Ergo",                   "Insurance"),
    (r"icici\s*lombard|icicilombard",         "ICICI Lombard",               "Insurance"),
    (r"policy\s*bazaar|policybazaar",         "PolicyBazaar",                "Insurance"),
    (r"digit\s*insurance|godigit",            "Go Digit",                    "Insurance"),
    (r"acko\b",                               "Acko",                        "Insurance"),

    # ── Education ────────────────────────────────────────────────────
    (r"udemy",                                "Udemy",                       "Education"),
    (r"coursera",                             "Coursera",                    "Education"),
    (r"unacademy",                            "Unacademy",                   "Education"),
    (r"byju|byjus",                           "Byju's",                     "Education"),
    (r"school\s*fee|college\s*fee|tuition",   "Education Fee",               "Education"),

    # ── Government / tax ─────────────────────────────────────────────
    (r"incometax|income\s*tax|e-?filing",     "Income Tax",                  "Government"),
    (r"mcd\b|municipal|nagar\s*nigam",        "Municipal Tax",               "Government"),
    (r"passport\s*seva|passport",             "Passport",                    "Government"),
    (r"challan|traffic\s*fine|e-?challan",    "Traffic Challan",             "Government"),

    # ── Rent ─────────────────────────────────────────────────────────
    (r"\brent\b|house\s*rent|flat\s*rent",    "Rent",                        "Rent"),
    (r"nobroker",                             "NoBroker",                    "Rent"),
    (r"society\s*maintenance|maintenance\s*charge", "Society Maintenance",   "Rent"),

    # ── Wallet add-money ─────────────────────────────────────────────
    (r"mbkwalletadd|one\s*mobikwik\s*systems.*mbkwallet", "MobiKwik Wallet", "Transfer"),
    (r"mbkprepaid",                           "MobiKwik Prepaid",            "Transfer"),
    (r"\bonemobikwik\b",                      "MobiKwik Wallet",             "Transfer"),

    # ── CRED bill payment ────────────────────────────────────────────
    (r"cred\.club|payment\s*on\s*cred|paidoncred|paidviacred|paid\s*via\s*cred",
                                              "CRED",                        "Bill Payment"),

    # ── NBFC / lending ───────────────────────────────────────────────
    (r"bajaj\s*finance|bflautopay|bajajfinance", "Bajaj Finance",            "Loans/EMI"),
    (r"navi\s*limited|navilimited",           "Navi",                        "Loans/EMI"),
    (r"home\s*credit|homecredit",             "Home Credit",                 "Loans/EMI"),
    (r"muthoot\s*finance|muthootfinance|rtgs\s*cr.*muthoot", "Muthoot Finance", "Income"),

    # ── Investments ──────────────────────────────────────────────────
    (r"icc?l\s*mutual\s*funds?|mfautopay|sip\s*registration", "Mutual Fund SIP", "Investments"),
    (r"zerodha|kite\s*broking",               "Zerodha",                     "Investments"),
    (r"groww\b",                              "Groww",                       "Investments"),
    (r"coin\s*by\s*zerodha|coin\b.*zerodha",  "Zerodha Coin",                "Investments"),
    (r"paytm\s*money",                        "Paytm Money",                 "Investments"),
    (r"upstox",                               "Upstox",                      "Investments"),
    (r"kuvera",                               "Kuvera",                      "Investments"),
    (r"ppf\b|public\s*provident",             "PPF",                         "Investments"),
    (r"nps\b|national\s*pension",             "NPS",                         "Investments"),

    # ── Salary / income patterns ─────────────────────────────────────
    (r"chitlangia.*infotech|chitlangiainfotech", "Chitlangia Infotech (Salary)", "Income"),
    (r"finalsalary|final\s*salary",           "Salary",                      "Income"),
    (r"\bsalary\b",                           "Salary",                      "Income"),

    # ── Cash / branch ops ────────────────────────────────────────────
    (r"cash\s*deposit|cashdeposit",           "Cash Deposit",                "Transfer"),
    (r"atm\s*withdrawal|atm\s*wdl|atm\s*wd",  "ATM Withdrawal",             "Cash Spend"),
    (r"cash\s*withdrawal|cwdr",               "Cash Withdrawal",             "Cash Spend"),

    # ── Bank charges ─────────────────────────────────────────────────
    (r"debit\s*card\s*annual\s*fee|amc\s*fee","Bank Charge - Annual Fee",    "Bank Charges"),
    (r"sms\s*charge|sms\s*alerts",            "SMS Charge",                  "Bank Charges"),
    (r"\bgst\b|\bigst\b|\bcgst\b",            "GST",                         "Bank Charges"),
    (r"insufficient\s*fund|isf\s*charge|bounce\s*charge", "Bounce Charge",   "Bank Charges"),
    (r"min\s*balance|minimum\s*balance",      "Min Balance Charge",          "Bank Charges"),
]

# "paid via mobikwik" is a payment rail, not the merchant. Strip before matching.
_RAIL_SUFFIXES = re.compile(
    r"\b(paid\s*via\s*mobikwik|paidviamobikwik|via\s*mobikwik)\b",
    re.IGNORECASE,
)

# UPI-XXXXXXX8666-SBIN0001602-... -> masked counterparty
_UPI_MASKED_RX = re.compile(r"upi-x{4,}(\d{4})\b", re.IGNORECASE)

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
