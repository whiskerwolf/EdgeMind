# EdgeMind Admin Usage Analytics API

## Overview

`GET /api/v1/admin/usage` exposes system-wide AI token usage and estimated USD cost analytics aggregated from the persisted `ai_token_usages` ledger (`UsageRepository.get_admin_usage_analytics`).

## Permission Enforcement & Security Guarantees

- **Strict RBAC Guard**: Enforced by `require_role("admin")` (`core/auth/dependencies.py`).
  1. Extracts the Bearer JWT access token via OAuth2PasswordBearer (`401 Unauthorized` when missing, malformed, expired, or wrong token type).
  2. Resolves the user row from the database (`401 Unauthorized` if deleted; `403 Forbidden` if `is_active=False`).
  3. Verifies `user.role == "admin"` against the database record (`403 Forbidden` with `"Operation requires 'admin' privileges."` for `"user"` or any non-admin role).
- **No Privilege Escalation**: Role checks rely exclusively on the database `User.role` resolved from the signed JWT `sub` UUID. Query parameters, forged JWT `role` payloads paired with a normal user `sub`, and profile updates (`PATCH /api/v1/users/me`) cannot elevate privileges.
- **Tenant Isolation Preserved for Standard Users**: Standard users remain scoped to their own usage on `GET /api/v1/agent/usage/summary` and receive `403 Forbidden` on `/api/v1/admin/usage`.
- **Zero Secret or PII Exposure**: Responses exclude API keys, JWT secrets, password hashes, email addresses, raw prompts, and user source code. Tenant attribution uses pseudonymous `user_id` UUID strings (`null` for anonymous sessions).
- **Sanitized Failure Handling**: Unhandled database failures sanitize credentials via `settings.sanitize_error(...)` and return a generic `500 Internal Server Error` detail. Unavailable persistence returns `503 Service Unavailable`.

## Query Parameters

| Parameter | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `period` | `string` (`day` \| `month` \| `all`) | `month` | Time window (`day`: 24h, `month`: 30d, `all`: full ledger) |
| `user_id` | `UUID` (optional) | `null` | Narrow aggregation to one tenant UUID |
| `project_id` | `UUID` (optional) | `null` | Narrow aggregation to one project UUID |
| `provider` | `string` (optional) | `null` | Filter by AI provider (`openai`, `ollama`, etc.) |
| `model` | `string` (optional) | `null` | Filter by model identifier |

## Response Structure (`200 OK`)

Returns `AdminUsageAnalyticsResponse`:

```json
{
  "period": "month",
  "filters": {
    "user_id": null,
    "project_id": null,
    "provider": null,
    "model": null
  },
  "total_prompt_tokens": 1500,
  "total_completion_tokens": 600,
  "total_tokens": 2100,
  "total_estimated_cost_usd": "0.002400000000",
  "is_estimated_cost_known": true,
  "requests_count": 3,
  "distinct_users_count": 2,
  "distinct_projects_count": 1,
  "anonymous_requests_count": 1,
  "by_provider": {
    "openai": {
      "provider": "openai",
      "prompt_tokens": 1000,
      "completion_tokens": 400,
      "total_tokens": 1400,
      "requests_count": 2,
      "estimated_cost_usd": "0.002400000000",
      "is_estimated_cost_known": true
    }
  },
  "by_model": {
    "gpt-4o-mini": {
      "model": "gpt-4o-mini",
      "prompt_tokens": 1000,
      "completion_tokens": 400,
      "total_tokens": 1400,
      "requests_count": 2,
      "estimated_cost_usd": "0.002400000000",
      "is_estimated_cost_known": true
    }
  },
  "by_source": {
    "ACTUAL_PROVIDER": 2,
    "LOCAL_INFERENCE": 1
  },
  "by_user": [
    {
      "user_id": "2c8b0f0a-...",
      "prompt_tokens": 1000,
      "completion_tokens": 400,
      "total_tokens": 1400,
      "requests_count": 2,
      "estimated_cost_usd": "0.002400000000",
      "is_estimated_cost_known": true
    }
  ]
}
```

When recorded events lack pricing metadata (for example, local Ollama `LOCAL_INFERENCE` usage), `total_estimated_cost_usd` is `null` and `is_estimated_cost_known` is `false` — synthetic costs are never fabricated.
