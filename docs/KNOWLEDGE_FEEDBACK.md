# Knowledge Feedback Memory

## Visão Geral

O **Knowledge Feedback Memory** é um sistema automático que captura respostas úteis geradas pelo RAG e as indexa como conhecimento reutilizável. Isso permite que o sistema aprenda com suas próprias respostas, melhorando continuamente a qualidade das respostas futuras.

## Fluxo Automático

```
1. Usuário pergunta
   ↓
2. RAG executa pipeline normal
   ↓
3. Resposta é retornada IMEDIATAMENTE ao usuário
   ↓
4. [ASSÍNCRONO] Avaliação automática com LLM
   ├─ Se score >= threshold:
   │  ├─ Gera embedding da resposta
   │  ├─ Indexa no vector database
   │  └─ Salva metadata
   └─ Se score < threshold: Descarta
   ↓
5. Próximas buscas incluem respostas retroalimentadas com boost de score
```

## Componentes

### 1. KnowledgeFeedbackEvaluator

Avalia se uma resposta merece ser salva como conhecimento usando LLM.

**Critérios de Avaliação:**
- **Relevância**: Responde a pergunta
- **Reutilizabilidade**: Aplicável a situações similares
- **Valor Organizacional**: Conhecimento institucional
- **Clareza**: Bem estruturado
- **Factualidade**: Preciso e verificável
- **Informativeness**: Denso em informação

**Output:**
```json
{
  "approved": true,
  "usefulness_score": 0.85,
  "justification": "Implementação específica e reusável"
}
```

### 2. KnowledgeFeedbackIndexer

Indexa respostas aprovadas no vector database reutilizando a infraestrutura existente.

**Processamento:**
- Gera ID único: `feedback_<timestamp>_<hash>`
- Cria texto combinado: "Question: ...\n\nAnswer: ...\n\nSummary: ..."
- Gera embedding usando provider configurado
- Indexa com metadata: `source_type="knowledge_feedback"`
- Salva metadata em SQLite

### 3. KnowledgeFeedbackProcessor

Orquestra pipeline assíncrono sem bloquear resposta do usuário.

```python
processor = KnowledgeFeedbackProcessor()

# Assíncrono (padrão)
processor.process_async(
    question="Como implementar JWT?",
    response="Use PyJWT...",
    search_results=results,
    context=context
)

# Síncrono (para testes)
result = processor.process_sync(
    question="Como implementar JWT?",
    response="Use PyJWT..."
)
# → {"approved": True, "evaluated": True, "indexed": True, "score": 0.85}
```

## Configurações

Adicione ao `.env`:

```bash
# Knowledge Feedback Configuration
KNOWLEDGE_FEEDBACK_ENABLED=True
KNOWLEDGE_FEEDBACK_MIN_USEFULNESS_SCORE=0.7
KNOWLEDGE_FEEDBACK_MAX_RETRIEVAL_RESULTS=3
KNOWLEDGE_FEEDBACK_ASYNC_PROCESSING=True
KNOWLEDGE_FEEDBACK_EVALUATOR_MAX_TOKENS=256
KNOWLEDGE_FEEDBACK_SCORE_MULTIPLIER=1.5
```

### Parâmetros

| Config | Default | Descrição |
|--------|---------|-----------|
| `knowledge_feedback_enabled` | `True` | Ativa/desativa feature |
| `knowledge_feedback_min_usefulness_score` | `0.7` | Score mínimo para salvar |
| `knowledge_feedback_max_retrieval_results` | `3` | Máx respostas feedback no retrieval |
| `knowledge_feedback_async_processing` | `True` | Usar threading assíncrono |
| `knowledge_feedback_evaluator_max_tokens` | `256` | Tokens máx para LLM avaliar |
| `knowledge_feedback_score_multiplier` | `1.5` | Boost de score para feedback |

## Integração no RAG Pipeline

Automático - nenhuma mudança necessária no código existente:

```python
from fs_rag.rag import get_rag_pipeline

pipeline = get_rag_pipeline()
response = pipeline.answer_question("Qual é a melhor prática?")

# Resposta retorna imediatamente
# Avaliação e indexação ocorrem em background
```

## Integração no Search

O `HybridSearchEngine` agora busca respostas retroalimentadas automaticamente:

```python
from fs_rag.search import HybridSearchEngine

search = HybridSearchEngine()

# Busca combina agora:
# 1. Documentos normais (keyword + semantic)
# 2. Respostas retroalimentadas (com boost de score)
results = search.hybrid_search("Como implementar JWT?", top_k=5)
```

**Score Boosting:**
- Respostas retroalimentadas recebem multiplicador `knowledge_feedback_score_multiplier` (default: 1.5x)
- Isso garante que conhecimento acumulado tenha prioridade maior

## Exemplo Prático

