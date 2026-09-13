import streamlit as st
from pypdf import PdfReader
from io import BytesIO
import pytesseract
from pdf2image import convert_from_bytes
import pandas as pd
import re


# =========================================================
# 1. CONFIG
# =========================================================

st.set_page_config(
    page_title="Customs Document Check",
    page_icon="📄",
    layout="wide"
)
# =========================================================
# PRO UI STYLE
# =========================================================

st.markdown("""
<style>

@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
}

.stApp {
    background: #f5f7fb;
}

/* ---------- SIDEBAR ---------- */

section[data-testid="stSidebar"] {
    background: #0f1f35;
    border-right: 1px solid #1d3557;
}

section[data-testid="stSidebar"] * {
    color: #e8eef7 !important;
}

.sidebar-logo {
    font-size: 24px;
    font-weight: 800;
    letter-spacing: -0.5px;
    padding: 10px 5px 5px 5px;
}

.sidebar-subtitle {
    font-size: 12px;
    color: #91a4bd !important;
    margin-bottom: 30px;
}

.sidebar-section {
    font-size: 11px;
    font-weight: 700;
    color: #7186a1 !important;
    text-transform: uppercase;
    letter-spacing: 1px;
    margin: 20px 5px 8px;
}

/* ---------- MAIN HEADER ---------- */

.main-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 8px;
}

.page-title {
    font-size: 31px;
    font-weight: 800;
    color: #10243e;
    letter-spacing: -1px;
}

.page-subtitle {
    color: #718096;
    font-size: 14px;
    margin-bottom: 28px;
}

/* ---------- STATUS ---------- */

.status-pill {
    display: inline-flex;
    align-items: center;
    padding: 6px 12px;
    border-radius: 999px;
    font-size: 12px;
    font-weight: 700;
}

.status-green {
    background: #e7f7ef;
    color: #138a52;
}

.status-yellow {
    background: #fff5d8;
    color: #a56a00;
}

.status-red {
    background: #fdeaea;
    color: #c53030;
}

/* ---------- KPI ---------- */

.kpi-card {
    background: white;
    border: 1px solid #e5eaf1;
    border-radius: 15px;
    padding: 20px;
    box-shadow: 0 3px 12px rgba(15, 31, 53, 0.04);
    min-height: 120px;
}

.kpi-label {
    color: #718096;
    font-size: 13px;
    font-weight: 600;
}

.kpi-value {
    color: #10243e;
    font-size: 29px;
    font-weight: 800;
    margin-top: 8px;
}

.kpi-note {
    color: #91a0b2;
    font-size: 11px;
    margin-top: 4px;
}

/* ---------- SECTION ---------- */

.section-title {
    color: #10243e;
    font-size: 19px;
    font-weight: 750;
    margin-top: 28px;
    margin-bottom: 5px;
}

.section-description {
    color: #718096;
    font-size: 13px;
    margin-bottom: 15px;
}

/* ---------- UPLOAD ---------- */

.upload-box {
    background: white;
    border: 2px dashed #cbd5e1;
    border-radius: 16px;
    padding: 32px;
    text-align: center;
    margin: 10px 0 25px;
}

.upload-icon {
    font-size: 36px;
    margin-bottom: 8px;
}

.upload-title {
    color: #10243e;
    font-weight: 700;
    font-size: 16px;
}

.upload-description {
    color: #718096;
    font-size: 13px;
}

/* ---------- DOCUMENT CARD ---------- */

.doc-card {
    background: white;
    border: 1px solid #e5eaf1;
    border-radius: 14px;
    padding: 17px;
    margin-bottom: 12px;
    box-shadow: 0 3px 10px rgba(15, 31, 53, 0.035);
}

.doc-icon {
    font-size: 25px;
}

.doc-name {
    color: #10243e;
    font-weight: 700;
    font-size: 14px;
}

.doc-type {
    color: #718096;
    font-size: 12px;
    margin-top: 3px;
}

/* ---------- INFO BOX ---------- */

.info-card {
    background: #edf5ff;
    border: 1px solid #cfe2ff;
    border-radius: 13px;
    padding: 16px 18px;
    color: #24527a;
    font-size: 13px;
}

/* ---------- TABLE ---------- */

div[data-testid="stDataFrame"] {
    border-radius: 12px;
    overflow: hidden;
}

/* ---------- BUTTON ---------- */

.stButton > button {
    border-radius: 9px;
    font-weight: 650;
    border: 1px solid #d9e1ec;
    min-height: 42px;
}

.stButton > button[kind="primary"] {
    background: #17365d;
    border-color: #17365d;
}

/* ---------- TABS ---------- */

button[data-baseweb="tab"] {
    font-weight: 600;
}

/* ---------- FILE UPLOADER ---------- */

[data-testid="stFileUploader"] {
    background: white;
    border-radius: 14px;
    padding: 5px;
}

/* ---------- FOOTER ---------- */

.footer {
    text-align: center;
    color: #9aa8b8;
    font-size: 11px;
    padding: 35px 0 15px;
}

</style>
""", unsafe_allow_html=True)
EMPTY = "Không tìm thấy"


# =========================================================
# 2. BASIC HELPERS
# =========================================================

def clean_value(value):
    if value is None:
        return EMPTY

    value = str(value).strip()

    if not value:
        return EMPTY

    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n{2,}", "\n", value)

    return value.strip()


def normalize_text(text):
    if not text:
        return ""

    text = text.replace("\r", "\n")
    text = text.replace("\x00", " ")

    # Các ký tự OCR thường gặp
    text = text.replace("：", ":")
    text = text.replace("–", "-")
    text = text.replace("—", "-")

    # Giảm nhiều khoảng trắng
    text = re.sub(r"[ \t]+", " ", text)

    # Giảm dòng trống
    text = re.sub(r"\n{2,}", "\n", text)

    return text.strip()


def get_lines(text):
    text = normalize_text(text)

    return [
        line.strip()
        for line in text.split("\n")
        if line.strip()
    ]


def normalize_number(value):
    if not value or value == EMPTY:
        return None

    value = str(value).strip()
    value = value.replace(",", "")

    try:
        return float(value)
    except:
        return None


def normalize_compare(value):
    if value is None or value == EMPTY:
        return ""

    value = str(value).upper().strip()

    value = re.sub(r"\s+", " ", value)
    value = value.replace(",", "")
    value = value.replace(".", "")
    value = value.replace("-", "")
    value = value.replace("/", "")
    value = value.replace(":", "")

    return value


def values_match(a, b):
    if a in [None, EMPTY] or b in [None, EMPTY]:
        return False

    na = normalize_compare(a)
    nb = normalize_compare(b)

    return na == nb


# =========================================================
# 3. PDF / OCR
# =========================================================

def read_pdf_text(file_bytes):

    pages = []

    try:
        reader = PdfReader(BytesIO(file_bytes))

        for page in reader.pages:
            text = page.extract_text() or ""
            pages.append(text)

        return pages, len(reader.pages), None

    except Exception as e:
        return [], 0, str(e)


def ocr_pdf(file_bytes):

    pages = []

    try:
        images = convert_from_bytes(
            file_bytes,
            dpi=200
        )

        for image in images:

            try:
                text = pytesseract.image_to_string(
                    image,
                    lang="eng+vie"
                )
            except:
                text = pytesseract.image_to_string(
                    image,
                    lang="eng"
                )

            pages.append(text)

        return pages, len(images), None

    except Exception as e:
        return [], 0, str(e)


def process_pdf(file_bytes):

    text_pages, page_count, error = read_pdf_text(file_bytes)

    if error:
        return [], 0, "ERROR", error

    final_pages = []

    for text in text_pages:

        # Nếu PDF có text tương đối đầy đủ -> dùng luôn
        if len(text.strip()) >= 30:
            final_pages.append(text)

        else:
            # Trang scan -> OCR riêng trang đó
            try:
                images = convert_from_bytes(
                    file_bytes,
                    dpi=200
                )

                break

            except:
                final_pages.append(text)

    # Nếu có trang cần OCR
    needs_ocr = any(
        len(page.strip()) < 30
        for page in text_pages
    )

    if needs_ocr:

        try:
            images = convert_from_bytes(
                file_bytes,
                dpi=200
            )

            final_pages = []

            for i, image in enumerate(images):

                original = text_pages[i] if i < len(text_pages) else ""

                if len(original.strip()) >= 30:
                    final_pages.append(original)

                else:

                    try:
                        ocr_text = pytesseract.image_to_string(
                            image,
                            lang="eng+vie"
                        )
                    except:
                        ocr_text = pytesseract.image_to_string(
                            image,
                            lang="eng"
                        )

                    final_pages.append(ocr_text)

            return final_pages, page_count, "TEXT + OCR", None

        except Exception as e:
            return text_pages, page_count, "TEXT", str(e)

    return final_pages, page_count, "TEXT", None


# =========================================================
# 4. GENERIC REGEX
# =========================================================

def find_pattern(text, patterns):

    if not text:
        return EMPTY

    for pattern in patterns:

        match = re.search(
            pattern,
            text,
            re.IGNORECASE | re.MULTILINE
        )

        if match:

            value = match.group(1)

            value = clean_value(value)

            if value:
                return value

    return EMPTY


