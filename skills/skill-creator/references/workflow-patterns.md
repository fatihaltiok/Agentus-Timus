# Workflow Patterns

Common patterns for multi-step processes in skills.

---

## Pattern 1: Sequential Workflow

**Wann:** Schritte müssen in Reihenfolge ausgeführt werden

```markdown
## Workflow

### Step 1: Prepare
1. Check prerequisites
2. Load resources
3. Validate input

### Step 2: Process
1. Execute main operation
2. Monitor progress
3. Handle errors

### Step 3: Finalize
1. Save results
2. Clean up
3. Report status
```

---

## Pattern 2: Conditional Workflow

**Wann:** Verschiedene Pfade basierend auf Bedingungen

```markdown
## Decision Tree

**IF** condition A:
- Path A1: Do X
- Path A2: Do Y

**ELSE IF** condition B:
- Path B: Do Z

**ELSE**:
- Default path

### Error Handling
- **On failure**: Rollback und Retry
- **On timeout**: Cleanup und Alert
```

---

## Pattern 3: Iterative Workflow

**Wann:** Wiederholte Operationen bis Goal erreicht

```markdown
## Iteration Loop

### Initialize
- Set counter = 0
- Set max_iterations = 10

### Loop
WHILE not complete AND counter < max_iterations:
1. Attempt operation
2. Check result
3. IF success: mark complete
4. ELSE: increment counter, adjust parameters

### Completion
- IF complete: Return result
- ELSE: Report failure with logs
```

---

## Pattern 4: Parallel Workflow

**Wann:** Unabhängige Tasks können parallel laufen

```markdown
## Parallel Execution

### Phase 1: Setup
- Prepare Task A
- Prepare Task B
- Prepare Task C

### Phase 2: Execute (Parallel)
RUN concurrently:
- Task A (timeout: 30s)
- Task B (timeout: 60s)
- Task C (timeout: 30s)

### Phase 3: Collect
- Gather results from A, B, C
- Combine outputs
- Handle partial failures
```

---

## Pattern 5: State Machine

**Wann:** Komplexe Zustandsübergänge

```markdown
## States

### IDLE
- Wait for trigger
- On trigger → PROCESSING

### PROCESSING
- Execute operation
- On success → COMPLETED
- On error → ERROR
- On timeout → TIMEOUT

### COMPLETED
- Save results
- Notify user
- Return to IDLE

### ERROR
- Log error details
- Attempt recovery
- IF recovered → PROCESSING
- ELSE → FAILED

### FAILED
- Report failure
- Cleanup resources
- Return to IDLE
```

---

## Best Practices für Workflows

1. **Always include error handling**
2. **Set timeouts** für lange Operationen
3. **Include cleanup** in finally-Block
4. **Log intermediate states** für Debugging
5. **Validate inputs** vor dem Start
6. **Check preconditions** in jedem Schritt
