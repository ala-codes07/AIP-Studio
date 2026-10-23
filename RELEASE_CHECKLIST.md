# AIP Studio — GitHub release checklist

This checklist is for publishing the **source code**. A public GitHub repository is **not** a publicly hosted or security-audited SaaS service.

## 1. Smoke tests on the intended release machine

From `AIP-Studio-Final` on Windows PowerShell:

```powershell
cd .\backend
.\.venv\Scripts\python.exe -m pytest -q
cd ..
node --check .\frontend\app.js
```

Both commands should exit successfully. If Node is unavailable, install Node or rely on the GitHub Actions JavaScript check; do **not** claim you ran it locally.

Manual acceptance checks: register and verify email, password recovery (old password fails), create and access a workspace, scan an authorized public site, view its report, import a GSC Queries CSV, and confirm Insights loads. Mark both successful cases **and known limits** in the public README.

## 2. Secrets and private data

Never upload `.env`, any database, real GSC exports, mail credentials, logs, private screenshots, backup archives, tokens or API keys. `.env.example` contains only placeholders. Scrutinize the staged file list before committing.

```powershell
git init
git add .
git status --short
git diff --cached --name-only
```

Stop if **any sensitive or unknown file** appears in the staging list. Remove it from staging with `git restore --staged <path>` and add an ignore rule before proceeding. If secrets were *ever committed*, simply adding `.gitignore` is insufficient: rotate the secrets and remove the exposure from the history.

## 3. Publish the repository

Create an **empty** repository on GitHub (e.g., `aip-studio`), without generating an initial README or license in the GitHub UI. Then use the HTTPS repository address provided by GitHub:

```powershell
git commit -m "Initial AIP Studio release"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/aip-studio.git
git push -u origin main
```

GitHub sign-in/authorization may be required. If Git complains that the author is unknown, configure `git config --global user.name` and `git config --global user.email` with the identity you want on public commits.

## 4. Final presentation and truthfulness

- Check GitHub Actions is green. If red, fix that failure before declaring release complete.
- Add an unedited screenshot of the actual running application (redact account email, user data, and proprietary client data). Screenshots made with illustrative data should be labeled **demo**, not real search traffic.
- Explain that SEO scoring is heuristic, crawling is bounded, GSC evidence is a user-uploaded CSV and not a live OAuth integration, and generative AI requires separately installed Ollama.
- Do not claim 10/10 SEO accuracy, measured search volume, SERP position beyond imported evidence, full Core Web Vitals, or audited production security.
- Share the GitHub repo + a 60–90-second demo on LinkedIn. This does not require a paid host or followers.

## 5. Hosting is a separate, later decision

Before offering the crawler to anonymous internet users, address HTTPS, PostgreSQL, per-IP rate limits, outbound network controls, email sender policy, abuse prevention, backups, monitoring, privacy notices and independent security review. The local Windows server is **not** a production hosting setup.
