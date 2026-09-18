import os
import re
import json
import unicodedata
from io import BytesIO
from pathlib import Path
from datetime import datetime

import streamlit as st
import pandas as pd

from supabase import create_client
from pypdf import PdfReader

import fitz  # PyMuPDF

from pdf2image import convert_from_bytes

from PIL import (
    Image,
    ImageOps,
    ImageEnhance,
    ImageFilter,
)

import pytesseract
from pytesseract import Output


# ============================================================
# CONFIG
# ============================================================

st.set_page_config(
    page_title="CustomsDoc Check",
    page_icon="📄",
    layout="wide",
)

EMPTY = "Không tìm thấy"

OCR_DPI = 250
MAX_OCR_PAGES = 30

BASE_DIR = Path(__file__).resolve().parent
KNOWLEDGE_DIR = BASE_DIR / "knowledge"


# ============================================================
# SUPABASE
# ============================================================

@st.cache_resource
def get_supabase():

    try:
        url = st.secrets.get("SUPABASE_URL", "")
        key = st.secrets.get("SUPABASE_KEY", "")

        if not url or not key:
            return None

        return create_client(url, key)

    except Exception:
        return None


supabase = get_supabase()


# ============================================================
# BASIC HELPERS
# ============================================================

def safe_text(value):

    if value is None:
        return ""

    return str(value).strip()


def normalize_text(text):

    text = safe_text(text)

    text = text.replace("\x00", " ")

    text = text.replace("\r\n", "\n")
    text = text.replace("\r", "\n")

    text = re.sub(r"[ \t]+", " ", text)

    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def present(value):

    value = safe_text(value)

    return value not in (
        "",
        EMPTY,
        "[]",
        "{}",
        "None",
        "NULL",
    )


def normalize_label(text):

    text = unicodedata.normalize(
        "NFKC",
        safe_text(text)
    )

    text = text.upper()

    text = re.sub(
        r"[^A-Z0-9]+",
        " ",
        text
    )

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text.strip()


# ============================================================
# KNOWLEDGE FILES
# ============================================================

@st.cache_data
def load_json_knowledge(filename):

    path = KNOWLEDGE_DIR / filename

    if not path.exists():
        return {}

    try:

        with open(
            path,
            "r",
            encoding="utf-8"
        ) as f:

            return json.load(f)

    except Exception:

        return {}


FIELD_MAPPING_KB = load_json_knowledge(
    "field_mapping.json"
)

DOCUMENT_NOTATIONS_KB = load_json_knowledge(
    "document_notations.json"
)

LEARNING_RULES_KB = load_json_knowledge(
    "learning_rules.json"
)


# ============================================================
# DATABASE LOADERS
# ============================================================

@st.cache_data(ttl=300)
def load_database_aliases():

    if supabase is None:
        return []

    try:

        result = (
            supabase
            .table("field_aliases")
            .select("*")
            .execute()
        )

        return result.data or []

    except Exception:

        return []


@st.cache_data(ttl=300)
def load_database_notations():

    if supabase is None:
        return []

    try:

        result = (
            supabase
            .table("document_notations")
            .select("*")
            .execute()
        )

        return result.data or []

    except Exception:

        return []


@st.cache_data(ttl=300)
def load_database_corrections():

    if supabase is None:
        return []

    try:

        result = (
            supabase
            .table("confirmed_corrections")
            .select("*")
            .execute()
        )

        return result.data or []

    except Exception:

        return []


def get_db_aliases(
    standard_field,
    document_type=None
):

    rows = load_database_aliases()

    result = []

    for row in rows:

        db_field = safe_text(
            row.get("standard_field")
        ).upper()

        if db_field != standard_field.upper():
            continue

        db_doc = safe_text(
            row.get("document_type")
        ).upper()

        if (
            document_type
            and db_doc
            and db_doc not in (
                document_type.upper(),
                "ALL",
                "*",
            )
        ):
            continue

        alias = safe_text(
            row.get("raw_label")
        )

        if alias:
            result.append(alias)

    return result


def get_kb_aliases(
    standard_field,
    document_type=None
):

    result = []

    if not isinstance(
        FIELD_MAPPING_KB,
        dict
    ):
        return result

    # Format:
    # {
    #   "EXPORTER": [...]
    # }

    item = FIELD_MAPPING_KB.get(
        standard_field
    )

    if isinstance(item, list):

        result.extend(
            str(x)
            for x in item
        )

    elif isinstance(item, dict):

        aliases = item.get(
            "aliases",
            []
        )

        if isinstance(
            aliases,
            list
        ):
            result.extend(
                str(x)
                for x in aliases
            )

    # Format:
    # {
    #   "fields": {
    #       "EXPORTER": {
    #           "aliases": [...]
    #       }
    #   }
    # }

    fields = FIELD_MAPPING_KB.get(
        "fields"
    )

    if isinstance(
        fields,
        dict
    ):

        item = fields.get(
            standard_field,
            {}
        )

        if isinstance(
            item,
            dict
        ):

            aliases = item.get(
                "aliases",
                []
            )

            if isinstance(
                aliases,
                list
            ):
                result.extend(
                    str(x)
                    for x in aliases
                )

    return result

# ============================================================
# STANDARD FIELD DEFINITIONS
# ============================================================

FIELD_DEFINITIONS = {

    # --------------------------------------------------------
    # PARTIES
    # --------------------------------------------------------

    "EXPORTER": {
        "label": "Seller / Exporter / Shipper",
        "aliases": [
            "SELLER",
            "EXPORTER",
            "SHIPPER",
            "SUPPLIER",
            "FROM",
        ],
        "type": "party",
    },

    "IMPORTER": {
        "label": "Buyer / Importer",
        "aliases": [
            "BUYER",
            "IMPORTER",
            "PURCHASER",
        ],
        "type": "party",
    },

    "CONSIGNEE": {
        "label": "Consignee",
        "aliases": [
            "CONSIGNEE",
        ],
        "type": "party",
    },

    "NOTIFY_PARTY": {
        "label": "Notify Party",
        "aliases": [
            "NOTIFY PARTY",
            "NOTIFY",
        ],
        "type": "party",
    },

    "EXPORTER_ADDRESS": {
        "label": "Exporter Address",
        "aliases": [
            "SELLER ADDRESS",
            "EXPORTER ADDRESS",
            "SHIPPER ADDRESS",
        ],
        "type": "address",
    },

    "IMPORTER_ADDRESS": {
        "label": "Importer Address",
        "aliases": [
            "BUYER ADDRESS",
            "IMPORTER ADDRESS",
        ],
        "type": "address",
    },

    "CONSIGNEE_ADDRESS": {
        "label": "Consignee Address",
        "aliases": [
            "CONSIGNEE ADDRESS",
        ],
        "type": "address",
    },


    # --------------------------------------------------------
    # DOCUMENT IDENTIFICATION
    # --------------------------------------------------------

    "CONTRACT_NUMBER": {
        "label": "Contract No.",
        "aliases": [
            "CONTRACT NO",
            "CONTRACT NO.",
            "CONTRACT NUMBER",
            "CONTRACT #",
        ],
        "type": "id",
    },

    "CONTRACT_DATE": {
        "label": "Contract Date",
        "aliases": [
            "CONTRACT DATE",
            "DATE OF CONTRACT",
        ],
        "type": "date",
    },

    "INVOICE_NUMBER": {
        "label": "Invoice No.",
        "aliases": [
            "INVOICE NO",
            "INVOICE NO.",
            "INVOICE NUMBER",
            "INVOICE #",
        ],
        "type": "id",
    },

    "INVOICE_DATE": {
        "label": "Invoice Date",
        "aliases": [
            "INVOICE DATE",
            "DATE OF INVOICE",
        ],
        "type": "date",
    },

    "PACKING_LIST_NUMBER": {
        "label": "Packing List No.",
        "aliases": [
            "PACKING LIST NO",
            "PACKING LIST NO.",
            "PACKING LIST NUMBER",
            "PL NO",
        ],
        "type": "id",
    },

    "BOOKING_NUMBER": {
        "label": "Booking No.",
        "aliases": [
            "BOOKING NO",
            "BOOKING NO.",
            "BOOKING NUMBER",
            "BOOKING #",
        ],
        "type": "id",
    },

    "BL_NUMBER": {
        "label": "B/L No.",
        "aliases": [
            "B/L NO",
            "B/L NO.",
            "BL NO",
            "BILL OF LADING NO",
            "B/L NUMBER",
        ],
        "type": "id",
    },

    "CO_NUMBER": {
        "label": "C/O No.",
        "aliases": [
            "C/O NO",
            "C/O NO.",
            "CO NO",
            "CERTIFICATE OF ORIGIN NO",
        ],
        "type": "id",
    },

    "PO_NUMBER": {
        "label": "PO No.",
        "aliases": [
            "PO NO",
            "PO NO.",
            "PO NUMBER",
            "PURCHASE ORDER NO",
            "P.O. NO",
        ],
        "type": "id",
    },


    # --------------------------------------------------------
    # CARGO
    # --------------------------------------------------------

    "DESCRIPTION": {
        "label": "Description of Goods",
        "aliases": [
            "DESCRIPTION OF GOODS",
            "DESCRIPTION",
            "GOODS DESCRIPTION",
            "PRODUCT DESCRIPTION",
            "ITEM DESCRIPTION",
            "COMMODITY",
        ],
        "type": "description",
    },

    "HS_CODE": {
        "label": "HS Code",
        "aliases": [
            "HS CODE",
            "HS",
            "H.S. CODE",
            "HARMONIZED SYSTEM CODE",
        ],
        "type": "hs",
    },

    "COUNTRY_OF_ORIGIN": {
        "label": "Country of Origin",
        "aliases": [
            "COUNTRY OF ORIGIN",
            "ORIGIN",
            "COUNTRY OF ORIGIN OF GOODS",
        ],
        "type": "country",
    },

    "QUANTITY": {
        "label": "Quantity",
        "aliases": [
            "QUANTITY",
            "QTY",
            "Q'TY",
            "QTY.",
            "TOTAL QTY",
            "NO. OF UNITS",
        ],
        "type": "number",
    },

    "PACKAGE_COUNT": {
        "label": "Package Count",
        "aliases": [
            "NO. OF PACKAGES",
            "NUMBER OF PACKAGES",
            "TOTAL PACKAGES",
            "TOTAL PKGS",
            "NO OF PKGS",
            "PACKAGES",
            "PKGS",
        ],
        "type": "number",
    },

    "GROSS_WEIGHT": {
        "label": "Gross Weight",
        "aliases": [
            "GROSS WEIGHT",
            "GROSS WT",
            "G.W.",
            "GW",
            "GROSS WT.",
        ],
        "type": "weight",
    },

    "NET_WEIGHT": {
        "label": "Net Weight",
        "aliases": [
            "NET WEIGHT",
            "NET WT",
            "N.W.",
            "NW",
            "NET WT.",
        ],
        "type": "weight",
    },

    "TARE_WEIGHT": {
        "label": "Tare Weight",
        "aliases": [
            "TARE",
            "TARE WEIGHT",
            "TARE WT",
        ],
        "type": "weight",
    },

    "MEASUREMENT": {
        "label": "Measurement",
        "aliases": [
            "MEASUREMENT",
            "MEAS",
            "CBM",
            "VOLUME",
            "VOL",
            "M3",
            "M³",
            "CBFT",
        ],
        "type": "measurement",
    },


    # --------------------------------------------------------
    # COMMERCIAL
    # --------------------------------------------------------

    "UNIT_PRICE": {
        "label": "Unit Price",
        "aliases": [
            "UNIT PRICE",
            "UNITPRICE",
            "PRICE/UNIT",
            "PRICE PER UNIT",
        ],
        "type": "money",
    },

    "TOTAL_AMOUNT": {
        "label": "Total Amount",
        "aliases": [
            "TOTAL AMOUNT",
            "GRAND TOTAL",
            "TOTAL VALUE",
            "TOTAL",
            "AMOUNT",
        ],
        "type": "money",
    },

    "CURRENCY": {
        "label": "Currency",
        "aliases": [
            "CURRENCY",
            "CURRENCY CODE",
        ],
        "type": "currency",
    },

    "INCOTERMS": {
        "label": "Incoterm",
        "aliases": [
            "INCOTERM",
            "INCOTERMS",
            "TRADE TERM",
            "TERMS OF DELIVERY",
        ],
        "type": "incoterm",
    },

    "PAYMENT_TERMS": {
        "label": "Payment Terms",
        "aliases": [
            "PAYMENT TERMS",
            "TERMS OF PAYMENT",
            "PAYMENT",
            "PAYMENT CONDITION",
        ],
        "type": "text",
    },


    # --------------------------------------------------------
    # SHIPPING
    # --------------------------------------------------------

    "VESSEL": {
        "label": "Vessel",
        "aliases": [
            "VESSEL",
            "VESSEL NAME",
            "MOTHER VESSEL",
        ],
        "type": "vessel",
    },

    "VOYAGE": {
        "label": "Voyage",
        "aliases": [
            "VOYAGE",
            "VOYAGE NO",
            "VOYAGE NUMBER",
        ],
        "type": "text",
    },

    "VESSEL_VOYAGE": {
        "label": "Vessel / Voyage",
        "aliases": [
            "VESSEL/VOYAGE",
            "VESSEL / VOYAGE",
            "VESSEL VOYAGE",
        ],
        "type": "text",
    },

    "CONTAINER_NUMBER": {
        "label": "Container No.",
        "aliases": [
            "CONTAINER NO",
            "CONTAINER NO.",
            "CONTAINER NUMBER",
            "CONTAINER",
        ],
        "type": "container",
    },

    "SEAL_NUMBER": {
        "label": "Seal No.",
        "aliases": [
            "SEAL NO",
            "SEAL NO.",
            "SEAL NUMBER",
            "SEAL",
        ],
        "type": "seal",
    },

    "PORT_OF_LOADING": {
        "label": "Port of Loading",
        "aliases": [
            "PORT OF LOADING",
            "POL",
            "LOAD PORT",
            "LOADING PORT",
            "PLACE OF LOADING",
        ],
        "type": "port",
    },

    "PORT_OF_DISCHARGE": {
        "label": "Port of Discharge",
        "aliases": [
            "PORT OF DISCHARGE",
            "POD",
            "DISCHARGE PORT",
            "DESTINATION PORT",
            "PLACE OF DISCHARGE",
        ],
        "type": "port",
    },

    "FINAL_DESTINATION": {
        "label": "Final Destination",
        "aliases": [
            "FINAL DESTINATION",
            "PLACE OF DESTINATION",
            "DESTINATION",
        ],
        "type": "port",
    },

    "DELIVERY_TERMS": {
        "label": "Delivery Terms",
        "aliases": [
            "DELIVERY TERMS",
            "DELIVERY CONDITION",
        ],
        "type": "text",
    },

    "TIME_OF_SHIPMENT": {
        "label": "Time of Shipment",
        "aliases": [
            "TIME OF SHIPMENT",
            "SHIPMENT DATE",
            "SHIPMENT PERIOD",
            "LATEST SHIPMENT",
            "SHIPMENT",
        ],
        "type": "text",
    },

    "ETA": {
        "label": "ETA",
        "aliases": [
            "ETA",
            "ESTIMATED TIME OF ARRIVAL",
        ],
        "type": "date",
    },

    "ETD": {
        "label": "ETD",
        "aliases": [
            "ETD",
            "ESTIMATED TIME OF DEPARTURE",
        ],
        "type": "date",
    },
}


# ============================================================
# DOCUMENT FIELD SCOPE
# ============================================================

DOCUMENT_FIELD_SCOPE = {

    "PURCHASE CONTRACT": {
        "CONTRACT_NUMBER",
        "CONTRACT_DATE",
        "EXPORTER",
        "IMPORTER",
        "CONSIGNEE",
        "EXPORTER_ADDRESS",
        "IMPORTER_ADDRESS",
        "CONSIGNEE_ADDRESS",
        "DESCRIPTION",
        "QUANTITY",
        "PACKAGE_COUNT",
        "UNIT_PRICE",
        "TOTAL_AMOUNT",
        "CURRENCY",
        "INCOTERMS",
        "PAYMENT_TERMS",
        "PO_NUMBER",
        "PORT_OF_LOADING",
        "FINAL_DESTINATION",
        "TIME_OF_SHIPMENT",
    },

    "COMMERCIAL INVOICE": {
        "INVOICE_NUMBER",
        "INVOICE_DATE",
        "CONTRACT_NUMBER",
        "CONTRACT_DATE",
        "EXPORTER",
        "IMPORTER",
        "CONSIGNEE",
        "NOTIFY_PARTY",
        "EXPORTER_ADDRESS",
        "IMPORTER_ADDRESS",
        "CONSIGNEE_ADDRESS",
        "DESCRIPTION",
        "HS_CODE",
        "COUNTRY_OF_ORIGIN",
        "QUANTITY",
        "PACKAGE_COUNT",
        "GROSS_WEIGHT",
        "NET_WEIGHT",
        "TARE_WEIGHT",
        "MEASUREMENT",
        "UNIT_PRICE",
        "TOTAL_AMOUNT",
        "CURRENCY",
        "INCOTERMS",
        "PAYMENT_TERMS",
        "PO_NUMBER",
        "BL_NUMBER",
        "CONTAINER_NUMBER",
        "SEAL_NUMBER",
        "PORT_OF_LOADING",
        "PORT_OF_DISCHARGE",
    },

    "PACKING LIST": {
        "PACKING_LIST_NUMBER",
        "INVOICE_NUMBER",
        "CONTRACT_NUMBER",
        "EXPORTER",
        "IMPORTER",
        "CONSIGNEE",
        "NOTIFY_PARTY",
        "EXPORTER_ADDRESS",
        "IMPORTER_ADDRESS",
        "CONSIGNEE_ADDRESS",
        "DESCRIPTION",
        "HS_CODE",
        "COUNTRY_OF_ORIGIN",
        "QUANTITY",
        "PACKAGE_COUNT",
        "GROSS_WEIGHT",
        "NET_WEIGHT",
        "TARE_WEIGHT",
        "MEASUREMENT",
        "CONTAINER_NUMBER",
        "SEAL_NUMBER",
    },

    "BILL OF LADING": {
        "BL_NUMBER",
        "EXPORTER",
        "CONSIGNEE",
        "NOTIFY_PARTY",
        "EXPORTER_ADDRESS",
        "IMPORTER_ADDRESS",
        "CONSIGNEE_ADDRESS",
        "DESCRIPTION",
        "PACKAGE_COUNT",
        "GROSS_WEIGHT",
        "NET_WEIGHT",
        "TARE_WEIGHT",
        "MEASUREMENT",
        "CONTAINER_NUMBER",
        "SEAL_NUMBER",
        "VESSEL",
        "VOYAGE",
        "VESSEL_VOYAGE",
        "PORT_OF_LOADING",
        "PORT_OF_DISCHARGE",
        "FINAL_DESTINATION",
        "ETA",
        "ETD",
        "DELIVERY_TERMS",
    },

    "BOOKING": {
        "BOOKING_NUMBER",
        "EXPORTER",
        "IMPORTER",
        "CONSIGNEE",
        "CONTAINER_NUMBER",
        "SEAL_NUMBER",
        "VESSEL",
        "VOYAGE",
        "VESSEL_VOYAGE",
        "PORT_OF_LOADING",
        "PORT_OF_DISCHARGE",
        "FINAL_DESTINATION",
        "ETA",
        "ETD",
    },

    "CERTIFICATE OF ORIGIN": {
        "CO_NUMBER",
        "EXPORTER",
        "IMPORTER",
        "CONSIGNEE",
        "EXPORTER_ADDRESS",
        "IMPORTER_ADDRESS",
        "CONSIGNEE_ADDRESS",
        "DESCRIPTION",
        "HS_CODE",
        "COUNTRY_OF_ORIGIN",
        "QUANTITY",
        "PACKAGE_COUNT",
        "INVOICE_NUMBER",
        "CONTRACT_NUMBER",
    },

    "ARRIVAL NOTICE": {
        "BL_NUMBER",
        "EXPORTER",
        "CONSIGNEE",
        "NOTIFY_PARTY",
        "VESSEL",
        "VOYAGE",
        "VESSEL_VOYAGE",
        "PORT_OF_LOADING",
        "PORT_OF_DISCHARGE",
        "FINAL_DESTINATION",
        "CONTAINER_NUMBER",
        "SEAL_NUMBER",
        "ETA",
        "ETD",
        "GROSS_WEIGHT",
        "NET_WEIGHT",
        "PACKAGE_COUNT",
    },
}


# ============================================================
# PHẦN 3/9 — DOCUMENT DETECTION + PDF/OCR
# ============================================================

DOCUMENT_PROFILES = {

    "PURCHASE CONTRACT": [
        "PURCHASE CONTRACT",
        "SALES CONTRACT",
        "SALE CONTRACT",
        "CONTRACT",
    ],

    "COMMERCIAL INVOICE": [
        "COMMERCIAL INVOICE",
        "COMMERCIAL\nINVOICE",
        "INVOICE",
    ],

    "PACKING LIST": [
        "PACKING LIST",
        "PACKING\nLIST",
    ],

    "BILL OF LADING": [
        "BILL OF LADING",
        "OCEAN BILL OF LADING",
        "SEA WAYBILL",
        "B/L",
    ],

    "BOOKING": [
        "BOOKING CONFIRMATION",
        "BOOKING CONFIRMATION SHEET",
        "BOOKING",
    ],

    "CERTIFICATE OF ORIGIN": [
        "CERTIFICATE OF ORIGIN",
        "CERTIFICATE\nOF ORIGIN",
        "FORM E",
        "FORM D",
        "FORM AK",
        "FORM RCEP",
        "C/O",
    ],

    "ARRIVAL NOTICE": [
        "ARRIVAL NOTICE",
        "NOTICE OF ARRIVAL",
        "ARRIVAL NOTIFICATION",
    ],
}


def _contains_phrase(text, phrase):
    """
    Kiểm tra phrase trong text sau khi chuẩn hóa khoảng trắng.
    """

    text_norm = normalize_text(text)
    phrase_norm = normalize_text(phrase)

    if not text_norm or not phrase_norm:
        return False

    return phrase_norm in text_norm


def detect_document_type(text):
    """
    Nhận diện loại chứng từ dựa trên nội dung thực tế.

    Không sử dụng tên file.

    Nguyên tắc:
    - cụm từ đặc trưng được ưu tiên;
    - không có bằng chứng thì UNKNOWN;
    - không dùng dữ liệu của chứng từ khác để đoán.
    """

    if not text:
        return "UNKNOWN"

    text_norm = normalize_text(text)

    scores = {}

    for document_type, keywords in DOCUMENT_PROFILES.items():

        score = 0

        for keyword in keywords:

            keyword_norm = normalize_text(keyword)

            if not keyword_norm:
                continue

            if keyword_norm in text_norm:

                # Cụm từ dài, đặc trưng có trọng số cao hơn
                if len(keyword_norm) >= 20:
                    score += 10

                elif len(keyword_norm) >= 12:
                    score += 7

                elif len(keyword_norm) >= 7:
                    score += 4

                else:
                    score += 1

        scores[document_type] = score

    if not scores:
        return "UNKNOWN"

    best_type = max(
        scores,
        key=scores.get
    )

    best_score = scores[best_type]

    if best_score <= 0:
        return "UNKNOWN"

    # --------------------------------------------------------
    # ƯU TIÊN CÁC DẤU HIỆU ĐẶC TRƯNG
    # --------------------------------------------------------

    if (
        _contains_phrase(text, "PURCHASE CONTRACT")
        or _contains_phrase(text, "SALES CONTRACT")
        or _contains_phrase(text, "SALE CONTRACT")
    ):
        return "PURCHASE CONTRACT"

    if _contains_phrase(
        text,
        "COMMERCIAL INVOICE"
    ):
        return "COMMERCIAL INVOICE"

    if _contains_phrase(
        text,
        "PACKING LIST"
    ):
        return "PACKING LIST"

    if (
        _contains_phrase(text, "BILL OF LADING")
        or _contains_phrase(text, "OCEAN BILL OF LADING")
        or _contains_phrase(text, "SEA WAYBILL")
    ):
        return "BILL OF LADING"

    if _contains_phrase(
        text,
        "BOOKING CONFIRMATION"
    ):
        return "BOOKING"

    if (
        _contains_phrase(text, "CERTIFICATE OF ORIGIN")
        or re.search(
            r"\bFORM\s+[A-Z]{1,6}\b",
            text_norm,
            re.I
        )
    ):
        return "CERTIFICATE OF ORIGIN"

    if (
        _contains_phrase(text, "ARRIVAL NOTICE")
        or _contains_phrase(text, "NOTICE OF ARRIVAL")
        or _contains_phrase(text, "ARRIVAL NOTIFICATION")
    ):
        return "ARRIVAL NOTICE"

    # "INVOICE" chỉ được dùng như fallback
    if re.search(
        r"\bINVOICE\b",
        text_norm,
        re.I
    ):
        return "COMMERCIAL INVOICE"

    if re.search(
        r"\bCONTRACT\b",
        text_norm,
        re.I
    ):
        return "PURCHASE CONTRACT"

    return best_type


# ============================================================
# PDF TEXT EXTRACTION
# ============================================================

def extract_pdf_text_native(pdf_bytes):
    """
    Đọc text layer của PDF bằng PyMuPDF.
    """

    pages = []
    all_text = []

    try:

        pdf = fitz.open(
            stream=pdf_bytes,
            filetype="pdf"
        )

        for page_number, page in enumerate(
            pdf,
            start=1
        ):

            page_text = page.get_text(
                "text"
            ) or ""

            page_text = page_text.strip()

            pages.append({
                "page": page_number,
                "text": page_text,
                "method": "PDF TEXT"
            })

            if page_text:
                all_text.append(page_text)

        pdf.close()

        text = "\n".join(
            all_text
        ).strip()

        return {
            "text": text,
            "pages": pages,
            "has_text": bool(text),
        }

    except Exception:
        return {
            "text": "",
            "pages": [],
            "has_text": False,
        }


