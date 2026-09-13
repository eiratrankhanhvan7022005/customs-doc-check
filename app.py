import streamlit as st
from pypdf import PdfReader
import pytesseract
from pdf2image import convert_from_bytes
import pandas as pd
import re


# =========================================================
# CẤU HÌNH
# =========================================================

st.set_page_config(
    page_title="CustomsDoc Check",
    page_icon="📋",
    layout="wide"
)

st.title("📋 CustomsDoc Check")
st.subheader("Kiểm soát chứng từ phục vụ khai báo hải quan")

st.write(
    "Hệ thống tự động đọc PDF, OCR tài liệu scan, "
    "nhận diện loại chứng từ, trích xuất dữ liệu "
    "và kiểm tra chéo thông tin giữa các chứng từ."
)

st.divider()


# =========================================================
# GIÁ TRỊ RỖNG
# =========================================================

EMPTY = "Không tìm thấy"


# =========================================================
# ĐỌC PDF
# =========================================================

def read_pdf_text(file_bytes):

    try:

        reader = PdfReader(file_bytes)

        pages = []

        for page in reader.pages:

            page_text = page.extract_text() or ""

            pages.append(page_text)

        return pages, len(reader.pages)

    except Exception:

        return [], 0


# =========================================================
# OCR
# =========================================================

def ocr_pdf(file_bytes):

    images = convert_from_bytes(
        file_bytes,
        dpi=200
    )

    pages = []

    for i, image in enumerate(images):

        try:

            page_text = pytesseract.image_to_string(
                image,
                lang="eng+vie"
            )

        except Exception:

            page_text = pytesseract.image_to_string(
                image,
                lang="eng"
            )

        pages.append(page_text)

    return pages, len(images)


# =========================================================
# XỬ LÝ PDF TEXT + OCR
# =========================================================

def process_pdf(file_bytes):

    pdf_pages, page_count = read_pdf_text(
        file_bytes
    )

    if not pdf_pages:

        return [], 0, "Không đọc được PDF"

    final_pages = []

    need_ocr = False

    for page in pdf_pages:

        if page and page.strip():

            final_pages.append(page)

        else:

            final_pages.append(None)

            need_ocr = True

    # Nếu có trang scan → OCR toàn bộ PDF
    if need_ocr:

        try:

            ocr_pages, _ = ocr_pdf(
                file_bytes
            )

            for i in range(len(final_pages)):

                if not final_pages[i]:

                    if i < len(ocr_pages):

                        final_pages[i] = ocr_pages[i]

            method = "PDF Text + OCR"

        except Exception:

            method = "PDF Text"

    else:

        method = "PDF Text"

    final_pages = [
        p if p else ""
        for p in final_pages
    ]

    return final_pages, page_count, method


# =========================================================
# CHUẨN HÓA TEXT
# =========================================================

def normalize_text(text):

    if not text:

        return ""

    text = text.replace("\xa0", " ")

    text = text.replace("–", "-")
    text = text.replace("—", "-")
    text = text.replace("−", "-")

    # OCR đôi khi tạo CR
    text = text.replace("\r", "\n")

    # Chuẩn hóa khoảng trắng ngang
    text = re.sub(
        r"[ \t]+",
        " ",
        text
    )

    # Chuẩn hóa quá nhiều dòng trống
    text = re.sub(
        r"\n\s*\n+",
        "\n",
        text
    )

    return text.strip()


# =========================================================
# CHUẨN HÓA GIÁ TRỊ
# =========================================================

def clean_value(value):

    if value is None:

        return None

    value = str(value)

    value = value.strip()

    value = re.sub(
        r"\s+",
        " ",
        value
    )

    value = value.strip(
        " :-|"
    )

    if not value:

        return None

    return value


# =========================================================
# LẤY DÒNG
# =========================================================

def get_lines(text):

    lines = []

    for line in text.splitlines():

        line = clean_value(line)

        if line:

            lines.append(line)

    return lines


# =========================================================
# REGEX CƠ BẢN
# =========================================================

def find_pattern(text, patterns):

    for pattern in patterns:

        try:

            match = re.search(
                pattern,
                text,
                re.IGNORECASE | re.MULTILINE
            )

        except Exception:

            continue

        if match:

            value = clean_value(
                match.group(1)
            )

            if value:

                return value

    return None


# =========================================================
# TÌM NHIỀU GIÁ TRỊ
# =========================================================

def find_all_patterns(text, patterns):

    results = []

    for pattern in patterns:

        try:

            matches = re.findall(
                pattern,
                text,
                re.IGNORECASE | re.MULTILINE
            )

        except Exception:

            continue

        for match in matches:

            if isinstance(match, tuple):

                value = match[0]

            else:

                value = match

            value = clean_value(value)

            if value and value not in results:

                results.append(value)

    return results


# =========================================================
# CHUẨN HÓA SỐ
# =========================================================

def normalize_number(value):

    if not value:

        return None

    value = str(value)

    value = value.replace(",", "")

    value = re.sub(
        r"[^\d.]",
        "",
        value
    )

    return value or None


# =========================================================
# CHUẨN HÓA CONTAINER
# =========================================================

def extract_containers(text):

    text_upper = text.upper()

    # Trường hợp bình thường
    matches = re.findall(
        r"\b[A-Z]{4}\s*\d{7}\b",
        text_upper
    )

    containers = []

    for item in matches:

        item = re.sub(
            r"\s+",
            "",
            item
        )

        if re.fullmatch(
            r"[A-Z]{4}\d{7}",
            item
        ):

            if item not in containers:

                containers.append(item)

    if containers:

        return ", ".join(containers)

    return None


# =========================================================
# VALIDATE CONTAINER
# =========================================================

def is_container(value):

    if not value:

        return False

    value = re.sub(
        r"\s+",
        "",
        value.upper()
    )

    return bool(
        re.fullmatch(
            r"[A-Z]{4}\d{7}",
            value
        )
    )


# =========================================================
# CURRENCY
# =========================================================

