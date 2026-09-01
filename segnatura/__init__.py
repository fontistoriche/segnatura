"""Structure-aware EPUB extraction with stable source citations."""

from .api import (Creator, EpubExtractionError, ExtractedBook,
                  ExtractionBlock, ExtractionDocument, ExtractionUnit,
                  RAGRecord, SCHEMA_RAG_RECORD, TextMatch, Tokenizer,
                  TokenSpan, extract)
from .audit import (AUDIT_PROMPT_VERSION, SCHEMA_AUDIT_REPORT, AuditBackend,
                    AuditCancelledError, AuditConfig, AuditCoverage,
                    AuditEstimate, AuditFinding, AuditReport,
                    AuditValidationIssue, audit, estimate_audit)
from .edition_profile import (EditionProfileError,
                              EditionProfileMismatchError,
                              EditionProfileSchemaError)
from .epub_safety import EpubSafetyLimits
from .llm import (InvalidLLMResponseError, LLMError, LLMUnavailableError,
                  OpenAICompatibleBackend, OpenAICompatibleConfig,
                  StructuredLLMBackend, StructuredResponse)


__version__ = "1.0.0"

__all__ = [
    "__version__",
    "extract",
    "ExtractedBook",
    "ExtractionUnit",
    "ExtractionDocument",
    "ExtractionBlock",
    "Creator",
    "RAGRecord",
    "TextMatch",
    "Tokenizer",
    "TokenSpan",
    "StructuredLLMBackend",
    "StructuredResponse",
    "OpenAICompatibleConfig",
    "OpenAICompatibleBackend",
    "LLMError",
    "LLMUnavailableError",
    "InvalidLLMResponseError",
    "EpubExtractionError",
    "EpubSafetyLimits",
    "SCHEMA_RAG_RECORD",
    "EditionProfileError",
    "EditionProfileSchemaError",
    "EditionProfileMismatchError",
    "audit",
    "AuditBackend",
    "AuditCancelledError",
    "AuditConfig",
    "AuditFinding",
    "AuditCoverage",
    "AuditEstimate",
    "AuditValidationIssue",
    "AuditReport",
    "estimate_audit",
    "SCHEMA_AUDIT_REPORT",
    "AUDIT_PROMPT_VERSION",
]
