# Skill Best Practices

Basierend auf OpenClaw Guidelines.

---

## 1. Concise is Key

**"The context window is a public good."**

Skills teilen sich den Context mit:
- System Prompt
- Conversation History
- Andere Skills
- User Request

**Challenge jedes Element:**
- "Does Codex really need this explanation?"
- "Does this justify its token cost?"

**Lieber konkrete Beispiele als ausführliche Erklärungen.**

---

## 2. Degrees of Freedom

Match Specificity to Fragility:

| Freedom | Wann | Beispiel |
|---------|------|----------|
| **High** | Multiple approaches valid | Text instructions |
| **Medium** | Preferred pattern exists | Pseudocode |
| **Low** | Fragile operations, consistency critical | Specific scripts |

**Analogy:**
- Narrow bridge with cliffs → Low freedom (specific guardrails)
- Open field → High freedom (many routes possible)

---

## 3. Progressive Disclosure

Drei-Ebenen-System:

```
┌─────────────────────────────────────┐
│  Level 1: Metadata                  │  ← Always loaded (~100 words)
│  (name, description)                │
├─────────────────────────────────────┤
│  Level 2: SKILL.md Body             │  ← On trigger (<5k words)
│  (Instructions)                     │
├─────────────────────────────────────┤
│  Level 3: Bundled Resources         │  ← On demand (unlimited)
│  (scripts/, references/, assets/)     │
└─────────────────────────────────────┘
```

---

## 4. What NOT to Include

**Keine Extraneous Documentation:**
- ❌ README.md
- ❌ INSTALLATION_GUIDE.md
- ❌ QUICK_REFERENCE.md
- ❌ CHANGELOG.md
- ❌ etc.

**Nur essentielle Files für die Funktionalität!**

---

## 5. Reference Patterns

### Pattern 1: High-Level mit References

```markdown
## Quick start
Extract text with pdfplumber: [code example]

## Advanced features
- **Form filling**: See [FORMS.md](FORMS.md)
- **API reference**: See [REFERENCE.md](REFERENCE.md)
```

### Pattern 2: Domain-Specific

```
bigquery-skill/
├── SKILL.md (overview)
└── reference/
    ├── finance.md
    ├── sales.md
    └── marketing.md
```

### Pattern 3: Conditional Details

```markdown
## Creating documents
Use docx-js for new documents. See [DOCX-JS.md](DOCX-JS.md).

**For tracked changes**: See [REDLINING.md](REDLINING.md)
**For OOXML details**: See [OOXML.md](OOXML.md)
```

---

## 6. Writing Guidelines

**Always use imperative/infinitive form:**
- ✅ "Create a new file"
- ✅ "Extract the text"
- ❌ "You should create..."
- ❌ "We need to extract..."

**Frontmatter Description:**
- Include "what it does" AND "when to use"
- Include ALL trigger contexts
- NO "When to Use" sections in Body (wird nie gelesen vor Trigger!)

---

## 7. Testing

**Scripts MUST be tested:**
- Actually run them before bundling
- Ensure no bugs
- Output matches expectations

**Skill Test:**
- Try skill on real tasks
- Notice struggles
- Iterate