def extract_currency(text):

    patterns = [

        (r"\bUSD\b", "USD"),
        (r"\bUS\s+DOLLARS?\b", "USD"),

        (r"\bEUR\b", "EUR"),
        (r"\bEUROS?\b", "EUR"),

        (r"\bKRW\b", "KRW"),
        (r"\bWON\b", "KRW"),

        (r"\bJPY\b", "JPY"),
        (r"\bYEN\b", "JPY"),

        (r"\bVND\b", "VND"),
        (r"\bVIETNAM\s+DONG\b", "VND"),

        (r"\bGBP\b", "GBP"),
        (r"\bPOUNDS?\b", "GBP"),

        (r"\bCNY\b", "CNY"),
        (r"\bRMB\b", "CNY"),
        (r"\bYUAN\b", "CNY")
    ]

    for pattern, currency in patterns:

        if re.search(
            pattern,
            text,
            re.IGNORECASE
        ):

            return currency

    return None


# =========================================================
# INCOTERM
# =========================================================

def extract_incoterm(text):

    pattern = (
        r"\b"
        r"(EXW|FCA|FAS|FOB|CFR|CIF|CPT|CIP|DAP|DPU|DDP)"
        r"\b"
        r"(?:\s+([A-Z][A-Z\s,.-]{2,40}))?"
    )

    matches = re.findall(
        pattern,
        text.upper()
    )

    if not matches:

        return None

    code = matches[0][0]

    return code


# =========================================================
# PHONE
# =========================================================

def extract_phone(text):

    match = re.search(
        r"(?:TEL|PHONE|TELEPHONE|MOBILE)"
        r"\s*[:\-]?\s*"
        r"(\+?\d[\d\s().-]{7,20})",
        text,
        re.IGNORECASE
    )

    if match:

        return clean_value(
            match.group(1)
        )

    return None


# =========================================================
# NHẬN DIỆN CHỨNG TỪ
# =========================================================

def detect_document_type(text):

    text_upper = text.upper()

    scores = {
        "COMMERCIAL INVOICE": 0,
        "BILL OF LADING": 0,
        "PACKING LIST": 0,
        "CERTIFICATE OF ORIGIN": 0
    }

    # -------------------------
    # Invoice
    # -------------------------

    invoice_keywords = [
        "COMMERCIAL INVOICE",
        "PROFORMA INVOICE",
        "INVOICE NO",
        "INVOICE NUMBER",
        "INVOICE DATE",
        "UNIT PRICE",
        "TOTAL AMOUNT",
        "INVOICE VALUE",
        "PAYMENT TERMS",
        "DELIVERY TERMS"
    ]

    for keyword in invoice_keywords:

        if keyword in text_upper:

            scores["COMMERCIAL INVOICE"] += 2

    # -------------------------
    # B/L
    # -------------------------

    bl_keywords = [
        "BILL OF LADING",
        "B/L NO",
        "B/L NUMBER",
        "BILL OF LADING NO",
        "SHIPPER",
        "CONSIGNEE",
        "NOTIFY PARTY",
        "PORT OF LOADING",
        "PORT OF DISCHARGE",
        "VESSEL",
        "VOYAGE",
        "PLACE OF DELIVERY"
    ]

    for keyword in bl_keywords:

        if keyword in text_upper:

            scores["BILL OF LADING"] += 2

    # -------------------------
    # Packing List
    # -------------------------

    pl_keywords = [
        "PACKING LIST",
        "PACKING LIST NO",
        "PACKING NO",
        "P/L NO",
        "NET WEIGHT",
        "GROSS WEIGHT",
        "NO. OF PACKAGES",
        "NUMBER OF PACKAGES",
        "TOTAL PACKAGES",
        "CARTONS",
        "CTNS",
        "PKGS"
    ]

    for keyword in pl_keywords:

        if keyword in text_upper:

            scores["PACKING LIST"] += 2

    # -------------------------
    # C/O
    # -------------------------

    co_keywords = [
        "CERTIFICATE OF ORIGIN",
        "CERTIFICATE OF ORIGIN FORM",
        "ORIGIN CRITERION",
        "ORIGIN CRITERIA",
        "COUNTRY OF ORIGIN",
        "ISSUED IN",
        "EXPORTER",
        "HS CODE"
    ]

    for keyword in co_keywords:

        if keyword in text_upper:

            scores["CERTIFICATE OF ORIGIN"] += 2

    # -------------------------
    # Strong indicators
    # -------------------------

    if re.search(
        r"\bBILL\s+OF\s+LADING\b",
        text_upper
    ):

        scores["BILL OF LADING"] += 10

    if re.search(
        r"\bCOMMERCIAL\s+INVOICE\b",
        text_upper
    ):

        scores["COMMERCIAL INVOICE"] += 10

    if re.search(
        r"\bPACKING\s+LIST\b",
        text_upper
    ):

        scores["PACKING LIST"] += 10

    if re.search(
        r"\bCERTIFICATE\s+OF\s+ORIGIN\b",
        text_upper
    ):

        scores["CERTIFICATE OF ORIGIN"] += 10

    best_type = max(
        scores,
        key=scores.get
    )

    best_score = scores[best_type]

    if best_score == 0:

        return "KHÔNG XÁC ĐỊNH", scores

    return best_type, scores


# =========================================================
# FIELD BLOCK
# =========================================================

def extract_labeled_block(
    text,
    labels,
    stop_labels,
    max_lines=5
):

    lines = get_lines(text)

    label_pattern = (
        r"^\s*(?:"
        + "|".join(labels)
        + r")\s*(?::|-)?\s*(.*)$"
    )

    stop_pattern = (
        r"^\s*(?:"
        + "|".join(stop_labels)
        + r")\s*(?::|-)?"
    )

    for i, line in enumerate(lines):

        match = re.match(
            label_pattern,
            line,
            re.IGNORECASE
        )

        if not match:

            continue

        first_value = clean_value(
            match.group(1)
        )

        values = []

        if first_value:

            values.append(first_value)

        for j in range(
            i + 1,
            min(
                i + 1 + max_lines,
                len(lines)
            )
        ):

            next_line = lines[j]

            if re.match(
                stop_pattern,
                next_line,
                re.IGNORECASE
            ):

                break

            # Không ăn các câu điều khoản rõ ràng
            if re.search(
                r"Combined Transport ONLY|"
                r"This B/L is|"
                r"Unless marked|"
                r"CLAUSES?|"
                r"ENDORSEMENTS?",
                next_line,
                re.IGNORECASE
            ):

                break

            values.append(
                next_line
            )

        if values:

            result = " ".join(values)

            result = clean_value(result)

            if result:

                return result

    return None


