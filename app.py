import streamlit as st
from pypdf import PdfReader
from io import BytesIO
import pytesseract
from pdf2image import convert_from_bytes
import pandas as pd
import re


# =========================================================
# CONFIG
# =========================================================

st.set_page_config(
    page_title="CustomsDoc Check",
    page_icon="📋",
    layout="wide"
)

st.title("📋 CustomsDoc Check")
st.subheader("Kiểm soát chứng từ phục vụ khai báo hải quan")

st.write(
    "Tự động đọc PDF, OCR tài liệu scan, nhận diện nhiều mẫu "
    "Invoice / Packing List / B/L / C/O / Booking, trích xuất "
    "dữ liệu và kiểm tra chéo."
)

st.divider()

EMPTY = "Không tìm thấy"


# =========================================================
# BASIC HELPERS
# =========================================================

def clean_value(value):
    if value is None:
        return None
    value = str(value).replace("\xa0", " ")
    value = re.sub(r"\s+", " ", value).strip(" :-|")
    return value or None


def normalize_text(text):
    if not text:
        return ""
    text = text.replace("\xa0", " ")
    text = text.replace("–", "-").replace("—", "-").replace("−", "-")
    text = text.replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text.strip()


def get_lines(text):
    return [clean_value(x) for x in text.splitlines() if clean_value(x)]


def normalize_number(value):
    if not value:
        return None
    s = str(value).upper().strip()
    s = re.sub(r"[^\d.,]", "", s)
    if not s:
        return None

    # 1,234.56 / 1234.56
    if "," in s and "." in s:
        if s.rfind(".") > s.rfind(","):
            s = s.replace(",", "")
        else:
            s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        parts = s.split(",")
        if len(parts[-1]) in (1, 2):
            s = s.replace(",", ".")
        else:
            s = s.replace(",", "")

    return s


def normalize_compare(value):
    if not value:
        return ""
    value = str(value).upper()
    value = value.replace("&", "AND")
    value = re.sub(r"[^A-Z0-9]", "", value)
    return value


def values_match(a, b):
    a = normalize_compare(a)
    b = normalize_compare(b)
    if not a or not b:
        return False
    return a == b or a in b or b in a


# =========================================================
# PDF + OCR
# =========================================================

def read_pdf_text(file_bytes):
    try:
        reader = PdfReader(BytesIO(file_bytes))
        pages = []

        for page in reader.pages:
            try:
                pages.append(page.extract_text() or "")
            except Exception:
                pages.append("")

        return pages, len(reader.pages), None

    except Exception as e:
        return [], 0, str(e)


def ocr_pdf(file_bytes):
    try:
        images = convert_from_bytes(
            file_bytes,
            dpi=250,
            fmt="png"
        )
    except Exception as e:
        return [], 0, str(e)

    pages = []

    for image in images:
        try:
            text = pytesseract.image_to_string(
                image,
                lang="eng+vie",
                config="--psm 6"
            )
        except Exception:
            try:
                text = pytesseract.image_to_string(
                    image,
                    lang="eng",
                    config="--psm 6"
                )
            except Exception:
                text = ""

        pages.append(text or "")

    return pages, len(images), None


def process_pdf(file_bytes):
    pdf_pages, page_count, pdf_error = read_pdf_text(file_bytes)

    if not pdf_pages:
        return [], 0, "Không đọc được PDF", pdf_error

    final_pages = list(pdf_pages)
    need_ocr = []

    # OCR các trang scan hoặc text quá ít
    for i, page in enumerate(final_pages):
        if len((page or "").strip()) < 30:
            need_ocr.append(i)

    if need_ocr:
        ocr_pages, _, ocr_error = ocr_pdf(file_bytes)

        for i in need_ocr:
            if i < len(ocr_pages) and len(ocr_pages[i].strip()) > 0:
                final_pages[i] = ocr_pages[i]

        method = "PDF Text + OCR"
        error = ocr_error
    else:
        method = "PDF Text"
        error = None

    final_pages = [p or "" for p in final_pages]

    if not "\n".join(final_pages).strip():
        return final_pages, page_count, method, error or "Không có nội dung đọc được"

    return final_pages, page_count, method, error


# =========================================================
# GENERIC PATTERN HELPERS
# =========================================================

def find_pattern(text, patterns):
    for pattern in patterns:
        try:
            m = re.search(pattern, text, re.I | re.M)
            if m:
                value = clean_value(m.group(1))
                if value:
                    return value
        except Exception:
            pass
    return None


def find_all_patterns(text, patterns):
    results = []
    for pattern in patterns:
        try:
            matches = re.findall(pattern, text, re.I | re.M)
            for m in matches:
                value = m[0] if isinstance(m, tuple) else m
                value = clean_value(value)
                if value and value not in results:
                    results.append(value)
        except Exception:
            pass
    return results


