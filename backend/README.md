# StudyMate AI – Backend

A FastAPI backend using Groq by default for general StudyMate AI features.
Mind-map generation and customization use OpenRouter exclusively.

## Setup

```bash
cd backend
pip install -r requirements.txt
```

## Configure API Key

Edit `.env` and add the API key for the selected provider:
```
AI_PROVIDER=groq
GROQ_API_KEY=your_actual_key_here
OPENROUTER_API_KEY=your_openrouter_api_key_here
OPENROUTER_MIND_MAP_MODEL=openrouter/free
```

Set `AI_PROVIDER=gemini` and `GEMINI_API_KEY` to use Gemini instead.
`AI_PROVIDER` controls non-mind-map features. Mind-map generation, validation
repair requests, chunk merges, and customization always use OpenRouter. Set
`OPENROUTER_MIND_MAP_MODEL` to select the OpenRouter model; it defaults to
`openrouter/free`. Keep `OPENROUTER_API_KEY` in the backend `.env`; it is used
only by the backend and is never sent to the frontend. Groq remains the provider
for other features when `AI_PROVIDER=groq`.

## Scanned PDFs (local OCR on Windows)

Text-based PDFs use normal PDF text extraction. PDFs with fewer than 50
readable extracted characters are processed page-by-page with English OCR.
Scanned PDFs are rendered and OCRed in ordered batches of 15 pages. PDF uploads
default to a 100 MB file-size limit and a 500-page maximum; text uploads remain
limited to 20 MB. Configure PDF limits with `STUDYMATE_MAX_PDF_SIZE_MB` and
`STUDYMATE_MAX_PDF_PAGES` in the backend environment. PDFs over either limit
are rejected, never partially processed.

Install the Python OCR dependencies with `pip install -r requirements.txt`.
PyMuPDF and pytesseract are Python packages, but Tesseract OCR itself is a
separate Windows application and must also be installed. If it is not on
`PATH`, set `TESSERACT_CMD` to its executable, for example:

```powershell
$env:TESSERACT_CMD = 'C:\Program Files\Tesseract-OCR\tesseract.exe'
```

## Run

```bash
uvicorn main:app --reload --port 8000
```

API will be available at: http://localhost:8000

## Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/upload` | Upload PDF/TXT file |
| POST | `/summarize` | Summarize uploaded document |
| POST | `/mind-map` | Generate a structured mind map from uploaded study material |
| POST | `/ask` | Ask a question about the document |
| POST | `/generate-quiz` | Generate a document-based multiple-choice quiz |
| POST | `/submit-quiz` | Submit quiz answers and receive a score and explanations |
| POST | `/study-plan` | Generate a study plan |
| DELETE | `/document/{id}` | Remove a document |

Mind-map generation uses the `o200k_base` tokenizer to split long documents
into source-grounded requests. Independent source chunks run with bounded
concurrency (default 2, maximum 3), configurable with
`STUDYMATE_MIND_MAP_CONCURRENCY`. Each request allows up to 3,200
prompt tokens plus 4,000 completion tokens. Partial maps are merged in bounded
stages and validated before the API responds. OpenRouter model availability and
free-tier limits are controlled by OpenRouter; a provider-side rejection is
returned as an error with no Groq fallback.
