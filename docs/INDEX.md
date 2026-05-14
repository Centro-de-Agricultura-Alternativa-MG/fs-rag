# FS-RAG Documentation Index

Welcome to the **Filesystem Indexing & RAG-Powered Q&A Skill** for OpenWebUI/OpenClaw!

This document serves as your entry point to all documentation and resources.

## 🎯 Start Here

### First Time User?
1. Read: **[README.md](README.md)** - Complete user guide with examples
2. Then: **[QUICK_REFERENCE.md](QUICK_REFERENCE.md)** - Command cheatsheet
3. Try: Run `./example.sh` - See it in action

### Want to Integrate with OpenWebUI?
→ Follow: **[INTEGRATION.md](INTEGRATION.md)** - Step-by-step setup

### Need Architecture Details?
→ Review: **[PROJECT_SUMMARY.md](PROJECT_SUMMARY.md)** - System overview

### Looking for Specific Files?
→ Check: **[FILE_MANIFEST.md](FILE_MANIFEST.md)** - Complete file listing

## 📚 Documentation Files

| Document | Size | Purpose |
|----------|------|---------|
| **[README.md](README.md)** | 7.5 KB | Complete user guide with features, usage, and troubleshooting |
| **[QUICK_REFERENCE.md](QUICK_REFERENCE.md)** | 4.2 KB | Quick command reference and common workflows |
| **[INTEGRATION.md](INTEGRATION.md)** | 6.8 KB | OpenWebUI/OpenClaw integration guide |
| **[PROJECT_SUMMARY.md](PROJECT_SUMMARY.md)** | 8.5 KB | High-level architecture and features overview |
| **[FILE_MANIFEST.md](FILE_MANIFEST.md)** | 10+ KB | Detailed listing of all project files |
| **[BUILD_COMPLETE.txt](BUILD_COMPLETE.txt)** | 14 KB | Build completion summary and checklist |
| **[INDEX.md](INDEX.md)** | This file | Documentation navigation guide |

## 🚀 Quick Start

```bash
# Setup (one-time)
./setup.sh

# Index documents
./run-cli.sh index /path/to/documents

# Ask questions
./run-cli.sh ask "Your question?" --sources

# Start API (for OpenWebUI)
./run-skill.sh 8000
```

## 🏗️ Project Structure

```
fs-rag/
├── Documentation/
│   ├── INDEX.md                 ← You are here
│   ├── README.md                ← Start with this
│   ├── QUICK_REFERENCE.md
│   ├── INTEGRATION.md
│   ├── PROJECT_SUMMARY.md
│   ├── FILE_MANIFEST.md
│   └── BUILD_COMPLETE.txt
│
├── Source Code/
│   └── fs_rag/
│       ├── core/                Configuration, embeddings, vector DB
│       ├── processor/           Document format handlers
│       ├── indexer/             Filesystem indexing
│       ├── search/              Hybrid search engine
│       ├── rag/                 RAG pipeline
│       ├── cli/                 Command-line interface
│       ├── skill/               FastAPI REST server
│       └── tests/               Unit tests
│
├── Configuration/
│   ├── requirements.txt
│   ├── .env.example
│   ├── setup.py
│   └── manifest.json
│
├── Scripts/
│   ├── setup.sh
│   ├── run-cli.sh
│   ├── run-skill.sh
│   └── example.sh
│
└── Deployment/
    ├── Dockerfile
    └── docker-compose.yml
```

## 📖 Reading Guide by Use Case

### "I want to get started right now"
1. Run: `./setup.sh`
2. Read: [QUICK_REFERENCE.md](QUICK_REFERENCE.md)
3. Run: `./example.sh`
4. Try: `./run-cli.sh ask "Your question?"`

### "I want to integrate with OpenWebUI"
1. Read: [INTEGRATION.md](INTEGRATION.md)
2. Follow the step-by-step guide
3. Register the skill in OpenWebUI settings

### "I need to understand the architecture"
1. Read: [PROJECT_SUMMARY.md](PROJECT_SUMMARY.md)
2. Review: [FILE_MANIFEST.md](FILE_MANIFEST.md)
3. Browse: Source code in `fs_rag/`

### "I want to customize or extend it"
1. Read: [PROJECT_SUMMARY.md](PROJECT_SUMMARY.md) (Architecture section)
2. Check: Source code for extension points
3. Review: Code comments and type hints

### "Something isn't working"
1. Check: [README.md](README.md) → Troubleshooting section
2. Check: [INTEGRATION.md](INTEGRATION.md) → Troubleshooting section
3. Run: `./run-cli.sh stats` to verify setup
4. Review: Logs and error messages

## 🎯 Key Concepts

