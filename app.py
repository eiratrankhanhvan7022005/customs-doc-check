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
    "nhận diện loại chứng từ và trích xuất dữ liệu "
    "từ nhiều mẫu chứng từ khác nhau."
)

st.divider()


# =========================================================
# ĐỌC PDF TEXT
# =========================================================

def read_pdf_text(file_bytes):

    try:
        reader = PdfReader(file_bytes)

        text = ""

        for page in reader.pages:

            page_text = page.extract_text() or ""

            text += "\n" + page_text

        return text, len(reader.pages)

    except Exception:

        return "", 0


# =========================================================
# OCR PDF
# =========================================================

def ocr_pdf(file_bytes):

    images = convert_from_bytes(
        file_bytes,
        dpi=200
    )

    text = ""

    for i, image in enumerate(images):

        page_text = pytesseract.image_to_string(
            image,
            lang="eng+vie"
        )

        text += f"\n--- PAGE {i + 1} ---\n"
        text += page_text

    return text, len(images)


# =========================================================
# CHUẨN HÓA TEXT
# =========================================================

def normalize_text(text):

    if not text:
        return ""

    text = text.replace("\xa0", " ")

    # Chuẩn hóa các loại gạch
    text = text.replace("–", "-")
    text = text.replace("—", "-")
    text = text.replace("−", "-")

    # Chuẩn hóa khoảng trắng
    text = re.sub(r"[ \t]+", " ", text)

    # Không xóa xuống dòng vì nhiều chứng từ
    # dựa vào cấu trúc dòng
    text = re.sub(r"\n\s*\n+", "\n", text)

    return text.strip()


# =========================================================
# CHUẨN HÓA CHUỖI
# =========================================================

def clean_value(value):

    if not value:
        return None

    value = value.strip()

    value = re.sub(
        r"\s+",
        " ",
        value
    )

    value = value.strip(" :-|")

    if not value:
        return None

    return value


# =========================================================
# TÌM REGEX
# =========================================================

def find_pattern(text, patterns):

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

    return None


# =========================================================
# TÌM NHIỀU GIÁ TRỊ
# =========================================================

def find_all_patterns(text, patterns):

    results = []

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


# =========================================================
# CHUẨN HÓA SỐ
# =========================================================