# ============================================================
# OCR TEXT
# ============================================================

def extract_pdf_text_ocr(pdf_bytes):
    """
    OCR fallback cho PDF scan.

    OCR chỉ được dùng khi:
    - PDF không có text layer
    - hoặc text layer quá ít.
    """

    pages = []
    all_text = []

    try:

        images = convert_from_bytes(
            pdf_bytes,
            dpi=OCR_DPI,
            fmt="png"
        )

        images = images[
            :MAX_OCR_PAGES
        ]

        for page_number, image in enumerate(
            images,
            start=1
        ):

            try:

                page_text = pytesseract.image_to_string(
                    image,
                    config="--psm 6"
                ) or ""

            except Exception:
                page_text = ""

            page_text = page_text.strip()

            pages.append({
                "page": page_number,
                "text": page_text,
                "method": "OCR"
            })

            if page_text:
                all_text.append(
                    page_text
                )

        text = "\n".join(
            all_text
        ).strip()

        return {
            "text": text,
            "pages": pages,
            "has_text": bool(text),
        }

    except Exception:
        return {
            "text": "",
            "pages": [],
            "has_text": False,
        }


# ============================================================
# OCR LAYOUT
# ============================================================

def extract_ocr_layout(pdf_bytes):
    """
    OCR có tọa độ.

    Chuyển dữ liệu OCR về cấu trúc tương tự
    PyMuPDF words để engine phía sau dùng chung.
    """

    pages = []

    try:

        images = convert_from_bytes(
            pdf_bytes,
            dpi=OCR_DPI,
            fmt="png"
        )

        images = images[
            :MAX_OCR_PAGES
        ]

        for page_number, image in enumerate(
            images,
            start=1
        ):

            try:

                data = pytesseract.image_to_data(
                    image,
                    config="--psm 6",
                    output_type=pytesseract.Output.DICT
                )

            except Exception:
                continue

            page_words = []

            total = len(
                data.get("text", [])
            )

            for i in range(total):

                word = safe_text(
                    data["text"][i]
                )

                if not word:
                    continue

                try:
                    confidence = float(
                        data["conf"][i]
                    )
                except Exception:
                    confidence = 0.0

                if confidence < 15:
                    continue

                x = float(
                    data["left"][i]
                )

                y = float(
                    data["top"][i]
                )

                w = float(
                    data["width"][i]
                )

                h = float(
                    data["height"][i]
                )

                page_words.append({
                    "text": word,
                    "x0": x,
                    "y0": y,
                    "x1": x + w,
                    "y1": y + h,
                    "page": page_number,
                    "confidence": confidence,
                    "block": data["block_num"][i],
                    "line": data["line_num"][i],
                })

            lines = group_layout_words_into_lines(
                page_words
            )

            pages.append({
                "page": page_number,
                "words": page_words,
                "lines": lines,
            })

        return pages

    except Exception:
        return []


# ============================================================
# PDF LAYOUT
# ============================================================

def extract_pdf_layout(pdf_bytes):
    """
    Lấy tọa độ word từ PDF text layer.
    """

    pages = []

    try:

        pdf = fitz.open(
            stream=pdf_bytes,
            filetype="pdf"
        )

        for page_number, page in enumerate(
            pdf,
            start=1
        ):

            words = page.get_text(
                "words"
            ) or []

            page_words = []

            for item in words:

                if len(item) < 5:
                    continue

                x0, y0, x1, y1, word = item[:5]

                word = safe_text(word)

                if not word:
                    continue

                page_words.append({
                    "text": word,
                    "x0": float(x0),
                    "y0": float(y0),
                    "x1": float(x1),
                    "y1": float(y1),
                    "page": page_number,
                })

            lines = group_layout_words_into_lines(
                page_words
            )

            pages.append({
                "page": page_number,
                "words": page_words,
                "lines": lines,
            })

        pdf.close()

        return pages

    except Exception:
        return []


# ============================================================
# GROUP WORDS -> LINES
# ============================================================

def group_layout_words_into_lines(words):
    """
    Gom word theo vị trí Y.
    """

    if not words:
        return []

    sorted_words = sorted(
        words,
        key=lambda x: (
            x["y0"],
            x["x0"]
        )
    )

    lines = []

    for word in sorted_words:

        matched = None

        word_height = max(
            1.0,
            word["y1"] - word["y0"]
        )

        tolerance = max(
            3.0,
            word_height * 0.6
        )

        for line in lines:

            if abs(
                word["y0"]
                - line["y0"]
            ) <= tolerance:

                matched = line
                break

        if matched is None:

            matched = {
                "page": word["page"],
                "y0": word["y0"],
                "y1": word["y1"],
                "words": [],
            }

            lines.append(
                matched
            )

        matched["words"].append(
            word
        )

        matched["y0"] = min(
            matched["y0"],
            word["y0"]
        )

        matched["y1"] = max(
            matched["y1"],
            word["y1"]
        )

    for line in lines:

        line["words"].sort(
            key=lambda x: x["x0"]
        )

        line["text"] = " ".join(
            w["text"]
            for w in line["words"]
        ).strip()

        line["x0"] = min(
            w["x0"]
            for w in line["words"]
        )

        line["x1"] = max(
            w["x1"]
            for w in line["words"]
        )

    lines.sort(
        key=lambda x: (
            x["y0"],
            x["x0"]
        )
    )

    return lines


# ============================================================
# UNIFIED PDF PROCESSING
# ============================================================

def process_pdf(pdf_bytes):
    """
    Pipeline:

    PDF TEXT
        ↓
    kiểm tra chất lượng
        ↓
    nếu không đủ → OCR
        ↓
    detect document type
        ↓
    layout extraction
    """

    native_result = extract_pdf_text_native(
        pdf_bytes
    )

    native_text = (
        native_result["text"]
        or ""
    ).strip()

    normalized_native = normalize_text(
        native_text
    )

    use_native = (
        len(normalized_native) >= 30
    )

    if use_native:

        document_text = native_text

        pages = native_result[
            "pages"
        ]

        extraction_method = "PDF TEXT"

        layout_pages = extract_pdf_layout(
            pdf_bytes
        )

    else:

        ocr_result = extract_pdf_text_ocr(
            pdf_bytes
        )

        document_text = (
            ocr_result["text"]
            or ""
        ).strip()

        pages = ocr_result[
            "pages"
        ]

        extraction_method = "OCR"

        layout_pages = extract_ocr_layout(
            pdf_bytes
        )

    document_type = detect_document_type(
        document_text
    )

    return {
        "text": document_text,
        "pages": pages,
        "layout_pages": layout_pages,
        "document_type": document_type,
        "extraction_method": extraction_method,
    }

# ============================================================
# PHẦN 4/9 — SEMANTIC FIELD ENGINE
# ============================================================

FIELD_DEFINITIONS = {

    "EXPORTER": {
        "group": "PARTIES",
        "display": "Seller / Exporter",
        "aliases": [
            "SELLER",
            "EXPORTER",
            "SHIPPER",
            "SUPPLIER",
            "VENDOR",
            "FROM",
        ],
        "types": ["PARTY"],
        "ambiguous": True,
    },

    "IMPORTER": {
        "group": "PARTIES",
        "display": "Buyer / Importer",
        "aliases": [
            "BUYER",
            "IMPORTER",
            "PURCHASER",
            "CUSTOMER",
            "TO",
        ],
        "types": ["PARTY"],
        "ambiguous": True,
    },

    "CONSIGNEE": {
        "group": "PARTIES",
        "display": "Consignee",
        "aliases": [
            "CONSIGNEE",
            "CONSIGNEE NAME",
        ],
        "types": ["PARTY"],
    },

    "NOTIFY_PARTY": {
        "group": "PARTIES",
        "display": "Notify Party",
        "aliases": [
            "NOTIFY PARTY",
            "NOTIFY",
        ],
        "types": ["PARTY"],
    },

    "EXPORTER_ADDRESS": {
        "group": "PARTIES",
        "display": "Exporter Address",
        "aliases": [
            "SELLER ADDRESS",
            "EXPORTER ADDRESS",
            "SHIPPER ADDRESS",
        ],
        "types": ["ADDRESS"],
    },

    "IMPORTER_ADDRESS": {
        "group": "PARTIES",
        "display": "Importer Address",
        "aliases": [
            "BUYER ADDRESS",
            "IMPORTER ADDRESS",
            "CONSIGNEE ADDRESS",
        ],
        "types": ["ADDRESS"],
    },

    "CONTRACT_NUMBER": {
        "group": "DOCUMENTS",
        "display": "Contract No.",
        "aliases": [
            "CONTRACT NO",
            "CONTRACT NO.",
            "CONTRACT NUMBER",
            "CONTRACT #",
            "SALES CONTRACT NO",
            "PURCHASE CONTRACT NO",
        ],
        "types": ["ID"],
    },

    "CONTRACT_DATE": {
        "group": "DOCUMENTS",
        "display": "Contract Date",
        "aliases": [
            "CONTRACT DATE",
            "DATE OF CONTRACT",
        ],
        "types": ["DATE"],
    },

    "INVOICE_NUMBER": {
        "group": "DOCUMENTS",
        "display": "Invoice No.",
        "aliases": [
            "INVOICE NO",
            "INVOICE NO.",
            "INVOICE NUMBER",
            "INVOICE #",
        ],
        "types": ["ID"],
    },

    "INVOICE_DATE": {
        "group": "DOCUMENTS",
        "display": "Invoice Date",
        "aliases": [
            "INVOICE DATE",
            "DATE OF INVOICE",
        ],
        "types": ["DATE"],
    },

    "PACKING_LIST_NUMBER": {
        "group": "DOCUMENTS",
        "display": "Packing List No.",
        "aliases": [
            "PACKING LIST NO",
            "PACKING LIST NO.",
            "PACKING LIST NUMBER",
            "PL NO",
            "PL NO.",
        ],
        "types": ["ID"],
    },

    "PACKING_LIST_DATE": {
        "group": "DOCUMENTS",
        "display": "Packing List Date",
        "aliases": [
            "PACKING LIST DATE",
            "PL DATE",
        ],
        "types": ["DATE"],
    },

    "BL_NUMBER": {
        "group": "SHIPPING",
        "display": "B/L No.",
        "aliases": [
            "B/L NO",
            "B/L NO.",
            "B/L NUMBER",
            "BL NO",
            "BL NO.",
            "BL NUMBER",
            "BILL OF LADING NO",
            "BILL OF LADING NUMBER",
        ],
        "types": ["ID"],
    },

    "BOOKING_NUMBER": {
        "group": "SHIPPING",
        "display": "Booking No.",
        "aliases": [
            "BOOKING NO",
            "BOOKING NO.",
            "BOOKING NUMBER",
            "BOOKING #",
        ],
        "types": ["ID"],
    },

    "CO_NUMBER": {
        "group": "DOCUMENTS",
        "display": "C/O No.",
        "aliases": [
            "C/O NO",
            "C/O NO.",
            "C/O NUMBER",
            "CERTIFICATE NO",
            "CERTIFICATE NUMBER",
        ],
        "types": ["ID"],
    },

    "PO_NUMBER": {
        "group": "COMMERCIAL",
        "display": "PO No.",
        "aliases": [
            "PO NO",
            "PO NO.",
            "PO NUMBER",
            "PO #",
            "P.O. NO",
            "P.O. NUMBER",
            "PURCHASE ORDER NO",
        ],
        "types": ["ID"],
    },

    "DESCRIPTION": {
        "group": "CARGO",
        "display": "Description of Goods",
        "aliases": [
            "DESCRIPTION",
            "DESCRIPTION OF GOODS",
            "GOODS DESCRIPTION",
            "COMMODITY",
            "PRODUCT DESCRIPTION",
            "ITEM DESCRIPTION",
        ],
        "types": ["DESCRIPTION"],
    },

    "HS_CODE": {
        "group": "CARGO",
        "display": "HS Code",
        "aliases": [
            "HS CODE",
            "HS",
            "HS NO",
            "HS NO.",
            "HS NUMBER",
            "HARMONIZED SYSTEM CODE",
        ],
        "types": ["HS"],
    },

    "COUNTRY_OF_ORIGIN": {
        "group": "CARGO",
        "display": "Country of Origin",
        "aliases": [
            "COUNTRY OF ORIGIN",
            "ORIGIN COUNTRY",
            "COUNTRY ORIGIN",
            "MADE IN",
            "ORIGIN",
        ],
        "types": ["COUNTRY"],
        "ambiguous": True,
    },

    "QUANTITY": {
        "group": "CARGO",
        "display": "Quantity",
        "aliases": [
            "QUANTITY",
            "QTY",
            "Q'TY",
            "QTY.",
            "QUANTITIES",
        ],
        "types": ["NUMBER"],
    },

    "PACKAGE_COUNT": {
        "group": "CARGO",
        "display": "Package Count",
        "aliases": [
            "NO. OF PACKAGES",
            "NUMBER OF PACKAGES",
            "TOTAL PACKAGES",
            "TOTAL PKGS",
            "NO OF PKGS",
            "PKGS",
            "PACKAGES",
            "PACKAGE COUNT",
        ],
        "types": ["NUMBER"],
    },

    "GROSS_WEIGHT": {
        "group": "CARGO",
        "display": "Gross Weight",
        "aliases": [
            "GROSS WEIGHT",
            "GROSS WT",
            "GROSS WT.",
            "G.W.",
            "GW",
        ],
        "types": ["WEIGHT"],
    },

    "NET_WEIGHT": {
        "group": "CARGO",
        "display": "Net Weight",
        "aliases": [
            "NET WEIGHT",
            "NET WT",
            "NET WT.",
            "N.W.",
            "NW",
        ],
        "types": ["WEIGHT"],
    },

    "TARE_WEIGHT": {
        "group": "CARGO",
        "display": "Tare Weight",
        "aliases": [
            "TARE WEIGHT",
            "TARE WT",
            "T.W.",
            "TARE",
        ],
        "types": ["WEIGHT"],
    },

    "MEASUREMENT": {
        "group": "CARGO",
        "display": "Measurement",
        "aliases": [
            "MEASUREMENT",
            "MEAS",
            "VOLUME",
            "CBM",
            "M3",
        ],
        "types": ["MEASUREMENT"],
    },

    "UNIT_PRICE": {
        "group": "COMMERCIAL",
        "display": "Unit Price",
        "aliases": [
            "UNIT PRICE",
            "UNITPRICE",
            "UNIT PR",
            "PRICE/UNIT",
            "PRICE PER UNIT",
            "RATE",
        ],
        "types": ["MONEY"],
    },

    "TOTAL_AMOUNT": {
        "group": "COMMERCIAL",
        "display": "Total Amount",
        "aliases": [
            "TOTAL AMOUNT",
            "TOTAL VALUE",
            "GRAND TOTAL",
            "INVOICE TOTAL",
            "TOTAL",
            "AMOUNT",
        ],
        "types": ["MONEY"],
        "ambiguous": True,
    },

    "CURRENCY": {
        "group": "COMMERCIAL",
        "display": "Currency",
        "aliases": [
            "CURRENCY",
        ],
        "types": ["CURRENCY"],
    },

    "INCOTERMS": {
        "group": "COMMERCIAL",
        "display": "Incoterms",
        "aliases": [
            "INCOTERM",
            "INCOTERMS",
            "DELIVERY TERM",
            "DELIVERY TERMS",
            "TRADE TERM",
            "TERMS OF DELIVERY",
        ],
        "types": ["INCOTERM"],
    },

    "PAYMENT_TERMS": {
        "group": "COMMERCIAL",
        "display": "Payment Terms",
        "aliases": [
            "PAYMENT TERMS",
            "TERMS OF PAYMENT",
            "PAYMENT",
            "PAYMENT CONDITION",
        ],
        "types": ["TEXT"],
    },

    "VESSEL": {
        "group": "SHIPPING",
        "display": "Vessel",
        "aliases": [
            "VESSEL",
            "VESSEL NAME",
            "SHIP NAME",
            "MOTHER VESSEL",
        ],
        "types": ["VESSEL"],
    },

    "VOYAGE": {
        "group": "SHIPPING",
        "display": "Voyage",
        "aliases": [
            "VOYAGE",
            "VOY",
            "VOYAGE NO",
            "VOYAGE NUMBER",
        ],
        "types": ["ID"],
    },

    "VESSEL_VOYAGE": {
        "group": "SHIPPING",
        "display": "Vessel / Voyage",
        "aliases": [
            "VESSEL/VOYAGE",
            "VESSEL / VOYAGE",
            "VESSEL & VOYAGE",
            "VESSEL VOYAGE",
        ],
        "types": ["VESSEL_VOYAGE"],
    },

    "CONTAINER_NUMBER": {
        "group": "SHIPPING",
        "display": "Container No.",
        "aliases": [
            "CONTAINER NO",
            "CONTAINER NO.",
            "CONTAINER NUMBER",
            "CONTAINER",
            "CONT NO",
            "CONT. NO",
        ],
        "types": ["CONTAINER"],
    },

    "SEAL_NUMBER": {
        "group": "SHIPPING",
        "display": "Seal No.",
        "aliases": [
            "SEAL NO",
            "SEAL NO.",
            "SEAL NUMBER",
            "SEAL",
        ],
        "types": ["SEAL"],
    },

    "PORT_OF_LOADING": {
        "group": "SHIPPING",
        "display": "Port of Loading",
        "aliases": [
            "PORT OF LOADING",
            "PORT OF LOADING (POL)",
            "POL",
            "LOADING PORT",
            "PORT OF SHIPMENT",
        ],
        "types": ["PORT"],
        "ambiguous": True,
    },

    "PORT_OF_DISCHARGE": {
        "group": "SHIPPING",
        "display": "Port of Discharge",
        "aliases": [
            "PORT OF DISCHARGE",
            "PORT OF DISCHARGE (POD)",
            "POD",
            "DISCHARGE PORT",
        ],
        "types": ["PORT"],
        "ambiguous": True,
    },

    "PLACE_OF_RECEIPT": {
        "group": "SHIPPING",
        "display": "Place of Receipt",
        "aliases": [
            "PLACE OF RECEIPT",
            "RECEIPT PLACE",
            "PLACE OF RECEIPT BY CARRIER",
        ],
        "types": ["PORT"],
    },

    "FINAL_DESTINATION": {
        "group": "SHIPPING",
        "display": "Final Destination",
        "aliases": [
            "FINAL DESTINATION",
            "PLACE OF DELIVERY",
            "DELIVERY PLACE",
            "DESTINATION",
        ],
        "types": ["PORT"],
        "ambiguous": True,
    },

    "SHIPMENT_TIME": {
        "group": "SHIPPING",
        "display": "Shipment Time",
        "aliases": [
            "SHIPMENT DATE",
            "DATE OF SHIPMENT",
            "SHIPMENT TIME",
            "SHIPMENT PERIOD",
            "LATEST SHIPMENT",
            "LATEST DATE OF SHIPMENT",
        ],
        "types": ["DATE_OR_PERIOD"],
    },

    "ETA": {
        "group": "SHIPPING",
        "display": "ETA",
        "aliases": [
            "ETA",
            "ESTIMATED TIME OF ARRIVAL",
        ],
        "types": ["DATETIME"],
    },

    "ETD": {
        "group": "SHIPPING",
        "display": "ETD",
        "aliases": [
            "ETD",
            "ESTIMATED TIME OF DEPARTURE",
        ],
        "types": ["DATETIME"],
    },
}


# ------------------------------------------------------------
# DOCUMENT SCOPE
# ------------------------------------------------------------

DOCUMENT_FIELD_SCOPE = {

    "PURCHASE CONTRACT": {
        "CONTRACT_NUMBER",
        "CONTRACT_DATE",
        "EXPORTER",
        "IMPORTER",
        "CONSIGNEE",
        "PO_NUMBER",
        "DESCRIPTION",
        "QUANTITY",
        "UNIT_PRICE",
        "TOTAL_AMOUNT",
        "CURRENCY",
        "INCOTERMS",
        "PAYMENT_TERMS",
        "SHIPMENT_TIME",
        "PORT_OF_LOADING",
        "FINAL_DESTINATION",
    },

    "COMMERCIAL INVOICE": {
        "INVOICE_NUMBER",
        "INVOICE_DATE",
        "CONTRACT_NUMBER",
        "EXPORTER",
        "IMPORTER",
        "CONSIGNEE",
        "DESCRIPTION",
        "HS_CODE",
        "COUNTRY_OF_ORIGIN",
        "QUANTITY",
        "PACKAGE_COUNT",
        "GROSS_WEIGHT",
        "NET_WEIGHT",
        "MEASUREMENT",
        "UNIT_PRICE",
        "TOTAL_AMOUNT",
        "CURRENCY",
        "INCOTERMS",
        "PAYMENT_TERMS",
        "PORT_OF_LOADING",
        "FINAL_DESTINATION",
    },

    "PACKING LIST": {
        "PACKING_LIST_NUMBER",
        "PACKING_LIST_DATE",
        "CONTRACT_NUMBER",
        "EXPORTER",
        "IMPORTER",
        "CONSIGNEE",
        "DESCRIPTION",
        "HS_CODE",
        "QUANTITY",
        "PACKAGE_COUNT",
        "GROSS_WEIGHT",
        "NET_WEIGHT",
        "MEASUREMENT",
        "CONTAINER_NUMBER",
        "SEAL_NUMBER",
    },

    "BILL OF LADING": {
        "BL_NUMBER",
        "BOOKING_NUMBER",
        "EXPORTER",
        "IMPORTER",
        "CONSIGNEE",
        "NOTIFY_PARTY",
        "DESCRIPTION",
        "PACKAGE_COUNT",
        "GROSS_WEIGHT",
        "MEASUREMENT",
        "CONTAINER_NUMBER",
        "SEAL_NUMBER",
        "VESSEL",
        "VOYAGE",
        "VESSEL_VOYAGE",
        "PORT_OF_LOADING",
        "PORT_OF_DISCHARGE",
        "PLACE_OF_RECEIPT",
        "FINAL_DESTINATION",
        "ETA",
        "ETD",
    },

    "BOOKING": {
        "BOOKING_NUMBER",
        "EXPORTER",
        "IMPORTER",
        "CONSIGNEE",
        "VESSEL",
        "VOYAGE",
        "VESSEL_VOYAGE",
        "PORT_OF_LOADING",
        "PORT_OF_DISCHARGE",
        "PLACE_OF_RECEIPT",
        "FINAL_DESTINATION",
        "CONTAINER_NUMBER",
        "SEAL_NUMBER",
        "DESCRIPTION",
        "PACKAGE_COUNT",
        "GROSS_WEIGHT",
        "MEASUREMENT",
        "ETD",
        "ETA",
    },

    "CERTIFICATE OF ORIGIN": {
        "CO_NUMBER",
        "EXPORTER",
        "IMPORTER",
        "CONSIGNEE",
        "DESCRIPTION",
        "QUANTITY",
        "GROSS_WEIGHT",
        "NET_WEIGHT",
        "COUNTRY_OF_ORIGIN",
        "PORT_OF_LOADING",
        "PORT_OF_DISCHARGE",
    },

    "ARRIVAL NOTICE": {
        "BL_NUMBER",
        "BOOKING_NUMBER",
        "CONSIGNEE",
        "NOTIFY_PARTY",
        "VESSEL",
        "VOYAGE",
        "VESSEL_VOYAGE",
        "PORT_OF_LOADING",
        "PORT_OF_DISCHARGE",
        "FINAL_DESTINATION",
        "CONTAINER_NUMBER",
        "SEAL_NUMBER",
        "ETA",
        "ETD",
    },
}


def get_document_scope(document_type):
    """
    Field nào được phép xét trong loại chứng từ hiện tại.
    """

    document_type = safe_text(
        document_type
    ).strip().upper()

    if document_type in DOCUMENT_FIELD_SCOPE:
        return DOCUMENT_FIELD_SCOPE[
            document_type
        ]

    return set(
        FIELD_DEFINITIONS.keys()
    )


# ------------------------------------------------------------
# KNOWLEDGE BASE ALIAS LOADER
# ------------------------------------------------------------

