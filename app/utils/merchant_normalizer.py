"""
Merchant normalizer + category mapper + description generator for Finsight.

Resolution order (first hit wins):
  1. Named-merchant regex table
  2. Masked-counterparty UPI rule
  3. UPI person-to-person (with handle)
  4. UPI person-to-person (truncated, no handle)
  5. NEFT / RTGS sender
  6. Cleaned fallback
"""
import re

MERCHANT_PATTERNS: list[tuple[str, str, str, str]] = [
    (r"swiggyinstamart",                      "Swiggy Instamart",   "Groceries",     "Quick grocery delivery via Swiggy Instamart"),
    (r"swiggy",                               "Swiggy",             "Food",          "Food delivery via Swiggy"),
    (r"zomato",                               "Zomato",             "Food",          "Food delivery via Zomato"),
    (r"dominos|domino",                       "Domino's",           "Food",          "Food order at Domino's"),
    (r"mcdonalds|mcdonald",                   "McDonald's",         "Food",          "Food order at McDonald's"),
    (r"starbucks",                            "Starbucks",          "Food",          "Coffee at Starbucks"),
    (r"kfc",                                "KFC",                "Food",          "Food order at KFC"),
    (r"pizzahut|pizza\s*hut",                 "Pizza Hut",          "Food",          "Food order at Pizza Hut"),
    (r"burgerking|burger\s*king",             "Burger King",        "Food",          "Food order at Burger King"),
    (r"haldirams|haldiram",                   "Haldiram's",         "Food",          "Food order at Haldiram's"),
    (r"cafe\s*coffee\s*day|ccd",            "Cafe Coffee Day",    "Food",          "Coffee at Cafe Coffee Day"),
    (r"chaayos",                              "Chaayos",            "Food",          "Tea/snacks at Chaayos"),
    (r"zepto",                                "Zepto",              "Groceries",     "Quick grocery delivery via Zepto"),
    (r"blinkit|grofers",                      "Blinkit",            "Groceries",     "Quick grocery delivery via Blinkit"),
    (r"bigbasket",                            "BigBasket",          "Groceries",     "Grocery order via BigBasket"),
    (r"dmart|d[-\s]?mart|avenue\s*super",     "DMart",              "Groceries",     "Grocery purchase at DMart"),
    (r"jiomart",                              "JioMart",            "Groceries",     "Grocery order via JioMart"),
    (r"reliance\s*fresh|reliancefresh",       "Reliance Fresh",     "Groceries",     "Grocery purchase at Reliance Fresh"),
    (r"spencers|spencer",                     "Spencer's",          "Groceries",     "Grocery purchase at Spencer's"),
    (r"amazon\s*pay|amzn\s*pay",              "Amazon Pay",         "Shopping",      "Payment via Amazon Pay wallet"),
    (r"amazon|amzn",                          "Amazon",             "Shopping",      "Purchase on Amazon"),
    (r"flipkart|fkrt",                        "Flipkart",           "Shopping",      "Purchase on Flipkart"),
    (r"myntra",                               "Myntra",             "Shopping",      "Fashion purchase on Myntra"),
    (r"ajio",                               "AJIO",               "Shopping",      "Fashion purchase on AJIO"),
    (r"nykaa",                                "Nykaa",              "Shopping",      "Beauty purchase on Nykaa"),
    (r"meesho",                               "Meesho",             "Shopping",      "Purchase on Meesho"),
    (r"croma",                              "Croma",              "Shopping",      "Electronics purchase at Croma"),
    (r"reliancedigital|reliance\s*digital",   "Reliance Digital",   "Shopping",      "Electronics purchase at Reliance Digital"),
    (r"jiodigital|jiorecharge|jio\s*recharge|jio\s*prepaid|jio\s*postpaid|reliance\s*jio",
                                              "Jio Recharge",       "Utilities",     "Jio mobile recharge or bill payment"),
    (r"airtelrecharge|airtel\s*recharge|bharti\s*airtel|airtel\s*prepaid|airtel\s*postpaid|airtel",
                                              "Airtel Recharge",    "Utilities",     "Airtel mobile recharge or bill payment"),
    (r"vi\s*recharge|vodafone|idea\s*recharge|vodafoneidea|vi.*recharge",
                                              "Vi Recharge",        "Utilities",     "Vi mobile recharge or bill payment"),
    (r"bsnl\s*recharge|bsnl",               "BSNL Recharge",      "Utilities",     "BSNL recharge or bill payment"),
    (r"act\s*fibernet|actfibernet",           "ACT Fibernet",       "Utilities",     "ACT Fibernet broadband bill"),
    (r"jiofiber|jio\s*fiber",                 "Jio Fiber",          "Utilities",     "Jio Fiber broadband bill"),
    (r"airtel\s*broadband|airtel\s*xstream",  "Airtel Broadband",   "Utilities",     "Airtel broadband bill"),
    (r"electricity|bijli|discom|avvnl|jdvvnl|jvvnl|jodhpur\s*vidyut|jaipur\s*vidyut",
                                              "Electricity Bill",   "Utilities",     "Electricity bill payment"),
    (r"rajasthan\s*rajya\s*vidyut",           "Rajasthan Electricity", "Utilities",  "Rajasthan electricity board bill payment"),
    (r"tata\s*power|tatapower",               "Tata Power",         "Utilities",     "Tata Power electricity bill"),
    (r"adani\s*electricity",                  "Adani Electricity",  "Utilities",     "Adani electricity bill payment"),
    (r"bses",                               "BSES",               "Utilities",     "BSES electricity bill payment"),
    (r"mahanagar\s*gas|mgl",                "Mahanagar Gas",      "Utilities",     "Mahanagar Gas bill payment"),
    (r"indraprastha\s*gas|igl",             "IGL Gas",            "Utilities",     "IGL gas bill payment"),
    (r"water\s*bill|jal\s*board|phed",      "Water Bill",         "Utilities",     "Water bill payment"),
    (r"indigoairline|indigo\s*air|indigo.*air", "IndiGo",       "Travel",        "IndiGo flight booking or payment"),
    (r"irctc",                            "IRCTC",              "Travel",        "Train ticket via IRCTC"),
    (r"uber\s*india|uber",                "Uber",               "Travel",        "Cab ride via Uber"),
    (r"olacabs|ola\s*cabs",           "Ola",                "Travel",        "Cab ride via Ola"),
    (r"makemytrip|mmt",                   "MakeMyTrip",         "Travel",        "Travel booking via MakeMyTrip"),
    (r"rapido",                             "Rapido",             "Travel",        "Bike/cab ride via Rapido"),
    (r"goibibo",                              "Goibibo",            "Travel",        "Travel booking via Goibibo"),
    (r"easemytrip",                           "EaseMyTrip",         "Travel",        "Travel booking via EaseMyTrip"),
    (r"redbus|red\s*bus",                     "RedBus",             "Travel",        "Bus ticket via RedBus"),
    (r"cleartrip",                            "Cleartrip",          "Travel",        "Travel booking via Cleartrip"),
    (r"yatra",                              "Yatra",              "Travel",        "Travel booking via Yatra"),
    (r"indianoil|iocl|indian\s*oil",        "Indian Oil",         "Fuel",          "Fuel purchase at Indian Oil"),
    (r"hp\s*petrol|hpcl|hindustan\s*petroleum", "HP Petrol",      "Fuel",          "Fuel purchase at HP petrol pump"),
    (r"bharat\s*petroleum|bpcl",            "Bharat Petroleum",   "Fuel",          "Fuel purchase at Bharat Petroleum"),
    (r"shell\s*petrol|shell.*fuel",         "Shell",              "Fuel",          "Fuel purchase at Shell"),
    (r"reliance\s*petrol|nayara",             "Nayara Energy",      "Fuel",          "Fuel purchase at Nayara Energy"),
    (r"netflix",                              "Netflix",            "Subscriptions", "Netflix subscription payment"),
    (r"hotstar|disney\s*\+\s*hotstar|jiohotstar|jio\s*hotstar",
                                              "Hotstar",            "Subscriptions", "Disney+ Hotstar subscription payment"),
    (r"spotify",                              "Spotify",            "Subscriptions", "Spotify subscription payment"),
    (r"amazon\s*prime|prime\s*video",         "Amazon Prime",       "Subscriptions", "Amazon Prime subscription payment"),
    (r"youtube\s*premium|youtube\s*music",    "YouTube Premium",    "Subscriptions", "YouTube Premium subscription payment"),
    (r"sonyliv|sony\s*liv",                   "SonyLIV",            "Subscriptions", "SonyLIV subscription payment"),
    (r"zee5",                               "ZEE5",               "Subscriptions", "ZEE5 subscription payment"),
    (r"quick\s*tv|paytm-?83855917",           "QuickTV",            "Subscriptions", "QuickTV subscription payment"),
    (r"apple\.com|itunes|icloud",             "Apple",              "Subscriptions", "Apple subscription payment"),
    (r"google\s*storage|google\s*one",        "Google One",         "Subscriptions", "Google One storage subscription"),
    (r"chatgpt|openai",                       "ChatGPT",            "Subscriptions", "ChatGPT/OpenAI subscription payment"),
    (r"bookmyshow|book\s*my\s*show",          "BookMyShow",         "Entertainment", "Movie/event ticket via BookMyShow"),
    (r"pvr|inox|pvrinox",                 "PVR INOX",           "Entertainment", "Movie ticket at PVR INOX"),
    (r"pharmeasy|pharm\s*easy",               "PharmEasy",          "Medical",       "Medicine order via PharmEasy"),
    (r"1mg|onemg|tata\s*1mg",               "Tata 1mg",           "Medical",       "Medicine order via Tata 1mg"),
    (r"netmeds",                              "Netmeds",            "Medical",       "Medicine order via Netmeds"),
    (r"apollo\s*pharmacy|apollopharmacy",      "Apollo Pharmacy",    "Medical",       "Medicine purchase at Apollo Pharmacy"),
    (r"practo",                             "Practo",             "Medical",       "Doctor consultation via Practo"),
    (r"hospital|clinic|diagnostic|patholog",   "Medical",            "Medical",       "Medical expense"),
    (r"lic\s*of\s*india|licindia|lic\s*premium", "LIC",             "Insurance",     "LIC insurance premium payment"),
    (r"star\s*health|starhealth",             "Star Health",        "Insurance",     "Star Health insurance premium"),
    (r"hdfc\s*ergo|hdfcergo",                 "HDFC Ergo",          "Insurance",     "HDFC Ergo insurance premium"),
    (r"icici\s*lombard|icicilombard",         "ICICI Lombard",      "Insurance",     "ICICI Lombard insurance premium"),
    (r"policy\s*bazaar|policybazaar",         "PolicyBazaar",       "Insurance",     "Insurance via PolicyBazaar"),
    (r"digit\s*insurance|godigit",            "Go Digit",           "Insurance",     "Go Digit insurance premium"),
    (r"acko",                               "Acko",               "Insurance",     "Acko insurance premium"),
    (r"udemy",                                "Udemy",              "Education",     "Online course on Udemy"),
    (r"coursera",                             "Coursera",           "Education",     "Online course on Coursera"),
    (r"unacademy",                            "Unacademy",          "Education",     "Unacademy subscription or course"),
    (r"byju|byjus",                           "Byju's",             "Education",     "Byju's subscription or course"),
    (r"school\s*fee|college\s*fee|tuition",   "Education Fee",      "Education",     "School/college fee payment"),
    (r"incometax|income\s*tax|e-?filing",     "Income Tax",         "Government",    "Income tax payment or e-filing fee"),
    (r"mcd|municipal|nagar\s*nigam",        "Municipal Tax",      "Government",    "Municipal tax or property tax payment"),
    (r"passport\s*seva|passport",             "Passport",           "Government",    "Passport fee payment"),
    (r"challan|traffic\s*fine|e-?challan",    "Traffic Challan",    "Government",    "Traffic challan or fine payment"),
    (r"rent|house\s*rent|flat\s*rent",    "Rent",               "Rent",          "House/flat rent payment"),
    (r"nobroker",                             "NoBroker",           "Rent",          "Rent payment via NoBroker"),
    (r"society\s*maintenance|maintenance\s*charge", "Society Maintenance", "Rent",   "Society maintenance charge"),
    (r"mbkwalletadd|one\s*mobikwik\s*systems.*mbkwallet", "MobiKwik Wallet", "Transfer", "Wallet top-up to MobiKwik via UPI"),
    (r"mbkprepaid",                           "MobiKwik Prepaid",   "Transfer",      "MobiKwik prepaid wallet top-up"),
    (r"onemobikwik",                      "MobiKwik Wallet",    "Transfer",      "Wallet top-up to MobiKwik via UPI"),
    (r"cred\.club|payment\s*on\s*cred|paidoncred",
                                              "CRED",               "Bill Payment",  "Credit card bill payment via CRED"),
    (r"bajaj\s*finance|bflautopay|bajajfinance", "Bajaj Finance",   "Loans/EMI",     "Bajaj Finance EMI or loan repayment"),
    (r"navi\s*limited|navilimited",           "Navi",               "Loans/EMI",     "Navi loan EMI payment"),
    (r"home\s*credit|homecredit",             "Home Credit",        "Loans/EMI",     "Home Credit EMI payment"),
    (r"muthoot\s*finance|muthootfinance|rtgs\s*cr.*muthoot", "Muthoot Finance", "Income", "Funds received from Muthoot Finance"),
    (r"icc?l\s*mutual\s*funds?|mfautopay|sip\s*registration", "Mutual Fund SIP", "Investments", "Mutual fund SIP auto-debit"),
    (r"zerodha|kite\s*broking",               "Zerodha",            "Investments",   "Zerodha trading/investment"),
    (r"groww",                              "Groww",              "Investments",   "Groww investment"),
    (r"paytm\s*money",                        "Paytm Money",        "Investments",   "Paytm Money investment"),
    (r"upstox",                               "Upstox",             "Investments",   "Upstox trading/investment"),
    (r"kuvera",                               "Kuvera",             "Investments",   "Kuvera mutual fund investment"),
    (r"ppf|public\s*provident",             "PPF",                "Investments",   "PPF contribution"),
    (r"nps|national\s*pension",             "NPS",                "Investments",   "NPS contribution"),
    (r"chitlangia.*infotech|chitlangiainfotech", "Chitlangia Infotech (Salary)", "Income", "Salary credit from Chitlangia Infotech"),
    (r"finalsalary|final\s*salary",           "Salary",             "Income",        "Monthly salary credit"),
    (r"salary",                           "Salary",             "Income",        "Salary credit"),
    (r"cash\s*deposit|cashdeposit",           "Cash Deposit",       "Transfer",      "Cash deposited to bank account"),
    (r"atm\s*withdrawal|atm\s*wdl|atm\s*wd",  "ATM Withdrawal",     "Cash Spend",    "ATM cash withdrawal"),
    (r"cash\s*withdrawal|cwdr",               "Cash Withdrawal",    "Cash Spend",    "Cash withdrawal from branch"),
    (r"debit\s*card\s*annual\s*fee|amc\s*fee","Bank Charge - Annual Fee", "Bank Charges", "Debit card annual maintenance charge"),
    (r"sms\s*charge|sms\s*alerts",            "SMS Charge",         "Bank Charges",  "SMS alert charges from bank"),
    (r"gst|igst|cgst",            "GST",                "Bank Charges",  "GST charge on banking service"),
    (r"insufficient\s*fund|isf\s*charge|bounce\s*charge", "Bounce Charge", "Bank Charges", "Cheque/mandate bounce charge"),
    (r"min\s*balance|minimum\s*balance",      "Min Balance Charge", "Bank Charges",  "Minimum balance non-maintenance charge"),
]

