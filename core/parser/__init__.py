"""core.parser — PDF parsing and storage layer.

Public API re-exported here (analogous to core/models.py re-export shim).
Internal backend seam (_backend.py) is NOT re-exported.
"""

from core.parser.pdf import ParseResult, PdfParser

__all__ = ["PdfParser", "ParseResult"]
