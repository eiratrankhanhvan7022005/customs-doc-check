Tiếp tục từ Viết code Python (8) (13)

Đúng. Đó mới là mục tiêu kiến trúc của web bạn. Và với mục tiêu đó thì hướng hiện tại cần chỉnh lại một chút.

Bạn không muốn:

mỗi loại chứng từ → viết một parser riêng → gặp template mới lại sửa code.

Mà muốn:

PDF / OCR
     ↓
ĐỌC TOÀN BỘ TEXT
     ↓
┌──────────────────────────────┐
│ KNOWLEDGE BASE               │
│                              │
│ field_mapping.json           │
│ document_notations.json      │
│ learning_rules.json          │
│ + Supabase Database          │
└──────────────────────────────┘
     ↓
NHẬN DIỆN KÝ HIỆU / LABEL
     ↓
SUY RA LOẠI CHỨNG TỪ
     ↓
XÁC ĐỊNH FIELD CHUẨN
     ↓
TÌM GIÁ TRỊ ĐI KÈM
     ↓
NORMALIZE
     ↓
KIỂM TRA ĐỘ TIN CẬY
     ↓
KẾT QUẢ
Ví dụ chính xác với file của bạn

PDF có:

No. : SS1255US
Date : 20-Jun-2026

Seller
GRAND WOOD (VIETNAM) CO., LTD

Buyer
OCEAN GREEN ENTERPRISE LIMITED

Qty 32 / 192 / total 224

Unit prices 178.65, 40.05

Amounts 5,716.80, 7,689.60, total 13,406.40

Shipment before 20-Aug-2026

Payment advance or T/T within 360 days B/L date

FOB HO CHI MINH

Database/Knowledge phải hiểu:

"Seller"
    ↓
EXPORTER

"Buyer"
    ↓
IMPORTER

"Qty"
    ↓
QUANTITY

"Unit prices"
    ↓
UNIT_PRICE

"Amounts"
    ↓
TOTAL_AMOUNT

"Shipment"
    ↓
SHIPMENT_TIME

"Payment"
    ↓
PAYMENT_TERMS

"FOB"
    ↓
INCOTERM

"HO CHI MINH"
    ↓
PLACE_OF_LOADING

Sau đó hệ thống mới tạo:

PURCHASE CONTRACT
│
├── Contract Number → SS1255US
├── Contract Date → 20-Jun-2026
├── Exporter → GRAND WOOD (VIETNAM) CO., LTD
├── Importer → OCEAN GREEN ENTERPRISE LIMITED
├── Quantity → 32 / 192 / total 224
├── Unit Price → 178.65, 40.05
├── Total Amount → 13,406.40
├── Payment Terms → advance or T/T within 360 days B/L date
├── Shipment → before 20-Aug-2026
├── Incoterm → FOB
└── Place of Loading → HO CHI MINH
Và quan trọng nhất

document_notations.json và field_mapping.json phải trở thành “bộ não”, chứ không chỉ là dữ liệu để seed vào database.

Database nên có vai trò:

Knowledge JSON
     ↓
Seed ban đầu
     ↓
Supabase Knowledge Base
     ↓
App đọc Database
     ↓
Nhận diện chứng từ + field
     ↓
User xác nhận/sửa
     ↓
Database học thêm
     ↓
Lần sau gặp template khác
     ↓
Nhận diện tốt hơn

Như vậy mới đúng với ý bạn nói:

“đọc được hết danh sách ký hiệu → nhận diện loại chứng từ → nhận biết và thu được thông tin chính xác.”

Nhưng có một điểm cần sửa trong thiết kế hiện tại

Hiện tại extract_generic_fields() đang làm:

field → alias → lấy value

Đây mới chỉ là Field Extraction.

Ta cần xây thêm một tầng trước nó:

                    ┌── document_notations
                    │