def get_kb_aliases(
    standard_field,
    document_type=None
):
    """
    Lấy alias cho một standard field.

    Nguồn dữ liệu:
    1. field_mapping.json
    2. Các cấu trúc FIELD_MAPPING / fields / mappings
    3. Các cấu trúc list of objects
    4. Alias đã học trong database
    5. Alias định nghĩa trực tiếp trong FIELD_DEFINITIONS

    Không phụ thuộc vào mẫu chứng từ cụ thể.
    """

    aliases = []

    data = FIELD_MAPPING_KB

    if not isinstance(
        data,
        dict
    ):
        return aliases

    # --------------------------------------------------------
    # HELPER
    # --------------------------------------------------------

    def add_alias(value):
        """
        Thêm alias hợp lệ, tránh trùng.
        """

        if value is None:
            return

        value = safe_text(
            value
        ).strip()

        if not value:
            return

        if value not in aliases:
            aliases.append(
                value
            )

    # ========================================================
    # 1. FIELD TRỰC TIẾP Ở ROOT
    # ========================================================

    raw_field = data.get(
        standard_field
    )

    if isinstance(
        raw_field,
        list
    ):

        for item in raw_field:

            if isinstance(
                item,
                str
            ):
                add_alias(item)

            elif isinstance(
                item,
                dict
            ):

                for key in (
                    "alias",
                    "aliases",
                    "raw_label",
                    "labels",
                    "name",
                ):

                    value = item.get(
                        key
                    )

                    if isinstance(
                        value,
                        str
                    ):
                        add_alias(
                            value
                        )

                    elif isinstance(
                        value,
                        list
                    ):

                        for x in value:
                            add_alias(x)

    elif isinstance(
        raw_field,
        dict
    ):

        for key in (
            "alias",
            "aliases",
            "raw_label",
            "labels",
            "name",
        ):

            value = raw_field.get(
                key
            )

            if isinstance(
                value,
                str
            ):
                add_alias(
                    value
                )

            elif isinstance(
                value,
                list
            ):

                for x in value:
                    add_alias(x)

    # ========================================================
    # 2. FIELD MAPPING DẠNG DICTIONARY
    # ========================================================

    for key in (
        "FIELD_MAPPING",
        "fields",
        "mappings",
        "FIELD_ALIASES",
    ):

        section = data.get(
            key
        )

        if not isinstance(
            section,
            dict
        ):
            continue

        field_data = section.get(
            standard_field
        )

        if isinstance(
            field_data,
            list
        ):

            for item in field_data:

                if isinstance(
                    item,
                    str
                ):
                    add_alias(
                        item
                    )

                elif isinstance(
                    item,
                    dict
                ):

                    for alias_key in (
                        "alias",
                        "aliases",
                        "raw_label",
                        "labels",
                        "name",
                    ):

                        value = item.get(
                            alias_key
                        )

                        if isinstance(
                            value,
                            str
                        ):
                            add_alias(
                                value
                            )

                        elif isinstance(
                            value,
                            list
                        ):

                            for x in value:
                                add_alias(x)

        elif isinstance(
            field_data,
            dict
        ):

            for alias_key in (
                "alias",
                "aliases",
                "raw_label",
                "labels",
                "name",
            ):

                value = field_data.get(
                    alias_key
                )

                if isinstance(
                    value,
                    str
                ):
                    add_alias(
                        value
                    )

                elif isinstance(
                    value,
                    list
                ):

                    for x in value:
                        add_alias(x)

    # ========================================================
    # 3. LIST OF OBJECTS
    # ========================================================

    for key in (
        "aliases",
        "field_aliases",
        "mappings",
    ):

        section = data.get(
            key
        )

        if not isinstance(
            section,
            list
        ):
            continue

        for item in section:

            if not isinstance(
                item,
                dict
            ):
                continue

            item_field = (
                item.get(
                    "standard_field"
                )
                or item.get(
                    "field"
                )
                or item.get(
                    "field_name"
                )
            )

            if item_field != standard_field:
                continue

            for alias_key in (
                "alias",
                "raw_label",
                "label",
                "name",
            ):

                value = item.get(
                    alias_key
                )

                if isinstance(
                    value,
                    str
                ):
                    add_alias(
                        value
                    )

            value = item.get(
                "aliases"
            )

            if isinstance(
                value,
                list
            ):

                for x in value:
                    add_alias(x)

    # ========================================================
    # 4. DATABASE LEARNED ALIASES
    # ========================================================

    try:

        database_aliases = (
            load_database_aliases()
        )

    except Exception:

        database_aliases = []

    for row in database_aliases:

        if not isinstance(
            row,
            dict
        ):
            continue

        row_field = (
            row.get(
                "standard_field"
            )
            or row.get(
                "field_name"
            )
        )

        if row_field != standard_field:
            continue

        row_doc = row.get(
            "document_type"
        )

        # Nếu alias có giới hạn document type
        # thì chỉ dùng đúng context.
        if (
            document_type
            and row_doc
            and row_doc != document_type
        ):
            continue

        value = (
            row.get(
                "raw_label"
            )
            or row.get(
                "alias"
            )
            or row.get(
                "label"
            )
        )

        add_alias(
            value
        )

    # ========================================================
    # 5. ALIAS ĐỊNH NGHĨA TRỰC TIẾP
    # ========================================================

    definition = FIELD_DEFINITIONS.get(
        standard_field,
        {}
    )

    if isinstance(
        definition,
        dict
    ):

        direct_aliases = definition.get(
            "aliases",
            []
        )

        if isinstance(
            direct_aliases,
            list
        ):

            for alias in direct_aliases:
                add_alias(alias)

    # ========================================================
    # 6. LOẠI BỎ ALIAS KHÔNG HỢP LỆ
    # ========================================================

    cleaned = []

    for alias in aliases:

        alias = safe_text(
            alias
        ).strip()

        if not alias:
            continue

        normalized_alias = normalize_text(
            alias
        )

        if not normalized_alias:
            continue

        if normalized_alias in {
            normalize_text(x)
            for x in cleaned
        }:
            continue

        cleaned.append(
            alias
        )

    aliases = cleaned

    # ========================================================
    # 7. SORT
    # ========================================================

    # Alias dài hơn đứng trước.
    #
    # Ví dụ:
    #
    # PORT OF DISCHARGE
    #
    # phải được xét trước:
    #
    # POD
    #
    # và:
    #
    # INVOICE NUMBER
    #
    # trước các alias ngắn hơn.

    aliases.sort(
        key=lambda x: len(
            normalize_text(x)
        ),
        reverse=True
    )

    return aliases


# ------------------------------------------------------------
# MERGE FIELD ALIASES
# ------------------------------------------------------------

def get_database_field_aliases(
    standard_field,
    document_type=None
):
    """
    Gộp alias từ:
    - Knowledge Base
    - Database learned aliases
    - FIELD_DEFINITIONS

    Database alias được ưu tiên trước.
    """

    result = []

    def add(value):

        if value is None:
            return

        value = safe_text(
            value
        ).strip()

        if not value:
            return

        normalized = normalize_text(
            value
        )

        if not normalized:
            return

        existing = {
            normalize_text(x)
            for x in result
        }

        if normalized not in existing:
            result.append(
                value
            )

    # --------------------------------------------------------
    # 1. DATABASE LEARNED ALIAS
    # --------------------------------------------------------

    try:

        rows = load_database_aliases()

    except Exception:

        rows = []

    for row in rows:

        if not isinstance(
            row,
            dict
        ):
            continue

        row_field = (
            row.get(
                "standard_field"
            )
            or row.get(
                "field_name"
            )
        )

        if row_field != standard_field:
            continue

        row_doc = row.get(
            "document_type"
        )

        if (
            document_type
            and row_doc
            and row_doc != document_type
        ):
            continue

        alias = (
            row.get(
                "raw_label"
            )
            or row.get(
                "alias"
            )
            or row.get(
                "label"
            )
        )

        add(alias)

    # --------------------------------------------------------
    # 2. KNOWLEDGE BASE + DIRECT DEFINITION
    # --------------------------------------------------------

    for alias in get_kb_aliases(
        standard_field,
        document_type
    ):
        add(alias)

    # --------------------------------------------------------
    # 3. SORT
    # --------------------------------------------------------

    result.sort(
        key=lambda x: len(
            normalize_text(x)
        ),
        reverse=True
    )

    return result


# ------------------------------------------------------------
# BUILD ALIAS PATTERN
# ------------------------------------------------------------

def build_alias_pattern(
    aliases
):
    """
    Chuyển danh sách alias thành regex pattern.

    Alias dài hơn được đặt trước để tránh:
        NUMBER
    match trước:
        INVOICE NUMBER

    Không hard-code mẫu chứng từ.
    """

    valid_aliases = []

    if not aliases:
        return r"(?!x)x"

    for alias in aliases:

        alias = safe_text(
            alias
        ).strip()

        if not alias:
            continue

        if alias not in valid_aliases:
            valid_aliases.append(
                alias
            )

    if not valid_aliases:
        return r"(?!x)x"

    valid_aliases.sort(
        key=lambda x: len(
            normalize_text(x)
        ),
        reverse=True
    )

    escaped = []

    for alias in valid_aliases:

        pattern = re.escape(
            alias
        )

        # Cho phép khoảng trắng giữa các từ
        pattern = pattern.replace(
            r"\ ",
            r"\s+"
        )

        escaped.append(
            pattern
        )

    return (
        r"(?<![A-Z0-9])(?:"
        + "|".join(
            escaped
        )
        + r")(?![A-Z0-9])"
    )


# ------------------------------------------------------------
# FIELD ALIAS MAP
# ------------------------------------------------------------

def build_field_alias_map(
    document_type
):
    """
    Tạo mapping:

        STANDARD_FIELD
            -> aliases

    Chỉ xét các field nằm trong
    DOCUMENT_FIELD_SCOPE.
    """

    scope = get_document_scope(
        document_type
    )

    field_alias_map = {}

    for standard_field in scope:

        aliases = get_database_field_aliases(
            standard_field,
            document_type
        )

        if not aliases:
            continue

        field_alias_map[
            standard_field
        ] = aliases

    return field_alias_map


# ------------------------------------------------------------
# FIELD PATTERN MAP
# ------------------------------------------------------------

def build_field_pattern_map(
    document_type
):
    """
    Tạo regex pattern cho từng standard field.

    Kết quả:

        {
            "EXPORTER": "...",
            "IMPORTER": "...",
            ...
        }
    """

    alias_map = build_field_alias_map(
        document_type
    )

    pattern_map = {}

    for field_name, aliases in alias_map.items():

        pattern = build_alias_pattern(
            aliases
        )

        if pattern:
            pattern_map[
                field_name
            ] = pattern

    return pattern_map


# ------------------------------------------------------------
# FIND SEMANTIC LABEL HITS
# ------------------------------------------------------------

def find_semantic_label_hits(
    text,
    document_type
):
    """
    Tìm tất cả label đã biết trong toàn bộ text.

    Kết quả không phải giá trị cuối cùng.
    Đây chỉ là bước xác định:
        "đoạn nào trong chứng từ đang nói về field nào".

    Mỗi hit gồm:
        standard_field
        alias
        start
        end
        text

    Không phụ thuộc vị trí cố định của mẫu chứng từ.
    """

    text = safe_text(
        text
    )

    if not text.strip():
        return []

    alias_map = build_field_alias_map(
        document_type
    )

    hits = []

    for standard_field, aliases in alias_map.items():

        if not aliases:
            continue

        pattern = build_alias_pattern(
            aliases
        )

        if not pattern:
            continue

        try:

            for match in re.finditer(
                pattern,
                text,
                re.IGNORECASE
            ):

                alias = match.group(
                    0
                )

                hits.append({
                    "standard_field":
                        standard_field,

                    "alias":
                        alias,

                    "start":
                        match.start(),

                    "end":
                        match.end(),

                    "text":
                        match.group(0),
                })

        except Exception:
            continue

    # --------------------------------------------------------
    # SORT THEO VỊ TRÍ
    # --------------------------------------------------------

    hits.sort(
        key=lambda x: (
            x.get(
                "start",
                0
            ),
            -len(
                x.get(
                    "alias",
                    ""
                )
            )
        )
    )

    # --------------------------------------------------------
    # LOẠI HIT TRÙNG / CHỒNG
    # --------------------------------------------------------

    final_hits = []

    for hit in hits:

        start = hit.get(
            "start",
            0
        )

        end = hit.get(
            "end",
            0
        )

        overlapped = False

        for previous in final_hits:

            p_start = previous.get(
                "start",
                0
            )

            p_end = previous.get(
                "end",
                0
            )

            if (
                start < p_end
                and end > p_start
            ):

                # Giữ alias dài hơn.
                previous_length = (
                    p_end - p_start
                )

                current_length = (
                    end - start
                )

                if (
                    current_length
                    <= previous_length
                ):
                    overlapped = True

                else:
                    final_hits.remove(
                        previous
                    )

                break

        if not overlapped:
            final_hits.append(
                hit
            )

    final_hits.sort(
        key=lambda x: x.get(
            "start",
            0
        )
    )

    return final_hits


# ------------------------------------------------------------
# GET FIELD DEFINITION
# ------------------------------------------------------------

def get_field_definition(
    standard_field
):
    """
    Lấy định nghĩa chuẩn của field.

    Nếu field không tồn tại trong
    FIELD_DEFINITIONS thì trả về {}.
    """

    definition = FIELD_DEFINITIONS.get(
        standard_field,
        {}
    )

    if not isinstance(
        definition,
        dict
    ):
        return {}

    return definition


# ------------------------------------------------------------
# FIELD EXPECTED TYPE
# ------------------------------------------------------------

def get_field_expected_type(
    standard_field
):
    """
    Xác định kiểu dữ liệu nghiệp vụ mà field mong đợi.

    Có thể khai báo trong FIELD_DEFINITIONS
    bằng các key:
        expected_type
        type
        value_type
    """

    definition = get_field_definition(
        standard_field
    )

    expected_type = (
        definition.get(
            "expected_type"
        )
        or definition.get(
            "value_type"
        )
        or definition.get(
            "type"
        )
    )

    if expected_type is None:
        return "TEXT"

    return safe_text(
        expected_type
    ).strip().upper()


# ------------------------------------------------------------
# FIELD PRIORITY
# ------------------------------------------------------------

def get_field_priority(
    standard_field
):
    """
    Độ ưu tiên của field khi có nhiều candidate.

    Giá trị càng lớn càng được ưu tiên.
    """

    definition = get_field_definition(
        standard_field
    )

    value = definition.get(
        "priority",
        0
    )

    try:
        return int(value)

    except Exception:
        return 0


# ------------------------------------------------------------
# FIELD STOP ALIASES
# ------------------------------------------------------------

def get_field_stop_aliases(
    standard_field,
    document_type
):
    """
    Xác định các label có thể báo hiệu
    rằng giá trị của field hiện tại đã kết thúc.

    Ví dụ:

        INVOICE NO.: INV001
        DATE: 20-JUN-2026

    Khi đọc INVOICE NO.,
    DATE là stop label.
    """

    definition = get_field_definition(
        standard_field
    )

    stop_aliases = []

    configured = definition.get(
        "stop_aliases",
        []
    )

    if isinstance(
        configured,
        str
    ):
        configured = [
            configured
        ]

    if isinstance(
        configured,
        list
    ):

        for alias in configured:

            if alias is not None:
                stop_aliases.append(
                    safe_text(
                        alias
                    ).strip()
                )

    # --------------------------------------------------------
    # Nếu FIELD_DEFINITIONS không khai báo stop_aliases,
    # dùng tất cả semantic aliases của document.
    # --------------------------------------------------------

    if not stop_aliases:

        field_alias_map = build_field_alias_map(
            document_type
        )

        for field_name, aliases in field_alias_map.items():

            if field_name == standard_field:
                continue

            for alias in aliases:
                stop_aliases.append(
                    alias
                )

    # --------------------------------------------------------
    # REMOVE DUPLICATES
    # --------------------------------------------------------

    final = []

    seen = set()

    for alias in stop_aliases:

        normalized = normalize_text(
            alias
        )

        if not normalized:
            continue

        if normalized in seen:
            continue

        seen.add(
            normalized
        )

        final.append(
            alias
        )

    final.sort(
        key=lambda x: len(
            normalize_text(x)
        ),
        reverse=True
    )

    return final


# ------------------------------------------------------------
# FIELD AMBIGUITY
# ------------------------------------------------------------

def is_ambiguous_field(
    standard_field
):
    """
    Kiểm tra field có alias/ngữ nghĩa dễ nhầm hay không.

    Những field như:
        POD
        POL
        FROM
        TO
        NO
        DATE

    cần xử lý context thay vì tự động lấy
    giá trị đầu tiên.
    """

    definition = get_field_definition(
        standard_field
    )

    if definition.get(
        "ambiguous",
        False
    ):
        return True

    if definition.get(
        "context_required",
        False
    ):
        return True

    return False


# ------------------------------------------------------------
# FIELD DOCUMENT VALIDATION
# ------------------------------------------------------------

def field_allowed_for_document(
    standard_field,
    document_type
):
    """
    Kiểm tra field có thuộc scope của document hay không.
    """

    scope = get_document_scope(
        document_type
    )

    return (
        standard_field
        in scope
    )


# ------------------------------------------------------------
# SEMANTIC FIELD CONFIG
# ------------------------------------------------------------

def get_semantic_field_config(
    standard_field,
    document_type
):
    """
    Trả về toàn bộ cấu hình cần thiết
    cho semantic extraction của một field.
    """

    definition = get_field_definition(
        standard_field
    )

    return {
        "standard_field":
            standard_field,

        "document_type":
            document_type,

        "aliases":
            get_database_field_aliases(
                standard_field,
                document_type
            ),

        "expected_type":
            get_field_expected_type(
                standard_field
            ),

        "priority":
            get_field_priority(
                standard_field
            ),

        "ambiguous":
            is_ambiguous_field(
                standard_field
            ),

        "stop_aliases":
            get_field_stop_aliases(
                standard_field,
                document_type
            ),

        "definition":
            definition,
    }


# ------------------------------------------------------------
# BUILD COMPLETE SEMANTIC CONFIG
# ------------------------------------------------------------

def build_semantic_field_config(
    document_type
):
    """
    Xây dựng cấu hình semantic extraction
    cho toàn bộ field của một chứng từ.

    Đây là lớp trung gian giữa:
        Knowledge Base
        Database
        FIELD_DEFINITIONS
        Document Scope

    và extraction engine.
    """

    scope = get_document_scope(
        document_type
    )

    config = {}

    for standard_field in scope:

        config[
            standard_field
        ] = get_semantic_field_config(
            standard_field,
            document_type
        )

    return config


# ------------------------------------------------------------
# SEMANTIC FIELD DISPLAY NAME
# ------------------------------------------------------------

def get_field_display_name(
    standard_field
):
    """
    Lấy tên hiển thị của standard field.
    """

    definition = get_field_definition(
        standard_field
    )

    display = definition.get(
        "display"
    )

    if display:
        return safe_text(
            display
        ).strip()

    return standard_field.replace(
        "_",
        " "
    ).title()


# ------------------------------------------------------------
# SEMANTIC FIELD GROUP
# ------------------------------------------------------------

def get_field_group(
    standard_field
):
    """
    Lấy nhóm nghiệp vụ của field.

    Ví dụ:
        PARTIES
        COMMERCIAL
        CARGO
        SHIPPING
        DOCUMENT
    """

    definition = get_field_definition(
        standard_field
    )

    group = definition.get(
        "group"
    )

    if group:
        return safe_text(
            group
        ).strip().upper()

    return "OTHER"


# ------------------------------------------------------------
# SEMANTIC FIELD INFO
# ------------------------------------------------------------

def get_semantic_field_info(
    standard_field,
    document_type
):
    """
    Trả về thông tin chuẩn hóa của field
    để các engine phía sau sử dụng thống nhất.
    """

    config = get_semantic_field_config(
        standard_field,
        document_type
    )

    return {
        "standard_field":
            standard_field,

        "display":
            get_field_display_name(
                standard_field
            ),

        "group":
            get_field_group(
                standard_field
            ),

        "document_type":
            document_type,

        "aliases":
            config.get(
                "aliases",
                []
            ),

        "expected_type":
            config.get(
                "expected_type",
                "TEXT"
            ),

        "priority":
            config.get(
                "priority",
                0
            ),

        "ambiguous":
            config.get(
                "ambiguous",
                False
            ),

        "stop_aliases":
            config.get(
                "stop_aliases",
                []
            ),
    }

# ============================================================
# PHẦN 5/9 — SEMANTIC CANDIDATE ENGINE
# ============================================================

# ------------------------------------------------------------
# TEXT CLEANING
# ------------------------------------------------------------

def clean_extracted_value(
    value
):
    """
    Làm sạch giá trị sau khi extraction.

    Không sửa nội dung nghiệp vụ.
    Chỉ loại bỏ:
        - khoảng trắng thừa
        - dấu xuống dòng
        - dấu phân cách thừa ở đầu/cuối
    """

    value = safe_text(
        value
    )

    if not value:
        return EMPTY

    value = value.replace(
        "\r",
        " "
    )

    value = value.replace(
        "\n",
        " "
    )

    value = re.sub(
        r"\s+",
        " ",
        value
    )

    value = value.strip(
        " \t:;|"
    )

    return value.strip()


# ------------------------------------------------------------
# NORMALIZE CANDIDATE TEXT
# ------------------------------------------------------------

def normalize_candidate_text(
    value
):
    """
    Chuẩn hóa nhẹ để so sánh candidate.

    Không dùng hàm này để thay thế normalize nghiệp vụ
    cuối cùng.
    """

    value = clean_extracted_value(
        value
    )

    if value == EMPTY:
        return EMPTY

    return normalize_text(
        value
    )


# ------------------------------------------------------------
# SPLIT TEXT INTO LINES
# ------------------------------------------------------------

def semantic_lines(
    text
):
    """
    Tách raw text thành các dòng logic.

    Giữ nguyên thứ tự xuất hiện.
    """

    text = safe_text(
        text
    )

    if not text:
        return []

    raw_lines = text.splitlines()

    lines = []

    for index, line in enumerate(
        raw_lines
    ):

        line = clean_extracted_value(
            line
        )

        if not line:
            continue

        lines.append({
            "index":
                index,

            "text":
                line,
        })

    return lines


# ------------------------------------------------------------
# BUILD ALL LABEL PATTERNS
# ------------------------------------------------------------

def build_all_semantic_label_patterns(
    document_type
):
    """
    Tạo pattern cho tất cả semantic fields
    thuộc document hiện tại.
    """

    config = build_semantic_field_config(
        document_type
    )

    result = {}

    for field_name, info in config.items():

        aliases = info.get(
            "aliases",
            []
        )

        if not aliases:
            continue

        result[
            field_name
        ] = build_alias_pattern(
            aliases
        )

    return result


# ------------------------------------------------------------
# FIND LABEL IN LINE
# ------------------------------------------------------------

def find_labels_in_line(
    line,
    document_type
):
    """
    Tìm các semantic labels xuất hiện trong một dòng.

    Trả về:
        [
            {
                "field": ...,
                "alias": ...,
                "start": ...,
                "end": ...
            }
        ]
    """

    line = safe_text(
        line
    )

    if not line:
        return []

    patterns = build_all_semantic_label_patterns(
        document_type
    )

    hits = []

    for field_name, pattern in patterns.items():

        try:

            for match in re.finditer(
                pattern,
                line,
                re.IGNORECASE
            ):

                hits.append({
                    "field":
                        field_name,

                    "alias":
                        match.group(0),

                    "start":
                        match.start(),

                    "end":
                        match.end(),
                })

        except Exception:
            continue

    # --------------------------------------------------------
    # SORT
    # --------------------------------------------------------

    hits.sort(
        key=lambda x: (
            x["start"],
            -(x["end"] - x["start"])
        )
    )

    # --------------------------------------------------------
    # REMOVE OVERLAP
    # --------------------------------------------------------

    final_hits = []

    for hit in hits:

        overlap = False

        for previous in final_hits:

            if (
                hit["start"]
                < previous["end"]
                and
                hit["end"]
                > previous["start"]
            ):

                current_length = (
                    hit["end"]
                    - hit["start"]
                )

                previous_length = (
                    previous["end"]
                    - previous["start"]
                )

                if (
                    current_length
                    <= previous_length
                ):
                    overlap = True

                else:
                    final_hits.remove(
                        previous
                    )

                break

        if not overlap:
            final_hits.append(
                hit
            )

    return final_hits


# ------------------------------------------------------------
# EXTRACT TEXT AFTER LABEL
# ------------------------------------------------------------

def extract_after_label(
    line,
    label_hit,
    document_type,
    standard_field
):
    """
    Lấy phần text nằm sau semantic label
    trên cùng một dòng.

    Ví dụ:

        Invoice No.: INV001

    -> INV001
    """

    line = safe_text(
        line
    )

    if not line:
        return EMPTY

    end = label_hit.get(
        "end",
        0
    )

    if end >= len(line):
        return EMPTY

    value = line[end:]

    # --------------------------------------------------------
    # Bỏ separator
    # --------------------------------------------------------

    value = re.sub(
        r"^[\s:：=\-#]+",
        "",
        value
    )

    value = clean_extracted_value(
        value
    )

    if not value:
        return EMPTY

    # --------------------------------------------------------
    # Nếu phía sau vẫn còn semantic label khác,
    # chỉ lấy phần trước label đó.
    # --------------------------------------------------------

    other_hits = find_labels_in_line(
        line,
        document_type
    )

    next_positions = []

    for hit in other_hits:

        if hit["start"] <= end:
            continue

        next_positions.append(
            hit["start"]
        )

    if next_positions:

        next_start = min(
            next_positions
        )

        value = line[
            end:next_start
        ]

        value = re.sub(
            r"^[\s:：=\-#]+",
            "",
            value
        )

        value = clean_extracted_value(
            value
        )

    return value


# ------------------------------------------------------------
# CHECK IF TEXT IS A LABEL ONLY
# ------------------------------------------------------------

def is_semantic_label_only(
    text,
    document_type
):
    """
    Kiểm tra một dòng có phải chỉ là label/header
    mà chưa chứa value hay không.
    """

    text = clean_extracted_value(
        text
    )

    if not text:
        return True

    hits = find_labels_in_line(
        text,
        document_type
    )

    if not hits:
        return False

    # Nếu toàn bộ dòng chính là semantic label
    # thì không xem là value.
    for hit in hits:

        before = text[
            :hit["start"]
        ].strip(
            " :：=-"
        )

        after = text[
            hit["end"]:]
        .strip(
            " :：=-"
        )

        if not before and not after:
            return True

    return False


# ------------------------------------------------------------
# EXTRACT VALUE FROM FOLLOWING LINES
# ------------------------------------------------------------

def extract_from_following_lines(
    lines,
    current_index,
    document_type,
    standard_field,
    max_lines=3
):
    """
    Nếu label không có value cùng dòng,
    tìm value ở các dòng kế tiếp.

    Không lấy dòng tiếp theo nếu dòng đó
    đã là semantic label khác.
    """

    collected = []

    for offset in range(
        1,
        max_lines + 1
    ):

        target_index = (
            current_index
            + offset
        )

        if target_index >= len(
            lines
        ):
            break

        candidate = clean_extracted_value(
            lines[target_index]["text"]
        )

        if not candidate:
            continue

        # Nếu gặp label khác thì dừng.
        if is_semantic_label_only(
            candidate,
            document_type
        ):
            break

        # Không lấy dòng có quá nhiều semantic labels.
        label_hits = find_labels_in_line(
            candidate,
            document_type
        )

        if len(label_hits) >= 2:
            break

        collected.append(
            candidate
        )

        # Với field thông thường,
        # một dòng value là đủ.
        if standard_field not in {
            "EXPORTER",
            "IMPORTER",
            "CONSIGNEE",
            "NOTIFY_PARTY",
            "DESCRIPTION",
            "ADDRESS",
        }:
            break

    if not collected:
        return EMPTY

    return clean_extracted_value(
        " ".join(collected)
    )


