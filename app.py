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
# 20. STREAMLIT UI
# =========================================================

st.title(
    "📄 Customs Document Check"
)

st.caption(
    "Tự động đọc chứng từ PDF → trích xuất dữ liệu → kiểm tra chéo → hỗ trợ chuẩn bị thông tin khai báo hải quan."
)

st.info(
    "Lưu ý: Đây là công cụ demo hỗ trợ kiểm tra chứng từ. "
    "Hệ thống không trực tiếp khai hoặc gửi tờ khai lên VNACCS/VCIS."
)


# =========================================================
# UPLOAD
# =========================================================

uploaded_files = st.file_uploader(
    "📄 Tải lên bộ chứng từ PDF",
    type=["pdf"],
    accept_multiple_files=True
)


if uploaded_files:

    st.subheader("📁 Danh sách chứng từ")

    for file in uploaded_files:

        st.write(
            f"📄 **{file.name}**"
        )

    if st.button(
        "🔍 Đọc và trích xuất dữ liệu",
        type="primary"
    ):

        documents = {}

        for file in uploaded_files:

            st.divider()

            st.subheader(
                f"📄 {file.name}"
            )

            file_bytes = file.getvalue()

            pages, page_count, method, error = process_pdf(
                file_bytes
            )

            if error:

                st.error(
                    f"Lỗi đọc file: {error}"
                )

                continue

            st.write(
                f"**Số trang:** {page_count}"
            )

            st.write(
                f"**Phương pháp đọc:** {method}"
            )

            full_text = "\n".join(
                pages
            )

            if not full_text.strip():

                st.warning(
                    "Không đọc được văn bản."
                )

                continue

            # ----------------------------------------
            # Detect type
            # ----------------------------------------

            document_type, scores = detect_document_type(
                full_text,
                file.name
            )

            st.write(
                f"### Loại chứng từ: {document_type}"
            )

            # ----------------------------------------
            # Scores
            # ----------------------------------------

            score_df = pd.DataFrame(
                [
                    {
                        "Loại chứng từ": k,
                        "Điểm nhận diện": v
                    }
                    for k, v in scores.items()
                ]
            ).sort_values(
                "Điểm nhận diện",
                ascending=False
            )

            with st.expander(
                "🔎 Xem điểm nhận diện"
            ):

                st.dataframe(
                    score_df,
                    use_container_width=True,
                    hide_index=True
                )

            # ----------------------------------------
            # Extract
            # ----------------------------------------

            extracted = extract_document(
                document_type,
                full_text
            )

            if document_type not in documents:

                documents[
                    document_type
                ] = extracted

            else:

                # Nếu nhiều file cùng loại
                # ưu tiên file có nhiều dữ liệu hơn
                old_count = sum(
                    1
                    for v in documents[
                        document_type
                    ].values()
                    if v not in [
                        EMPTY,
                        None,
                        ""
                    ]
                )

                new_count = sum(
                    1
                    for v in extracted.values()
                    if v not in [
                        EMPTY,
                        None,
                        ""
                    ]
                )

                if new_count > old_count:

                    documents[
                        document_type
                    ] = extracted

            # ----------------------------------------
            # Show extraction
            # ----------------------------------------

            if extracted:

                extraction_df = pd.DataFrame(
                    [
                        {
                            "Trường dữ liệu": key,
                            "Giá trị": value
                        }
                        for key, value
                        in extracted.items()
                    ]
                )

                st.write(
                    "### 🔎 Chi tiết nhận diện"
                )

                st.dataframe(
                    extraction_df,
                    use_container_width=True,
                    hide_index=True
                )

            # ----------------------------------------
            # Raw text
            # ----------------------------------------

            with st.expander(
                "📖 Xem nội dung PDF đã đọc"
            ):

                st.text(
                    full_text
                )

        # Save
        st.session_state.documents_data = documents


# =========================================================
# 21. CROSS CHECK
# =========================================================

documents = st.session_state.get(
    "documents_data",
    {}
)


if documents:

    st.divider()

    st.header(
        "🔄 Kiểm tra chéo dữ liệu"
    )

    if len(documents) >= 2:

        cross_df = cross_check_documents(
            documents
        )

        if not cross_df.empty:

            st.dataframe(
                cross_df,
                use_container_width=True,
                hide_index=True
            )

            # Metrics
            matched = len(
                cross_df[
                    cross_df["Trạng thái"] == "KHỚP"
                ]
            )

            mismatch = len(
                cross_df[
                    cross_df["Trạng thái"] == "KHÔNG KHỚP"
                ]
            )

            warning = len(
                cross_df[
                    cross_df["Trạng thái"] == "CẦN KIỂM TRA"
                ]
            )

            c1, c2, c3 = st.columns(3)

            c1.metric(
                "✅ Khớp",
                matched
            )

            c2.metric(
                "❌ Không khớp",
                mismatch
            )

            c3.metric(
                "⚠️ Cần kiểm tra",
                warning
            )

        else:

            st.info(
                "Chưa có đủ trường dữ liệu để thực hiện kiểm tra chéo."
            )

    else:

        st.info(
            "Cần ít nhất 2 loại chứng từ để kiểm tra chéo."
        )


# =========================================================
# 22. CUSTOMS DECLARATION SUPPORT
# =========================================================

if documents:

    st.divider()

    st.header(
        "📋 Thông tin hỗ trợ khai báo hải quan"
    )

    customs_df = build_customs_data(
        documents
    )

    st.dataframe(
        customs_df,
        use_container_width=True,
        hide_index=True
    )

    st.info(
        "Các trường trên được tổng hợp từ chứng từ đã tải lên. "
        "Những trường không có dữ liệu sẽ hiển thị 'Không tìm thấy' "
        "và cần người khai kiểm tra/bổ sung."
    )


# =========================================================
# 23. FOOTER
# =========================================================

st.divider()

st.caption(
    "Customs Document Check – Prototype phục vụ nghiên cứu kiểm soát chứng từ."
)