def extract_labeled_block(text, labels, stop_labels, max_lines=5):
    lines = get_lines(text)

    labels_regex = "|".join(
        re.escape(x) for x in labels
    )
    stops_regex = "|".join(
        re.escape(x) for x in stop_labels
    )

    label_re = re.compile(
        rf"^\s*(?:{labels_regex})\s*(?:[:#\-]\s*)?(.*)$",
        re.I
    )

    stop_re = re.compile(
        rf"^\s*(?:{stops_regex})\s*(?:[:#\-]|\s|$)",
        re.I
    )

    for i, line in enumerate(lines):
        m = label_re.match(line)
        if not m:
            continue

        values = []

        first = clean_value(m.group(1))
        if first:
            values.append(first)

        for j in range(i + 1, min(i + 1 + max_lines, len(lines))):
            nxt = lines[j]

            if stop_re.match(nxt):
                break

            # Không nuốt các dòng điều khoản B/L
            if re.search(
                r"COMBINED TRANSPORT|THIS B/L IS|CLAUSES?|"
                r"CARRIER'S AGENTS|ENDORSEMENTS|"
                r"FREIGHT PREPAID|FREIGHT COLLECT",
                nxt,
                re.I
            ):
                break

            values.append(nxt)

        if values:
            return clean_value(" ".join(values))

    return None


# =========================================================
# CONTAINER / WEIGHT / CURRENCY / INCOTERM
# =========================================================

def extract_containers(text):
    matches = re.findall(
        r"\b[A-Z]{4}\s*\d{7}\b",
        text.upper()
    )

    result = []
    for x in matches:
        x = re.sub(r"\s+", "", x)
        if x not in result:
            result.append(x)

    return ", ".join(result) if result else None


def container_set(value):
    if not value:
        return set()
    return set(
        re.findall(r"[A-Z]{4}\d{7}", value.upper())
    )


def extract_weight(text, weight_type):
    if weight_type == "gross":
        labels = [
            r"GROSS\s+WEIGHT",
            r"GROSS\s+WT",
            r"GROSS\s*W/T",
            r"G\.?\s*W\.?",
            r"G/W"
        ]
    else:
        labels = [
            r"NET\s+WEIGHT",
            r"NET\s+WT",
            r"NET\s*W/T",
            r"N\.?\s*W\.?",
            r"N/W"
        ]

    label_re = "|".join(labels)

    # label + value cùng dòng
    patterns = [
        rf"(?:{label_re})\s*[:#\-]?\s*"
        r"([\d,]+(?:\.\d+)?)\s*(?:KG|KGS|KILOGRAMS)?",

        # value trước label
        rf"([\d,]+(?:\.\d+)?)\s*(?:KG|KGS)\s+"
        rf"(?:{label_re})"
    ]

    return find_pattern(text, patterns)


def extract_currency(text):
    patterns = [
        (r"\bUSD\b|US\s+DOLLARS?", "USD"),
        (r"\bEUR\b|EUROS?", "EUR"),
        (r"\bKRW\b|KOREAN\s+WON", "KRW"),
        (r"\bJPY\b|JAPANESE\s+YEN", "JPY"),
        (r"\bVND\b|VIETNAM\s+DONG", "VND"),
        (r"\bGBP\b|POUNDS?", "GBP"),
        (r"\bCNY\b|\bRMB\b|YUAN", "CNY")
    ]

    for pattern, code in patterns:
        if re.search(pattern, text, re.I):
            return code
    return None


def extract_incoterm(text):
    m = re.search(
        r"\b(EXW|FCA|FAS|FOB|CFR|CIF|CPT|CIP|DAP|DPU|DDP)\b",
        text.upper()
    )
    return m.group(1) if m else None


# =========================================================
# DOCUMENT DETECTION
# =========================================================

def detect_document_type(text):
    t = text.upper()

    scores = {
        "COMMERCIAL INVOICE": 0,
        "BILL OF LADING": 0,
        "PACKING LIST": 0,
        "CERTIFICATE OF ORIGIN": 0,
        "BOOKING": 0
    }

    keyword_groups = {
        "COMMERCIAL INVOICE": [
            "COMMERCIAL INVOICE", "PROFORMA INVOICE", "INVOICE NO",
            "INVOICE NUMBER", "UNIT PRICE", "TOTAL AMOUNT",
            "INVOICE VALUE", "PAYMENT TERMS", "DELIVERY TERMS"
        ],
        "BILL OF LADING": [
            "BILL OF LADING", "B/L NO", "B/L NUMBER", "SHIPPER",
            "CONSIGNEE", "NOTIFY PARTY", "PORT OF LOADING",
            "PORT OF DISCHARGE", "PLACE OF DELIVERY", "VESSEL",
            "VOYAGE"
        ],
        "PACKING LIST": [
            "PACKING LIST", "PACKING LIST NO", "NET WEIGHT",
            "GROSS WEIGHT", "NO. OF PACKAGES", "TOTAL PACKAGES",
            "CARTONS", "CTNS", "PKGS"
        ],
        "CERTIFICATE OF ORIGIN": [
            "CERTIFICATE OF ORIGIN", "ORIGIN CRITERION",
            "ORIGIN CRITERIA", "COUNTRY OF ORIGIN", "EXPORTER",
            "HS CODE"
        ],
        "BOOKING": [
            "BOOKING CONFIRMATION", "BOOKING CONFIRM",
            "BOOKING NO", "BOOKING NUMBER", "BOOKING REFERENCE",
            "VESSEL", "VOYAGE", "ETD", "ETA", "CUT-OFF",
            "SI CUT-OFF", "CY CUT-OFF", "PORT OF LOADING",
            "PORT OF DISCHARGE"
        ]
    }

    for dtype, keywords in keyword_groups.items():
        for k in keywords:
            if k in t:
                scores[dtype] += 2

    strong = {
        "COMMERCIAL INVOICE": "COMMERCIAL INVOICE",
        "BILL OF LADING": "BILL OF LADING",
        "PACKING LIST": "PACKING LIST",
        "CERTIFICATE OF ORIGIN": "CERTIFICATE OF ORIGIN",
        "BOOKING": "BOOKING CONFIRMATION"
    }

    for dtype, phrase in strong.items():
        if phrase in t:
            scores[dtype] += 10

    best = max(scores, key=scores.get)

    if scores[best] == 0:
        return "KHÔNG XÁC ĐỊNH", scores

    return best, scores