# =========================================================
# B/L NUMBER VALIDATION
# =========================================================

def valid_bl_number(value):

    if not value:

        return False

    value = value.strip()

    # Không nhận các câu dài
    if len(value) > 30:

        return False

    # Không nhận text chứa khoảng trắng dài
    if len(value.split()) > 2:

        return False

    # Phải có chữ và số
    if not re.search(
        r"[A-Z]",
        value,
        re.IGNORECASE
    ):

        return False

    if not re.search(
        r"\d",
        value
    ):

        return False

    return bool(
        re.fullmatch(
            r"[A-Z0-9./_-]{5,30}",
            value,
            re.IGNORECASE
        )
    )


# =========================================================
# B/L NUMBER
# =========================================================

def extract_bl_number(text):

    patterns = [

        r"(?:BILL\s+OF\s+LADING)"
        r"\s*(?:NO\.?|NUMBER|#)"
        r"\s*[:#\-]?\s*"
        r"([A-Z0-9][A-Z0-9./_-]{4,29})",

        r"\bB/L"
        r"\s*(?:NO\.?|NUMBER|#)"
        r"\s*[:#\-]?\s*"
        r"([A-Z0-9][A-Z0-9./_-]{4,29})",

        r"\bBL"
        r"\s*(?:NO\.?|NUMBER|#)"
        r"\s*[:#\-]?\s*"
        r"([A-Z0-9][A-Z0-9./_-]{4,29})",

        r"\bBIL"
        r"\s*(?:NO\.?|NUMBER|#)"
        r"\s*[:#\-]?\s*"
        r"([A-Z0-9][A-Z0-9./_-]{4,29})"
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            text,
            re.IGNORECASE
        )

        if match:

            value = clean_value(
                match.group(1)
            )

            if valid_bl_number(value):

                return value.upper()

    # Một số B/L có label và value nằm dòng sau
    lines = get_lines(text)

    for i, line in enumerate(lines):

        if re.search(
            r"\b(?:B/L|BL|BIL)"
            r"\s*(?:NO\.?|NUMBER|#)\b",
            line,
            re.IGNORECASE
        ):

            for candidate in lines[
                i + 1:i + 3
            ]:

                candidate = clean_value(
                    candidate
                )

                if valid_bl_number(
                    candidate
                ):

                    return candidate.upper()

    return None


# =========================================================
# PORT VALIDATION
# =========================================================

def valid_port(value):

    if not value:

        return False

    value = clean_value(value)

    if not value:

        return False

    # Loại câu điều khoản
    forbidden = [
        "COMBINED TRANSPORT",
        "CLAUSES",
        "THIS B/L",
        "UNLESS MARKED",
        "ENDORSEMENTS",
        "CARRIER'S AGENTS"
    ]

    upper = value.upper()

    for word in forbidden:

        if word in upper:

            return False

    if len(value) > 100:

        return False

    return True


# =========================================================
# TÌM PORT
# =========================================================

def extract_port(text, field):

    if field == "loading":

        labels = [
            "PORT OF LOADING",
            "PORT OF SHIPMENT",
            "POL"
        ]

    elif field == "discharge":

        labels = [
            "PORT OF DISCHARGE",
            "POD"
        ]

    else:

        labels = [
            "PLACE OF DELIVERY",
            "FINAL DESTINATION",
            "PLACE OF DELIVERY/DESTINATION"
        ]

    stop_labels = [
        "SHIPPER",
        "CONSIGNEE",
        "NOTIFY PARTY",
        "VESSEL",
        "VOYAGE",
        "PORT OF LOADING",
        "PORT OF DISCHARGE",
        "PLACE OF DELIVERY",
        "CONTAINER",
        "GROSS WEIGHT",
        "NET WEIGHT",
        "B/L NO",
        "B/L NUMBER",
        "MARKS AND NUMBERS",
        "DESCRIPTION"
    ]

    value = extract_labeled_block(
        text,
        labels,
        stop_labels,
        max_lines=2
    )

    if valid_port(value):

        return value

    return None


# =========================================================
# WEIGHT
# =========================================================

def extract_weight(text, weight_type):

    if weight_type == "gross":

        labels = [
            r"GROSS\s+WEIGHT",
            r"GROSS\s+WT",
            r"G\.?\s*W\.?",
            r"G/W"
        ]

    else:

        labels = [
            r"NET\s+WEIGHT",
            r"NET\s+WT",
            r"N\.?\s*W\.?",
            r"N/W"
        ]

    pattern = (
        r"(?:"
        + "|".join(labels)
        + r")"
        r"\s*[:\-]?\s*"
        r"([\d,]+(?:\.\d+)?)"
        r"\s*(?:KG|KGS|KILOGRAMS)?"
    )

    matches = re.findall(
        pattern,
        text,
        re.IGNORECASE
    )

    for value in matches:

        value = clean_value(value)

        number = normalize_number(value)

        if number:

            return value

    return None


# =========================================================
# VESSEL
# =========================================================

def extract_vessel(text):

    labels = [
        "VESSEL",
        "NAME OF VESSEL",
        "OCEAN VESSEL"
    ]

    stop_labels = [
        "VOYAGE",
        "PORT OF LOADING",
        "PORT OF DISCHARGE",
        "PLACE OF DELIVERY",
        "CONSIGNEE",
        "NOTIFY PARTY",
        "SHIPPER",
        "CONTAINER",
        "GROSS WEIGHT",
        "B/L NO"
    ]

    value = extract_labeled_block(
        text,
        labels,
        stop_labels,
        max_lines=1
    )

    if not value:

        return None

    if len(value) > 100:

        return None

    if re.search(
        r"THIS B/L|CLAUSES|COMBINED TRANSPORT",
        value,
        re.IGNORECASE
    ):

        return None

    return value