# ------------------------------------------------------------
# EXTRACT LABEL-VALUE CANDIDATES
# ------------------------------------------------------------

def extract_label_value_candidates(
    text,
    document_type
):
    """
    Extraction cơ bản dựa trên semantic label.

    Không gán trực tiếp giá trị cuối cùng.
    Mỗi kết quả chỉ là candidate.

    Candidate gồm:
        field
        raw_value
        source
        confidence
    """

    lines = semantic_lines(
        text
    )

    candidates = []

    for line_position, line_info in enumerate(
        lines
    ):

        line = line_info["text"]

        label_hits = find_labels_in_line(
            line,
            document_type
        )

        if not label_hits:
            continue

        for label_hit in label_hits:

            standard_field = label_hit[
                "field"
            ]

            # ------------------------------------------------
            # 1. SAME LINE
            # ------------------------------------------------

            value = extract_after_label(
                line,
                label_hit,
                document_type,
                standard_field
            )

            source = "same_line"

            # ------------------------------------------------
            # 2. NEXT LINE
            # ------------------------------------------------

            if not value:

                value = extract_from_following_lines(
                    lines,
                    line_position,
                    document_type,
                    standard_field
                )

                source = "following_line"

            if not value:
                continue

            # ------------------------------------------------
            # 3. CLEAN
            # ------------------------------------------------

            value = clean_extracted_value(
                value
            )

            if not value:
                continue

            # ------------------------------------------------
            # 4. BASIC HEADER REJECTION
            # ------------------------------------------------

            if is_semantic_label_only(
                value,
                document_type
            ):
                continue

            candidates.append({
                "standard_field":
                    standard_field,

                "raw_value":
                    value,

                "source":
                    source,

                "line_index":
                    line_info["index"],

                "alias":
                    label_hit["alias"],

                "confidence":
                    0.50,
            })

    return candidates


# ------------------------------------------------------------
# NUMERIC VALIDATION
# ------------------------------------------------------------

def is_numeric_value(
    value
):
    """
    Kiểm tra candidate có dạng số nghiệp vụ hay không.

    Chấp nhận:
        32
        32.00
        13,406.40
        35,650 KGS
        USD 12,208.13
    """

    value = clean_extracted_value(
        value
    )

    if not value:
        return False

    numeric_pattern = (
        r"(?<![A-Z])"
        r"[-+]?"
        r"\d{1,3}"
        r"(?:,\d{3})*"
        r"(?:\.\d+)?"
        r"(?:\s*[A-Z]{2,10})?"
        r"(?![A-Z])"
    )

    if re.search(
        numeric_pattern,
        value,
        re.IGNORECASE
    ):
        return True

    # Dạng không có comma
    if re.search(
        r"\b\d+(?:\.\d+)?\b",
        value
    ):
        return True

    return False


# ------------------------------------------------------------
# DATE VALIDATION
# ------------------------------------------------------------

def is_date_value(
    value
):
    """
    Kiểm tra các dạng ngày phổ biến trong chứng từ.
    """

    value = clean_extracted_value(
        value
    )

    if not value:
        return False

    patterns = [

        r"\b\d{1,2}[-/]\d{1,2}[-/]\d{2,4}\b",

        r"\b\d{1,2}[-/][A-Za-z]{3,9}[-/]\d{2,4}\b",

        r"\b[A-Za-z]{3,9}\s+\d{1,2},?\s+\d{2,4}\b",

        r"\b\d{1,2}\s+[A-Za-z]{3,9}\s+\d{2,4}\b",

        r"\b\d{4}[-/]\d{1,2}[-/]\d{1,2}\b",
    ]

    for pattern in patterns:

        if re.search(
            pattern,
            value,
            re.IGNORECASE
        ):
            return True

    return False


# ------------------------------------------------------------
# CONTAINER VALIDATION
# ------------------------------------------------------------

def is_container_value(
    value
):
    """
    Kiểm tra container number.

    Chuẩn phổ biến:
        4 chữ + 7 số

    Không phụ thuộc hãng tàu.
    """

    value = clean_extracted_value(
        value
    ).upper()

    if not value:
        return False

    compact = re.sub(
        r"[^A-Z0-9]",
        "",
        value
    )

    return bool(
        re.fullmatch(
            r"[A-Z]{4}\d{7}",
            compact
        )
    )


# ------------------------------------------------------------
# SEAL VALIDATION
# ------------------------------------------------------------

def is_seal_value(
    value
):
    """
    Kiểm tra seal number ở mức cơ bản.

    Không ép một format duy nhất vì seal
    có thể khác nhau theo hãng/đơn vị.
    """

    value = clean_extracted_value(
        value
    ).upper()

    if not value:
        return False

    compact = re.sub(
        r"[^A-Z0-9]",
        "",
        value
    )

    if len(compact) < 5:
        return False

    if len(compact) > 20:
        return False

    return bool(
        re.fullmatch(
            r"[A-Z0-9]+",
            compact
        )
    )


# ------------------------------------------------------------
# BL VALIDATION
# ------------------------------------------------------------

def is_bl_candidate(
    value
):
    """
    Kiểm tra B/L number ở mức cấu trúc.

    Không hard-code hãng tàu hoặc prefix cụ thể.
    """

    value = clean_extracted_value(
        value
    ).upper()

    if not value:
        return False

    compact = re.sub(
        r"[^A-Z0-9]",
        "",
        value
    )

    if len(compact) < 8:
        return False

    if len(compact) > 25:
        return False

    # B/L thường là chuỗi alphanumeric,
    # có ít nhất chữ và số.
    has_letter = bool(
        re.search(
            r"[A-Z]",
            compact
        )
    )

    has_digit = bool(
        re.search(
            r"\d",
            compact
        )
    )

    return (
        has_letter
        and has_digit
    )


# ------------------------------------------------------------
# PO VALIDATION
# ------------------------------------------------------------

def is_po_candidate(
    value
):
    """
    Kiểm tra PO number.

    Không đồng nhất PO với Contract.
    """

    value = clean_extracted_value(
        value
    ).upper()

    if not value:
        return False

    compact = re.sub(
        r"\s+",
        "",
        value
    )

    if len(compact) < 3:
        return False

    if len(compact) > 40:
        return False

    return bool(
        re.fullmatch(
            r"[A-Z0-9][A-Z0-9._/-]*",
            compact
        )
    )


# ------------------------------------------------------------
# HS CODE VALIDATION
# ------------------------------------------------------------

def is_hs_code_candidate(
    value
):
    """
    Kiểm tra HS code ở mức hình thức.

    Không tự tra cứu hoặc tự suy đoán HS code.
    """

    value = clean_extracted_value(
        value
    )

    compact = re.sub(
        r"[\s.\-]",
        "",
        value
    )

    return bool(
        re.fullmatch(
            r"\d{4,12}",
            compact
        )
    )


# ------------------------------------------------------------
# CURRENCY VALIDATION
# ------------------------------------------------------------

def is_currency_candidate(
    value
):
    """
    Nhận diện currency code / tên tiền tệ.
    """

    value = clean_extracted_value(
        value
    ).upper()

    if not value:
        return False

    known_codes = {
        "USD",
        "EUR",
        "CNY",
        "RMB",
        "VND",
        "JPY",
        "KRW",
        "GBP",
        "AUD",
        "CAD",
        "SGD",
        "THB",
        "MYR",
        "HKD",
        "TWD",
        "CHF",
    }

    if value in known_codes:
        return True

    return bool(
        re.fullmatch(
            r"[A-Z]{3}",
            value
        )
    )


# ------------------------------------------------------------
# INCOTERM VALIDATION
# ------------------------------------------------------------

def is_incoterm_candidate(
    value
):
    """
    Kiểm tra Incoterms.

    Chỉ xác nhận format/thuật ngữ,
    không suy đoán từ địa chỉ hoặc tuyến vận chuyển.
    """

    value = clean_extracted_value(
        value
    ).upper()

    if not value:
        return False

    known = {
        "EXW",
        "FCA",
        "FAS",
        "FOB",
        "CFR",
        "CIF",
        "CPT",
        "CIP",
        "DAP",
        "DPU",
        "DDP",
    }

    first = value.split()[0]

    return first in known


# ------------------------------------------------------------
# GENERIC TEXT VALIDATION
# ------------------------------------------------------------

def is_valid_text_candidate(
    value
):
    """
    Validation cho field dạng text.

    Loại:
        - rỗng
        - label
        - header table
        - chuỗi chỉ gồm punctuation
    """

    value = clean_extracted_value(
        value
    )

    if not value:
        return False

    if re.fullmatch(
        r"[\W_]+",
        value,
        re.UNICODE
    ):
        return False

    return True


# ------------------------------------------------------------
# FIELD-SPECIFIC VALIDATION
# ------------------------------------------------------------

def validate_semantic_candidate(
    standard_field,
    value
):
    """
    Validation dựa trên ý nghĩa của standard field.

    Trả về:
        (is_valid, validation_score)
    """

    value = clean_extracted_value(
        value
    )

    if not value:
        return False, 0.0

    field_type = get_field_expected_type(
        standard_field
    )

    field = safe_text(
        standard_field
    ).upper()

    # --------------------------------------------------------
    # FIELD ID / NUMBER
    # --------------------------------------------------------

    if field in {
        "CONTAINER_NUMBER"
    }:

        valid = is_container_value(
            value
        )

        return (
            valid,
            0.95 if valid else 0.0
        )

    if field in {
        "SEAL_NUMBER"
    }:

        valid = is_seal_value(
            value
        )

        return (
            valid,
            0.80 if valid else 0.0
        )

    if field in {
        "BL_NUMBER"
    }:

        valid = is_bl_candidate(
            value
        )

        return (
            valid,
            0.90 if valid else 0.0
        )

    if field in {
        "PO_NUMBER"
    }:

        valid = is_po_candidate(
            value
        )

        return (
            valid,
            0.85 if valid else 0.0
        )

    if field in {
        "HS_CODE"
    }:

        valid = is_hs_code_candidate(
            value
        )

        return (
            valid,
            0.95 if valid else 0.0
        )

    # --------------------------------------------------------
    # DATE
    # --------------------------------------------------------

    if field.endswith(
        "_DATE"
    ):

        valid = is_date_value(
            value
        )

        return (
            valid,
            0.95 if valid else 0.0
        )

    # --------------------------------------------------------
    # NUMERIC FIELDS
    # --------------------------------------------------------

    if field in {
        "QUANTITY",
        "PACKAGE_COUNT",
        "GROSS_WEIGHT",
        "NET_WEIGHT",
        "TARE_WEIGHT",
        "MEASUREMENT",
        "MEASUREMENT_CUFT",
        "UNIT_PRICE",
        "TOTAL_AMOUNT",
    }:

        valid = is_numeric_value(
            value
        )

        return (
            valid,
            0.90 if valid else 0.0
        )

    # --------------------------------------------------------
    # CURRENCY
    # --------------------------------------------------------

    if field == "CURRENCY":

        valid = is_currency_candidate(
            value
        )

        return (
            valid,
            0.95 if valid else 0.0
        )

    # --------------------------------------------------------
    # INCOTERMS
    # --------------------------------------------------------

    if field == "INCOTERMS":

        valid = is_incoterm_candidate(
            value
        )

        return (
            valid,
            0.95 if valid else 0.0
        )

    # --------------------------------------------------------
    # TYPE TỪ FIELD_DEFINITIONS
    # --------------------------------------------------------

    if field_type in {
        "NUMBER",
        "NUMERIC",
        "DECIMAL",
        "AMOUNT",
        "PRICE",
        "QUANTITY",
        "WEIGHT",
    }:

        valid = is_numeric_value(
            value
        )

        return (
            valid,
            0.90 if valid else 0.0
        )

    if field_type == "DATE":

        valid = is_date_value(
            value
        )

        return (
            valid,
            0.95 if valid else 0.0
        )

    # --------------------------------------------------------
    # DEFAULT TEXT
    # --------------------------------------------------------

    valid = is_valid_text_candidate(
        value
    )

    return (
        valid,
        0.65 if valid else 0.0
    )


# ------------------------------------------------------------
# REJECT TABLE HEADER CANDIDATES
# ------------------------------------------------------------

def looks_like_table_header(
    value,
    document_type
):
    """
    Loại các candidate kiểu:

        Qty UnitPrice Amount

    hoặc:

        Description Quantity Unit Price Amount

    Đây là HEADER chứ không phải giá trị.
    """

    value = clean_extracted_value(
        value
    )

    if not value:
        return True

    hits = find_labels_in_line(
        value,
        document_type
    )

    # Có từ 2 semantic labels trở lên
    # trong cùng candidate => rất có khả năng là header.
    if len(hits) >= 2:
        return True

    normalized = normalize_text(
        value
    )

    header_terms = {
        "QTY",
        "QUANTITY",
        "UNIT PRICE",
        "UNITPRICE",
        "AMOUNT",
        "DESCRIPTION",
        "TOTAL",
        "PRICE",
        "NO",
        "NUMBER",
        "PACKAGE",
        "PACKAGES",
        "GROSS WEIGHT",
        "NET WEIGHT",
        "CBM",
        "MEASUREMENT",
    }

    tokens = set(
        normalized.split()
    )

    if tokens and len(
        tokens.intersection(
            {
                normalize_text(x)
                for x in header_terms
            }
        )
    ) >= 2:
        return True

    return False


# ------------------------------------------------------------
# SCORE SEMANTIC CANDIDATE
# ------------------------------------------------------------

def score_semantic_candidate(
    candidate,
    document_type
):
    """
    Tính điểm candidate.

    Điểm dựa trên:
        - label recognition
        - validation
        - source
        - priority
        - ambiguity
        - header rejection

    Không dùng tên công ty / tuyến cảng / mẫu PDF
    để cộng điểm.
    """

    field = candidate.get(
        "standard_field"
    )

    value = candidate.get(
        "raw_value",
        EMPTY
    )

    score = 0.0

    # --------------------------------------------------------
    # LABEL
    # --------------------------------------------------------

    score += 0.30

    # --------------------------------------------------------
    # VALIDATION
    # --------------------------------------------------------

    valid, validation_score = (
        validate_semantic_candidate(
            field,
            value
        )
    )

    if not valid:
        return 0.0

    score += (
        validation_score
        * 0.50
    )

    # --------------------------------------------------------
    # SOURCE
    # --------------------------------------------------------

    source = candidate.get(
        "source"
    )

    if source == "same_line":
        score += 0.12

    elif source == "following_line":
        score += 0.07

    # --------------------------------------------------------
    # PRIORITY
    # --------------------------------------------------------

    priority = get_field_priority(
        field
    )

    score += min(
        max(priority, 0)
        * 0.01,
        0.05
    )

    # --------------------------------------------------------
    # AMBIGUITY
    # --------------------------------------------------------

    if is_ambiguous_field(
        field
    ):
        score -= 0.05

    # --------------------------------------------------------
    # TABLE HEADER
    # --------------------------------------------------------

    if looks_like_table_header(
        value,
        document_type
    ):
        return 0.0

    # --------------------------------------------------------
    # CLAMP
    # --------------------------------------------------------

    return max(
        0.0,
        min(
            score,
            1.0
        )
    )


# ------------------------------------------------------------
# SCORE ALL CANDIDATES
# ------------------------------------------------------------

def score_semantic_candidates(
    candidates,
    document_type
):
    """
    Tính score cho toàn bộ candidates.
    """

    scored = []

    for candidate in candidates:

        item = dict(
            candidate
        )

        item[
            "semantic_score"
        ] = score_semantic_candidate(
            item,
            document_type
        )

        if (
            item[
                "semantic_score"
            ] <= 0
        ):
            continue

        scored.append(
            item
        )

    return scored


# ------------------------------------------------------------
# GROUP CANDIDATES BY FIELD
# ------------------------------------------------------------

def group_candidates_by_field(
    candidates
):
    """
    Nhóm candidate theo standard field.
    """

    grouped = {}

    for candidate in candidates:

        field = candidate.get(
            "standard_field"
        )

        if not field:
            continue

        grouped.setdefault(
            field,
            []
        ).append(
            candidate
        )

    return grouped


# ------------------------------------------------------------
# SELECT BEST CANDIDATE
# ------------------------------------------------------------

def select_best_semantic_candidate(
    candidates
):
    """
    Chọn candidate tốt nhất cho một field.

    Không tự ghép nhiều candidate thành một giá trị.
    """

    if not candidates:
        return None

    ranked = sorted(
        candidates,
        key=lambda x: (
            x.get(
                "semantic_score",
                0
            ),
            x.get(
                "confidence",
                0
            )
        ),
        reverse=True
    )

    return ranked[0]


# ------------------------------------------------------------
# BUILD SEMANTIC EXTRACTION RESULT
# ------------------------------------------------------------

def build_semantic_extraction_result(
    text,
    document_type
):
    """
    Pipeline semantic extraction cơ bản:

        RAW TEXT
            ↓
        LABEL DETECTION
            ↓
        CANDIDATE EXTRACTION
            ↓
        SEMANTIC VALIDATION
            ↓
        CANDIDATE SCORING
            ↓
        BEST CANDIDATE
    """

    document_type = safe_text(
        document_type
    ).strip().upper()

    if not text:
        return {}

    candidates = extract_label_value_candidates(
        text,
        document_type
    )

    scored = score_semantic_candidates(
        candidates,
        document_type
    )

    grouped = group_candidates_by_field(
        scored
    )

    result = {}

    for field_name, field_candidates in grouped.items():

        best = select_best_semantic_candidate(
            field_candidates
        )

        if not best:
            continue

        result[
            field_name
        ] = {
            "value":
                best.get(
                    "raw_value",
                    EMPTY
                ),

            "raw_value":
                best.get(
                    "raw_value",
                    EMPTY
                ),

            "alias":
                best.get(
                    "alias",
                    EMPTY
                ),

            "source":
                best.get(
                    "source",
                    EMPTY
                ),

            "confidence":
                round(
                    best.get(
                        "semantic_score",
                        0
                    ),
                    4
                ),
        }

    return result


# ============================================================
# PHẦN 6/9 — LAYOUT / TABLE SEMANTIC ENGINE
# ============================================================

# ------------------------------------------------------------
# LAYOUT TOKEN
# ------------------------------------------------------------

def make_layout_token(
    text,
    x0=0.0,
    y0=0.0,
    x1=0.0,
    y1=0.0,
    page=0,
    block=0,
    line=0,
    word=0,
    confidence=1.0
):
    """
    Chuẩn hóa một token về cấu trúc layout chung.

    Dùng được cho:
        - Native PDF
        - OCR
    """

    return {
        "text": clean_extracted_value(text),
        "x0": float(x0 or 0),
        "y0": float(y0 or 0),
        "x1": float(x1 or 0),
        "y1": float(y1 or 0),
        "page": int(page or 0),
        "block": int(block or 0),
        "line": int(line or 0),
        "word": int(word or 0),
        "confidence": float(
            confidence or 0
        ),
    }


# ------------------------------------------------------------
# TOKEN CENTER
# ------------------------------------------------------------

def token_center_x(
    token
):
    return (
        float(token.get("x0", 0))
        + float(token.get("x1", 0))
    ) / 2


def token_center_y(
    token
):
    return (
        float(token.get("y0", 0))
        + float(token.get("y1", 0))
    ) / 2


# ------------------------------------------------------------
# GROUP TOKENS INTO LINES
# ------------------------------------------------------------

def group_layout_tokens_into_lines(
    tokens,
    y_tolerance=4.0
):
    """
    Gom token theo tọa độ Y.

    Các token nằm gần cùng một dòng được gom lại.
    """

    if not tokens:
        return []

    valid_tokens = []

    for token in tokens:

        if not isinstance(
            token,
            dict
        ):
            continue

        text = clean_extracted_value(
            token.get("text", "")
        )

        if not text:
            continue

        item = dict(token)

        item["text"] = text

        valid_tokens.append(
            item
        )

    valid_tokens.sort(
        key=lambda x: (
            x.get("page", 0),
            token_center_y(x),
            x.get("x0", 0)
        )
    )

    lines = []

    for token in valid_tokens:

        placed = False

        for line in reversed(lines):

            if line["page"] != token["page"]:
                continue

            if abs(
                token_center_y(token)
                - line["center_y"]
            ) <= y_tolerance:

                line["tokens"].append(
                    token
                )

                # cập nhật center Y
                ys = [
                    token_center_y(x)
                    for x in line["tokens"]
                ]

                line["center_y"] = (
                    sum(ys) / len(ys)
                )

                placed = True
                break

        if not placed:

            lines.append({
                "page":
                    token.get(
                        "page",
                        0
                    ),

                "center_y":
                    token_center_y(
                        token
                    ),

                "tokens":
                    [token],
            })

    # --------------------------------------------------------
    # SORT TOKEN TRONG TỪNG DÒNG
    # --------------------------------------------------------

    for line in lines:

        line["tokens"].sort(
            key=lambda x: (
                x.get("x0", 0),
                x.get("word", 0)
            )
        )

        line["text"] = " ".join(
            token["text"]
            for token in line["tokens"]
        )

    # --------------------------------------------------------
    # SORT LINE
    # --------------------------------------------------------

    lines.sort(
        key=lambda x: (
            x.get("page", 0),
            x.get("center_y", 0)
        )
    )

    for index, line in enumerate(
        lines
    ):
        line["index"] = index

    return lines


# ------------------------------------------------------------
# BUILD LAYOUT FROM PDF WORDS
# ------------------------------------------------------------

def build_layout_from_pdf_words(
    pdf_words
):
    """
    Chuyển dữ liệu words của PyMuPDF:

        (x0, y0, x1, y1, text, block, line, word)

    thành layout token thống nhất.
    """

    tokens = []

    if not pdf_words:
        return tokens

    for item in pdf_words:

        if not isinstance(
            item,
            (list, tuple)
        ):
            continue

        if len(item) < 5:
            continue

        try:

            x0 = item[0]
            y0 = item[1]
            x1 = item[2]
            y1 = item[3]
            text = item[4]

            block = (
                item[5]
                if len(item) > 5
                else 0
            )

            line = (
                item[6]
                if len(item) > 6
                else 0
            )

            word = (
                item[7]
                if len(item) > 7
                else 0
            )

            page = (
                item[8]
                if len(item) > 8
                else 0
            )

        except Exception:
            continue

        text = clean_extracted_value(
            text
        )

        if not text:
            continue

        tokens.append(
            make_layout_token(
                text=text,
                x0=x0,
                y0=y0,
                x1=x1,
                y1=y1,
                page=page,
                block=block,
                line=line,
                word=word,
                confidence=1.0,
            )
        )

    return tokens


# ------------------------------------------------------------
# BUILD LAYOUT FROM OCR DATA
# ------------------------------------------------------------

def build_layout_from_ocr_data(
    ocr_data,
    page_number=0
):
    """
    Chuyển output pytesseract.image_to_data()
    thành cùng cấu trúc token với PDF native.
    """

    tokens = []

    if not ocr_data:
        return tokens

    try:

        texts = ocr_data.get(
            "text",
            []
        )

        lefts = ocr_data.get(
            "left",
            []
        )

        tops = ocr_data.get(
            "top",
            []
        )

        widths = ocr_data.get(
            "width",
            []
        )

        heights = ocr_data.get(
            "height",
            []
        )

        confs = ocr_data.get(
            "conf",
            []
        )

        blocks = ocr_data.get(
            "block_num",
            []
        )

        lines = ocr_data.get(
            "line_num",
            []
        )

        words = ocr_data.get(
            "word_num",
            []
        )

    except Exception:
        return tokens

    total = len(texts)

    for i in range(total):

        text = clean_extracted_value(
            texts[i]
        )

        if not text:
            continue

        try:

            x0 = float(
                lefts[i]
            )

            y0 = float(
                tops[i]
            )

            width = float(
                widths[i]
            )

            height = float(
                heights[i]
            )

        except Exception:

            x0 = 0.0
            y0 = 0.0
            width = 0.0
            height = 0.0

        try:

            confidence = float(
                confs[i]
            )

            if confidence < 0:
                confidence = 0.0

            confidence /= 100.0

        except Exception:

            confidence = 0.0

        tokens.append(
            make_layout_token(
                text=text,
                x0=x0,
                y0=y0,
                x1=x0 + width,
                y1=y0 + height,
                page=page_number,
                block=(
                    blocks[i]
                    if i < len(blocks)
                    else 0
                ),
                line=(
                    lines[i]
                    if i < len(lines)
                    else 0
                ),
                word=(
                    words[i]
                    if i < len(words)
                    else 0
                ),
                confidence=confidence,
            )
        )

    return tokens


# ------------------------------------------------------------
# LINE TOKEN TEXT
# ------------------------------------------------------------

def layout_line_text(
    line
):
    """
    Ghép token thành text của một dòng.
    """

    if not isinstance(
        line,
        dict
    ):
        return EMPTY

    tokens = line.get(
        "tokens",
        []
    )

    if not tokens:
        return EMPTY

    return clean_extracted_value(
        " ".join(
            token.get(
                "text",
                ""
            )
            for token in tokens
        )
    )


# ------------------------------------------------------------
# FIND LABEL TOKENS IN LAYOUT LINE
# ------------------------------------------------------------

