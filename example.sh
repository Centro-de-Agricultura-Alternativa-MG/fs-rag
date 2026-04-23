#!/bin/bash
# Example: Index a sample directory and ask questions

set -e

source venv/bin/activate

echo "🔍 FS-RAG Example: Sample Indexing and Q&A"
echo "=========================================="
echo ""

# Create sample documents
mkdir -p example_docs

cat > example_docs/project_summary.txt << 'EOF'
Misereor Project Summary

The Misereor project is a comprehensive development initiative focusing on sustainable infrastructure development in emerging markets. The project covers multiple areas:

1. Infrastructure Development
   - Road construction and maintenance
   - Water supply systems
   - Electricity distribution networks

2. Funding and Budget
   - Total project budget: $50 million
   - Funding sources: Government grants, international donors, private investments
   - Expenses include: Labor costs, materials, equipment
   
3. Specific Expenses
   - Fuel expenses: $2.5 million annually for vehicles and generators
   - Transportation costs: $3.2 million
   - Administrative costs: $1.8 million
   - Maintenance and operations: $5 million per year

4. Timeline
   - Project start: January 2023
   - Expected completion: December 2026
   - Major milestones scheduled quarterly

The project is monitored by international oversight board to ensure compliance with environmental and social standards.
EOF

cat > example_docs/budget_details.txt << 'EOF'
Detailed Budget Breakdown for Misereor Project

Transportation and Logistics
- Truck fuel: $1.2 million/year
- Generator fuel: $0.8 million/year
- Equipment transport: $0.5 million/year
Total Fuel Costs: $2.5 million/year

Personnel
- Site managers: $200,000/year
- Engineers: $150,000/year
- Administrative staff: $100,000/year

Equipment and Materials
- Heavy machinery rental: $3 million/year
- Construction materials: $8 million/year
- Safety equipment: $500,000/year

Contingency Reserve: 10% of total budget
EOF

echo "✓ Created example documents in ./example_docs"
echo ""

# Index the documents
echo "📑 Indexing documents..."
python3 -m fs_rag.cli.main index ./example_docs
echo "✓ Indexing complete"
echo ""

# Show stats
echo "📊 Index Statistics:"
python3 -m fs_rag.cli.main stats
echo ""

# Example searches
echo "🔎 Example Searches:"
echo "=================="
echo ""

echo "1. Keyword search for 'fuel':"
python3 -m fs_rag.cli.main search "fuel" --method keyword --top-k 3
echo ""

echo "2. Semantic search for 'fuel expenses':"
python3 -m fs_rag.cli.main search "fuel expenses" --method semantic --top-k 3
echo ""

echo "3. Hybrid search for 'Does project cover fuel costs':"
python3 -m fs_rag.cli.main search "Does project cover fuel costs" --method hybrid --top-k 3
echo ""

# Example Q&A
echo "❓ Example Questions:"
echo "===================="
echo ""

echo "Q: Does the Misereor project cover fuel expenses?"
python3 -m fs_rag.cli.main ask "Does the Misereor project cover fuel expenses?" --sources
echo ""

echo "Q: What is the annual fuel budget?"
python3 -m fs_rag.cli.main ask "What is the annual fuel budget?" --sources
echo ""

echo "Q: When does the project end?"
python3 -m fs_rag.cli.main ask "When does the project end?" --sources
echo ""

echo "✅ Example complete!"
echo ""
echo "Try your own questions with:"
echo "  ./run-cli.sh ask 'Your question here' --sources"
