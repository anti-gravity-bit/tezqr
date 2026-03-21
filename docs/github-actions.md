# GitHub Actions Setup

## CI

The `ci.yml` workflow runs on pull requests and pushes to `main`.

It performs:

- dependency install with `uv`
- Ruff lint checks
- the pytest suite
- a production-style Docker Compose smoke test using `.env.local.prod.example`

## CD

The `cd.yml` workflow publishes the API image to GHCR on pushes to `main` and version tags.

Image tags include:

- `latest` on the default branch
- branch and tag names
- the Git commit SHA

The deploy job is manual through `workflow_dispatch` and expects the production server to already have:

- this repository cloned
- `.env` configured for production
- Docker and Docker Compose installed
- access to pull the published GHCR image

## Required GitHub Secrets For Deploy

- `DEPLOY_HOST`
- `DEPLOY_USER`
- `DEPLOY_SSH_KEY`
- `DEPLOY_PATH`

## Production Server Expectation

Set `API_IMAGE` in the production `.env` file so `docker-compose-prod.yml` pulls the GHCR image instead of relying on local-only build tags.