_RAIL_SUFFIXES = re.compile(
    r"(paid\s*via\s*mobikwik|paidviamobikwik|via\s*mobikwik)",
    re.IGNORECASE,
)

_UPI_MASKED_RX = re.compile(r"upi-x{4,}(\d{4})", re.IGNORECASE)
_UPI_PERSON_RX = re.compile(
    r"upi-([A-Za-z][A-Za-z\s\.]{2,40}?)-[^@\-]*@",
    re.IGNORECASE,
)
_UPI_PERSON_NO_HANDLE_RX = re.compile(
    r"^upi-([A-Za-z][A-Za-z\.]{2,40})\s*$",
    re.IGNORECASE,
)
_NEFT_RX = re.compile(
    r"(?:neft|rtgs)(?:cr|dr)?-[A-Za-z0-9]+-([A-Za-z][A-Za-z\s\&\.]{2,60}?)-",
    re.IGNORECASE,
)

_UPI_APP_MAP = {
    "ptyes": "Paytm", "paytm": "Paytm", "pthdfc": "Paytm", "ptsbi": "Paytm",
    "okaxis": "Google Pay", "oksbi": "Google Pay", "okicici": "Google Pay", "okhdfcbank": "Google Pay",
    "ybl": "PhonePe", "ibl": "PhonePe", "axl": "PhonePe",
    "mbkns": "MobiKwik", "mbk": "MobiKwik",
    "apl": "Amazon Pay", "rapl": "Amazon Pay",
    "icici": "ICICI", "hdfc": "HDFC", "sbi": "SBI", "axis": "Axis",
    "kotak": "Kotak",
}

