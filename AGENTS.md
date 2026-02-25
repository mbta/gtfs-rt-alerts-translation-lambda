# GTFS-RT Alerts Translation Lambda

This project translates GTFS-Realtime ServiceAlerts feeds from English to multiple target languages using the Smartling API.

## Project Structure

```
.
├── gtfs_translation/           # Main source package
│   ├── core/
│   │   ├── processor.py        # FeedProcessor: GTFS parsing/serialization
│   │   ├── translator.py       # TranslationService interface
│   │   ├── smartling.py        # SmartlingTranslator: Concrete Smartling implementation
│   │   └── fetcher.py          # S3/HTTP fetch utilities & secret resolution
│   ├── config.py               # Settings & Environment variables
│   └── lambda_handler.py       # AWS Lambda entry point
├── tests/                      # Pytest suite
│   ├── unit/                   # Isolated logic tests
│   └── integration/            # Smartling API & S3 integration tests
├── scripts/                    # Utility scripts (e.g., local runner)
├── terraform/                  # Terraform infrastructure (Lambda + S3)
│   ├── main.tf                 # Lambda function, IAM, CloudWatch
│   ├── variables.tf            # Input variables
│   └── outputs.tf              # Output values
├── pyproject.toml              # uv dependency management
├── mise.toml                   # Development task runner
└── README.md
```

## Architecture Patterns

- **Language:** Python 3.13+
- **Dependency Management:** uv
- **Infrastructure:** AWS Lambda + S3 (defined via Terraform)

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
    - `Translator` is an abstract base class in `translator.py`.
    - `SmartlingTranslator` in `smartling.py` is the concrete implementation.
    - This allows easy swapping for `MockTranslator` in tests or other providers later.

4.  **Language Code Mapping:**
    - GTFS-standard language codes (e.g., `es-419`) are used in configuration and output feeds.
    - Automatic mapping to Smartling API codes (e.g., `es-LA`) happens transparently via `config.py`.
    - Mapping defined in `SMARTLING_LANGUAGE_MAP` dictionary.

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
5.  **Package:** `mise run build`
6.  **Deploy:** Apply Terraform configuration in `terraform/` directory

## Configuration

Required Environment Variables:
- `SMARTLING_USER_ID` - Smartling API User Identifier
- `SMARTLING_USER_SECRET` - Smartling API User Secret (or use `SMARTLING_USER_SECRET_ARN`)
- `SMARTLING_USER_SECRET_ARN` - AWS Secrets Manager ARN (alternative to direct secret)
- `SMARTLING_ACCOUNT_UID` - Smartling Account UID
- `SMARTLING_PROJECT_ID` - Smartling Project ID (optional)
- `SMARTLING_JOB_NAME_TEMPLATE` - Template for job names (default: "GTFS Alerts Translation")
- `SOURCE_URL` - Default HTTP or S3 feed URL (e.g., `s3://bucket/alerts.pb` or `https://...`)
- `DESTINATION_BUCKET_URLS` - Comma-separated S3 URLs for translated output (e.g., `s3://bucket/alerts-es.pb,s3://bucket/alerts-es.json`)
- `TARGET_LANGUAGES` - Comma-separated GTFS language codes (e.g., `es-419,fr,pt`)
- `CONCURRENCY_LIMIT` - Max concurrent translation requests (default: 20)
- `LOG_LEVEL` - Logging level (default: NOTICE)

## Workflow Rules

- **Pre-flight Checks:** ALWAYS run `mise run format` and `mise run check` before finishing a task to ensure code quality and type safety.
- **Run Tests:** Always run `mise run test` and ensure all tests pass before completing a task.
- **Commit:** Commit changes with a descriptive message after completing a task or logical unit of work. Use **Conventional Commits** format (e.g., `feat: ...`, `fix: ...`, `chore: ...`).
- **Terraform State:** Never remove or delete `.tfstate` files if they exist in the repo.
- **Deployment Artifact:** `function.zip` is required for deployment; do not delete or ignore it.
