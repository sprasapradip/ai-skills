---
name: text-humanizer
description: Scrubs AI writing tells, repetitive transitions, and robotic phrasing from draft copy to produce natural, human-sounding text.
triggers:
  - "humanize this text"
  - "make this sound written by a human"
  - "remove ai tone from this article"
---

# Text Humanizer Skill

## Overview
This skill identifies and replaces common AI language patterns, overly formal syntax, and monotonous sentence structures to produce natural, engaging, authentic human copy.

## Target AI Patterns to Remove
- **Overused Buzzwords**: "delve", "tapestry", "testament", "pivotal", "crucial", "seamlessly", "spearhead", "beacon", "demystify", "fostering".
- **Formulaic Transitions**: "Furthermore,", "Moreover,", "In conclusion,", "It is worth noting that,", "In today's fast-paced digital world,".
- **Uniform Sentence Length**: AI tends to output sentences of equal character length. Introduce variation (mix punchy short sentences with longer compound ones).
- **Passive Over-Explanation**: Replace passive voice explanations with direct, active statements and relatable phrasing.

## Humanization Protocol
1. **Tone Assessment**: Identify intended context (friendly, professional, editorial, technical).
2. **Pattern Scrubbing**: Scan input for red-flag vocabulary and rigid transitional phrases.
3. **Sentence Rhythm Variation**: Restructure paragraphs to vary cadence. Insert rhetorical questions, em-dashes, or conversational turns where appropriate.
4. **Fact Preservation**: Ensure 100% of underlying facts, metrics, and core logic are preserved without addition or distortion.
5. **Output Diff**: Provide the polished humanized text followed by a brief summary of key phrasing changes made.