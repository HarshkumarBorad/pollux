# Deploying Pollux to HuggingFace Spaces

A HuggingFace Space is its own Git repo (separate from the main `pollux`
GitHub repo). The flow:

1. Create an empty Space on huggingface.co.
2. Set the `HF_TOKEN` secret.
3. Clone the Space's Git repo locally.
4. Copy Pollux's source + the `spaces/` overrides in.
5. Push → HF builds the Docker image and starts the container.

Same flow as the DocuMind Space deploy — minus the per-namespace
ingestion step, since Pollux ingests sample knowledge automatically on
first container start.

---

## Prerequisites

- A free HuggingFace account.
- The `HF_TOKEN` you've been using locally
  ([huggingface.co/settings/tokens](https://huggingface.co/settings/tokens)
  — "Read" scope is enough; "Write" is only needed if you're going to
  push code from the Space's runtime, which Pollux doesn't).
- An HF access token with **Write** scope (different from `HF_TOKEN`) —
  for pushing to the Space's Git repo. Create at the same URL but pick
  "Write" type.

---

## Step 1 — create the Space

1. Open <https://huggingface.co/new-space>.
2. Fill in:
   - **Owner:** your HF username (e.g. `Harshborad`).
   - **Space name:** `pollux`.
   - **License:** MIT.
   - **Space SDK:** **Docker** → pick the **Blank** template.
   - **Hardware:** *CPU basic — free* (2 vCPU, 16 GB RAM). The sentence-
     transformers reranker isn't pulled in by Pollux, so the free tier
     fits comfortably.
   - **Visibility:** Public.
3. Click **Create Space**.

The Space lives at `https://huggingface.co/spaces/<your-username>/pollux`.

## Step 2 — set the `HF_TOKEN` secret

The Space needs your token to call HF Inference for embeddings (BGE-M3) and
chat (Qwen, Llama, etc.).

1. On the Space page, click **Settings**.
2. Scroll to **Variables and secrets** → click **New secret**.
3. Name: `HF_TOKEN`. Value: paste your token. Save.
4. *(Optional)* Add `OPENAI_API_KEY` as a second secret. The Coordinator
   + Ops Planner agents will auto-upgrade to GPT-4o-mini (better
   classification + planning quality). Specialists stay on HF either way.

Without `HF_TOKEN` set the Space boots, but every query errors out with
`HF_TOKEN is not set`.

## Step 3 — clone the Space's Git repo

The Space URL is also a Git remote:

```cmd
cd C:\Users\harsh\.gemini\antigravity\scratch
git clone https://huggingface.co/spaces/<your-username>/pollux pollux-space
```

This creates `pollux-space/` next to `pollux/`, containing the auto-
generated `README.md` template.

## Step 4 — copy the application files into the Space repo

From the **pollux** directory, copy source packages + the `spaces/`
overrides into **pollux-space**:

```cmd
cd C:\Users\harsh\.gemini\antigravity\scratch\pollux

:: Source packages
xcopy /E /I /Y core           ..\pollux-space\core
xcopy /E /I /Y agents         ..\pollux-space\agents
xcopy /E /I /Y orchestrator   ..\pollux-space\orchestrator
xcopy /E /I /Y api            ..\pollux-space\api
xcopy /E /I /Y ui             ..\pollux-space\ui
xcopy /E /I /Y scripts        ..\pollux-space\scripts
xcopy /E /I /Y data           ..\pollux-space\data
xcopy /E /I /Y docs           ..\pollux-space\docs

:: Repo metadata
copy LICENSE                  ..\pollux-space\LICENSE
copy requirements.txt         ..\pollux-space\requirements.txt
copy .gitignore               ..\pollux-space\.gitignore
copy .dockerignore            ..\pollux-space\.dockerignore

:: HF Spaces-specific overrides (these REPLACE files of the same name)
copy spaces\Dockerfile        ..\pollux-space\Dockerfile
copy spaces\README.md         ..\pollux-space\README.md
copy spaces\entrypoint.sh     ..\pollux-space\entrypoint.sh
```

> **What you're deliberately NOT copying:**
> - `mcp_variant/`, `a2a_variant/` — these need their own public ports;
>   HF Spaces only gives us one. The docker-compose deploy in the main
>   repo is the right place to run them.
> - `docker-compose.yml`, the root `Dockerfile` — replaced by the
>   single-container Dockerfile in `spaces/`.
> - `tests/`, `.venv/`, `chroma_data/`, `*.db` — see `.dockerignore`.

## Step 5 — commit and push

```cmd
cd ..\pollux-space
git add -A
git commit -m "initial deployment: Pollux"
git push
```

You'll be prompted for HuggingFace credentials:

- **Username:** your HF username.
- **Password:** an HF **access token** with Write scope (not your
  account password — HF deprecated password auth in 2023).

If you've pushed to a HuggingFace Space before from this machine, Git
Credential Manager has the cached token and the push will go through
silently.

## Step 6 — watch the build

On the Space page, you'll see a **Building** badge. Click **Logs** to
follow it.

First build takes **5–10 minutes** (torch, sentence-transformers, langchain
are the slow installs). Subsequent pushes reuse Docker layer cache and are
much faster.

Once the badge flips to **Running**, the Streamlit UI is live at:

```
https://huggingface.co/spaces/<your-username>/pollux
```

First load triggers sample-knowledge ingestion (~30–60s — embeds 8
markdown files through HF Inference). After that, queries are fast.

## Updating the Space later

Same flow as Step 4: in `pollux/`, change code → re-run the `xcopy`
block → commit + push from `pollux-space/`. The Space rebuilds
automatically.

For frequent updates you can enable **GitHub-to-HF auto-sync** in the
Space's settings — but it requires the Dockerfile + README at the GitHub
repo root, which conflicts with our project layout (root Dockerfile is
the multi-service one for docker-compose). Stick with the xcopy flow.

## Troubleshooting

**"HF_TOKEN is not set"** at runtime → the secret isn't set or has a
typo. Settings → Variables and secrets → confirm there's a secret named
exactly `HF_TOKEN`, then restart the Space.

**Build fails on `chromadb`** → make sure you copied the root
`requirements.txt` (which uses the full `chromadb` package), not an
older `chromadb-client` variant.

**Sample ingest takes forever** → first run after a rebuild re-embeds
the 8 markdown docs through HF. Subsequent wake-from-sleep cycles skip
this because the entrypoint sees existing chunks in the persistent
collection.

**Queries time out** → check the Space logs. Most common: a Coordinator
classification call hitting an unhealthy HF Inference provider. Try a
different model via the **💬 Chat** sidebar, or wait 30s and retry.

**Persistent storage** → `chroma_data/` and `pollux.db` live inside the
container's writable layer. They persist across wake-from-sleep cycles
but get wiped on rebuilds (i.e. when you push new code). Re-ingestion
runs automatically. For real persistence add the **Persistent Storage**
addon to the Space (~$5/mo).

## Streamlit + HF Spaces gotchas (already fixed in `spaces/`)

These bit me on the DocuMind deploy — the Pollux Dockerfile + entrypoint
already include all the workarounds:

- **CORS / XSRF disabled** in Streamlit (`--server.enableXsrfProtection
  false --server.enableCORS false`) — without these, file uploads fail
  with `AxiosError 403` because HF's reverse proxy can't round-trip the
  XSRF cookie.
- **Streamlit on port 7860** (HF Spaces standard), REST API on internal
  127.0.0.1:8001.
- **`UID 1000` non-root user** — required by HF Spaces' container
  runtime.
- **`GIT_PYTHON_REFRESH=quiet`** — silences `gitpython`'s missing-binary
  probe when ragas isn't even imported.

If you hit a new error, paste the Space's build/runtime logs into the
GitHub issue tracker and we'll iterate.