def find_layout_label_hits(
    line,
    document_type
):
    """
    Tìm semantic label trên layout line.

    Kết quả có tọa độ để engine biết
    label nằm ở đâu.
    """

    tokens = line.get(
        "tokens",
        []
    )

    if not tokens:
        return []

    text = layout_line_text(
        line
    )

    text_hits = find_labels_in_line(
        text,
        document_type
    )

    if not text_hits:
        return []

    hits = []

    for text_hit in text_hits:

        alias = text_hit.get(
            "alias",
            ""
        )

        alias_normalized = normalize_text(
            alias
        )

        alias_tokens = alias_normalized.split()

        if not alias_tokens:
            continue

        # ----------------------------------------------------
        # Tìm token tương ứng với alias
        # ----------------------------------------------------

        for start_index in range(
            len(tokens)
        ):

            matched = []

            current_text = []

            for offset in range(
                len(alias_tokens)
            ):

                index = (
                    start_index
                    + offset
                )

                if index >= len(
                    tokens
                ):
                    break

                token_text = normalize_text(
                    tokens[index].get(
                        "text",
                        ""
                    )
                )

                current_text.append(
                    token_text
                )

                matched.append(
                    tokens[index]
                )

            if (
                current_text
                == alias_tokens
            ):

                hits.append({
                    "field":
                        text_hit[
                            "field"
                        ],

                    "alias":
                        alias,

                    "tokens":
                        matched,

                    "start_token":
                        start_index,

                    "end_token":
                        start_index
                        + len(
                            matched
                        )
                        - 1,

                    "x0":
                        matched[0].get(
                            "x0",
                            0
                        ),

                    "x1":
                        matched[-1].get(
                            "x1",
                            0
                        ),

                    "y0":
                        min(
                            x.get(
                                "y0",
                                0
                            )
                            for x in matched
                        ),

                    "y1":
                        max(
                            x.get(
                                "y1",
                                0
                            )
                            for x in matched
                        ),
                })

                break

    return hits


# ------------------------------------------------------------
# TOKENS AFTER LABEL
# ------------------------------------------------------------

def get_tokens_after_label(
    line,
    label_hit
):
    """
    Lấy token nằm bên phải semantic label.
    """

    tokens = line.get(
        "tokens",
        []
    )

    end_token = label_hit.get(
        "end_token",
        -1
    )

    if end_token < 0:
        return []

    return tokens[
        end_token + 1:
    ]


# ------------------------------------------------------------
# TEXT FROM TOKENS
# ------------------------------------------------------------

def tokens_to_text(
    tokens
):
    if not tokens:
        return EMPTY

    return clean_extracted_value(
        " ".join(
            token.get(
                "text",
                ""
            )
            for token in tokens
        )
    )


# ------------------------------------------------------------
# REMOVE LABEL TOKENS FROM CANDIDATE
# ------------------------------------------------------------

def remove_semantic_labels_from_tokens(
    tokens,
    document_type
):
    """
    Nếu candidate vô tình chứa thêm label khác,
    loại phần label đó ra.
    """

    if not tokens:
        return []

    result = []

    for token in tokens:

        token_text = token.get(
            "text",
            ""
        )

        hits = find_labels_in_line(
            token_text,
            document_type
        )

        if hits:
            continue

        result.append(
            token
        )

    return result


# ------------------------------------------------------------
# LAYOUT SAME-LINE VALUE
# ------------------------------------------------------------

def extract_layout_same_line_value(
    line,
    label_hit,
    document_type
):
    """
    Lấy value bên phải label dựa trên tọa độ.

    Khác regex text:
    engine biết chính xác token nào nằm sau label.
    """

    tokens = get_tokens_after_label(
        line,
        label_hit
    )

    if not tokens:
        return EMPTY

    # --------------------------------------------------------
    # Nếu gặp label khác bên phải thì dừng.
    # --------------------------------------------------------

    selected = []

    for token in tokens:

        token_text = token.get(
            "text",
            ""
        )

        if not token_text:
            continue

        semantic_hits = find_labels_in_line(
            token_text,
            document_type
        )

        if semantic_hits:
            break

        selected.append(
            token
        )

    if not selected:
        return EMPTY

    value = tokens_to_text(
        selected
    )

    if not value:
        return EMPTY

    if looks_like_table_header(
        value,
        document_type
    ):
        return EMPTY

    return value


# ------------------------------------------------------------
# FIND NEARBY VALUE LINE
# ------------------------------------------------------------

def find_nearby_value_line(
    lines,
    current_line_index,
    document_type,
    max_distance=3
):
    """
    Tìm dòng value gần label.

    Chỉ tìm trong cùng page.
    """

    if not lines:
        return None

    current_line = lines[
        current_line_index
    ]

    current_page = current_line.get(
        "page",
        0
    )

    for offset in range(
        1,
        max_distance + 1
    ):

        index = (
            current_line_index
            + offset
        )

        if index >= len(
            lines
        ):
            break

        line = lines[index]

        if line.get(
            "page",
            0
        ) != current_page:
            break

        text = layout_line_text(
            line
        )

        if not text:
            continue

        label_hits = find_layout_label_hits(
            line,
            document_type
        )

        if label_hits:
            # Gặp field khác -> không vượt qua.
            break

        return line

    return None


# ------------------------------------------------------------
# EXTRACT VERTICAL VALUE
# ------------------------------------------------------------

def extract_layout_vertical_value(
    lines,
    current_line_index,
    document_type
):
    """
    Lấy value ở dòng dưới label.
    """

    value_line = find_nearby_value_line(
        lines,
        current_line_index,
        document_type
    )

    if value_line is None:
        return EMPTY

    value = layout_line_text(
        value_line
    )

    if not value:
        return EMPTY

    if looks_like_table_header(
        value,
        document_type
    ):
        return EMPTY

    return value


# ------------------------------------------------------------
# DETECT POSSIBLE TABLE HEADER
# ------------------------------------------------------------

def detect_table_header_fields(
    line,
    document_type
):
    """
    Xác định dòng có phải table header semantic hay không.

    Ví dụ:

        Description | Qty | Unit Price | Amount

    sẽ trả về các field tương ứng
    cùng tọa độ X.
    """

    hits = find_layout_label_hits(
        line,
        document_type
    )

    if len(hits) < 2:
        return []

    headers = []

    for hit in hits:

        headers.append({
            "field":
                hit["field"],

            "alias":
                hit["alias"],

            "x0":
                hit["x0"],

            "x1":
                hit["x1"],

            "center_x":
                (
                    hit["x0"]
                    + hit["x1"]
                ) / 2,

            "page":
                line.get(
                    "page",
                    0
                ),

            "line_index":
                line.get(
                    "index",
                    0
                ),
        })

    headers.sort(
        key=lambda x: x[
            "center_x"
        ]
    )

    return headers


# ------------------------------------------------------------
# FIND TABLE HEADER ROWS
# ------------------------------------------------------------

def find_table_header_rows(
    lines,
    document_type
):
    """
    Tìm tất cả dòng có từ 2 semantic fields trở lên.

    Đây là dấu hiệu mạnh của bảng dữ liệu.
    """

    result = []

    for line in lines:

        headers = detect_table_header_fields(
            line,
            document_type
        )

        if len(headers) >= 2:

            result.append({
                "line":
                    line,

                "headers":
                    headers,
            })

    return result


# ------------------------------------------------------------
# BUILD COLUMN BOUNDARIES
# ------------------------------------------------------------

def build_table_columns(
    headers,
    page_width=None
):
    """
    Xây khoảng X cho từng cột.

    Ví dụ:

        DESCRIPTION | QTY | UNIT PRICE | AMOUNT

    Mỗi field có:
        x_start
        x_end

    Không cần biết template cụ thể.
    """

    if not headers:
        return []

    headers = sorted(
        headers,
        key=lambda x: x.get(
            "center_x",
            0
        )
    )

    columns = []

    for index, header in enumerate(
        headers
    ):

        center = header.get(
            "center_x",
            0
        )

        if index == 0:

            previous_center = (
                header.get(
                    "x0",
                    center
                )
                - max(
                    20,
                    (
                        headers[1].get(
                            "center_x",
                            center + 100
                        )
                        - center
                    ) / 2
                )
                if len(headers) > 1
                else center - 100
            )

        else:

            previous_center = (
                headers[index - 1].get(
                    "center_x",
                    0
                )
                + center
            ) / 2

        if index == len(
            headers
        ) - 1:

            if page_width:
                next_boundary = page_width

            else:

                next_boundary = (
                    center
                    + max(
                        30,
                        center
                        - headers[
                            index - 1
                        ].get(
                            "center_x",
                            0
                        )
                    )
                )

        else:

            next_boundary = (
                center
                + headers[
                    index + 1
                ].get(
                    "center_x",
                    center
                )
            ) / 2

        columns.append({
            "field":
                header["field"],

            "alias":
                header["alias"],

            "x_start":
                previous_center,

            "x_end":
                next_boundary,

            "center_x":
                center,
        })

    return columns


# ------------------------------------------------------------
# TOKEN BELONGS TO COLUMN
# ------------------------------------------------------------

def token_belongs_to_column(
    token,
    column
):
    """
    Kiểm tra token có nằm trong khoảng X của column.
    """

    center = token_center_x(
        token
    )

    return (
        center
        >= column["x_start"]
        and
        center
        < column["x_end"]
    )


# ------------------------------------------------------------
# PARSE TABLE DATA ROW
# ------------------------------------------------------------

def parse_table_data_row(
    line,
    columns,
    document_type
):
    """
    Đọc một dòng dữ liệu bên dưới table header.

    Token được phân vào column dựa trên X,
    không dựa vào số lượng token.

    Đây là điểm quan trọng để xử lý:

        32 | 178.65 | 5716.80

    mà không nhầm thành header.
    """

    if not columns:
        return []

    tokens = line.get(
        "tokens",
        []
    )

    if not tokens:
        return []

    values = []

    for column in columns:

        column_tokens = []

        for token in tokens:

            if token_belongs_to_column(
                token,
                column
            ):
                column_tokens.append(
                    token
                )

        if not column_tokens:
            continue

        column_tokens.sort(
            key=lambda x: x.get(
                "x0",
                0
            )
        )

        value = tokens_to_text(
            column_tokens
        )

        if not value:
            continue

        if looks_like_table_header(
            value,
            document_type
        ):
            continue

        values.append({
            "standard_field":
                column["field"],

            "raw_value":
                value,

            "source":
                "table",

            "line_index":
                line.get(
                    "index",
                    0
                ),

            "x_start":
                column["x_start"],

            "x_end":
                column["x_end"],

            "confidence":
                0.80,
        })

    return values


# ------------------------------------------------------------
# FIND TABLE DATA ROWS
# ------------------------------------------------------------

def extract_table_candidates(
    lines,
    document_type
):
    """
    Phát hiện bảng và trích candidate từ các dòng dữ liệu.

    Không hard-code:
        Qty
        UnitPrice
        Amount
        tên sản phẩm
        số lượng cụ thể

    Tất cả dựa vào semantic field definitions.
    """

    candidates = []

    table_headers = find_table_header_rows(
        lines,
        document_type
    )

    for table in table_headers:

        header_line = table["line"]

        headers = table["headers"]

        columns = build_table_columns(
            headers
        )

        if len(columns) < 2:
            continue

        header_index = header_line.get(
            "index",
            0
        )

        header_page = header_line.get(
            "page",
            0
        )

        # ----------------------------------------------------
        # Đọc các dòng sau header
        # ----------------------------------------------------

        for line in lines:

            line_index = line.get(
                "index",
                0
            )

            if line_index <= header_index:
                continue

            if line.get(
                "page",
                0
            ) != header_page:
                continue

            # Không đi quá xa khỏi header.
            if (
                line_index
                > header_index + 30
            ):
                break

            # Nếu gặp một semantic label block mới
            # thì có thể đã ra khỏi bảng.
            line_hits = find_layout_label_hits(
                line,
                document_type
            )

            if line_hits:

                # Nếu dòng có >= 2 label,
                # đây có thể là bảng mới/header mới.
                if len(line_hits) >= 2:
                    break

                # Một label duy nhất có thể là
                # giá trị text hợp lệ trong bảng.
                # Nhưng không tự động dùng làm data row.
                continue

            row_candidates = parse_table_data_row(
                line,
                columns,
                document_type
            )

            for candidate in row_candidates:

                field = candidate.get(
                    "standard_field"
                )

                value = candidate.get(
                    "raw_value",
                    EMPTY
                )

                valid, validation_score = (
                    validate_semantic_candidate(
                        field,
                        value
                    )
                )

                if not valid:
                    continue

                candidate[
                    "semantic_score"
                ] = min(
                    1.0,
                    0.30
                    + (
                        validation_score
                        * 0.55
                    )
                )

                candidates.append(
                    candidate
                )

    return candidates


# ------------------------------------------------------------
# MERGE LABEL + TABLE CANDIDATES
# ------------------------------------------------------------

def merge_semantic_candidates(
    label_candidates,
    table_candidates
):
    """
    Gộp candidate từ:
        - label/value
        - table/layout

    Không tự overwrite.
    Candidate tốt hơn sẽ được chọn
    ở bước ranking sau.
    """

    merged = []

    for candidate in (
        label_candidates
        or []
    ):

        item = dict(
            candidate
        )

        if "semantic_score" not in item:

            item[
                "semantic_score"
            ] = item.get(
                "confidence",
                0
            )

        merged.append(
            item
        )

    for candidate in (
        table_candidates
        or []
    ):

        item = dict(
            candidate
        )

        if "semantic_score" not in item:

            item[
                "semantic_score"
            ] = item.get(
                "confidence",
                0
            )

        merged.append(
            item
        )

    return merged


# ------------------------------------------------------------
# DEDUPLICATE CANDIDATES
# ------------------------------------------------------------

def deduplicate_semantic_candidates(
    candidates
):
    """
    Loại candidate trùng hoàn toàn.

    Không loại các candidate khác giá trị,
    vì chúng có thể cần dùng cho CẦN KIỂM TRA.
    """

    result = []

    seen = set()

    for candidate in candidates:

        field = candidate.get(
            "standard_field",
            EMPTY
        )

        value = normalize_candidate_text(
            candidate.get(
                "raw_value",
                EMPTY
            )
        )

        source = candidate.get(
            "source",
            EMPTY
        )

        key = (
            field,
            value,
            source
        )

        if key in seen:
            continue

        seen.add(
            key
        )

        result.append(
            candidate
        )

    return result


# ------------------------------------------------------------
# LAYOUT SEMANTIC EXTRACTION
# ------------------------------------------------------------

def extract_layout_semantic_candidates(
    layout_tokens,
    document_type
):
    """
    Pipeline layout:

        TOKENS
          ↓
        LINES
          ↓
        LABEL POSITIONS
          ↓
        SAME-LINE VALUES
          ↓
        VERTICAL VALUES
          ↓
        TABLE HEADER
          ↓
        TABLE COLUMNS
          ↓
        TABLE ROWS
    """

    if not layout_tokens:
        return []

    lines = group_layout_tokens_into_lines(
        layout_tokens
    )

    if not lines:
        return []

    label_candidates = []

    # --------------------------------------------------------
    # LABEL/VALUE
    # --------------------------------------------------------

    for line_index, line in enumerate(
        lines
    ):

        label_hits = find_layout_label_hits(
            line,
            document_type
        )

        if not label_hits:
            continue

        for hit in label_hits:

            field = hit.get(
                "field"
            )

            # ------------------------------------------------
            # SAME LINE
            # ------------------------------------------------

            value = extract_layout_same_line_value(
                line,
                hit,
                document_type
            )

            source = "layout_same_line"

            # ------------------------------------------------
            # VERTICAL
            # ------------------------------------------------

            if not value:

                value = extract_layout_vertical_value(
                    lines,
                    line_index,
                    document_type
                )

                source = "layout_vertical"

            if not value:
                continue

            valid, validation_score = (
                validate_semantic_candidate(
                    field,
                    value
                )
            )

            if not valid:
                continue

            label_candidates.append({
                "standard_field":
                    field,

                "raw_value":
                    value,

                "source":
                    source,

                "alias":
                    hit.get(
                        "alias",
                        EMPTY
                    ),

                "line_index":
                    line_index,

                "semantic_score":
                    min(
                        1.0,
                        0.40
                        + (
                            validation_score
                            * 0.50
                        )
                    ),

                "confidence":
                    validation_score,
            })

    # --------------------------------------------------------
    # TABLE
    # --------------------------------------------------------

    table_candidates = extract_table_candidates(
        lines,
        document_type
    )

    # --------------------------------------------------------
    # MERGE
    # --------------------------------------------------------

    candidates = merge_semantic_candidates(
        label_candidates,
        table_candidates
    )

    candidates = deduplicate_semantic_candidates(
        candidates
    )

    return candidates


# ------------------------------------------------------------
# FINAL LAYOUT FIELD RESULT
# ------------------------------------------------------------

def build_layout_extraction_result(
    layout_tokens,
    document_type
):
    """
    Chọn candidate tốt nhất từ layout engine.

    Nếu có nhiều candidate khác nhau cho cùng field,
    không ghép chúng lại.
    """

    candidates = extract_layout_semantic_candidates(
        layout_tokens,
        document_type
    )

    grouped = group_candidates_by_field(
        candidates
    )

    result = {}

    for field, field_candidates in grouped.items():

        best = select_best_semantic_candidate(
            field_candidates
        )

        if not best:
            continue

        result[field] = {
            "value":
                best.get(
                    "raw_value",
                    EMPTY
                ),

            "raw_value":
                best.get(
                    "raw_value",
                    EMPTY
                ),

            "alias":
                best.get(
                    "alias",
                    EMPTY
                ),

            "source":
                best.get(
                    "source",
                    EMPTY
                ),

            "confidence":
                round(
                    best.get(
                        "semantic_score",
                        0
                    ),
                    4
                ),
        }

    return result


# ------------------------------------------------------------
# MERGE TEXT ENGINE + LAYOUT ENGINE
# ------------------------------------------------------------

def merge_extraction_engines(
    text_result,
    layout_result
):
    """
    Gộp kết quả text engine và layout engine.

    Layout engine được ưu tiên khi có confidence cao hơn.

    Không tự tạo field mới ngoài kết quả
    của hai engine.
    """

    final = {}

    text_result = (
        text_result
        if isinstance(
            text_result,
            dict
        )
        else {}
    )

    layout_result = (
        layout_result
        if isinstance(
            layout_result,
            dict
        )
        else {}
    )

    all_fields = set(
        text_result.keys()
    ).union(
        layout_result.keys()
    )

    for field in all_fields:

        text_item = text_result.get(
            field
        )

        layout_item = layout_result.get(
            field
        )

        if not text_item and not layout_item:
            continue

        if not text_item:

            final[field] = layout_item
            continue

        if not layout_item:

            final[field] = text_item
            continue

        text_confidence = float(
            text_item.get(
                "confidence",
                0
            )
            or 0
        )

        layout_confidence = float(
            layout_item.get(
                "confidence",
                0
            )
            or 0
        )

        # ----------------------------------------------------
        # Ưu tiên layout nếu:
        # - confidence cao hơn
        # - hoặc candidate text là table/header-like
        # ----------------------------------------------------

        if (
            layout_confidence
            > text_confidence
        ):

            final[field] = layout_item

        else:

            final[field] = text_item

    return final

# ============================================================
# PHẦN 7/9 — VALUE NORMALIZATION + DOCUMENT EXTRACTION PIPELINE
# ============================================================

# ------------------------------------------------------------
# 7.1 — BASIC NORMALIZATION
# ------------------------------------------------------------

def normalize_spaces(value):
    """
    Chuẩn hóa khoảng trắng nhưng không làm mất nội dung nghiệp vụ.
    """

    if value is None:
        return EMPTY

    value = str(value)
    value = value.replace("\n", " ").replace("\r", " ")
    value = re.sub(r"\s+", " ", value)

    return value.strip()


def normalize_punctuation(value):
    """
    Chuẩn hóa dấu câu cơ bản.
    Không suy diễn nội dung.
    """

    value = normalize_spaces(value)

    if not value:
        return EMPTY

    value = value.replace("：", ":")
    value = value.replace("–", "-")
    value = value.replace("—", "-")
    value = value.replace("‐", "-")

    return value.strip(" :;|")


def normalize_upper(value):
    """
    Uppercase dùng cho mã, ký hiệu, Incoterms...
    """

    value = normalize_punctuation(value)

    if not value:
        return EMPTY

    return value.upper()


# ------------------------------------------------------------
# 7.2 — DATE NORMALIZATION
# ------------------------------------------------------------

MONTH_MAP = {
    "JAN": "01",
    "JANUARY": "01",
    "FEB": "02",
    "FEBRUARY": "02",
    "MAR": "03",
    "MARCH": "03",
    "APR": "04",
    "APRIL": "04",
    "MAY": "05",
    "JUN": "06",
    "JUNE": "06",
    "JUL": "07",
    "JULY": "07",
    "AUG": "08",
    "AUGUST": "08",
    "SEP": "09",
    "SEPT": "09",
    "SEPTEMBER": "09",
    "OCT": "10",
    "OCTOBER": "10",
    "NOV": "11",
    "NOVEMBER": "11",
    "DEC": "12",
    "DECEMBER": "12",
}


def normalize_date_value(value):
    """
    Chuẩn hóa ngày về YYYY-MM-DD.

    Ví dụ:
        20-Jun-2026
        20/06/2026
        20-06-2026
        2026-06-20
        Jun 20, 2026
    """

    value = normalize_spaces(value)

    if not value or value == EMPTY:
        return EMPTY

    raw = value.strip()

    # YYYY-MM-DD
    m = re.fullmatch(
        r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})",
        raw
    )

    if m:
        year, month, day = m.groups()

        try:
            return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
        except Exception:
            return raw

    # DD/MM/YYYY hoặc DD-MM-YYYY
    m = re.fullmatch(
        r"(\d{1,2})[-/.](\d{1,2})[-/.](\d{2,4})",
        raw
    )

    if m:
        day, month, year = m.groups()

        if len(year) == 2:
            year = "20" + year

        try:
            return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
        except Exception:
            return raw

    # DD-MMM-YYYY
    m = re.fullmatch(
        r"(\d{1,2})[\s\-/.]+([A-Za-z]+)[\s\-/.]+(\d{2,4})",
        raw
    )

    if m:
        day, month_text, year = m.groups()

        month = MONTH_MAP.get(month_text.upper())

        if month:
            if len(year) == 2:
                year = "20" + year

            try:
                return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
            except Exception:
                return raw

    # MMM DD, YYYY
    m = re.fullmatch(
        r"([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{2,4})",
        raw
    )

    if m:
        month_text, day, year = m.groups()

        month = MONTH_MAP.get(month_text.upper())

        if month:
            if len(year) == 2:
                year = "20" + year

            try:
                return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
            except Exception:
                return raw

    return raw


# ------------------------------------------------------------
# 7.3 — NUMERIC NORMALIZATION
# ------------------------------------------------------------

def normalize_numeric_value(value):
    """
    Chuẩn hóa số.

    Ví dụ:
        13,406.40 -> 13406.40
        13.406,40 -> 13406.40
        5,762.50 KG -> 5762.50 KG
    """

    value = normalize_spaces(value)

    if not value or value == EMPTY:
        return EMPTY

    # Tìm phần số đầu tiên.
    m = re.search(
        r"[-+]?\d[\d\s,\.]*",
        value
    )

    if not m:
        return value

    number_text = m.group(0).strip()
    number_text = number_text.replace(" ", "")

    if "," in number_text and "." in number_text:

        # 1,234.56
        if number_text.rfind(".") > number_text.rfind(","):
            number_text = number_text.replace(",", "")

        # 1.234,56
        else:
            number_text = number_text.replace(".", "")
            number_text = number_text.replace(",", ".")

    elif "," in number_text:

        parts = number_text.split(",")

        # 12,50 -> decimal
        if len(parts) == 2 and len(parts[1]) <= 2:
            number_text = parts[0] + "." + parts[1]

        # 13,406 -> thousands
        else:
            number_text = number_text.replace(",", "")

    elif "." in number_text:

        parts = number_text.split(".")

        # Nhiều dấu chấm -> thường là phân cách hàng nghìn
        if len(parts) > 2:
            number_text = number_text.replace(".", "")

        # 13.406 có thể là 13.406 hoặc 13406.
        # Không tự đổi nếu không đủ bằng chứng.
        else:
            number_text = number_text

    return number_text


def normalize_numeric_with_unit(value):
    """
    Chuẩn hóa số + đơn vị nếu đơn vị thực sự xuất hiện.

    Ví dụ:
        5,762.50 KG -> 5762.50 KG
        125.50 CBM -> 125.50 CBM
    """

    value = normalize_spaces(value)

    if not value or value == EMPTY:
        return EMPTY

    number = normalize_numeric_value(value)

    if not number:
        return EMPTY

    unit_match = re.search(
        r"\b(KG|KGS|MT|TON|TONS|CBM|M3|M²|M2|PCS|PC|SET|SETS|CTN|CTNS|BOX|BOXES|PKG|PKGS)\b",
        value,
        re.I
    )

    if unit_match:
        unit = unit_match.group(1).upper()

        unit_map = {
            "KGS": "KG",
            "MT": "MT",
            "TON": "TON",
            "TONS": "TON",
            "M3": "CBM",
            "M²": "M2",
            "M2": "M2",
            "PCS": "PCS",
            "PC": "PCS",
            "SETS": "SET",
            "CTNS": "CTN",
            "BOXES": "BOX",
            "PKGS": "PKG",
        }

        unit = unit_map.get(unit, unit)

        return f"{number} {unit}"

    return number


# ------------------------------------------------------------
# 7.4 — CURRENCY NORMALIZATION
# ------------------------------------------------------------

CURRENCY_CANONICAL = {
    "USD": "USD",
    "US$": "USD",
    "$": "USD",
    "DOLLAR": "USD",
    "DOLLARS": "USD",

    "EUR": "EUR",
    "€": "EUR",
    "EURO": "EUR",
    "EUROS": "EUR",

    "CNY": "CNY",
    "RMB": "CNY",
    "¥": "CNY",
    "YUAN": "CNY",

    "VND": "VND",
    "VNĐ": "VND",
    "₫": "VND",

    "JPY": "JPY",
    "YEN": "JPY",

    "KRW": "KRW",
    "WON": "KRW",

    "GBP": "GBP",
    "£": "GBP",

    "AUD": "AUD",
    "CAD": "CAD",
    "CHF": "CHF",
    "SGD": "SGD",
}


def normalize_currency_value(value):
    """
    Chuẩn hóa tiền tệ về mã ISO phổ biến.
    """

    value = normalize_upper(value)

    if not value:
        return EMPTY

    # Thử match trực tiếp
    if value in CURRENCY_CANONICAL:
        return CURRENCY_CANONICAL[value]

    # Tìm currency code trong chuỗi
    for raw, canonical in CURRENCY_CANONICAL.items():

        if re.search(
            rf"(?<![A-Z]){re.escape(raw)}(?![A-Z])",
            value,
            re.I
        ):
            return canonical

    return value


