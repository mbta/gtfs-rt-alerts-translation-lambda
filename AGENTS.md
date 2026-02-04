# GTFS-RT Alerts Translation Lambda

This project translates GTFS-Realtime ServiceAlerts feeds from English to multiple target languages using the Smartling API.

## Project Structure

```
.
├── gtfs_translation/           # Main source package
│   ├── core/
│   │   ├── processor.py        # FeedProcessor: GTFS parsing/serialization
│   │   └── translator.py       # TranslationService interface & Smartling implementation
│   ├── config.py               # Settings & Environment variables
│   └── lambda_handler.py       # AWS Lambda entry point
├── tests/                      # Pytest suite
│   ├── unit/                   # Isolated logic tests
│   └── integration/            # Smartling API & S3 integration tests
├── scripts/                    # Utility scripts (e.g., local runner)
├── template.yaml               # AWS SAM template (Infrastructure as Code)
├── pyproject.toml              # uv dependency management
└── README.md
```

## Architecture Patterns

- **Language:** Python 3.13+
- **Dependency Management:** uv
- **Infrastructure:** AWS Lambda + S3 (defined via AWS SAM)

## Development Environment

- **Tool Versioning:** `mise` (or `asdf`) is used to manage tool versions via `.tool-versions`.
- **Python:** 3.13.x
- **uv:** 0.9.x

### Core Patterns

1.  **Typed GTFS Processing:**
    - We NEVER generic walk the JSON.
    - We ALWAYS deserialize to `gtfs_realtime_pb2.FeedMessage`.
    - We modify only known fields (`header_text`, `description_text`).

2.  **Event-Aware Configuration:**
    - The Lambda is "Hybrid Triggered".
    - **Default:** It looks at `SOURCE_URL` env var.
    - **Override:** If `event` contains S3 records, it uses the specific Bucket/Key.

3.  **Interface Segregation:**
    - `Translator` is an abstract base class.
    - `SmartlingTranslator` is the concrete implementation.
    - This allows easy swapping for `MockTranslator` in tests or other providers later.

## Coding Standards

### Typing
- **Strict Type Hints:** All function signatures must be typed.
- **MyPy:** Run `mypy .` in CI to enforce type safety.

### Testing
- **Framework:** `pytest`
- **Coverage:** Aim for 90%+ coverage on core logic (`processor.py`).
- **Mocking:** Use `unittest.mock` or `pytest-mock`.
    - NEVER make real HTTP calls in Unit tests.
    - Use `vcrpy` or explicit mocks for Smartling API tests.

### Linting & Formatting
- **Ruff:** Use `ruff` for both linting and formatting (replaces Flake8 + Black).
- **Line Length:** 100 characters.

## CI/CD Pipeline

1.  **Build:** `mise run setup`
2.  **Lint:** `mise run format`
3.  **Type Check:** `mise run check`
4.  **Test:** `mise run test`
5.  **Package:** `sam build`

## Configuration

Required Environment Variables:
- `SMARTLING_USER_ID`
- `SMARTLING_USER_SECRET`
- `SMARTLING_PROJECT_ID`
- `SOURCE_URL` (Default HTTP feed URL)
- `DESTINATION_BUCKET_URL` (S3 path)
- `TARGET_LANGUAGES` (Comma-separated: `es,fr,pt`)

## Workflow Rules

- **Pre-flight Checks:** ALWAYS run `mise run format` and `mise run check` before finishing a task to ensure code quality and type safety.
- **Run Tests:** Always run `mise run test` and ensure all tests pass before completing a task.
- **Commit:** Commit changes with a descriptive message after completing a task or logical unit of work. Use **Conventional Commits** format (e.g., `feat: ...`, `fix: ...`, `chore: ...`).
- **Terraform State:** Never remove or delete `.tfstate` files if they exist in the repo.
- **Deployment Artifact:** `function.zip` is required for deployment; do not delete or ignore it.
