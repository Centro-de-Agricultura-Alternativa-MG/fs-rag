#!/bin/bash
set -e

echo "🚀 Setting up FS-RAG..."

# Check Python version
python_version=$(python3 --version 2>&1 | awk '{print $2}' | cut -d. -f1,2)
echo "✓ Python version: $python_version"

# Create virtual environment (optional but recommended)
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
    source venv/bin/activate
    echo "✓ Virtual environment created"
fi

# Install dependencies
echo "Installing dependencies..."
pip install -q --upgrade pip setuptools wheel
pip install -q -r requirements.txt
echo "✓ Dependencies installed"

# Copy environment template
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "✓ Created .env from template (edit with your settings)"
fi

# Create data directories
mkdir -p data/{vector_db,index}
echo "✓ Created data directories"

# Test imports
echo "Testing imports..."
python3 -c "from fs_rag.core import get_config; print('✓ Core imports working')"
python3 -c "from fs_rag.processor import ProcessorFactory; print('✓ Processor imports working')"
python3 -c "from fs_rag.indexer import FilesystemIndexer; print('✓ Indexer imports working')"
python3 -c "from fs_rag.search import HybridSearchEngine; print('✓ Search imports working')"
python3 -c "from fs_rag.rag import get_rag_pipeline; print('✓ RAG imports working')"

echo ""
echo "✅ Setup complete!"
echo ""
echo "Next steps:"
echo "1. Edit .env with your configuration"
echo "2. Run: python3 -m fs_rag.cli.main index /path/to/directory"
echo "3. Or: python3 -m fs_rag.skill.server (starts API server on port 8000)"
echo ""