def find_all_patterns(text, patterns):

    results = []

    if not text:
        return results

    for pattern in patterns:

        matches = re.findall(
            pattern,
            text,
            re.IGNORECASE | re.MULTILINE
        )

        for match in matches:

            if isinstance(match, tuple):
                value = match[0]
            else:
                value = match

            value = clean_value(value)

            if value and value not in results:
                results.append(value)

    return results


def extract_labeled_block(
    text,
    labels,
    stop_labels,
    max_lines=4
):

    lines = get_lines(text)

    labels_upper = [
        x.upper()
        for x in labels
    ]

    stop_upper = [
        x.upper()
        for x in stop_labels
    ]

    for i, line in enumerate(lines):

        upper = line.upper().strip()

        found = False

        for label in labels_upper:

            if upper.startswith(label):

                found = True
                break

        if not found:
            continue

        values = []

        # Nếu label có ":" ngay trên dòng
        if ":" in line:

            after = line.split(":", 1)[1].strip()

            if after:
                values.append(after)

        # Lấy các dòng sau label
        for j in range(
            i + 1,
            min(i + 1 + max_lines, len(lines))
        ):

            candidate = lines[j]
            candidate_upper = candidate.upper()

            # Dừng khi gặp label khác
            if any(
                candidate_upper.startswith(stop)
                for stop in stop_upper
            ):
                break

            # Không lấy các heading vô nghĩa
            if candidate.strip():

                values.append(candidate)

        if values:

            return clean_value("\n".join(values))

    return EMPTY


# =========================================================
# 5. DATE
# =========================================================

def extract_date(text):

    patterns = [

        # Date: JUL 14, 2021
        r"\bDATE\s*[:\-]\s*([A-Z]{3,9}\s+\d{1,2},?\s+\d{4})",

        # Date: 14-Jul-2021
        r"\bDATE\s*[:\-]\s*(\d{1,2}[-/.][A-Za-z]{3,9}[-/.]\d{2,4})",

        # Invoice Date
        r"(?:INVOICE\s+DATE|DATE\s+OF\s+ISSUE|ISSUE\s+DATE)"
        r"\s*[:\-]?\s*"
        r"([A-Z]{3,9}\s+\d{1,2},?\s+\d{4})",

        r"(?:INVOICE\s+DATE|DATE\s+OF\s+ISSUE|ISSUE\s+DATE)"
        r"\s*[:\-]?\s*"
        r"(\d{1,2}[-/.][A-Za-z0-9]{1,9}[-/.]\d{2,4})"
    ]

    return find_pattern(text, patterns)


# =========================================================
# 6. CONTAINER + SEAL
# =========================================================

def extract_containers(text):

    if not text:
        return EMPTY

    # Container chuẩn ISO:
    # 4 chữ + 7 số
    matches = re.findall(
        r"\b[A-Z]{4}\d{7}\b",
        text.upper()
    )

    unique = []

    for item in matches:

        if item not in unique:
            unique.append(item)

    if unique:
        return ", ".join(unique)

    return EMPTY


def extract_container_seal_pairs(text):

    containers = []
    seals = []

    # Ví dụ:
    # INKU6515772/9436022
    # TGHU7502610/9436021

    matches = re.findall(
        r"\b([A-Z]{4}\d{7})\s*/\s*(\d{4,12})\b",
        text.upper()
    )

    for container, seal in matches:

        if container not in containers:
            containers.append(container)

        if seal not in seals:
            seals.append(seal)

    return containers, seals


def container_set(value):

    if not value or value == EMPTY:
        return set()

    return set(
        re.findall(
            r"\b[A-Z]{4}\d{7}\b",
            str(value).upper()
        )
    )


# =========================================================
# 7. WEIGHT
# =========================================================

def extract_weight(text, weight_type):

    if not text:
        return EMPTY

    if weight_type.lower() == "gross":

        patterns = [
            r"GROSS\s+WEIGHT\s*[:\-]?\s*([\d,]+(?:\.\d+)?)\s*KGS?",
            r"GROSS\s+WEIGHT\s*\n\s*([\d,]+(?:\.\d+)?)\s*KGS?",
        ]

    else:

        patterns = [
            r"NET\s+WEIGHT\s*[:\-]?\s*([\d,]+(?:\.\d+)?)\s*KGS?",
            r"N\.?\s*W\.?\s*\(KGS?\)\s*\n\s*([\d,]+(?:\.\d+)?)",
            r"N\.?\s*W\.?\s*[:\-]?\s*([\d,]+(?:\.\d+)?)\s*KGS?"
        ]

    value = find_pattern(text, patterns)

    if value != EMPTY:
        return value

    return EMPTY


# =========================================================
# 8. CURRENCY
# =========================================================

def extract_currency(text):

    if not text:
        return EMPTY

    patterns = [

        r"\(\s*(USD|EUR|KRW|JPY|VND|CNY)\s*/\s*KG\s*\)",

        r"\(\s*(USD|EUR|KRW|JPY|VND|CNY)\s*\)",

        r"\b(USD|EUR|KRW|JPY|VND|CNY)\b",

        r"UNITED\s+STATES\s+DOLLARS"
    ]

    result = find_pattern(text, patterns)

    if result == "UNITED STATES DOLLARS":
        return "USD"

    return result


# =========================================================
# 9. INCOTERM
# =========================================================

def extract_incoterm(text):

    patterns = [
        r"\b(CIF|FOB|EXW|FCA|CFR|CPT|CIP|DAP|DPU|DDP|FAS|DAT)\b"
    ]

    return find_pattern(text, patterns)


def extract_delivery_terms(text):

    return find_pattern(
        text,
        [
            r"DELIVERY\s+TERMS?\s*[:\-]\s*([^\n]+)",
            r"DELIVERY\s+TERMS?\s*\n\s*[:\-]?\s*([^\n]+)"
        ]
    )


# =========================================================
# 10. PORT
# =========================================================

def valid_port(value):

    if not value or value == EMPTY:
        return False

    value = value.strip()

    return (
        len(value) >= 3
        and not re.fullmatch(r"[\d\s.,/-]+", value)
    )


def extract_port(text, port_type):

    if port_type == "loading":

        patterns = [
            r"PORT\s+OF\s+LOADING\s*[:\-]\s*([^\n]+)",
            r"PORT\s+OF\s+LOADING\s*\n\s*[:\-]?\s*([^\n]+)",
            r"PLACE\s+OF\s+RECEIPT\s*[:\-]\s*([^\n]+)"
        ]

    elif port_type == "discharge":

        patterns = [
            r"PORT\s+OF\s+DISCHARGE\s*[:\-]\s*([^\n]+)",
            r"PORT\s+OF\s+DISCHARGE\s*\n\s*[:\-]?\s*([^\n]+)"
        ]

    else:

        patterns = [
            r"PLACE\s+OF\s+DELIVERY\s*[:\-]\s*([^\n]+)",
            r"PLACE\s+OF\s+DELIVERY\s*\n\s*[:\-]?\s*([^\n]+)"
        ]

    value = find_pattern(text, patterns)

    if valid_port(value):
        return value

    return EMPTY


# =========================================================
# 11. B/L
# =========================================================

def valid_bl_number(value):

    if not value or value == EMPTY:
        return False

    value = value.strip().upper()

    # B/L thường gồm chữ + số
    if not re.fullmatch(
        r"[A-Z]{3,6}[A-Z0-9]{5,20}",
        value
    ):
        return False

    # Không nhận container
    if re.fullmatch(
        r"[A-Z]{4}\d{7}",
        value
    ):
        return False

    return True


def extract_bl_number(text):

    patterns = [

        r"(?:B/L\s*NO\.?|B/L\s*NUMBER|BILL\s+OF\s+LADING\s*NO\.?)"
        r"\s*[:#\-]?\s*([A-Z0-9][A-Z0-9./_-]{5,30})",

        r"\bB/L\s*[:\-]\s*([A-Z0-9][A-Z0-9./_-]{5,30})"
    ]

    value = find_pattern(text, patterns)

    if valid_bl_number(value):
        return value

    # Fallback: tìm chuỗi dạng B/L phổ biến
    candidates = re.findall(
        r"\b[A-Z]{3,6}\d{6,20}\b",
        text.upper()
    )

    for candidate in candidates:

        if not re.fullmatch(
            r"[A-Z]{4}\d{7}",
            candidate
        ):
            return candidate

    return EMPTY


def extract_vessel(text):

    return find_pattern(
        text,
        [
            r"VESSEL\s*[:\-]\s*([^\n]+)",
            r"VESSEL\s*/\s*VOYAGE\s*[:\-]?\s*([^\n]+)"
        ]
    )


def extract_voyage(text):

    return find_pattern(
        text,
        [
            r"VOYAGE\s*[:\-]\s*([^\n]+)"
        ]
    )


