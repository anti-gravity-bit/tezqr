# FastAPI Backend Engineering Learning Roadmap Using TezQR

This roadmap is designed around two things:

1. The TezQR codebase
2. The book you attached:
   *Building Python Web APIs with FastAPI* by Abdulazeez Abdulazeez Adeshina

The goal is not just to finish the book. The goal is to become the kind of engineer who
can read a real backend codebase, understand why it is structured the way it is, and then
build and test similar systems independently.

## 1. How to use this roadmap

For every chapter:

1. Read the chapter actively.
2. Trace the same concept in TezQR.
3. Do one code-reading task.
4. Do one small hands-on task.
5. Write down what you learned in your own words.

Do not try to "speedrun" the book. You will learn more if you move chapter by chapter
and keep the repo open while reading.

## 2. Suggested pace

Recommended pace:

- 9 core study weeks for Chapters 1 to 9
- 2 additional weeks for your own practice project
- 4 to 6 focused hours per week minimum

If you have more time, spend it on coding the practice tasks rather than reading faster.

## 3. Before you start

Make sure you can do these comfortably:

- run the repo locally
- open Swagger at `/docs`
- run `uv run pytest -q`
- open and navigate the source tree
- explain what FastAPI, SQLAlchemy, Alembic, and Docker each do at a basic level

## 4. Study method for each chapter

Use this pattern every week:

### Read

Read the assigned chapter from the book.

### Trace

Open the suggested TezQR files and follow the flow from entry point to domain logic to
persistence.

### Rebuild

Write a tiny version of the same idea in a scratch FastAPI app or a temporary branch.

### Reflect

Answer:

- What problem does this concept solve?
- Where is it used in TezQR?
- What tradeoff does TezQR make?

## 5. Chapter-by-chapter roadmap

## Chapter 1: Getting Started with FastAPI

Book focus:

- Python API setup basics
- package management
- virtual environments
- Docker
- first FastAPI app

TezQR files to read:

- `pyproject.toml`
- `Dockerfile`
- `docker-compose-local.yml`
- `README.md`
- `src/tezqr/presentation/app.py`
- `src/tezqr/shared/config.py`

What to understand in this repo:

- how dependencies are defined with `uv`
- how Docker builds the image
- how local compose runs API plus Postgres
- how app settings are injected from environment variables

Code-reading task:

- Trace how `create_app()` bootstraps the app and attaches the container.

Hands-on task:

- Run the app locally with Docker.
- Verify `/health`.
- Open `/docs`.
- Change one harmless setting in `.env` and verify you understand where it is read.

What good looks like:

- You can explain how FastAPI starts.
- You can explain the difference between local runtime and production runtime.

## Chapter 2: Routing in FastAPI

Book focus:

- path operations
- request bodies
- path/query parameters
- `APIRouter`
- docs generation

TezQR files to read:

- `src/tezqr/presentation/router.py`
- `src/tezqr/presentation/controllers/health_controller.py`
- `src/tezqr/presentation/controllers/merchant_webhook_controller.py`
- `src/tezqr/presentation/controllers/provider_api_controller.py`
- `src/tezqr/presentation/controllers/provider_webhook_controller.py`
- `src/tezqr/presentation/schemas.py`
- `src/tezqr/presentation/dependencies.py`

What to understand in this repo:

- routes are grouped by responsibility
- controllers are thin
- request validation happens through Pydantic schemas
- route handlers call services instead of embedding business logic

Code-reading task:

- Trace `POST /api/providers/{provider_slug}/payments` from controller to service.

Hands-on task:

- Add one non-breaking route such as `/version` or `/ping` on a feature branch.
- Give it a summary and description in Swagger.

What good looks like:

- You can explain where validation happens.
- You can explain why controllers should stay thin.

## Chapter 3: Response Models and Error Handling

Book focus:

- responses
- response models
- headers/body/status codes
- error handling

TezQR files to read:

- `src/tezqr/presentation/schemas.py`
- `src/tezqr/presentation/docs.py`
- `src/tezqr/presentation/dependencies.py`
- `src/tezqr/domain/exceptions.py`
- `src/tezqr/application/control_plane_presenter.py`

What to understand in this repo:

- domain/application exceptions are translated to HTTP errors centrally
- OpenAPI descriptions live close to the presentation layer
- payload shaping is extracted into a presenter helper

Code-reading task:

- Trace how `DomainValidationError` becomes a `400` HTTP response.

Hands-on task:

- Pick one provider endpoint and improve its schema documentation or example payload.
- Add or improve one OpenAPI-focused test.

What good looks like:

- You understand the difference between domain errors and HTTP errors.
- You can explain why response shaping should not be mixed into every service method.

## Chapter 4: Templating in FastAPI

Book focus:

- server-rendered HTML
- Jinja templates

TezQR reality check:

TezQR is currently API-first and webhook-first. It does not use Jinja templating in the
main product flow.