# =========================================================
# B/L
# =========================================================

def valid_bl_number(value):
    if not value or len(value) > 35:
        return False
    if len(value.split()) > 2:
        return False
    return bool(
        re.fullmatch(
            r"[A-Z0-9./_-]{5,35}",
            value.strip(),
            re.I
        )
    ) and bool(re.search(r"[A-Z]", value, re.I)) \
      and bool(re.search(r"\d", value))


def extract_bl_number(text):
    patterns = [
        r"(?:BILL\s+OF\s+LADING)\s*(?:NO\.?|NUMBER|#)\s*[:#\-]?\s*([A-Z0-9][A-Z0-9./_-]{4,34})",
        r"\bB/L\s*(?:NO\.?|NUMBER|#)\s*[:#\-]?\s*([A-Z0-9][A-Z0-9./_-]{4,34})",
        r"\bBL\s*(?:NO\.?|NUMBER|#)\s*[:#\-]?\s*([A-Z0-9][A-Z0-9./_-]{4,34})",
        r"\bBIL\s*(?:NO\.?|NUMBER|#)\s*[:#\-]?\s*([A-Z0-9][A-Z0-9./_-]{4,34})",
        r"\b(?:B/L|BL|BIL)\s*[:#]\s*([A-Z0-9][A-Z0-9./_-]{4,34})"
    ]

    for p in patterns:
        m = re.search(p, text, re.I)
        if m and valid_bl_number(m.group(1)):
            return m.group(1).upper()

    # Label và value ở dòng kế tiếp
    lines = get_lines(text)
    for i, line in enumerate(lines):
        if re.search(r"\b(?:B/L|BL|BIL)\b.*(?:NO|NUMBER|#)", line, re.I):
            for candidate in lines[i + 1:i + 4]:
                if valid_bl_number(candidate):
                    return candidate.upper()

    return None


def valid_port(value):
    if not value or len(value) > 100:
        return False

    bad = [
        "COMBINED TRANSPORT", "THIS B/L", "CLAUSES",
        "UNLESS MARKED", "ENDORSEMENTS", "CARRIER'S AGENTS"
    ]

    return not any(x in value.upper() for x in bad)


def extract_port(text, field):
    if field == "loading":
        labels = ["PORT OF LOADING", "PORT OF SHIPMENT", "POL"]
    elif field == "discharge":
        labels = ["PORT OF DISCHARGE", "POD"]
    else:
        labels = [
            "PLACE OF DELIVERY",
            "FINAL DESTINATION",
            "PLACE OF DELIVERY/DESTINATION"
        ]

    stops = [
        "SHIPPER", "CONSIGNEE", "NOTIFY PARTY", "NOTIFY",
        "VESSEL", "VOYAGE", "PORT OF LOADING",
        "PORT OF DISCHARGE", "PLACE OF DELIVERY",
        "CONTAINER", "GROSS WEIGHT", "NET WEIGHT",
        "B/L NO", "MARKS AND NUMBERS", "DESCRIPTION",
        "FREIGHT"
    ]

    value = extract_labeled_block(text, labels, stops, 2)
    return value if valid_port(value) else None


def extract_vessel(text):
    value = extract_labeled_block(
        text,
        ["VESSEL", "NAME OF VESSEL", "OCEAN VESSEL"],
        [
            "VOYAGE", "PORT OF LOADING", "PORT OF DISCHARGE",
            "PLACE OF DELIVERY", "CONSIGNEE", "NOTIFY PARTY",
            "SHIPPER", "CONTAINER", "GROSS WEIGHT", "B/L NO"
        ],
        1
    )

    if value and len(value) <= 100 and not re.search(
        r"THIS B/L|CLAUSES|COMBINED TRANSPORT|ENDORSEMENTS",
        value,
        re.I
    ):
        return value

    return None