# ------------------------------------------------------------
# 7.5 — INCOTERMS NORMALIZATION
# ------------------------------------------------------------

INCOTERM_LIST = [
    "EXW",
    "FCA",
    "FAS",
    "FOB",
    "CFR",
    "CIF",
    "CPT",
    "CIP",
    "DAP",
    "DPU",
    "DDP",
]


def normalize_incoterm_value(value):
    """
    Chuẩn hóa Incoterms về uppercase.

    Không tự thêm địa điểm nếu chứng từ không cung cấp.
    """

    value = normalize_upper(value)

    if not value:
        return EMPTY

    for term in INCOTERM_LIST:

        if re.search(
            rf"\b{re.escape(term)}\b",
            value
        ):
            return term

    return value


# ------------------------------------------------------------
# 7.6 — CONTAINER / SEAL NORMALIZATION
# ------------------------------------------------------------

def normalize_container_value(value):
    """
    Chuẩn hóa container number.

    Ví dụ:
        MSKU 123456 7 -> MSKU1234567
        msku1234567   -> MSKU1234567
    """

    value = normalize_upper(value)

    if not value:
        return EMPTY

    compact = re.sub(r"[^A-Z0-9]", "", value)

    # ISO container thường 4 chữ + 7 số
    m = re.search(
        r"[A-Z]{4}\d{7}",
        compact
    )

    if m:
        return m.group(0)

    return compact


def normalize_seal_value(value):
    """
    Seal number chỉ chuẩn hóa ký tự/khoảng trắng.
    Không ép theo một format cố định vì seal của từng hãng có thể khác.
    """

    value = normalize_upper(value)

    if not value:
        return EMPTY

    return re.sub(r"[^A-Z0-9\-]", "", value)


# ------------------------------------------------------------
# 7.7 — DOCUMENT / PARTY / LOCATION NORMALIZATION
# ------------------------------------------------------------

LEGAL_SUFFIXES = [
    "LIMITED LIABILITY COMPANY",
    "JOINT STOCK COMPANY",
    "CORPORATION",
    "COMPANY",
    "CO., LTD.",
    "CO., LTD",
    "CO LTD",
    "LTD.",
    "LTD",
    "INC.",
    "INC",
    "LLC",
    "JSC",
]


def normalize_company_value(value):
    """
    Chuẩn hóa tên doanh nghiệp để cross-check.

    Chỉ loại bỏ khác biệt hình thức.
    Không đổi tên doanh nghiệp sang tên khác.
    """

    value = normalize_upper(value)

    if not value:
        return EMPTY

    value = re.sub(r"[,\.;:]+", " ", value)
    value = normalize_spaces(value)

    return value


def normalize_port_value(value):
    """
    Chuẩn hóa cả chữ hoa và dấu câu.
    Không suy diễn quốc gia / cảng tương ứng.
    """

    value = normalize_upper(value)

    if not value:
        return EMPTY

    value = re.sub(r"[,\.;:]+", " ", value)
    value = normalize_spaces(value)

    return value


def normalize_address_value(value):
    """
    Chuẩn hóa địa chỉ.
    Không tự sửa hoặc suy diễn địa chỉ.
    """

    value = normalize_spaces(value)

    if not value:
        return EMPTY

    value = re.sub(r"[;,]+", ", ", value)
    value = re.sub(r"\s*,\s*", ", ", value)

    return value.strip(" ,")


def normalize_description_value(value):
    """
    Chuẩn hóa mô tả hàng hóa nhưng giữ nguyên nội dung.
    """

    value = normalize_spaces(value)

    if not value:
        return EMPTY

    value = value.strip(" :;|")

    return value


# ------------------------------------------------------------
# 7.8 — GENERIC IDENTIFIER NORMALIZATION
# ------------------------------------------------------------

def normalize_identifier_value(value):
    """
    Chuẩn hóa mã chứng từ:
    Invoice No., Contract No., PO No., Booking No., B/L No., C/O No...
    """

    value = normalize_upper(value)

    if not value:
        return EMPTY

    value = re.sub(r"\s+", "", value)
    value = value.strip(":#;,.")

    return value


def normalize_hs_code_value(value):
    """
    Chuẩn hóa HS code.

    Giữ dạng số, bỏ khoảng trắng/dấu chấm không cần thiết.
    Không tự bổ sung chữ số.
    """

    value = normalize_spaces(value)

    if not value:
        return EMPTY

    value = re.sub(r"\s+", "", value)

    # 9403.60 -> 940360
    if re.fullmatch(r"\d+(?:\.\d+)+", value):
        value = value.replace(".", "")

    return value


# ------------------------------------------------------------
# 7.9 — VESSEL / VOYAGE
# ------------------------------------------------------------

def normalize_vessel_value(value):
    """
    Chuẩn hóa tên tàu.
    """

    value = normalize_upper(value)

    if not value:
        return EMPTY

    value = re.sub(r"[,:;]+", " ", value)
    value = normalize_spaces(value)

    return value


def normalize_voyage_value(value):
    """
    Chuẩn hóa voyage.
    """

    value = normalize_upper(value)

    if not value:
        return EMPTY

    value = re.sub(r"\s+", "", value)
    value = value.strip(":#;,.")

    return value


def split_vessel_voyage(value):
    """
    Tách VESSEL_VOYAGE thành:
        VESSEL
        VOYAGE

    Chỉ tách khi có dấu phân cách hoặc cấu trúc rõ ràng.
    Không đoán tên tàu.
    """

    value = normalize_spaces(value)

    if not value or value == EMPTY:
        return EMPTY, EMPTY

    # Vessel / Voyage
    m = re.match(
        r"^(.*?)\s*[/|]\s*([A-Z0-9][A-Z0-9\-_]*)$",
        value,
        re.I
    )

    if m:
        vessel = normalize_vessel_value(m.group(1))
        voyage = normalize_voyage_value(m.group(2))

        if vessel and voyage:
            return vessel, voyage

    # Vessel - Voyage
    m = re.match(
        r"^(.+?)\s+-\s+([A-Z0-9][A-Z0-9\-_]*)$",
        value,
        re.I
    )

    if m:
        vessel = normalize_vessel_value(m.group(1))
        voyage = normalize_voyage_value(m.group(2))

        if vessel and voyage:
            return vessel, voyage

    # Không đủ bằng chứng để tách.
    return normalize_vessel_value(value), EMPTY


# ------------------------------------------------------------
# 7.10 — FIELD-SPECIFIC NORMALIZATION
# ------------------------------------------------------------

def normalize_field_value(field_name, value):
    """
    Bộ điều phối normalization theo standard field.
    """

    if value is None:
        return EMPTY

    value = clean_extracted_value(value)

    if not value or value == EMPTY:
        return EMPTY

    field = str(field_name).strip().upper()

    # -------------------------
    # DATE
    # -------------------------

    if field.endswith("_DATE"):
        return normalize_date_value(value)

    if field in {
        "ETA",
        "ETD",
        "ATA",
        "ATD",
        "SHIPMENT_TIME",
    }:

        normalized_date = normalize_date_value(value)

        if normalized_date != value:
            return normalized_date

        return normalize_spaces(value)

    # -------------------------
    # CURRENCY
    # -------------------------

    if field == "CURRENCY":
        return normalize_currency_value(value)

    # -------------------------
    # INCOTERMS
    # -------------------------

    if field == "INCOTERMS":
        return normalize_incoterm_value(value)

    # -------------------------
    # CONTAINER
    # -------------------------

    if field == "CONTAINER_NUMBER":
        return normalize_container_value(value)

    # -------------------------
    # SEAL
    # -------------------------

    if field == "SEAL_NUMBER":
        return normalize_seal_value(value)

    # -------------------------
    # HS CODE
    # -------------------------

    if field == "HS_CODE":
        return normalize_hs_code_value(value)

    # -------------------------
    # DOCUMENT IDs
    # -------------------------

    if field in {
        "INVOICE_NUMBER",
        "PACKING_LIST_NUMBER",
        "CONTRACT_NUMBER",
        "PO_NUMBER",
        "BL_NUMBER",
        "BOOKING_NUMBER",
        "CO_NUMBER",
    }:
        return normalize_identifier_value(value)

    # -------------------------
    # VESSEL
    # -------------------------

    if field == "VESSEL":
        return normalize_vessel_value(value)

    # -------------------------
    # VOYAGE
    # -------------------------

    if field == "VOYAGE":
        return normalize_voyage_value(value)

    # -------------------------
    # VESSEL + VOYAGE
    # -------------------------

    if field == "VESSEL_VOYAGE":
        vessel, voyage = split_vessel_voyage(value)

        if vessel and voyage:
            return f"{vessel} / {voyage}"

        return vessel

    # -------------------------
    # NUMERIC FIELDS
    # -------------------------

    if field in {
        "QUANTITY",
        "PACKAGE_COUNT",
        "UNIT_PRICE",
        "TOTAL_AMOUNT",
        "GROSS_WEIGHT",
        "NET_WEIGHT",
        "TARE_WEIGHT",
        "MEASUREMENT",
    }:
        return normalize_numeric_with_unit(value)

    # -------------------------
    # COMPANY / PARTY
    # -------------------------

    if field in {
        "EXPORTER",
        "IMPORTER",
        "CONSIGNEE",
        "NOTIFY_PARTY",
    }:
        return normalize_company_value(value)

    # -------------------------
    # PORT / LOCATION
    # -------------------------

    if field in {
        "PORT_OF_LOADING",
        "PORT_OF_DISCHARGE",
        "PLACE_OF_RECEIPT",
        "FINAL_DESTINATION",
    }:
        return normalize_port_value(value)

    # -------------------------
    # ADDRESS
    # -------------------------

    if field.endswith("_ADDRESS"):
        return normalize_address_value(value)

    # -------------------------
    # DESCRIPTION
    # -------------------------

    if field == "DESCRIPTION":
        return normalize_description_value(value)

    # -------------------------
    # DEFAULT
    # -------------------------

    return normalize_punctuation(value)


# ------------------------------------------------------------
# 7.11 — NORMALIZE ONE CANDIDATE
# ------------------------------------------------------------

def normalize_semantic_candidate(candidate):
    """
    Chuẩn hóa một candidate nhưng giữ nguyên metadata.

    Không thay đổi:
        field
        confidence
        source
        label
        page
        coordinates
    """

    if not isinstance(candidate, dict):
        return None

    result = dict(candidate)

    field_name = (
        candidate.get("field")
        or candidate.get("standard_field")
        or candidate.get("field_name")
        or EMPTY
    )

    raw_value = (
        candidate.get("raw_value")
        or candidate.get("value")
        or EMPTY
    )

    field_name = str(field_name).strip().upper()

    if not field_name or not raw_value:
        return None

    normalized = normalize_field_value(
        field_name,
        raw_value
    )

    result["field"] = field_name
    result["raw_value"] = clean_extracted_value(raw_value)
    result["normalized_value"] = normalized

    return result


# ------------------------------------------------------------
# 7.12 — NORMALIZE EXTRACTION RESULT
# ------------------------------------------------------------

def normalize_extraction_result(extraction_result):
    """
    Chuẩn hóa toàn bộ kết quả extraction.

    Hỗ trợ:
        list[candidate]
        dict[field] = value
    """

    if extraction_result is None:
        return []

    normalized_results = []

    # ----------------------------------------
    # CASE 1 — LIST CANDIDATES
    # ----------------------------------------

    if isinstance(extraction_result, list):

        for candidate in extraction_result:

            normalized_candidate = normalize_semantic_candidate(
                candidate
            )

            if normalized_candidate:
                normalized_results.append(
                    normalized_candidate
                )

        return normalized_results

    # ----------------------------------------
    # CASE 2 — DICT FIELD -> VALUE
    # ----------------------------------------

    if isinstance(extraction_result, dict):

        for field_name, value in extraction_result.items():

            if isinstance(value, dict):

                candidate = dict(value)

                candidate.setdefault(
                    "field",
                    field_name
                )

            else:

                candidate = {
                    "field": field_name,
                    "raw_value": value,
                    "normalized_value": EMPTY,
                    "confidence": 0.0,
                    "source": "normalization",
                }

            normalized_candidate = normalize_semantic_candidate(
                candidate
            )

            if normalized_candidate:
                normalized_results.append(
                    normalized_candidate
                )

    return normalized_results


# ------------------------------------------------------------
# 7.13 — BUILD FIELD VALUE MAP
# ------------------------------------------------------------

def build_normalized_field_map(candidates):
    """
    Chuyển list candidate thành:

        {
            "EXPORTER": {
                "value": "...",
                "confidence": 0.95,
                ...
            }
        }

    Mỗi field chỉ giữ candidate tốt nhất.
    """

    field_map = {}

    if not candidates:
        return field_map

    for candidate in candidates:

        if not isinstance(candidate, dict):
            continue

        field = (
            candidate.get("field")
            or candidate.get("standard_field")
            or candidate.get("field_name")
            or EMPTY
        )

        field = str(field).strip().upper()

        if not field:
            continue

        value = (
            candidate.get("normalized_value")
            or candidate.get("raw_value")
            or candidate.get("value")
            or EMPTY
        )

        if not value or value == EMPTY:
            continue

        confidence = candidate.get(
            "confidence",
            0.0
        )

        try:
            confidence = float(confidence)
        except Exception:
            confidence = 0.0

        existing = field_map.get(field)

        if existing is None:

            field_map[field] = candidate
            continue

        try:
            existing_confidence = float(
                existing.get("confidence", 0.0)
            )
        except Exception:
            existing_confidence = 0.0

        # Candidate confidence cao hơn -> thay thế
        if confidence > existing_confidence:

            field_map[field] = candidate

    return field_map


# ------------------------------------------------------------
# 7.14 — SPLIT VESSEL_VOYAGE RESULT
# ------------------------------------------------------------

def expand_vessel_voyage_candidates(candidates):
    """
    Nếu engine tìm thấy VESSEL_VOYAGE,
    tách thành VESSEL và VOYAGE khi có đủ bằng chứng.

    Không tự tạo nếu không tách được.
    """

    expanded = []

    for candidate in candidates:

        if not isinstance(candidate, dict):
            continue

        field = str(
            candidate.get("field", "")
        ).strip().upper()

        if field != "VESSEL_VOYAGE":

            expanded.append(candidate)
            continue

        value = (
            candidate.get("normalized_value")
            or candidate.get("raw_value")
            or EMPTY
        )

        vessel, voyage = split_vessel_voyage(value)

        if vessel and voyage:

            vessel_candidate = dict(candidate)
            vessel_candidate["field"] = "VESSEL"
            vessel_candidate["raw_value"] = vessel
            vessel_candidate["normalized_value"] = vessel

            voyage_candidate = dict(candidate)
            voyage_candidate["field"] = "VOYAGE"
            voyage_candidate["raw_value"] = voyage
            voyage_candidate["normalized_value"] = voyage

            expanded.append(vessel_candidate)
            expanded.append(voyage_candidate)

        else:

            # Không đủ dữ liệu để tách.
            # Giữ VESSEL_VOYAGE thay vì đoán.
            expanded.append(candidate)

    return expanded


# ------------------------------------------------------------
# 7.15 — DOCUMENT EXTRACTION CONTEXT
# ------------------------------------------------------------

def build_document_context(
    document_type,
    raw_text,
    layout_document=None
):
    """
    Tạo context thống nhất cho một chứng từ.

    Engine phía dưới chỉ sử dụng:
        - document_type
        - raw_text
        - layout
        - knowledge base
        - database aliases

    Không chứa dữ liệu mẫu cụ thể.
    """

    return {
        "document_type": document_type or EMPTY,
        "raw_text": raw_text or EMPTY,
        "layout": layout_document,
        "scope": get_document_scope(
            document_type
        ),
    }


# ------------------------------------------------------------
# 7.16 — EXTRACT DOCUMENT SEMANTIC
# ------------------------------------------------------------

def extract_document_semantic(
    document_type,
    raw_text,
    layout_document=None
):
    """
    Extraction pipeline chính.

    Ưu tiên:
        1. Layout semantic engine
        2. Text semantic engine

    Sau đó:
        normalize
        split vessel/voyage
        deduplicate
        select best
    """

    raw_text = raw_text or EMPTY

    context = build_document_context(
        document_type=document_type,
        raw_text=raw_text,
        layout_document=layout_document,
    )

    # --------------------------------------------------------
    # STEP 1 — LAYOUT ENGINE
    # --------------------------------------------------------

    layout_candidates = []

    if layout_document:

        try:

            layout_candidates = extract_layout_semantic_candidates(
                layout_document,
                document_type=document_type,
            )

        except Exception:
            layout_candidates = []

    # --------------------------------------------------------
    # STEP 2 — TEXT ENGINE
    # --------------------------------------------------------

    text_candidates = []

    if raw_text:

        try:

            text_candidates = extract_label_value_candidates(
                raw_text,
                document_type=document_type,
            )

        except TypeError:

            # Trường hợp hàm cũ chỉ nhận text.
            try:
                text_candidates = extract_label_value_candidates(
                    raw_text
                )
            except Exception:
                text_candidates = []

        except Exception:
            text_candidates = []

    # --------------------------------------------------------
    # STEP 3 — MERGE
    # --------------------------------------------------------

    merged = merge_semantic_candidates(
        layout_candidates,
        text_candidates,
    )

    # --------------------------------------------------------
    # STEP 4 — DEDUPLICATE
    # --------------------------------------------------------

    merged = deduplicate_semantic_candidates(
        merged
    )

    # --------------------------------------------------------
    # STEP 5 — NORMALIZE
    # --------------------------------------------------------

    normalized = normalize_extraction_result(
        merged
    )

    # --------------------------------------------------------
    # STEP 6 — SPLIT VESSEL / VOYAGE
    # --------------------------------------------------------

    normalized = expand_vessel_voyage_candidates(
        normalized
    )

    # --------------------------------------------------------
    # STEP 7 — DEDUPLICATE AGAIN
    # --------------------------------------------------------

    normalized = deduplicate_semantic_candidates(
        normalized
    )

    # --------------------------------------------------------
    # STEP 8 — FINAL BEST CANDIDATE PER FIELD
    # --------------------------------------------------------

    field_map = build_normalized_field_map(
        normalized
    )

    return {
        "document_type": document_type,
        "raw_text": raw_text,
        "candidates": normalized,
        "fields": field_map,
    }


# ------------------------------------------------------------
# 7.17 — COMPATIBILITY WRAPPER
# ------------------------------------------------------------

def extract_document(
    document_type,
    text,
    layout_document=None
):
    """
    Wrapper tương thích với pipeline cũ.

    Code phía UI có thể tiếp tục gọi:

        extract_document(document_type, text)

    hoặc:

        extract_document(
            document_type,
            text,
            layout_document
        )
    """

    result = extract_document_semantic(
        document_type=document_type,
        raw_text=text,
        layout_document=layout_document,
    )

    return result


# ------------------------------------------------------------
# 7.18 — CONVERT RESULT TO SIMPLE FIELD DICT
# ------------------------------------------------------------

def extraction_result_to_field_dict(result):
    """
    Chuyển extraction result thành:

        {
            "EXPORTER": "...",
            "IMPORTER": "...",
            ...
        }

    Chỉ lấy normalized_value của candidate tốt nhất.
    """

    if not result:
        return {}

    if isinstance(result, dict):

        field_map = result.get("fields")

        if isinstance(field_map, dict):

            output = {}

            for field, candidate in field_map.items():

                if isinstance(candidate, dict):

                    value = (
                        candidate.get("normalized_value")
                        or candidate.get("raw_value")
                        or EMPTY
                    )

                else:
                    value = candidate

                if value and value != EMPTY:
                    output[field] = value

            return output

    return {}


# ------------------------------------------------------------
# 7.19 — BUILD STANDARD EXTRACTION RECORD
# ------------------------------------------------------------

def build_standard_extraction_record(
    field_name,
    candidate,
    document_type
):
    """
    Chuẩn hóa record dùng cho:
        UI
        database
        cross-check
        customs data
    """

    if not candidate:
        return None

    field_name = str(
        field_name or candidate.get("field", "")
    ).strip().upper()

    if not field_name:
        return None

    raw_value = (
        candidate.get("raw_value")
        or candidate.get("value")
        or EMPTY
    )

    normalized_value = (
        candidate.get("normalized_value")
        or normalize_field_value(
            field_name,
            raw_value
        )
    )

    confidence = candidate.get(
        "confidence",
        0.0
    )

    try:
        confidence = float(confidence)
    except Exception:
        confidence = 0.0

    return {
        "field_name": field_name,
        "display_name": get_field_display_name(
            field_name
        ),
        "document_type": document_type,
        "raw_value": raw_value,
        "normalized_value": normalized_value,
        "confidence": confidence,
        "source": candidate.get(
            "source",
            "semantic_engine"
        ),
        "raw_label": candidate.get(
            "label",
            candidate.get(
                "raw_label",
                EMPTY
            )
        ),
        "page": candidate.get(
            "page"
        ),
        "x0": candidate.get(
            "x0"
        ),
        "y0": candidate.get(
            "y0"
        ),
        "x1": candidate.get(
            "x1"
        ),
        "y1": candidate.get(
            "y1"
        ),
    }


# ------------------------------------------------------------
# 7.20 — BUILD DOCUMENT FIELD RECORDS
# ------------------------------------------------------------

def build_document_field_records(
    extraction_result
):
    """
    Tạo danh sách record chuẩn cho một chứng từ.
    """

    if not extraction_result:
        return []

    document_type = extraction_result.get(
        "document_type",
        EMPTY
    )

    field_map = extraction_result.get(
        "fields",
        {}
    )

    records = []

    for field_name, candidate in field_map.items():

        record = build_standard_extraction_record(
            field_name=field_name,
            candidate=candidate,
            document_type=document_type,
        )

        if record:
            records.append(record)

    return records


# ------------------------------------------------------------
# 7.21 — GET EXTRACTED VALUE
# ------------------------------------------------------------

def get_extracted_value(
    extraction_result,
    field_name
):
    """
    Lấy normalized value của một field.
    Nếu không có -> EMPTY.
    """

    if not extraction_result:
        return EMPTY

    field_name = str(
        field_name
    ).strip().upper()

    fields = extraction_result.get(
        "fields",
        {}
    )

    candidate = fields.get(
        field_name
    )

    if not candidate:
        return EMPTY

    if isinstance(candidate, dict):

        return (
            candidate.get("normalized_value")
            or candidate.get("raw_value")
            or EMPTY
        )

    return str(candidate)


# ------------------------------------------------------------
# 7.22 — CHECK DOCUMENT FIELD SCOPE
# ------------------------------------------------------------

def filter_extraction_by_document_scope(
    extraction_result
):
    """
    Không cho phép candidate thuộc field ngoài scope
    của loại chứng từ.

    Đây là lớp bảo vệ semantic cuối cùng.
    """

    if not extraction_result:
        return extraction_result

    document_type = extraction_result.get(
        "document_type",
        EMPTY
    )

    scope = get_document_scope(
        document_type
    )

    if not scope:
        return extraction_result

    candidates = extraction_result.get(
        "candidates",
        []
    )

    filtered = []

    for candidate in candidates:

        if not isinstance(candidate, dict):
            continue

        field_name = str(
            candidate.get("field", "")
        ).strip().upper()

        if field_name not in scope:
            continue

        filtered.append(candidate)

    extraction_result["candidates"] = filtered

    extraction_result["fields"] = (
        build_normalized_field_map(
            filtered
        )
    )

    return extraction_result


# ------------------------------------------------------------
# 7.23 — FINAL DOCUMENT PIPELINE
# ------------------------------------------------------------

def process_document_semantically(
    document_type,
    raw_text,
    layout_document=None
):
    """
    Pipeline cuối cùng cho từng chứng từ:

        RAW TEXT
           ↓
        LAYOUT
           ↓
        SEMANTIC LABEL
           ↓
        VALUE CANDIDATE
           ↓
        VALIDATION
           ↓
        NORMALIZATION
           ↓
        VESSEL/VOYAGE SPLIT
           ↓
        DOCUMENT SCOPE
           ↓
        FINAL FIELDS
    """

    result = extract_document_semantic(
        document_type=document_type,
        raw_text=raw_text,
        layout_document=layout_document,
    )

    result = filter_extraction_by_document_scope(
        result
    )

    result["records"] = (
        build_document_field_records(
            result
        )
    )

    return result


# ============================================================
# KẾT THÚC PHẦN 7/9
# ============================================================


# ============================================================
# PHẦN 8/9 — MULTI-DOCUMENT MERGE + CUSTOMS DATA
# ============================================================


# ------------------------------------------------------------
# 8.1 — DOCUMENT PRIORITY
# ------------------------------------------------------------

DOCUMENT_PRIORITY = {
    "PURCHASE CONTRACT": 1,
    "COMMERCIAL INVOICE": 2,
    "PACKING LIST": 3,
    "BILL OF LADING": 4,
    "BOOKING": 5,
    "CERTIFICATE OF ORIGIN": 6,
    "ARRIVAL NOTICE": 7,
}


def get_document_priority(document_type):
    """
    Xác định độ ưu tiên của loại chứng từ.

    Lưu ý:
    Priority chỉ dùng để chọn candidate khi cần hiển thị
    dữ liệu tổng hợp.

    Không có nghĩa chứng từ có priority cao hơn luôn đúng.
    Cross-check vẫn phải đối chiếu dữ liệu độc lập.
    """

    document_type = str(
        document_type or EMPTY
    ).strip().upper()

    return DOCUMENT_PRIORITY.get(
        document_type,
        99
    )


# ------------------------------------------------------------
# 8.2 — DOCUMENT CONTAINER
# ------------------------------------------------------------