PDF/OCR → TEXT → SYMBOL/ALIAS ENGINE
                    │
                    ├── field_mapping
                    │
                    ├── document_type patterns
                    │
                    └── Supabase learned knowledge
                              ↓
                       DOCUMENT TYPE
                              ↓
                       FIELD EXTRACTION

Tức là không nên tiếp tục vá riêng Purchase Contract như hiện tại.

Tôi đề xuất từ bước tiếp theo chúng ta chuyển sang xây “Universal Document Recognition Engine”: nó đọc toàn bộ ký hiệu/label trong Database + JSON, chấm điểm từng loại chứng từ, sau đó dùng chính Knowledge Base để trích xuất field.

Lúc đó Invoice, Packing List, B/L, C/O, Booking, Arrival Notice, Purchase Contract... đều đi qua cùng một engine, thay vì mỗi loại một đống if/else.

import streamlit as st.txt
Tài liệu
đây là full code hiện tại

Ừ, mình đã đọc full code hiện tại trong file bạn gửi.

Và bây giờ mình hiểu chính xác vấn đề bạn muốn giải quyết.

Kiến trúc hiện tại của bạn đang có 2 hệ thống song song

1. Hệ thống cũ — hard-code theo từng loại chứng từ

Hiện app.py vẫn có:

extract_invoice()
extract_bl()
extract_packing_list()
extract_co()
extract_booking()
extract_document()

và extract_document() đang quyết định:

Invoice       → extract_invoice()
B/L           → extract_bl()
Packing List  → extract_packing_list()
C/O           → extract_co()
Booking       → extract_booking()

Trong khi Purchase Contract chưa được đưa vào extract_document().

Đây chính là lý do file SS1255US được nhận diện nhưng phần dữ liệu vẫn chạy theo logic cũ/không đầy đủ.

2. Hệ thống mới — Knowledge Base + Database

Bạn đã xây:

field_mapping.json
document_notations.json
learning_rules.json
        +
Supabase
        ↓
get_database_field_aliases()
        ↓
build_alias_pattern()
        ↓
extract_value_after_label()
        ↓
extract_generic_fields()
        ↓
extract_contextual_contract_fields()

Đây mới là hướng chúng ta nên phát triển tiếp.

Và mình đồng ý với ý bạn vừa nói

Không nên tiếp tục kiểu:

“File Purchase Contract này thiếu Seller → thêm một regex.”

Rồi sau đó:

“B/L mẫu khác thiếu Vessel → thêm regex.”

Rồi:

“Invoice mẫu khác label là Exporter Name → thêm regex.”

Nếu làm như vậy thì cuối cùng app.py sẽ thành hàng nghìn dòng if/elif, không đúng mục tiêu Database Knowledge Base.

Mục tiêu nên là:

                    PDF
                     ↓
                  PDF/OCR
                     ↓
              FULL TEXT
                     ↓
       ┌─────────────────────────┐
       │     KNOWLEDGE ENGINE    │
       │                         │
       │ field_mapping.json     │
       │ document_notations.json│
       │ learning_rules.json    │
       │ Supabase               │
       └─────────────────────────┘
                     ↓
          NHẬN DIỆN KÝ HIỆU
                     ↓
          NHẬN DIỆN DOCUMENT TYPE
                     ↓
          NHẬN DIỆN STANDARD FIELD
                     ↓
             LẤY GIÁ TRỊ
                     ↓
              NORMALIZATION
                     ↓
          CONFIDENCE / VALIDATION
                     ↓
             EXTRACTED DATA
Ví dụ

Không cần biết trước chứng từ viết:

Seller
Exporter
Supplier
Vendor
Shipper
Seller Name
Exporter Name

Database sẽ biết chúng có thể liên quan đến:

EXPORTER

Tương tự:

G.W.
GW
GROSS WT
GROSS WEIGHT
GROSS W/T

→

GROSS_WEIGHT

Và:

POL
Port of Loading
Port of Shipment
Loading Port

