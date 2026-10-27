import csv
import html
import logging
import os
import re
import xml.etree.ElementTree as ET
import zipfile
from typing import List

from docx import Document
from openpyxl import Workbook, load_workbook
from PIL import Image
from pypdf import PdfReader
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

try:
    import pythoncom
    import win32com.client
    HAS_WIN32COM = True
except ImportError:
    HAS_WIN32COM = False

logger = logging.getLogger(__name__)

# Kirill va Lotin harflari to'g'ri chiqishi uchun shriftlarni ro'yxatdan o'tkazamiz (Windows va Linux/Render uchun)
FONT_NAME = "Helvetica"
possible_fonts = [
    # Windows shriftlari
    r"C:\Windows\Fonts\arial.ttf",
    r"C:\Windows\Fonts\calibri.ttf",
    # Linux shriftlari (Ubuntu / Debian / Render)
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/TTF/DejaVuSans.ttf",
]
for font_path in possible_fonts:
    if os.path.exists(font_path):
        try:
            pdfmetrics.registerFont(TTFont("CustomFont", font_path))
            FONT_NAME = "CustomFont"
            break
        except Exception as e:
            logger.warning(f"Shriftni yuklashda xatolik ({font_path}): {e}")


def extract_text_from_word_file(file_path: str) -> List[str]:
    """
    Istalgan Word (.docx, .doc, XML, RTF) faylidan matnlarni ajratib oladi.
    Standart bo'lmagan yoki eski formatdagi fayllarni ham xatosiz o'qiydi.
    """
    paragraphs = []

    # 1-usul: python-docx orqali o'qish
    try:
        doc = Document(file_path)
        for p in doc.paragraphs:
            text = p.text.strip()
            if text:
                paragraphs.append(text)
        if paragraphs:
            return paragraphs
    except Exception as e:
        logger.warning(f"python-docx orqali o'qishda xatolik ({e}), to'g'ridan-to'g'ri XML tekshirilmoqda...")

    # 2-usul: Agar fayl ZIP arxiv bo'lsa (DOCX aslida ZIP arxiv), word/document.xml ni to'g'ridan-to'g'ri o'qiymiz
    if zipfile.is_zipfile(file_path):
        try:
            with zipfile.ZipFile(file_path, "r") as z:
                # Arxiv ichidagi barcha xml fayllarni qidiramiz
                xml_targets = [name for name in z.namelist() if name.endswith(".xml") and ("document" in name or "content" in name)]
                if not xml_targets:
                    xml_targets = [name for name in z.namelist() if name.endswith(".xml")]

                for target in xml_targets:
                    try:
                        content = z.read(target)
                        root = ET.fromstring(content)
                        # Barcha matn elementlarini topish
                        for elem in root.iter():
                            if elem.tag.endswith("p"):  # Paragraf
                                p_text = "".join(node.text or "" for node in elem.iter() if node.tag.endswith("t"))
                                p_text = p_text.strip()
                                if p_text:
                                    paragraphs.append(p_text)
                    except Exception:
                        continue

            if paragraphs:
                return paragraphs
        except Exception as e:
            logger.warning(f"ZIP/XML orqali o'qishda xatolik: {e}")

    # 3-usul: Agar fayl eski binary .doc yoki oddiy matn/RTF/HTML bo'lsa
    try:
        with open(file_path, "rb") as f:
            raw_data = f.read()

        # UTF-8 yoki Windows-1251 (Kirill) matnlarni qidirish
        # Matnli qismlarni muntazam ifoda yordamida ajratib olish
        text_chunks = re.findall(rb"[\x20-\x7E\x80-\xFF]{4,}", raw_data)
        for chunk in text_chunks:
            for enc in ["utf-8", "cp1251", "latin-1"]:
                try:
                    decoded = chunk.decode(enc).strip()
                    # Foydali matnlarni ajratish
                    if len(decoded) > 3 and not decoded.startswith("http") and not decoded.startswith("<?xml"):
                        paragraphs.append(decoded)
                        break
                except Exception:
                    continue

        if paragraphs:
            return paragraphs
    except Exception as e:
        logger.error(f"Binary .doc dan matn ajratishda xatolik: {e}")

    return paragraphs or ["Hujjatdan matn topilmadi."]


