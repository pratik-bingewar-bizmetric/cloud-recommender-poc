# CI Pipeline and Reproducible Backend Builds

CI only. Nothing here deploys, logs in to Azure, runs migrations or needs a secret.

## 1. Python version

**Python 3.12** everywhere (`requires-python = ">=3.12,<3.13"`, `.python-version`, App Service runtime `PYTHON|3.12`, CI `actions/setup-python` 3.12). Do not run the suite on another minor version.

## 2. Dependency strategy

| File | Role | Edited by |
|---|---|---|
| `backend/pyproject.toml` | Human-edited dependency **ranges** (runtime + `dev` group) | You |
| `backend/uv.lock` | **Single source of truth**: exact versions + hashes for every package (88) | `uv lock` |
| `backend/requirements.txt` | The 15 **direct** runtime dependencies pinned `==` to the locked versions; ends up on App Service (Oryx installs it); includes `-c requirements.lock.txt` | generated |
| `backend/requirements.lock.txt` | Exact pins of the whole **runtime** closure (constraints) | generated |
| `backend/requirements-dev.lock.txt` | Exact pins of runtime + **dev tooling** (pytest, ruff, mypy, pytest-timeout, ...) — used by CI and local `pip` installs | generated |
| `backend/scripts/sync_requirements.py` | Derives the three generated files from `uv.lock` (no `pip freeze`, no unrelated packages) | — |

Why: the committed `uv.lock` had not been updated since Milestone 0 (it lacked PyJWT, cryptography, sqlglot, databricks-sdk, deltalake, pyarrow, ...), so `uv sync` re-resolved the newest releases on every run and `requirements.txt` used open `>=` ranges. The lock was regenerated and then **constrained to the versions the 931-test suite was verified with** (databricks-sdk 0.162.0, sqlglot 30.30.0, google-auth 2.62.1 instead of the newer releases `uv` preferred). Current key pins: FastAPI 0.143.0, Starlette 1.7.0, Pydantic 2.14.1, SQLAlchemy 2.1.4, Alembic 1.20.0, asyncpg 0.32.0, uvicorn 0.54.0, PyJWT 2.15.1, cryptography 50.0.2.

Platform-specific packages carry markers (`uvloop` only on non-Windows, `httpx2-jsfetch` only on Emscripten), so the same files install on Windows, Linux and App Service.

Added in this change: `pytest-timeout` (dev only) so a single test can never hang the suite.

## 3. Install locally

```powershell
cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.lock.txt    # exact, reproducible
.\.venv\Scripts\python.exe -m pip check
```
With `uv`: `uv sync --frozen --all-groups`. Behind a TLS-inspecting proxy (Zscaler) add `--system-certs` to `uv` commands; never disable certificate verification.

Runtime-only install (what App Service does): `pip install -r requirements.txt` — the `-c requirements.lock.txt` line means **the lock file must sit next to `requirements.txt`** in the ZIP.

## 4. CI workflow (`.github/workflows/backend-ci.yml`)

Triggers: `push` and `pull_request` for `feature/backend-security-hardening` and `main`. Ubuntu latest, read-only `contents` permission, no secrets, per-ref concurrency (older runs cancelled).

| Job | Timeout | Steps |
|---|---|---|
| **backend** (Python 3.12) | 25 min | `pip install -r requirements-dev.lock.txt` → `pip check` → `uv lock --check` + `sync_requirements.py --check` (locks in sync) → `ruff check .` → `ruff format --check .` → `mypy src` → `pytest` (verbose, `--durations=15`, coverage, JUnit XML; uploaded as an artifact) |
| **frontend** (Node 20, `frontend/`) | 20 min | `npm ci` → `npm run lint` → `npm run typecheck` → `npm test` → `npm run build` |
| **result** | — | Always runs; writes a pass/fail table to the run summary and fails if either job failed |

Environment for tests: `APP_ENV=testing`, `LLM_PROVIDER=mock`. All tests are offline (mock LLM, SQLite/in-memory stand-ins, no PostgreSQL, no Azure). The Fabric frontend (`fabric-integration/finops-app`) is **not** in this workflow: its `@microsoft/rayfin-*` packages need verification against the CI registry first.

Note: the older `.github/workflows/ci.yml` (main only) also runs backend checks and uses `uv run mypy src tests`, which fails because `tests/` has no package structure; it was left unchanged.

## 5. Updating dependencies intentionally

1. Edit the range in `backend/pyproject.toml` (both `dependencies` and, for tooling, the two `dev` lists).
2. `uv lock` — or `uv lock --upgrade-package <name>` / `--upgrade-package "<name>==<version>"` for one package. Do **not** run a bare `uv lock --upgrade` without intending to move everything.
3. `python scripts/sync_requirements.py` (needs `uv` on PATH) to regenerate the three requirement files.
4. Verify in a clean venv: `pip install -r requirements-dev.lock.txt && pip check`, then ruff, mypy, pytest.
5. Commit `pyproject.toml`, `uv.lock` and the three generated files together. CI fails if they disagree.

## 6. Troubleshooting test timeouts

- Every test has a **180 s ceiling** (`timeout`, `timeout_method = "thread"` in `pyproject.toml`); the process is ended with a traceback of the stuck test. CI also sets `faulthandler_timeout=120` and a 25-minute job limit.
- Find slow tests: `pytest --durations=20`. Run one verbosely: `pytest path::test -vv -s`.
- Concurrency tests must use `tests/thread_utils.run_concurrently`: daemon threads, a barrier **with a timeout**, bounded joins, and clear errors (`Barrier broken…`, `worker thread(s) still running…`, a worker's own exception). Never use a bare `threading.Barrier.wait()` or `Thread.join()` in a test.
- A "Barrier broken or timed out" failure means not all workers started (overloaded runner or an exception while starting threads), not that the code under test is wrong; rerun, and check for resource exhaustion.
- A timeout in an `async` test usually means an `asyncio.Event` was never set because an earlier assertion raised; fix the first failure.
- Local `.env` files are ignored when `APP_ENV=testing`; run the suite as CI does: `APP_ENV=testing LLM_PROVIDER=mock python -m pytest`.
- Windows: very long virtual-environment paths can break compiled extensions (`DLL load failed … filename or extension is too long`); keep the venv at a short path.

### Root cause of the suite hang seen on 2026-11-17

Reproduced and fixed. The hang was **not** the barrier test: a `faulthandler` dump showed the event loop idle inside `test_stage_a_authorization.py::test_concurrent_pricing_refresh_is_rejected_with_409`. That test waited a fixed `asyncio.sleep(0.2)` for the first request to enter the guarded section; on a loaded machine the second request could win, then block on an `asyncio.Event` that is only released *after* it returns, a deadlock. Under 8 busy processes the old test hung 2 of 5 times; the fixed version (waits on an `entered` event, every await bounded, gate released in `finally`) passed 5 of 5. The barrier test was also hardened (it was a latent hazard, not the cause). Rule: never synchronise concurrent tests with `sleep`; wait for an explicit event, bound every wait, and release gates in `finally`.

`pytest-timeout` was verified to end a hung async test in isolation (~183 s with the CI flags). In the one real hang above the process did **not** exit by itself for 36 minutes and the reason was not established, so do not rely on it alone: the 25-minute job limit and the `faulthandler` dump (printed after 2 minutes, naming the stuck test) remain the backstops.
