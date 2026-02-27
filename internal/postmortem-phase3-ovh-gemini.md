# Post-Mortem: Phase 3 OVH Persona Re-Generation Job

## Incident Summary

The Phase 3 persona re-generation job (`batch_regenerate.py`) on OVH was blocked due to compounding failures
spanning API key misalignment, model deprecations, and silent Docker build failures.

**Total Failed OVH Jobs Run:** 8

## What Went Wrong (The Fuckups)

### 1. API Key Format Masking

The `.env` file contained `GEMINI_API_KEY` set to an `AQ...` token. This token format is an OAuth/refresh token,
not a standard REST API key.

- **The Failure:** `v1beta` standard REST endpoints were constantly returning `401 Unauthorized`.
- **The Waste:** Extensive debugging of endpoints when the key itself was the wrong format for the REST API.
- **The Fix:** We had to switch the `.env` variable to use `GOOGLE_CLOUD_API_KEY` (`AIza...`), which works directly
  with `https://generativelanguage.googleapis.com/...` via the `google-genai` SDK.

### 2. Phantom Model Dependencies (404 Not Found)

The default models hardcoded in `gestalt_simulator.py` and `manager.py` (for Mem0) were `gemini-1.5-flash` and `gemini-2.0-flash`.

- **The Failure:** Even with the correct `AIza` key, the SDK returned
  `404 Not Found (User location is not supported for the API use)` or `no longer available to new users`.
  This specific API key tier did not have access to the models we hardcoded.
- **The Waste:** Assuming the code was broken when the API service actively rejected the specific model string on
  that specific tier/key.
- **The Fix:** We ran a `client.models.list()` loop with the *exact* `AIza` key to see what models it could actually
  access, discovering that **only `gemini-2.5-flash` was available**.

### 3. Silent Docker Build Failures

The OVH job uses a custom image. I attempted to build it via
`docker build -f ai/training/ready_packages/platforms/ovh/Dockerfile.training ./ai/training/ready_packages/platforms/ovh`.

- **The Failure:** The `Dockerfile` relies on `COPY ai/core /app/ai/core` and similar root-level paths. Building from
  the `ai/training` subdirectory caused these files to not exist, but due to internal environment checks in shell
  files, the build often exited `0` without actually creating the image correctly.
- **The Waste:** Launching jobs with previous, outdated images (v1, v2) because the local `docker build` failed to
  overwrite them but didn't scream loud enough.
- **The Fix:** `docker build` must **always** be run from the repository root:
  `cd /home/vivi/pixelated && docker build ... -f ai/training/.../Dockerfile.training .`

### 4. Git History PII/Secrets Leak (The Rube Key)

During the frantic debugging of the OVH jobs and attempting to manage Asana tasks using the Composio integration,
the `.gemini/` system directory (which holds local assistant configuration and the sensitive Composio/Rube MCP API key)
was accidentally staged and committed to the repository.

- **The Failure:** Sensitive credentials leaked directly into the git history and were subsequently pushed up to GitHub,
  GitLab, and Bitbucket remotes. This occurred because `.gemini/` was not explicitly excluded in `.gitignore`.
- **The Waste:** Immediate stop-work to rewrite 18,000+ commits across the whole repository to purge the footprint.
- **The Fix:** We ran `git filter-repo --path .gemini/ --path .gemini --invert-paths --force` to irrevocably remove
  the directory from all past commits in the repository. We also appended `*.pt`, `*.ckpt`, and `.gemini/` into
  `.gitignore`. A global `git push --force --all` was dispatched to all upstream remotes (GitLab requires branch
  unprotection to fully scrub).

## File Locations Critical to This Fix

These are the files that were blocking the system and were painfully difficult to trace:

1. **`ai/core/gestalt_simulator.py`** (line ~83) - Hardcoded `_call_llm` model version.
2. **`ai/training/defense_mechanisms/generate_synthetic_loop.py`** (line ~48) - Hardcoded `generate_with_retry` model version.
3. **`ai/utils/llm_capabilities.py`** - **NEW** The newly created utility module that dynamically tests and selects
   the highest functioning Gemini model based on user constraints rather than hardcoded failures.
4. **`/home/vivi/pixelated/.env`** (line ~344) - Contained the conflicting `GEMINI_API_KEY` vs `GOOGLE_CLOUD_API_KEY`.
5. **`/home/vivi/pixelated/.gitignore`** - Now explicitly blocks `.gemini/`, large `.jsonl` files, and multi-gigabyte
   `.zip`/`.pt` model artifacts.

## Next Actions / Preventive Measures (Resolved)

1. **Standardize API Keys:** All AI initialization code uses `ensure_valid_key()` to throw a loud ValueError on
   startup if an `AQ...` token is provided.
2. **Dynamic Model Fallbacks:** The new `get_best_available_gemini_model(client)` automatically tests
   `gemini-2.5-pro` down to `gemini-1.5-flash` on boot and selects the functioning one.
3. **Docker Strictness:** `scripts/ovh/ovh-ai-deploy-training.sh` has been created to enforce
   `cd /home/vivi/pixelated` before attempting `docker build`.
4. **Permanent Git Scrub:** `git filter-repo` executed, `.gemini/` obliterated from history, and `.gitignore` updated.
   Force-pushes completed across primary origins.