Why this chapter still matters:

- it teaches when FastAPI is serving HTML versus JSON
- it helps you recognize when not to use templates
- it prepares you for admin dashboards or internal tools

TezQR files to compare:

- `src/tezqr/presentation/app.py`
- `src/tezqr/presentation/controllers/*`
- `src/tezqr/presentation/docs.py`

Code-reading task:

- Explain in writing why TezQR uses OpenAPI docs and chat interfaces instead of HTML templates.

Hands-on task:

- Optional stretch: create a tiny internal HTML page such as `/internal/health-ui`
  rendered with Jinja, purely as a learning exercise.

What good looks like:

- You can explain when HTML templating is useful in a backend.
- You can explain why many modern backend products are JSON/API-first.

## Chapter 5: Structuring FastAPI Applications

Book focus:

- project structure
- separating responsibilities
- organizing larger apps

TezQR files to read:

- `src/tezqr/application/services.py`
- `src/tezqr/application/control_plane.py`
- `src/tezqr/application/ports.py`
- `src/tezqr/infrastructure/container.py`
- `src/tezqr/presentation/controllers/*`
- `src/tezqr/infrastructure/persistence/repositories.py`
- `src/tezqr/infrastructure/persistence/provider_control_repository.py`

What to understand in this repo:

- the codebase has two major bounded product surfaces
- the presentation layer is separate from orchestration
- the provider service uses repository/presenter/message collaborators
- the legacy merchant side still uses a unit-of-work style

Code-reading task:

- Draw a dependency diagram of one complete flow:
  controller -> service -> domain -> repository -> database.

Hands-on task:

- Refactor one tiny helper or repeated formatting concern into a helper module of your own
  on a scratch branch.

What good looks like:

- You can explain the difference between domain, application, infrastructure, and presentation.
- You can identify where a new feature should be added.

## Chapter 6: Connecting to a Database

Book focus:

- SQL databases
- NoSQL databases
- CRUD persistence
- sessions and models

TezQR files to read:

- `src/tezqr/infrastructure/persistence/models.py`
- `src/tezqr/infrastructure/persistence/repositories.py`
- `src/tezqr/infrastructure/persistence/provider_control_repository.py`
- `src/tezqr/infrastructure/persistence/uow.py`
- `src/tezqr/shared/db.py`
- `alembic/versions/0001_initial.py`
- `alembic/versions/0002_upgrade_request_codes.py`
- `alembic/versions/0003_provider_control_plane.py`

What to understand in this repo:

- SQLAlchemy models are the database representation
- domain entities are not the same thing as persistence models
- Alembic is how schema changes are versioned
- the provider side now uses richer repository queries

Code-reading task:

- Choose one model relationship chain and explain it end to end.
  Example: provider -> client -> payment request -> QR assets.

Hands-on task:

- Add a tiny field in a practice branch, generate the migration manually, and explain what changed.
- If you do not want to alter this repo, create a micro FastAPI sandbox app and practice the migration there.

What good looks like:

- You understand the difference between entities, tables, repositories, and migrations.
- You can explain when to use a simple repository method versus direct query composition.

## Chapter 7: Securing FastAPI Applications

Book focus:

- authentication
- authorization
- dependency injection
- OAuth2/JWT
- access control

TezQR files to read:

- `src/tezqr/application/control_plane.py`
- `src/tezqr/domain/enums.py`
- `src/tezqr/domain/exceptions.py`
- `src/tezqr/presentation/dependencies.py`
- `src/tezqr/shared/config.py`

Important context:

TezQR does not currently implement OAuth2/JWT user login.

Instead, the provider surface uses:

- `x-api-key`
- `x-actor-code`
- role checks (`owner`, `manager`, `operator`, `viewer`)

This is simpler than the book's auth model, but it is still a real authorization system.

Code-reading task:

- Trace `_authorize()` in `ControlPlaneService` and explain how access is granted or denied.

Hands-on task:

- Write down how you would evolve TezQR from API-key-plus-actor auth into JWT auth.
- Optional coding task: prototype a separate small FastAPI auth service with sign-up, sign-in, and protected routes.

What good looks like:

- You can distinguish authentication from authorization.
- You can explain what TezQR has today and what it would need for a stronger auth model.

## Chapter 8: Testing FastAPI Applications

Book focus:

- pytest
- fixtures
- endpoint tests
- reducing repetition
- coverage

TezQR files to read:

- `tests/conftest.py`
- `tests/unit/domain/test_domain_models.py`
- `tests/unit/application/test_bot_service.py`
- `tests/unit/presentation/test_openapi.py`
- `tests/integration/test_persistence.py`
- `tests/e2e/test_webhook.py`
- `tests/e2e/test_control_plane.py`

What to understand in this repo:

- unit, integration, and e2e tests have different jobs
- e2e tests protect the actual product flows
- the OpenAPI contract is tested too

Code-reading task:

