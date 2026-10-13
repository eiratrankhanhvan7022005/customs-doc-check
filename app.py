import os
import re
import io
import json
import logging
import datetime
import math
from typing import Dict, List, Any, Optional, Tuple, Union

import pdfplumber
import pytesseract
from PIL import Image, ImageEnhance, ImageFilter
import pandas as pd
import streamlit as st

# Safe import for Supabase
try:
    from supabase import create_client, Client
    HAS_SUPABASE = True
except ImportError:
    HAS_SUPABASE = False

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# ==========================================
# 1. CONFIGURATION & EXTENSIVE ALIAS MAPPING
# ==========================================

DEFAULT_FIELD_ALIASES = {
    "invoice_number": [
        "invoice no", "invoice number", "inv no", "inv number", "inv #", "so hoa don", "số hóa đơn",
        "commercial invoice no", "facture no", "bill no"
    ],
    "invoice_date": [
        "invoice date", "date of invoice", "inv date", "ngay hoa don", "ngày hóa đơn", "dated", "date"
    ],
    "contract_number": [
        "contract no", "contract number", "so hop dong", "số hợp đồng", "po no", "p.o. no",
        "purchase order no", "purchase order number", "agreement no", "sales contract no"
    ],
    "contract_date": [
        "contract date", "date of contract", "ngay hop dong", "ngày hợp đồng", "po date", "p.o. date"
    ],
    "seller_name": [
        "seller", "exporter", "vendor", "beneficiary", "nguoi ban", "người bán",
        "supplier", "shipper/exporter", "seller/exporter"
    ],
    "buyer_name": [
        "buyer", "importer", "applicant", "nguoi mua", "người mua",
        "purchaser", "buyer/importer"
    ],
    "shipper_name": [
        "shipper", "consignor", "expediter", "nguoi gui hang", "người gửi hàng",
        "shipper/consignor", "from"
    ],
    "consignee_name": [
        "consignee", "deliver to", "ship to", "nguoi nhan hang", "người nhận hàng",
        "consignee/notify", "to the order of", "for account of"
    ],
    "notify_party": [
        "notify party", "notify", "ben duoc thong bao", "bên được thông báo", "also notify"
    ],
    "total_amount": [
        "total amount", "grand total", "total value", "tong tien", "tổng tiền",
        "amount payable", "total invoice amount", "total usd", "total eur", "total vnd"
    ],
    "currency": [
        "currency", "curr", "loai tien", "loại tiền", "currency code"
    ],
    "port_of_loading": [
        "port of loading", "pol", "loading port", "cang xat hang", "cảng xếp hàng",
        "cang dau", "port of departure", "place of loading"
    ],
    "port_of_discharge": [
        "port of discharge", "pod", "discharge port", "cang do hang", "cảng dỡ hàng",
        "cang den", "port of destination", "place of delivery"
    ],
    "vessel_flight": [
        "vessel", "vessel name", "ocean vessel", "vessel/voyage", "flight no",
        "flight number", "feeder vessel", "voyage no", "voy no"
    ],
    "gross_weight": [
        "gross weight", "g.w.", "gw", "tong trong luong", "trọng lượng cả bì",
        "gross weight (kgs)", "total gross weight", "gross wt"
    ],
    "net_weight": [
        "net weight", "n.w.", "nw", "trong luong thuan", "trọng lượng tịnh",
        "net weight (kgs)", "total net weight", "net wt"
    ],
    "volume": [
        "measurement", "cbm", "volume", "thetich", "thể tích", "total cbm", "total measurement"
    ],
    "payment_terms": [
        "payment terms", "terms of payment", "tieu chuan thanh toan", "dieu khoan thanh toan",
        "dầu khoản thanh toán", "lc no", "l/c no", "payment method"
    ],
    "incoterms": [
        "incoterms", "price term", "delivery term", "trade term", "terms of delivery",
        "fob", "cif", "cfr", "exw", "ddp", "dap", "fca"
    ]
}

# ==========================================
# 2. SUPABASE INTEGRATION & KNOWLEDGE BASE
# ==========================================

def get_supabase_client() -> Optional[Any]:
    """Initialize and return Supabase client if configured."""
    if not HAS_SUPABASE:
        return None
    url = st.secrets.get("SUPABASE_URL") or os.getenv("SUPABASE_URL")
    key = st.secrets.get("SUPABASE_KEY") or os.getenv("SUPABASE_KEY")
    if url and key:
        try:
            return create_client(url, key)
        except Exception as e:
            logging.error(f"Failed to connect to Supabase: {e}")
            return None
    return None