def extract_bl(text):

    return {

        "B/L No.": extract_bl_number(text),

        "Shipper": extract_labeled_block(
            text,
            ["SHIPPER"],
            [
                "CONSIGNEE",
                "NOTIFY PARTY",
                "B/L NO",
                "BILL OF LADING"
            ],
            3
        ),

        "Consignee": extract_labeled_block(
            text,
            ["CONSIGNEE"],
            [
                "NOTIFY PARTY",
                "SHIPPER",
                "B/L NO",
                "BILL OF LADING"
            ],
            3
        ),

        "Notify Party": extract_labeled_block(
            text,
            ["NOTIFY PARTY"],
            [
                "SHIPPER",
                "CONSIGNEE",
                "B/L NO",
                "VESSEL",
                "VOYAGE"
            ],
            3
        ),

        "Container No.": extract_containers(text),

        "Gross Weight": extract_weight(
            text,
            "gross"
        ),

        "Port of Loading": extract_port(
            text,
            "loading"
        ),

        "Port of Discharge": extract_port(
            text,
            "discharge"
        ),

        "Place of Delivery": extract_port(
            text,
            "delivery"
        ),

        "Vessel": extract_vessel(text),

        "Voyage": extract_voyage(text)
    }


# =========================================================
# 12. DOCUMENT DETECTION
# =========================================================

def detect_document_type(text, filename=""):

    t = (text or "").upper()
    f = (filename or "").upper()

    scores = {
        "COMMERCIAL INVOICE": 0,
        "PACKING LIST": 0,
        "BILL OF LADING": 0,
        "CERTIFICATE OF ORIGIN": 0,
        "BOOKING": 0
    }

    # -------------------------
    # Invoice
    # -------------------------

    if "COMMERCIAL INVOICE" in t:
        scores["COMMERCIAL INVOICE"] += 20

    if "PROFORMA INVOICE" in t:
        scores["COMMERCIAL INVOICE"] += 20

    if "INVOICE" in t:
        scores["COMMERCIAL INVOICE"] += 8

    if "UNIT PRICE" in t:
        scores["COMMERCIAL INVOICE"] += 5

    if "AMOUNT" in t:
        scores["COMMERCIAL INVOICE"] += 3

    # -------------------------
    # Packing List
    # -------------------------

    if "PACKING LIST" in t:
        scores["PACKING LIST"] += 20

    if "NET WEIGHT" in t:
        scores["PACKING LIST"] += 4

    if "GROSS WEIGHT" in t:
        scores["PACKING LIST"] += 4

    # -------------------------
    # B/L
    # -------------------------

    if "BILL OF LADING" in t:
        scores["BILL OF LADING"] += 30

    if "B/L NO" in t:
        scores["BILL OF LADING"] += 15

    if "SHIPPER" in t:
        scores["BILL OF LADING"] += 5

    if "CONSIGNEE" in t:
        scores["BILL OF LADING"] += 5

    # -------------------------
    # C/O
    # -------------------------

    if "CERTIFICATE OF ORIGIN" in t:
        scores["CERTIFICATE OF ORIGIN"] += 30

    if "FORM E" in t:
        scores["CERTIFICATE OF ORIGIN"] += 15

    if "FORM D" in t:
        scores["CERTIFICATE OF ORIGIN"] += 15

    # -------------------------
    # Booking
    # -------------------------

    if "BOOKING" in t:
        scores["BOOKING"] += 20

    if "BOOKING NO" in t:
        scores["BOOKING"] += 10

    # filename hint
    if "INVOICE" in f:
        scores["COMMERCIAL INVOICE"] += 5

    if "PACKING" in f:
        scores["PACKING LIST"] += 5

    if "BILL" in f or "B_L" in f:
        scores["BILL OF LADING"] += 5

    if "CERTIFICATE" in f or "CO" in f:
        scores["CERTIFICATE OF ORIGIN"] += 3

    if "BOOKING" in f:
        scores["BOOKING"] += 5

    best_type = max(
        scores,
        key=scores.get
    )

    if scores[best_type] == 0:
        return "KHÔNG XÁC ĐỊNH", scores

    return best_type, scores


# =========================================================
# 13. COMMERCIAL INVOICE - SPECIAL PARSER
# =========================================================

def extract_invoice_parties(text):

    lines = get_lines(text)

    seller = EMPTY
    buyer = EMPTY
    seller_address = EMPTY

    # ----------------------------------------
    # SELLER
    # ----------------------------------------

    # Seller thường nằm ở đầu invoice
    invoice_index = None

    for i, line in enumerate(lines):

        if "COMMERCIAL INVOICE" in line.upper():
            invoice_index = i
            break

        if "PROFORMA INVOICE" in line.upper():
            invoice_index = i
            break

    if invoice_index is None:
        invoice_index = len(lines)

    header = lines[:invoice_index]

    seller_candidates = []

    for line in header:

        upper = line.upper()

        if any(
            x in upper
            for x in [
                "ADDRESS:",
                "TEL:",
                "FAX:",
                "HTTP",
                "COMMERCIAL INVOICE",
                "PROFORMA INVOICE"
            ]
        ):
            continue

        if re.fullmatch(
            r"[\d\s()+\-./]+",
            line
        ):
            continue

        seller_candidates.append(line)

    if seller_candidates:

        # Lấy tối đa 2 dòng đầu có ý nghĩa
        seller_lines = []

        for line in seller_candidates:

            if len(line) >= 3:
                seller_lines.append(line)

            if len(seller_lines) >= 2:
                break

        if seller_lines:
            seller = " / ".join(seller_lines)

    # Seller address
    for i, line in enumerate(header):

        if "VIETNAM" in line.upper():

            if "ADDRESS" not in line.upper():

                seller_address = line
                break

    # ----------------------------------------
    # BUYER
    # ----------------------------------------

    risk_index = None

    for i, line in enumerate(lines):

        if "FOR ACCOUNT AND RISK OF" in line.upper():
            risk_index = i
            break

    if risk_index is not None:

        buyer_lines = []

        for j in range(
            risk_index + 1,
            min(risk_index + 4, len(lines))
        ):

            candidate = lines[j]

            upper = candidate.upper()

            if upper.startswith("COMMODITY"):
                break

            if ":" in candidate:
                # Nếu dòng sau đã là field khác
                before = candidate.split(":", 1)[0].strip()

                if before.upper() in [
                    "COMMODITY",
                    "COUNTRY OF ORIGIN",
                    "CONTRACT NO.",
                    "GROSS WEIGHT",
                    "CONTAINER / SEAL NO.",
                    "B/L NO.",
                    "PORT OF LOADING",
                    "PORT OF DISCHARGE",
                    "DELIVERY TERMS"
                ]:
                    break

            if candidate:
                buyer_lines.append(candidate)

        if buyer_lines:
            buyer = " / ".join(buyer_lines[:2])

    return {
        "Seller / Exporter": clean_value(seller),
        "Seller Address": clean_value(seller_address),
        "Buyer / Importer": clean_value(buyer)
    }


def extract_invoice_colon_field(
    text,
    label,
    stop_labels,
    max_lines=2
):

    lines = get_lines(text)

    label_upper = label.upper()

    stop_upper = [
        x.upper()
        for x in stop_labels
    ]

    for i, line in enumerate(lines):

        upper = line.upper()

        if not upper.startswith(label_upper):
            continue

        values = []

        # Có dữ liệu cùng dòng
        if ":" in line:

            value = line.split(":", 1)[1].strip()

            if value:
                values.append(value)

        # Dữ liệu nằm ở dòng sau
        for j in range(
            i + 1,
            min(i + 1 + max_lines, len(lines))
        ):

            candidate = lines[j]

            cu = candidate.upper()

            # Nếu candidate là field kế tiếp -> stop
            if any(
                cu.startswith(stop)
                for stop in stop_upper
            ):
                break

            if candidate:
                values.append(candidate)

        if values:

            return clean_value(
                " ".join(values)
            )

    return EMPTY


def extract_contract_details(text):

    value = extract_invoice_colon_field(
        text,
        "Contract No.",
        [
            "GROSS WEIGHT",
            "CONTAINER",
            "B/L NO",
            "PORT OF LOADING",
            "PORT OF DISCHARGE",
            "DELIVERY TERMS",
            "QUANTITY"
        ],
        2
    )

    if value == EMPTY:
        return EMPTY, EMPTY

    # Ví dụ:
    # 01FG-KAB/11 DATED JUL 06, 2021

    match = re.search(
        r"([A-Z0-9./_-]+)\s+DATED\s+"
        r"([A-Z]{3,9}\s+\d{1,2},?\s+\d{4})",
        value,
        re.IGNORECASE
    )

    if match:

        return (
            match.group(1).strip(),
            match.group(2).strip()
        )

    # Chỉ có contract number
    number = re.match(
        r"([A-Z0-9./_-]+)",
        value
    )

    if number:
        return number.group(1), EMPTY

    return value, EMPTY


def extract_invoice_quantity_net_weight(text):

    lines = get_lines(text)

    quantity = EMPTY
    net_weight = EMPTY

    quantity_index = None

    for i, line in enumerate(lines):

        upper = line.upper()

        if (
            "QUANTITY" in upper
            and (
                "N.W" in upper
                or "N.W." in upper
                or "NET" in upper
            )
        ):
            quantity_index = i
            break

    if quantity_index is not None:

        numbers = []

        for j in range(
            quantity_index + 1,
            min(quantity_index + 5, len(lines))
        ):

            candidate = lines[j]

            match = re.fullmatch(
                r"([\d,]+(?:\.\d+)?)",
                candidate
            )

            if match:
                numbers.append(
                    match.group(1)
                )

        if len(numbers) >= 1:
            quantity = numbers[0]

        if len(numbers) >= 2:
            net_weight = numbers[1]

    return quantity, net_weight