_RAIL_SUFFIX_MAP = {
    "paidviacred": "CRED", "paidoncred": "CRED",
    "phonepe": "PhonePe",
    "googlepay": "Google Pay", "gpay": "Google Pay",
    "amazonpay": "Amazon Pay",
}


def _extract_upi_app(handle: str, raw: str) -> str:
    raw_lower = raw.lower()
    for suffix, app in _RAIL_SUFFIX_MAP.items():
        if suffix in raw_lower:
            return app
    if handle:
        h = handle.lower().strip()
        for key, app in _UPI_APP_MAP.items():
            if h.endswith(key) or h == key:
                return app
    return ""


def _build_description(raw_text: str) -> str:
    if not raw_text:
        return ""
    text = raw_text.strip()
    text_lower = text.lower()

    if re.search(r"atm\s*w", text_lower):
        return "ATM cash withdrawal"
    if re.search(r"cash\s*withdrawal|cwdr", text_lower):
        return "Cash withdrawal from branch"
    if re.search(r"cash\s*deposit", text_lower):
        return "Cash deposited to account"

    m = re.match(r"(neft|rtgs)(cr|dr)?[-\s]([A-Za-z0-9]+)[-\s](.+?)[-\s]\d", text, re.IGNORECASE)
    if m:
        rail = m.group(1).upper()
        direction = (m.group(2) or "").upper()
        name_part = re.sub(r"[^A-Za-z0-9 ]", " ", m.group(4)).strip().title()
        if direction == "CR":
            return f"{rail} credit from {name_part}"
        elif direction == "DR":
            return f"{rail} payment to {name_part}"
        else:
            return f"{rail} transfer - {name_part}"

    if text_lower.startswith("upi"):
        parts = re.split(r"-", text, maxsplit=5)
        name = ""
        handle = ""
        if len(parts) >= 2:
            name = re.sub(r"\s+", " ", parts[1]).strip().title()
        handle_match = re.search(r"[A-Za-z0-9.]+@([A-Za-z0-9]+)", text)
        if handle_match:
            handle = handle_match.group(1)
        app = _extract_upi_app(handle, text)
        if not name or len(name) < 2:
            return "UPI payment"
        via = f" via {app}" if app else ""
        return f"UPI payment to {name}{via}"

    cleaned = re.sub(r"\d{8,}", "", text)
    cleaned = re.sub(r"[A-Z]{4}\d{7}", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned.title()[:80] if cleaned else ""


def normalize_merchant(raw_text: str) -> tuple[str, str]:
    merchant, category, _ = normalize_merchant_full(raw_text)
    return merchant, category


def normalize_merchant_full(raw_text: str) -> tuple[str, str, str]:
    if not raw_text:
        return "Unknown", "Uncategorized", ""

    text = raw_text.strip()
    matchable = _RAIL_SUFFIXES.sub(" ", text)
    matchable = re.sub(r"\s+", " ", matchable).lower()

    for pattern, name, category, description in MERCHANT_PATTERNS:
        if re.search(pattern, matchable, re.IGNORECASE):
            return name, category, description

    m = _UPI_MASKED_RX.search(text)
    if m:
        last4 = m.group(1)
        desc = _build_description(text)
        return f"UPI to xx{last4}", "Transfer", desc or f"UPI payment to account ending {last4}"

    m = _UPI_PERSON_RX.search(text)
    if m:
        name = re.sub(r"\s+", " ", m.group(1)).strip().title()
        name = name[:60] or "P2P Transfer"
        desc = _build_description(text)
        return name, "P2P Transfer", desc or f"UPI payment to {name}"

    m = _UPI_PERSON_NO_HANDLE_RX.search(text)
    if m:
        name = re.sub(r"\s+", " ", m.group(1)).strip().title()
        name = name[:60] or "P2P Transfer"
        desc = _build_description(text)
        return name, "P2P Transfer", desc or f"UPI payment to {name}"

    m = _NEFT_RX.search(text)
    if m:
        sender = re.sub(r"\s+", " ", m.group(1)).strip().title()
        sender = sender[:60] or "Bank Transfer"
        desc = _build_description(text)
        return sender, "Transfer", desc or f"NEFT transfer from {sender}"

    cleaned = re.sub(r"upi[-/]?", "", text, flags=re.IGNORECASE)
    cleaned = re.sub(r"neftcr-?|rtgscr-?|neftdr-?|rtgsdr-?", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\d{6,}", "", cleaned)
    cleaned = re.sub(r"[^A-Za-z0-9 ]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    merchant = cleaned.title()[:60] or "Unknown"
    desc = _build_description(text)
    return merchant, "Uncategorized", desc
