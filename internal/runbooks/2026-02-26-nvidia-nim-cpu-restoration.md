# Runbook: NVIDIA NIM CPU-Only Restoration (2026-02-26)

## 🚨 Issue Description
Docker Engine was updated to `29.2.1`, causing service start limit hits. Additionally, NVIDIA NIM containers were crashing on CPU-only hardware due to:
1. **Hardcoded Library Checks**: Startup scripts requiring `libnvidia-ml.so.1`.
2. **Missing Database Schemas**: NeMo Infrastructure not initializing all required PostgreSQL databases.
3. **Model Compatibility**: Previous model tags requiring GPU-only features.

## 🛠️ Resolution Steps

### 1. Bypassing Hardware Checks
NIM startup scripts contain a check in `32-ld-library-path.sh` that exits if NVML is missing.
- **Fix**: Created `/docker/scripts/skip-lib-check.sh` and mounted it over the internal script.
- **Mount Path**: `./scripts/skip-lib-check.sh:/opt/nim/start_server.d/32-ld-library-path.sh:ro`

### 2. Manual Database Initialization
The NeMo stack requires specific databases that the standard `init.sql` may miss.
- **Databases Created**: `entitystore`, `customizer`, `evaluator`, `auditor`, `datastore`, `guardrails`, `jobs`, `inference`, `intake`.
- **Command**: `docker exec -i nemo-postgres psql -U nmp -d postgres -c 'CREATE DATABASE "..." OWNER nmp;'`

### 3. CPU-Optimized Model Selection
- **Embedding**: Switched to `nvcr.io/nim/nvidia/nv-embedqa-e5-v5:latest` (Tag `1.10.1+`) for better ONNX/CPU support.
- **Reranking**: Switched to `nvcr.io/nim/nvidia/llama-3.2-nv-rerankqa-1b-v2:latest` for low-resource CPU compatibility.
- **Profile ID**: Forced profile `f7391ddbcb95b2406853526b8e489fedf20083a2420563ca3e65358ff417b10f`.

### 4. Triton Runtime Patching
Forced Triton to use CPU instances even when the model manifest defaults to GPU.
- **Implementation**: Background loop in `docker-compose.nemo-retriever.yml` that runs `sed` on `config.pbtxt` to change `KIND_GPU` to `KIND_CPU`.

## ✅ Verification
Confirm service readiness via:
```bash
curl -s http://localhost:8080/v1/health/ready
curl -s http://localhost:8081/v1/health/ready
```

## ⚠️ Notes
- Ensure `NIM_CPU_ONLY=1` and `NIM_MANIFEST_ALLOW_UNSAFE=1` are set in the environment.
- The `skip-lib-check.sh` script must remain in `/docker/scripts/`.