def normalize_document_record(document):
    """
    Chuẩn hóa cấu trúc một document record.

    Hỗ trợ nhiều dạng dữ liệu khác nhau từ pipeline cũ.
    """

    if not isinstance(document, dict):
        return None

    document_type = (
        document.get("document_type")
        or document.get("type")
        or document.get("doc_type")
        or EMPTY
    )

    document_type = str(
        document_type
    ).strip().upper()

    file_name = (
        document.get("file_name")
        or document.get("filename")
        or EMPTY
    )

    raw_text = (
        document.get("raw_text")
        or document.get("text")
        or EMPTY
    )

    extraction = (
        document.get("extraction")
        or document.get("result")
        or {}
    )

    # Trường hợp document đã có fields trực tiếp
    if not extraction and document.get("fields"):
        extraction = {
            "document_type": document_type,
            "fields": document.get("fields", {}),
            "candidates": document.get(
                "candidates",
                []
            ),
        }

    return {
        "document_type": document_type,
        "file_name": file_name,
        "raw_text": raw_text,
        "extraction": extraction,
        "priority": get_document_priority(
            document_type
        ),
    }


# ------------------------------------------------------------
# 8.3 — GET DOCUMENT FIELDS
# ------------------------------------------------------------

def get_document_fields(document):
    """
    Lấy field map của một document.
    """

    if not isinstance(document, dict):
        return {}

    extraction = document.get(
        "extraction",
        {}
    )

    if isinstance(extraction, dict):

        fields = extraction.get(
            "fields",
            {}
        )

        if isinstance(fields, dict):
            return fields

    fields = document.get(
        "fields",
        {}
    )

    if isinstance(fields, dict):
        return fields

    return {}


# ------------------------------------------------------------
# 8.4 — GET CANDIDATE FROM DOCUMENT
# ------------------------------------------------------------

def get_document_candidate(
    document,
    field_name
):
    """
    Lấy candidate tốt nhất của field từ document.
    """

    field_name = str(
        field_name or EMPTY
    ).strip().upper()

    fields = get_document_fields(
        document
    )

    candidate = fields.get(
        field_name
    )

    if not candidate:
        return None

    if isinstance(candidate, dict):
        return candidate

    return {
        "field": field_name,
        "raw_value": str(candidate),
        "normalized_value": str(candidate),
        "confidence": 0.0,
    }


# ------------------------------------------------------------
# 8.5 — GET CANDIDATE VALUE
# ------------------------------------------------------------

def get_candidate_normalized_value(
    candidate
):
    """
    Ưu tiên normalized_value.
    """

    if not candidate:
        return EMPTY

    if isinstance(candidate, dict):

        value = (
            candidate.get("normalized_value")
            or candidate.get("raw_value")
            or candidate.get("value")
            or EMPTY
        )

        return normalize_spaces(value)

    return normalize_spaces(candidate)


def get_candidate_raw_value(
    candidate
):
    """
    Lấy raw value.
    """

    if not candidate:
        return EMPTY

    if isinstance(candidate, dict):

        value = (
            candidate.get("raw_value")
            or candidate.get("value")
            or candidate.get("normalized_value")
            or EMPTY
        )

        return normalize_spaces(value)

    return normalize_spaces(candidate)


def get_candidate_confidence(
    candidate
):
    """
    Lấy confidence an toàn.
    """

    if not candidate:
        return 0.0

    if isinstance(candidate, dict):

        try:
            return float(
                candidate.get(
                    "confidence",
                    0.0
                )
            )
        except Exception:
            return 0.0

    return 0.0


# ------------------------------------------------------------
# 8.6 — BUILD DOCUMENT VALUE SOURCES
# ------------------------------------------------------------

def collect_field_sources(
    documents,
    field_name
):
    """
    Thu thập tất cả giá trị của một field
    từ tất cả chứng từ.

    Ví dụ:

        CONTRACT_NUMBER

        PURCHASE CONTRACT -> SS1255US
        COMMERCIAL INVOICE -> SS1255US
        PACKING LIST -> SS1255US

    Không sửa hoặc chọn winner ở bước này.
    """

    field_name = str(
        field_name or EMPTY
    ).strip().upper()

    sources = []

    for document in documents:

        normalized_document = (
            normalize_document_record(
                document
            )
        )

        if not normalized_document:
            continue

        candidate = get_document_candidate(
            normalized_document,
            field_name
        )

        if not candidate:
            continue

        value = get_candidate_normalized_value(
            candidate
        )

        if not value:
            continue

        sources.append({
            "field_name": field_name,
            "document_type": normalized_document[
                "document_type"
            ],
            "file_name": normalized_document[
                "file_name"
            ],
            "raw_value": get_candidate_raw_value(
                candidate
            ),
            "normalized_value": value,
            "confidence": get_candidate_confidence(
                candidate
            ),
            "priority": normalized_document[
                "priority"
            ],
            "source": candidate.get(
                "source",
                "semantic_engine"
            )
            if isinstance(candidate, dict)
            else "semantic_engine",
        })

    return sources


# ------------------------------------------------------------
# 8.7 — BUILD ALL FIELD SOURCES
# ------------------------------------------------------------

def collect_all_field_sources(
    documents
):
    """
    Gom toàn bộ field xuất hiện trong tất cả chứng từ.
    """

    field_sources = {}

    for document in documents:

        fields = get_document_fields(
            document
        )

        for field_name in fields.keys():

            field_name = str(
                field_name
            ).strip().upper()

            if not field_name:
                continue

            if field_name not in field_sources:
                field_sources[field_name] = (
                    collect_field_sources(
                        documents,
                        field_name
                    )
                )

    return field_sources


# ------------------------------------------------------------
# 8.8 — CHOOSE REPRESENTATIVE VALUE
# ------------------------------------------------------------

def choose_representative_source(
    sources
):
    """
    Chọn một source đại diện để hiển thị trong
    consolidated data.

    Quy tắc:

    1. Confidence cao hơn.
    2. Nếu confidence bằng nhau -> priority chứng từ.
    3. Nếu vẫn bằng nhau -> giữ source đầu tiên.

    QUAN TRỌNG:
    Đây chỉ là giá trị đại diện để hiển thị.
    Không đồng nghĩa với "giá trị đúng".
    """

    if not sources:
        return None

    valid_sources = [
        source
        for source in sources
        if source.get(
            "normalized_value",
            EMPTY
        )
    ]

    if not valid_sources:
        return None

    sorted_sources = sorted(
        valid_sources,
        key=lambda x: (
            -float(
                x.get(
                    "confidence",
                    0.0
                )
            ),
            int(
                x.get(
                    "priority",
                    99
                )
            ),
        )
    )

    return sorted_sources[0]


# ------------------------------------------------------------
# 8.9 — COMPARE SOURCE VALUES
# ------------------------------------------------------------

def compare_source_values(
    sources
):
    """
    So sánh các giá trị độc lập của cùng một field.

    Không tự sửa giá trị.
    """

    if not sources:
        return {
            "status": "CẦN KIỂM TRA",
            "reason": "Không có dữ liệu",
            "values": [],
        }

    unique_values = []

    for source in sources:

        value = normalize_spaces(
            source.get(
                "normalized_value",
                EMPTY
            )
        )

        if not value:
            continue

        if value not in unique_values:
            unique_values.append(value)

    # Chỉ có một nguồn
    if len(sources) == 1:

        return {
            "status": "CẦN KIỂM TRA",
            "reason": "Chỉ có một nguồn dữ liệu",
            "values": unique_values,
        }

    # Có nhiều nguồn nhưng thiếu dữ liệu thực tế
    if len(unique_values) == 0:

        return {
            "status": "CẦN KIỂM TRA",
            "reason": "Không có giá trị để đối chiếu",
            "values": [],
        }

    # Tất cả giống nhau
    if len(unique_values) == 1:

        return {
            "status": "KHỚP",
            "reason": "Các nguồn dữ liệu có cùng giá trị",
            "values": unique_values,
        }

    # Có giá trị khác nhau
    return {
        "status": "KHÔNG KHỚP",
        "reason": "Các nguồn dữ liệu có giá trị khác nhau",
        "values": unique_values,
    }


# ------------------------------------------------------------
# 8.10 — BUILD CONSOLIDATED FIELD
# ------------------------------------------------------------

def build_consolidated_field(
    field_name,
    sources
):
    """
    Tạo record tổng hợp cho một standard field.
    """

    field_name = str(
        field_name or EMPTY
    ).strip().upper()

    if not field_name:
        return None

    comparison = compare_source_values(
        sources
    )

    representative = (
        choose_representative_source(
            sources
        )
    )

    if representative:

        value = representative.get(
            "normalized_value",
            EMPTY
        )

        raw_value = representative.get(
            "raw_value",
            EMPTY
        )

        confidence = representative.get(
            "confidence",
            0.0
        )

        source_document = representative.get(
            "document_type",
            EMPTY
        )

        source_file = representative.get(
            "file_name",
            EMPTY
        )

    else:

        value = EMPTY
        raw_value = EMPTY
        confidence = 0.0
        source_document = EMPTY
        source_file = EMPTY

    return {
        "field_name": field_name,
        "display_name": get_field_display_name(
            field_name
        ),
        "group": get_field_group(
            field_name
        ),
        "value": value,
        "raw_value": raw_value,
        "confidence": confidence,
        "source_document": source_document,
        "source_file": source_file,
        "status": comparison[
            "status"
        ],
        "reason": comparison[
            "reason"
        ],
        "sources": sources,
    }


# ------------------------------------------------------------
# 8.11 — BUILD CONSOLIDATED DATA
# ------------------------------------------------------------

def build_consolidated_data(
    documents
):
    """
    Gom toàn bộ chứng từ thành một dataset chuẩn.

    Đây là tầng trung gian giữa:
        Document Extraction
        và
        Cross-check / Customs Data
    """

    if not documents:
        return {
            "fields": {},
            "groups": {},
            "documents": [],
        }

    normalized_documents = []

    for document in documents:

        normalized_document = (
            normalize_document_record(
                document
            )
        )

        if normalized_document:
            normalized_documents.append(
                normalized_document
            )

    field_sources = collect_all_field_sources(
        normalized_documents
    )

    consolidated_fields = {}

    for field_name, sources in field_sources.items():

        record = build_consolidated_field(
            field_name,
            sources
        )

        if record:
            consolidated_fields[
                field_name
            ] = record

    # --------------------------------------------------------
    # GROUP FIELDS
    # --------------------------------------------------------

    groups = {}

    for field_name, record in consolidated_fields.items():

        group = record.get(
            "group",
            "OTHER"
        )

        if group not in groups:
            groups[group] = {}

        groups[group][field_name] = record

    return {
        "fields": consolidated_fields,
        "groups": groups,
        "documents": normalized_documents,
    }


# ------------------------------------------------------------
# 8.12 — CUSTOMS FIELD GROUPS
# ------------------------------------------------------------

CUSTOMS_FIELD_GROUPS = {
    "PARTIES": [
        "EXPORTER",
        "IMPORTER",
        "CONSIGNEE",
        "NOTIFY_PARTY",
    ],

    "DOCUMENTS": [
        "CONTRACT_NUMBER",
        "CONTRACT_DATE",
        "INVOICE_NUMBER",
        "INVOICE_DATE",
        "PACKING_LIST_NUMBER",
        "PACKING_LIST_DATE",
        "PO_NUMBER",
        "BL_NUMBER",
        "BOOKING_NUMBER",
        "CO_NUMBER",
    ],

    "CARGO": [
        "DESCRIPTION",
        "HS_CODE",
        "QUANTITY",
        "PACKAGE_COUNT",
        "GROSS_WEIGHT",
        "NET_WEIGHT",
        "MEASUREMENT",
        "COUNTRY_OF_ORIGIN",
    ],

    "COMMERCIAL": [
        "UNIT_PRICE",
        "TOTAL_AMOUNT",
        "CURRENCY",
        "INCOTERMS",
        "PAYMENT_TERMS",
    ],

    "SHIPPING": [
        "CONTAINER_NUMBER",
        "SEAL_NUMBER",
        "VESSEL",
        "VOYAGE",
        "VESSEL_VOYAGE",
        "PORT_OF_LOADING",
        "PORT_OF_DISCHARGE",
        "PLACE_OF_RECEIPT",
        "FINAL_DESTINATION",
        "ETA",
        "ETD",
    ],
}


# ------------------------------------------------------------
# 8.13 — BUILD CUSTOMS DATA
# ------------------------------------------------------------

def build_customs_data(
    documents
):
    """
    Tạo dataset phục vụ kiểm tra dữ liệu khai báo hải quan.

    Không tự điền field còn thiếu.
    Không lấy Contract No. làm Invoice No.
    Không lấy dữ liệu chứng từ này để "bịa" dữ liệu
    cho chứng từ khác.

    Dữ liệu được lấy từ actual extracted values.
    """

    consolidated = build_consolidated_data(
        documents
    )

    customs_data = []

    fields = consolidated.get(
        "fields",
        {}
    )

    # --------------------------------------------------------
    # GIỮ THỨ TỰ THEO NHÓM NGHIỆP VỤ
    # --------------------------------------------------------

    processed = set()

    for group_name, field_list in CUSTOMS_FIELD_GROUPS.items():

        for field_name in field_list:

            if field_name in processed:
                continue

            processed.add(field_name)

            record = fields.get(
                field_name
            )

            if record:

                customs_data.append({
                    "group": group_name,
                    "field_name": field_name,
                    "display_name": get_field_display_name(
                        field_name
                    ),
                    "value": record.get(
                        "value",
                        EMPTY
                    ),
                    "source_document": record.get(
                        "source_document",
                        EMPTY
                    ),
                    "source_file": record.get(
                        "source_file",
                        EMPTY
                    ),
                    "confidence": record.get(
                        "confidence",
                        0.0
                    ),
                    "status": record.get(
                        "status",
                        "CẦN KIỂM TRA"
                    ),
                    "reason": record.get(
                        "reason",
                        EMPTY
                    ),
                })

            else:

                # Field nằm trong bộ customs chuẩn
                # nhưng không tìm thấy trong chứng từ.
                customs_data.append({
                    "group": group_name,
                    "field_name": field_name,
                    "display_name": get_field_display_name(
                        field_name
                    ),
                    "value": EMPTY,
                    "source_document": EMPTY,
                    "source_file": EMPTY,
                    "confidence": 0.0,
                    "status": "CẦN KIỂM TRA",
                    "reason": "Không tìm thấy dữ liệu",
                })

    # --------------------------------------------------------
    # FIELD NGOÀI CUSTOMS GROUP
    # --------------------------------------------------------

    for field_name, record in fields.items():

        if field_name in processed:
            continue

        customs_data.append({
            "group": record.get(
                "group",
                "OTHER"
            ),
            "field_name": field_name,
            "display_name": record.get(
                "display_name",
                field_name
            ),
            "value": record.get(
                "value",
                EMPTY
            ),
            "source_document": record.get(
                "source_document",
                EMPTY
            ),
            "source_file": record.get(
                "source_file",
                EMPTY
            ),
            "confidence": record.get(
                "confidence",
                0.0
            ),
            "status": record.get(
                "status",
                "CẦN KIỂM TRA"
            ),
            "reason": record.get(
                "reason",
                EMPTY
            ),
        })

    return {
        "data": customs_data,
        "fields": fields,
        "groups": consolidated.get(
            "groups",
            {}
        ),
        "documents": consolidated.get(
            "documents",
            []
        ),
    }


# ------------------------------------------------------------
# 8.14 — GET CUSTOMS VALUE
# ------------------------------------------------------------

def get_customs_value(
    customs_data,
    field_name
):
    """
    Lấy giá trị field từ customs dataset.
    """

    if not customs_data:
        return EMPTY

    field_name = str(
        field_name
    ).strip().upper()

    fields = customs_data.get(
        "fields",
        {}
    )

    record = fields.get(
        field_name
    )

    if not record:
        return EMPTY

    return record.get(
        "value",
        EMPTY
    )


# ------------------------------------------------------------
# 8.15 — GET CUSTOMS STATUS
# ------------------------------------------------------------

def get_customs_status(
    customs_data,
    field_name
):
    """
    Lấy trạng thái cross-source của field.
    """

    if not customs_data:
        return "CẦN KIỂM TRA"

    field_name = str(
        field_name
    ).strip().upper()

    fields = customs_data.get(
        "fields",
        {}
    )

    record = fields.get(
        field_name
    )

    if not record:
        return "CẦN KIỂM TRA"

    return record.get(
        "status",
        "CẦN KIỂM TRA"
    )


# ------------------------------------------------------------
# 8.16 — BUILD DOCUMENT SUMMARY
# ------------------------------------------------------------

def build_document_summary(
    documents
):
    """
    Tạo summary theo từng loại chứng từ.
    """

    summary = {}

    for document in documents:

        normalized_document = (
            normalize_document_record(
                document
            )
        )

        if not normalized_document:
            continue

        document_type = normalized_document[
            "document_type"
        ]

        fields = get_document_fields(
            normalized_document
        )

        summary[document_type] = {
            "document_type": document_type,
            "file_name": normalized_document[
                "file_name"
            ],
            "field_count": len(fields),
            "fields": fields,
        }

    return summary


# ------------------------------------------------------------
# 8.17 — FINAL MULTI-DOCUMENT PIPELINE
# ------------------------------------------------------------

def process_all_documents(
    documents
):
    """
    Pipeline tổng:

        DOCUMENTS
             ↓
        NORMALIZE RECORDS
             ↓
        COLLECT SOURCES
             ↓
        CONSOLIDATE
             ↓
        CUSTOMS DATA
             ↓
        CROSS-CHECK READY
    """

    normalized_documents = []

    for document in documents:

        normalized_document = (
            normalize_document_record(
                document
            )
        )

        if normalized_document:
            normalized_documents.append(
                normalized_document
            )

    consolidated = build_consolidated_data(
        normalized_documents
    )

    customs_data = build_customs_data(
        normalized_documents
    )

    summary = build_document_summary(
        normalized_documents
    )

    return {
        "documents": normalized_documents,
        "summary": summary,
        "consolidated": consolidated,
        "customs_data": customs_data,
    }


# ------------------------------------------------------------
# 8.18 — SAFE VALUE FOR UI
# ------------------------------------------------------------

def display_extracted_value(value):
    """
    Giá trị dùng cho UI.

    Không có dữ liệu -> Không tìm thấy
    """

    if value is None:
        return "Không tìm thấy"

    value = normalize_spaces(value)

    if not value or value == EMPTY:
        return "Không tìm thấy"

    return value


# ------------------------------------------------------------
# 8.19 — SAFE STATUS FOR UI
# ------------------------------------------------------------

def display_check_status(status):
    """
    Chuẩn hóa trạng thái hiển thị.
    """

    valid_statuses = {
        "KHỚP",
        "KHÔNG KHỚP",
        "CẦN KIỂM TRA",
        "KHÔNG ÁP DỤNG",
    }

    status = normalize_spaces(
        status
    ).upper()

    if status in valid_statuses:
        return status

    return "CẦN KIỂM TRA"


# ============================================================
# KẾT THÚC PHẦN 8/9
# ============================================================

# ============================================================
# PHẦN 9/9 — CROSS-CHECK + LEARNING + SAVE DATABASE
# ============================================================


# ------------------------------------------------------------
# 9.1 — CROSS-CHECK STATUS
# ------------------------------------------------------------

STATUS_MATCH = "KHỚP"
STATUS_MISMATCH = "KHÔNG KHỚP"
STATUS_REVIEW = "CẦN KIỂM TRA"
STATUS_NOT_APPLICABLE = "KHÔNG ÁP DỤNG"


# ------------------------------------------------------------
# 9.2 — CROSS-CHECK FIELD SPECIFICATIONS
# ------------------------------------------------------------

CROSS_CHECK_SPECS = {

    "CONTRACT_NUMBER": {
        "documents": [
            "PURCHASE CONTRACT",
            "COMMERCIAL INVOICE",
            "PACKING LIST",
        ],
    },

    "INVOICE_NUMBER": {
        "documents": [
            "COMMERCIAL INVOICE",
        ],
    },

    "PACKING_LIST_NUMBER": {
        "documents": [
            "PACKING LIST",
        ],
    },

    "PO_NUMBER": {
        "documents": [
            "PURCHASE CONTRACT",
            "COMMERCIAL INVOICE",
            "PACKING LIST",
        ],
    },

    "EXPORTER": {
        "documents": [
            "PURCHASE CONTRACT",
            "COMMERCIAL INVOICE",
            "PACKING LIST",
            "BILL OF LADING",
            "CERTIFICATE OF ORIGIN",
        ],
    },

    "IMPORTER": {
        "documents": [
            "PURCHASE CONTRACT",
            "COMMERCIAL INVOICE",
            "PACKING LIST",
            "BILL OF LADING",
            "CERTIFICATE OF ORIGIN",
        ],
    },

    "CONSIGNEE": {
        "documents": [
            "PURCHASE CONTRACT",
            "COMMERCIAL INVOICE",
            "PACKING LIST",
            "BILL OF LADING",
        ],
    },

    "DESCRIPTION": {
        "documents": [
            "PURCHASE CONTRACT",
            "COMMERCIAL INVOICE",
            "PACKING LIST",
            "BILL OF LADING",
            "CERTIFICATE OF ORIGIN",
        ],
    },

    "HS_CODE": {
        "documents": [
            "COMMERCIAL INVOICE",
            "PACKING LIST",
            "CERTIFICATE OF ORIGIN",
        ],
    },

    "QUANTITY": {
        "documents": [
            "PURCHASE CONTRACT",
            "COMMERCIAL INVOICE",
            "PACKING LIST",
            "CERTIFICATE OF ORIGIN",
        ],
    },

    "PACKAGE_COUNT": {
        "documents": [
            "COMMERCIAL INVOICE",
            "PACKING LIST",
            "BILL OF LADING",
            "CERTIFICATE OF ORIGIN",
        ],
    },

    "GROSS_WEIGHT": {
        "documents": [
            "COMMERCIAL INVOICE",
            "PACKING LIST",
            "BILL OF LADING",
            "CERTIFICATE OF ORIGIN",
        ],
    },

    "NET_WEIGHT": {
        "documents": [
            "COMMERCIAL INVOICE",
            "PACKING LIST",
            "CERTIFICATE OF ORIGIN",
        ],
    },

    "MEASUREMENT": {
        "documents": [
            "COMMERCIAL INVOICE",
            "PACKING LIST",
            "BILL OF LADING",
        ],
    },

    "UNIT_PRICE": {
        "documents": [
            "PURCHASE CONTRACT",
            "COMMERCIAL INVOICE",
        ],
    },

    "TOTAL_AMOUNT": {
        "documents": [
            "PURCHASE CONTRACT",
            "COMMERCIAL INVOICE",
        ],
    },

    "CURRENCY": {
        "documents": [
            "PURCHASE CONTRACT",
            "COMMERCIAL INVOICE",
        ],
    },

    "INCOTERMS": {
        "documents": [
            "PURCHASE CONTRACT",
            "COMMERCIAL INVOICE",
        ],
    },

    "PAYMENT_TERMS": {
        "documents": [
            "PURCHASE CONTRACT",
            "COMMERCIAL INVOICE",
        ],
    },

    "CONTAINER_NUMBER": {
        "documents": [
            "PACKING LIST",
            "BILL OF LADING",
            "BOOKING",
            "ARRIVAL NOTICE",
        ],
    },

    "SEAL_NUMBER": {
        "documents": [
            "PACKING LIST",
            "BILL OF LADING",
            "BOOKING",
            "ARRIVAL NOTICE",
        ],
    },

    "BL_NUMBER": {
        "documents": [
            "BILL OF LADING",
            "ARRIVAL NOTICE",
            "COMMERCIAL INVOICE",
            "PACKING LIST",
        ],
    },

    "BOOKING_NUMBER": {
        "documents": [
            "BILL OF LADING",
            "BOOKING",
            "ARRIVAL NOTICE",
        ],
    },

    "VESSEL": {
        "documents": [
            "BILL OF LADING",
            "BOOKING",
            "ARRIVAL NOTICE",
        ],
    },

    "VOYAGE": {
        "documents": [
            "BILL OF LADING",
            "BOOKING",
            "ARRIVAL NOTICE",
        ],
    },

    "PORT_OF_LOADING": {
        "documents": [
            "PURCHASE CONTRACT",
            "COMMERCIAL INVOICE",
            "BILL OF LADING",
            "BOOKING",
            "CERTIFICATE OF ORIGIN",
            "ARRIVAL NOTICE",
        ],
    },

    "PORT_OF_DISCHARGE": {
        "documents": [
            "BILL OF LADING",
            "BOOKING",
            "CERTIFICATE OF ORIGIN",
            "ARRIVAL NOTICE",
        ],
    },

    "PLACE_OF_RECEIPT": {
        "documents": [
            "BILL OF LADING",
            "BOOKING",
        ],
    },

    "FINAL_DESTINATION": {
        "documents": [
            "PURCHASE CONTRACT",
            "BILL OF LADING",
            "BOOKING",
            "ARRIVAL NOTICE",
        ],
    },

    "COUNTRY_OF_ORIGIN": {
        "documents": [
            "COMMERCIAL INVOICE",
            "CERTIFICATE OF ORIGIN",
        ],
    },

    "ETA": {
        "documents": [
            "BILL OF LADING",
            "BOOKING",
            "ARRIVAL NOTICE",
        ],
    },

    "ETD": {
        "documents": [
            "BILL OF LADING",
            "BOOKING",
            "ARRIVAL NOTICE",
        ],
    },
}


# ------------------------------------------------------------
# 9.3 — NORMALIZE FOR CROSS-CHECK
# ------------------------------------------------------------