def extract_voyage(text):
    return find_pattern(
        text,
        [
            r"VOYAGE\s*(?:NO\.?|NUMBER|#)?\s*[:\-]?\s*([A-Z0-9./_-]+)",
            r"\bV\.?\s*NO\.?\s*[:\-]?\s*([A-Z0-9./_-]+)"
        ]
    )


def extract_bl(text):
    shipper = extract_labeled_block(
        text,
        ["SHIPPER", "EXPORTER", "SHIPPER/EXPORTER"],
        [
            "CONSIGNEE", "NOTIFY PARTY", "NOTIFY",
            "PRE-CARRIAGE", "PLACE OF RECEIPT",
            "PORT OF LOADING", "PORT OF DISCHARGE",
            "PLACE OF DELIVERY", "VESSEL", "VOYAGE",
            "CONTAINER", "GROSS WEIGHT", "DESCRIPTION"
        ],
        5
    )

    consignee = extract_labeled_block(
        text,
        ["CONSIGNEE", "CONSIGNEE/IMPORTER"],
        [
            "NOTIFY PARTY", "NOTIFY", "SHIPPER",
            "PRE-CARRIAGE", "PLACE OF RECEIPT",
            "PORT OF LOADING", "PORT OF DISCHARGE",
            "PLACE OF DELIVERY", "VESSEL", "VOYAGE",
            "CONTAINER", "GROSS WEIGHT", "DESCRIPTION"
        ],
        5
    )

    notify = extract_labeled_block(
        text,
        ["NOTIFY PARTY", "NOTIFY"],
        [
            "SHIPPER", "CONSIGNEE", "PRE-CARRIAGE",
            "PLACE OF RECEIPT", "PORT OF LOADING",
            "PORT OF DISCHARGE", "PLACE OF DELIVERY",
            "VESSEL", "VOYAGE", "CONTAINER",
            "GROSS WEIGHT", "DESCRIPTION", "FREIGHT"
        ],
        5
    )

    # Loại kết quả sai thường gặp
    if notify:
        if container_set(notify):
            notify = None
        if re.search(
            r"COMBINED TRANSPORT|THIS B/L|CARRIER'S AGENTS|ENDORSEMENTS",
            notify,
            re.I
        ):
            notify = None

    return {
        "B/L No.": extract_bl_number(text),
        "Shipper": shipper,
        "Consignee": consignee,
        "Notify Party": notify,
        "Container No.": extract_containers(text),
        "Gross Weight": extract_weight(text, "gross"),
        "Port of Loading": extract_port(text, "loading"),
        "Port of Discharge": extract_port(text, "discharge"),
        "Place of Delivery": extract_port(text, "delivery"),
        "Vessel": extract_vessel(text),
        "Voyage": extract_voyage(text)
    }


# =========================================================
# INVOICE
# =========================================================

def extract_invoice(text):
    return {
        "Invoice No.": find_pattern(
            text,
            [
                r"(?:COMMERCIAL\s+INVOICE|PROFORMA\s+INVOICE|INVOICE)\s*(?:NO\.?|NUMBER|#)\s*[:#\-]?\s*([A-Z0-9][A-Z0-9./_-]{2,40})",
                r"\bINV\.?\s*(?:NO\.?|NUMBER|#)\s*[:#\-]?\s*([A-Z0-9][A-Z0-9./_-]{2,40})"
            ]
        ),

        "Invoice Date": find_pattern(
            text,
            [
                r"(?:INVOICE\s+DATE|DATE\s+OF\s+ISSUE|ISSUE\s+DATE)\s*[:\-]?\s*([0-9]{1,2}[-/.][A-Za-z0-9]{1,9}[-/.][0-9]{2,4})",
                r"(?:INVOICE\s+DATE|DATE\s+OF\s+ISSUE|ISSUE\s+DATE)\s*[:\-]?\s*([A-Za-z]{3,9}\s+[0-9]{1,2},?\s+[0-9]{4})",
                r"\bDATE\s*[:\-]\s*([0-9]{1,2}[-/.][0-9]{1,2}[-/.][0-9]{2,4})"
            ]
        ),

        "Seller / Exporter": extract_labeled_block(
            text,
            ["SELLER", "EXPORTER", "SUPPLIER", "SHIPPER"],
            ["BUYER", "IMPORTER", "BILL TO", "CONSIGNEE",
             "INVOICE NO", "DATE", "DESCRIPTION"],
            4
        ),

        "Buyer / Importer": extract_labeled_block(
            text,
            ["BUYER", "IMPORTER", "BILL TO", "CONSIGNEE"],
            ["SELLER", "EXPORTER", "SUPPLIER", "SHIPPER",
             "INVOICE NO", "DATE", "DESCRIPTION"],
            4
        ),

        "Commodity": extract_labeled_block(
            text,
            ["DESCRIPTION OF GOODS", "GOODS DESCRIPTION",
             "DESCRIPTION", "COMMODITY"],
            ["QUANTITY", "QTY", "UNIT PRICE", "PRICE",
             "AMOUNT", "TOTAL", "NET WEIGHT", "GROSS WEIGHT"],
            3
        ),

        "Country of Origin": find_pattern(
            text,
            [
                r"COUNTRY\s+OF\s+ORIGIN\s*[:>\-]?\s*([^\n]+)",
                r"MADE\s+IN\s+([A-Z][A-Z ,.&'-]+)"
            ]
        ),

        "Contract No.": find_pattern(
            text,
            [r"CONTRACT\s+(?:NO\.?|NUMBER)\s*[:#\-]?\s*([A-Z0-9./_-]+)"]
        ),

        "Gross Weight": extract_weight(text, "gross"),
        "Net Weight": extract_weight(text, "net"),
        "Container No.": extract_containers(text),
        "B/L No.": extract_bl_number(text),
        "Incoterm": extract_incoterm(text),
        "Currency": extract_currency(text),

        "Quantity": find_pattern(
            text,
            [
                r"(?:TOTAL\s+)?QUANTITY\s*[:\-]?\s*([\d,]+(?:\.\d+)?)",
                r"\bQTY\s*[:\-]?\s*([\d,]+(?:\.\d+)?)"
            ]
        ),

        "Unit Price": find_pattern(
            text,
            [
                r"(?:UNIT\s+PRICE|UNIT\s+VALUE|PRICE/UNIT|RATE)\s*[:\-]?\s*(?:USD|EUR|KRW|JPY|VND|CNY)?\s*([\d,]+(?:\.\d+)?)"
            ]
        ),

        "Total Amount": find_pattern(
            text,
            [
                r"(?:GRAND\s+TOTAL|TOTAL\s+AMOUNT|INVOICE\s+VALUE)\s*[:\-]?\s*(?:USD|EUR|KRW|JPY|VND|CNY)?\s*([\d,]+(?:\.\d+)?)",
                r"\bTOTAL\b\s*[:\-]?\s*(?:USD|EUR|KRW|JPY|VND|CNY)?\s*([\d,]+\.\d{2})"
            ]
        )
    }