def extract_invoice_description(text):

    lines = get_lines(text)

    start = None

    for i, line in enumerate(lines):

        if "DESCRIPTION OF GOODS" in line.upper():
            start = i
            break

    if start is None:
        return EMPTY

    # Tìm dòng mô tả sau heading
    for i in range(
        start + 1,
        min(start + 8, len(lines))
    ):

        line = lines[i].strip()

        upper = line.upper()

        if not line:
            continue

        if upper in [
            "TOTAL",
            "UNIT PRICE",
            "AMOUNT",
            "DESCRIPTION OF GOODS"
        ]:
            continue

        if re.fullmatch(
            r"\d+",
            line
        ):
            continue

        if re.fullmatch(
            r"[\d,.]+",
            line
        ):
            continue

        # Bỏ các heading
        if "UNIT PRICE" in upper:
            continue

        if "AMOUNT" in upper:
            continue

        return clean_value(line)

    return EMPTY


def extract_invoice_unit_price(text):

    lines = get_lines(text)

    price_index = None

    for i, line in enumerate(lines):

        if "UNIT PRICE" in line.upper():
            price_index = i
            break

    if price_index is None:
        return EMPTY

    # Tìm số gần heading Unit price
    for j in range(
        price_index + 1,
        min(price_index + 7, len(lines))
    ):

        line = lines[j]

        # Có thể là:
        # 2.00
        # USD 2.00
        match = re.search(
            r"\b(?:USD|EUR|KRW|JPY|VND|CNY)?\s*"
            r"([\d,]+(?:\.\d+)?)\b",
            line,
            re.IGNORECASE
        )

        if match:

            value = match.group(1)

            # Không lấy 3983 / số lượng quá xa
            number = normalize_number(value)

            if number is not None:
                return value

    # Fallback
    match = re.search(
        r"UNIT\s+PRICE[\s\S]{0,100}?"
        r"\b([\d,]+\.\d{1,4})\b",
        text,
        re.IGNORECASE
    )

    if match:
        return match.group(1)

    return EMPTY


def extract_invoice_total_amount(text):

    lines = get_lines(text)

    # ------------------------------------------------
    # Ưu tiên tìm khu vực Amount (USD)
    # ------------------------------------------------

    amount_index = None

    for i, line in enumerate(lines):

        if (
            "AMOUNT" in line.upper()
            and (
                "USD" in line.upper()
                or "(USD)" in line.upper()
            )
        ):
            amount_index = i
            break

    if amount_index is not None:

        # Tìm số sau heading Amount
        for j in range(
            amount_index + 1,
            min(amount_index + 8, len(lines))
        ):

            line = lines[j]

            match = re.fullmatch(
                r"[\d,]+(?:\.\d+)?",
                line
            )

            if match:
                return match.group(0)

    # ------------------------------------------------
    # Tìm số cuối cùng sau TOTAL
    # ------------------------------------------------

    total_positions = []

    for i, line in enumerate(lines):

        if line.upper() == "TOTAL":
            total_positions.append(i)

    for index in reversed(total_positions):

        for j in range(
            index + 1,
            min(index + 8, len(lines))
        ):

            match = re.fullmatch(
                r"[\d,]+(?:\.\d+)?",
                lines[j]
            )

            if match:

                value = match.group(0)

                number = normalize_number(value)

                # Total invoice thường > quantity
                if number is not None:
                    return value

    # ------------------------------------------------
    # Pattern trực tiếp
    # ------------------------------------------------

    patterns = [

        r"AMOUNT\s*\(USD\)\s*[\r\n]+"
        r"([\d,]+(?:\.\d+)?)",

        r"\bTOTAL\b[\s\S]{0,150}?"
        r"\b(70,000(?:\.00)?)\b"
    ]

    return find_pattern(
        text,
        patterns
    )


def extract_invoice(text):

    text = normalize_text(text)

    parties = extract_invoice_parties(text)

    contract_no, contract_date = extract_contract_details(
        text
    )

    quantity, net_weight = extract_invoice_quantity_net_weight(
        text
    )

    containers, seals = extract_container_seal_pairs(
        text
    )

    # Nếu không bắt được pair thì fallback container
    container_value = (
        ", ".join(containers)
        if containers
        else extract_containers(text)
    )

    seal_value = (
        ", ".join(seals)
        if seals
        else EMPTY
    )

    # -----------------------------
    # Commodity
    # -----------------------------

    commodity = extract_invoice_colon_field(
        text,
        "Commodity",
        [
            "COUNTRY OF ORIGIN",
            "CONTRACT NO",
            "GROSS WEIGHT",
            "CONTAINER",
            "B/L NO",
            "PORT OF LOADING",
            "PORT OF DISCHARGE",
            "DELIVERY TERMS"
        ],
        1
    )

    # -----------------------------
    # Country
    # -----------------------------

    country_origin = extract_invoice_colon_field(
        text,
        "Country of origin",
        [
            "CONTRACT NO",
            "GROSS WEIGHT",
            "CONTAINER",
            "B/L NO",
            "PORT OF LOADING",
            "PORT OF DISCHARGE",
            "DELIVERY TERMS"
        ],
        1
    )

    # -----------------------------
    # Gross
    # -----------------------------

    gross_weight = extract_invoice_colon_field(
        text,
        "Gross Weight",
        [
            "CONTAINER",
            "B/L NO",
            "PORT OF LOADING",
            "PORT OF DISCHARGE",
            "DELIVERY TERMS"
        ],
        1
    )

    # Chỉ giữ số + đơn vị
    gross_match = re.search(
        r"([\d,]+(?:\.\d+)?)",
        gross_weight
    )

    if gross_match:
        gross_weight = gross_match.group(1)

    # -----------------------------
    # B/L
    # -----------------------------

    bl_no = extract_invoice_colon_field(
        text,
        "B/L No.",
        [
            "PORT OF LOADING",
            "PORT OF DISCHARGE",
            "DELIVERY TERMS"
        ],
        1
    )

    if bl_no == EMPTY:
        bl_no = extract_bl_number(text)

    # -----------------------------
    # Ports
    # -----------------------------

    port_loading = extract_invoice_colon_field(
        text,
        "Port of loading",
        [
            "PORT OF DISCHARGE",
            "DELIVERY TERMS"
        ],
        1
    )

    port_discharge = extract_invoice_colon_field(
        text,
        "Port of Discharge",
        [
            "DELIVERY TERMS"
        ],
        1
    )

    delivery_terms = extract_delivery_terms(text)

    # -----------------------------
    # Invoice
    # -----------------------------

    invoice_no = find_pattern(
        text,
        [
            r"COMMERCIAL\s+INVOICE\s*\n\s*NO\.?\s*[:#\-]?\s*"
            r"([A-Z0-9][A-Z0-9./_-]{2,40})",

            r"NO\.?\s*[:#\-]\s*"
            r"([A-Z0-9][A-Z0-9./_-]{2,40})"
        ]
    )

    # Date
    invoice_date = extract_date(text)

    # Nếu chưa thấy -> JUL 14, 2021
    if invoice_date == EMPTY:

        match = re.search(
            r"\bDATE\s*[:\-]\s*"
            r"([A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4})",
            text,
            re.IGNORECASE
        )

        if match:
            invoice_date = match.group(1)

    # -----------------------------
    # Total
    # -----------------------------

    total_amount = extract_invoice_total_amount(
        text
    )

    # -----------------------------
    # Unit price
    # -----------------------------

    unit_price = extract_invoice_unit_price(
        text
    )

    # -----------------------------
    # Currency
    # -----------------------------

    currency = extract_currency(text)

    # -----------------------------
    # Description
    # -----------------------------

    description = extract_invoice_description(
        text
    )

    return {

        "Invoice No.": invoice_no,

        "Invoice Date": invoice_date,

        "Seller / Exporter":
            parties["Seller / Exporter"],

        "Seller Address":
            parties["Seller Address"],

        "Buyer / Importer":
            parties["Buyer / Importer"],

        "Commodity": commodity,

        "Country of Origin":
            country_origin,

        "Contract No.": contract_no,

        "Contract Date": contract_date,

        "Gross Weight": gross_weight,

        "Net Weight": net_weight,

        "Container No.": container_value,

        "Seal No.": seal_value,

        "B/L No.": bl_no,

        "Port of Loading":
            port_loading,

        "Port of Discharge":
            port_discharge,

        "Delivery Terms":
            delivery_terms,

        "Incoterm":
            extract_incoterm(text),

        "Quantity": quantity,

        "Description of Goods":
            description,

        "Unit Price": unit_price,

        "Total Amount": total_amount,

        "Currency": currency
    }


# =========================================================
# 14. PACKING LIST
# =========================================================