def normalize_crosscheck_value(
    field_name,
    value
):
    """
    Chuẩn hóa riêng cho cross-check.

    Mục tiêu:
        loại bỏ khác biệt hình thức,
        nhưng không thay đổi ý nghĩa nghiệp vụ.
    """

    if value is None:
        return EMPTY

    field_name = str(
        field_name or EMPTY
    ).strip().upper()

    value = normalize_spaces(value)

    if not value:
        return EMPTY

    # --------------------------------------------------------
    # COMPANY
    # --------------------------------------------------------

    if field_name in {
        "EXPORTER",
        "IMPORTER",
        "CONSIGNEE",
        "NOTIFY_PARTY",
    }:

        value = normalize_company_value(
            value
        )

        # Chỉ bỏ legal suffix ở cuối để đối chiếu
        # "ABC CO., LTD" và "ABC"
        # Không đổi phần tên chính.

        changed = True

        while changed:

            changed = False

            for suffix in LEGAL_SUFFIXES:

                pattern = (
                    r"\s+"
                    + re.escape(
                        suffix.upper()
                    )
                    + r"$"
                )

                new_value = re.sub(
                    pattern,
                    "",
                    value,
                    flags=re.I,
                )

                if new_value != value:

                    value = normalize_spaces(
                        new_value
                    )

                    changed = True

        return value

    # --------------------------------------------------------
    # PORT
    # --------------------------------------------------------

    if field_name in {
        "PORT_OF_LOADING",
        "PORT_OF_DISCHARGE",
        "PLACE_OF_RECEIPT",
        "FINAL_DESTINATION",
    }:

        return normalize_port_value(
            value
        )

    # --------------------------------------------------------
    # DESCRIPTION
    # --------------------------------------------------------

    if field_name == "DESCRIPTION":

        value = normalize_upper(
            value
        )

        value = re.sub(
            r"[,\.;:]+",
            " ",
            value
        )

        return normalize_spaces(
            value
        )

    # --------------------------------------------------------
    # DATE
    # --------------------------------------------------------

    if field_name.endswith(
        "_DATE"
    ):

        return normalize_date_value(
            value
        )

    # --------------------------------------------------------
    # CURRENCY
    # --------------------------------------------------------

    if field_name == "CURRENCY":

        return normalize_currency_value(
            value
        )

    # --------------------------------------------------------
    # INCOTERMS
    # --------------------------------------------------------

    if field_name == "INCOTERMS":

        return normalize_incoterm_value(
            value
        )

    # --------------------------------------------------------
    # CONTAINER
    # --------------------------------------------------------

    if field_name == "CONTAINER_NUMBER":

        return normalize_container_value(
            value
        )

    # --------------------------------------------------------
    # SEAL
    # --------------------------------------------------------

    if field_name == "SEAL_NUMBER":

        return normalize_seal_value(
            value
        )

    # --------------------------------------------------------
    # NUMERIC
    # --------------------------------------------------------

    if field_name in {
        "QUANTITY",
        "PACKAGE_COUNT",
        "UNIT_PRICE",
        "TOTAL_AMOUNT",
        "GROSS_WEIGHT",
        "NET_WEIGHT",
        "MEASUREMENT",
    }:

        return normalize_numeric_with_unit(
            value
        )

    # --------------------------------------------------------
    # IDENTIFIERS
    # --------------------------------------------------------

    if field_name in {
        "CONTRACT_NUMBER",
        "INVOICE_NUMBER",
        "PACKING_LIST_NUMBER",
        "PO_NUMBER",
        "BL_NUMBER",
        "BOOKING_NUMBER",
        "CO_NUMBER",
    }:

        return normalize_identifier_value(
            value
        )

    # --------------------------------------------------------
    # VESSEL
    # --------------------------------------------------------

    if field_name == "VESSEL":

        return normalize_vessel_value(
            value
        )

    # --------------------------------------------------------
    # VOYAGE
    # --------------------------------------------------------

    if field_name == "VOYAGE":

        return normalize_voyage_value(
            value
        )

    return normalize_punctuation(
        value
    ).upper()


# ------------------------------------------------------------
# 9.4 — GET DOCUMENT SOURCES FOR CROSS-CHECK
# ------------------------------------------------------------

def get_crosscheck_sources(
    documents,
    field_name,
    allowed_documents=None
):
    """
    Lấy actual extracted values của field
    từ các chứng từ được phép đối chiếu.
    """

    field_name = str(
        field_name or EMPTY
    ).strip().upper()

    if allowed_documents is None:

        spec = CROSS_CHECK_SPECS.get(
            field_name,
            {}
        )

        allowed_documents = spec.get(
            "documents",
            []
        )

    allowed_documents = {
        str(doc).strip().upper()
        for doc in allowed_documents
    }

    sources = []

    for document in documents:

        normalized_document = (
            normalize_document_record(
                document
            )
        )

        if not normalized_document:
            continue

        document_type = normalized_document[
            "document_type"
        ]

        if (
            allowed_documents
            and document_type not in allowed_documents
        ):
            continue

        candidate = get_document_candidate(
            normalized_document,
            field_name
        )

        if not candidate:
            continue

        raw_value = get_candidate_raw_value(
            candidate
        )

        if not raw_value:
            continue

        normalized_value = (
            normalize_crosscheck_value(
                field_name,
                raw_value
            )
        )

        if not normalized_value:
            continue

        sources.append({
            "field_name": field_name,
            "document_type": document_type,
            "file_name": normalized_document[
                "file_name"
            ],
            "raw_value": raw_value,
            "normalized_value": normalized_value,
            "confidence": get_candidate_confidence(
                candidate
            ),
        })

    return sources


# ------------------------------------------------------------
# 9.5 — CROSS-CHECK ONE FIELD
# ------------------------------------------------------------

def cross_check_field(
    documents,
    field_name
):
    """
    Đối chiếu một standard field.

    Quy tắc:

        0 source
            -> CẦN KIỂM TRA

        1 source
            -> CẦN KIỂM TRA

        >=2 source + cùng giá trị
            -> KHỚP

        >=2 source + khác giá trị
            -> KHÔNG KHỚP
    """

    field_name = str(
        field_name or EMPTY
    ).strip().upper()

    spec = CROSS_CHECK_SPECS.get(
        field_name
    )

    if not spec:

        return {
            "field_name": field_name,
            "status": STATUS_NOT_APPLICABLE,
            "reason": "Chưa có quy tắc đối chiếu cho field này",
            "sources": [],
            "values": [],
        }

    allowed_documents = spec.get(
        "documents",
        []
    )

    # Các chứng từ thực tế có trong bộ hồ sơ
    existing_document_types = {
        str(
            document.get(
                "document_type",
                ""
            )
        ).strip().upper()
        for document in documents
        if isinstance(document, dict)
    }

    relevant_documents = (
        existing_document_types
        & {
            str(doc).strip().upper()
            for doc in allowed_documents
        }
    )

    # Không có chứng từ liên quan
    if not relevant_documents:

        return {
            "field_name": field_name,
            "status": STATUS_NOT_APPLICABLE,
            "reason": "Bộ hồ sơ không có chứng từ áp dụng",
            "sources": [],
            "values": [],
        }

    sources = get_crosscheck_sources(
        documents,
        field_name,
        allowed_documents,
    )

    # Không tìm thấy field
    if not sources:

        return {
            "field_name": field_name,
            "status": STATUS_REVIEW,
            "reason": "Không tìm thấy dữ liệu để đối chiếu",
            "sources": [],
            "values": [],
        }

    # Chỉ có một nguồn
    if len(sources) == 1:

        return {
            "field_name": field_name,
            "status": STATUS_REVIEW,
            "reason": "Chỉ có một nguồn dữ liệu",
            "sources": sources,
            "values": [
                sources[0][
                    "normalized_value"
                ]
            ],
        }

    unique_values = []

    for source in sources:

        value = source.get(
            "normalized_value",
            EMPTY
        )

        if value and value not in unique_values:
            unique_values.append(
                value
            )

    # Tất cả giống nhau
    if len(unique_values) == 1:

        return {
            "field_name": field_name,
            "status": STATUS_MATCH,
            "reason": "Các chứng từ có cùng giá trị",
            "sources": sources,
            "values": unique_values,
        }

    # Có khác nhau
    return {
        "field_name": field_name,
        "status": STATUS_MISMATCH,
        "reason": "Các chứng từ có giá trị khác nhau",
        "sources": sources,
        "values": unique_values,
    }


# ------------------------------------------------------------
# 9.6 — CROSS-CHECK ALL FIELDS
# ------------------------------------------------------------

def cross_check_all_documents(
    documents
):
    """
    Chạy cross-check toàn bộ field có rule.
    """

    results = {}

    for field_name in CROSS_CHECK_SPECS.keys():

        results[field_name] = (
            cross_check_field(
                documents,
                field_name
            )
        )

    return results


# ------------------------------------------------------------
# 9.7 — CROSS-CHECK SUMMARY
# ------------------------------------------------------------

def summarize_crosscheck(
    crosscheck_results
):
    """
    Thống kê số lượng:

        KHỚP
        KHÔNG KHỚP
        CẦN KIỂM TRA
        KHÔNG ÁP DỤNG
    """

    summary = {
        STATUS_MATCH: 0,
        STATUS_MISMATCH: 0,
        STATUS_REVIEW: 0,
        STATUS_NOT_APPLICABLE: 0,
    }

    if not crosscheck_results:
        return summary

    for result in crosscheck_results.values():

        status = result.get(
            "status",
            STATUS_REVIEW
        )

        if status not in summary:
            status = STATUS_REVIEW

        summary[status] += 1

    return summary


# ------------------------------------------------------------
# 9.8 — BUILD CROSS-CHECK TABLE
# ------------------------------------------------------------

def build_crosscheck_rows(
    crosscheck_results
):
    """
    Chuyển kết quả cross-check thành list row
    để Streamlit hiển thị.
    """

    rows = []

    for field_name, result in (
        crosscheck_results.items()
    ):

        sources = result.get(
            "sources",
            []
        )

        source_values = []

        for source in sources:

            source_values.append({
                "document_type": source.get(
                    "document_type",
                    EMPTY
                ),
                "file_name": source.get(
                    "file_name",
                    EMPTY
                ),
                "value": source.get(
                    "raw_value",
                    EMPTY
                ),
                "normalized_value": source.get(
                    "normalized_value",
                    EMPTY
                ),
                "confidence": source.get(
                    "confidence",
                    0.0
                ),
            })

        rows.append({
            "field_name": field_name,
            "display_name": get_field_display_name(
                field_name
            ),
            "status": result.get(
                "status",
                STATUS_REVIEW
            ),
            "reason": result.get(
                "reason",
                EMPTY
            ),
            "values": result.get(
                "values",
                []
            ),
            "sources": source_values,
        })

    return rows


# ------------------------------------------------------------
# 9.9 — CONFIRMED CORRECTION
# ------------------------------------------------------------

def build_confirmed_correction(
    field_name,
    old_value,
    new_value,
    document_type=None,
    raw_label=None
):
    """
    Tạo correction record.

    Correction chỉ được tạo khi USER xác nhận.
    """

    field_name = str(
        field_name or EMPTY
    ).strip().upper()

    old_value = normalize_spaces(
        old_value
    )

    new_value = normalize_spaces(
        new_value
    )

    if not field_name:
        return None

    if not new_value:
        return None

    normalized_new_value = (
        normalize_field_value(
            field_name,
            new_value
        )
    )

    return {
        "field_name": field_name,
        "document_type": (
            str(
                document_type
                or EMPTY
            ).strip().upper()
        ),
        "raw_label": normalize_spaces(
            raw_label
        ),
        "old_value": old_value,
        "new_value": new_value,
        "normalized_value": normalized_new_value,
        "confirmed": True,
    }


# ------------------------------------------------------------
# 9.10 — SAVE CONFIRMED CORRECTION
# ------------------------------------------------------------

def save_confirmed_correction(
    correction
):
    """
    Lưu correction đã được USER xác nhận.

    Không gọi hàm này tự động sau extraction.
    """

    if not correction:
        return False

    try:

        payload = {
            "field_name": correction.get(
                "field_name",
                EMPTY
            ),
            "document_type": correction.get(
                "document_type",
                EMPTY
            ),
            "raw_label": correction.get(
                "raw_label",
                EMPTY
            ),
            "old_value": correction.get(
                "old_value",
                EMPTY
            ),
            "new_value": correction.get(
                "new_value",
                EMPTY
            ),
            "normalized_value": correction.get(
                "normalized_value",
                EMPTY
            ),
            "confirmed": True,
        }

        result = supabase.table(
            "confirmed_corrections"
        ).insert(
            payload
        ).execute()

        return bool(
            result.data
        )

    except Exception:
        return False


# ------------------------------------------------------------
# 9.11 — LEARNING CONFIG
# ------------------------------------------------------------

def get_learning_config():
    """
    Đọc cấu hình learning từ knowledge base.
    """

    config = (
        LEARNING_RULES_KB.get(
            "LEARNING_CONFIG",
            {}
        )
        if isinstance(
            LEARNING_RULES_KB,
            dict
        )
        else {}
    )

    return config


# ------------------------------------------------------------
# 9.12 — CHECK WHETHER LEARNING IS ALLOWED
# ------------------------------------------------------------

def learning_allowed():
    """
    Chỉ cho phép learning nếu cấu hình yêu cầu
    learning từ confirmed data.
    """

    config = get_learning_config()

    return bool(
        config.get(
            "learn_only_from_confirmed_data",
            True
        )
    )


# ------------------------------------------------------------
# 9.13 — PROMOTE CONFIRMED CORRECTION
# ------------------------------------------------------------

def promote_confirmed_correction(
    correction
):
    """
    Promote correction thành alias học được.

    CHỈ chạy khi correction đã confirmed.

    Không promote:
        - extraction tự động
        - mismatch chưa xác nhận
        - candidate confidence thấp
        - dữ liệu chưa được user xác nhận
    """

    if not correction:
        return False

    if not learning_allowed():
        return False

    if not correction.get(
        "confirmed",
        False
    ):
        return False

    field_name = str(
        correction.get(
            "field_name",
            EMPTY
        )
    ).strip().upper()

    raw_label = normalize_spaces(
        correction.get(
            "raw_label",
            EMPTY
        )
    )

    document_type = str(
        correction.get(
            "document_type",
            EMPTY
        )
    ).strip().upper()

    if not field_name or not raw_label:
        return False

    # --------------------------------------------------------
    # Kiểm tra alias hiện tại
    # --------------------------------------------------------

    try:

        query = (
            supabase
            .table("field_aliases")
            .select("*")
            .eq(
                "raw_label",
                raw_label
            )
            .eq(
                "standard_field",
                field_name
            )
        )

        if document_type:

            query = query.eq(
                "document_type",
                document_type
            )

        existing_result = (
            query
            .limit(1)
            .execute()
        )

        existing_rows = (
            existing_result.data
            or []
        )

    except Exception:
        existing_rows = []

    # --------------------------------------------------------
    # ALIAS ĐÃ TỒN TẠI
    # --------------------------------------------------------

    if existing_rows:

        row = existing_rows[0]

        current_times = row.get(
            "times_confirmed",
            0
        )

        try:
            current_times = int(
                current_times
            )
        except Exception:
            current_times = 0

        current_confidence = row.get(
            "confidence",
            0.8
        )

        try:
            current_confidence = float(
                current_confidence
            )
        except Exception:
            current_confidence = 0.8

        config = get_learning_config()

        increment = float(
            config.get(
                "confidence_increment_on_confirmation",
                0.05
            )
        )

        maximum = float(
            config.get(
                "maximum_confidence",
                1.0
            )
        )

        new_times = (
            current_times + 1
        )

        new_confidence = min(
            current_confidence + increment,
            maximum
        )

        try:

            supabase.table(
                "field_aliases"
            ).update({
                "confirmed": True,
                "times_confirmed": new_times,
                "confidence": new_confidence,
            }).eq(
                "id",
                row.get("id")
            ).execute()

            return True

        except Exception:

            return False

    # --------------------------------------------------------
    # ALIAS MỚI
    # --------------------------------------------------------

    config = get_learning_config()

    default_confidence = float(
        config.get(
            "default_confidence",
            0.8
        )
    )

    minimum_confirmations = int(
        config.get(
            "minimum_confirmations_for_promotion",
            2
        )
    )

    # Một correction chưa đủ để promote mạnh.
    # Chỉ lưu confirmed record.
    payload = {
        "raw_label": raw_label,
        "standard_field": field_name,
        "document_type": (
            document_type
            if document_type
            else None
        ),
        "context": None,
        "confidence": default_confidence,
        "confirmed": True,
        "times_confirmed": 1,
    }

    # --------------------------------------------------------
    # KHÔNG tự promote nếu chưa đủ confirmation
    # --------------------------------------------------------

    if minimum_confirmations > 1:

        try:

            result = (
                supabase
                .table("field_aliases")
                .insert(payload)
                .execute()
            )

            return bool(
                result.data
            )

        except Exception:

            return False

    # Nếu cấu hình yêu cầu 1 confirmation
    try:

        result = (
            supabase
            .table("field_aliases")
            .insert(payload)
            .execute()
        )

        return bool(
            result.data
        )

    except Exception:

        return False


# ------------------------------------------------------------
# 9.14 — APPLY CONFIRMED CORRECTION TO CURRENT RESULT
# ------------------------------------------------------------

def apply_confirmed_correction_to_result(
    extraction_result,
    correction
):
    """
    Áp dụng correction vào kết quả hiện tại trong memory.

    Đây KHÔNG phải auto-correction.
    Hàm này chỉ được gọi sau khi user xác nhận.
    """

    if not extraction_result:
        return extraction_result

    if not correction:
        return extraction_result

    field_name = str(
        correction.get(
            "field_name",
            EMPTY
        )
    ).strip().upper()

    new_value = correction.get(
        "new_value",
        EMPTY
    )

    if not field_name or not new_value:
        return extraction_result

    normalized_value = (
        normalize_field_value(
            field_name,
            new_value
        )
    )

    candidate = {
        "field": field_name,
        "raw_value": new_value,
        "normalized_value": normalized_value,
        "confidence": 1.0,
        "source": "confirmed_correction",
        "confirmed": True,
    }

    extraction_result.setdefault(
        "fields",
        {}
    )

    extraction_result["fields"][
        field_name
    ] = candidate

    candidates = extraction_result.setdefault(
        "candidates",
        []
    )

    candidates.append(
        candidate
    )

    return extraction_result


# ------------------------------------------------------------
# 9.15 — SAVE DOCUMENT SAMPLE
# ------------------------------------------------------------

def save_document_sample(
    document_type,
    file_name,
    raw_text
):
    """
    Lưu document sample thông qua SECURITY DEFINER RPC.

    Tránh INSERT trực tiếp vào document_samples
    khi RLS đang bật.
    """

    try:

        result = supabase.rpc(
            "insert_document_sample",
            {
                "p_document_type": (
                    document_type
                    or EMPTY
                ),
                "p_file_name": (
                    file_name
                    or EMPTY
                ),
                "p_raw_text": (
                    raw_text
                    or EMPTY
                ),
            },
        ).execute()

        if result.data is None:
            return None

        # RPC trả về bigint
        try:
            return int(
                result.data
            )
        except Exception:
            return result.data

    except Exception as e:

        return None


# ------------------------------------------------------------
# 9.16 — SAVE EXTRACTED FIELDS
# ------------------------------------------------------------

def save_extracted_fields(
    sample_id,
    extraction_result
):
    """
    Lưu extracted fields thông qua RPC.

    Không lưu candidate rỗng.
    """

    if not sample_id:
        return 0

    if not extraction_result:
        return 0

    fields = extraction_result.get(
        "fields",
        {}
    )

    if not isinstance(fields, dict):
        return 0

    saved_count = 0

    for field_name, candidate in fields.items():

        if not isinstance(candidate, dict):
            candidate = {
                "raw_value": str(
                    candidate
                ),
                "normalized_value": str(
                    candidate
                ),
            }

        raw_value = (
            candidate.get(
                "raw_value"
            )
            or candidate.get(
                "value"
            )
            or EMPTY
        )

        normalized_value = (
            candidate.get(
                "normalized_value"
            )
            or normalize_field_value(
                field_name,
                raw_value
            )
        )

        if not raw_value:
            continue

        try:

            result = supabase.rpc(
                "insert_extracted_fields",
                {
                    "p_sample_id": int(
                        sample_id
                    ),
                    "p_field_name": str(
                        field_name
                    ).strip().upper(),
                    "p_raw_value": str(
                        raw_value
                    ),
                    "p_normalized_value": str(
                        normalized_value
                    ),
                },
            ).execute()

            if result.data is not None:
                saved_count += 1

        except Exception:
            continue

    return saved_count


# ------------------------------------------------------------
# 9.17 — SAVE COMPLETE DOCUMENT
# ------------------------------------------------------------

def save_processed_document(
    document_type,
    file_name,
    raw_text,
    extraction_result
):
    """
    Lưu:
        document_samples
        extracted_fields

    """

    sample_id = save_document_sample(
        document_type=document_type,
        file_name=file_name,
        raw_text=raw_text,
    )

    if not sample_id:
        return {
            "success": False,
            "sample_id": None,
            "saved_fields": 0,
        }

    saved_fields = save_extracted_fields(
        sample_id=sample_id,
        extraction_result=extraction_result,
    )

    return {
        "success": True,
        "sample_id": sample_id,
        "saved_fields": saved_fields,
    }


# ------------------------------------------------------------
# 9.18 — COMPLETE CUSTOMS CHECK PIPELINE
# ------------------------------------------------------------

def run_customs_document_pipeline(
    documents
):
    """
    Pipeline hoàn chỉnh:

        1. Multi-document consolidation
        2. Customs data
        3. Cross-check
        4. Summary
    """

    processed = process_all_documents(
        documents
    )

    crosscheck_results = (
        cross_check_all_documents(
            documents
        )
    )

    crosscheck_summary = (
        summarize_crosscheck(
            crosscheck_results
        )
    )

    crosscheck_rows = (
        build_crosscheck_rows(
            crosscheck_results
        )
    )

    return {
        "documents": processed.get(
            "documents",
            []
        ),

        "summary": processed.get(
            "summary",
            {}
        ),

        "consolidated": processed.get(
            "consolidated",
            {}
        ),

        "customs_data": processed.get(
            "customs_data",
            {}
        ),

        "crosscheck": {
            "results": crosscheck_results,
            "rows": crosscheck_rows,
            "summary": crosscheck_summary,
        },
    }


# ------------------------------------------------------------
# 9.19 — GET MISMATCH FIELDS
# ------------------------------------------------------------

def get_mismatch_fields(
    crosscheck_results
):
    """
    Lấy các field đang KHÔNG KHỚP.
    """

    mismatch = []

    if not crosscheck_results:
        return mismatch

    for field_name, result in (
        crosscheck_results.items()
    ):

        if result.get(
            "status"
        ) == STATUS_MISMATCH:

            mismatch.append(
                field_name
            )

    return mismatch


# ------------------------------------------------------------
# 9.20 — GET REVIEW FIELDS
# ------------------------------------------------------------

def get_review_fields(
    crosscheck_results
):
    """
    Lấy các field CẦN KIỂM TRA.
    """

    review = []

    if not crosscheck_results:
        return review

    for field_name, result in (
        crosscheck_results.items()
    ):

        if result.get(
            "status"
        ) == STATUS_REVIEW:

            review.append(
                field_name
            )

    return review


# ------------------------------------------------------------
# 9.21 — BUILD CHECK STATUS TEXT
# ------------------------------------------------------------

def build_check_status_text(
    crosscheck_result
):
    """
    Tạo text ngắn để UI hiển thị.
    """

    if not crosscheck_result:
        return STATUS_REVIEW

    status = crosscheck_result.get(
        "status",
        STATUS_REVIEW
    )

    reason = crosscheck_result.get(
        "reason",
        EMPTY
    )

    if reason:
        return f"{status} — {reason}"

    return status


# ------------------------------------------------------------
# 9.22 — LEARNING SAFETY CHECK
# ------------------------------------------------------------

def can_save_learning_event(
    correction
):
    """
    Safety gate cuối cùng trước khi ghi learning.

    Learning chỉ hợp lệ khi:

        confirmed == True
        field_name tồn tại
        raw_label tồn tại
        new_value tồn tại
    """

    if not correction:
        return False

    if not correction.get(
        "confirmed",
        False
    ):
        return False

    if not correction.get(
        "field_name"
    ):
        return False

    if not correction.get(
        "raw_label"
    ):
        return False

    if not correction.get(
        "new_value"
    ):
        return False

    return True


# ------------------------------------------------------------
# 9.23 — HANDLE USER CONFIRMED CORRECTION
# ------------------------------------------------------------

def handle_confirmed_correction(
    extraction_result,
    field_name,
    old_value,
    new_value,
    document_type=None,
    raw_label=None
):
    """
    Luồng learning chính.

    Chỉ gọi hàm này sau khi user bấm xác nhận.

        USER CONFIRMS
             ↓
        BUILD CORRECTION
             ↓
        SAVE CORRECTION
             ↓
        APPLY CURRENT RESULT
             ↓
        PROMOTE LEARNING
    """

    correction = build_confirmed_correction(
        field_name=field_name,
        old_value=old_value,
        new_value=new_value,
        document_type=document_type,
        raw_label=raw_label,
    )

    if not can_save_learning_event(
        correction
    ):
        return {
            "success": False,
            "correction": None,
            "saved": False,
            "promoted": False,
        }

    saved = save_confirmed_correction(
        correction
    )

    if saved:

        extraction_result = (
            apply_confirmed_correction_to_result(
                extraction_result,
                correction
            )
        )

        promoted = (
            promote_confirmed_correction(
                correction
            )
        )

    else:

        promoted = False

    return {
        "success": saved,
        "correction": correction,
        "saved": saved,
        "promoted": promoted,
        "extraction_result": extraction_result,
    }


# ============================================================
# 9.24 — FINAL HELPER
# ============================================================

def build_final_analysis(
    documents
):
    """
    Hàm duy nhất có thể gọi từ UI để lấy toàn bộ kết quả.

    Output:

        {
            documents,
            consolidated,
            customs_data,
            crosscheck
        }
    """

    if not documents:
        return {
            "documents": [],
            "summary": {},
            "consolidated": {},
            "customs_data": {},
            "crosscheck": {
                "results": {},
                "rows": [],
                "summary": {
                    STATUS_MATCH: 0,
                    STATUS_MISMATCH: 0,
                    STATUS_REVIEW: 0,
                    STATUS_NOT_APPLICABLE: 0,
                },
            },
        }

    return run_customs_document_pipeline(
        documents
    )


# ============================================================
# KẾT THÚC PHẦN 9/9
# ============================================================