- Trace one e2e test and explain exactly what it proves.
  Good example: `test_control_plane_routes_cover_provider_payment_and_export_flow`.

Hands-on task:

- Add one new e2e or unit test for a small missing edge case.

What good looks like:

- You can explain why some tests use fakes and others use real database flows.
- You are comfortable reading tests before reading implementation.

## Chapter 9: Deploying FastAPI Applications

Book focus:

- production readiness
- environment variables
- Docker
- deployment choices

TezQR files to read:

- `Dockerfile`
- `docker-compose-local.yml`
- `docker-compose-prod.yml`
- `docker-compose-local.prod.yml`
- `scripts/start-prod.sh`
- `docs/deployment.md`
- `docs/github-actions.md`

What to understand in this repo:

- local and production deployment are intentionally different
- Alembic migrations are part of runtime setup
- health checks and reverse proxies matter
- CI validates more than just Python tests

Code-reading task:

- Explain how local development differs from production startup in this repo.

Hands-on task:

- Bring the app up in Docker locally.
- Run the migration inside the container.
- Verify `/health`.
- Read the deployment guide and explain what you would need on a VPS.

What good looks like:

- You can explain the path from code to container to running API.

## 6. TezQR-specific mastery tasks after the book

After you finish the 9 chapters, do these three repo tasks:

1. Trace three complete product flows in your own notes

- legacy merchant `/pay`
- provider API payment creation
- provider Telegram `/item-code`

2. Make one small feature yourself

Examples:

- add a new dashboard metric
- add a new payment export field
- add a new provider validation rule

3. Write tests before changing behavior

Use this repo to practice strict TDD:

- write a failing test
- implement the smallest change
- refactor
- rerun the suite

## 7. A second practice project to build yourself

You asked for another project so you can code independently. This is the one I recommend.

## Practice project: Repair Desk API

### Why this project

It is close enough to TezQR that the lessons transfer, but different enough that you will
have to design it yourself.

It will teach you:

- CRUD design
- authentication and roles
- SQL modeling
- status workflows
- reminders
- file or asset handling
- testing
- deployment

### Product idea

Build a backend for a repair and service business.

The business has:

- staff members
- customers
- service jobs
- job statuses
- quotes and invoices
- reminder messages
- downloadable invoice PDFs

### Core entities

Start with:

- User
- Role
- Customer
- Device
- ServiceJob
- Quote
- Invoice
- Reminder
- OutboundMessage

### Suggested feature list

Version 1:

- create customers
- create devices
- create service jobs
- update job status
- list jobs by customer
- add notes to a job

Version 2:

- add JWT auth
- add roles for admin, technician, support
- add quotes and invoices
- add reminder scheduling

Version 3:

- add CSV export
- add PDF invoice generation
- add Docker deployment
- add CI

## 8. How to build the practice project chapter by chapter

### Chapter 1

- initialize repo
- set up FastAPI app
- set up Docker and environment variables

### Chapter 2

- create routers for customers, devices, jobs
- validate request bodies
- build CRUD endpoints

### Chapter 3

- add response models
- add custom error responses
- standardize status codes

### Chapter 4

- optional: add a tiny admin HTML page showing jobs by status

### Chapter 5

- split project into `domain`, `application`, `presentation`, `infrastructure`
- add service classes and repositories

### Chapter 6

- connect PostgreSQL
- model relationships
- add Alembic migrations

### Chapter 7

- add JWT auth
- add role-based route protection

### Chapter 8

- unit tests for job rules
- e2e tests for customer/job API
- fixtures for auth and database

### Chapter 9

- Dockerize fully
- add local compose stack
- add health checks
- document deployment

## 9. Rules for the practice project

Do these to learn faster:

- do not copy-paste TezQR implementation blindly
- redesign names and workflows yourself
- write tests before non-trivial features
- keep commits small
- document every new model and route
- explain every design choice in a `docs/notes.md` file

## 10. Backend engineering skills this roadmap will build

If you follow this seriously, you will build competence in:

- API design
- request validation
- error handling
- layered architecture
- business rule modeling
- SQL schema design
- migrations
- repository patterns
- testing strategy
- Docker-based local development
- deployment thinking
- reading and extending an existing backend system

## 11. What to do after finishing

After the book and the practice project, the best next steps are:

1. Add JWT auth to a separate sandbox project.
2. Build one background-job feature using a queue or scheduler.
3. Build one file-processing feature such as PDF generation or report export.
4. Read another production-oriented backend codebase and compare architectures.
5. Come back to TezQR and implement one medium-sized feature fully on your own.

## 12. Final advice

Do not measure progress by how many chapters you finished.

Measure progress by whether you can do these without help:

- explain a request flow from HTTP entry to database write
- add a route without breaking the architecture
- change a model and write the migration
- write a failing test first
- debug a broken container or startup path

That is backend engineering. The book gives you the concepts, and TezQR gives you a real
system to practice them on.