def doc_to_docx(doc_path: str, docx_path: str) -> bool:
    """
    Eski .doc yoki noan'anaviy Word faylini zamonaviy .docx ga o'tkazadi.
    1-usul: MS Word COM (asl format, jadval, rasm va uslublarni to'liq saqlagan holda).
    2-usul: python-docx zaxira usuli.
    """
    abs_in = os.path.abspath(doc_path)
    abs_out = os.path.abspath(docx_path)

    if HAS_WIN32COM:
        try:
            pythoncom.CoInitialize()
            word = win32com.client.Dispatch("Word.Application")
            word.Visible = False
            word.DisplayAlerts = 0
            doc = word.Documents.Open(abs_in, ReadOnly=True, ConfirmConversions=False)
            doc.SaveAs(abs_out, FileFormat=16)  # 16 = wdFormatXMLDocument (.docx)
            doc.Close(False)
            word.Quit()
            pythoncom.CoUninitialize()

            if os.path.exists(abs_out) and os.path.getsize(abs_out) > 0:
                logger.info(f"MS Word COM orqali DOCX muvaffaqiyatli yaratildi: {abs_out}")
                return True
        except Exception as e:
            logger.warning(f"MS Word COM doc_to_docx xatolik: {e}")
            try:
                pythoncom.CoUninitialize()
            except Exception:
                pass

    try:
        paragraphs = extract_text_from_word_file(doc_path)
        doc = Document()
        for p in paragraphs:
            doc.add_paragraph(p)
        doc.save(abs_out)
        return True
    except Exception as e:
        logger.error(f"DOC -> DOCX xatolik: {e}")
        return False


def docx_to_pdf(doc_path: str, pdf_path: str) -> bool:
    """
    Word (.docx yoki .doc) faylini PDF formatiga o'tkazadi.
    1-usul: Microsoft Word COM orqali 100% asl dizayn, jadvallar, rasmlar va shriftlar bilan.
    2-usul: Agar Word ishlamasa, ReportLab zaxira tizimi.
    """
    abs_in = os.path.abspath(doc_path)
    abs_out = os.path.abspath(pdf_path)

    # 1-usul: MS Word COM orqali to'g'ridan-to'g'ri o'girish (Asl sifat)
    if HAS_WIN32COM:
        try:
            pythoncom.CoInitialize()
            word = win32com.client.Dispatch("Word.Application")
            word.Visible = False
            word.DisplayAlerts = 0  # wdAlertsNone
            doc = word.Documents.Open(abs_in, ReadOnly=True, ConfirmConversions=False)
            doc.SaveAs(abs_out, FileFormat=17)  # 17 = wdFormatPDF
            doc.Close(False)
            word.Quit()
            pythoncom.CoUninitialize()

            if os.path.exists(abs_out) and os.path.getsize(abs_out) > 0:
                logger.info(f"MS Word COM orqali PDF muvaffaqiyatli yaratildi: {abs_out}")
                return True
        except Exception as e:
            logger.warning(f"MS Word COM orqali PDF yaratishda xatolik: {e}, ReportLab ga o'tilmoqda...")
            try:
                pythoncom.CoUninitialize()
            except Exception:
                pass

    # 2-usul: ReportLab zaxira tizimi
    try:
        paragraphs = extract_text_from_word_file(doc_path)
        if not paragraphs:
            paragraphs = ["Hujjat bo'sh yoki matn topilmadi."]

        doc = SimpleDocTemplate(
            abs_out,
            pagesize=A4,
            leftMargin=36,
            rightMargin=36,
            topMargin=36,
            bottomMargin=36
        )

        styles = getSampleStyleSheet()
        normal_style = ParagraphStyle(
            "CustomWordStyle",
            parent=styles["Normal"],
            fontName=FONT_NAME,
            fontSize=11,
            leading=15,
            spaceAfter=6
        )

        story = []
        for p in paragraphs:
            safe_text = html.escape(p).replace("\n", "<br/>")
            story.append(Paragraph(safe_text, normal_style))

        doc.build(story)
        return os.path.exists(abs_out) and os.path.getsize(abs_out) > 0
    except Exception as e:
        logger.error(f"DOCX/DOC -> PDF konvertatsiyasida xatolik: {e}")
        return False


def docx_to_txt(doc_path: str, txt_path: str) -> bool:
    """
    Word (.docx yoki .doc) faylini .txt matn fayliga o'tkazadi.
    """
    try:
        paragraphs = extract_text_from_word_file(doc_path)
        full_text = "\n\n".join(paragraphs)

        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(full_text)
        return True
    except Exception as e:
        logger.error(f"DOCX/DOC -> TXT xatolik: {e}")
        return False


def pdf_to_docx(pdf_path: str, docx_path: str) -> bool:
    """
    PDF faylini Word (.docx) ga o'giradi.
    """
    try:
        reader = PdfReader(pdf_path)
        doc = Document()

        has_content = False
        for i, page in enumerate(reader.pages):
            text = page.extract_text()
            if text:
                has_content = True
                for line in text.split("\n"):
                    clean_line = line.strip()
                    if clean_line:
                        doc.add_paragraph(clean_line)
            if i < len(reader.pages) - 1:
                doc.add_page_break()

        if not has_content:
            doc.add_paragraph("PDF hujjatidan matn topilmadi (ehtimol skanerlangan rasm ko'rinishidagi PDF).")

        doc.save(docx_path)
        return True
    except Exception as e:
        logger.error(f"PDF -> DOCX xatolik: {e}")
        return False


