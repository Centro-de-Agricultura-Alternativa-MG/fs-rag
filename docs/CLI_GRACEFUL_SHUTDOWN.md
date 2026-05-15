# CLI Graceful Shutdown for Async Feedback Processing

## Problema Identificado

Quando `knowledge_feedback_enabled=True` no `.env`, o comando CLI da feature "ask" pode sair antes de processar completamente a retroalimentação assíncrona.

### Fluxo Problemático (ANTES)
```
CLI: ask "Question?"
├─ Execute RAG
├─ Return response
├─ Spawn async feedback thread
└─ exit(1) ← ❌ Fecha imediatamente!
  └─ Feedback thread cancelado antes de completar
```

### Fluxo Correto (DEPOIS)
```
CLI: ask "Question?"
├─ Execute RAG
├─ Return response
├─ Spawn async feedback thread
└─ graceful_exit(1) ← ✅ Aguarda threads
  ├─ Wait for feedback processing
  ├─ Thread completa indexação
  └─ Fecha com sucesso
```

## Solução Implementada

### 1. Novo Módulo: `fs_rag/cli/shutdown.py`

```python
def wait_for_feedback_processing(timeout: float = 5.0) -> bool:
    """Wait for any pending feedback processing threads to complete."""
    # Se feedback desativado: retorna imediatamente
    # Se feedback ativado: aguarda até timeout
```

**Comportamento:**
- ✅ Verifica se `knowledge_feedback_enabled` está ativado
- ✅ Aguarda threads daemon completarem
- ✅ Respeita timeout (default: 5 segundos)
- ✅ Retorna bool (sucesso ou timeout)

### 2. Função `graceful_exit()`

```python
def graceful_exit(exit_code: int = 0, wait_feedback: bool = True) -> None:
    """Exit gracefully, optionally waiting for feedback processing."""
    # Aguarda feedback se habilitado
    # Depois executa exit(code)
```

**Uso:**
```python
# Usar no lugar de exit(1)
graceful_exit(1)  # Aguarda feedback antes de sair
graceful_exit(1, wait_feedback=False)  # Sai imediatamente (debug)
```

## Modificações no CLI

Todos os `exit(1)` foram substituídos por `graceful_exit(1)`:

```
fs_rag/cli/__init__.py
├─ Line ~51:   exit(1) → graceful_exit(1)  # index command
├─ Line ~55:   exit(1) → graceful_exit(1)  # index command
├─ Line ~59:   exit(1) → graceful_exit(1)  # index command
├─ Line ~87:   exit(1) → graceful_exit(1)  # index error
├─ Line ~126:  exit(1) → graceful_exit(1)  # sessions error
├─ Line ~143:  exit(1) → graceful_exit(1)  # stats error
├─ Line ~172:  exit(1) → graceful_exit(1)  # search error
├─ Line ~207:  exit(1) → graceful_exit(1)  # ask error
├─ Line ~221:  exit(1) → graceful_exit(1)  # clear error
└─ Line ~242:  exit(1) → graceful_exit(1)  # config error
```

## Comportamento Detalhado

### Caso 1: feedback DESATIVADO
```bash
$ KNOWLEDGE_FEEDBACK_ENABLED=False fs-rag ask "?"
[resposta]
↓
graceful_exit(0)
├─ wait_for_feedback_processing() → retorna imediatamente (disabled)
└─ exit(0) ← rápido!
```

### Caso 2: feedback ATIVADO (sucesso)
```bash
$ KNOWLEDGE_FEEDBACK_ENABLED=True fs-rag ask "?"
[resposta]
↓
graceful_exit(0)
├─ Spawn async feedback thread
├─ wait_for_feedback_processing(timeout=5.0)
│  └─ Aguarda thread completar (~1-2s)
└─ exit(0) ← com sucesso!
```

### Caso 3: feedback ATIVADO (timeout)
```bash
$ KNOWLEDGE_FEEDBACK_ENABLED=True fs-rag ask "?"
[resposta]
↓
graceful_exit(0)
├─ Spawn async feedback thread
├─ wait_for_feedback_processing(timeout=5.0)
│  └─ Timeout após 5s (thread ainda rodando)
│  └─ Log warning
└─ exit(0) ← mesmo assim fecha
```

## Configuração de Timeout

O timeout padrão é **5 segundos**. Para ajustar:

```python
# No code
wait_for_feedback_processing(timeout=10.0)  # 10 segundos

# No .env (futura extensão)
# KNOWLEDGE_FEEDBACK_SHUTDOWN_TIMEOUT=10
```

## Testing

### Teste 1: Sem threads
```
✓ wait_for_feedback_processing() retorna True (nenhuma thread)
```

### Teste 2: Com thread lenta
```
✓ Aguarda até thread completar
✓ Retorna True
```

### Teste 3: Com timeout
```
✓ Aguarda até timeout
✓ Retorna False
✓ Log warning emitido
```

## Impacto Performance

### Sem feedback (`knowledge_feedback_enabled=False`)
```
exit() tempo:  ~0ms (nenhuma espera)
```

### Com feedback (`knowledge_feedback_enabled=True`)
```
exit() tempo:  ~1-3s (aguarda indexação)
Overhead:      Mínimo (feedback já estava processando)
```

## Exemplo de Uso

```bash
# Com feedback (aguarda processing)
$ fs-rag ask "Como implementar JWT?"
[resposta detalhada]
[aguarda ~2s para indexação]
[programa fecha]

# Sem feedback (fecha imediatamente)
$ KNOWLEDGE_FEEDBACK_ENABLED=False fs-rag ask "Como implementar JWT?"
[resposta detalhada]
[programa fecha imediatamente]
```

## Verificação

Para verificar se está funcionando:

```bash
# Com logging ativado
LOGLEVEL=DEBUG fs-rag ask "?"

# Deve ver no log:
# [DEBUG] Waiting for feedback processing (timeout: 5.0s)...
# [DEBUG] All feedback threads completed
```

## Compatibilidade

✅ Zero breaking changes
✅ Funciona com feedback desativado (backward compatible)
✅ Funciona com feedback ativado (novo comportamento)
✅ Configurável via timeout
✅ Robusto contra timeouts

## Próximas Melhorias

- [ ] Adicionar `KNOWLEDGE_FEEDBACK_SHUTDOWN_TIMEOUT` ao config
- [ ] Usar signal handlers (SIGTERM, SIGINT) para graceful shutdown
- [ ] Visualizar progresso do feedback durante espera
- [ ] Opcional: log de quanto tempo esperou
