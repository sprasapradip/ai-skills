# AI Skills: Premium Agent Skill Pack

Ten premium agent skills by **Pradip Subedi ([@sprasapradip](https://github.com/sprasapradip))** for Claude Code and any agent that can follow a Markdown instruction file (Cursor, Gemini CLI and others). Each skill ships a three-tier workflow (Starter, Pro, Enterprise), strict input validation, design and quality standards, explicit NEVER rules, and zero-dependency scripts that check the output offline.

## Table of Contents

<!-- toc -->
- [Features](#features)
- [Installation](#installation)
- [Usage](#usage)
- [Skill anatomy](#skill-anatomy)
- [Development](#development)
- [Contributing](#contributing)
- [License](#license)
- [Author](#author)
<!-- tocstop -->

## Features

| Skill | What it produces | Offline gates (`scripts/`) |
|---|---|---|
| [`landing-page-builder`](landing-page-builder/SKILL.md) | Single-file landing page (HTML/CSS/JS) | `audit_html.py`: accessibility, light/dark contrast, SEO, Open Graph, JSON-LD, script safety |
| [`portfolio-maker`](portfolio-maker/SKILL.md) | Personal portfolio site and validated `profile.json` | `validate_profile.py`, `audit_html.py` |
| [`pdf-maker`](pdf-maker/SKILL.md) | Styled, paginated PDF from Markdown or JSON | `md_to_pdf.py` (stdlib PDF engine), `verify_pdf.py` |
| [`social-card-generator`](social-card-generator/SKILL.md) | Open Graph, GitHub and square cards (SVG + PNG) | `render_card.py`, `validate_svg.py`, `svg_to_png.sh` |
| [`code-cleaner`](code-cleaner/SKILL.md) | Behaviour-preserving refactors (Python, PHP, JS, TS) | `scan_smells.py` (+ `--compare` gate), `syntax_check.sh` |
| [`text-humanizer`](text-humanizer/SKILL.md) | Natural rewrites with every fact preserved | `ai_tells.py scan` / `suggest --fix` / `compare` |
| [`seo-blog-writer`](seo-blog-writer/SKILL.md) | SEO articles that pass an SEO gate **and** the humanizer | `seo_check.py` (+ FAQ JSON-LD), `ai_tells.py` |
| [`readme-generator`](readme-generator/SKILL.md) | Verified GitHub READMEs with generated table of contents | `readme_lint.py` (`--toc`, `--write-toc`) |
| [`email-template-builder`](email-template-builder/SKILL.md) | Responsive HTML email for Gmail, Outlook and Apple Mail, with dark mode | `email_lint.py` |
| [`resume-builder`](resume-builder/SKILL.md) | ATS-friendly resumes tailored to a job description | `ats_check.py` (+ PDF via `pdf-maker`) |

## Installation

Requirements: Python 3.8+ and a POSIX shell. Nothing to `pip install`.

```bash
git clone https://github.com/sprasapradip/ai-skills.git
cd ai-skills
sh install.sh                              # all skills -> ~/.claude/skills
sh install.sh --project ~/code/my-app      # one project -> ~/code/my-app/.claude/skills
sh install.sh text-humanizer seo-blog-writer   # only selected skills
```

## Usage

Ask in plain language. Claude loads the matching skill from the trigger phrases in its `description`:

```text
Write an SEO blog post about Laravel queue workers for intermediate developers
Humanize this article but keep every number and link
Tailor my resume to this job description
```

Every script also runs on its own:

```bash
python3 text-humanizer/scripts/ai_tells.py suggest draft.md --fix draft.safe.md
python3 seo-blog-writer/scripts/seo_check.py post.md --tier pro --site example.org
python3 email-template-builder/scripts/email_lint.py welcome.html --type marketing --allow-vars
```

For other agents, point the agent's rules or context file (a Cursor rule or `GEMINI.md`) at the relevant `SKILL.md`, and keep its `scripts/` folder next to it.

## Skill anatomy

```text
<skill>/
├── SKILL.md      # frontmatter: name, description + triggers, version, tier: premium, author
│                 # 1 Role & Objective · 2 Mode Selection · 3 Pre-Flight Validation
│                 # 4 Core Execution Workflow · 5 Design / Output Standards
│                 # 6 Automation Scripts · 7 Negative Constraints · 8 Production Checklist
└── scripts/      # stdlib-only CLIs: exit 0 = pass, 1 = gate failed, 2 = usage/IO error
```

These scripts exist in two skills so each folder installs on its own. CI fails if the copies drift apart:

- `audit_html.py` is in `landing-page-builder` (the canonical copy) and `portfolio-maker`.
- `ai_tells.py` is in `text-humanizer` (the canonical copy) and `seo-blog-writer`.

## Development

```bash
python3 scripts/validate_skills.py   # lint every SKILL.md, script headers and shared copies
sh tests/run_all.sh                  # end-to-end gate tests against tests/fixtures/
```

CI (`.github/workflows/validate.yml`) runs both on Python 3.8 and 3.12.

## Contributing

Issues and pull requests are welcome. Run both commands above before opening a PR, and keep every script on the Python standard library.

## License

No license file has been added yet, so all rights are reserved by the author until one is chosen.

## Author

**Pradip Subedi** ([@sprasapradip](https://github.com/sprasapradip)), electrical engineering student and PHP/Laravel and WordPress developer from Nepal.
