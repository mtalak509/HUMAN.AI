"""core.extractor — LLM extraction layer.

Public API re-exported here.
"""

from core.extractor.llm import Extractor
from core.extractor.schema import Contact, Education, Experience, ExtractedCandidate

__all__ = ["Extractor", "ExtractedCandidate", "Contact", "Experience", "Education"]
