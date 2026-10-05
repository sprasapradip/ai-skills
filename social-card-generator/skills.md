---
name: social-card-generator
description: Generates OpenGraph (OG) preview images, GitHub header cards, and SVG badges for open-source repositories and blog posts.
triggers:
  - "create an og social card"
  - "generate github banner image"
  - "build an svg preview card"
---

# Social Card Generator Skill

## Overview
Produces eye-catching, high-resolution OpenGraph preview images (1200x630px) and SVG repository headers designed to increase click-through rates on Twitter/X, LinkedIn, and GitHub.

## Design Specifications
- **Standard Dimensions**: 1200 x 630 pixels (standard 1.91:1 aspect ratio for OG images).
- **Visual Hierarchy**:
  - **Category / Badge**: Small uppercase tag (e.g., `OPEN SOURCE`, `AI SKILL`, `PYTHON`).
  - **Main Title**: Bold, high-contrast typography (48-64pt).
  - **Subtitle / Tagline**: Brief description (24-32pt, 60% opacity or secondary color).
  - **Brand Footer**: Logo icon, author/repo handle, website URL.
- **Color Theme**: Dark mode gradient background (e.g., slate/indigo/cyan) with high-contrast text.

## Execution Workflow
1. **Extract Metadata**: Project title, tagline, topic tags, brand colors.
2. **Generate SVG or Python Plot**: Render visually appealing card using SVG vector paths or Python PIL/matplotlib.
3. **Output File**: Export high-quality SVG or PNG artifact for immediate use in repository headers or HTML meta tags.