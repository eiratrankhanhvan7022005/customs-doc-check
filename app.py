import streamlit as st
from pypdf import PdfReader

st.set_page_config(
    page_title="CustomsDoc Check",
    page_icon="📋",
    layout="wide"
)

st.title("📋 CustomsDoc Check")
st.subheader("Kiểm soát chứng từ phục vụ khai báo hải quan")

st.write(
    "Tải lên bộ chứng từ để hệ thống tự động đọc và "
    "trích xuất thông tin từ file PDF."
)

st.divider()

# ==============================
# 1. UPLOAD PDF
# ==============================

uploaded_files = st.file_uploader(
    "📄 Tải lên chứng từ PDF",
    type=["pdf"],
    accept_multiple_files=True
)

# ==============================
# 2. HIỂN THỊ FILE
# ==============================

if uploaded_files:

    st.success(f"Đã tải lên {len(uploaded_files)} chứng từ.")

    st.write("### 📁 Danh sách chứng từ")

    for file in uploaded_files:
        st.write(f"📄 {file.name}")

    st.divider()

    # ==============================
    # 3. ĐỌC PDF
    # ==============================

    if st.button("🔍 Đọc và kiểm tra chứng từ", type="primary"):

        for file in uploaded_files:

            st.write(f"### 📄 {file.name}")

            try:
                reader = PdfReader(file)

                st.write(
                    f"**Số trang:** {len(reader.pages)}"
                )

                all_text = ""

                for page in reader.pages:

                    text = page.extract_text() or ""

                    all_text += text + "\n"

                # ==============================
                # 4. HIỂN THỊ TEXT ĐỌC ĐƯỢC
                # ==============================

                if all_text.strip():

                    st.success("Đọc PDF thành công.")

                    with st.expander("📖 Xem nội dung PDF"):

                        st.text_area(
                            "Nội dung trích xuất",
                            all_text,
                            height=400
                        )

                else:

                    st.warning(
                        "Không đọc được văn bản trong PDF. "
                        "File có thể là PDF dạng ảnh và cần OCR."
                    )

            except Exception as e:

                st.error(
                    f"Không thể đọc file {file.name}: {e}"
                )
