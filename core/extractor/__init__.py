"""core.extractor — LLM extraction layer.

Public API re-exported here. Plan 05-02 will add Extractor class.
"""

from core.extractor.schema import Contact, Education, Experience, ExtractedCandidate

__all__ = ["ExtractedCandidate", "Contact", "Experience", "Education"]