### Indexing
Scan and extract text from documents, split into chunks, generate embeddings, store in vector DB.
→ See: [README.md](README.md#indexing)

### Hybrid Search
Combine keyword search (SQLite) with semantic search (vector DB) for best results.
→ See: [README.md](README.md#search)

### RAG Pipeline
Retrieve relevant documents, generate LLM prompt, produce answer with sources.
→ See: [PROJECT_SUMMARY.md](PROJECT_SUMMARY.md#rag-pipeline)

### Flexible Backends
Choose local or cloud embeddings, local or cloud LLM, embedded or scalable vector DB.
→ See: [README.md](README.md#configuration)

## 🔧 Common Commands

```bash
# Indexing
./run-cli.sh index /path/to/docs                    # Index directory
./run-cli.sh index /path/to/docs --force            # Re-index everything

# Searching
./run-cli.sh search "query"                         # Hybrid search
./run-cli.sh search "query" --method semantic       # Semantic only
./run-cli.sh search "query" --method keyword        # Keyword only

# Q&A
./run-cli.sh ask "question?" --sources              # With sources

# Maintenance
./run-cli.sh stats                                  # Show index statistics
./run-cli.sh config                                 # Show configuration
./run-cli.sh clear                                  # Clear index
```

For more commands: See [QUICK_REFERENCE.md](QUICK_REFERENCE.md)

## 📊 What's Included

✅ Complete Python application (~3,500 lines)
✅ Multi-format document processor (7+ formats)
✅ Hybrid search engine (keyword + semantic)
✅ RAG pipeline with LLM integration
✅ REST API via FastAPI
✅ CLI tool with rich output
✅ Multiple backend support
✅ Docker & Docker Compose setup
✅ Comprehensive documentation
✅ Example scripts & tests

## 🔗 External Resources

For integrating with OpenWebUI:
- OpenWebUI Documentation: https://docs.openwebui.com/
- OpenClaw Documentation: https://openclaw.io/

For local LLM:
- Ollama: https://ollama.ai/
- LM Studio: https://lmstudio.ai/

For embeddings:
- Chroma (ChromaDB): https://www.trychroma.com/
- Qdrant: https://qdrant.tech/

## ❓ FAQ

**Q: Do I need to install Ollama?**
A: Not required, but recommended for local (free) operation. See [.env.example](.env.example) for configuration.

**Q: Can I use OpenAI instead?**
A: Yes! Set `EMBEDDINGS_TYPE=openai` and `LLM_TYPE=openai` in `.env`. Requires API key.

**Q: How many documents can it handle?**
A: With ChromaDB (default): ~100k documents. With Qdrant: >1M documents. See [README.md](README.md#performance).

**Q: How do I integrate with OpenWebUI?**
A: Follow the step-by-step guide in [INTEGRATION.md](INTEGRATION.md).

**Q: Can I add custom document formats?**
A: Yes! See the extending section in [PROJECT_SUMMARY.md](PROJECT_SUMMARY.md).

## �� Support

If you need help:
1. Check the **[README.md](README.md)** troubleshooting section
2. Review **[QUICK_REFERENCE.md](QUICK_REFERENCE.md)** for command syntax
3. Read **[INTEGRATION.md](INTEGRATION.md)** for OpenWebUI issues
4. Check inline code comments for implementation details

## 📋 File Checklist

Essential files:
- ✅ [README.md](README.md) - Start here
- ✅ [setup.sh](setup.sh) - Run for setup
- ✅ [requirements.txt](requirements.txt) - Dependencies
- ✅ [.env.example](.env.example) - Configuration template

Important for integration:
- ✅ [INTEGRATION.md](INTEGRATION.md) - OpenWebUI setup
- ✅ [docker-compose.yml](docker-compose.yml) - Docker deployment
- ✅ [manifest.json](manifest.json) - OpenWebUI metadata

Documentation:
- ✅ [QUICK_REFERENCE.md](QUICK_REFERENCE.md) - Command reference
- ✅ [PROJECT_SUMMARY.md](PROJECT_SUMMARY.md) - Architecture
- ✅ [FILE_MANIFEST.md](FILE_MANIFEST.md) - File listing

## 🎓 Learning Path

**Beginner:**
1. [README.md](README.md) - Learn what it does
2. Run `./setup.sh` - Get it running
3. [QUICK_REFERENCE.md](QUICK_REFERENCE.md) - Learn commands
4. `./example.sh` - See it work

**Intermediate:**
1. [INTEGRATION.md](INTEGRATION.md) - Set up with OpenWebUI
2. [PROJECT_SUMMARY.md](PROJECT_SUMMARY.md) - Understand architecture
3. Edit `.env` - Customize configuration

**Advanced:**
1. [FILE_MANIFEST.md](FILE_MANIFEST.md) - Understand structure
2. Review source code in `fs_rag/`
3. Extend with custom processors/providers

## 🚀 Next Steps

1. **Setup**: Run `./setup.sh`
2. **Learn**: Read [README.md](README.md)
3. **Try**: Execute `./example.sh`
4. **Integrate**: Follow [INTEGRATION.md](INTEGRATION.md)

---

**Version**: 0.1.0 | **Status**: Production Ready ✅

For documentation overview, see this file.
For quick commands, see [QUICK_REFERENCE.md](QUICK_REFERENCE.md).
For complete guide, see [README.md](README.md).
