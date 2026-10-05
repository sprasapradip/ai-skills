---
name: pdf-maker
description: Converts Markdown notes, structured JSON, or text documents into styled, publication-ready PDF files using Python scripts.
triggers:
  - "generate a pdf report"
  - "convert markdown to pdf"
  - "create a formatted pdf document"
---

# PDF Maker Skill

## Overview
Automates the compilation of raw markdown or text content into styled, print-ready PDF files with headers, page numbering, tables, and clean typography.

## Workflow
1. **Content Parsing**: Parse source Markdown or JSON into semantic structures (headings, paragraphs, lists, code blocks, tables).
2. **Script Generation**: Produce a python script using standard, lightweight PDF rendering libraries (such as `fpdf2` or `reportlab`).
3. **Styling Guidelines**:
   - **Page Setup**: Standard Letter/A4 layout with balanced margins (0.75 in / 20mm).
   - **Typography**: Clear hierarchy (Title: 24pt bold, H1: 18pt bold, H2: 14pt bold, Body: 10-11pt regular).
   - **Header/Footer**: Page numbers (`Page X of Y`), document title, and horizontal rule dividers.
   - **Tables**: Striped rows, bold headers, auto-wrapped text cells.
   - **Code Blocks**: Fixed-width font (Courier) with light grey background shading.
4. **Execution & Delivery**: Run script in environment, verify generated `.pdf` artifact size and layout completeness.