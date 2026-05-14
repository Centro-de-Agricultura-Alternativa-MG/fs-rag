# FS-RAG Quick Reference

## 🚀 Quick Start (Copy & Paste)

```bash
# Clone/Navigate to project
cd /path/to/fs-rag

# Setup (one-time, ~2 minutes)
./setup.sh

# Index your documents
./run-cli.sh index /path/to/your/documents

# Ask a question
./run-cli.sh ask "Your question here?" --sources

# Start API server
./run-skill.sh 8000
```

## 📋 CLI Commands

```bash
# Indexing
./run-cli.sh index /path/to/docs          # Index a directory
./run-cli.sh index /path/to/docs --force  # Re-index everything

# Search
./run-cli.sh search "query"                # Search (default: hybrid)
./run-cli.sh search "query" --method semantic
./run-cli.sh search "query" --method keyword
./run-cli.sh search "query" --top-k 10

# Q&A
./run-cli.sh ask "question?" --sources
./run-cli.sh ask "question?" --method semantic

# Maintenance
./run-cli.sh stats                         # Show index stats
./run-cli.sh config                        # Show configuration
./run-cli.sh clear                         # Clear entire index
```

## 🔌 API Endpoints

```bash
# Health check
curl http://localhost:8000/health

# Index documents
curl -X POST http://localhost:8000/index \
  -H "Content-Type: application/json" \
  -d '{"directory": "/path"}'

# Search
curl -X POST http://localhost:8000/search \
  -H "Content-Type: application/json" \
  -d '{"query": "fuel", "method": "hybrid", "top_k": 5}'

# Ask question (RAG)
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "Does it cover fuel?", "include_sources": true}'

# Stats
curl http://localhost:8000/stats
```

## 📁 Supported Formats

- **Text**: `.txt`, `.md`, `.log`
- **PDF**: `.pdf`
- **Office**: `.docx`, `.doc`
- **Data**: `.csv`, `.json`
- **Images**: `.png`, `.jpg`, `.jpeg` (basic)

## ⚙️ Configuration (.env)

```env
# Choose backend
VECTOR_DB_TYPE=chromadb        # chromadb or qdrant
EMBEDDINGS_TYPE=ollama         # ollama or openai
LLM_TYPE=ollama                # ollama or openai

# Ollama settings (local, free)
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=nomic-embed-text
OLLAMA_LLM_MODEL=mistral

# OpenAI settings (cloud, paid)
OPENAI_API_KEY=sk-...
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
OPENAI_LLM_MODEL=gpt-4

# Tuning
CHUNK_SIZE=512                 # Document chunk size
CHUNK_OVERLAP=50               # Overlap between chunks
SEARCH_TOP_K=5                 # Results per search
```

## 🐳 Docker Setup

```bash
# Quick deployment
docker-compose up -d

# Index documents (from host)
curl -X POST http://localhost:8000/index \
  -d '{"directory": "/documents"}'

# Register in OpenWebUI
# Go to Settings → Skills
# Add: http://localhost:8000
```

## 🔍 Common Workflows

### Index Company Documents
```bash
./run-cli.sh index ~/Documents/Company
./run-cli.sh stats
./run-cli.sh ask "What contracts do we have?"
```

### Search Contracts
```bash
./run-cli.sh search "insurance liability" --method semantic
```

### Compliance Check
```bash
./run-cli.sh ask "Find all mentions of GDPR compliance"
```

### Budget Analysis
```bash
./run-cli.sh ask "What are the total expenses?" --sources
```

## 🛠️ Troubleshooting

| Issue | Solution |
|-------|----------|
| No results | Check stats: `./run-cli.sh stats` |
| Ollama error | Start Ollama: `ollama serve` |
| Setup fails | Delete venv: `rm -rf venv && ./setup.sh` |
| Port 8000 in use | `./run-skill.sh 9000` |
| API not responding | Check: `curl http://localhost:8000/health` |

## 📊 Performance

- **Index speed**: ~30-60s per 100 documents
- **Search speed**: <1 second
- **Q&A response**: 2-5 seconds
- **Storage**: ~10KB per document (vector index)

## 🔐 Security

```bash
# Never commit .env with real API keys
git checkout .env

# For production
export OPENAI_API_KEY=sk-...
export QDRANT_API_KEY=...
```

## 🚀 Production Deployment

```bash
# Docker Compose
docker-compose up -d

# Systemd service
sudo cp fs-rag.service /etc/systemd/system/
sudo systemctl enable fs-rag
sudo systemctl start fs-rag
```

## 📚 Documentation

- **README.md** - Full documentation
- **INTEGRATION.md** - OpenWebUI integration
- **PROJECT_SUMMARY.md** - Architecture overview

## 💡 Tips

1. Use **hybrid search** for best results
2. **Semantic search** for conceptual matching
3. **Keyword search** for exact phrases
4. Increase `top_k` for more results
5. Reduce `CHUNK_SIZE` for dense documents
6. Use `--force` flag sparingly (slow)
7. Monitor `data/` folder size
8. Backup `data/index.db` for metadata

## 🔗 Integration

```python
# Python SDK
from fs_rag.indexer import FilesystemIndexer
from fs_rag.rag import get_rag_pipeline

indexer = FilesystemIndexer()
indexer.index_directory("/docs")

rag = get_rag_pipeline()
answer = rag.answer_question("Question?", include_sources=True)
print(answer["answer"])
```

---

**Need help?** Check README.md, INTEGRATION.md, or PROJECT_SUMMARY.md
