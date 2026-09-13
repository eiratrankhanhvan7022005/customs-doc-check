import streamlit as st
from pypdf import PdfReader
import re
import pandas as pd

st.set_page_config(
    page_title="CustomsDoc Check",
    page_icon="📋",
    layout="wide"
)

st.title("📋 CustomsDoc Check")
st.subheader("Kiểm soát chứng từ phục vụ khai báo hải quan")

st.write(
    "Tải lên bộ chứng từ để hệ thống tự động đọc "
    "và trích xuất thông tin."
)

st.divider()

uploaded_files = st.file_uploader(
    "📄 Tải lên chứng từ PDF",
    type=["pdf"],
    accept_multiple_files=True
)


def extract_data(text):

    data = {}

    # Invoice No.
    match = re.search(
        r'(?:Profoma|Proforma)\s+Invoice\s+No\.\s*([A-Z0-9\-\/]+)',
        text,
        re.IGNORECASE
    )
    data["Invoice No."] = match.group(1) if match else "Không tìm thấy"

    # Invoice Date
    match = re.search(
        r'Date:\s*(\d{1,2}-[A-Za-z]+-\d{4})',
        text
    )
    data["Invoice Date"] = match.group(1) if match else "Không tìm thấy"

    # Total Weight
    match = re.search(
        r'TOTAL:\s*([\d,]+(?:\.\d+)?)\s*KG',
        text,
        re.IGNORECASE
    )
    data["Total Weight"] = (
        match.group(1) + " KG"
        if match else "Không tìm thấy"
    )

    # Total Amount
    match = re.search(
        r'TOTAL:\s*[\d,]+(?:\.\d+)?\s*KG\s+USD\s*([\d,]+(?:\.\d+)?)',
        text,
        re.IGNORECASE
    )
    data["Total Amount"] = (
        "USD " + match.group(1)
        if match else "Không tìm thấy"
    )

    # B/L No.
    match = re.search(
        r'Số vận tải đơn \(B/L No\)\s*([A-Z0-9]+)',
        text,
        re.IGNORECASE
    )
    data["B/L No."] = match.group(1) if match else "Không tìm thấy"

    # Gross Weight
    match = re.search(
        r'Trọng lượng \(Gross weight\)\s*([\d,]+(?:\.\d+)?)\s*KGS',
        text,
        re.IGNORECASE
    )
    data["Gross Weight"] = (
        match.group(1) + " KGS"
        if match else "Không tìm thấy"
    )

    return data


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

            reader = PdfReader(file)

            all_text = ""

            for page in reader.pages:
                all_text += (page.extract_text() or "") + "\n"

            st.write(f"### 📄 {file.name}")

            st.write(
                f"**Số trang:** {len(reader.pages)}"
            )

            if all_text.strip():

                data = extract_data(all_text)

                rows = []

                for field, value in data.items():
                    rows.append([field, value])

                df = pd.DataFrame(
                    rows,
                    columns=["Trường dữ liệu", "Giá trị"]
                )

                st.write("### 📊 Dữ liệu tự động trích xuất")

                st.dataframe(
                    df,
                    use_container_width=True,
                    hide_index=True
                )

            else:

                st.warning(
                    "Không đọc được văn bản trong PDF."
                )
