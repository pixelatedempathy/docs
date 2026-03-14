# OVH AI Training: Troubleshooting & Best Practices

This document records the critical configuration fixes required for running
Pixelated Empathy AI jobs on OVHcloud AI Platform.

## 🛑 Common Failure Modes

### 0. 403 "pci project status is \"\"" (ovhai me / job run)

**Symptom**: `ovhai me` or `ovhai job run` fails with:

```text text
AI Training error: request error: 403: forbidden, pci project status is ""

```

**Cause**: OVH **backend bug**. Our side is correctly set up: project is activated,
users have AI Training Operator + ObjectStore operator, tokens and region (e.g.
US-EAST-VA) are correct. The AI Training API is returning an empty `pci project
status` for the project; the console shows "account already authorized" when
trying to activate. **We cannot fix this ourselves** — resolution requires OVH
to fix their backend or status lookup.

**What we do**: Escalate to OVH support. Include: exact error
`403: forbidden, pci project status is ""`, project ID (e.g.
`49c5c322-6340-459a-8dea-2fcfd6237e7f`), and that the project is activated and
the console reports "account already authorized." Optional: retry later or try
a new application token and `ovhai login --token <NEW_TOKEN>` in case their
backend eventually recovers; the fix is still on their side.

---

## OVH CLI and config reference

Useful for debugging and for support tickets.

- **CLI binary**: Typically `~/.local/bin/ovhai` or from install script.
  Top-level: `--token <TOKEN>`, `-v` (verbose), `config`, `login`, `me`, `job`,
  `token`, `feature`, `debug`.
- **Region**: `ovhai config list` shows available configs (e.g. `US-EAST-VA`).
  `ovhai config set US-EAST-VA` switches region. You must be on the region that
  matches your Public Cloud project (e.g. vampires is US-EAST-VA).
- **Config file**: `~/.config/ovhai/config.json` — holds `current_config_name`,
  per-region `api_http_url`, `shared_registry`, OAuth client ids (no project ID;
  project comes from the token).
- **Context (stored auth)**: `~/.config/ovhai/context.json` — holds `access_tokens` per region (JWT).
  The JWT payload includes `project` (your Public Cloud project UUID) and `exp`. If you get 403 with empty pci project
  status, the token is usually valid and project-scoped; the backend's "pci project status" lookup for that project
  is failing.
- **Login**: `ovhai login` (interactive) or `ovhai login --token <APP_TOKEN>`.
  Requires a user with **AI Training Operator** and **ObjectStore operator**
  (see Control Panel → Public Cloud → Project → Users & Roles). Application
  tokens can be created from AI Dashboard → Users & Tokens.
- **Token subcommands**: `ovhai token create | renew | list | delete` — manage
  application tokens (use `--token` for auth when calling these).
- **Features**: `ovhai feature list` — toggles like auto-upgrade,
  confirm-before-upgrade; nothing that would fix 403.
- **Debug**: When a command fails, the error message may include
  `ovhai debug <SESSION_ID>` to print full request/response logs for that run.
- **Install (US-EAST-VA)**: `curl <https://cli.us-east-va.ai.cloud.ovh.us/install.sh> | bash`.

### 1. Exit Code 2 (Immediate Crash)

**Symptom**: The job fails within seconds with no logs or a generic "Exit Code
2". **Root Cause**: Permission mismatch. OVH forces containers to run as **UID
42420** (`ovhcloud`), ignoring the `USER` instruction in the Dockerfile. If your
app tries to write to directories owned by another user (e.g., UID 1000
`ubuntu`), it will crash early. **Resolution**:

- Explicitly create and use UID 42420 in the Dockerfile.
- Ensure all app directories (`/app`, `/app/logs`, `/app/tmp`) are recursively
  owned by 42420.

### 2. ModuleNotFoundError / ImportError

**Symptom**: `No module named 'ai.core'` even though the directory exists.
**Root Cause**: PYTHONPATH Paradox. If the source code is copied into
`/app/ai/`, setting `PYTHONPATH=/app/ai` will cause Python to look *inside* that
folder for an `ai` package, which it won't find. **Resolution**:

