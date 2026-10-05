---
name: code-cleaner
description: Refactors draft or AI-generated code snippets into production-ready, idiomatic, clean, and well-structured code.
triggers:
  - "clean up this code"
  - "refactor code for production"
  - "make this code idiomatic"
---

# Code Cleaner Skill

## Overview
Eliminates code smell, redundant comments, deeply nested conditionals, and anti-patterns in AI-generated or draft code, returning clean, maintainable, production-ready code.

## Cleaning Directives
1. **Remove Comment Clutter**: Delete self-explanatory comments (e.g., `# increment i by 1`). Retain only non-obvious architecture or business logic explanations.
2. **Eliminate Dead Code**: Remove unused imports, dead variables, unreachable branches, and redundant function declarations.
3. **Enforce Language Idioms**:
   - **Python**: Enforce PEP 8 style, list comprehensions, context managers (`with`), explicit type hints.
   - **JavaScript/TypeScript**: Enforce ES6+ syntax, optional chaining (`?.`), nullish coalescing (`??`), strong typing without `any`.
4. **Flatten Control Flow**: Replace nested `if-else` blocks with guard clauses and early returns.
5. **Standardize Naming**: Apply clear, descriptive camelCase or snake_case naming based on language standards.

## Execution Process
1. Analyze raw code snippet for structure, bugs, and maintainability issues.
2. Apply refactoring rules systematically.
3. Return clean code followed by a bulleted summary of refactorings made.