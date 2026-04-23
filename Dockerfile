FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy project
COPY . .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Create data directories
RUN mkdir -p data/{vector_db,index}

# Default environment
ENV VECTOR_DB_TYPE=chromadb
ENV EMBEDDINGS_TYPE=ollama
ENV LLM_TYPE=ollama
ENV OLLAMA_BASE_URL=http://ollama:11434
ENV OLLAMA_LLM_BASE_URL=http://ollama:11434
ENV SKILL_PORT=8000

# Expose API port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Default command: run skill server
CMD ["python3", "-m", "fs_rag.skill.server"]
