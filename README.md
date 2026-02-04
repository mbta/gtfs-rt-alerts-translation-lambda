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

The application is configured via environment variables:

| Variable | Description |
|----------|-------------|
| `SMARTLING_USER_ID` | Smartling API User Identifier |
| `SMARTLING_USER_SECRET` | Smartling API User Secret |
| `SMARTLING_ACCOUNT_UID` | Smartling Account UID |
| `SOURCE_URL` | Default HTTP or S3 URL (e.g., `s3://bucket/alerts.pb`) |
| `DESTINATION_BUCKET_URL` | S3 URL for translated output (e.g., `s3://bucket/alerts-translated.pb`) |
| `TARGET_LANGUAGES` | Comma-separated language codes (e.g., `es,fr,pt`) |

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
