# GTFS-RT Alerts Translation Lambda

An AWS Lambda function that translates GTFS-Realtime ServiceAlerts feeds from English into multiple target languages using the Smartling Machine Translation API.

## Features

- **Hybrid Trigger Support**: Can be triggered by S3 Event Notifications (Push) or Scheduled EventBridge rules (Pull).
- **Stateful Translation Diffing**: Fetches the previous version of the translated feed and only translates strings that have changed, significantly reducing API costs.
- **Async Processing**: Uses `asyncio` and `httpx` to translate multiple alerts concurrently.
- **Format Preservation**: Automatically detects and maintains the input format (Protobuf or JSON).
- **URL Localization**: Appends `?locale={lang}` to alert URLs for non-English translations.

## Prerequisites
- [mise](https://mise.jdx.dev/)
- [uv](https://docs.astral.sh/uv/) (installed by Mise)
- Python 3.13+ (installed by Uv)

## Configuration

### Environment Variables

The application is configured via environment variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `SMARTLING_USER_ID` | Smartling API User Identifier | (required) |
| `SMARTLING_USER_SECRET` | Smartling API User Secret (can be provided directly or via `SMARTLING_USER_SECRET_ARN`) | (required) |
| `SMARTLING_USER_SECRET_ARN` | AWS Secrets Manager ARN containing the Smartling User Secret (alternative to `SMARTLING_USER_SECRET`) | - |
| `SMARTLING_ACCOUNT_UID` | Smartling Account UID (required for MT Router API, not used with Job Batches) | - |
| `SMARTLING_PROJECT_ID` | Smartling Project ID (required for Job Batches API, leave empty for MT Router API) | - |
| `SMARTLING_JOB_NAME_TEMPLATE` | Template for Smartling job names when using Job Batches API | `"GTFS Alerts Translation"` |
| `SOURCE_URL` | Default HTTP or S3 URL for source feed (e.g., `https://example.com/alerts.json` or `s3://bucket/alerts.pb`) | (required) |
| `DESTINATION_BUCKET_URLS` | Comma-separated S3 URLs for translated output (e.g., `s3://bucket/alerts.pb,s3://bucket/alerts.json`) | (required) |
| `TARGET_LANGUAGES` | Comma-separated language codes (e.g., `es-419,fr,pt`). Uses GTFS standard codes. | `es-419` |
| `CONCURRENCY_LIMIT` | Maximum number of concurrent translation requests | `20` |
| `LOG_LEVEL` | Logging level (`DEBUG`, `INFO`, `NOTICE`, `WARNING`, `ERROR`) | `NOTICE` |
| `TRANSLATION_TIMEOUT` | Maximum time (in seconds) to wait for translations before publishing feed without them | `50` |

### Translation Timeout Behavior

The Lambda is configured with two timeout values to ensure alerts are always published even if translation fails:

- **`translation_timeout`**: The maximum time to wait for Smartling API responses (default: 50s)
- **`lambda_timeout`**: The AWS Lambda function timeout (default: 60s, must be greater than `translation_timeout`)

If translation doesn't complete within `translation_timeout` seconds, the Lambda will:
1. Log a warning about the timeout
2. Publish the original English-only feed to the destination
3. Allow the next scheduled run to attempt translation again

This ensures critical alert information reaches users even during Smartling API outages or slowdowns.

### Language Code Mapping

The Lambda uses GTFS-standard language codes in configuration and output feeds, but automatically maps them to Smartling's API codes when making translation requests:

| GTFS Code | Smartling Code | Description |
|-----------|----------------|-------------|
| `es-419` | `es-LA` | Latin American Spanish |

Other language codes pass through unchanged (e.g., `fr`, `pt`, `zh`).

## Development

### Setup

```bash
mise run setup
```

### Running Tests

```bash
mise run test
```

### Formatting

```bash
mise run format
```

### Linting & Type Checking

```bash
mise run check
```

### Local Execution

You can run the translation logic locally without deploying to Lambda. This will output the translated JSON to `stdout`:

```bash
# Export Smartling credentials
export SMARTLING_USER_ID=...
export SMARTLING_USER_SECRET=...
export SMARTLING_ACCOUNT_UID=...
export SMARTLING_PROJECT_ID=...

# Run for a specific URL and languages
mise run run-local https://cdn.mbta.com/realtime/Alerts_enhanced.json --langs es,zh
```

## How it Works

1. **Trigger**: The Lambda starts via S3 Event or Schedule.
2. **Fetch**: It downloads the "source" feed from the source and the "dest" translated feed from the destination.
3. **Diff**: It compares every Alert. If the English text matches an entry in the "dest" feed, it reuses the existing translations.
4. **Translate**: New or changed strings are sent to Smartling MT API concurrently.
5. **Serialize**: The resulting GTFS object is serialized back to the original format.
6. **Upload**: The final feed is saved back to S3.

## Deployment

Deploy using the provided Terraform module. See [terraform/README.md](terraform/README.md) for details.

## License

MIT