def fetch_knowledge_base_aliases(client: Optional[Any]) -> Dict[str, List[str]]:
    """Fetch additional dynamic field aliases from Supabase Knowledge Base if available."""
    aliases = DEFAULT_FIELD_ALIASES.copy()
    if not client:
        return aliases
    try:
        response = client.table("field_aliases").select("field_name, alias_value").execute()
        if response.data:
            for row in response.data:
                field = row.get("field_name")
                alias = row.get("alias_value")
                if field and alias:
                    if field not in aliases:
                        aliases[field] = []
                    if alias.lower() not in [a.lower() for a in aliases[field]]:
                        aliases[field].append(alias)
    except Exception as e:
        logging.warning(f"Could not load aliases from Supabase: {e}")
    return aliases

# ==========================================
# 3. HYBRID OCR & ADVANCED PDF EXTRACTION
# ==========================================

def preprocess_image_advanced(image: Image.Image) -> Image.Image:
    """Enhance image quality before running Tesseract OCR to minimize character misrecognition."""
    # Convert to Grayscale
    gray = image.convert('L')
    # Increase Contrast
    enhancer = ImageEnhance.Contrast(gray)
    enhanced = enhancer.enhance(2.2)
    # Sharpen edges
    sharpened = enhanced.filter(ImageFilter.SHARPEN)
    # Binarization (Thresholding)
    threshold = 180
    binarized = sharpened.point(lambda p: 255 if p > threshold else 0)
    return binarized