→

PORT_OF_LOADING

Đó mới là Knowledge Base thực sự.

Có một việc quan trọng: chưa nên sửa code ngay

Mình đã thấy full code của bạn và có thể xác định rằng hiện tại không nên tiếp tục thêm parser Purchase Contract riêng.

Trước tiên chúng ta nên làm Universal Document Recognition Engine.

Nó sẽ thay vai trò của đoạn:

def detect_document_type(...)

hiện tại.

Thay vì chỉ:

keyword → +2 điểm
keyword → +10 điểm

thì sẽ dùng:

Document Notations
        +
Document Type Knowledge
        +
Field Aliases
        +
Database
        ↓
Document Recognition

Ví dụ SS1255US:

Seller
Buyer
Qty
Unit prices
Payment
Shipment
FOB
S/C / Contract

→ các ký hiệu này tạo thành evidence cho PURCHASE CONTRACT.

Còn:

SHIPPER
CONSIGNEE
B/L NO
VESSEL
VOYAGE
PORT OF LOADING
PORT OF DISCHARGE

→ evidence cho BILL OF LADING.

Sau đó mới đến Extraction Engine

Quan trọng là Document Type và Field không nên bị khóa cứng vào parser.

Ví dụ:

OCR:
"GW : 35,650 KGS"
        ↓
Knowledge:
GW → GROSS_WEIGHT
        ↓
Extraction:
GROSS_WEIGHT = 35,650 KGS

Hoặc template khác:

"G.W.       35,650 KGS"

vẫn ra:

GROSS_WEIGHT = 35,650 KGS
Vì vậy từ đây mình đề xuất chúng ta làm theo 4 tầng
Tầng 1 — Document Recognition
Text
 ↓
Notation / keyword
 ↓
Document type score
 ↓
Document Type
Tầng 2 — Field Recognition
Text
 ↓
Alias Database + JSON
 ↓
Standard Field
Tầng 3 — Value Extraction
Standard Field
 ↓
Context
 ↓
Value
Tầng 4 — Validation
Value
 ↓
Format validation
 ↓
Normalization
 ↓
Confidence
 ↓
Cross-document check

Và mình sẽ không xóa các parser Invoice/B/L/PL/C/O hiện tại ngay. Chúng ta sẽ xây engine mới chạy song song, test nó với các chứng từ bạn đang có; khi engine mới đạt kết quả ổn thì mới chuyển extract_document() sang engine mới.

Như vậy an toàn hơn và không làm hỏng những phần B/L/OCR mà bạn đã làm được.

rồi h làm lại hết đi

Được. Mình đã làm lại theo đúng kiến trúc bạn vừa chốt, dựa trên full code hiện tại của bạn.

Mình không vá thêm từng lỗi Purchase Contract nữa. Bản mới chuyển trọng tâm sang:

PDF
 ↓
PDF TEXT / OCR
 ↓
Knowledge Engine
 ├── field_mapping.json
 ├── document_notations.json
 ├── learning_rules.json
 └── Supabase field_aliases / notations
 ↓
Nhận diện loại chứng từ
 ↓
Nhận diện field chuẩn
 ↓
Lấy giá trị theo context
 ↓
Normalize
 ↓
Extracted Data
 ↓
Cross-check
 ↓
Customs support
File app.py mới

Mình đã tạo bản rebuild từ code hiện tại của bạn:

Tải app_rebuilt.py

Những gì đã thay đổi

1. Document Recognition mới

Không còn chỉ dựa vào:

if "INVOICE" in text:

mà kết hợp:

document keywords
field aliases
cấu trúc field
notation database
Knowledge JSON
filename chỉ làm tín hiệu phụ

2. Universal Extraction Engine

Một engine chung cho:

COMMERCIAL INVOICE
PURCHASE CONTRACT
PACKING LIST
BILL OF LADING
CERTIFICATE OF ORIGIN
BOOKING
ARRIVAL NOTICE