# =========================================================
# PACKING LIST
# =========================================================

def extract_packing_list(text):
    return {
        "Packing List No.": find_pattern(
            text,
            [
                r"(?:PACKING\s+LIST|PACKING)\s*(?:NO\.?|NUMBER|#)\s*[:#\-]?\s*([A-Z0-9./_-]+)"
            ]
        ),
        "Net Weight": extract_weight(text, "net"),
        "Gross Weight": extract_weight(text, "gross"),
        "Packages": find_pattern(
            text,
            [
                r"(?:TOTAL\s+)?(?:NO\.?\s+OF\s+PACKAGES|NUMBER\s+OF\s+PACKAGES|PACKAGES|PKGS)\s*[:\-]?\s*(\d+)",
                r"(?:TOTAL\s+)?(?:CARTONS|CTNS)\s*[:\-]?\s*(\d+)"
            ]
        ),
        "Container No.": extract_containers(text),
        "Description": extract_labeled_block(
            text,
            ["DESCRIPTION OF GOODS", "GOODS DESCRIPTION", "DESCRIPTION"],
            ["QUANTITY", "QTY", "NET WEIGHT", "GROSS WEIGHT",
             "PACKAGES", "PKGS", "CONTAINER"],
            3
        ),
        "Quantity": find_pattern(
            text,
            [r"(?:QUANTITY|QTY)\s*[:\-]?\s*([\d,]+(?:\.\d+)?)"]
        )
    }


# =========================================================
# C/O
# =========================================================

def extract_co(text):
    return {
        "C/O No.": find_pattern(
            text,
            [
                r"(?:CERTIFICATE\s+NO|CERTIFICATE\s+NUMBER)\s*[:#\-]?\s*([A-Z0-9./_-]+)",
                r"(?:C/O|CO)\s*(?:NO\.?|NUMBER)\s*[:#\-]?\s*([A-Z0-9./_-]+)"
            ]
        ),

        "Exporter": extract_labeled_block(
            text,
            ["EXPORTER"],
            ["IMPORTER", "CONSIGNEE", "BUYER",
             "COUNTRY OF ORIGIN", "DESCRIPTION", "HS CODE"],
            5
        ),

        "Importer": extract_labeled_block(
            text,
            ["IMPORTER", "CONSIGNEE", "BUYER"],
            ["EXPORTER", "COUNTRY OF ORIGIN",
             "DESCRIPTION", "HS CODE"],
            5
        ),

        "Origin": find_pattern(
            text,
            [
                r"COUNTRY\s+OF\s+ORIGIN\s*[:\-]?\s*([^\n]+)",
                r"ORIGIN\s*[:\-]\s*([^\n]+)",
                r"MADE\s+IN\s+([A-Z][A-Z ,.&'-]+)"
            ]
        ),

        "HS Code": find_pattern(
            text,
            [
                r"HS\s*(?:CODE|NO\.?|NUMBER)\s*[:\-]?\s*(\d{4,10})",
                r"\bHS\s*[:\-]\s*(\d{4,10})"
            ]
        ),

        "Description": extract_labeled_block(
            text,
            ["DESCRIPTION OF GOODS", "GOODS DESCRIPTION", "DESCRIPTION"],
            ["HS CODE", "QUANTITY", "QTY",
             "ORIGIN CRITERIA", "ORIGIN CRITERION"],
            4
        ),

        "Quantity": find_pattern(
            text,
            [r"(?:QUANTITY|QTY)\s*[:\-]?\s*([\d,]+(?:\.\d+)?)"]
        )
    }


