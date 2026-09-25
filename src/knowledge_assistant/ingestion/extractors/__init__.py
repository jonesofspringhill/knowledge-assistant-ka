"""Format-specific text and document-metadata extractors."""

from knowledge_assistant.ingestion.extractors.docx import extract_docx
from knowledge_assistant.ingestion.extractors.markdown import extract_markdown
from knowledge_assistant.ingestion.extractors.pdf import extract_pdf
from knowledge_assistant.ingestion.extractors.text import extract_text

EXTRACTORS = {
    ".pdf": extract_pdf,
    ".docx": extract_docx,
    ".md": extract_markdown,
    ".txt": extract_text,
}