### Primeira pergunta (gera feedback)
```
User: Como implementar autenticação JWT em Python?

System: [resposta completa com detalhes técnicos]
        [LLM avalia: score=0.89 - APROVADA]
        [Resposta indexada como knowledge_feedback]
```

### Segunda pergunta similar (reutiliza feedback)
```
User: Qual é a forma correta de usar JWT com FastAPI?

Search Results:
  1. [Knowledge Feedback] "Question: Como implementar autenticação JWT..."
     Score: 0.78 (1.5x boost) ← Encontrada como feedback!
  
  2. [Document] "JWT best practices..."
     Score: 0.62

System: [usa a resposta anterioraprovada como contexto adicional]
        [resposta melhora porque inclui exemplo real anterior]
```

## Dados Persistidos

### Vector Database
Cada feedback salvo tem:
- `id`: `feedback_20260515094530_a1b2c3d4`
- `document`: Texto combinado (pergunta + resposta + resumo)
- `metadata`:
  - `source_type`: `"knowledge_feedback"`
  - `original_question`: Pergunta original
  - `usefulness_score`: Score do evaluator
  - `summary`: Resumo da resposta
  - `source_documents`: Documentos originais usados

### SQLite (index.db)
Tabela `feedback_responses`:
```sql
CREATE TABLE feedback_responses (
    id TEXT PRIMARY KEY,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    summary TEXT,
    usefulness_score REAL NOT NULL,
    embedding_id TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    source_type TEXT DEFAULT 'knowledge_feedback'
)
```

## Gestão e Monitoramento

### Ver respostas retroalimentadas salvos

```python
import sqlite3
from pathlib import Path
from fs_rag.core import get_config

config = get_config()
db_path = config.index_dir / "index.db"

conn = sqlite3.connect(db_path)
cursor = conn.execute("""
    SELECT id, question, usefulness_score, created_at 
    FROM feedback_responses 
    ORDER BY created_at DESC 
    LIMIT 10
""")

for row in cursor:
    print(f"ID: {row[0]}")
    print(f"Question: {row[1][:100]}")
    print(f"Score: {row[2]}")
    print(f"Created: {row[3]}\n")

conn.close()
```

### Deletar feedback específico

```python
from fs_rag.core.vector_db import get_vector_db
import sqlite3

# Vector DB
vector_db = get_vector_db()
vector_db.delete(ids=["feedback_20260515094530_a1b2c3d4"])

# SQLite
conn = sqlite3.connect(config.index_dir / "index.db")
conn.execute("DELETE FROM feedback_responses WHERE id = ?", 
             ("feedback_20260515094530_a1b2c3d4",))
conn.commit()
conn.close()
```

## Logs

O sistema registra todas as ações:

```
INFO | Processing feedback for question: Como implementar...
DEBUG | Step 1: Evaluating response...
INFO | Response rejected by evaluator (score: 0.45). Reason: Too generic
```

```
INFO | Processing feedback for question: Qual é a melhor...
INFO | Successfully processed feedback response (score: 0.87)
```

## Desabilitar Feature

Simples desabilitar no `.env`:

```bash
KNOWLEDGE_FEEDBACK_ENABLED=False
```

Nenhuma resposta será avaliada ou indexada, mas o sistema continua funcionando normalmente.

## Troubleshooting

### "Avaliação não está ocorrendo"
- Verifique `KNOWLEDGE_FEEDBACK_ENABLED=True`
- Verifique logs: `KNOWLEDGE_FEEDBACK_ASYNC_PROCESSING` pode estar False
- Confirme que LLM (Ollama/OpenAI) está acessível

### "Respostas feedback não aparecem no search"
- Verifique vector database (ChromaDB/Qdrant) está funcionando
- Confirme tabela `feedback_responses` existe em SQLite
- Verifique `KNOWLEDGE_FEEDBACK_MAX_RETRIEVAL_RESULTS > 0`

### "Score multiplier não está sendo aplicado"
- Verifique `KNOWLEDGE_FEEDBACK_SCORE_MULTIPLIER` value
- Confirme `source_type="knowledge_feedback"` está sendo setado

## Arquitetura de Reutilização

✅ **Infraestrutura Existente:**
- Vector DB (ChromaDB/Qdrant) - reutilizado
- Embeddings (Ollama/OpenAI) - reutilizado
- LLM Providers - reutilizado
- SQLite index.db - estendido com nova tabela
- HybridSearchEngine - estendido com novo search method
- System Instructions pattern - reutilizado

✅ **Zero Duplicação:**
- Sem novo vector DB
- Sem novos providers
- Sem novo sistema de config

## Próximos Passos (Opcional)

1. **Feedback de Usuário Manual**: Interface para usuários aprovarem/rejeitar respostas
2. **Decay de Scores**: Reduzir score de feedback muito antigo
3. **Deduplicação**: Detectar respostas duplicadas para não indexar múltiplas vezes
4. **Export**: Exportar feedback para usar em fine-tuning de modelos
5. **Analytics**: Dashboard com estatísticas de feedback