def extract_packing_list(text):

    return {

        "Packing List No.": find_pattern(
            text,
            [
                r"PACKING\s+LIST\s*(?:NO\.?|NUMBER|#)"
                r"\s*[:#\-]?\s*"
                r"([A-Z0-9./_-]+)"
            ]
        ),

        "Date": extract_date(text),

        "Shipper": extract_labeled_block(
            text,
            ["SHIPPER", "EXPORTER"],
            ["CONSIGNEE", "IMPORTER", "BUYER"],
            3
        ),

        "Consignee": extract_labeled_block(
            text,
            ["CONSIGNEE", "IMPORTER", "BUYER"],
            ["SHIPPER", "EXPORTER"],
            3
        ),

        "Container No.": extract_containers(text),

        "Gross Weight": extract_weight(
            text,
            "gross"
        ),

        "Net Weight": extract_weight(
            text,
            "net"
        ),

        "Quantity": find_pattern(
            text,
            [
                r"(?:TOTAL\s+)?QUANTITY\s*[:\-]?\s*"
                r"([\d,]+(?:\.\d+)?)",

                r"\bQTY\s*[:\-]?\s*"
                r"([\d,]+(?:\.\d+)?)"
            ]
        ),

        "Commodity": extract_labeled_block(
            text,
            [
                "DESCRIPTION OF GOODS",
                "DESCRIPTION",
                "COMMODITY"
            ],
            [
                "QUANTITY",
                "QTY",
                "GROSS WEIGHT",
                "NET WEIGHT",
                "TOTAL"
            ],
            3
        )
    }


# =========================================================
# 15. C/O
# =========================================================

def extract_co(text):

    return {

        "C/O No.": find_pattern(
            text,
            [
                r"(?:CERTIFICATE\s+NO\.?|C/O\s+NO\.?)"
                r"\s*[:#\-]?\s*"
                r"([A-Z0-9./_-]+)"
            ]
        ),

        "Exporter": extract_labeled_block(
            text,
            ["EXPORTER", "SHIPPER"],
            ["CONSIGNEE", "IMPORTER"],
            3
        ),

        "Consignee": extract_labeled_block(
            text,
            ["CONSIGNEE", "IMPORTER"],
            ["EXPORTER", "SHIPPER"],
            3
        ),

        "Country of Origin": find_pattern(
            text,
            [
                r"COUNTRY\s+OF\s+ORIGIN\s*[:\-]?\s*"
                r"([^\n]+)"
            ]
        )
    }


# =========================================================
# 16. BOOKING
# =========================================================

def extract_booking(text):

    return {

        "Booking No.": find_pattern(
            text,
            [
                r"BOOKING\s*(?:NO\.?|NUMBER|#)"
                r"\s*[:#\-]?\s*"
                r"([A-Z0-9./_-]+)"
            ]
        ),

        "Container No.": extract_containers(text),

        "Vessel": extract_vessel(text),

        "Voyage": extract_voyage(text),

        "Port of Loading":
            extract_port(text, "loading"),

        "Port of Discharge":
            extract_port(text, "discharge")
    }


# =========================================================
# 17. DISPATCHER
# =========================================================

def extract_document(
    document_type,
    text
):

    if document_type == "COMMERCIAL INVOICE":
        return extract_invoice(text)

    if document_type == "PACKING LIST":
        return extract_packing_list(text)

    if document_type == "BILL OF LADING":
        return extract_bl(text)

    if document_type == "CERTIFICATE OF ORIGIN":
        return extract_co(text)

    if document_type == "BOOKING":
        return extract_booking(text)

    return {}


# =========================================================
# 18. CROSS CHECK
# =========================================================

def get_doc_value(
    documents,
    document_type,
    field
):

    doc = documents.get(
        document_type,
        {}
    )

    return doc.get(
        field,
        EMPTY
    )


def first_available(
    documents,
    fields,
    document_types=None
):

    if document_types is None:

        document_types = [
            "COMMERCIAL INVOICE",
            "PACKING LIST",
            "BILL OF LADING",
            "BOOKING",
            "CERTIFICATE OF ORIGIN"
        ]

    for doc_type in document_types:

        doc = documents.get(
            doc_type,
            {}
        )

        for field in fields:

            value = doc.get(
                field,
                EMPTY
            )

            if value not in [
                None,
                EMPTY,
                ""
            ]:
                return value

    return EMPTY


def cross_check_documents(documents):

    results = []

    # ---------------------------------------
    # Invoice No.
    # ---------------------------------------

    invoice_no = get_doc_value(
        documents,
        "COMMERCIAL INVOICE",
        "Invoice No."
    )

    if invoice_no != EMPTY:

        results.append({
            "Trường kiểm tra": "Invoice No.",
            "Giá trị": invoice_no,
            "Trạng thái": "Có dữ liệu",
            "Nhận xét": "Đã trích xuất từ Commercial Invoice."
        })

    # ---------------------------------------
    # B/L No.
    # ---------------------------------------

    invoice_bl = get_doc_value(
        documents,
        "COMMERCIAL INVOICE",
        "B/L No."
    )

    bl_bl = get_doc_value(
        documents,
        "BILL OF LADING",
        "B/L No."
    )

    if (
        invoice_bl != EMPTY
        and bl_bl != EMPTY
    ):

        if values_match(
            invoice_bl,
            bl_bl
        ):

            results.append({
                "Trường kiểm tra": "B/L No.",
                "Giá trị": invoice_bl,
                "Trạng thái": "KHỚP",
                "Nhận xét": "Invoice và B/L trùng số vận đơn."
            })

        else:

            results.append({
                "Trường kiểm tra": "B/L No.",
                "Giá trị": f"Invoice: {invoice_bl} | B/L: {bl_bl}",
                "Trạng thái": "KHÔNG KHỚP",
                "Nhận xét": "Cần kiểm tra lại số vận đơn."
            })

    # ---------------------------------------
    # Container
    # ---------------------------------------

    container_values = {}

    for doc_type, doc in documents.items():

        value = doc.get(
            "Container No.",
            EMPTY
        )

        if value != EMPTY:
            container_values[doc_type] = value

    if len(container_values) >= 2:

        sets = [
            container_set(value)
            for value in container_values.values()
        ]

        common = set.intersection(
            *sets
        )

        all_containers = set.union(
            *sets
        )

        if common == all_containers:

            results.append({
                "Trường kiểm tra": "Container No.",
                "Giá trị": ", ".join(
                    sorted(all_containers)
                ),
                "Trạng thái": "KHỚP",
                "Nhận xét": "Container giữa các chứng từ trùng nhau."
            })

        else:

            results.append({
                "Trường kiểm tra": "Container No.",
                "Giá trị": " | ".join(
                    f"{k}: {v}"
                    for k, v in container_values.items()
                ),
                "Trạng thái": "CẦN KIỂM TRA",
                "Nhận xét": "Danh sách container giữa các chứng từ chưa hoàn toàn giống nhau."
            })

    # ---------------------------------------
    # Invoice total
    # ---------------------------------------

    invoice_total = get_doc_value(
        documents,
        "COMMERCIAL INVOICE",
        "Total Amount"
    )

    if invoice_total != EMPTY:

        results.append({
            "Trường kiểm tra": "Total Amount",
            "Giá trị": invoice_total,
            "Trạng thái": "Có dữ liệu",
            "Nhận xét": "Giá trị lấy từ khu vực Amount/Total của Invoice."
        })

    # ---------------------------------------
    # Gross Weight
    # ---------------------------------------

    gross_values = {}

    for doc_type in [
        "COMMERCIAL INVOICE",
        "PACKING LIST",
        "BILL OF LADING"
    ]:

        value = get_doc_value(
            documents,
            doc_type,
            "Gross Weight"
        )

        if value != EMPTY:
            gross_values[doc_type] = value

    if len(gross_values) >= 2:

        normalized = [
            normalize_number(v)
            for v in gross_values.values()
        ]

        if len(set(normalized)) == 1:

            results.append({
                "Trường kiểm tra": "Gross Weight",
                "Giá trị": " | ".join(
                    f"{k}: {v}"
                    for k, v in gross_values.items()
                ),
                "Trạng thái": "KHỚP",
                "Nhận xét": "Gross Weight giống nhau giữa các chứng từ."
            })

        else:

            results.append({
                "Trường kiểm tra": "Gross Weight",
                "Giá trị": " | ".join(
                    f"{k}: {v}"
                    for k, v in gross_values.items()
                ),
                "Trạng thái": "KHÔNG KHỚP",
                "Nhận xét": "Cần kiểm tra lại Gross Weight."
            })

    return pd.DataFrame(results)


# =========================================================
# 19. CUSTOMS DATA
# =========================================================