def pdf_to_txt(pdf_path: str, txt_path: str) -> bool:
    """
    PDF faylidan matnni ajratib olib .txt faylga saqlaydi.
    """
    try:
        reader = PdfReader(pdf_path)
        text_content = []
        for i, page in enumerate(reader.pages):
            page_text = page.extract_text()
            if page_text:
                text_content.append(f"--- Sahifa {i + 1} ---\n" + page_text)

        full_text = "\n\n".join(text_content)
        if not full_text.strip():
            full_text = "PDF hujjatidan matn topilmadi (ehtimol skanerlangan rasm)."

        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(full_text)
        return True
    except Exception as e:
        logger.error(f"PDF -> TXT xatolik: {e}")
        return False


def excel_to_csv(xlsx_path: str, csv_path: str) -> bool:
    """
    Excel (.xlsx) faylini CSV formatiga o'tkazadi (Kirill harflari buzilmasligi uchun utf-8-sig).
    """
    try:
        wb = load_workbook(xlsx_path, data_only=True)
        sheet = wb.active
        with open(csv_path, mode="w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            for row in sheet.iter_rows(values_only=True):
                if any(cell is not None for cell in row):
                    writer.writerow([str(cell) if cell is not None else "" for cell in row])
        return True
    except Exception as e:
        logger.error(f"Excel -> CSV xatolik: {e}")
        return False


def csv_to_excel(csv_path: str, xlsx_path: str) -> bool:
    """
    CSV faylini Excel (.xlsx) ga o'tkazadi.
    """
    try:
        wb = Workbook()
        ws = wb.active
        with open(csv_path, mode="r", encoding="utf-8-sig", errors="ignore") as f:
            reader = csv.reader(f)
            for row in reader:
                ws.append(row)
        wb.save(xlsx_path)
        return True
    except Exception as e:
        logger.error(f"CSV -> Excel xatolik: {e}")
        return False


def excel_to_pdf(xlsx_path: str, pdf_path: str) -> bool:
    """
    Excel (.xlsx, .xls) jadvallarini PDF formatiga o'tkazadi.
    1-usul: MS Excel COM (asl jadvallar, ranglar va ustunlar kengligi to'liq saqlanadi).
    2-usul: ReportLab zaxira usuli.
    """
    abs_in = os.path.abspath(xlsx_path)
    abs_out = os.path.abspath(pdf_path)

    if HAS_WIN32COM:
        try:
            pythoncom.CoInitialize()
            excel = win32com.client.Dispatch("Excel.Application")
            excel.Visible = False
            excel.DisplayAlerts = False
            wb = excel.Workbooks.Open(abs_in, ReadOnly=True)
            wb.ExportAsFixedFormat(0, abs_out)  # 0 = xlTypePDF
            wb.Close(False)
            excel.Quit()
            pythoncom.CoUninitialize()

            if os.path.exists(abs_out) and os.path.getsize(abs_out) > 0:
                logger.info(f"MS Excel COM orqali PDF muvaffaqiyatli yaratildi: {abs_out}")
                return True
        except Exception as e:
            logger.warning(f"MS Excel COM excel_to_pdf xatolik: {e}")
            try:
                pythoncom.CoUninitialize()
            except Exception:
                pass

    try:
        wb = load_workbook(xlsx_path, data_only=True)
        sheet = wb.active
        data = []

        styles = getSampleStyleSheet()
        cell_style = ParagraphStyle(
            "ExcelCell",
            parent=styles["Normal"],
            fontName=FONT_NAME,
            fontSize=8,
            leading=10
        )

        for row in sheet.iter_rows(values_only=True):
            if any(cell is not None for cell in row):
                row_cells = []
                for cell in row:
                    cell_val = str(cell)[:50] if cell is not None else ""
                    row_cells.append(Paragraph(html.escape(cell_val), cell_style))
                data.append(row_cells)

        if not data:
            data = [[Paragraph("Jadval bo'sh", cell_style)]]

        pdf = SimpleDocTemplate(
            abs_out,
            pagesize=A4,
            leftMargin=20,
            rightMargin=20,
            topMargin=20,
            bottomMargin=20
        )
        story = []
        table = Table(data)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#2C3E50")),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, -1), FONT_NAME),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 4),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ]))
        story.append(table)
        pdf.build(story)
        return os.path.exists(abs_out) and os.path.getsize(abs_out) > 0
    except Exception as e:
        logger.error(f"Excel -> PDF xatolik: {e}")
        return False


def image_to_pdf(image_path: str, pdf_path: str) -> bool:
    """
    Rasmni (JPG, PNG) PDF formatiga o'tkazadi.
    """
    try:
        img = Image.open(image_path)
        if img.mode != "RGB":
            img = img.convert("RGB")
        img.save(pdf_path, "PDF", resolution=100.0)
        return True
    except Exception as e:
        logger.error(f"Rasm -> PDF xatolik: {e}")
        return False
