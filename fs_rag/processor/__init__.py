"""Document processor for handling multiple file types."""

from pathlib import Path
from typing import Optional
from abc import ABC, abstractmethod
from dataclasses import dataclass

import subprocess

from fs_rag.core import get_logger

logger = get_logger(__name__)


@dataclass
class DocumentChunk:
    """Represents a chunk of document text."""
    content: str
    source_file: Path
    chunk_index: int
    metadata: dict


class DocumentProcessor(ABC):
    """Base class for document processors."""

    @abstractmethod
    def can_process(self, file_path: Path) -> bool:
        """Check if this processor can handle the file."""
        pass

    @abstractmethod
    def extract_text(self, file_path: Path) -> str:
        """Extract text from the document."""
        pass

    def chunk_text(self, text: str, chunk_size: int = 512, chunk_overlap: int = 50) -> list[str]:
        """Split text into overlapping chunks."""
        chunks = []
        if len(text) <= chunk_size:
            return [text]

        for i in range(0, len(text), chunk_size - chunk_overlap):
            chunk = text[i : i + chunk_size]
            if chunk.strip():
                chunks.append(chunk)
        return chunks


class TextProcessor(DocumentProcessor):
    """Processor for plain text files."""

    def can_process(self, file_path: Path) -> bool:
        return file_path.suffix.lower() in {".txt", ".md", ".log"}

    def extract_text(self, file_path: Path) -> str:
        try:
            return file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            logger.warning(f"Failed to decode {file_path} as UTF-8, trying latin-1")
            return file_path.read_text(encoding="latin-1")


class PDFProcessor(DocumentProcessor):
    """Processor for PDF files."""

    def can_process(self, file_path: Path) -> bool:
        return file_path.suffix.lower() == ".pdf"

    def extract_text(self, file_path: Path) -> str:
        try:
            from PyPDF2 import PdfReader
        except ImportError:
            logger.error("PyPDF2 not installed. Install with: pip install PyPDF2")
            return ""

        try:
            text = []
            with open(file_path, "rb") as f:
                reader = PdfReader(f)
                for page in reader.pages:
                    text.append(page.extract_text())
            return "\n".join(text)
        except Exception as e:
            logger.error(f"Error extracting text from PDF {file_path}: {e}")
            return ""


class DocxProcessor(DocumentProcessor):
    """Processor for Microsoft Word documents."""

    def can_process(self, file_path: Path) -> bool:
        return file_path.suffix.lower() in {".docx"}

    def extract_text(self, file_path: Path) -> str:
        try:
            from docx import Document
        except ImportError:
            logger.error("python-docx not installed. Install with: pip install python-docx")
            return ""

        try:
            doc = Document(file_path)
            return "\n".join(paragraph.text for paragraph in doc.paragraphs)
        except Exception as e:
            logger.error(f"Error extracting text from DOCX {file_path}: {e}")
            return ""


class DocProcessor(DocumentProcessor):
    """Processor for Legacy Microsoft Word documents (.doc)."""

    def can_process(self, file_path: Path) -> bool:
        return file_path.suffix.lower() in {".doc"}

    def extract_text(self, file_path: Path) -> str:
        # 1️⃣ Tenta antiword (mais comum)
        try:
            result = subprocess.run(
                ["antiword", str(file_path)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True
            )
            return result.stdout.decode("utf-8", errors="ignore")
        except FileNotFoundError:
            logger.warning("antiword not installed, trying next fallback...")
        except Exception as e:
            logger.warning(f"antiword failed for {file_path}: {e}")

        # 2️⃣ Tenta catdoc
        try:
            result = subprocess.run(
                ["catdoc", str(file_path)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True
            )
            return result.stdout.decode("utf-8", errors="ignore")
        except FileNotFoundError:
            logger.warning("catdoc not installed, trying next fallback...")
        except Exception as e:
            logger.warning(f"catdoc failed for {file_path}: {e}")

        # 3️⃣ Fallback: converter via LibreOffice → docx
        try:
            subprocess.run(
                [
                    "libreoffice",
                    "--headless",
                    "--convert-to", "docx",
                    "--outdir", str(file_path.parent),
                    str(file_path)
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True
            )

            converted = file_path.with_suffix(".docx")

            if converted.exists():
                from docx import Document
                doc = Document(converted)
                return "\n".join(p.text for p in doc.paragraphs)

        except FileNotFoundError:
            logger.error("LibreOffice not installed. Cannot process .doc file.")
        except Exception as e:
            logger.error(f"LibreOffice conversion failed for {file_path}: {e}")

        logger.error(f"All extraction methods failed for {file_path}")
        return ""

class CSVProcessor(DocumentProcessor):
    """Processor for CSV files."""

    def can_process(self, file_path: Path) -> bool:
        return file_path.suffix.lower() == ".csv"

    def extract_text(self, file_path: Path) -> str:
        try:
            import csv
        except ImportError:
            logger.error("csv module not available")
            return ""

        try:
            text = []
            with open(file_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    text.append(str(row))
            return "\n".join(text)
        except Exception as e:
            logger.error(f"Error extracting text from CSV {file_path}: {e}")
            return ""


class JSONProcessor(DocumentProcessor):
    """Processor for JSON files."""

    def can_process(self, file_path: Path) -> bool:
        return file_path.suffix.lower() == ".json"

    def extract_text(self, file_path: Path) -> str:
        try:
            import json
        except ImportError:
            logger.error("json module not available")
            return ""

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return json.dumps(data, indent=2)
        except Exception as e:
            logger.error(f"Error extracting text from JSON {file_path}: {e}")
            return ""


class ImageProcessor(DocumentProcessor):
    """Processor for image files (using OCR if available)."""

    def can_process(self, file_path: Path) -> bool:
        return file_path.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".bmp"}

    def extract_text(self, file_path: Path) -> str:
        try:
            from PIL import Image
        except ImportError:
            logger.warning("Pillow not installed. Returning image metadata only.")
            return f"[Image: {file_path.name}]"

        try:
            # For now, just return metadata. Full OCR requires pytesseract
            img = Image.open(file_path)
            return f"[Image: {file_path.name} - {img.size} - {img.format}]"
        except Exception as e:
            logger.error(f"Error processing image {file_path}: {e}")
            return f"[Image: {file_path.name}]"


class ProcessorFactory:
    """Factory for creating appropriate document processors."""

    _processors = [
        PDFProcessor(),
        DocxProcessor(),
        DocProcessor(),
        CSVProcessor(),
        JSONProcessor(),
        ImageProcessor(),
        TextProcessor(),  # Keep last as fallback
    ]

    @classmethod
    def get_processor(cls, file_path: Path) -> Optional[DocumentProcessor]:
        """Get appropriate processor for a file."""
        for processor in cls._processors:
            if processor.can_process(file_path):
                return processor
        return None

    @classmethod
    def can_process(cls, file_path: Path) -> bool:
        """Check if any processor can handle the file."""
        return cls.get_processor(file_path) is not None

    @classmethod
    def register_processor(cls, processor: DocumentProcessor, priority: int = 0) -> None:
        """Register a custom processor."""
        if priority == 0:
            cls._processors.append(processor)
        else:
            cls._processors.insert(priority, processor)