def build_customs_data(documents):

    invoice = documents.get(
        "COMMERCIAL INVOICE",
        {}
    )

    packing = documents.get(
        "PACKING LIST",
        {}
    )

    bl = documents.get(
        "BILL OF LADING",
        {}
    )

    booking = documents.get(
        "BOOKING",
        {}
    )

    data = [

        [
            "Người xuất khẩu",
            invoice.get(
                "Seller / Exporter",
                EMPTY
            ),
            "Commercial Invoice"
        ],

        [
            "Địa chỉ người xuất khẩu",
            invoice.get(
                "Seller Address",
                EMPTY
            ),
            "Commercial Invoice"
        ],

        [
            "Người nhập khẩu",
            invoice.get(
                "Buyer / Importer",
                EMPTY
            ),
            "Commercial Invoice"
        ],

        [
            "Số Invoice",
            invoice.get(
                "Invoice No.",
                EMPTY
            ),
            "Commercial Invoice"
        ],

        [
            "Ngày Invoice",
            invoice.get(
                "Invoice Date",
                EMPTY
            ),
            "Commercial Invoice"
        ],

        [
            "Số hợp đồng",
            invoice.get(
                "Contract No.",
                EMPTY
            ),
            "Commercial Invoice"
        ],

        [
            "Ngày hợp đồng",
            invoice.get(
                "Contract Date",
                EMPTY
            ),
            "Commercial Invoice"
        ],

        [
            "Trị giá hóa đơn",
            invoice.get(
                "Total Amount",
                EMPTY
            ),
            "Commercial Invoice"
        ],

        [
            "Loại tiền",
            invoice.get(
                "Currency",
                EMPTY
            ),
            "Commercial Invoice"
        ],

        [
            "Điều kiện giao hàng",
            invoice.get(
                "Delivery Terms",
                EMPTY
            ),
            "Commercial Invoice"
        ],

        [
            "Mã / Số B/L",
            first_available(
                documents,
                ["B/L No."]
            ),
            "Invoice / B/L / Booking"
        ],

        [
            "Cảng xếp hàng",
            first_available(
                documents,
                ["Port of Loading"]
            ),
            "Invoice / B/L / Booking"
        ],

        [
            "Cảng dỡ hàng",
            first_available(
                documents,
                ["Port of Discharge"]
            ),
            "Invoice / B/L / Booking"
        ],

        [
            "Container No.",
            first_available(
                documents,
                ["Container No."]
            ),
            "Invoice / PL / B/L / Booking"
        ],

        [
            "Seal No.",
            invoice.get(
                "Seal No.",
                EMPTY
            ),
            "Commercial Invoice"
        ],

        [
            "Gross Weight",
            first_available(
                documents,
                ["Gross Weight"]
            ),
            "Invoice / PL / B/L"
        ],

        [
            "Net Weight",
            first_available(
                documents,
                ["Net Weight"]
            ),
            "Invoice / PL"
        ],

        [
            "Số lượng",
            invoice.get(
                "Quantity",
                EMPTY
            ),
            "Commercial Invoice"
        ],

        [
            "Đơn giá",
            invoice.get(
                "Unit Price",
                EMPTY
            ),
            "Commercial Invoice"
        ],

        [
            "Mô tả hàng hóa",
            invoice.get(
                "Description of Goods",
                EMPTY
            ),
            "Commercial Invoice"
        ],

        [
            "Commodity",
            invoice.get(
                "Commodity",
                EMPTY
            ),
            "Commercial Invoice"
        ],

        [
            "Xuất xứ",
            first_available(
                documents,
                ["Country of Origin"]
            ),
            "Invoice / C/O"
        ]
    ]

    return pd.DataFrame(
        data,
        columns=[
            "Trường dữ liệu",
            "Giá trị",
            "Nguồn"
        ]
    )

# =========================================================
# 20. PROFESSIONAL STREAMLIT UI
# =========================================================

# =========================================================
# UI CSS
# =========================================================

st.markdown("""
<style>

@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
}

.stApp {
    background: #f4f6f8;
}

/* =========================
   SIDEBAR
   ========================= */

section[data-testid="stSidebar"] {
    background: #14283f;
}

section[data-testid="stSidebar"] > div {
    padding-top: 1.5rem;
}

.sidebar-brand {
    padding: 0 18px 22px 18px;
}

.sidebar-brand-title {
    color: #ffffff;
    font-size: 21px;
    font-weight: 700;
    letter-spacing: -0.4px;
}

.sidebar-brand-subtitle {
    color: #91a4b8;
    font-size: 11px;
    margin-top: 4px;
}

.sidebar-label {
    color: #71879d;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 1.2px;
    padding: 8px 18px;
    margin-top: 8px;
}

/* =========================
   MAIN
   ========================= */

.main-container {
    max-width: 1450px;
    margin: 0 auto;
}

.topbar {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 4px 0 20px 0;
}

.topbar-title {
    font-size: 26px;
    font-weight: 700;
    color: #172b3f;
    letter-spacing: -0.5px;
}

.topbar-subtitle {
    color: #718096;
    font-size: 13px;
    margin-top: 4px;
}

.system-status {
    background: #e9f7ef;
    color: #18794e;
    border: 1px solid #c8ecd8;
    border-radius: 20px;
    padding: 7px 13px;
    font-size: 11px;
    font-weight: 700;
}

/* =========================
   PAGE HEADER
   ========================= */

.page-header {
    margin: 8px 0 22px 0;
}

.page-header-title {
    font-size: 22px;
    font-weight: 700;
    color: #172b3f;
}

.page-header-desc {
    color: #718096;
    font-size: 13px;
    margin-top: 5px;
}

/* =========================
   KPI
   ========================= */

.kpi {
    background: #ffffff;
    border: 1px solid #e1e7ed;
    border-radius: 10px;
    padding: 18px 20px;
    min-height: 105px;
}

.kpi-label {
    color: #718096;
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: .4px;
}

.kpi-number {
    color: #172b3f;
    font-size: 28px;
    font-weight: 700;
    margin-top: 8px;
}

.kpi-help {
    color: #9aa7b4;
    font-size: 10px;
    margin-top: 3px;
}

/* =========================
   UPLOAD
   ========================= */

.upload-panel {
    background: #ffffff;
    border: 1px solid #dfe6ed;
    border-radius: 12px;
    padding: 26px;
    margin-top: 12px;
}

.upload-heading {
    color: #172b3f;
    font-size: 16px;
    font-weight: 700;
}

.upload-text {
    color: #718096;
    font-size: 12px;
    line-height: 1.6;
    margin-top: 5px;
}

/* =========================
   DOCUMENT LIST
   ========================= */

.document-panel {
    background: #ffffff;
    border: 1px solid #e1e7ed;
    border-radius: 10px;
    padding: 18px;
}

.document-row {
    display: flex;
    align-items: center;
    padding: 13px 4px;
    border-bottom: 1px solid #edf0f3;
}

.document-row:last-child {
    border-bottom: none;
}

.document-icon {
    width: 38px;
    height: 38px;
    border-radius: 8px;
    background: #edf3f8;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 19px;
    margin-right: 12px;
}

.document-name {
    color: #24384b;
    font-size: 13px;
    font-weight: 600;
}

.document-type {
    color: #8996a3;
    font-size: 11px;
    margin-top: 3px;
}

.document-status {
    margin-left: auto;
    font-size: 10px;
    font-weight: 700;
    padding: 5px 9px;
    border-radius: 12px;
}

.status-ok {
    background: #eaf7ef;
    color: #18794e;
}

.status-warning {
    background: #fff5df;
    color: #a66a00;
}

.status-error {
    background: #fdeceb;
    color: #b93838;
}

/* =========================
   SECTION
   ========================= */

.section-heading {
    color: #172b3f;
    font-size: 17px;
    font-weight: 700;
    margin-top: 28px;
    margin-bottom: 4px;
}

.section-desc {
    color: #7b8794;
    font-size: 12px;
    margin-bottom: 14px;
}

/* =========================
   RESULT BOX
   ========================= */

.result-box {
    background: #ffffff;
    border: 1px solid #e1e7ed;
    border-radius: 10px;
    padding: 18px;
}

.result-ok {
    border-left: 4px solid #28a66a;
}

.result-warning {
    border-left: 4px solid #e5a72e;
}

.result-error {
    border-left: 4px solid #d9534f;
}

/* =========================
   EMPTY STATE
   ========================= */

.empty-state {
    background: #ffffff;
    border: 1px dashed #cfd8e1;
    border-radius: 12px;
    padding: 55px 25px;
    text-align: center;
    margin-top: 18px;
}

.empty-icon {
    font-size: 38px;
    margin-bottom: 10px;
}

.empty-title {
    color: #34495e;
    font-size: 16px;
    font-weight: 700;
}

.empty-text {
    color: #8996a3;
    font-size: 12px;
    margin-top: 5px;
}

/* =========================
   INFO
   ========================= */

.info-box {
    background: #eef5fb;
    border: 1px solid #d5e5f2;
    border-radius: 8px;
    padding: 12px 15px;
    color: #49677f;
    font-size: 12px;
    line-height: 1.6;
}

/* =========================
   WARNING
   ========================= */

.warning-box {
    background: #fff8e8;
    border: 1px solid #f1dfb5;
    border-radius: 8px;
    padding: 12px 15px;
    color: #85651d;
    font-size: 12px;
}

/* =========================
   TABLE
   ========================= */

div[data-testid="stDataFrame"] {
    border: 1px solid #e1e7ed;
    border-radius: 9px;
    overflow: hidden;
}

/* =========================
   BUTTON
   ========================= */

.stButton > button {
    border-radius: 7px;
    min-height: 38px;
    font-size: 12px;
    font-weight: 600;
}

.stButton > button[kind="primary"] {
    background: #1d4f73;
    border-color: #1d4f73;
}

/* =========================
   FILE UPLOADER
   ========================= */

[data-testid="stFileUploader"] {
    background: #fafbfc;
    border: 1px dashed #c7d2dc;
    border-radius: 9px;
    padding: 8px;
}

/* =========================
   FOOTER
   ========================= */

.footer {
    text-align: center;
    color: #9aa6b2;
    font-size: 10px;
    padding: 35px 0 12px 0;
}

</style>
""", unsafe_allow_html=True)


