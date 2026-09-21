# Deploying on Vercel

LocalPulse AI's Flask app (`web/app.py`) is Vercel-deployable as a single
Python serverless function. Every route — `/`, `/api/*`, `/static/*` — is
routed by `vercel.json` to `api/index.py`, which exposes the Flask app as a
WSGI callable (`app` / `vercel_app`).

## Prerequisites

- The repo is pushed to GitHub (`https://github.com/Himal-Badu/Leadgen-AI`).
- You have a Vercel account (free tier is fine).

## Deploy steps

1. **Push `main` to GitHub**

   ```bash
   git checkout main
   git pull origin main
   git push origin main
   ```

2. **Import the repo in Vercel**

   - New project → **Import Git Repository** → pick `Himal-Badu/Leadgen-AI`.
   - **Framework Preset:** *Other* (Python/Flask — Vercel auto-detects
     `vercel.json` and the `api/` directory).
   - **Root Directory:** `/`
   - Vercel reads `vercel.json`: all routes go to `api/index.py` (Python 3.12).

3. **Set environment variables** (Project → Settings → Environment Variables):

   | Variable              | Required | Notes                                                        |
   | --------------------- | -------- | ------------------------------------------------------------ |
   | `STRIPE_SECRET_KEY`   | no*      | Stripe secret key (test or live). Needed for checkout.       |
   | `STRIPE_WEBHOOK_SECRET` | no*    | Stripe webhook signing secret.                               |
   | `RESEND_API_KEY`      | no*      | Resend key for transactional email (snapshot reports).       |
   | `DATA_DIR`            | yes      | Writable path for the local SQLite fallback store, e.g. `/tmp/lp-data` (Vercel uses an ephemeral filesystem per instance). |
   | `DATABASE_URL`        | optional | Accepted for future managed storage; without the team-db CLI the app falls back to local SQLite and never crashes. |

   \* The app imports cleanly without them — endpoints that need the key
   return a clear error instead of crashing.

4. **Deploy**

   Click **Deploy**. Vercel runs the Python build (installs `requirements.txt`)
   and exposes the app at your `*.vercel.app` URL.

## What works after deploy

- `GET /` — landing page (with `/static/*` assets served by Flask).
- `POST /api/request-report` — creates a snapshot (local SQLite under `DATA_DIR`)
  and sends the welcome email when `RESEND_API_KEY` is set.
- `GET /api/health` — health check.
- Stripe checkout + webhook endpoints when Stripe keys are configured.

## Limitations on serverless

- The Flask app is stateless: the local SQLite fallback lives on an ephemeral
  instance filesystem (Vercel may recycle it). Use it for demos and
  light-traffic launches; wire `DATABASE_URL` to a managed store for durable
  persistence.
- Long-running pipeline jobs (Scout → Analyzer → Scorer → Strategist →
  Builder) are skipped on serverless runtimes (`PIPELINE_AVAILABLE=False`) to
  respect the 30s `maxDuration`; the API still works end-to-end for lead
  capture.