- Set `PYTHONPATH=/app`.
- This allows `from ai.core import ...` to correctly resolve because Python sees
  the `ai/` folder inside `/app`.

### 3. "Ghost" Code (Stale Image)

**Symptom**: You push a fix, but the logs show old code or an old file
structure. **Root Cause**: OVH nodes cache the `:latest` tag locally. If a node
already has a `:latest` image, it may not re-pull even if you pushed a new
revision to Docker Hub. **Resolution**:

- **Never use `:latest` for active development.**
- Use unique, timestamped tags (e.g., `v1772392159`).
- Update your deployment script to generate these tags dynamically.

### 4. Persona Re-Generation Uses NIM Only (No Gemini)

Persona re-generation (**batch_regenerate.py** / Lightning script) uses
**NVIDIA NIM** for LLM response rewriting via the OpenAI-compatible API.
Gemini is not used. **Required env**: **NIM_API_KEY** or **NVIDIA_API_KEY**.
Optional: **OPENAI_BASE_URL** (default `<https://integrate.api.nvidia.com/v1`),>
**PERSONA_NIM_MODEL** or **LLM_MODEL** (default `meta/llama-3.3-70b-instruct`).
Do not rely on GEMINI_API_KEY for this job.

---

## 🛠️ Dockerfile Best Practices (OVH-Ready)

Ensure your production stage looks like this:

```dockerfile

## OVH AI Training runs as UID 42420
RUN groupadd -g 42420 ovhcloud && \
    useradd -u 42420 -g 42420 -m -s /bin/bash ovhcloud

WORKDIR /app
COPY . ai/

## Set ownership to OVH user
RUN chown -R 42420:42420 /app
USER 42420

CMD ["python", "-m", "ai.api.main"]

```

## 🚀 Running the Job

Always specify `PYTHONPATH` in the environment variables:

```bash

ovhai job run \
  --env PYTHONPATH="/app" \
  docker.io/pixelatedempathy/training-node:v<TIMESTAMP> \
  -- python /app/ai/training/scripts/batch_regenerate.py ...

```

## 🔁 Persona Re-Generation Resume (OVH Output-Count Based)

When `--resume` is enabled on `batch_regenerate.py`, Persona Re-Generation can continue from the last completed output
record instead of restarting from zero.

- Checkpoint metadata is written to S3 on a stable object key (`checkpoints/persona-regeneration/<job>.json`).
- The resume path uses output-count derivation first from checkpoint state
  (`output_records_written`) and falls back to counting existing lines in
  `--output-s3-key`.
- Processing stops when `--max-records` is reached.

Example launch flags:

```bash

ovhai job run \
  ... \
  --env CHECKPOINT_PREFIX="checkpoints/persona-regeneration" \
  --env CHECKPOINT_JOB_NAME="persona-regen-${VERSION_TAG}" \
  -- \
  python /app/ai/training/scripts/batch_regenerate.py \
    --resume \
    --checkpoint-prefix "${CHECKPOINT_PREFIX}" \
    --checkpoint-job-name "${CHECKPOINT_JOB_NAME}" \
    --checkpoint-frequency 250

``` text


Inspect or clear checkpoint data manually (for example, if a bad checkpoint is blocking progress):


```bash

PYTHONPATH="${PYTHONPATH:-$(pwd)}" python - <<'PY'
import os

from ai.core.utils.s3_dataset_loader import S3DatasetLoader

checkpoint_key = os.path.join(
    "checkpoints",
    "persona-regeneration",
    f"{os.getenv('CHECKPOINT_JOB_NAME', 'persona-regeneration')}.json",
)
loader = S3DatasetLoader(bucket="pixel-data")
try:
    loader.s3_client.delete_object(Bucket=loader.bucket, Key=checkpoint_key)
    print("Deleted", checkpoint_key)
except Exception as exc:
    print("Failed", checkpoint_key, exc)
PY

```