# =========================================================
# BOOKING
# =========================================================

def extract_booking(text):
    return {
        "Booking No.": find_pattern(
            text,
            [
                r"(?:BOOKING\s*(?:NO\.?|NUMBER|#)|BOOKING\s+REFERENCE)\s*[:#\-]?\s*([A-Z0-9./_-]{4,40})"
            ]
        ),

        "B/L No.": extract_bl_number(text),

        "Shipper": extract_labeled_block(
            text,
            ["SHIPPER", "EXPORTER"],
            ["CONSIGNEE", "NOTIFY", "BOOKING", "VESSEL",
             "VOYAGE", "PORT OF LOADING", "PORT OF DISCHARGE"],
            4
        ),

        "Consignee": extract_labeled_block(
            text,
            ["CONSIGNEE", "IMPORTER"],
            ["SHIPPER", "NOTIFY", "BOOKING", "VESSEL",
             "VOYAGE", "PORT OF LOADING", "PORT OF DISCHARGE"],
            4
        ),

        "Container No.": extract_containers(text),
        "Vessel": extract_vessel(text),
        "Voyage": extract_voyage(text),
        "Port of Loading": extract_port(text, "loading"),
        "Port of Discharge": extract_port(text, "discharge"),

        "ETD": find_pattern(
            text,
            [r"\bETD\b\s*[:\-]?\s*([^\n]+)"]
        ),

        "ETA": find_pattern(
            text,
            [r"\bETA\b\s*[:\-]?\s*([^\n]+)"]
        ),

        "CY Cut-off": find_pattern(
            text,
            [r"(?:CY\s*)?CUT[- ]?OFF\s*[:\-]?\s*([^\n]+)"]
        )
    }


# =========================================================
# DISPATCH
# =========================================================

def extract_document(text, document_type):
    if document_type == "COMMERCIAL INVOICE":
        return extract_invoice(text)
    if document_type == "BILL OF LADING":
        return extract_bl(text)
    if document_type == "PACKING LIST":
        return extract_packing_list(text)
    if document_type == "CERTIFICATE OF ORIGIN":
        return extract_co(text)
    if document_type == "BOOKING":
        return extract_booking(text)
    return {}


# =========================================================
# CROSS CHECK
# =========================================================

def add_check(results, field, a, b, status):
    results.append([
        field,
        a or EMPTY,
        b or EMPTY,
        status
    ])


def cross_check_documents(documents):
    results = []

    invoice = documents.get("COMMERCIAL INVOICE", {})
    bl = documents.get("BILL OF LADING", {})
    pl = documents.get("PACKING LIST", {})
    co = documents.get("CERTIFICATE OF ORIGIN", {})
    booking = documents.get("BOOKING", {})

    # Seller / Shipper
    if invoice and bl:
        a = invoice.get("Seller / Exporter")
        b = bl.get("Shipper")
        if a and b:
            add_check(
                results, "Seller / Shipper", a, b,
                "KHỚP" if values_match(a, b) else "KHÔNG KHỚP"
            )

    # Buyer / Consignee: role semantics can differ
    if invoice and bl:
        a = invoice.get("Buyer / Importer")
        b = bl.get("Consignee")
        if a and b:
            add_check(
                results, "Buyer / Consignee", a, b,
                "KHỚP" if values_match(a, b) else "CẦN XÁC NHẬN"
            )

    # Containers
    container_sources = []
    for name, d in [
        ("Invoice", invoice),
        ("PL", pl),
        ("B/L", bl),
        ("Booking", booking)
    ]:
        s = container_set(d.get("Container No."))
        if s:
            container_sources.append((name, s))

    if len(container_sources) >= 2:
        base_name, base = container_sources[0]
        for other_name, other in container_sources[1:]:
            if base == other:
                status = "KHỚP"
            elif base.intersection(other):
                status = "CẢNH BÁO"
            else:
                status = "KHÔNG KHỚP"

            add_check(
                results,
                f"Container {base_name} ↔ {other_name}",
                ", ".join(sorted(base)),
                ", ".join(sorted(other)),
                status
            )

    # PL Gross ↔ B/L Gross
    if pl and bl:
        a = pl.get("Gross Weight")
        b = bl.get("Gross Weight")
        if a and b:
            na = normalize_number(a)
            nb = normalize_number(b)
            status = "KHỚP" if na and nb and float(na) == float(nb) else "KHÔNG KHỚP"
            add_check(results, "Gross Weight PL ↔ B/L", a, b, status)

    # Invoice B/L No ↔ B/L
    if invoice and bl:
        a = invoice.get("B/L No.")
        b = bl.get("B/L No.")
        if a and b:
            add_check(
                results, "B/L No. Invoice ↔ B/L", a, b,
                "KHỚP" if values_match(a, b) else "KHÔNG KHỚP"
            )

    # Booking B/L No ↔ B/L
    if booking and bl:
        a = booking.get("B/L No.")
        b = bl.get("B/L No.")
        if a and b:
            add_check(
                results, "B/L No. Booking ↔ B/L", a, b,
                "KHỚP" if values_match(a, b) else "KHÔNG KHỚP"
            )

    # Vessel / Voyage Booking ↔ B/L
    if booking and bl:
        for field in ["Vessel", "Voyage"]:
            a = booking.get(field)
            b = bl.get(field)
            if a and b:
                add_check(
                    results,
                    f"{field} Booking ↔ B/L",
                    a, b,
                    "KHỚP" if values_match(a, b) else "CẦN XÁC NHẬN"
                )

    # Ports Booking ↔ B/L
    if booking and bl:
        for field in ["Port of Loading", "Port of Discharge"]:
            a = booking.get(field)
            b = bl.get(field)
            if a and b:
                add_check(
                    results,
                    f"{field} Booking ↔ B/L",
                    a, b,
                    "KHỚP" if values_match(a, b) else "CẦN XÁC NHẬN"
                )

    # Invoice Origin ↔ C/O
    if invoice and co:
        a = invoice.get("Country of Origin")
        b = co.get("Origin")
        if a and b:
            add_check(
                results, "Country of Origin Invoice ↔ C/O",
                a, b,
                "KHỚP" if values_match(a, b) else "CẦN XÁC NHẬN"
            )

    # Invoice / PL quantity
    if invoice and pl:
        a = invoice.get("Quantity")
        b = pl.get("Quantity")
        if a and b:
            na = normalize_number(a)
            nb = normalize_number(b)
            if na and nb:
                add_check(
                    results, "Quantity Invoice ↔ PL",
                    a, b,
                    "KHỚP" if float(na) == float(nb) else "CẦN XÁC NHẬN"
                )

    return results


