"""Tests for PDF processor with OCR fallback."""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

from fs_rag.processor import PDFProcessor


class TestPDFProcessor:
    """Tests for PDFProcessor with OCR fallback."""

    def test_can_process_pdf(self):
        """Test that PDFProcessor can process PDF files."""
        processor = PDFProcessor()
        assert processor.can_process(Path("test.pdf"))
        assert not processor.can_process(Path("test.txt"))
        assert not processor.can_process(Path("test.docx"))

    @patch("fs_rag.processor.PDFProcessor._extract_with_pypdf2")
    def test_extract_text_pypdf2_success(self, mock_pypdf2):
        """Test successful extraction with PyPDF2."""
        mock_pypdf2.return_value = ("Extracted text content", True)
        
        processor = PDFProcessor()
        result = processor.extract_text(Path("test.pdf"))
        
        assert result == "Extracted text content"
        mock_pypdf2.assert_called_once()

    @patch("fs_rag.processor.PDFProcessor._extract_with_ocr")
    @patch("fs_rag.processor.PDFProcessor._extract_with_pypdf2")
    def test_extract_text_pypdf2_fail_ocr_success(self, mock_pypdf2, mock_ocr):
        """Test fallback to OCR when PyPDF2 fails."""
        mock_pypdf2.return_value = ("", False)
        mock_ocr.return_value = "OCR extracted text"
        
        processor = PDFProcessor()
        result = processor.extract_text(Path("test.pdf"))
        
        assert result == "OCR extracted text"
        mock_pypdf2.assert_called_once()
        mock_ocr.assert_called_once()

    @patch("fs_rag.processor.PDFProcessor._extract_with_ocr")
    @patch("fs_rag.processor.PDFProcessor._extract_with_pypdf2")
    def test_extract_text_both_fail(self, mock_pypdf2, mock_ocr):
        """Test when both PyPDF2 and OCR fail."""
        mock_pypdf2.return_value = ("", False)
        mock_ocr.return_value = ""
        
        processor = PDFProcessor()
        result = processor.extract_text(Path("test.pdf"))
        
        assert result == ""

    @patch("PyPDF2.PdfReader")
    def test_extract_with_pypdf2_basic(self, mock_reader_class):
        """Test basic PyPDF2 extraction."""
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "Page content"
        
        mock_reader = MagicMock()
        mock_reader.pages = [mock_page]
        mock_reader_class.return_value = mock_reader
        
        processor = PDFProcessor()
        with patch("builtins.open", create=True):
            text, success = processor._extract_with_pypdf2(Path("test.pdf"))
        
        assert success is True
        assert "Page content" in text

    @patch("PyPDF2.PdfReader")
    def test_extract_with_pypdf2_minimal_text(self, mock_reader_class):
        """Test PyPDF2 with minimal text (likely scanned PDF)."""
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "a"  # Too short
        
        mock_reader = MagicMock()
        mock_reader.pages = [mock_page]
        mock_reader_class.return_value = mock_reader
        
        processor = PDFProcessor()
        with patch("builtins.open", create=True):
            text, success = processor._extract_with_pypdf2(Path("test.pdf"))
        
        assert success is False
        assert text == ""

    def test_extract_with_pypdf2_import_error(self):
        """Test PyPDF2 extraction when library is not installed."""
        processor = PDFProcessor()
        
        with patch.dict("sys.modules", {"PyPDF2": None}):
            text, success = processor._extract_with_pypdf2(Path("test.pdf"))
        
        assert success is False
        assert text == ""

    @patch("fs_rag.processor.easyocr", create=True)
    @patch("fs_rag.processor.convert_from_path")
    def test_extract_with_ocr_basic(self, mock_convert, mock_easyocr):
        """Test basic OCR extraction."""
        # Mock PDF to images conversion
        mock_image = MagicMock()
        mock_convert.return_value = [mock_image]
        
        # Mock OCR reader
        mock_reader = MagicMock()
        mock_reader.readtext.return_value = ["Scanned", "text", "content"]
        mock_easyocr.Reader.return_value = mock_reader
        
        processor = PDFProcessor()
        result = processor._extract_with_ocr(Path("test.pdf"))
        
        assert "Scanned" in result
        assert "text" in result
        mock_convert.assert_called_once()
        mock_reader.readtext.assert_called_once()


    def test_extract_with_ocr_pdf2image_import_error(self):
        """Test OCR extraction when pdf2image is not installed."""
        processor = PDFProcessor()
        
        with patch.dict("sys.modules", {"pdf2image": None}):
            result = processor._extract_with_ocr(Path("test.pdf"))
        
        assert result == ""

    def test_extract_with_ocr_easyocr_import_error(self):
        """Test OCR extraction when EasyOCR is not installed."""
        processor = PDFProcessor()
        
        with patch("pdf2image.convert_from_path"):
            with patch.dict("sys.modules", {"easyocr": None}):
                result = processor._extract_with_ocr(Path("test.pdf"))
        
        assert result == ""

    @patch("fs_rag.processor.easyocr", create=True)
    @patch("fs_rag.processor.convert_from_path")
    def test_extract_with_ocr_empty_result(self, mock_convert, mock_easyocr):
        """Test OCR extraction with no text found."""
        mock_convert.return_value = []  # No images
        
        processor = PDFProcessor()
        result = processor._extract_with_ocr(Path("test.pdf"))
        
        assert result == ""


    @patch("fs_rag.processor.easyocr", create=True)
    @patch("fs_rag.processor.convert_from_path")
    def test_extract_with_ocr_max_pages(self, mock_convert, mock_easyocr):
        """Test OCR extraction respects page limit."""
        # Create many mock images
        mock_images = [MagicMock() for _ in range(60)]
        mock_convert.return_value = mock_images
        
        # Mock OCR reader
        mock_reader = MagicMock()
        mock_reader.readtext.return_value = ["text"]
        mock_easyocr.Reader.return_value = mock_reader
        
        processor = PDFProcessor()
        processor._extract_with_ocr(Path("test.pdf"))
        
        # Should be called with last_page=50
        call_args = mock_convert.call_args
        assert call_args[1]["last_page"] == 50


    @patch("fs_rag.processor.easyocr", create=True)
    @patch("fs_rag.processor.convert_from_path")
    def test_extract_with_ocr_page_skip_on_error(self, mock_convert, mock_easyocr):
        """Test OCR continues on single page error."""
        # Create 3 mock images
        mock_images = [MagicMock() for _ in range(3)]
        mock_convert.return_value = mock_images
        
        # Mock OCR reader - fails on page 2
        mock_reader = MagicMock()
        mock_reader.readtext.side_effect = [
            ["page1"],
            Exception("OCR failed"),
            ["page3"]
        ]
        mock_easyocr.Reader.return_value = mock_reader
        
        processor = PDFProcessor()
        result = processor._extract_with_ocr(Path("test.pdf"))
        
        # Should contain page 1 and 3, skip page 2
        assert "page1" in result
        assert "page3" in result
        assert mock_reader.readtext.call_count == 3



