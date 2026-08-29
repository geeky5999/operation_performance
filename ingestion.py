from __future__ import annotations

from io import BytesIO
import pandas as pd
import pdfplumber
from PIL import Image


def read_table(uploaded_file) -> pd.DataFrame:
    name = uploaded_file.name.lower()
    if name.endswith(".csv"):
        return pd.read_csv(uploaded_file)
    if name.endswith((".xlsx", ".xls")):
        return pd.read_excel(uploaded_file)
    raise ValueError("Use a CSV or XLSX file for numerical analysis.")


def extract_report_text(uploaded_file) -> str:
    name = uploaded_file.name.lower()
    raw = uploaded_file.getvalue()
    if name.endswith(".pdf"):
        with pdfplumber.open(BytesIO(raw)) as pdf:
            return "\n".join((page.extract_text() or "") for page in pdf.pages)
    if name.endswith((".png", ".jpg", ".jpeg")):
        try:
            import pytesseract
            return pytesseract.image_to_string(Image.open(BytesIO(raw)))
        except Exception as exc:
            return f"OCR unavailable: {exc}"
    return ""