# =========================================================
# VOYAGE
# =========================================================

def extract_voyage(text):

    return find_pattern(
        text,
        [

            r"VOYAGE\s+(?:NO\.?|NUMBER)"
            r"\s*[:\-]?\s*([A-Z0-9./_-]+)",

            r"\bVOYAGE\b"
            r"\s*[:\-]?\s*([A-Z0-9./_-]+)"
        ]
    )


# =========================================================
# B/L - ĐA TEMPLATE
# =========================================================

def extract_bl(text):

    data = {}

    # -----------------------------------------------------
    # B/L NUMBER
    # -----------------------------------------------------

    data["B/L No."] = extract_bl_number(
        text
    )

    # -----------------------------------------------------
    # SHIPPER
    # -----------------------------------------------------

    shipper_stop = [
        "CONSIGNEE",
        "NOTIFY PARTY",
        "NOTIFY",
        "PRE-CARRIAGE",
        "PLACE OF RECEIPT",
        "PORT OF LOADING",
        "PORT OF DISCHARGE",
        "PLACE OF DELIVERY",
        "VESSEL",
        "VOYAGE",
        "CONTAINER",
        "GROSS WEIGHT",
        "DESCRIPTION",
        "MARKS AND NUMBERS"
    ]

    data["Shipper"] = extract_labeled_block(
        text,
        [
            "SHIPPER",
            "EXPORTER",
            "SHIPPER/EXPORTER"
        ],
        shipper_stop,
        max_lines=5
    )

    # -----------------------------------------------------
    # CONSIGNEE
    # -----------------------------------------------------

    consignee_stop = [
        "NOTIFY PARTY",
        "NOTIFY",
        "SHIPPER",
        "PRE-CARRIAGE",
        "PLACE OF RECEIPT",
        "PORT OF LOADING",
        "PORT OF DISCHARGE",
        "PLACE OF DELIVERY",
        "VESSEL",
        "VOYAGE",
        "CONTAINER",
        "GROSS WEIGHT",
        "DESCRIPTION",
        "MARKS AND NUMBERS"
    ]

    data["Consignee"] = extract_labeled_block(
        text,
        [
            "CONSIGNEE",
            "CONSIGNEE/IMPORTER"
        ],
        consignee_stop,
        max_lines=5
    )

    # -----------------------------------------------------
    # NOTIFY PARTY
    # -----------------------------------------------------

    notify_stop = [
        "SHIPPER",
        "CONSIGNEE",
        "PRE-CARRIAGE",
        "PLACE OF RECEIPT",
        "PORT OF LOADING",
        "PORT OF DISCHARGE",
        "PLACE OF DELIVERY",
        "VESSEL",
        "VOYAGE",
        "CONTAINER",
        "GROSS WEIGHT",
        "DESCRIPTION",
        "MARKS AND NUMBERS",
        "FREIGHT"
    ]

    notify = extract_labeled_block(
        text,
        [
            "NOTIFY PARTY",
            "NOTIFY"
        ],
        notify_stop,
        max_lines=5
    )

    # Không chấp nhận container list làm Notify Party
    if notify:

        if re.fullmatch(
            r"[\s,;A-Z0-9]+",
            notify.upper()
        ):

            containers = extract_containers(
                notify
            )

            if containers:

                notify = None

    if notify and re.search(
        r"COMBINED TRANSPORT|THIS B/L|"
        r"CARRIER'S AGENTS|ENDORSEMENTS",
        notify,
        re.IGNORECASE
    ):

        notify = None

    data["Notify Party"] = notify

    # -----------------------------------------------------
    # CONTAINER
    # -----------------------------------------------------

    data["Container No."] = extract_containers(
        text
    )

    # -----------------------------------------------------
    # GROSS WEIGHT
    # -----------------------------------------------------

    data["Gross Weight"] = extract_weight(
        text,
        "gross"
    )

    # -----------------------------------------------------
    # PORT OF LOADING
    # -----------------------------------------------------

    data["Port of Loading"] = extract_port(
        text,
        "loading"
    )

    # -----------------------------------------------------
    # PORT OF DISCHARGE
    # -----------------------------------------------------

    data["Port of Discharge"] = extract_port(
        text,
        "discharge"
    )

    # -----------------------------------------------------
    # PLACE OF DELIVERY
    # -----------------------------------------------------

    data["Place of Delivery"] = extract_port(
        text,
        "delivery"
    )

    # -----------------------------------------------------
    # VESSEL
    # -----------------------------------------------------

    data["Vessel"] = extract_vessel(
        text
    )

    # -----------------------------------------------------
    # VOYAGE
    # -----------------------------------------------------

    data["Voyage"] = extract_voyage(
        text
    )

    return data


# =========================================================
# INVOICE
# =========================================================

