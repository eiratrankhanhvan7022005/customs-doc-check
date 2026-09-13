import streamlit as st
from pypdf import PdfReader
import re
import pandas as pd


# =========================================================
# 1. CẤU HÌNH
# =========================================================

st.set_page_config(
    page_title="CustomsDoc Check",
    page_icon="📋",
    layout="wide"
)

st.title("📋 CustomsDoc Check")
st.subheader("Kiểm soát chứng từ phục vụ khai báo hải quan")

st.write(
    "Tải lên bộ chứng từ PDF để hệ thống tự động đọc, "
    "nhận diện loại chứng từ và trích xuất dữ liệu."
)

st.divider()


# =========================================================
# 2. CHUẨN HÓA TEXT
# =========================================================

def normalize_text(text):
    """
    Chuẩn hóa khoảng trắng nhưng vẫn giữ nội dung.
    """

    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)

    return text.strip()


def clean_value(value):
    """
    Làm sạch giá trị lấy được từ PDF.
    """

    if not value:
        return None

    value = value.strip()
    value = re.sub(r"\s+", " ", value)

    return value.strip(" :;-.")


# =========================================================
# 3. TÌM THEO NHIỀU MẪU
# =========================================================

def search_patterns(text, patterns):

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
# 4. NHẬN DIỆN LOẠI CHỨNG TỪ
# =========================================================

def detect_document_type(text, filename):

    text_lower = text.lower()
    filename_lower = filename.lower()

    # -------------------------
    # B/L
    # -------------------------

    bl_keywords = [
        "bill of lading",
        "bill of lading no",
        "b/l no",
        "b/l number",
        "vessel",
        "port of loading",
        "port of discharge",
        "shipper",
        "consignee"
    ]

    bl_score = sum(
        1 for keyword in bl_keywords
        if keyword in text_lower
    )

    # -------------------------
    # Packing List
    # -------------------------

    pl_keywords = [
        "packing list",
        "packing list no",
        "package",
        "packages",
        "carton",
        "cartons",
        "gross weight",
        "net weight"
    ]

    pl_score = sum(
        1 for keyword in pl_keywords
        if keyword in text_lower
    )

    # -------------------------
    # C/O
    # -------------------------

    co_keywords = [
        "certificate of origin",
        "certificate of origin form",
        "country of origin",
        "origin criterion",
        "exporter",
        "issuing authority"
    ]

    co_score = sum(
        1 for keyword in co_keywords
        if keyword in text_lower
    )

    # -------------------------
    # Invoice
    # -------------------------

    invoice_keywords = [
        "invoice",
        "invoice no",
        "invoice number",
        "unit price",
        "amount",
        "total amount",
        "seller",
        "buyer"
    ]

    invoice_score = sum(
        1 for keyword in invoice_keywords
        if keyword in text_lower
    )

    # -------------------------
    # Ưu tiên kết quả
    # -------------------------

    scores = {
        "B/L": bl_score,
        "Packing List": pl_score,
        "C/O": co_score,
        "Invoice": invoice_score
    }

    document_type = max(
        scores,
        key=scores.get
    )

    if scores[document_type] == 0:

        # thử dựa vào tên file

        if "invoice" in filename_lower:
            document_type = "Invoice"

        elif "packing" in filename_lower:
            document_type = "Packing List"

        elif "bl" in filename_lower or "bill" in filename_lower:
            document_type = "B/L"

        elif "co" in filename_lower:
            document_type = "C/O"

        else:
            document_type = "Chưa xác định"

    return document_type


# =========================================================
# 5. EXTRACT INVOICE
# =========================================================