class TestPDFProcessorIntegration:
    """Integration tests for PDFProcessor."""

    def test_processor_factory_can_create_pdf_processor(self):
        """Test that ProcessorFactory can create PDFProcessor."""
        from fs_rag.processor import ProcessorFactory
        
        processor = ProcessorFactory.get_processor(Path("test.pdf"))
        assert isinstance(processor, PDFProcessor)

    def test_processor_factory_supports_pdf_files(self):
        """Test that ProcessorFactory recognizes PDF files."""
        from fs_rag.processor import ProcessorFactory
        
        assert ProcessorFactory.can_process(Path("test.pdf"))
        assert ProcessorFactory.can_process(Path("DOCUMENT.PDF"))
        assert not ProcessorFactory.can_process(Path("test.txt"))

    @patch("fs_rag.processor.PDFProcessor._extract_with_pypdf2")
    @patch("fs_rag.processor.PDFProcessor._extract_with_ocr")
    def test_extraction_strategy_selection(self, mock_ocr, mock_pypdf2):
        """Test that extraction strategy is chosen based on PDF content."""
        processor = PDFProcessor()
        
        # Scenario 1: Text PDF (PyPDF2 works)
        mock_pypdf2.return_value = ("text content", True)
        result = processor.extract_text(Path("text.pdf"))
        assert result == "text content"
        
        # Reset mocks
        mock_pypdf2.reset_mock()
        mock_ocr.reset_mock()
        
        # Scenario 2: Scanned PDF (PyPDF2 fails, OCR works)
        mock_pypdf2.return_value = ("", False)
        mock_ocr.return_value = "ocr content"
        result = processor.extract_text(Path("scanned.pdf"))
        assert result == "ocr content"
        
        # Verify fallback was triggered
        assert mock_pypdf2.call_count == 1
        assert mock_ocr.call_count == 1
