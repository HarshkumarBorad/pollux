# Aurora API Reference

The Aurora REST API exposes compute and storage primitives over HTTPS. All endpoints served at `https://api.aurora.example/v1`.

## Authentication

All requests require a Bearer token in the `Authorization` header:

```
Authorization: Bearer <your_api_key>
```

API keys are issued from the Aurora Console under **Account → API Keys**. Each key is scoped to a specific project and can be rotated or revoked at any time.

## Rate limits

| Tier | Per-minute | Daily cap |
|---|---|---|
| Free | 60 req/min | 10,000 req/day |
| Pro | 600 req/min | none |
| Enterprise | custom | custom |

Exceeding the limit returns `429 Too Many Requests` with a `Retry-After` header.

## Compute endpoints

### `POST /compute/jobs`
Submit a new compute job.

```json
{
  "image": "myregistry/myimage:latest",
  "command": ["python", "train.py"],
  "resources": {"cpu": 4, "memory_gb": 16, "gpu": "a100:1"}
}
```

Returns `201 Created` with the job ID.

### `GET /compute/jobs/{id}`
Fetch job status. Values: `pending`, `running`, `succeeded`, `failed`, `cancelled`, `oom_killed`.

### `DELETE /compute/jobs/{id}`
Cancel a running or pending job. No-op if already in terminal state.

## Storage endpoints

### `PUT /storage/objects/{bucket}/{key}`
Upload. Supports multipart for files >100MB.

### `GET /storage/objects/{bucket}/{key}`
Download. Supports `Range` requests.

### `DELETE /storage/objects/{bucket}/{key}`
Delete. Soft-deleted by default; pass `?hard=true` to bypass the 7-day recovery window.

## SDK

Official SDKs available for **Python**, **TypeScript**, and **Go**. See the SDK Quickstart for installation.

## Versioning

Semantic versioning. Breaking changes in a new major version (`/v2`). Minor versions add fields without removing existing ones. Deprecated endpoints supported for at least 12 months after announcement.