def extract_invoice(text):

    data = {}

    # Invoice number

    data["Invoice No."] = search_patterns(
        text,
        [
            r"(?:proforma\s+)?invoice\s*(?:no\.?|number|#)\s*[:\-]?\s*([A-Z0-9][A-Z0-9\-\/]*)",

            r"commercial\s+invoice\s*(?:no\.?|number|#)\s*[:\-]?\s*([A-Z0-9][A-Z0-9\-\/]*)",

            r"invoice\s+ref(?:erence)?\s*[:\-]?\s*([A-Z0-9][A-Z0-9\-\/]*)"
        ]
    )

    # Date

    data["Invoice Date"] = search_patterns(
        text,
        [
            r"(?:invoice\s+)?date\s*[:\-]?\s*(\d{1,2}[-\/.][A-Za-z0-9]+[-\/.]\d{2,4})",

            r"(?:invoice\s+)?date\s*[:\-]?\s*(\d{1,2}[-\/.]\d{1,2}[-\/.]\d{2,4})"
        ]
    )

    # Seller

    data["Seller"] = search_patterns(
        text,
        [
            r"seller\s*[:\-]?\s*(.+)",

            r"exporter\s*[:\-]?\s*(.+)",

            r"from\s*[:\-]?\s*(.+)"
        ]
    )

    # Buyer

    data["Buyer"] = search_patterns(
        text,
        [
            r"buyer\s*[:\-]?\s*(.+)",

            r"importer\s*[:\-]?\s*(.+)"
        ]
    )

    # Currency

    currency = search_patterns(
        text,
        [
            r"\b(USD|EUR|JPY|KRW|VND|CNY|GBP)\b"
        ]
    )

    data["Currency"] = currency

    # Incoterm

    incoterm = search_patterns(
        text,
        [
            r"\b(FOB|CIF|CFR|EXW|FCA|DAP|DDP|CPT|CIP|FAS|DAT)\b"
        ]
    )

    data["Incoterm"] = incoterm

    # Total amount

    data["Total Amount"] = search_patterns(
        text,
        [
            r"total\s+amount\s*[:\-]?\s*(?:USD|EUR|JPY|KRW|VND|CNY|GBP)?\s*([\d,]+(?:\.\d+)?)",

            r"grand\s+total\s*[:\-]?\s*(?:USD|EUR|JPY|KRW|VND|CNY|GBP)?\s*([\d,]+(?:\.\d+)?)",

            r"TOTAL\s*:\s*[\d,]+(?:\.\d+)?\s*KG\s+(?:USD|EUR|JPY|KRW|VND|CNY|GBP)\s*([\d,]+(?:\.\d+)?)"
        ]
    )

    # Total weight

    data["Total Weight"] = search_patterns(
        text,
        [
            r"TOTAL\s*:\s*([\d,]+(?:\.\d+)?)\s*KG",

            r"total\s+(?:net\s+)?weight\s*[:\-]?\s*([\d,]+(?:\.\d+)?)\s*(?:KG|KGS)",

            r"net\s+weight\s*[:\-]?\s*([\d,]+(?:\.\d+)?)\s*(?:KG|KGS)"
        ]
    )

    return data


# =========================================================
# 6. EXTRACT PACKING LIST
# =========================================================

def extract_packing_list(text):

    data = {}

    data["Packing List No."] = search_patterns(
        text,
        [
            r"packing\s+list\s*(?:no\.?|number|#)\s*[:\-]?\s*([A-Z0-9\-\/]+)"
        ]
    )

    data["Net Weight"] = search_patterns(
        text,
        [
            r"net\s+weight\s*[:\-]?\s*([\d,]+(?:\.\d+)?)\s*(?:KG|KGS)",

            r"n\.?w\.?\s*[:\-]?\s*([\d,]+(?:\.\d+)?)\s*(?:KG|KGS)"
        ]
    )

    data["Gross Weight"] = search_patterns(
        text,
        [
            r"gross\s+weight\s*[:\-]?\s*([\d,]+(?:\.\d+)?)\s*(?:KG|KGS)",

            r"g\.?w\.?\s*[:\-]?\s*([\d,]+(?:\.\d+)?)\s*(?:KG|KGS)"
        ]
    )

    data["Package Count"] = search_patterns(
        text,
        [
            r"(?:total\s+)?(?:package|packages|carton|cartons)\s*[:\-]?\s*(\d+)",

            r"(\d+)\s*(?:PLTS|PALLETS|CARTONS|CTNS)"
        ]
    )

    data["Container"] = search_patterns(
        text,
        [
            r"container\s*(?:no\.?|number)?\s*[:\-]?\s*([A-Z]{4}\d{7})",

            r"\b([A-Z]{4}\d{7})\b"
        ]
    )

    return data


# =========================================================
# 7. EXTRACT B/L
# =========================================================

