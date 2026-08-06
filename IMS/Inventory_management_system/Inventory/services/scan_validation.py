"""
Signed-scan validation: confirm an uploaded PDF/image carries the expected
release code, either as a QR code or as visible printed text.

Validation strategy (in priority order):
1. OpenCV QRCodeDetector — pure-pip via opencv-python-headless, no system
   binaries needed. Works on images and rasterised PDF pages.
2. PyMuPDF text extraction — if no QR found, scrape the PDF text layer for
   any printed RE-yyyy-NNNN codes. Catches scans where the QR is damaged
   but the printed code is legible.
3. pyzbar + pdf2image — legacy fallback for environments that have those
   libs installed alongside system zbar/poppler.

Outcomes from decode_qr_outcome():
  'match'      — expected code present
  'mismatch'   — code(s) found but none match
  'not_found'  — nothing decoded
  'error'      — unexpected decode failure

Decoding happens in-memory; callers can reject before persisting the file.
"""

from __future__ import annotations

import io
import logging
import re
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

# Sniff which decoders are available at import-time.
try:
    import cv2  # type: ignore
    import numpy as np  # type: ignore
    _OPENCV_OK = True
except Exception:  # noqa: BLE001
    _OPENCV_OK = False

try:
    import fitz  # type: ignore  # PyMuPDF
    _PYMUPDF_OK = True
except Exception:  # noqa: BLE001
    _PYMUPDF_OK = False

try:
    from PIL import Image  # type: ignore
    _PIL_OK = True
except Exception:  # noqa: BLE001
    _PIL_OK = False

try:
    from pyzbar.pyzbar import decode as _zbar_decode  # type: ignore
    _PYZBAR_OK = True
except Exception:  # noqa: BLE001
    _PYZBAR_OK = False

try:
    from pdf2image import convert_from_bytes  # type: ignore
    _PDF2IMAGE_OK = True
except Exception:  # noqa: BLE001
    _PDF2IMAGE_OK = False


def decoder_status() -> dict:
    """Surface which optional decoders are available."""
    return {
        'opencv': _OPENCV_OK,
        'pymupdf': _PYMUPDF_OK,
        'pillow': _PIL_OK,
        'pyzbar': _PYZBAR_OK,
        'pdf2image': _PDF2IMAGE_OK,
        'has_viable_path': _OPENCV_OK or _PYMUPDF_OK or _PYZBAR_OK,
    }


def _pdf_page_images_pymupdf(file_bytes: bytes, dpi: int = 220, max_pages: int = 3) -> List[bytes]:
    """Rasterise the first max_pages of a PDF to PNG bytes via PyMuPDF.

    Returns a list of PNG byte strings. Empty on failure. PyMuPDF ships
    its rasterisation engine in the wheel — no poppler needed.
    """
    if not _PYMUPDF_OK:
        return []
    try:
        doc = fitz.open(stream=file_bytes, filetype="pdf")
    except Exception:  # noqa: BLE001
        logger.exception("PyMuPDF failed to open PDF")
        return []

    pages = []
    try:
        zoom = dpi / 72.0
        mat = fitz.Matrix(zoom, zoom)
        for i, page in enumerate(doc):
            if i >= max_pages:
                break
            pix = page.get_pixmap(matrix=mat, alpha=False)
            pages.append(pix.tobytes("png"))
    except Exception:  # noqa: BLE001
        logger.exception("PyMuPDF page rasterisation failed")
    finally:
        doc.close()
    return pages


def _pdf_text_pymupdf(file_bytes: bytes, max_pages: int = 3) -> str:
    """Pull the text layer from the first max_pages of a PDF."""
    if not _PYMUPDF_OK:
        return ""
    try:
        doc = fitz.open(stream=file_bytes, filetype="pdf")
    except Exception:  # noqa: BLE001
        logger.exception("PyMuPDF failed to open PDF for text extraction")
        return ""

    parts = []
    try:
        for i, page in enumerate(doc):
            if i >= max_pages:
                break
            parts.append(page.get_text("text") or "")
    except Exception:  # noqa: BLE001
        logger.exception("PyMuPDF text extraction failed")
    finally:
        doc.close()
    return "\n".join(parts)


