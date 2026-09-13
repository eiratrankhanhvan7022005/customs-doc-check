import streamlit as st
from pypdf import PdfReader
import pytesseract
from pdf2image import convert_from_bytes
import pandas as pd
import re


# =========================
# CẤU HÌNH TRANG
# =========================

st.set_page_config(
    page_title="CustomsDoc Check",
    page_icon="📋",
    layout="wide"
)

st.title("📋 CustomsDoc Check")
st.subheader("Kiểm soát chứng từ phục vụ khai báo hải quan")

st.write(
    "Hệ thống tự động đọc PDF, OCR tài liệu scan "
    "và trích xuất thông tin phục vụ kiểm tra chứng từ."
)

st.divider()


# =========================
# ĐỌC PDF BẰNG TEXT
# =========================

def read_pdf_text(file_bytes):

    try:
        reader = PdfReader(file_bytes)

        text = ""

        for page in reader.pages:
            page_text = page.extract_text() or ""
            text += page_text + "\n"

        return text, len(reader.pages)

    except Exception:
        return "", 0


# =========================
# OCR PDF SCAN
# =========================

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


# =========================
# CHUẨN HÓA TEXT
# =========================

def normalize_text(text):

    text = text.replace("\xa0", " ")

    text = re.sub(
        r"[ \t]+",
        " ",
        text
    )

    return text


# =========================
# NHẬN DIỆN LOẠI CHỨNG TỪ
# =========================

def detect_document_type(text):

    text_upper = text.upper()

    scores = {
        "COMMERCIAL INVOICE": 0,
        "BILL OF LADING": 0,
        "PACKING LIST": 0,
        "CERTIFICATE OF ORIGIN": 0
    }

    invoice_keywords = [
        "COMMERCIAL INVOICE",
        "PROFORMA INVOICE",
        "INVOICE NO",
        "UNIT PRICE",
        "TOTAL AMOUNT"
    ]

    bl_keywords = [
        "BILL OF LADING",
        "B/L",
        "SHIPPER",
        "CONSIGNEE",
        "PORT OF LOADING",
        "PORT OF DISCHARGE"
    ]

    pl_keywords = [
        "PACKING LIST",
        "NET WEIGHT",
        "GROSS WEIGHT",
        "PACKAGES",
        "CARTON"
    ]

    co_keywords = [
        "CERTIFICATE OF ORIGIN",
        "CERTIFICATE OF ORIGIN FORM",
        "ORIGIN CRITERION",
        "EXPORTER"
    ]

    for keyword in invoice_keywords:
        if keyword in text_upper:
            scores["COMMERCIAL INVOICE"] += 1

    for keyword in bl_keywords:
        if keyword in text_upper:
            scores["BILL OF LADING"] += 1

    for keyword in pl_keywords:
        if keyword in text_upper:
            scores["PACKING LIST"] += 1

    for keyword in co_keywords:
        if keyword in text_upper:
            scores["CERTIFICATE OF ORIGIN"] += 1

    document_type = max(
        scores,
        key=scores.get
    )

    if scores[document_type] == 0:
        return "KHÔNG XÁC ĐỊNH"

    return document_type


# =========================
# HÀM TÌM REGEX
# =========================

def find_pattern(text, patterns):

    for pattern in patterns:

        match = re.search(
            pattern,
            text,
            re.IGNORECASE
        )

        if match:
            return match.group(1).strip()

    return None


# =========================
# TRÍCH XUẤT INVOICE
# =========================

def extract_invoice(text):

    data = {}

    data["Invoice No."] = find_pattern(
        text,
        [
            r"(?:COMMERCIAL|PROFORMA)\s+INVOICE\s*(?:NO\.?|NUMBER)?\s*[:#]?\s*([A-Z0-9\-\/]+)",
            r"Invoice\s+No\.?\s*[:#]?\s*([A-Z0-9\-\/]+)"
        ]
    )

    data["Invoice Date"] = find_pattern(
        text,
        [
            r"Date\s*[:\-]?\s*(\d{1,2}[-\/][A-Za-z0-9]+[-\/]?\d{0,4})",
            r"Date\s*[:\-]?\s*(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4})"
        ]
    )

    data["Seller / Exporter"] = find_pattern(
        text,
        [
            r"(?:Seller|Exporter)\s*[:\-]?\s*(.+)",
            r"Shipper\s*[:\-]?\s*(.+)"
        ]
    )

    data["Buyer / Importer"] = find_pattern(
        text,
        [
            r"(?:Buyer|Importer)\s*[:\-]?\s*(.+)",
            r"Consignee\s*[:\-]?\s*(.+)"
        ]
    )

    data["Currency"] = find_pattern(
        text,
        [
            r"\b(USD|EUR|KRW|JPY|VND)\b"
        ]
    )

    data["Incoterm"] = find_pattern(
        text,
        [
            r"\b(EXW|FOB|CFR|CIF|FCA|CPT|CIP|DAP|DPU|DDP)\b"
        ]
    )

    data["Total Amount"] = find_pattern(
        text,
        [
            r"(?:TOTAL|TOTAL AMOUNT)\s*[:\-]?\s*(?:USD|EUR|KRW|JPY|VND)?\s*([\d,]+\.\d{2})"
        ]
    )

    data["Total Weight"] = find_pattern(
        text,
        [
            r"(?:TOTAL|TOTAL WEIGHT)\s*[:\-]?\s*([\d,]+(?:\.\d+)?)\s*(?:KG|KGS)"
        ]
    )

    return data


# =========================
# TRÍCH XUẤT BILL OF LADING
# =========================