def extract_invoice(text):

    data = {}

    # Invoice No.
    data["Invoice No."] = find_pattern(
        text,
        [

            r"(?:COMMERCIAL\s+INVOICE|PROFORMA\s+INVOICE|INVOICE)"
            r"\s*(?:NO\.?|NUMBER|#)"
            r"\s*[:#\-]?\s*"
            r"([A-Z0-9][A-Z0-9./_-]{2,40})",

            r"\bINV\.?\s*(?:NO\.?|NUMBER|#)"
            r"\s*[:#\-]?\s*"
            r"([A-Z0-9][A-Z0-9./_-]{2,40})"
        ]
    )

    # Date
    data["Invoice Date"] = find_pattern(
        text,
        [

            r"(?:INVOICE\s+DATE|DATE\s+OF\s+ISSUE|ISSUE\s+DATE)"
            r"\s*[:\-]?\s*"
            r"([0-9]{1,2}[-/.][A-Za-z0-9]{1,9}[-/.][0-9]{2,4})",

            r"(?:INVOICE\s+DATE|DATE\s+OF\s+ISSUE|ISSUE\s+DATE)"
            r"\s*[:\-]?\s*"
            r"([A-Za-z]{3,9}\s+[0-9]{1,2},?\s+[0-9]{4})",

            r"\bDATE\s*[:\-]\s*"
            r"([0-9]{1,2}[-/.][0-9]{1,2}[-/.][0-9]{2,4})"
        ]
    )

    # Seller
    data["Seller / Exporter"] = extract_labeled_block(
        text,
        [
            "SELLER",
            "EXPORTER",
            "SUPPLIER",
            "SHIPPER"
        ],
        [
            "BUYER",
            "IMPORTER",
            "BILL TO",
            "CONSIGNEE",
            "INVOICE NO",
            "DATE",
            "DESCRIPTION"
        ],
        max_lines=4
    )

    # Buyer
    data["Buyer / Importer"] = extract_labeled_block(
        text,
        [
            "BUYER",
            "IMPORTER",
            "BILL TO",
            "CONSIGNEE"
        ],
        [
            "SELLER",
            "EXPORTER",
            "SUPPLIER",
            "SHIPPER",
            "INVOICE NO",
            "DATE",
            "DESCRIPTION"
        ],
        max_lines=4
    )

    # Commodity
    data["Commodity"] = extract_labeled_block(
        text,
        [
            "DESCRIPTION OF GOODS",
            "GOODS DESCRIPTION",
            "DESCRIPTION",
            "COMMODITY"
        ],
        [
            "QUANTITY",
            "QTY",
            "UNIT PRICE",
            "PRICE",
            "AMOUNT",
            "TOTAL",
            "NET WEIGHT",
            "GROSS WEIGHT"
        ],
        max_lines=3
    )

    # Origin
    data["Country of Origin"] = find_pattern(
        text,
        [

            r"COUNTRY\s+OF\s+ORIGIN"
            r"\s*[:>\-]\s*([^\n]+)",

            r"MADE\s+IN\s+([A-Z][A-Z ,.-]+)"
        ]
    )

    # Contract
    data["Contract No."] = find_pattern(
        text,
        [
            r"CONTRACT\s+(?:NO\.?|NUMBER)"
            r"\s*[:#\-]?\s*"
            r"([A-Z0-9./_-]+)"
        ]
    )

    # Gross
    data["Gross Weight"] = extract_weight(
        text,
        "gross"
    )

    # Net
    data["Net Weight"] = extract_weight(
        text,
        "net"
    )

    # Container
    data["Container No."] = extract_containers(
        text
    )

    # B/L
    data["B/L No."] = extract_bl_number(
        text
    )

    # Incoterm
    data["Incoterm"] = extract_incoterm(
        text
    )

    # Currency
    data["Currency"] = extract_currency(
        text
    )

    # Quantity
    data["Quantity"] = find_pattern(
        text,
        [
            r"(?:TOTAL\s+)?QUANTITY"
            r"\s*[:\-]?\s*"
            r"([\d,]+(?:\.\d+)?)",

            r"\bQTY"
            r"\s*[:\-]?\s*"
            r"([\d,]+(?:\.\d+)?)"
        ]
    )

    # Unit Price
    data["Unit Price"] = find_pattern(
        text,
        [
            r"(?:UNIT\s+PRICE|UNIT\s+VALUE|PRICE/UNIT|RATE)"
            r"\s*[:\-]?\s*"
            r"(?:USD|EUR|KRW|JPY|VND)?\s*"
            r"([\d,]+(?:\.\d+)?)"
        ]
    )

    # Total Amount
    data["Total Amount"] = find_pattern(
        text,
        [
            r"(?:GRAND\s+TOTAL|TOTAL\s+AMOUNT|INVOICE\s+VALUE)"
            r"\s*[:\-]?\s*"
            r"(?:USD|EUR|KRW|JPY|VND)?\s*"
            r"([\d,]+(?:\.\d+)?)",

            r"\bTOTAL\b"
            r"\s*[:\-]?\s*"
            r"(?:USD|EUR|KRW|JPY|VND)?\s*"
            r"([\d,]+\.\d{2})"
        ]
    )

    # Fallback amount
    if not data["Total Amount"]:

        amounts = find_all_patterns(
            text,
            [
                r"(?:USD|EUR|KRW|JPY|VND)"
                r"\s*([\d,]+\.\d{2})"
            ]
        )

        if amounts:

            data["Total Amount"] = amounts[-1]

    return data


# =========================================================
# PACKING LIST
# =========================================================

def extract_packing_list(text):

    data = {}

    data["Packing List No."] = find_pattern(
        text,
        [

            r"(?:PACKING\s+LIST|PACKING)"
            r"\s*(?:NO\.?|NUMBER)"
            r"\s*[:#\-]?\s*"
            r"([A-Z0-9./_-]+)"
        ]
    )

    data["Net Weight"] = extract_weight(
        text,
        "net"
    )

    data["Gross Weight"] = extract_weight(
        text,
        "gross"
    )

    data["Packages"] = find_pattern(
        text,
        [

            r"(?:TOTAL\s+)?"
            r"(?:NO\.?\s+OF\s+PACKAGES|NUMBER\s+OF\s+PACKAGES|PACKAGES|PKGS)"
            r"\s*[:\-]?\s*(\d+)",

            r"(?:TOTAL\s+)?"
            r"(?:CARTONS|CTNS)"
            r"\s*[:\-]?\s*(\d+)"
        ]
    )

    data["Container No."] = extract_containers(
        text
    )

    data["Description"] = extract_labeled_block(
        text,
        [
            "DESCRIPTION OF GOODS",
            "GOODS DESCRIPTION",
            "DESCRIPTION"
        ],
        [
            "QUANTITY",
            "QTY",
            "NET WEIGHT",
            "GROSS WEIGHT",
            "PACKAGES",
            "PKGS",
            "CONTAINER"
        ],
        max_lines=3
    )

    data["Quantity"] = find_pattern(
        text,
        [
            r"(?:QUANTITY|QTY)"
            r"\s*[:\-]?\s*"
            r"([\d,]+(?:\.\d+)?)"
        ]
    )

    return data


# =========================================================
# C/O
# =========================================================