def _opencv_qr_payloads(image_bytes: bytes) -> List[str]:
    """Decode QR(s) from a PNG/JPG image using cv2.QRCodeDetector."""
    if not _OPENCV_OK:
        return []
    try:
        arr = np.frombuffer(image_bytes, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            return []
        detector = cv2.QRCodeDetector()
        try:
            ok, data, _, _ = detector.detectAndDecodeMulti(img)
            if ok and data:
                payloads = [d.strip() for d in data if d]
                if payloads:
                    return payloads
        except Exception:  # noqa: BLE001
            pass
        try:
            data, _, _ = detector.detectAndDecode(img)
            if data and data.strip():
                return [data.strip()]
        except Exception:  # noqa: BLE001
            pass
    except Exception:  # noqa: BLE001
        logger.exception("OpenCV QR decode failed")
    return []


def _pyzbar_payloads(image_bytes: bytes) -> List[str]:
    """Legacy pyzbar decode path."""
    if not (_PYZBAR_OK and _PIL_OK):
        return []
    try:
        img = Image.open(io.BytesIO(image_bytes))
        img.load()
        results = _zbar_decode(img)
        return [r.data.decode('utf-8', errors='ignore').strip() for r in results]
    except Exception:  # noqa: BLE001
        logger.exception("pyzbar decode failed")
        return []


def _pdf2image_pages(file_bytes: bytes) -> List[bytes]:
    """Legacy pdf2image rasterise path; needs poppler on host."""
    if not _PDF2IMAGE_OK:
        return []
    try:
        pages = convert_from_bytes(file_bytes, dpi=220, first_page=1, last_page=3)
        out = []
        for p in pages:
            buf = io.BytesIO()
            p.save(buf, format="PNG")
            out.append(buf.getvalue())
        return out
    except Exception:  # noqa: BLE001
        logger.exception("pdf2image rasterise failed (poppler probably missing)")
        return []


def extract_payloads(file_bytes: bytes, filename: Optional[str]) -> Tuple[List[str], str]:
    """Extract candidate codes from an upload.

    Returns (payloads, source). source is one of:
      'opencv-image', 'opencv-pdf', 'pyzbar-image', 'pyzbar-pdf',
      'pdf-text', or '' (nothing decoded).
    """
    is_pdf = (filename or '').lower().endswith('.pdf')

    if not is_pdf:
        payloads = _opencv_qr_payloads(file_bytes)
        if payloads:
            return payloads, 'opencv-image'
        payloads = _pyzbar_payloads(file_bytes)
        if payloads:
            return payloads, 'pyzbar-image'
        return [], ''

    # PDF path. Try PyMuPDF rasterise + OpenCV QR decode.
    if _PYMUPDF_OK and _OPENCV_OK:
        for page_png in _pdf_page_images_pymupdf(file_bytes):
            payloads = _opencv_qr_payloads(page_png)
            if payloads:
                return payloads, 'opencv-pdf'

    # PDF text-extraction fallback.
    if _PYMUPDF_OK:
        text = _pdf_text_pymupdf(file_bytes)
        if text:
            codes = re.findall(r'\bRE-\d{4}-\d{4}\b', text)
            if codes:
                seen, ordered = set(), []
                for c in codes:
                    if c not in seen:
                        seen.add(c)
                        ordered.append(c)
                return ordered, 'pdf-text'

    # Legacy pyzbar + pdf2image path.
    if _PYZBAR_OK and _PDF2IMAGE_OK:
        for page_png in _pdf2image_pages(file_bytes):
            payloads = _pyzbar_payloads(page_png)
            if payloads:
                return payloads, 'pyzbar-pdf'

    return [], ''


def payload_matches_code(payload: str, expected: str) -> bool:
    """Does a decoded QR payload identify `expected`?

    Two payload generations are in circulation and both must validate:

      * **bare code** — `RE-2026-0001`. Every document minted before the QR
        became a link. These are printed, signed and sitting in files; they
        cannot be reissued and must keep verifying forever.
      * **verify URL** — `https://host/verify/RE-2026-0001/`. What the QR
        encodes now, so that scanning a physical copy with a phone actually
        resolves the document instead of offering a web search.

    Matching is deliberately anchored rather than a loose substring test: the
    code must be the whole payload, or a complete path segment / query value
    within it. `RE-2026-0001` must never match `RE-2026-00012`, which would let
    one release validate another's scan.
    """
    payload = (payload or '').strip()
    expected = (expected or '').strip()
    if not payload or not expected:
        return False

    if payload.casefold() == expected.casefold():
        return True

    # Only treat it as a URL if it looks like one — a bare code should not be
    # split on '/' and matched piecewise.
    if '://' not in payload and not payload.startswith('/'):
        return False

    from urllib.parse import urlparse, parse_qs

    try:
        parsed = urlparse(payload)
    except ValueError:
        return False

    segments = [s for s in parsed.path.split('/') if s]
    if any(s.casefold() == expected.casefold() for s in segments):
        return True

    for values in parse_qs(parsed.query).values():
        if any(v.strip().casefold() == expected.casefold() for v in values):
            return True

    return False


def decode_qr_outcome(file_bytes: bytes, filename: Optional[str], expected_code: str) -> str:
    expected = (expected_code or '').strip()
    if not expected:
        return 'not_found'

    try:
        payloads, source = extract_payloads(file_bytes, filename)
        if not payloads:
            return 'not_found'
        if any(payload_matches_code(p, expected) for p in payloads):
            logger.info("Scan validated via %s: %s matched", source, expected)
            return 'match'
        logger.warning("Scan mismatch via %s: expected %s, got %s",
                       source, expected, payloads)
        return 'mismatch'
    except Exception:  # noqa: BLE001
        logger.exception("Unexpected error in decode_qr_outcome")
        return 'error'


# Action-oriented rejection messages (no internal library names exposed).
REJECTION_REASONS = {
    'mismatch': (
        "The verification code in this scan ({found_preview}) doesn't match "
        "the expected release event ({expected}). Verify you uploaded the "
        "correct signed scan and try again."
    ),
    'not_found': (
        "Couldn't read a verification code from this scan. Check that: "
        "(1) it's the scan of the system-generated release letter, "
        "(2) the QR code in the corner is visible and unobscured, "
        "(3) the printed RE-yyyy-NNNN code is legible. "
        "If the scan is genuinely correct, ask a superuser to force-accept."
    ),
    'error': (
        "Couldn't process this file. It may be corrupted or in an "
        "unsupported format. Try re-scanning at higher resolution as PDF or PNG."
    ),
}


def rejection_reason(outcome: str, expected_code: str, found_preview: str = "") -> str:
    template = REJECTION_REASONS.get(outcome, "Verification failed.")
    return template.format(
        expected=expected_code or 'the expected code',
        found_preview=found_preview or 'a different code',
    )
