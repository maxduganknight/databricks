# Recruiter Chatbot — Databricks Apps + DABs Demo

AI-powered recruiter assistant deployed as a Databricks App using **Databricks Asset
Bundles (DABs)** and **GitHub Actions CI/CD**. Demonstrates best practices for
multi-contributor app deployment.

## Architecture

```
.github/workflows/
  ci.yml          ← Lint + test on every PR
  deploy.yml      ← Bundle deploy on release

databricks.yml    ← DABs bundle config (dev + prod targets)
resources/app.yml ← App resource definition

src/app/
  app.py          ← Streamlit recruiter chatbot (Foundation Model API)
  app.yaml        ← App manifest
  tests/          ← Unit tests
```

## Why DABs for Apps?

When multiple developers deploy via the CLI:
```
databricks apps deploy my-app --source-code-path /Workspace/Users/<email>/...
```
The source path changes per developer, creating conflicts. **DABs solves this** by
defining the app as a resource with a relative `source_code_path` in `databricks.yml`.
CI/CD deploys from a single stable path.

## Deploy from Git Repository (Beta)

As an alternative to DABs, Databricks now supports **deploying Apps directly from a
Git repository** (Beta). This means you can point your app at a GitHub/GitLab/Bitbucket
repo and deploy from a branch, tag, or commit SHA — no workspace files needed.

See: [Deploy from a Git repository](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/deploy#deploy-from-a-git-repository)

**How it works:**
1. Create or select an app in **Compute > Apps**
2. Enter your Git repository URL
3. For private repos, configure a Git credential on the app's service principal
4. Click Deploy > "From Git" > specify branch/tag/commit

This is especially useful for teams that want zero workspace coupling — the app source
lives entirely in Git and deployments reference Git refs directly.

## Local Development

```bash
# Set up
python -m venv .venv && source .venv/bin/activate
pip install -r src/app/requirements.txt

# Validate bundle
databricks bundle validate

# Deploy to dev
databricks bundle deploy -t dev
databricks bundle run recruiter-chatbot -t dev
```

## CI/CD Setup (GitHub Actions)

Add these secrets to your GitHub repo → Settings → Secrets:
- `DATABRICKS_HOST` — workspace URL
- `DATABRICKS_CLIENT_ID` — service principal client ID
- `DATABRICKS_CLIENT_SECRET` — service principal secret

Then: create a GitHub Release to trigger production deployment.
# app_cicd_demo