def normalize_number(value):

    if not value:
        return None

    value = value.replace(",", "")

    value = re.sub(
        r"[^\d.]",
        "",
        value
    )

    return value or None


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

    # -----------------------------------------------------
    # INVOICE
    # -----------------------------------------------------

    invoice_keywords = [
        "COMMERCIAL INVOICE",
        "PROFORMA INVOICE",
        "INVOICE NO",
        "INVOICE NUMBER",
        "INVOICE DATE",
        "UNIT PRICE",
        "TOTAL AMOUNT",
        "INVOICE VALUE",
        "FOR ACCOUNT AND RISK",
        "DELIVERY TERMS"
    ]

    for keyword in invoice_keywords:

        if keyword in text_upper:
            scores["COMMERCIAL INVOICE"] += 2

    # -----------------------------------------------------
    # B/L
    # -----------------------------------------------------

    bl_keywords = [
        "BILL OF LADING",
        "B/L NO",
        "B/L NUMBER",
        "BL NO",
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

    # -----------------------------------------------------
    # PACKING LIST
    # -----------------------------------------------------

    pl_keywords = [
        "PACKING LIST",
        "PACKING NO",
        "PACKING LIST NO",
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

    # -----------------------------------------------------
    # C/O
    # -----------------------------------------------------

    co_keywords = [
        "CERTIFICATE OF ORIGIN",
        "CERTIFICATE OF ORIGIN FORM",
        "ORIGIN CRITERION",
        "COUNTRY OF ORIGIN",
        "ISSUED IN",
        "EXPORTER",
        "ORIGIN CRITERIA",
        "HS CODE"
    ]

    for keyword in co_keywords:

        if keyword in text_upper:
            scores["CERTIFICATE OF ORIGIN"] += 2

    # -----------------------------------------------------
    # Một số dấu hiệu đặc biệt
    # -----------------------------------------------------

    if re.search(
        r"\bCOMMERCIAL\s+INVOICE\b",
        text_upper
    ):
        scores["COMMERCIAL INVOICE"] += 5

    if re.search(
        r"\bBILL\s+OF\s+LADING\b",
        text_upper
    ):
        scores["BILL OF LADING"] += 5

    if re.search(
        r"\bPACKING\s+LIST\b",
        text_upper
    ):
        scores["PACKING LIST"] += 5

    if re.search(
        r"\bCERTIFICATE\s+OF\s+ORIGIN\b",
        text_upper
    ):
        scores["CERTIFICATE OF ORIGIN"] += 5

    best_type = max(
        scores,
        key=scores.get
    )

    best_score = scores[best_type]

    if best_score == 0:
        return "KHÔNG XÁC ĐỊNH", scores

    return best_type, scores


# =========================================================
# TÌM CONTAINER
# =========================================================

def extract_containers(text):

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

    return None


# =========================================================
# TÌM CURRENCY
# =========================================================

def extract_currency(text):

    patterns = [
        r"\b(USD|US\s*DOLLARS?)\b",
        r"\b(EUR|EURO)\b",
        r"\b(KRW|WON)\b",
        r"\b(JPY|YEN)\b",
        r"\b(VND|VIETNAM\s*DONG)\b",
        r"\b(GBP|POUNDS?)\b",
        r"\b(CNY|RMB|YUAN)\b"
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            text,
            re.IGNORECASE
        )

        if match:

            value = match.group(1).upper()

            if "DOLLAR" in value:
                return "USD"

            if "EURO" in value:
                return "EUR"

            if "WON" in value:
                return "KRW"

            if "YEN" in value:
                return "JPY"

            if "DONG" in value:
                return "VND"

            if "POUND" in value:
                return "GBP"

            if "YUAN" in value:
                return "CNY"

            return value

    return None


# =========================================================
# TÌM INCOTERM
# =========================================================

def extract_incoterm(text):

    pattern = (
        r"\b"
        r"(EXW|FCA|FAS|FOB|CFR|CIF|CPT|CIP|DAP|DPU|DDP)"
        r"\b"
        r"(?:\s+([A-Z][A-Z\s,.-]{2,50}))?"
    )

    matches = re.findall(
        pattern,
        text.upper()
    )

    if not matches:
        return None

    for code, destination in matches:

        result = code

        if destination:

            destination = destination.strip()

            # Không lấy quá nhiều text sau Incoterm
            destination = destination.split("\n")[0]

            if len(destination) <= 40:

                result += " " + destination

        return result.strip()

    return None


# =========================================================
# TÌM SỐ ĐIỆN THOẠI
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
# INVOICE - ĐA MẪU
# =========================================================

def extract_invoice(text):

    data = {}

    # -----------------------------------------------------
    # INVOICE NUMBER
    # -----------------------------------------------------

    data["Invoice No."] = find_pattern(
        text,
        [

            r"(?:INVOICE|COMMERCIAL\s+INVOICE|PROFORMA\s+INVOICE)"
            r"\s*(?:NO\.?|NUMBER|#)"
            r"\s*[:#\-]?\s*([A-Z0-9][A-Z0-9./_-]{2,40})",

            r"(?:INV\.?|INV\s*NO)"
            r"\s*[:#\-]?\s*([A-Z0-9][A-Z0-9./_-]{2,40})",

            r"\bNO\.\s*[:#\-]?\s*([A-Z0-9][A-Z0-9./_-]{2,40})"
        ]
    )

    # -----------------------------------------------------
    # DATE
    # -----------------------------------------------------

    data["Invoice Date"] = find_pattern(
        text,
        [

            r"(?:INVOICE\s+DATE|ISSUE\s+DATE|DATE\s+OF\s+ISSUE)"
            r"\s*[:\-]?\s*"
            r"([0-9]{1,2}[-/.][0-9]{1,2}[-/.][0-9]{2,4})",

            r"(?:INVOICE\s+DATE|ISSUE\s+DATE|DATE\s+OF\s+ISSUE)"
            r"\s*[:\-]?\s*"
            r"([0-9]{1,2}[-/.][A-Za-z]{3,9}[-/.][0-9]{2,4})",

            r"(?:INVOICE\s+DATE|ISSUE\s+DATE|DATE\s+OF\s+ISSUE)"
            r"\s*[:\-]?\s*"
            r"([A-Za-z]{3,9}\s+[0-9]{1,2},?\s+[0-9]{4})",

            r"\bDATE\s*[:\-]\s*"
            r"([A-Za-z]{3,9}\s+[0-9]{1,2},?\s+[0-9]{4})",

            r"\bDATE\s*[:\-]\s*"
            r"([0-9]{1,2}[-/.][0-9]{1,2}[-/.][0-9]{2,4})"
        ]
    )

    # -----------------------------------------------------
    # SELLER / EXPORTER
    # -----------------------------------------------------

    data["Seller / Exporter"] = find_pattern(
        text,
        [

            r"(?:SELLER|EXPORTER|SUPPLIER|FROM)"
            r"\s*[:\-]\s*([^\n]+)",

            r"(?:SELLER|EXPORTER|SUPPLIER)"
            r"\s*\n\s*([^\n]+)",

            r"SHIPPER\s*[:\-]\s*([^\n]+)"
        ]
    )

    # Nếu không có label rõ ràng:
    # tìm dòng công ty chứa LTD / INC / CO.
    if not data["Seller / Exporter"]:

        company_patterns = [
            r"(?m)^\s*([A-Z][A-Z0-9&.,' -]{3,80}"
            r"(?:CO\.?\s*,?\s*LTD\.?|LTD\.?|LIMITED|INC\.?|CORP\.?))\s*$"
        ]

        candidates = find_all_patterns(
            text,
            company_patterns
        )

        if candidates:

            data["Seller / Exporter"] = candidates[0]

    # -----------------------------------------------------
    # BUYER / IMPORTER
    # -----------------------------------------------------

    data["Buyer / Importer"] = find_pattern(
        text,
        [

            r"(?:BUYER|IMPORTER|BUY TO|BILL TO)"
            r"\s*[:\-]\s*([^\n]+)",

            r"(?:BUYER|IMPORTER|BILL TO)"
            r"\s*\n\s*([^\n]+)",

            r"FOR ACCOUNT AND RISK OF\s*[:\-]?\s*([^\n]+)",

            r"CONSIGNEE\s*[:\-]\s*([^\n]+)"
        ]
    )

    # -----------------------------------------------------
    # COMMODITY
    # -----------------------------------------------------

    data["Commodity"] = find_pattern(
        text,
        [
            r"COMMODITY\s*[:\-]\s*([^\n]+)",

            r"DESCRIPTION\s+OF\s+GOODS\s*[:\-]\s*([^\n]+)",

            r"DESCRIPTION\s*[:\-]\s*([^\n]+)",

            r"GOODS\s+DESCRIPTION\s*[:\-]\s*([^\n]+)"
        ]
    )

    # -----------------------------------------------------
    # COUNTRY OF ORIGIN
    # -----------------------------------------------------

    data["Country of Origin"] = find_pattern(
        text,
        [

            r"COUNTRY\s+OF\s+ORIGIN\s*[:>\-]\s*([^\n]+)",

            r"ORIGIN\s*[:\-]\s*([^\n]+)",

            r"MADE\s+IN\s+([A-Z][A-Z ,.-]+)"
        ]
    )

    # -----------------------------------------------------
    # CONTRACT
    # -----------------------------------------------------

    data["Contract No."] = find_pattern(
        text,
        [
            r"CONTRACT\s+(?:NO\.?|NUMBER)"
            r"\s*[:#\-]?\s*([A-Z0-9./_-]+)",

            r"CONTRACT\s*[:#\-]\s*([A-Z0-9./_-]+)"
        ]
    )

    # -----------------------------------------------------
    # GROSS WEIGHT
    # -----------------------------------------------------

    data["Gross Weight"] = find_pattern(
        text,
        [

            r"(?:GROSS\s+WEIGHT|GROSS\s+WT|G\.W\.|G/W)"
            r"\s*[:\-]?\s*"
            r"([\d,]+(?:\.\d+)?)"
            r"\s*(?:KG|KGS|KILOGRAMS)\b",

            r"(?:GROSS\s+WEIGHT|GROSS\s+WT|G\.W\.|G/W)"
            r"\s*[:\-]?\s*"
            r"([\d,]+(?:\.\d+)?)"
        ]
    )

    # -----------------------------------------------------
    # NET WEIGHT
    # -----------------------------------------------------

    data["Net Weight"] = find_pattern(
        text,
        [

            r"(?:NET\s+WEIGHT|NET\s+WT|N\.W\.|N/W)"
            r"\s*[:\-]?\s*"
            r"([\d,]+(?:\.\d+)?)"
            r"\s*(?:KG|KGS|KILOGRAMS)\b",

            r"(?:NET\s+WEIGHT|NET\s+WT|N\.W\.|N/W)"
            r"\s*[:\-]?\s*"
            r"([\d,]+(?:\.\d+)?)"
        ]
    )

    # -----------------------------------------------------
    # CONTAINER
    # -----------------------------------------------------

    data["Container No."] = extract_containers(
        text
    )

    # -----------------------------------------------------
    # B/L
    # -----------------------------------------------------

    data["B/L No."] = find_pattern(
        text,
        [

            r"(?:B/L|BIL|BL|BILL\s+OF\s+LADING)"
            r"\s*(?:NO\.?|NUMBER)"
            r"\s*[:#\-]?\s*([A-Z0-9./_-]+)",

            r"(?:B/L|BL)\s*[:#\-]\s*([A-Z0-9./_-]+)"
        ]
    )

    # -----------------------------------------------------
    # PORT OF LOADING
    # -----------------------------------------------------

    data["Port of Loading"] = find_pattern(
        text,
        [

            r"PORT\s+OF\s+LOADING\s*[:\-]\s*([^\n]+)",

            r"PORT\s+OF\s+SHIPMENT\s*[:\-]\s*([^\n]+)",

            r"\bPOL\s*[:\-]\s*([^\n]+)"
        ]
    )

    # -----------------------------------------------------
    # PORT OF DISCHARGE
    # -----------------------------------------------------

    data["Port of Discharge"] = find_pattern(
        text,
        [

            r"PORT\s+OF\s+DISCHARGE\s*[:\-]\s*([^\n]+)",

            r"\bPOD\s*[:\-]\s*([^\n]+)"
        ]
    )

    # -----------------------------------------------------
    # INCOTERM
    # -----------------------------------------------------

    data["Incoterm"] = extract_incoterm(
        text
    )

    # -----------------------------------------------------
    # CURRENCY
    # -----------------------------------------------------

    data["Currency"] = extract_currency(
        text
    )

    # -----------------------------------------------------
    # QUANTITY
    # -----------------------------------------------------

    data["Quantity"] = find_pattern(
        text,
        [

            r"(?:QUANTITY|QTY)"
            r"\s*[:\-]?\s*"
            r"([\d,]+(?:\.\d+)?)",

            r"TOTAL\s+QUANTITY"
            r"\s*[:\-]?\s*"
            r"([\d,]+(?:\.\d+)?)"
        ]
    )

    # -----------------------------------------------------
    # UNIT PRICE
    # -----------------------------------------------------

    data["Unit Price"] = find_pattern(
        text,
        [

            r"(?:UNIT\s+PRICE|UNIT\s+VALUE|PRICE/UNIT|RATE)"
            r"\s*[:\-]?\s*"
            r"(?:USD|EUR|KRW|JPY|VND)?\s*"
            r"([\d,]+(?:\.\d+)?)"
        ]
    )

    # -----------------------------------------------------
    # TOTAL AMOUNT
    # -----------------------------------------------------

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

    # -----------------------------------------------------
    # FALLBACK TOTAL AMOUNT
    # -----------------------------------------------------

    if not data["Total Amount"]:

        amount_patterns = [
            r"(?:USD|EUR|KRW|JPY|VND)"
            r"\s*([\d,]+\.\d{2})"
        ]

        amounts = find_all_patterns(
            text,
            amount_patterns
        )

        if amounts:

            # Chọn giá trị cuối cùng,
            # thường là tổng tiền
            data["Total Amount"] = amounts[-1]

    # -----------------------------------------------------
    # TOTAL WEIGHT
    # -----------------------------------------------------

    if data["Net Weight"]:

        data["Total Weight"] = data["Net Weight"]

    elif data["Gross Weight"]:

        data["Total Weight"] = data["Gross Weight"]

    else:

        data["Total Weight"] = find_pattern(
            text,
            [
                r"TOTAL\s+WEIGHT"
                r"\s*[:\-]?\s*"
                r"([\d,]+(?:\.\d+)?)"
            ]
        )

    return data


# =========================================================
# BILL OF LADING - ĐA MẪU
# =========================================================

def extract_bl(text):

    data = {}

    data["B/L No."] = find_pattern(
        text,
        [

            r"(?:BILL\s+OF\s+LADING|B/L|BL|BIL)"
            r"\s*(?:NO\.?|NUMBER)"
            r"\s*[:#\-]?\s*([A-Z0-9./_-]+)",

            r"(?:B/L|BL)"
            r"\s*[:#\-]\s*([A-Z0-9./_-]+)"
        ]
    )

    data["Shipper"] = find_pattern(
        text,
        [
            r"SHIPPER\s*[:\-]\s*([^\n]+)",
            r"SHIPPER\s*\n\s*([^\n]+)",
            r"EXPORTER\s*[:\-]\s*([^\n]+)"
        ]
    )

    data["Consignee"] = find_pattern(
        text,
        [
            r"CONSIGNEE\s*[:\-]\s*([^\n]+)",
            r"CONSIGNEE\s*\n\s*([^\n]+)",
            r"IMPORTER\s*[:\-]\s*([^\n]+)"
        ]
    )

    data["Notify Party"] = find_pattern(
        text,
        [
            r"NOTIFY\s+PARTY\s*[:\-]\s*([^\n]+)"
        ]
    )

    data["Container No."] = extract_containers(
        text
    )

    data["Gross Weight"] = find_pattern(
        text,
        [
            r"(?:GROSS\s+WEIGHT|GROSS\s+WT|G\.W\.|G/W)"
            r"\s*[:\-]?\s*"
            r"([\d,]+(?:\.\d+)?)"
            r"\s*(?:KG|KGS)?"
        ]
    )

    data["Port of Loading"] = find_pattern(
        text,
        [
            r"PORT\s+OF\s+LOADING\s*[:\-]\s*([^\n]+)",
            r"\bPOL\s*[:\-]\s*([^\n]+)",
            r"PORT\s+OF\s+SHIPMENT\s*[:\-]\s*([^\n]+)"
        ]
    )

    data["Port of Discharge"] = find_pattern(
        text,
        [
            r"PORT\s+OF\s+DISCHARGE\s*[:\-]\s*([^\n]+)",
            r"\bPOD\s*[:\-]\s*([^\n]+)"
        ]
    )

    data["Place of Delivery"] = find_pattern(
        text,
        [
            r"PLACE\s+OF\s+DELIVERY\s*[:\-]\s*([^\n]+)",
            r"FINAL\s+DESTINATION\s*[:\-]\s*([^\n]+)"
        ]
    )

    data["Vessel"] = find_pattern(
        text,
        [
            r"VESSEL\s*[:\-]\s*([^\n]+)",
            r"NAME\s+OF\s+VESSEL\s*[:\-]\s*([^\n]+)"
        ]
    )

    data["Voyage"] = find_pattern(
        text,
        [
            r"VOYAGE\s*[:\-]\s*([^\n]+)",
            r"VOYAGE\s+NO\.?\s*[:\-]\s*([^\n]+)"
        ]
    )

    return data


# =========================================================
# PACKING LIST - ĐA MẪU
# =========================================================

def extract_packing_list(text):

    data = {}

    data["Packing List No."] = find_pattern(
        text,
        [

            r"(?:PACKING\s+LIST|P/L|PL)"
            r"\s*(?:NO\.?|NUMBER)"
            r"\s*[:#\-]?\s*([A-Z0-9./_-]+)",

            r"(?:PACKING\s+LIST\s+NO|PACKING\s+NO)"
            r"\s*[:#\-]?\s*([A-Z0-9./_-]+)"
        ]
    )

    data["Net Weight"] = find_pattern(
        text,
        [
            r"(?:NET\s+WEIGHT|NET\s+WT|N\.W\.|N/W)"
            r"\s*[:\-]?\s*"
            r"([\d,]+(?:\.\d+)?)"
            r"\s*(?:KG|KGS)?"
        ]
    )

    data["Gross Weight"] = find_pattern(
        text,
        [
            r"(?:GROSS\s+WEIGHT|GROSS\s+WT|G\.W\.|G/W)"
            r"\s*[:\-]?\s*"
            r"([\d,]+(?:\.\d+)?)"
            r"\s*(?:KG|KGS)?"
        ]
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

    data["Description"] = find_pattern(
        text,
        [
            r"DESCRIPTION\s+OF\s+GOODS\s*[:\-]\s*([^\n]+)",
            r"DESCRIPTION\s*[:\-]\s*([^\n]+)"
        ]
    )

    data["Quantity"] = find_pattern(
        text,
        [
            r"(?:QUANTITY|QTY)"
            r"\s*[:\-]?\s*([\d,]+(?:\.\d+)?)"
        ]
    )

    return data


# =========================================================
# C/O - ĐA MẪU
# =========================================================

def extract_co(text):

    data = {}

    data["C/O No."] = find_pattern(
        text,
        [
            r"(?:CERTIFICATE\s+NO|CERTIFICATE\s+NUMBER|C/O\s+NO|CO\s+NO)"
            r"\s*[:#\-]?\s*([A-Z0-9./_-]+)"
        ]
    )

    data["Exporter"] = find_pattern(
        text,
        [
            r"EXPORTER\s*[:\-]\s*([^\n]+)",
            r"EXPORTER\s*\n\s*([^\n]+)"
        ]
    )

    data["Importer"] = find_pattern(
        text,
        [
            r"IMPORTER\s*[:\-]\s*([^\n]+)",
            r"CONSIGNEE\s*[:\-]\s*([^\n]+)",
            r"BUYER\s*[:\-]\s*([^\n]+)"
        ]
    )

    data["Origin"] = find_pattern(
        text,
        [
            r"COUNTRY\s+OF\s+ORIGIN\s*[:\-]\s*([^\n]+)",
            r"ORIGIN\s*[:\-]\s*([^\n]+)",
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

    data["Description"] = find_pattern(
        text,
        [
            r"DESCRIPTION\s+OF\s+GOODS\s*[:\-]\s*([^\n]+)",
            r"DESCRIPTION\s*[:\-]\s*([^\n]+)"
        ]
    )

    data["Quantity"] = find_pattern(
        text,
        [
            r"(?:QUANTITY|QTY)"
            r"\s*[:\-]?\s*([\d,]+(?:\.\d+)?)"
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
# HIỂN THỊ SCORE
# =========================================================

def display_detection_scores(scores):

    rows = []

    for document_type, score in scores.items():

        rows.append(
            [document_type, score]
        )

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
# XỬ LÝ
# =========================================================

if uploaded_files:

    st.success(
        f"Đã tải lên {len(uploaded_files)} chứng từ."
    )

    st.write("### 📁 Danh sách chứng từ")

    for file in uploaded_files:

        st.write(
            f"📄 {file.name}"
        )

    st.divider()

    if st.button(
        "🔍 Đọc và trích xuất dữ liệu",
        type="primary"
    ):

        for file in uploaded_files:

            st.write(
                f"## 📄 {file.name}"
            )

            file_bytes = file.getvalue()

            # =================================================
            # ĐỌC PDF TEXT
            # =================================================

            text, page_count = read_pdf_text(
                file_bytes
            )

            extraction_method = "PDF Text"

            # =================================================
            # OCR NẾU PDF SCAN
            # =================================================

            if not text.strip():

                st.info(
                    "PDF không có lớp văn bản → đang sử dụng OCR..."
                )

                try:

                    text, page_count = ocr_pdf(
                        file_bytes
                    )

                    extraction_method = "OCR"

                except Exception as e:

                    st.error(
                        f"OCR thất bại: {e}"
                    )

                    continue

            # =================================================
            # CHUẨN HÓA
            # =================================================

            text = normalize_text(
                text
            )

            st.write(
                f"**Số trang:** {page_count}"
            )

            st.write(
                f"**Phương thức đọc:** {extraction_method}"
            )

            # =================================================
            # KIỂM TRA TEXT
            # =================================================

            if not text.strip():

                st.error(
                    "Không đọc được nội dung tài liệu."
                )

                continue

            st.success(
                "Đọc tài liệu thành công."
            )

            # =================================================
            # NHẬN DIỆN
            # =================================================

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

            # =================================================
            # TRÍCH XUẤT
            # =================================================

            data = extract_document(
                text,
                document_type
            )

            if data:

                rows = []

                for field, value in data.items():

                    if value is None:
                        value = "Không tìm thấy"

                    rows.append(
                        [field, value]
                    )

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
                    "Chưa xác định được mẫu "
                    "trích xuất cho chứng từ này."
                )

            # =================================================
            # XEM TEXT
            # =================================================

            with st.expander(
                "📖 Xem nội dung hệ thống đọc được"
            ):

                st.text_area(
                    "PDF Text / OCR Text",
                    text,
                    height=400
                )