def extract_pdf_with_hybrid_ocr(pdf_bytes: bytes) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Extract text and positional layout bounding boxes. Uses Native PDF text layer first.
    If a page is scanned or text density is low, uses high-resolution OCR fallback per page.
    """
    full_text_pages = []
    layout_elements = []

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page_idx, page in enumerate(pdf.pages):
            native_text = page.extract_text() or ""
            words = page.extract_words() or []
            
            # If native layer is too sparse or empty, trigger OCR fallback for this specific page
            if len(native_text.strip()) < 40 or len(words) < 5:
                try:
                    # Convert page to image at 300 DPI
                    pil_img = page.to_image(resolution=300).original
                    processed_img = preprocess_image_advanced(pil_img)
                    
                    # OCR with Tesseract
                    ocr_data = pytesseract.image_to_data(processed_img, lang='eng+vie', output_type=pytesseract.Output.DICT)
                    
                    page_text_lines = []
                    current_line_num = -1
                    current_line_text = []

                    for i in range(len(ocr_data['text'])):
                        word = ocr_data['text'][i].strip()
                        if not word:
                            continue
                        line_num = ocr_data['line_num'][i]
                        top = ocr_data['top'][i]
                        left = ocr_data['left'][i]
                        width = ocr_data['width'][i]
                        height = ocr_data['height'][i]

                        layout_elements.append({
                            "page": page_idx + 1,
                            "text": word,
                            "bbox": (left, top, left + width, top + height),
                            "source": "ocr"
                        })

                        if line_num != current_line_num:
                            if current_line_text:
                                page_text_lines.append(" ".join(current_line_text))
                            current_line_text = [word]
                            current_line_num = line_num
                        else:
                            current_line_text.append(word)

                    if current_line_text:
                        page_text_lines.append(" ".join(current_line_text))
                    
                    ocr_page_text = "\n".join(page_text_lines)
                    full_text_pages.append(f"--- Page {page_idx+1} (OCR Hybrid) ---\n" + ocr_page_text)

                except Exception as e:
                    logging.error(f"OCR Page {page_idx+1} failed: {e}")
                    full_text_pages.append(f"--- Page {page_idx+1} (Native Fallback) ---\n" + native_text)
            else:
                for w in words:
                    layout_elements.append({
                        "page": page_idx + 1,
                        "text": w["text"],
                        "bbox": (w["x0"], w["top"], w["x1"], w["bottom"]),
                        "source": "native"
                    })
                full_text_pages.append(f"--- Page {page_idx+1} ---\n" + native_text)

    return "\n\n".join(full_text_pages), layout_elements

# ==========================================
# 4. CONTEXT & PARTY IDENTIFICATION ENGINE
# ==========================================

def clean_value(val: str) -> str:
    """Clean unwanted prefix/suffix symbols from extracted values."""
    val = re.sub(r'^[:\-\s\.]+', '', val)
    val = re.sub(r'[:\-\s\.]+$', '', val)
    return val.strip()

def extract_fields_by_context(text: str, aliases: Dict[str, List[str]]) -> Dict[str, Any]:
    """
    Extract key-value pairs using labels, aliases, positional context, and line rules.
    Maintains strict distinction between legal entities (Seller vs Shipper, Buyer vs Consignee).
    """
    extracted = {}
    lines = [l.strip() for l in text.split('\n') if l.strip()]

    # Pattern matchers for core fields
    for field, alias_list in aliases.items():
        if field in extracted:
            continue
        
        for idx, line in enumerate(lines):
            line_lower = line.lower()
            found = False

            for alias in alias_list:
                alias_lower = alias.lower()
                # Check for label match
                if alias_lower in line_lower:
                    # Method 1: Same line extraction (Key: Value)
                    pattern = rf"{re.escape(alias)}[:\s\-]+(.+)"
                    match = re.search(pattern, line, re.IGNORECASE)
                    if match:
                        val = clean_value(match.group(1))
                        if len(val) > 0 and not any(other_alias in val.lower() for other in alias_list if other.lower() != alias_lower):
                            extracted[field] = val
                            found = True
                            break
                    
                    # Method 2: Multi-line / Contextual extraction (Value is on the next line)
                    if not found and idx + 1 < len(lines):
                        next_line = lines[idx + 1]
                        # Ensure next line isn't another header/label
                        if not any(k in next_line.lower() for sublist in aliases.values() for k in sublist):
                            val = clean_value(next_line)
                            if len(val) > 1:
                                extracted[field] = val
                                found = True
                                break
            if found:
                break

    # Entity Differentiation Logic (Strictly avoid assuming Shipper == Seller or Consignee == Buyer)
    # Check for dedicated Shipper/Seller headers in text
    if "shipper_name" not in extracted:
        shipper_match = re.search(r"shipper[:\s\n]+([^\n]+)", text, re.IGNORECASE)
        if shipper_match:
            extracted["shipper_name"] = clean_value(shipper_match.group(1))

    if "seller_name" not in extracted:
        seller_match = re.search(r"(seller|exporter|vendor)[:\s\n]+([^\n]+)", text, re.IGNORECASE)
        if seller_match:
            extracted["seller_name"] = clean_value(seller_match.group(1))

    if "consignee_name" not in extracted:
        consignee_match = re.search(r"consignee[:\s\n]+([^\n]+)", text, re.IGNORECASE)
        if consignee_match:
            extracted["consignee_name"] = clean_value(consignee_match.group(1))

    if "buyer_name" not in extracted:
        buyer_match = re.search(r"(buyer|importer|applicant)[:\s\n]+([^\n]+)", text, re.IGNORECASE)
        if buyer_match:
            extracted["buyer_name"] = clean_value(buyer_match.group(1))

    # Fallback with explicit flag if one entity is inferred from another
    if "seller_name" not in extracted and "shipper_name" in extracted:
        extracted["seller_name"] = f"{extracted['shipper_name']} (Inferred from Shipper)"
    
    if "buyer_name" not in extracted and "consignee_name" in extracted:
        extracted["buyer_name"] = f"{extracted['consignee_name']} (Inferred from Consignee)"

    return extracted

# ==========================================
# 5. DOCUMENT CLASSIFICATION & CROSS-CHECK
# ==========================================

def classify_document_type(text: str, filename: str) -> str:
    """Classify the type of logistics/trade document automatically."""
    text_lower = text.lower() + " " + filename.lower()
    if "commercial invoice" in text_lower or "invoice" in text_lower or "inv" in text_lower:
        return "Invoice"
    elif "packing list" in text_lower or "packing" in text_lower:
        return "Packing List"
    elif "bill of lading" in text_lower or "lading" in text_lower or "b/l" in text_lower or "waybill" in text_lower:
        return "Bill of Lading"
    elif "contract" in text_lower or "agreement" in text_lower or "purchase order" in text_lower or "p.o" in text_lower:
        return "Contract"
    elif "certificate of origin" in text_lower or "c/o" in text_lower:
        return "Certificate of Origin"
    else:
        return "Other Document"

def normalize_compare_val(val: Any) -> str:
    """Normalize string/numbers for document cross-checking."""
    if not val:
        return ""
    val_str = str(val).lower().strip()
    # Strip non-alphanumeric except dots for float comparison
    val_clean = re.sub(r'[^a-z0-9\.]', '', val_str)
    return val_clean

def perform_document_cross_check(parsed_docs: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Cross-checks extracted data across uploaded documents.
    Prevents false alerts by mapping fields only when present in available documents.
    """
    discrepancies = []
    
    check_rules = [
        ("invoice_number", "Invoice Number"),
        ("contract_number", "Contract Number"),
        ("seller_name", "Seller Name"),
        ("buyer_name", "Buyer Name"),
        ("shipper_name", "Shipper Name"),
        ("consignee_name", "Consignee Name"),
        ("total_amount", "Total Amount"),
        ("gross_weight", "Gross Weight"),
        ("net_weight", "Net Weight"),
        ("port_of_loading", "Port of Loading"),
        ("port_of_discharge", "Port of Discharge")
    ]

    doc_names = list(parsed_docs.keys())
    if len(doc_names) < 2:
        return discrepancies

    for field_key, field_label in check_rules:
        found_values = {}
        for doc_name, doc_info in parsed_docs.items():
            val = doc_info.get("fields", {}).get(field_key)
            if val and "Inferred" not in str(val):
                found_values[doc_name] = val

        if len(found_values) > 1:
            # Compare normalized values
            norm_map = {doc: normalize_compare_val(v) for doc, v in found_values.items()}
            first_norm = list(norm_map.values())[0]

            is_mismatch = False
            for doc, norm_v in norm_map.items():
                if norm_v != first_norm and norm_v != "" and first_norm != "":
                    is_mismatch = True
                    break

            if is_mismatch:
                discrepancies.append({
                    "Field": field_label,
                    "Status": "⚠️ Mismatch / Misaligned",
                    "Details": found_values
                })

    return discrepancies

