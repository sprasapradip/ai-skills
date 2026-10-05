---
name: portfolio-maker
description: Creates sleek, personalized developer or professional portfolio websites from raw resumes, JSON profiles, or plain text descriptions.
triggers:
  - "build a portfolio for me"
  - "create a developer portfolio website"
  - "make a portfolio page from my resume"
---

# Portfolio Maker Skill

## Overview
This skill turns raw career history, GitHub profiles, or text resumes into a clean, modern, responsive portfolio page designed to highlight technical skills, featured projects, and contact info.

## Key Components
- **Hero Bio**: Personal tagline, role title, dynamic headline, and social links (GitHub, LinkedIn, Email).
- **About Me**: Narrative summary highlighting core expertise, years of experience, and philosophy.
- **Skills Matrix**: Categorized tags (Languages, Frameworks, Cloud/DevOps, AI/ML Tools).
- **Featured Projects Grid**: Interactive project cards with tech tags, summary, GitHub links, and live demo buttons.
- **Work Experience Timeline**: Structured career chronology with key metrics and achievements.
- **Contact Card**: Interactive contact form mockup and email trigger.

## Execution Rules
1. **Input Ingestion**: Extract experience, projects, skills, and contact links from user input.
2. **Responsive Styling**:
   - Dark mode default or auto dark/light toggle using CSS `prefers-color-scheme`.
   - Subtle entrance animations using CSS keyframes and `IntersectionObserver`.
3. **Clean Code Protocol**:
   - No heavy external JavaScript framework dependencies — use vanilla JS.
   - Clean SVG icons for social platforms and skill badges.
4. **Output Format**: Standalone HTML file ready to deploy on GitHub Pages, Vercel, or Netlify.