def extract_co(text):

    data = {}

    data["C/O No."] = find_pattern(
        text,
        [
            r"(?:CERTIFICATE\s+NO|CERTIFICATE\s+NUMBER)"
            r"\s*[:#\-]?\s*"
            r"([A-Z0-9./_-]+)",

            r"(?:C/O|CO)"
            r"\s*(?:NO\.?|NUMBER)"
            r"\s*[:#\-]?\s*"
            r"([A-Z0-9./_-]+)"
        ]
    )

    data["Exporter"] = extract_labeled_block(
        text,
        ["EXPORTER"],
        [
            "IMPORTER",
            "CONSIGNEE",
            "BUYER",
            "COUNTRY OF ORIGIN",
            "DESCRIPTION",
            "HS CODE"
        ],
        max_lines=5
    )

    data["Importer"] = extract_labeled_block(
        text,
        [
            "IMPORTER",
            "CONSIGNEE",
            "BUYER"
        ],
        [
            "EXPORTER",
            "COUNTRY OF ORIGIN",
            "DESCRIPTION",
            "HS CODE"
        ],
        max_lines=5
    )

    data["Origin"] = find_pattern(
        text,
        [
            r"COUNTRY\s+OF\s+ORIGIN"
            r"\s*[:\-]?\s*([^\n]+)",

            r"ORIGIN"
            r"\s*[:\-]\s*([^\n]+)",

            r"MADE\s+IN\s+([A-Z][A-Z ,.-]+)"
        ]
    )

    data["HS Code"] = find_pattern(
        text,
        [
            r"HS\s*(?:CODE|NO\.?|NUMBER)"
            r"\s*[:\-]?\s*(\d{4,10})",

            r"\bHS\s*[:\-]\s*(\d{4,10})"
        ]
    )

    data["Description"] = extract_labeled_block(
        text,
        [
            "DESCRIPTION OF GOODS",
            "GOODS DESCRIPTION",
            "DESCRIPTION"
        ],
        [
            "HS CODE",
            "QUANTITY",
            "QTY",
            "ORIGIN CRITERIA",
            "ORIGIN CRITERION"
        ],
        max_lines=4
    )

    data["Quantity"] = find_pattern(
        text,
        [
            r"(?:QUANTITY|QTY)"
            r"\s*[:\-]?\s*"
            r"([\d,]+(?:\.\d+)?)"
        ]
    )

    return data


# =========================================================
# ĐIỀU PHỐI
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

    return {}


# =========================================================
# CHUẨN HÓA TEXT ĐỂ SO SÁNH
# =========================================================

def normalize_compare(value):

    if not value:

        return ""

    value = str(value).upper()

    value = value.replace(
        "&",
        "AND"
    )

    value = re.sub(
        r"[^A-Z0-9]",
        "",
        value
    )

    return value


# =========================================================
# SO SÁNH TÊN / TEXT
# =========================================================

def values_match(value1, value2):

    if not value1 or not value2:

        return False

    a = normalize_compare(
        value1
    )

    b = normalize_compare(
        value2
    )

    if not a or not b:

        return False

    return (
        a == b
        or a in b
        or b in a
    )


# =========================================================
# TÁCH SỐ CONTAINER
# =========================================================

def container_set(value):

    if not value:

        return set()

    matches = re.findall(
        r"[A-Z]{4}\d{7}",
        value.upper()
    )

    return set(matches)


# =========================================================
# CHECK CHÉO
# =========================================================

def cross_check_documents(documents):

    results = []

    invoice = documents.get(
        "COMMERCIAL INVOICE"
    )

    bl = documents.get(
        "BILL OF LADING"
    )

    pl = documents.get(
        "PACKING LIST"
    )

    co = documents.get(
        "CERTIFICATE OF ORIGIN"
    )

    # -----------------------------------------------------
    # Invoice Seller ↔ B/L Shipper
    # -----------------------------------------------------

    if invoice and bl:

        seller = invoice.get(
            "Seller / Exporter"
        )

        shipper = bl.get(
            "Shipper"
        )

        if seller and shipper:

            if values_match(
                seller,
                shipper
            ):

                results.append([
                    "Seller / Shipper",
                    seller,
                    shipper,
                    "KHỚP"
                ])

            else:

                results.append([
                    "Seller / Shipper",
                    seller,
                    shipper,
                    "KHÔNG KHỚP"
                ])

        else:

            results.append([
                "Seller / Shipper",
                seller or EMPTY,
                shipper or EMPTY,
                "THIẾU DỮ LIỆU"
            ])

    # -----------------------------------------------------
    # Invoice Buyer ↔ B/L Consignee
    # -----------------------------------------------------

    if invoice and bl:

        buyer = invoice.get(
            "Buyer / Importer"
        )

        consignee = bl.get(
            "Consignee"
        )

        if buyer and consignee:

            if values_match(
                buyer,
                consignee
            ):

                results.append([
                    "Buyer / Consignee",
                    buyer,
                    consignee,
                    "KHỚP"
                ])

            else:

                results.append([
                    "Buyer / Consignee",
                    buyer,
                    consignee,
                    "CẦN XÁC NHẬN"
                ])

        else:

            results.append([
                "Buyer / Consignee",
                buyer or EMPTY,
                consignee or EMPTY,
                "THIẾU DỮ LIỆU"
            ])

    # -----------------------------------------------------
    # Container PL ↔ B/L
    # -----------------------------------------------------

    if pl and bl:

        pl_containers = container_set(
            pl.get("Container No.")
        )

        bl_containers = container_set(
            bl.get("Container No.")
        )

        if pl_containers and bl_containers:

            if pl_containers == bl_containers:

                results.append([
                    "Container",
                    ", ".join(
                        sorted(pl_containers)
                    ),
                    ", ".join(
                        sorted(bl_containers)
                    ),
                    "KHỚP"
                ])

            elif pl_containers.intersection(
                bl_containers
            ):

                results.append([
                    "Container",
                    ", ".join(
                        sorted(pl_containers)
                    ),
                    ", ".join(
                        sorted(bl_containers)
                    ),
                    "CẢNH BÁO"
                ])

            else:

                results.append([
                    "Container",
                    ", ".join(
                        sorted(pl_containers)
                    ),
                    ", ".join(
                        sorted(bl_containers)
                    ),
                    "KHÔNG KHỚP"
                ])

        else:

            results.append([
                "Container",
                ", ".join(
                    sorted(pl_containers)
                ) if pl_containers else EMPTY,
                ", ".join(
                    sorted(bl_containers)
                ) if bl_containers else EMPTY,
                "THIẾU DỮ LIỆU"
            ])

    # -----------------------------------------------------
    # Gross Weight PL ↔ B/L
    # -----------------------------------------------------

    if pl and bl:

        pl_gw = pl.get(
            "Gross Weight"
        )

        bl_gw = bl.get(
            "Gross Weight"
        )

        if pl_gw and bl_gw:

            a = normalize_number(
                pl_gw
            )

            b = normalize_number(
                bl_gw
            )

            if a and b:

                if float(a) == float(b):

                    status = "KHỚP"

                else:

                    status = "KHÔNG KHỚP"

                results.append([
                    "Gross Weight",
                    pl_gw,
                    bl_gw,
                    status
                ])

        else:

            results.append([
                "Gross Weight",
                pl_gw or EMPTY,
                bl_gw or EMPTY,
                "THIẾU DỮ LIỆU"
            ])

    # -----------------------------------------------------
    # Invoice B/L No ↔ B/L
    # -----------------------------------------------------

    if invoice and bl:

        inv_bl = invoice.get(
            "B/L No."
        )

        actual_bl = bl.get(
            "B/L No."
        )

        if inv_bl and actual_bl:

            if values_match(
                inv_bl,
                actual_bl
            ):

                status = "KHỚP"

            else:

                status = "KHÔNG KHỚP"

            results.append([
                "B/L No.",
                inv_bl,
                actual_bl,
                status
            ])

    # -----------------------------------------------------
    # Invoice Origin ↔ C/O
    # -----------------------------------------------------

    if invoice and co:

        inv_origin = invoice.get(
            "Country of Origin"
        )

        co_origin = co.get(
            "Origin"
        )

        if inv_origin and co_origin:

            if values_match(
                inv_origin,
                co_origin
            ):

                status = "KHỚP"

            else:

                status = "CẦN XÁC NHẬN"

            results.append([
                "Country of Origin",
                inv_origin,
                co_origin,
                status
            ])

        else:

            results.append([
                "Country of Origin",
                inv_origin or EMPTY,
                co_origin or EMPTY,
                "THIẾU DỮ LIỆU"
            ])

    return results


