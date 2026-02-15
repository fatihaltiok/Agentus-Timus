---
name: skill-creator
description: Create or update Skills for Timus. Use when designing, structuring, or packaging skills with scripts, references, and assets. Use this skill when the user wants to create a new skill, modify an existing skill, or needs help with skill architecture.
version: 1.0.0
author: Timus System
tags: skills, creation, development, meta
---

# Skill Creator

This skill creates other skills (meta!).

## About

The skill-creator skill guides you through the complete process of creating a new Timus skill, from understanding requirements to packaging for distribution.

## When to Use This Skill

Use this skill when:
- User wants to create a new skill
- User needs help structuring a skill
- User wants to add scripts/references to a skill
- User needs to package a skill for distribution
- User asks about skill best practices

## Skill Creation Process

### Step 1: Understand with Concrete Examples

**Goal:** Clearly understand what the skill should do.

**Ask the user:**
1. "What should this skill do?"
2. "Can you give me 3 concrete examples of how it would be used?"
3. "What would a user say that should trigger this skill?"

**Don't overwhelm:** Ask 1-2 questions at a time, follow up as needed.

**Example:**
```
User: "Create a skill for PDF processing"
→ "What should it do? Extract text, merge PDFs, rotate pages?"
→ "Example 1: 'Extract text from this PDF'"
→ "Example 2: 'Merge these PDFs into one'"
```

### Step 2: Plan Resources

Analyze the concrete examples and plan resources:

**Scripts** (Python/Bash):
- When: Code is rewritten repeatedly OR deterministic reliability needed
- Example: `scripts/rotate_pdf.py` for PDF rotation
- Include: If same code pattern appears multiple times

**References** (Documentation):
- When: Schemas, API docs, policies needed
- Example: `references/schema.md` for database structure
- Include: Detailed docs, schemas, workflows, examples

**Assets** (Templates, Images):
- When: Boilerplate or resources needed for output
- Example: `assets/template.html` for web projects
- Include: Templates, fonts, images, sample files

### Step 3: Initialize Skill

**Tool:** `init_skill_tool`

**Usage:**
```json
{
  "method": "init_skill_tool",
  "params": {
    "name": "pdf-processor",
    "description": "Process PDF files for text extraction, rotation, and merging",
    "resources": ["scripts", "references"],
    "examples": true
  }
}
```

**This creates:**
```
skills/pdf-processor/
├── SKILL.md (with template)
├── scripts/ (with example.py if examples=true)
└── references/ (with REFERENCE.md if examples=true)
```

### Step 4: Edit SKILL.md

**Frontmatter (YAML):**
```yaml
---
name: pdf-processor
description: Process PDF files for: (1) text extraction, (2) rotation, 
             (3) merging. Use when working with PDF files.
---
```

**Key Rule:** Description goes in frontmatter, NOT in body!
- Frontmatter: Always loaded → Perfect for trigger keywords
- Body: Only on trigger → Don't put "When to Use" here

**Body (Markdown):**
```markdown
# PDF Processor

## Quick Start
Extract text with pdfplumber:
```python
import pdfplumber
with pdfplumber.open("doc.pdf") as pdf:
    text = pdf.pages[0].extract_text()
```

## Advanced Features
- **Form filling**: See [FORMS.md](references/FORMS.md)
- **API Reference**: See [API.md](references/API.md)
```

**Writing Guidelines:**
- Always use imperative/infinitive form
- ✅ "Extract the text"
- ❌ "You should extract..."
- Keep under 500 lines
- Be concise - context window is limited!

### Step 5: Add Scripts & References

**Create scripts:**
```python
# skills/pdf-processor/scripts/rotate_pdf.py
import PyPDF2

def rotate_pdf(input_path, output_path, rotation):
    with open(input_path, 'rb') as f:
        reader = PyPDF2.PdfReader(f)
        writer = PyPDF2.PdfWriter()
        
        for page in reader.pages:
            page.rotate(rotation)
            writer.add_page(page)
        
        with open(output_path, 'wb') as out:
            writer.write(out)

if __name__ == "__main__":
    import sys
    rotate_pdf(sys.argv[1], sys.argv[2], int(sys.argv[3]))
```

**Test scripts:**
- Actually run them before bundling
- Ensure no bugs
- Output matches expectations

**Create references:**
```markdown
# skills/pdf-processor/references/PDFLIB.md

## PyPDF2 API

### PdfReader
- `pages` - List of pages
- `getPage(n)` - Get specific page

### Page Methods
- `rotateClockwise(degrees)` - Rotate page
- `extract_text()` - Extract text content
```

### Step 6: Package Skill

**Tool:** `package_skill_tool` (coming soon)

**For now:**
- Validate: Check SKILL.md structure
- Test: Run on real examples
- Distribute: Copy skill folder

## Validation Checklist

Before completing, verify:

- [ ] YAML frontmatter valid?
- [ ] Name between 2-64 chars?
- [ ] Description > 10 chars, < 500 chars?
- [ ] Body > 50 chars?
- [ ] Scripts tested?
- [ ] References linked from SKILL.md?
- [ ] No extraneous files (README, etc.)?

## Progressive Disclosure

This skill uses the three-level system:

1. **Metadata** (this frontmatter) - Always loaded (~100 words)
2. **SKILL.md Body** - Loaded on trigger (this document, <5k words)
3. **References** - Loaded on demand:
   - `best-practices.md` - OpenClaw best practices
   - `workflow-patterns.md` - Common workflow patterns

## References

- **Best Practices**: See [best-practices.md](references/best-practices.md)
- **Workflow Patterns**: See [workflow-patterns.md](references/workflow-patterns.md)