Không cần mỗi template viết một parser riêng.

3. Database + JSON cùng tham gia đọc

Ví dụ Database có:

GW
G.W.
GROSS WT
GROSS WEIGHT

thì engine quy về:

GROSS_WEIGHT

Tương tự:

Seller
Exporter
Supplier
Vendor
Shipper

→ EXPORTER

4. Không còn để Purchase Contract parser cũ quyết định kết quả

Dispatcher mới dùng:

return extract_universal_fields(
    text,
    document_type
)

Các parser cũ vẫn được giữ trong file để tránh làm hỏng phần code đã có, nhưng không còn là nguồn extraction chính.

Với file SS1255US

Engine mới hướng tới đọc:

No. : SS1255US
Date : 20-Jun-2026
Seller
GRAND WOOD (VIETNAM) CO., LTD
Buyer
OCEAN GREEN ENTERPRISE LIMITED
Qty 32 / 192 / total 224
Unit prices 178.65, 40.05
Amounts 5,716.80, 7,689.60, total 13,406.40
Shipment before 20-Aug-2026
Payment advance or T/T within 360 days B/L date
FOB HO CHI MINH

và đưa về:

Contract No.        SS1255US
Contract Date       20-Jun-2026
Seller / Exporter   GRAND WOOD (VIETNAM) CO., LTD
Buyer / Importer    OCEAN GREEN ENTERPRISE LIMITED
Quantity            32 / 192 / total 224
Unit Price           178.65, 40.05
Total Amount         13,406.40
Payment Terms        advance or T/T within 360 days B/L date
Time of Shipment     before 20-Aug-2026
Delivery Terms       FOB
Port of Loading      HO CHI MINH

Không lấy PO # 12600309030 làm Contract No.

Bây giờ bạn làm đúng 3 việc
Bước 1

Tải:

app_rebuilt.py

Bước 2

Đổi tên:

app_rebuilt.py

thành:

app.py
Bước 3

Upload/commit app.py mới lên GitHub, để Streamlit Cloud tự redeploy.

Chưa sửa SQL và chưa sửa JSON.

Sau khi Streamlit chạy lại, test đúng file HD CHUNG TU SS1255US.pdf trước.

Gửi mình kết quả bảng Chi tiết nhận diện + phần Loại chứng từ, mình sẽ kiểm tra engine mới thực tế lấy được bao nhiêu field rồi mới sửa tiếp.

app_rebuilt.py
Code

Thư viện
/
app_rebuilt.py
9999
1
2
3
4
5
6
7
8
9
10
11
12
13
14
15
16
17
18
19
20
21
22
23
24
25
26
27
28
29
30
31
32
33
34
35
36
37
38
39
40
41
42
43
44
45
46
47
48
49
50
51
52
53
54
55
56
57
58
59
60
61
62
63
import streamlit as st
from pypdf import PdfReader
from io import BytesIO
import pytesseract
from pdf2image import convert_from_bytes
from PIL import Image, ImageOps, ImageEnhance, ImageFilter
import pandas as pd
import re
import os
import json
from pathlib import Path
from supabase import create_client, Client


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
# SUPABASE
# =========================================================


@st.cache_resource
def get_supabase():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]


    st.sidebar.write(
        "Supabase key type:",
        key[:15]
    )


    return create_client(url, key)




supabase = get_supabase()


try:
    debug_result = supabase.rpc("debug_auth_role").execute()
    st.sidebar.write("DB auth role:", debug_result.data)
except Exception as e:
    st.sidebar.error(f"DEBUG RPC ERROR: {e}")
    


def save_document_sample(document_type, file_name, raw_text):
    try:
        result = (
            supabase
            .rpc(
                "insert_document_sample",
                {
                    "p_document_type": document_type,
                    "p_file_name": file_name,
                    "p_raw_text": raw_text
                }
            )