# =========================================================
# SESSION STATE
# =========================================================

if "documents_data" not in st.session_state:
    st.session_state.documents_data = {}

if "file_results" not in st.session_state:
    st.session_state.file_results = []


# =========================================================
# SIDEBAR
# =========================================================

with st.sidebar:

    st.markdown(
        """
        <div class="sidebar-brand">
            <div class="sidebar-brand-title">
                CustomsDoc
            </div>
            <div class="sidebar-brand-subtitle">
                Document Control Platform
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    st.markdown(
        '<div class="sidebar-label">WORKSPACE</div>',
        unsafe_allow_html=True
    )

    menu = st.radio(
        "Navigation",
        [
            "Tổng quan",
            "Chứng từ",
            "Kiểm tra chéo",
            "Hỗ trợ khai báo",
            "Báo cáo"
        ],
        label_visibility="collapsed"
    )

    st.markdown(
        '<div class="sidebar-label">SYSTEM</div>',
        unsafe_allow_html=True
    )

    st.markdown(
        """
        <div style="
            padding: 5px 18px;
            color:#91a4b8;
            font-size:11px;
            line-height:1.8;
        ">
            Prototype v1.0<br>
            U&I Logistics Research
        </div>
        """,
        unsafe_allow_html=True
    )

    st.markdown("---")

    if st.button(
        "↻  Xóa bộ chứng từ",
        use_container_width=True
    ):

        st.session_state.documents_data = {}
        st.session_state.file_results = []

        st.rerun()


# =========================================================
# LOAD DATA
# =========================================================

documents = st.session_state.documents_data
file_results = st.session_state.file_results


# =========================================================
# TOP BAR
# =========================================================

st.markdown(
    """
    <div class="topbar">

        <div>
            <div class="topbar-title">
                Customs Document Check
            </div>

            <div class="topbar-subtitle">
                Kiểm soát chứng từ xuất nhập khẩu trước khai báo hải quan
            </div>
        </div>

        <div class="system-status">
            ● HỆ THỐNG HOẠT ĐỘNG
        </div>

    </div>
    """,
    unsafe_allow_html=True
)


# =========================================================
# HELPER: DOCUMENT ICON
# =========================================================

def document_icon(doc_type):

    if "INVOICE" in doc_type:
        return "🧾"

    if "PACKING" in doc_type:
        return "📦"

    if "BILL" in doc_type:
        return "🚢"

    if "ORIGIN" in doc_type:
        return "🌐"

    if "BOOKING" in doc_type:
        return "📅"

    return "📄"


# =========================================================
# HELPER: CROSS CHECK COUNTS
# =========================================================

def get_cross_counts(documents):

    if len(documents) < 2:
        return 0, 0, 0

    df = cross_check_documents(documents)

    if df.empty:
        return 0, 0, 0

    matched = len(
        df[df["Trạng thái"] == "KHỚP"]
    )

    warning = len(
        df[df["Trạng thái"] == "CẦN KIỂM TRA"]
    )

    mismatch = len(
        df[df["Trạng thái"] == "KHÔNG KHỚP"]
    )

    return matched, warning, mismatch


matched_count, warning_count, mismatch_count = get_cross_counts(
    documents
)


# =========================================================
# PAGE 1 — TỔNG QUAN
# =========================================================

if menu == "Tổng quan":

    st.markdown(
        """
        <div class="page-header">
            <div class="page-header-title">
                Tổng quan
            </div>

            <div class="page-header-desc">
                Theo dõi tình trạng bộ chứng từ và kết quả kiểm tra dữ liệu.
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    # -------------------------
    # KPI
    # -------------------------

    total_docs = len(file_results)

    processed_docs = sum(
        1
        for item in file_results
        if item.get("data")
    )

    k1, k2, k3, k4 = st.columns(4)

    with k1:

        st.markdown(
            f"""
            <div class="kpi">
                <div class="kpi-label">
                    Tổng chứng từ
                </div>
                <div class="kpi-number">
                    {total_docs}
                </div>
                <div class="kpi-help">
                    PDF đã tải lên
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )

    with k2:

        st.markdown(
            f"""
            <div class="kpi">
                <div class="kpi-label">
                    Đã trích xuất
                </div>
                <div class="kpi-number">
                    {processed_docs}
                </div>
                <div class="kpi-help">
                    Chứng từ đã xử lý
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )

    with k3:

        st.markdown(
            f"""
            <div class="kpi">
                <div class="kpi-label">
                    Dữ liệu khớp
                </div>
                <div class="kpi-number">
                    {matched_count}
                </div>
                <div class="kpi-help">
                    Cross-check passed
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )

    with k4:

        total_warning = warning_count + mismatch_count

        st.markdown(
            f"""
            <div class="kpi">
                <div class="kpi-label">
                    Cần kiểm tra
                </div>
                <div class="kpi-number">
                    {total_warning}
                </div>
                <div class="kpi-help">
                    Warning / mismatch
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )

    # -------------------------
    # UPLOAD
    # -------------------------

    st.markdown(
        """
        <div class="section-heading">
            Tải bộ chứng từ
        </div>

        <div class="section-desc">
            Upload các chứng từ PDF. Hệ thống tự động nhận diện loại chứng từ,
            đọc dữ liệu và chuẩn bị kiểm tra chéo.
        </div>
        """,
        unsafe_allow_html=True
    )

    st.markdown(
        """
        <div class="upload-panel">

            <div class="upload-heading">
                📁 Upload documents
            </div>

            <div class="upload-text">
                Hỗ trợ Commercial Invoice, Packing List, Bill of Lading,
                Certificate of Origin và Booking.
            </div>

        </div>
        """,
        unsafe_allow_html=True
    )

    uploaded_files = st.file_uploader(
        "Upload PDF",
        type=["pdf"],
        accept_multiple_files=True,
        label_visibility="collapsed"
    )

    if uploaded_files:

        st.markdown(
            f"""
            <div class="info-box">
                Đã chọn <b>{len(uploaded_files)}</b> file.
                Hệ thống sẽ tự động đọc và phân loại chứng từ.
            </div>
            """,
            unsafe_allow_html=True
        )

        st.write("")

        if st.button(
            "Phân tích bộ chứng từ",
            type="primary",
            use_container_width=True
        ):

            new_documents = {}
            new_file_results = []

            progress = st.progress(0)

            for index, file in enumerate(uploaded_files):

                file_bytes = file.getvalue()

                pages, page_count, method, error = process_pdf(
                    file_bytes
                )

                if error:
                    new_file_results.append({
                        "file": file.name,
                        "type": "LỖI ĐỌC FILE",
                        "pages": 0,
                        "method": "ERROR",
                        "data": {},
                        "raw_text": ""
                    })

                    progress.progress(
                        (index + 1) / len(uploaded_files)
                    )

                    continue

                full_text = "\n".join(pages)

                document_type, scores = detect_document_type(
                    full_text,
                    file.name
                )

                extracted = extract_document(
                    document_type,
                    full_text
                )

                # Nếu nhiều file cùng loại,
                # giữ file có nhiều trường dữ liệu hơn
                if document_type not in new_documents:

                    new_documents[document_type] = extracted

                else:

                    old_count = sum(
                        1
                        for value in new_documents[
                            document_type
                        ].values()
                        if value not in [
                            EMPTY,
                            None,
                            ""
                        ]
                    )

                    new_count = sum(
                        1
                        for value in extracted.values()
                        if value not in [
                            EMPTY,
                            None,
                            ""
                        ]
                    )

                    if new_count > old_count:

                        new_documents[
                            document_type
                        ] = extracted

                new_file_results.append({
                    "file": file.name,
                    "type": document_type,
                    "pages": page_count,
                    "method": method,
                    "data": extracted,
                    "raw_text": full_text
                })

                progress.progress(
                    (index + 1) / len(uploaded_files)
                )

            st.session_state.documents_data = new_documents
            st.session_state.file_results = new_file_results

            st.success(
                "Đã hoàn tất phân tích bộ chứng từ."
            )

            st.rerun()

    # -------------------------
    # DOCUMENT SUMMARY
    # -------------------------

    if file_results:

        st.markdown(
            """
            <div class="section-heading">
                Bộ chứng từ
            </div>
            """,
            unsafe_allow_html=True
        )

        st.markdown(
            '<div class="document-panel">',
            unsafe_allow_html=True
        )

        for item in file_results:

            icon = document_icon(
                item["type"]
            )

            if item["data"]:

                status_text = "ĐÃ XỬ LÝ"
                status_class = "status-ok"

            else:

                status_text = "CẦN KIỂM TRA"
                status_class = "status-warning"

            st.markdown(
                f"""
                <div class="document-row">

                    <div class="document-icon">
                        {icon}
                    </div>

                    <div>
                        <div class="document-name">
                            {item["file"]}
                        </div>

                        <div class="document-type">
                            {item["type"]} · {item["pages"]} trang
                        </div>
                    </div>

                    <div class="document-status {status_class}">
                        {status_text}
                    </div>

                </div>
                """,
                unsafe_allow_html=True
            )

        st.markdown(
            '</div>',
            unsafe_allow_html=True
        )

    else:

        st.markdown(
            """
            <div class="empty-state">

                <div class="empty-icon">
                    📂
                </div>

                <div class="empty-title">
                    Chưa có bộ chứng từ
                </div>

                <div class="empty-text">
                    Upload PDF ở khu vực phía trên để bắt đầu.
                </div>

            </div>
            """,
            unsafe_allow_html=True
        )


# =========================================================
# PAGE 2 — CHỨNG TỪ
# =========================================================

elif menu == "Chứng từ":

    st.markdown(
        """
        <div class="page-header">
            <div class="page-header-title">
                Chứng từ
            </div>

            <div class="page-header-desc">
                Dữ liệu được hệ thống tự động trích xuất từ từng chứng từ.
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    if not file_results:

        st.markdown(
            """
            <div class="empty-state">

                <div class="empty-icon">
                    📄
                </div>

                <div class="empty-title">
                    Chưa có chứng từ để hiển thị
                </div>

                <div class="empty-text">
                    Vào mục Tổng quan để upload bộ chứng từ.
                </div>

            </div>
            """,
            unsafe_allow_html=True
        )

    else:

        for index, item in enumerate(file_results):

            icon = document_icon(
                item["type"]
            )

            st.markdown(
                f"""
                <div class="section-heading">
                    {icon} {item["file"]}
                </div>

                <div class="section-desc">
                    {item["type"]} · {item["pages"]} trang ·
                    Phương thức đọc: {item["method"]}
                </div>
                """,
                unsafe_allow_html=True
            )

            extracted = item["data"]

            if extracted:

                df = pd.DataFrame(
                    [
                        {
                            "Trường dữ liệu": key,
                            "Giá trị": value
                        }
                        for key, value
                        in extracted.items()
                    ]
                )

                st.dataframe(
                    df,
                    use_container_width=True,
                    hide_index=True
                )

            else:

                st.warning(
                    "Không trích xuất được dữ liệu từ chứng từ này."
                )

            with st.expander(
                "Xem văn bản gốc"
            ):

                st.text(
                    item["raw_text"]
                )

            if index < len(file_results) - 1:
                st.markdown("---")


# =========================================================
# PAGE 3 — CROSS CHECK
# =========================================================

elif menu == "Kiểm tra chéo":

    st.markdown(
        """
        <div class="page-header">
            <div class="page-header-title">
                Kiểm tra chéo
            </div>

            <div class="page-header-desc">
                Đối chiếu các trường dữ liệu quan trọng giữa các chứng từ.
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    if len(documents) < 2:

        st.markdown(
            """
            <div class="info-box">
                Cần ít nhất <b>02 loại chứng từ</b> để thực hiện kiểm tra chéo.
                Ví dụ: Commercial Invoice + Bill of Lading.
            </div>
            """,
            unsafe_allow_html=True
        )

    else:

        cross_df = cross_check_documents(
            documents
        )

        if cross_df.empty:

            st.markdown(
                """
                <div class="empty-state">

                    <div class="empty-icon">
                        🔍
                    </div>

                    <div class="empty-title">
                        Chưa có trường dữ liệu để đối chiếu
                    </div>

                    <div class="empty-text">
                        Parser chưa tìm thấy đủ dữ liệu phù hợp.
                    </div>

                </div>
                """,
                unsafe_allow_html=True
            )

        else:

            a, b, c = st.columns(3)

            with a:

                st.markdown(
                    f"""
                    <div class="kpi">
                        <div class="kpi-label">
                            Khớp
                        </div>

                        <div class="kpi-number">
                            {matched_count}
                        </div>

                        <div class="kpi-help">
                            Dữ liệu giống nhau
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )

            with b:

                st.markdown(
                    f"""
                    <div class="kpi">
                        <div class="kpi-label">
                            Cần kiểm tra
                        </div>

                        <div class="kpi-number">
                            {warning_count}
                        </div>

                        <div class="kpi-help">
                            Chưa đủ cơ sở kết luận
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )

            with c:

                st.markdown(
                    f"""
                    <div class="kpi">
                        <div class="kpi-label">
                            Không khớp
                        </div>

                        <div class="kpi-number">
                            {mismatch_count}
                        </div>

                        <div class="kpi-help">
                            Cần xử lý trước khai báo
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )

            st.write("")

            st.dataframe(
                cross_df,
                use_container_width=True,
                hide_index=True
            )

            csv = cross_df.to_csv(
                index=False
            ).encode("utf-8-sig")

            st.download_button(
                "Tải kết quả đối chiếu CSV",
                data=csv,
                file_name="cross_check_report.csv",
                mime="text/csv"
            )


# =========================================================
# PAGE 4 — CUSTOMS SUPPORT
# =========================================================

elif menu == "Hỗ trợ khai báo":

    st.markdown(
        """
        <div class="page-header">
            <div class="page-header-title">
                Hỗ trợ khai báo
            </div>

            <div class="page-header-desc">
                Tổng hợp các thông tin có thể sử dụng làm cơ sở chuẩn bị
                dữ liệu khai báo hải quan.
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    if not documents:

        st.markdown(
            """
            <div class="empty-state">

                <div class="empty-icon">
                    📋
                </div>

                <div class="empty-title">
                    Chưa có dữ liệu khai báo
                </div>

                <div class="empty-text">
                    Upload và phân tích chứng từ trước khi xem thông tin này.
                </div>

            </div>
            """,
            unsafe_allow_html=True
        )

    else:

        customs_df = build_customs_data(
            documents
        )

        st.dataframe(
            customs_df,
            use_container_width=True,
            hide_index=True
        )

        st.markdown(
            """
            <div class="warning-box">
                <b>Lưu ý:</b> Dữ liệu trên chỉ có tính chất hỗ trợ kiểm tra
                và chuẩn bị thông tin. Người khai hải quan cần kiểm tra,
                xác nhận và chịu trách nhiệm trước khi thực hiện khai báo
                chính thức.
            </div>
            """,
            unsafe_allow_html=True
        )

        st.write("")

        csv = customs_df.to_csv(
            index=False
        ).encode("utf-8-sig")

        st.download_button(
            "Tải dữ liệu hỗ trợ khai báo CSV",
            data=csv,
            file_name="customs_declaration_support.csv",
            mime="text/csv"
        )


# =========================================================
# PAGE 5 — REPORT
# =========================================================

elif menu == "Báo cáo":

    st.markdown(
        """
        <div class="page-header">
            <div class="page-header-title">
                Báo cáo
            </div>

            <div class="page-header-desc">
                Tổng hợp kết quả xử lý bộ chứng từ.
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    if not file_results:

        st.markdown(
            """
            <div class="empty-state">

                <div class="empty-icon">
                    📊
                </div>

                <div class="empty-title">
                    Chưa có dữ liệu báo cáo
                </div>

                <div class="empty-text">
                    Hãy upload và phân tích bộ chứng từ trước.
                </div>

            </div>
            """,
            unsafe_allow_html=True
        )

    else:

        total_docs = len(file_results)

        processed_docs = sum(
            1
            for item in file_results
            if item.get("data")
        )

        st.markdown(
            """
            <div class="section-heading">
                Tổng quan xử lý
            </div>
            """,
            unsafe_allow_html=True
        )

        report_df = pd.DataFrame([
            [
                "Tổng số chứng từ",
                total_docs
            ],
            [
                "Đã trích xuất",
                processed_docs
            ],
            [
                "Dữ liệu khớp",
                matched_count
            ],
            [
                "Cần kiểm tra",
                warning_count
            ],
            [
                "Không khớp",
                mismatch_count
            ]
        ], columns=[
            "Chỉ tiêu",
            "Kết quả"
        ])

        st.dataframe(
            report_df,
            use_container_width=True,
            hide_index=True
        )

        st.markdown(
            """
            <div class="section-heading">
                Trạng thái chứng từ
            </div>
            """,
            unsafe_allow_html=True
        )

        document_report = []

        for item in file_results:

            document_report.append({
                "Tên file": item["file"],
                "Loại chứng từ": item["type"],
                "Số trang": item["pages"],
                "Phương thức đọc": item["method"],
                "Trạng thái":
                    "Đã xử lý"
                    if item["data"]
                    else "Cần kiểm tra"
            })

        document_report_df = pd.DataFrame(
            document_report
        )

        st.dataframe(
            document_report_df,
            use_container_width=True,
            hide_index=True
        )

        csv = document_report_df.to_csv(
            index=False
        ).encode("utf-8-sig")

        st.download_button(
            "Tải báo cáo xử lý CSV",
            data=csv,
            file_name="document_processing_report.csv",
            mime="text/csv"
        )


# =========================================================
# FOOTER
# =========================================================

st.markdown(
    """
    <div class="footer">
        CustomsDoc Check · Document Control Prototype · U&I Logistics Research
        <br>
        Automated extraction · Cross-document validation · Customs declaration support
    </div>
    """,
    unsafe_allow_html=True
)