# ==========================================
# 6. EXCEL EXPORT FUNCTION
# ==========================================

def create_excel_report(parsed_docs: Dict[str, Dict[str, Any]], discrepancies: List[Dict[str, Any]]) -> bytes:
    """Generate Excel report in-memory with sheets for extracted fields and cross-check results."""
    output = io.BytesIO()
    
    # Sheet 1: Extracted Summary
    summary_rows = []
    for doc_name, data in parsed_docs.items():
        row = {
            "File Name": doc_name,
            "Document Type": data.get("doc_type", "Unknown")
        }
        row.update(data.get("fields", {}))
        summary_rows.append(row)

    df_summary = pd.DataFrame(summary_rows)

    # Sheet 2: Cross Check Report
    cross_check_rows = []
    for disc in discrepancies:
        row = {
            "Field Checked": disc["Field"],
            "Status": disc["Status"]
        }
        for doc_k, val_v in disc["Details"].items():
            row[f"Value in ({doc_k})"] = val_v
        cross_check_rows.append(row)

    df_cross_check = pd.DataFrame(cross_check_rows) if cross_check_rows else pd.DataFrame([{"Result": "All fields match across documents"}])

    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_summary.to_excel(writer, sheet_name="Extracted Summary", index=False)
        df_cross_check.to_excel(writer, sheet_name="Cross-Check Analysis", index=False)

    return output.getvalue()

# ==========================================
# 7. STREAMLIT WEB INTERFACE
# ==========================================