def extract_bl(text):

    data = {}

    data["B/L No."] = search_patterns(
        text,
        [
            r"(?:B\/L|BL|Bill\s+of\s+Lading)\s*(?:No\.?|Number|#)\s*[:\-]?\s*([A-Z0-9\-\/]+)",

            r"B\/L\s*[:\-]?\s*([A-Z0-9\-\/]+)"
        ]
    )

    data["Shipper"] = search_patterns(
        text,
        [
            r"shipper\s*[:\-]?\s*(.+)",

            r"exporter\s*[:\-]?\s*(.+)"
        ]
    )

    data["Consignee"] = search_patterns(
        text,
        [
            r"consignee\s*[:\-]?\s*(.+)",

            r"importer\s*[:\-]?\s*(.+)"
        ]
    )

    data["Container"] = search_patterns(
        text,
        [
            r"container\s*(?:no\.?|number)?\s*[:\-]?\s*([A-Z]{4}\d{7})",

            r"\b([A-Z]{4}\d{7})\b"
        ]
    )

    data["Gross Weight"] = search_patterns(
        text,
        [
            r"gross\s+weight\s*[:\-]?\s*([\d,]+(?:\.\d+)?)\s*(?:KG|KGS)",

            r"G\.?W\.?\s*[:\-]?\s*([\d,]+(?:\.\d+)?)\s*(?:KG|KGS)"
        ]
    )

    data["Port of Loading"] = search_patterns(
        text,
        [
            r"port\s+of\s+loading\s*[:\-]?\s*(.+)",

            r"P\.?O\.?L\.?\s*[:\-]?\s*(.+)"
        ]
    )

    data["Port of Discharge"] = search_patterns(
        text,
        [
            r"port\s+of\s+discharge\s*[:\-]?\s*(.+)",

            r"P\.?O\.?D\.?\s*[:\-]?\s*(.+)"
        ]
    )

    data["Voyage"] = search_patterns(
        text,
        [
            r"voyage\s*[:\-]?\s*(.+)"
        ]
    )

    return data


# =========================================================
# 8. EXTRACT C/O
# =========================================================

def extract_co(text):

    data = {}

    data["Exporter"] = search_patterns(
        text,
        [
            r"exporter\s*[:\-]?\s*(.+)"
        ]
    )

    data["Importer"] = search_patterns(
        text,
        [
            r"importer\s*[:\-]?\s*(.+)",

            r"consignee\s*[:\-]?\s*(.+)"
        ]
    )

    data["Country of Origin"] = search_patterns(
        text,
        [
            r"country\s+of\s+origin\s*[:\-]?\s*(.+)",

            r"origin\s*[:\-]?\s*(.+)",

            r"made\s+in\s+(.+)"
        ]
    )

    data["HS Code"] = search_patterns(
        text,
        [
            r"HS\s*(?:Code|CODE)?\s*[:\-]?\s*(\d{4,12})"
        ]
    )

    return data


# =========================================================
# 9. HÀM EXTRACT CHUNG
# =========================================================

def extract_document(text, filename):

    text = normalize_text(text)

    document_type = detect_document_type(
        text,
        filename
    )

    if document_type == "Invoice":

        data = extract_invoice(text)

    elif document_type == "Packing List":

        data = extract_packing_list(text)

    elif document_type == "B/L":

        data = extract_bl(text)

    elif document_type == "C/O":

        data = extract_co(text)

    else:

        data = {}

    return document_type, data


# =========================================================
# 10. UPLOAD FILE
# =========================================================

uploaded_files = st.file_uploader(
    "📄 Tải lên chứng từ PDF",
    type=["pdf"],
    accept_multiple_files=True
)


# =========================================================
# 11. XỬ LÝ
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

        all_documents = []

        for file in uploaded_files:

            st.write(
                f"## 📄 {file.name}"
            )

            try:

                reader = PdfReader(file)

                all_text = ""

                for page in reader.pages:

                    text = page.extract_text() or ""

                    all_text += text + "\n"

                st.write(
                    f"**Số trang:** {len(reader.pages)}"
                )

                if not all_text.strip():

                    st.warning(
                        "Không đọc được văn bản. "
                        "PDF có thể là file scan và cần OCR."
                    )

                    continue

                st.success(
                    "Đọc PDF thành công."
                )

                document_type, data = extract_document(
                    all_text,
                    file.name
                )

                st.info(
                    f"📑 Loại chứng từ nhận diện: **{document_type}**"
                )

                # Lưu lại

                all_documents.append({
                    "filename": file.name,
                    "type": document_type,
                    "data": data
                })

                # Hiển thị dữ liệu

                if data:

                    rows = []

                    for field, value in data.items():

                        rows.append([
                            field,
                            value if value else "Không tìm thấy"
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
                        "Chưa có bộ nhận diện phù hợp "
                        "cho chứng từ này."
                    )

                # Cho xem text

                with st.expander(
                    "📖 Xem nội dung PDF hệ thống đã đọc"
                ):

                    st.text_area(
                        "Nội dung",
                        all_text,
                        height=300,
                        key=f"text_{file.name}"
                    )

            except Exception as e:

                st.error(
                    f"Không thể đọc {file.name}: {e}"
                )


# =========================================================
# 12. THÔNG TIN DEMO
# =========================================================

st.divider()

st.caption(
    "CustomsDoc Check là công cụ prototype hỗ trợ kiểm soát "
    "chứng từ trước khai báo hải quan, không thay thế hệ thống "
    "khai báo chính thức của Hải quan."
)