# =========================================================
# CUSTOMS DATA
# =========================================================

def build_customs_data(documents):
    invoice = documents.get("COMMERCIAL INVOICE", {})
    pl = documents.get("PACKING LIST", {})
    bl = documents.get("BILL OF LADING", {})
    co = documents.get("CERTIFICATE OF ORIGIN", {})
    booking = documents.get("BOOKING", {})

    rows = [
        ["Người xuất khẩu",
         invoice.get("Seller / Exporter") or bl.get("Shipper") or co.get("Exporter"),
         "Invoice / B/L / C/O"],

        ["Người nhập khẩu",
         invoice.get("Buyer / Importer") or bl.get("Consignee") or co.get("Importer"),
         "Invoice / B/L / C/O"],

        ["Số Invoice", invoice.get("Invoice No."), "Invoice"],
        ["Ngày Invoice", invoice.get("Invoice Date"), "Invoice"],
        ["Trị giá hóa đơn", invoice.get("Total Amount"), "Invoice"],
        ["Tiền tệ", invoice.get("Currency"), "Invoice"],
        ["Điều kiện Incoterm", invoice.get("Incoterm"), "Invoice"],
        ["Mô tả hàng hóa",
         invoice.get("Commodity") or pl.get("Description") or co.get("Description"),
         "Invoice / PL / C/O"],
        ["Số lượng",
         invoice.get("Quantity") or pl.get("Quantity") or co.get("Quantity"),
         "Invoice / PL / C/O"],
        ["Gross Weight",
         pl.get("Gross Weight") or bl.get("Gross Weight"),
         "PL / B/L"],
        ["Net Weight",
         pl.get("Net Weight") or invoice.get("Net Weight"),
         "PL / Invoice"],
        ["Container No.",
         pl.get("Container No.") or bl.get("Container No.") or booking.get("Container No."),
         "PL / B/L / Booking"],
        ["B/L No.", bl.get("B/L No.") or booking.get("B/L No."), "B/L / Booking"],
        ["Booking No.", booking.get("Booking No."), "Booking"],
        ["Port of Loading", bl.get("Port of Loading") or booking.get("Port of Loading"), "B/L / Booking"],
        ["Port of Discharge", bl.get("Port of Discharge") or booking.get("Port of Discharge"), "B/L / Booking"],
        ["Place of Delivery", bl.get("Place of Delivery"), "B/L"],
        ["Vessel", bl.get("Vessel") or booking.get("Vessel"), "B/L / Booking"],
        ["Voyage", bl.get("Voyage") or booking.get("Voyage"), "B/L / Booking"],
        ["Country of Origin", invoice.get("Country of Origin") or co.get("Origin"), "Invoice / C/O"],
        ["HS Code", co.get("HS Code"), "C/O"]
    ]

    return pd.DataFrame(
        [
            [field, value if value else EMPTY, source]
            for field, value, source in rows
        ],
        columns=["Thông tin", "Giá trị", "Nguồn chứng từ"]
    )


# =========================================================
# UI
# =========================================================

