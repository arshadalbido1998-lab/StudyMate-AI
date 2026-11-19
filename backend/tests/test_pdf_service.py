import io
import os
import shutil
import unittest
from unittest.mock import patch

import fitz
from PIL import Image, ImageDraw, ImageFont
from pypdf import PdfWriter
import pytesseract

from services.pdf_service import PDFProcessingError, extract_text_from_pdf


def make_image_pdf(page_texts: list[str]) -> bytes:
    document = fitz.open()
    font_path = r"C:\Windows\Fonts\arial.ttf"
    font = ImageFont.truetype(font_path, 46) if os.path.exists(font_path) else None

    for page_text in page_texts:
        image = Image.new("RGB", (1800, 900), "white")
        draw = ImageDraw.Draw(image)
        draw.multiline_text((80, 80), page_text, fill="black", font=font, spacing=28)
        image_bytes = io.BytesIO()
        image.save(image_bytes, format="PNG")
        page = document.new_page(width=900, height=450)
        page.insert_image(page.rect, stream=image_bytes.getvalue())

    pdf_bytes = document.tobytes()
    document.close()
    return pdf_bytes


def make_text_pdf(page_count: int) -> bytes:
    document = fitz.open()
    for page_number in range(page_count):
        page = document.new_page()
        page.insert_text(
            (72, 72),
            f"Study textbook page {page_number + 1}. " * 6,
        )
    pdf_bytes = document.tobytes()
    document.close()
    return pdf_bytes


def make_scanned_pdf(page_count: int) -> bytes:
    image = Image.new("RGB", (1800, 900), "white")
    font_path = r"C:\Windows\Fonts\arial.ttf"
    font = ImageFont.truetype(font_path, 46) if os.path.exists(font_path) else None
    ImageDraw.Draw(image).text(
        (80, 80),
        "Scanned textbook page contains biology and learning content.",
        fill="black",
        font=font,
    )
    image_bytes = io.BytesIO()
    image.save(image_bytes, format="PNG")
    shared_image = image_bytes.getvalue()

    document = fitz.open()
    for _ in range(page_count):
        page = document.new_page(width=900, height=450)
        page.insert_image(page.rect, stream=shared_image)
    pdf_bytes = document.tobytes()
    document.close()
    return pdf_bytes


def make_blank_pdf(page_count: int, password: str | None = None) -> bytes:
    writer = PdfWriter()
    for _ in range(page_count):
        writer.add_blank_page(width=612, height=792)
    if password:
        writer.encrypt(password)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


class PDFExtractionTests(unittest.TestCase):
    def test_text_pdfs_below_and_above_40_pages_are_fully_extracted(self) -> None:
        for page_count in (40, 41):
            with self.subTest(page_count=page_count):
                text = extract_text_from_pdf(make_text_pdf(page_count))
                self.assertIn("Study textbook page 1.", text)
                self.assertIn(f"Study textbook page {page_count}.", text)

    def test_text_pdf_uses_normal_extraction_without_ocr(self) -> None:
        document = fitz.open()
        page = document.new_page()
        expected_text = (
            "The cell membrane controls what enters and leaves a cell. "
            "It is selectively permeable and supports homeostasis."
        )
        page.insert_text((72, 72), expected_text)
        pdf_bytes = document.tobytes()
        document.close()

        with patch("services.pdf_service._ocr_pdf") as ocr:
            text = extract_text_from_pdf(pdf_bytes)

        self.assertIn("cell membrane", text)
        ocr.assert_not_called()

    def test_empty_corrupted_encrypted_and_over_limit_pdfs_are_rejected(self) -> None:
        with self.assertRaisesRegex(PDFProcessingError, "empty"):
            extract_text_from_pdf(b"")
        with self.assertRaises(PDFProcessingError):
            extract_text_from_pdf(b"not a PDF")
        with self.assertRaisesRegex(PDFProcessingError, "encrypted"):
            extract_text_from_pdf(make_blank_pdf(1, password="secret"))
        with patch("services.pdf_service.MAX_PDF_PAGES", 41):
            with self.assertRaisesRegex(PDFProcessingError, "41 pages"):
                extract_text_from_pdf(make_blank_pdf(42))


@unittest.skipUnless(
    shutil.which("tesseract")
    or os.path.isfile(os.getenv("TESSERACT_CMD", "")),
    "Tesseract OCR executable is not installed or configured",
)
class ScannedPDFOCRTests(unittest.TestCase):
    def test_image_only_pdf_is_ocrd_in_page_order(self) -> None:
        pdf_bytes = make_image_pdf(
            [
                "Photosynthesis uses light energy to convert carbon dioxide "
                "and water into glucose and oxygen.",
                "Cellular respiration breaks down glucose and releases energy "
                "for cells to use.",
            ]
        )

        text = extract_text_from_pdf(pdf_bytes).casefold()

        first_page_position = text.index("photosynthesis")
        second_page_position = text.index("cellular respiration")
        self.assertLess(first_page_position, second_page_position)
        self.assertIn("glucose", text)

    def test_scanned_pdf_above_40_pages_is_ocrd_in_order_across_batches(self) -> None:
        page_texts = [
            "First scanned page marker. Biology textbook study material."
        ]
        page_texts.extend(
            f"Middle scanned page {page_number}. Biology textbook study material."
            for page_number in range(2, 41)
        )
        page_texts.append(
            "Last scanned page marker. Biology textbook study material."
        )
        pdf_bytes = make_image_pdf(page_texts)

        with patch.object(
            pytesseract,
            "image_to_string",
            wraps=pytesseract.image_to_string,
        ) as ocr:
            text = extract_text_from_pdf(pdf_bytes)

        self.assertEqual(ocr.call_count, 41)
        normalized_text = text.casefold()
        self.assertLess(
            normalized_text.index("first scanned page marker"),
            normalized_text.index("last scanned page marker"),
        )


if __name__ == "__main__":
    unittest.main()
