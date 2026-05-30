# Server

This is the thin Go HTTP layer for the Multi Layered Wood Art Generator project

# Server

This is the thin Go HTTP layer for the Multi Layered Wood Art Generator project.

## What it does

The Go server will eventually:

- accept image uploads
- create one job directory per request
- run the existing Python pipeline as a background process
- expose job status and download links

## Current starter behavior

`cmd/api/main.go` now loads configuration from environment variables (it auto-loads `server/.env` when present via `github.com/joho/godotenv`), validates them, and starts a tiny HTTP server exposing:

- `GET /healthz` — returns `ok` for quick liveness checks
- `GET /config` — (temporary) returns the loaded configuration as JSON for local debugging

The `/config` endpoint is intended only for local development; it exposes filesystem paths and should be removed or restricted before deploying the server publicly.

## Environment variables

Required (set in `server/.env` or in your shell):

- `JOBS_ROOT` — absolute path to jobs workspace directory (e.g. `${HOME}/Desktop/Multi_layered_wood_art_generator/jobs`)
- `PYTHON_PATH` — absolute path to the Python executable that should run the pipeline (e.g. `${HOME}/.../mwca_env/bin/python`)

Optional:

- `MAX_WORKERS` — number of jobs to process at once, default `2`
- `JOB_TIMEOUT_SEC` — per-job timeout in seconds, default `3600`
- `API_ADDR` — HTTP listen address, default `:8080` (use `127.0.0.1:8080` for local-only)

### Notes on `.env`

- Place a local `server/.env` for convenience. The server uses `godotenv` to load it automatically when started from the `server/` directory.
- Keep secrets out of version control. Add `server/.env` to `.gitignore` or add an appropriate rule in the repo root `.gitignore`.

## Examples and first steps

From the `server/` directory, install the local helper dependency and tidy modules (one-time):

```bash
go get github.com/joho/godotenv@latest
go mod tidy
```

Build the binary:

```bash
go build ./cmd/api
```

Run the server (when started from `server/` the `.env` file will be loaded automatically):

```bash
go run ./cmd/api
```

Or run the compiled binary:

```bash
./api
```

Verify endpoints:

```bash
curl http://localhost:8080/healthz
```
