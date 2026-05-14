# Integration with OpenWebUI/OpenClaw

This guide explains how to integrate the FS-RAG skill with OpenWebUI or OpenClaw.

## Prerequisites

- OpenWebUI or OpenClaw installed
- Docker (recommended for skill deployment)
- FS-RAG repository cloned or built

## Deployment Options

### Option 1: Docker Compose (Recommended)

The easiest way to deploy FS-RAG with all dependencies:

```bash
# 1. Update docker-compose.yml with your document directory
# Change: /path/to/documents to your actual path
vim docker-compose.yml

# 2. Build and start
docker-compose up -d

# 3. Index documents (from host or container)
curl -X POST http://localhost:8000/index \
  -H "Content-Type: application/json" \
  -d '{"directory": "/documents"}'

# 4. Test the API
curl http://localhost:8000/health
```

Then register in OpenWebUI:
- Go to Settings → Skills
- Add new skill: `http://localhost:8000`

### Option 2: Manual Installation

```bash
# 1. Setup FS-RAG
./setup.sh

# 2. Configure
# Edit .env with your Ollama/OpenAI settings

# 3. Start the skill server
./run-skill.sh 8000

# 4. Index your documents
./run-cli.sh index /path/to/documents

# 5. Register in OpenWebUI
# Go to Settings → Skills
# Add new skill: `http://localhost:8000`
```

### Option 3: Systemd Service (Linux)

Create `/etc/systemd/system/fs-rag.service`:

```ini
[Unit]
Description=FS-RAG Skill Server
After=network.target

[Service]
Type=simple
User=your-user
WorkingDirectory=/path/to/fs-rag
Environment="PATH=/path/to/fs-rag/venv/bin"
ExecStart=/path/to/fs-rag/venv/bin/python3 -m fs_rag.skill.server
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Then:
```bash
sudo systemctl daemon-reload
sudo systemctl enable fs-rag
sudo systemctl start fs-rag
```

## Using the Skill in OpenWebUI

### 1. Register the Skill

In OpenWebUI:
1. Go to **Settings** → **Skills** or **Tools**
2. Click **Add Tool** or **Add Skill**
3. Enter skill URL: `http://localhost:8000` (or your server address)
4. Click **Verify** or **Connect**

### 2. Using in Conversations

Once registered, you can use the skill in chats:

**As a Search Tool:**
```
Search my documents for: budget report 2024
```

**As a Q&A Tool:**
```
Ask my document database: What are the fuel expenses in the Misereor project?
```

**Combined with Chat:**
```
Based on my indexed documents, can you summarize the key expenses?
```

### 3. OpenClaw Integration (Advanced)

If using OpenClaw for workflow automation:

```yaml
workflows:
  document_analysis:
    steps:
      - name: index_documents
        action: fs-rag:index
        params:
          directory: /data/contracts
          
      - name: search_clauses
        action: fs-rag:search
        params:
          query: fuel expenses
          method: semantic
          
      - name: generate_report
        action: llm:generate
        params:
          prompt: "Based on these documents: {{search_results}}, summarize..."
```

## API Endpoints

The skill exposes these endpoints for integration:

### Health Check
```bash
GET /health
```

### Index Documents
```bash
POST /index
Content-Type: application/json

{
  "directory": "/path/to/documents",
  "force": false
}
```

### Search
```bash
POST /search
Content-Type: application/json

{
  "query": "your search query",
  "method": "hybrid",  # keyword, semantic, or hybrid
  "top_k": 5
}
```

### Ask Question (RAG)
```bash
POST /ask
Content-Type: application/json

{
  "question": "your question",
  "method": "hybrid",
  "top_k": 5,
  "include_sources": true
}
```

### Statistics
```bash
GET /stats
```

## Configuration for OpenWebUI

### Environment Variables

Set these before running the skill:

```bash
# For Ollama (local)
EMBEDDINGS_TYPE=ollama
LLM_TYPE=ollama
OLLAMA_BASE_URL=http://localhost:11434  # or IP from OpenWebUI container
OLLAMA_LLM_MODEL=mistral

# For OpenAI
EMBEDDINGS_TYPE=openai
LLM_TYPE=openai
OPENAI_API_KEY=sk-...
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
OPENAI_LLM_MODEL=gpt-4

# Vector DB
VECTOR_DB_TYPE=chromadb  # or qdrant
```

### Network Configuration

If running FS-RAG in Docker:

```yaml
# docker-compose.yml
services:
  fs-rag:
    networks:
      - open-webui-net  # Use OpenWebUI's network
```

Then in OpenWebUI, use the service name: `http://fs-rag:8000`

## Troubleshooting

### Skill not appearing in OpenWebUI

1. Check health: `curl http://localhost:8000/health`
2. Check CORS: Ensure OpenWebUI can reach the skill
3. Check firewall: `sudo ufw allow 8000`
4. Check skill URL format: Should include protocol and port

### Index not working

```bash
# Verify directory is accessible
ls -la /path/to/documents

# Check index status
curl http://localhost:8000/stats

# Check logs
tail -f ./data/logs  # If logging to file
```

### No search results

```bash
# Verify documents are indexed
curl http://localhost:8000/stats

# Test search directly
curl -X POST http://localhost:8000/search \
  -H "Content-Type: application/json" \
  -d '{"query": "test", "method": "keyword"}'
```

### LLM not responding

```bash
# Check Ollama is running
curl http://localhost:11434/api/tags

# Or verify OpenAI API key
echo $OPENAI_API_KEY
```

## Examples

### Index Company Documents

```bash
./run-cli.sh index ~/Documents/Company
```

Then in OpenWebUI:
```
Search my company documents for quarterly reports
```

### Budget Query

```
What's the total fuel budget in my indexed documents?
```

### Compliance Check

```
Find any mentions of insurance coverage requirements in my contracts
```

### Multi-language Support

```
Search for fuel expenses mentioned in any language
```

## Performance Tips

1. **Update Index Incrementally**
   - Don't re-index everything if only a few documents changed
   - Use `--force` flag only when needed

2. **Optimize Search**
   - Use keyword search for exact terms
   - Use semantic search for conceptual matching
   - Hybrid is best for general use

3. **Storage Management**
   - Monitor `data/vector_db` and `data/index` sizes
   - Clear old indexes if storage is limited
   - Use smaller chunk sizes for large document collections

4. **Connection Pooling**
   - The skill maintains persistent connections to Ollama/OpenAI
   - Multiple concurrent requests are handled efficiently

## Security Considerations

1. **API Keys**
   - Store in `.env` file, never commit to git
   - Use environment variables in production
   - Rotate keys regularly

2. **Document Access**
   - Only index documents you want searchable
   - Use file permissions to restrict access
   - Consider running in isolated container

3. **Network Security**
   - Use HTTPS in production
   - Restrict access to trusted networks
   - Use authentication if exposed publicly

## Support

For issues:
1. Check the main [README.md](README.md)
2. Review OpenWebUI documentation
3. Check skill logs: `curl http://localhost:8000/stats`
4. Test endpoints manually with `curl`
