# FS-RAG: Filesystem Indexing & RAG-Powered Q&A

A modular, maintainable Python-based skill for OpenWebUI/OpenClaw that enables fast filesystem indexing with semantic search and AI-powered question answering over document collections.

> ⚠️ **Disclaimer:** This project was developed with the assistance of LLM tools and GitHub Copilot.

## 🎯 Features

- **Recursive filesystem indexing** - Scan and index entire directory trees
- **Multi-format support** - PDF, Word, Text, CSV, JSON, Markdown, Images
- **Hybrid search** - Combine keyword and semantic (vector) search
- **RAG pipeline** - Retrieve documents and generate answers with AI
- **Flexible backends** - Choose between ChromaDB, Qdrant for vectors; Ollama, OpenAI for embeddings and LLMs
- **CLI & API** - Both command-line and REST API interfaces
- **Easy configuration** - Environment-based settings

## 📋 Requirements

- Python 3.9+
- OpenWebUI or OpenClaw (for skill integration)
- For local LLM: Ollama or LM Studio
- For cloud LLM: OpenAI API key (optional)

## 🚀 Quick Start

### 1. Setup

```bash
# Clone or download the repository
cd /path/to/fs-rag

# Run setup
./setup.sh

# This will:
# - Create a Python virtual environment
# - Install all dependencies
# - Create .env configuration file
# - Test imports
```

### 2. Configure

Edit `.env` with your settings:

```bash
# Choose embeddings provider (local or cloud)
EMBEDDINGS_TYPE=ollama  # or openai
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=nomic-embed-text

# Choose LLM (local or cloud)
LLM_TYPE=ollama  # or openai
OLLAMA_LLM_MODEL=mistral

# Choose vector DB
VECTOR_DB_TYPE=chromadb  # or qdrant
```

### 3. Index a Directory

```bash
# Using CLI
./run-cli.sh index /path/to/documents

# Or using Python directly
python3 -m fs_rag.cli.main index /path/to/documents
```

### 4. Search and Ask Questions

```bash
# Search indexed documents
./run-cli.sh search "your search query"

# Ask a question (uses RAG)
./run-cli.sh ask "Does the Misereor project cover fuel expenses?"

# With options
./run-cli.sh ask "Question" --method hybrid --top-k 5 --sources
```

### 5. API Server (for OpenWebUI integration)

```bash
# Start the skill server
./run-skill.sh 8000

# The server will be available at http://localhost:8000
# Swagger docs: http://localhost:8000/docs
```

## 📚 Usage Examples

### CLI Usage

```bash
# Index a directory
./run-cli.sh index ~/Documents

# Show index statistics
./run-cli.sh stats

# Search using different methods
./run-cli.sh search "machine learning" --method semantic --top-k 3
./run-cli.sh search "Python code" --method keyword
./run-cli.sh search "AI" --method hybrid --top-k 10

# Ask questions with sources
./run-cli.sh ask "What are the main topics?" --sources

# Clear the index
./run-cli.sh clear

# Show configuration
./run-cli.sh config
```

### API Usage

```bash
# Health check
curl http://localhost:8000/health

# Index a directory
curl -X POST http://localhost:8000/index \
  -H "Content-Type: application/json" \
  -d '{"directory": "/path/to/documents", "force": false}'

# Search
curl -X POST http://localhost:8000/search \
  -H "Content-Type: application/json" \
  -d '{"query": "search term", "method": "hybrid", "top_k": 5}'

# Ask a question
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{
    "question": "Does the project cover fuel expenses?",
    "method": "hybrid",
    "top_k": 5,
    "include_sources": true
  }'

# Get stats
curl http://localhost:8000/stats
```

## 🏗️ Architecture

### Core Components

1. **Processor** (`fs_rag.processor`)
   - Handles multiple document formats
   - Extracts text and chunks content
   - Extensible for custom formats

2. **Embeddings** (`fs_rag.core.embeddings`)
   - Abstractly supports Ollama and OpenAI
   - Easy to add new providers

3. **Vector DB** (`fs_rag.core.vector_db`)
   - Supports ChromaDB (embedded) and Qdrant (scalable)
   - Unified interface for both