def extract_bl(text):

    data = {}

    data["B/L No."] = find_pattern(
        text,
        [
            r"(?:B\/L|BILL OF LADING)\s*(?:NO\.?|NUMBER)?\s*[:#]?\s*([A-Z0-9\-]+)"
        ]
    )

    data["Shipper"] = find_pattern(
        text,
        [
            r"SHIPPER\s*[:\-]?\s*(.+)"
        ]
    )

    data["Consignee"] = find_pattern(
        text,
        [
            r"CONSIGNEE\s*[:\-]?\s*(.+)"
        ]
    )

    data["Container No."] = find_pattern(
        text,
        [
            r"(?:CONTAINER|CONTAINER NO\.?)\s*[:\-]?\s*([A-Z]{4}\d{7})"
        ]
    )

    data["Gross Weight"] = find_pattern(
        text,
        [
            r"GROSS\s+WEIGHT\s*[:\-]?\s*([\d,]+(?:\.\d+)?)\s*(?:KG|KGS)"
        ]
    )

    data["Port of Loading"] = find_pattern(
        text,
        [
            r"PORT OF LOADING\s*[:\-]?\s*(.+)"
        ]
    )

    data["Port of Discharge"] = find_pattern(
        text,
        [
            r"PORT OF DISCHARGE\s*[:\-]?\s*(.+)"
        ]
    )

    data["Voyage"] = find_pattern(
        text,
        [
            r"VOYAGE\s*[:\-]?\s*(.+)"
        ]
    )

    return data


# =========================
# TRÍCH XUẤT PACKING LIST
# =========================

def extract_packing_list(text):

    data = {}

    data["Packing List No."] = find_pattern(
        text,
        [
            r"(?:PACKING LIST|P\/L)\s*(?:NO\.?|NUMBER)?\s*[:#]?\s*([A-Z0-9\-\/]+)"
        ]
    )

    data["Net Weight"] = find_pattern(
        text,
        [
            r"NET\s+WEIGHT\s*[:\-]?\s*([\d,]+(?:\.\d+)?)\s*(?:KG|KGS)"
        ]
    )

    data["Gross Weight"] = find_pattern(
        text,
        [
            r"GROSS\s+WEIGHT\s*[:\-]?\s*([\d,]+(?:\.\d+)?)\s*(?:KG|KGS)"
        ]
    )

    data["Packages"] = find_pattern(
        text,
        [
            r"(?:TOTAL\s+)?(?:PACKAGES|PKGS|CARTONS|CTNS)\s*[:\-]?\s*(\d+)"
        ]
    )

    data["Container No."] = find_pattern(
        text,
        [
            r"(?:CONTAINER|CONTAINER NO\.?)\s*[:\-]?\s*([A-Z]{4}\d{7})"
        ]
    )

    return data


# =========================
# TRÍCH XUẤT C/O
# =========================

def extract_co(text):

    data = {}

    data["Exporter"] = find_pattern(
        text,
        [
            r"EXPORTER\s*[:\-]?\s*(.+)"
        ]
    )

    data["Importer"] = find_pattern(
        text,
        [
            r"IMPORTER\s*[:\-]?\s*(.+)"
        ]
    )

    data["Origin"] = find_pattern(
        text,
        [
            r"(?:COUNTRY OF ORIGIN|ORIGIN)\s*[:\-]?\s*(.+)",
            r"MADE IN\s+(.+)"
        ]
    )

    data["HS Code"] = find_pattern(
        text,
        [
            r"HS\s*(?:CODE|NO\.?)?\s*[:\-]?\s*(\d{4,10})"
        ]
    )

    return data


# =========================
# ĐIỀU PHỐI TRÍCH XUẤT
# =========================

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


# =========================
# UPLOAD FILE
# =========================

uploaded_files = st.file_uploader(
    "📄 Tải lên chứng từ PDF",
    type=["pdf"],
    accept_multiple_files=True
)


# =========================
# XỬ LÝ
# =========================

if uploaded_files:

    st.success(
        f"Đã tải lên {len(uploaded_files)} chứng từ."
    )

    st.write("### 📁 Danh sách chứng từ")

    for file in uploaded_files:
        st.write(f"📄 {file.name}")

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

            # -------------------------
            # THỬ ĐỌC TEXT TRƯỚC
            # -------------------------

            text, page_count = read_pdf_text(
                file_bytes
            )

            extraction_method = "PDF Text"

            # -------------------------
            # NẾU KHÔNG CÓ TEXT → OCR
            # -------------------------

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

            # -------------------------
            # CHUẨN HÓA
            # -------------------------

            text = normalize_text(text)

            st.write(
                f"**Số trang:** {page_count}"
            )

            st.write(
                f"**Phương thức đọc:** {extraction_method}"
            )

            if text.strip():

                st.success(
                    "Đọc tài liệu thành công."
                )

                # -------------------------
                # NHẬN DIỆN LOẠI CHỨNG TỪ
                # -------------------------

                document_type = detect_document_type(
                    text
                )

                st.write(
                    f"### 🗂️ Loại chứng từ: "
                    f"**{document_type}**"
                )

                # -------------------------
                # TRÍCH XUẤT
                # -------------------------

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
                        "Chưa có mẫu trích xuất cho "
                        "loại chứng từ này."
                    )

                # -------------------------
                # XEM TEXT
                # -------------------------

                with st.expander(
                    "📖 Xem nội dung hệ thống đọc được"
                ):

                    st.text_area(
                        "OCR / PDF Text",
                        text,
                        height=400
                    )

            else:

                st.error(
                    "Không đọc được nội dung tài liệu."
                )
