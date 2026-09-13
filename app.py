import streamlit as st

st.set_page_config(
    page_title="CustomsDoc Check",
    page_icon="📋",
    layout="wide"
)

st.title("📋 CustomsDoc Check")
st.subheader("Kiểm soát chứng từ phục vụ khai báo hải quan")

st.write(
    "Tải lên bộ chứng từ để hệ thống kiểm tra và đối chiếu "
    "thông tin trước khi khai báo."
)

st.divider()

uploaded_files = st.file_uploader(
    "📄 Tải lên chứng từ",
    type=["pdf"],
    accept_multiple_files=True
)

if uploaded_files:
    st.success(f"Đã tải lên {len(uploaded_files)} chứng từ.")

    st.write("### Danh sách chứng từ")

    for file in uploaded_files:
        st.write(f"📄 {file.name}")

    st.divider()

    if st.button("🔍 Bắt đầu kiểm tra", type="primary"):
        st.info("Hệ thống sẽ bắt đầu đọc và kiểm tra chứng từ...")
