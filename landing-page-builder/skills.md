---
name: landing-page-builder
description: Generates clean, modern, single-file responsive landing pages (HTML/CSS/JS) with hero sections, feature grids, pricing, and CTA forms.
triggers:
  - "create a landing page"
  - "build a landing page for"
  - "generate a product landing page"
---

# Landing Page Builder Skill

## Overview
This skill guides the AI assistant in creating high-converting, accessible, and responsive single-file landing pages using standard HTML5, CSS3, and modern vanilla JavaScript.

## Core Directives
1. **Single-File Architecture**: Deliver the entire landing page in a self-contained `.html` file with embedded `<style>` and `<script>` blocks unless specified otherwise.
2. **Design Standards**:
   - Modern color palette using CSS variables (`:root`).
   - Clean typography (system font stack or Google Fonts integration like Inter/Roboto).
   - Fully responsive design using CSS Flexbox and Grid.
   - Mobile-first approach with collapsible navigation and fluid spacing.
3. **Key Sections Included by Default**:
   - **Header / Nav**: Brand logo, navigation links, primary Call to Action (CTA) button.
   - **Hero Section**: Catchy headline, descriptive subdeck, dual CTA buttons, visual placeholder or preview element.
   - **Features Grid**: 3 to 6 key feature cards with icons and descriptive copy.
   - **Social Proof / Testimonials**: Customer quotes, metrics/stats counter, or brand badges.
   - **Pricing Table**: Tiered pricing cards with highlight on recommended plan.
   - **CTA Banner**: Final high-converting prompt.
   - **Footer**: Essential links, copyright, and social media handles.

## Execution Steps
1. **Requirement Extraction**: Identify the product/service name, target audience, core value proposition, primary CTA, and desired color scheme.
2. **HTML Structure Drafting**: Build semantic HTML5 layout (`<header>`, `<main>`, `<section>`, `<footer>`).
3. **CSS Styling**: Apply CSS reset, custom utility classes, flex/grid layouts, smooth scrolling, and hover interactions.
4. **Interactivity**: Add lightweight JS for mobile navigation toggles, smooth scroll anchor links, and form validation mockups.
5. **Quality Review**: Check color contrast accessibility (WCAG AA), responsive breakpoints (`768px`, `1024px`), and fast load performance.