uploaded_files = st.file_uploader(
    "📄 Tải lên bộ chứng từ PDF",
    type=["pdf"],
    accept_multiple_files=True
)

if "documents_data" not in st.session_state:
    st.session_state.documents_data = {}

if uploaded_files:
    st.success(f"Đã tải lên {len(uploaded_files)} chứng từ.")

    st.write("### 📁 Danh sách chứng từ")
    for file in uploaded_files:
        st.write(f"📄 {file.name}")

    st.divider()

    if st.button("🔍 Đọc và trích xuất dữ liệu", type="primary"):
        documents = {}

        for file in uploaded_files:
            st.write(f"## 📄 {file.name}")

            file_bytes = file.getvalue()

            pages, page_count, method, read_error = process_pdf(file_bytes)

            text = normalize_text("\n".join(pages))

            st.write(f"**Số trang:** {page_count}")
            st.write(f"**Phương thức đọc:** {method}")

            if read_error:
                st.caption(f"Thông tin xử lý: {read_error}")

            if not text:
                st.error("Không đọc được nội dung tài liệu.")
                continue

            st.success("Đọc tài liệu thành công.")

            document_type, scores = detect_document_type(text)

            st.write(
                f"### 🗂️ Loại chứng từ: **{document_type}**"
            )

            score_df = pd.DataFrame(
                [
                    [k, v]
                    for k, v in sorted(
                        scores.items(),
                        key=lambda x: x[1],
                        reverse=True
                    )
                ],
                columns=["Loại chứng từ", "Điểm nhận diện"]
            )

            with st.expander("🔎 Chi tiết nhận diện chứng từ"):
                st.dataframe(
                    score_df,
                    use_container_width=True,
                    hide_index=True
                )

            data = extract_document(text, document_type)

            if data:
                documents[document_type] = data

                df = pd.DataFrame(
                    [
                        [field, value if value else EMPTY]
                        for field, value in data.items()
                    ],
                    columns=["Trường dữ liệu", "Giá trị"]
                )

                st.write("### 📊 Dữ liệu tự động trích xuất")
                st.dataframe(
                    df,
                    use_container_width=True,
                    hide_index=True
                )
            else:
                st.warning("Chưa trích xuất được dữ liệu.")

            with st.expander("📖 Xem nội dung hệ thống đọc được"):
                st.text_area(
                    "PDF Text / OCR Text",
                    text,
                    height=400,
                    key=f"text_{file.name}"
                )

        st.session_state.documents_data = documents

# =========================================================
# CROSS CHECK UI
# =========================================================

documents = st.session_state.documents_data

if documents and len(documents) >= 2:
    st.divider()
    st.header("🔎 Kiểm tra chéo chứng từ")

    results = cross_check_documents(documents)

    if results:
        check_df = pd.DataFrame(
            results,
            columns=["Chỉ tiêu", "Chứng từ 1", "Chứng từ 2", "Kết quả"]
        )

        st.dataframe(
            check_df,
            use_container_width=True,
            hide_index=True
        )

        matched = sum(x[3] == "KHỚP" for x in results)
        warning = sum(x[3] in ["CẢNH BÁO", "CẦN XÁC NHẬN"] for x in results)
        mismatch = sum(x[3] == "KHÔNG KHỚP" for x in results)
        missing = sum(x[3] == "THIẾU DỮ LIỆU" for x in results)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("🟢 Khớp", matched)
        c2.metric("🟡 Cảnh báo", warning)
        c3.metric("🔴 Không khớp", mismatch)
        c4.metric("⚪ Thiếu", missing)

    else:
        st.info("Chưa có đủ trường dữ liệu để kiểm tra chéo.")

# =========================================================
# CUSTOMS SUPPORT
# =========================================================

if documents:
    st.divider()
    st.header("🧾 Thông tin phục vụ khai báo hải quan")

    customs_df = build_customs_data(documents)

    st.dataframe(
        customs_df,
        use_container_width=True,
        hide_index=True
    )

    st.info(
        "Đây là dữ liệu hỗ trợ chuẩn bị khai báo. "
        "Các trường chuyên biệt như mã loại hình, mã cơ quan Hải quan, "
        "mã bộ phận xử lý, phân luồng... không được hệ thống tự suy đoán."
    )

# =========================================================
# NOTE
# =========================================================

st.divider()

with st.expander("ℹ️ Lưu ý về hệ thống"):
    st.write(
        """
        CustomsDoc Check là công cụ hỗ trợ kiểm soát chứng từ.

        Hệ thống:
        - Đọc PDF và OCR tài liệu scan
        - Nhận diện nhiều mẫu chứng từ
        - Trích xuất dữ liệu theo alias/nhãn
        - Chuẩn hóa dữ liệu
        - Kiểm tra chéo Invoice / PL / B/L / C/O / Booking
        - Hỗ trợ chuẩn bị dữ liệu phục vụ khai báo

        Hệ thống không tự động gửi tờ khai lên VNACCS/VCIS
        và không thay thế quyết định kiểm tra của nhân viên nghiệp vụ.
        """
    )
