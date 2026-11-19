import io
import os

import pypdf
from pypdf.errors import PdfReadError

def _positive_int_setting(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError as error:
        raise RuntimeError(f"{name} must be a positive whole number.") from error
    if parsed < 1:
        raise RuntimeError(f"{name} must be a positive whole number.")
    return parsed


MAX_PDF_SIZE_MB = _positive_int_setting("STUDYMATE_MAX_PDF_SIZE_MB", 100)
MAX_PDF_SIZE_BYTES = MAX_PDF_SIZE_MB * 1024 * 1024
MAX_PDF_PAGES = _positive_int_setting("STUDYMATE_MAX_PDF_PAGES", 500)
OCR_BATCH_SIZE = 15
MIN_READABLE_PDF_CHARACTERS = 50
MAX_OCR_PIXELS = 20_000_000


class PDFProcessingError(ValueError):
    """A PDF is invalid, unsupported, or exceeds processing limits."""


class PDFPageLimitError(PDFProcessingError):
    """A PDF contains more pages than the application can safely process."""


class OCRDependencyError(RuntimeError):
    """The local OCR Python packages or Tesseract executable are unavailable."""


def _get_pdf_reader(file_bytes: bytes) -> pypdf.PdfReader:
    try:
        reader = pypdf.PdfReader(io.BytesIO(file_bytes))
        if reader.is_encrypted and not reader.decrypt(""):
            raise PDFProcessingError(
                "This PDF is encrypted. Upload an unencrypted PDF."
            )
        if not reader.pages:
            raise PDFProcessingError("This PDF contains no pages.")
        if len(reader.pages) > MAX_PDF_PAGES:
            raise PDFPageLimitError(
                f"PDFs are limited to {MAX_PDF_PAGES} pages. "
                "The PDF was not partially processed."
            )
        return reader
    except PDFProcessingError:
        raise
    except PdfReadError as error:
        raise PDFProcessingError(
            "This PDF is corrupted or invalid. Please upload a valid PDF."
        ) from error


def _ocr_pdf(file_bytes: bytes, page_count: int) -> str:
    try:
        import fitz
        import pytesseract
        from PIL import Image
    except ImportError as error:
        missing_package = error.name or "an OCR dependency"
        raise OCRDependencyError(
            "This scanned PDF needs local OCR. Install the backend OCR packages "
            "with 'pip install -r requirements.txt' "
            f"(missing: {missing_package}) and install Tesseract OCR for Windows."
        ) from error

    tesseract_path = os.getenv("TESSERACT_CMD", "").strip()
    if not tesseract_path:
        tesseract_path = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    if not os.path.isfile(tesseract_path):
        raise OCRDependencyError(
            f"Tesseract executable was not found at '{tesseract_path}'. "
            "Set TESSERACT_CMD to the full path of tesseract.exe."
        )
    pytesseract.pytesseract.tesseract_cmd = tesseract_path

    try:
        pytesseract.get_tesseract_version()
        with fitz.open(stream=file_bytes, filetype="pdf") as document:
            page_text: list[str] = []
            for batch_start in range(0, page_count, OCR_BATCH_SIZE):
                batch_end = min(batch_start + OCR_BATCH_SIZE, page_count)
                for page_number in range(batch_start, batch_end):
                    page = document.load_page(page_number)
                    page_area = page.rect.width * page.rect.height
                    if page_area <= 0:
                        raise PDFProcessingError(
                            "This PDF contains a page with invalid dimensions."
                        )
                    scale = min(2, (MAX_OCR_PIXELS / page_area) ** 0.5)
                    pixmap = page.get_pixmap(
                        matrix=fitz.Matrix(scale, scale),
                        alpha=False,
                    )
                    image_bytes = pixmap.tobytes("png")
                    with Image.open(io.BytesIO(image_bytes)) as image:
                        page_text.append(
                            pytesseract.image_to_string(image, lang="eng")
                        )
                    del image_bytes, pixmap, page
            return "\n\n".join(page_text).strip()
    except pytesseract.TesseractNotFoundError as error:
        raise OCRDependencyError(
            "Tesseract OCR was not found. Install Tesseract OCR for Windows, "
            "or set the TESSERACT_CMD environment variable to the full "
            "path of tesseract.exe."
        ) from error
    except pytesseract.TesseractError as error:
        raise OCRDependencyError(
        "Tesseract OCR could not process this scan. Verify that English "
        "language data is installed and that the PDF pages are readable."
        ) from error
    except PDFProcessingError:
        raise
    except (fitz.FileDataError, ValueError) as error:
        raise PDFProcessingError(
        "This PDF is corrupted or invalid. Please upload a valid PDF."
        ) from error
    except pypdf.errors.PdfReadError as error:
        raise PDFProcessingError(
        "This PDF is corrupted or invalid. Please upload a valid PDF."
        ) from error


def extract_text_from_pdf(file_bytes: bytes) -> str:
    """Extract PDF text, using local English OCR when pages are scanned."""
    if not file_bytes:
        raise PDFProcessingError("The uploaded PDF is empty.")

    reader = _get_pdf_reader(file_bytes)
    page_text: list[str] = []
    try:
        for page in reader.pages:
            extracted = page.extract_text()
            page_text.append(extracted or "")
    except (PdfReadError, ValueError, KeyError) as error:
        raise PDFProcessingError(
            "This PDF is corrupted or invalid. Please upload a valid PDF."
        ) from error
    text = "\n\n".join(page_text).strip()

    readable_characters = sum(character.isalnum() for character in text)
    if readable_characters >= MIN_READABLE_PDF_CHARACTERS:
        return text

    return _ocr_pdf(file_bytes, len(reader.pages))


def extract_text_from_txt(file_bytes: bytes) -> str:
    """Extract text from plain text file bytes."""
    try:
        return file_bytes.decode("utf-8").strip()
    except UnicodeDecodeError:
        return file_bytes.decode("latin-1").strip()


def chunk_text(text: str, chunk_size: int = 3000, overlap: int = 200) -> list[str]:
    """Split text into overlapping chunks for AI processing."""
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        chunks.append(chunk)
        start += chunk_size - overlap
    return chunks


def get_context_window(chunks: list[str], max_chars: int = 12000) -> str:
    """Get a safe context window from chunks."""
    context = ""
    for chunk in chunks:
        if len(context) + len(chunk) > max_chars:
            break
        context += chunk + "\n\n"
    return context.strip()