# =========================================================
# BẢNG THÔNG TIN PHỤC VỤ KHAI BÁO
# =========================================================

def build_customs_data(documents):

    rows = []

    invoice = documents.get(
        "COMMERCIAL INVOICE",
        {}
    )

    pl = documents.get(
        "PACKING LIST",
        {}
    )

    bl = documents.get(
        "BILL OF LADING",
        {}
    )

    co = documents.get(
        "CERTIFICATE OF ORIGIN",
        {}
    )

    fields = [

        (
            "Người xuất khẩu",
            invoice.get(
                "Seller / Exporter"
            ) or bl.get(
                "Shipper"
            ),
            "Invoice / B/L"
        ),

        (
            "Người nhập khẩu",
            invoice.get(
                "Buyer / Importer"
            ) or bl.get(
                "Consignee"
            ),
            "Invoice / B/L"
        ),

        (
            "Số Invoice",
            invoice.get(
                "Invoice No."
            ),
            "Invoice"
        ),

        (
            "Ngày Invoice",
            invoice.get(
                "Invoice Date"
            ),
            "Invoice"
        ),

        (
            "Trị giá hóa đơn",
            invoice.get(
                "Total Amount"
            ),
            "Invoice"
        ),

        (
            "Tiền tệ",
            invoice.get(
                "Currency"
            ),
            "Invoice"
        ),

        (
            "Điều kiện Incoterm",
            invoice.get(
                "Incoterm"
            ),
            "Invoice"
        ),

        (
            "Mô tả hàng hóa",
            invoice.get(
                "Commodity"
            ) or pl.get(
                "Description"
            ) or co.get(
                "Description"
            ),
            "Invoice / PL / C/O"
        ),

        (
            "Số lượng",
            invoice.get(
                "Quantity"
            ) or pl.get(
                "Quantity"
            ),
            "Invoice / PL"
        ),

        (
            "Gross Weight",
            pl.get(
                "Gross Weight"
            ) or bl.get(
                "Gross Weight"
            ),
            "PL / B/L"
        ),

        (
            "Net Weight",
            pl.get(
                "Net Weight"
            ) or invoice.get(
                "Net Weight"
            ),
            "PL / Invoice"
        ),

        (
            "Container No.",
            pl.get(
                "Container No."
            ) or bl.get(
                "Container No."
            ),
            "PL / B/L"
        ),

        (
            "B/L No.",
            bl.get(
                "B/L No."
            ),
            "B/L"
        ),

        (
            "Port of Loading",
            bl.get(
                "Port of Loading"
            ),
            "B/L"
        ),

        (
            "Port of Discharge",
            bl.get(
                "Port of Discharge"
            ),
            "B/L"
        ),

        (
            "Place of Delivery",
            bl.get(
                "Place of Delivery"
            ),
            "B/L"
        ),

        (
            "Vessel",
            bl.get(
                "Vessel"
            ),
            "B/L"
        ),

        (
            "Country of Origin",
            invoice.get(
                "Country of Origin"
            ) or co.get(
                "Origin"
            ),
            "Invoice / C/O"
        ),

        (
            "HS Code",
            co.get(
                "HS Code"
            ),
            "C/O"
        )
    ]

    for field, value, source in fields:

        rows.append([
            field,
            value if value else EMPTY,
            source
        ])

    return pd.DataFrame(
        rows,
        columns=[
            "Thông tin",
            "Giá trị",
            "Nguồn chứng từ"
        ]
    )


# =========================================================
# SCORE
# =========================================================

def display_detection_scores(scores):

    rows = []

    for document_type, score in scores.items():

        rows.append([
            document_type,
            score
        ])

    df = pd.DataFrame(
        rows,
        columns=[
            "Loại chứng từ",
            "Điểm nhận diện"
        ]
    )

    df = df.sort_values(
        "Điểm nhận diện",
        ascending=False
    )

    with st.expander(
        "🔎 Chi tiết nhận diện chứng từ"
    ):

        st.dataframe(
            df,
            use_container_width=True,
            hide_index=True
        )


