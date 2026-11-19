import io
import os
import shutil
import unittest
from unittest.mock import patch

import fitz
from PIL import Image, ImageDraw, ImageFont
from fastapi.testclient import TestClient

import main
from services.pdf_service import (
    OCRDependencyError,
    PDFPageLimitError,
    PDFProcessingError,
)


def make_image_pdf() -> bytes:
    image = Image.new("RGB", (1800, 900), "white")
    font_path = r"C:\Windows\Fonts\arial.ttf"
    font = ImageFont.truetype(font_path, 46) if os.path.exists(font_path) else None
    text = (
        "Photosynthesis uses light energy to convert carbon dioxide and water "
        "into glucose and oxygen."
    )
    ImageDraw.Draw(image).text((80, 80), text, fill="black", font=font)
    image_bytes = io.BytesIO()
    image.save(image_bytes, format="PNG")

    document = fitz.open()
    page = document.new_page(width=900, height=450)
    page.insert_image(page.rect, stream=image_bytes.getvalue())
    pdf_bytes = document.tobytes()
    document.close()
    return pdf_bytes


class PDFUploadTests(unittest.TestCase):
    def setUp(self) -> None:
        self.documents = main.document_store.copy()
        main.document_store.clear()
        self.client = TestClient(main.app)

    def tearDown(self) -> None:
        self.client.close()
        main.document_store.clear()
        main.document_store.update(self.documents)

    def test_extracted_pdf_text_is_saved_in_the_existing_document_store(self) -> None:
        with patch("main.extract_text_from_pdf", return_value="OCR content " * 12):
            response = self.client.post(
                "/upload",
                files={"file": ("scanned.pdf", b"pdf bytes", "application/pdf")},
            )

        self.assertEqual(response.status_code, 200)
        document_id = response.json()["document_id"]
        self.assertIn("OCR content", main.document_store[document_id]["full_text"])
        self.assertIn("OCR content", " ".join(main.document_store[document_id]["chunks"]))

    def test_missing_ocr_dependency_returns_actionable_error(self) -> None:
        with patch(
            "main.extract_text_from_pdf",
            side_effect=OCRDependencyError("Install Tesseract OCR for Windows."),
        ):
            response = self.client.post(
                "/upload",
                files={"file": ("scanned.pdf", b"pdf bytes", "application/pdf")},
            )

        self.assertEqual(response.status_code, 503)
        self.assertIn("Tesseract OCR", response.json()["detail"])

    def test_invalid_pdf_returns_client_error(self) -> None:
        with patch(
            "main.extract_text_from_pdf",
            side_effect=PDFProcessingError("This PDF is corrupted or invalid."),
        ):
            response = self.client.post(
                "/upload",
                files={"file": ("broken.pdf", b"bad pdf", "application/pdf")},
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn("corrupted", response.json()["detail"])

    def test_empty_and_unsupported_uploads_return_clear_errors(self) -> None:
        empty_pdf = self.client.post(
            "/upload",
            files={"file": ("empty.pdf", b"", "application/pdf")},
        )
        unsupported = self.client.post(
            "/upload",
            files={"file": ("notes.docx", b"text", "application/octet-stream")},
        )

        self.assertEqual(empty_pdf.status_code, 400)
        self.assertIn("empty", empty_pdf.json()["detail"])
        self.assertEqual(unsupported.status_code, 400)
        self.assertIn("Only PDF, TXT, and MD", unsupported.json()["detail"])

    def test_upload_size_limit_is_enforced(self) -> None:
        oversized = b"x" * (main.MAX_UPLOAD_SIZE + 1)
        response = self.client.post(
            "/upload",
            files={"file": ("notes.txt", io.BytesIO(oversized), "text/plain")},
        )

        self.assertEqual(response.status_code, 413)
        self.assertIn("20 MB", response.json()["detail"])

    def test_pdf_upload_uses_configured_pdf_size_limit(self) -> None:
        with (
            patch("main.MAX_PDF_SIZE_BYTES", 1024),
            patch("main.MAX_PDF_SIZE_MB", 1),
        ):
            oversized = b"x" * 1025
            response = self.client.post(
                "/upload",
                files={
                    "file": (
                        "large.pdf",
                        io.BytesIO(oversized),
                        "application/pdf",
                    )
                },
            )

        self.assertEqual(response.status_code, 413)
        self.assertIn("1 MB", response.json()["detail"])

    def test_page_limit_rejects_pdf_without_partial_storage(self) -> None:
        with patch(
            "main.extract_text_from_pdf",
            side_effect=PDFPageLimitError(
                "PDFs are limited to 500 pages. The PDF was not partially processed."
            ),
        ):
            response = self.client.post(
                "/upload",
                files={"file": ("large.pdf", b"pdf bytes", "application/pdf")},
            )

        self.assertEqual(response.status_code, 413)
        self.assertIn("not partially processed", response.json()["detail"])
        self.assertEqual(main.document_store, {})

    @unittest.skipUnless(
        shutil.which("tesseract")
        or os.path.isfile(os.getenv("TESSERACT_CMD", "")),
        "Tesseract OCR executable is not installed or configured",
    )
    def test_image_only_pdf_upload_saves_ocr_text_for_study_features(self) -> None:
        response = self.client.post(
            "/upload",
            files={
                "file": (
                    "scanned-textbook.pdf",
                    make_image_pdf(),
                    "application/pdf",
                )
            },
        )

        self.assertEqual(response.status_code, 200, response.json())
        document_id = response.json()["document_id"]
        stored_document = main.document_store[document_id]
        self.assertIn("Photosynthesis", stored_document["full_text"])
        self.assertIn("Photosynthesis", " ".join(stored_document["chunks"]))


if __name__ == "__main__":
    unittest.main()