4. **Indexer** (`fs_rag.indexer`)
   - Recursive directory scanning
   - Metadata tracking (SQLite)
   - Incremental indexing

5. **Search Engine** (`fs_rag.search`)
   - Keyword search (SQLite)
   - Semantic search (vector DB)
   - Hybrid ranking

6. **RAG Pipeline** (`fs_rag.rag`)
   - Document retrieval
   - LLM prompt engineering
   - Answer generation

7. **CLI** (`fs_rag.cli`)
   - Command-line interface
   - Rich output formatting

8. **Skill** (`fs_rag.skill`)
   - FastAPI REST server
   - OpenWebUI/OpenClaw integration

## 📁 Supported Document Formats

- **Text**: `.txt`, `.md`, `.log`
- **PDF**: `.pdf`
- **Word**: `.docx`, `.doc`
- **Data**: `.csv`, `.json`
- **Images**: `.png`, `.jpg`, `.jpeg`, `.gif`, `.bmp` (basic support)

## ⚙️ Configuration

All configuration is handled via environment variables in `.env`:

```env
# Vector DB
VECTOR_DB_TYPE=chromadb  # chromadb | qdrant
VECTOR_DB_PATH=./data/vector_db
QDRANT_URL=http://localhost:6333

# Embeddings
EMBEDDINGS_TYPE=ollama  # ollama | openai
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=nomic-embed-text
OPENAI_API_KEY=sk-...
OPENAI_EMBEDDING_MODEL=text-embedding-3-small

# LLM
LLM_TYPE=ollama  # ollama | openai
OLLAMA_LLM_BASE_URL=http://localhost:11434
OLLAMA_LLM_MODEL=mistral
OPENAI_LLM_API_KEY=sk-...
OPENAI_LLM_MODEL=gpt-4

# Indexing
CHUNK_SIZE=512
CHUNK_OVERLAP=50
INDEX_BATCH_SIZE=32

# Search
SEARCH_TOP_K=5
SEARCH_SCORE_THRESHOLD=0.5

# Application
LOG_LEVEL=INFO
DEBUG=false
SKILL_PORT=8000
```

## 🔧 Extending

### Add Custom Document Processor

```python
from fs_rag.processor import DocumentProcessor, ProcessorFactory

class CustomProcessor(DocumentProcessor):
    def can_process(self, file_path):
        return file_path.suffix == ".custom"
    
    def extract_text(self, file_path):
        # Your extraction logic
        return text

# Register it
ProcessorFactory.register_processor(CustomProcessor(), priority=0)
```

### Add Custom Embeddings Provider

```python
from fs_rag.core.embeddings import EmbeddingsProvider

class CustomEmbeddings(EmbeddingsProvider):
    def embed(self, text: str):
        # Your embedding logic
        return np.array(embedding)
    
    def embed_batch(self, texts: list[str]):
        # Batch embedding
        return embeddings
```

## 📊 Performance Tips

1. **Use Qdrant for large datasets** (>100k documents)
2. **Tune chunk size** based on document type (smaller for dense text)
3. **Adjust semantic_weight** in hybrid search for your use case
4. **Enable batch processing** for faster indexing
5. **Use keyword search** for exact matches, semantic for intent

## 🐛 Troubleshooting

### Ollama connection errors
```bash
# Make sure Ollama is running
ollama serve

# Pull required models
ollama pull nomic-embed-text
ollama pull mistral
```

### Out of memory during indexing
```bash
# Reduce batch size in .env
INDEX_BATCH_SIZE=8
CHUNK_SIZE=256
```

### No search results
```bash
# Check if index is populated
./run-cli.sh stats

# Try keyword search first
./run-cli.sh search "your term" --method keyword

# Check logs
tail -f ./data/logs
```

## 📝 License

This project is provided as-is for use with OpenWebUI/OpenClaw.

## 🤝 Contributing

Contributions welcome! Areas for improvement:
- OCR for images (requires pytesseract)
- Database full-text search index
- Caching layer for repeated queries
- Multi-language support
- Document summarization
- Batch question answering

## 📞 Support

For issues or questions:
1. Check `.env` configuration
2. Review logs in console output
3. Test components individually using CLI
4. Check OpenWebUI documentation for skill integration