# =========================================================
# UPLOAD
# =========================================================

uploaded_files = st.file_uploader(
    "📄 Tải lên bộ chứng từ PDF",
    type=["pdf"],
    accept_multiple_files=True
)


# =========================================================
# SESSION DATA
# =========================================================

if "documents_data" not in st.session_state:

    st.session_state.documents_data = {}


# =========================================================
# XỬ LÝ
# =========================================================

if uploaded_files:

    st.success(
        f"Đã tải lên {len(uploaded_files)} chứng từ."
    )

    st.write(
        "### 📁 Danh sách chứng từ"
    )

    for file in uploaded_files:

        st.write(
            f"📄 {file.name}"
        )

    st.divider()

    if st.button(
        "🔍 Đọc và trích xuất dữ liệu",
        type="primary"
    ):

        documents = {}

        for file in uploaded_files:

            st.write(
                f"## 📄 {file.name}"
            )

            file_bytes = file.getvalue()

            # -------------------------------------------------
            # ĐỌC
            # -------------------------------------------------

            pages, page_count, method = process_pdf(
                file_bytes
            )

            text = "\n".join(
                pages
            )

            text = normalize_text(
                text
            )

            st.write(
                f"**Số trang:** {page_count}"
            )

            st.write(
                f"**Phương thức đọc:** {method}"
            )

            if not text:

                st.error(
                    "Không đọc được nội dung tài liệu."
                )

                continue

            st.success(
                "Đọc tài liệu thành công."
            )

            # -------------------------------------------------
            # NHẬN DIỆN
            # -------------------------------------------------

            document_type, scores = detect_document_type(
                text
            )

            st.write(
                f"### 🗂️ Loại chứng từ: "
                f"**{document_type}**"
            )

            display_detection_scores(
                scores
            )

            # -------------------------------------------------
            # TRÍCH XUẤT
            # -------------------------------------------------

            data = extract_document(
                text,
                document_type
            )

            if data:

                documents[
                    document_type
                ] = data

                rows = []

                for field, value in data.items():

                    rows.append([
                        field,
                        value if value else EMPTY
                    ])

                df = pd.DataFrame(
                    rows,
                    columns=[
                        "Trường dữ liệu",
                        "Giá trị"
                    ]
                )

                st.write(
                    "### 📊 Dữ liệu tự động trích xuất"
                )

                st.dataframe(
                    df,
                    use_container_width=True,
                    hide_index=True
                )

            else:

                st.warning(
                    "Chưa trích xuất được dữ liệu."
                )

            # -------------------------------------------------
            # TEXT
            # -------------------------------------------------

            with st.expander(
                "📖 Xem nội dung hệ thống đọc được"
            ):

                st.text_area(
                    "PDF Text / OCR Text",
                    text,
                    height=400,
                    key=f"text_{file.name}"
                )

        # -----------------------------------------------------
        # LƯU
        # -----------------------------------------------------

        st.session_state.documents_data = documents


# =========================================================
# CHECK CHÉO
# =========================================================

documents = st.session_state.documents_data

if documents and len(documents) >= 2:

    st.divider()

    st.header(
        "🔎 Kiểm tra chéo chứng từ"
    )

    check_results = cross_check_documents(
        documents
    )

    if check_results:

        check_df = pd.DataFrame(
            check_results,
            columns=[
                "Chỉ tiêu",
                "Chứng từ 1",
                "Chứng từ 2",
                "Kết quả"
            ]
        )

        st.dataframe(
            check_df,
            use_container_width=True,
            hide_index=True
        )

        # -----------------------------------------------------
        # TÓM TẮT
        # -----------------------------------------------------

        matched = sum(
            1 for row in check_results
            if row[3] == "KHỚP"
        )

        warning = sum(
            1 for row in check_results
            if row[3] in [
                "CẢNH BÁO",
                "CẦN XÁC NHẬN"
            ]
        )

        mismatch = sum(
            1 for row in check_results
            if row[3] == "KHÔNG KHỚP"
        )

        missing = sum(
            1 for row in check_results
            if row[3] == "THIẾU DỮ LIỆU"
        )

        c1, c2, c3, c4 = st.columns(4)

        c1.metric(
            "🟢 Khớp",
            matched
        )

        c2.metric(
            "🟡 Cảnh báo",
            warning
        )

        c3.metric(
            "🔴 Không khớp",
            mismatch
        )

        c4.metric(
            "⚪ Thiếu",
            missing
        )

    else:

        st.info(
            "Chưa có đủ trường dữ liệu để kiểm tra chéo."
        )


# =========================================================
# THÔNG TIN PHỤC VỤ KHAI BÁO
# =========================================================

if documents:

    st.divider()

    st.header(
        "🧾 Thông tin phục vụ khai báo hải quan"
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
        "Bảng này là dữ liệu hỗ trợ chuẩn bị khai báo. "
        "Các trường nghiệp vụ hải quan chuyên biệt như mã loại hình, "
        "mã cơ quan Hải quan, mã bộ phận xử lý, phân luồng... "
        "không được hệ thống tự suy đoán nếu không có nguồn dữ liệu phù hợp."
    )


# =========================================================
# GHI CHÚ HỆ THỐNG
# =========================================================

st.divider()

with st.expander(
    "ℹ️ Lưu ý về hệ thống"
):

    st.write(
        """
        **CustomsDoc Check là công cụ hỗ trợ kiểm soát chứng từ.**

        Hệ thống có chức năng:
        - Đọc PDF
        - OCR tài liệu scan
        - Nhận diện loại chứng từ
        - Trích xuất dữ liệu
        - Chuẩn hóa dữ liệu
        - Kiểm tra chéo thông tin
        - Hỗ trợ chuẩn bị dữ liệu phục vụ khai báo

        Hệ thống không tự động gửi tờ khai lên VNACCS/VCIS
        và không thay thế quyết định kiểm tra của nhân viên nghiệp vụ.
        """
    )