def main():
    st.set_page_config(
        page_title="XNK Document Extraction & Cross-Check System",
        page_icon="📑",
        layout="wide",
        initial_sidebar_state="expanded"
    )

    st.title("📑 Hệ Thống Trích Xuất & Kiểm Tra Chéo Chứng Từ XNK (v5 Fixed Full)")
    st.markdown("""
    **Tính năng chính:**
    - **OCR Hybrid:** Kết hợp đọc PDF Native layer & OCR Tesseract đa ngôn ngữ (Anh/Việt) tránh bỏ sót trang scanned.
    - **Phân biệt Thực thể:** Phân biệt rõ ràng Seller/Shipper/Exporter và Buyer/Consignee/Importer.
    - **Kiểm tra Chéo (Cross-check):** Tự động so sánh dữ liệu giữa các chứng từ trong bộ hồ sơ.
    - **Xuất Báo Cáo:** Xuất toàn bộ dữ liệu ra Excel hỗ trợ thẩm định.
    """)

    # Supabase Client & Knowledge Base Setup
    supabase_client = get_supabase_client()
    field_aliases = fetch_knowledge_base_aliases(supabase_client)

    # Sidebar Options
    st.sidebar.header("⚙️ Trạng Thái & Cấu Hình")
    if supabase_client:
        st.sidebar.success("🟢 Supabase Connected")
    else:
        st.sidebar.info("⚪ Offline / Local Mode (Supabase not configured)")

    # Custom Field Mapping File Loader
    if os.path.exists("field_mapping.json"):
        try:
            with open("field_mapping.json", "r", encoding="utf-8") as f:
                custom_aliases = json.load(f)
                field_aliases.update(custom_aliases)
            st.sidebar.success("📂 Loaded custom `field_mapping.json`")
        except Exception as e:
            st.sidebar.error(f"Error loading `field_mapping.json`: {e}")

    # File Upload Section
    st.subheader("1. Tải Lên Bộ Hồ Sơ Xuất Nhập Khẩu (PDF)")
    uploaded_files = st.file_uploader(
        "Tải lên các file PDF chứng từ (Invoice, Packing List, Contract, Bill of Lading, C/O...)",
        type=["pdf"],
        accept_multiple_files=True
    )

    if uploaded_files:
        st.info(f"📁 Đã chọn {len(uploaded_files)} tệp chứng từ.")
        
        if st.button("🚀 Thực Hiện Trích Xuất & Kiểm Tra Chéo", type="primary"):
            parsed_docs = {}
            progress_bar = st.progress(0)

            for idx, file in enumerate(uploaded_files):
                st.text(f"Đang xử lý: {file.name}...")
                pdf_bytes = file.read()

                # Step 1: Extract PDF Text + Hybrid OCR
                extracted_text, layout_info = extract_pdf_with_hybrid_ocr(pdf_bytes)
                
                # Step 2: Classify Document Type
                doc_type = classify_document_type(extracted_text, file.name)

                # Step 3: Extract Fields by Context & Aliases
                fields = extract_fields_by_context(extracted_text, field_aliases)

                parsed_docs[file.name] = {
                    "doc_type": doc_type,
                    "fields": fields,
                    "full_text": extracted_text,
                    "layout": layout_info
                }

                progress_bar.progress((idx + 1) / len(uploaded_files))

            st.success("✅ Trích xuất và phân tích hoàn tất!")

            # Step 4: Display Results in Tabs
            st.subheader("2. Kết Quả Trích Xuất Chi Tiết")
            tabs = st.tabs([f"{f.name} ({parsed_docs[f.name]['doc_type']})" for f in uploaded_files])

            for tab, file in zip(tabs, uploaded_files):
                doc_data = parsed_docs[file.name]
                with tab:
                    c1, c2 = st.columns([1, 1])
                    with c1:
                        st.markdown(f"### Dữ Liệu Trích Xuất (`{doc_data['doc_type']}`)")
                        if doc_data["fields"]:
                            df_fields = pd.DataFrame(
                                list(doc_data["fields"].items()), 
                                columns=["Trường Thông Tin", "Giá Trị Trích Xuất"]
                            )
                            st.dataframe(df_fields, use_container_width=True)
                        else:
                            st.warning("Không tìm thấy các trường thông tin phù hợp trong file này.")

                    with c2:
                        st.markdown("### Văn Bản Gốc / Kết Quả OCR")
                        st.text_area("Full Extracted Text", doc_data["full_text"], height=350)

            # Step 5: Display Cross-Check Analysis
            st.subheader("3. Báo Cáo Đối Chiếu Chéo (Cross-Check Report)")
            discrepancies = perform_document_cross_check(parsed_docs)

            if discrepancies:
                st.warning("⚠️ Phát hiện sự không đồng nhất dữ liệu giữa các chứng từ:")
                for disc in discrepancies:
                    with st.expander(f"🔴 {disc['Field']} - {disc['Status']}"):
                        for doc_k, val_v in disc["Details"].items():
                            st.write(f"- **{doc_k}**: `{val_v}`")
            else:
                st.success("🎉 Tất cả các trường đối chiếu giữa các chứng từ hoàn toàn đồng nhất!")

            # Step 6: Excel Export
            st.subheader("4. Xuất Báo Cáo Thẩm Định")
            excel_bytes = create_excel_report(parsed_docs, discrepancies)
            
            st.download_button(
                label="📥 Tải Xuất Báo Cáo Excel (.xlsx)",
                data=excel_bytes,
                file_name=f"XNK_CrossCheck_Report_{datetime.date.today()}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

            # Store in Supabase if configured
            if supabase_client:
                try:
                    for fname, fdata in parsed_docs.items():
                        supabase_client.table("extracted_fields").insert({
                            "filename": fname,
                            "doc_type": fdata["doc_type"],
                            "extracted_data": fdata["fields"],
                            "created_at": datetime.datetime.utcnow().isoformat()
                        }).execute()
                    st.info("💾 Đã lưu kết quả trích xuất vào database Supabase.")
                except Exception as e:
                    logging.error(f"Failed to save results to Supabase: {e}")

if __name__ == "__main__":
    main()
