# Error Handling Reference

This document describes how the URL Shortener application handles errors, edge
cases, and HTTP response codes across every layer of the stack.

---

## Table of Contents

1. [Design Principles](#1-design-principles)
2. [Response Format](#2-response-format)
3. [HTTP Status Code Reference](#3-http-status-code-reference)
4. [Application Error Handlers](#4-application-error-handlers)
5. [Route-Level Validation](#5-route-level-validation)
6. [Database Layer](#6-database-layer)
7. [Reverse Proxy (Nginx)](#7-reverse-proxy-nginx)
8. [Error Propagation Flow](#8-error-propagation-flow)

---

## 1. Design Principles

- **Consistent JSON responses.** Every error, at every layer, returns
  `application/json`. HTML error pages are never exposed to clients.
- **No stack trace leakage.** Internal details are logged server-side but never
  included in the response body. All 500-class errors return a generic message.
- **Fail fast, fail loud.** Invalid input is rejected at the boundary before any
  database work occurs.
- **Graceful degradation.** When the database is unreachable, the application
  returns 503 rather than crashing.

---

## 2. Response Format

All error responses follow the same JSON structure:

```json
{
  "error": "<human-readable message>",
  "status": <integer status code>
}
```

Successful responses return resource representations directly (single object or
array). Successful deletions return `204 No Content` with an empty body.

---

## 3. HTTP Status Code Reference

### Success Codes

| Code | Meaning      | Used By                                      |
|------|--------------|----------------------------------------------|
| 200  | OK           | GET requests, PUT updates                    |
| 201  | Created      | POST `/shorten`, POST `/urls`, POST `/users`, POST `/events`, POST `/users/bulk` |
| 204  | No Content   | DELETE `/urls/:id`, DELETE `/users/:id`, DELETE `/events/:id` |

### Client Error Codes

| Code | Meaning              | Trigger                                                            |
|------|----------------------|--------------------------------------------------------------------|
| 400  | Bad Request          | Missing required fields, malformed JSON, invalid field types       |
| 404  | Not Found            | Resource does not exist (URL, user, event), unknown route          |
| 405  | Method Not Allowed   | HTTP method not supported on the requested endpoint                |
| 409  | Conflict             | Unique constraint violation (duplicate username)                   |

### Server Error Codes

| Code | Meaning                       | Trigger                                                  |
|------|-------------------------------|----------------------------------------------------------|
| 500  | Internal Server Error         | Unhandled exception, short-code generation exhaustion     |
| 502  | Bad Gateway                   | Nginx cannot reach the application process                |
| 503  | Service Unavailable           | Database connection failure, application not ready        |
| 504  | Gateway Timeout               | Application does not respond within `proxy_connect_timeout` (3 s) |

---

## 4. Application Error Handlers

Global error handlers are registered in `app/errors.py` and apply to every
request processed by Flask. They guarantee that no error escapes as raw HTML or
an unstructured string.

| Handler                  | Status | Behavior                                               |
|--------------------------|--------|--------------------------------------------------------|
| `bad_request`            | 400    | Returns `{"error": "Bad request"}`                     |
| `not_found`              | 404    | Returns `{"error": "Not found"}`                       |
| `method_not_allowed`     | 405    | Returns `{"error": "Method not allowed"}`              |
| `internal_error`         | 500    | Logs the exception. Returns `{"error": "Internal server error"}` |
| `service_unavailable`    | 503    | Returns `{"error": "Service unavailable"}`             |
| `unhandled_exception`    | 500    | Catch-all for any `Exception` subclass not matched above. Logs full traceback with `logger.exception`. Returns `{"error": "Internal server error"}` |

The catch-all handler ensures that even unexpected exceptions (library bugs,
OS-level errors) produce a valid JSON response and a corresponding log entry.

---

## 5. Route-Level Validation

Each route validates input before performing any database operation. The
following tables list every documented validation path per resource.

### URLs (`/shorten`, `/urls`)

| Condition                                   | Response Code | Error Message                              |
|---------------------------------------------|---------------|--------------------------------------------|
| Request body is not valid JSON              | 400           | `Missing 'url' field` or `Invalid JSON`   |
| `url` / `original_url` field missing        | 400           | `Missing 'url' field` / `Missing or invalid 'original_url'` |
| URL does not start with `http://` or `https://` | 400       | `URL must start with http:// or https://`  |
| Referenced `user_id` does not exist         | 404           | `User not found`                           |
| Target URL not found (GET/PUT/DELETE by id) | 404           | `URL not found`                            |
| Short-code collision after 10 retries       | 500           | `Failed to generate unique code`           |

### Users (`/users`)

| Condition                                   | Response Code | Error Message                              |
|---------------------------------------------|---------------|--------------------------------------------|
| Request body is not valid JSON              | 400           | `Invalid JSON`                             |
| `username` missing, empty, or not a string  | 400           | `Invalid or missing username` / `Invalid username` |
| `email` missing, empty, or not a string     | 400           | `Invalid or missing email` / `Invalid email` |
| Target user not found (GET/PUT/DELETE by id)| 404           | `User not found`                           |
| Duplicate username on create or update      | 409           | `Username already exists`                  |

### Users Bulk Import (`/users/bulk`)

| Condition                                   | Response Code | Error Message                              |
|---------------------------------------------|---------------|--------------------------------------------|
| No file attached in the multipart request   | 400           | `No file provided`                         |
| CSV rows with missing `username`/`email`    | --            | Silently skipped (row excluded from batch) |
| Duplicate usernames within file             | --            | Handled via `ON CONFLICT ... PRESERVE`     |

### Events (`/events`)

| Condition                                   | Response Code | Error Message                              |
|---------------------------------------------|---------------|--------------------------------------------|
| Request body is not valid JSON              | 400           | `Invalid JSON`                             |
| `event_type` missing, empty, or not a string| 400           | `Missing or invalid 'event_type'`          |
| Referenced `url_id` does not exist          | 404           | `URL not found`                            |
| Referenced `user_id` does not exist         | 404           | `User not found`                           |
| Target event not found (GET/DELETE by id)   | 404           | `Event not found`                          |

---

## 6. Database Layer

Database connection management is handled in `app/database.py`.

### Per-Request Connection Lifecycle

```
before_request        teardown_appcontext
      |                       |
      v                       v
  db.connect()            db.close()
```

- `before_request`: Opens a connection (or reuses an open one). If the
  connection fails, the hook short-circuits the request and returns:

  ```json
  {"error": "Service unavailable", "status": 503}
  ```

  The exception is logged at `ERROR` level with the message
  `"Database connection failed"`.

- `teardown_appcontext`: Closes the connection after the response is sent,
  regardless of success or failure.

### Startup Behavior

During application initialization (`app/__init__.py`), the app attempts to
connect, create tables, and seed initial data. If the database is not yet
available (common in container orchestration), the exception is caught silently
and the application starts anyway. The `before_request` hook will return 503
for individual requests until the database becomes reachable.

---

## 7. Reverse Proxy (Nginx)

Nginx sits in front of the application and handles errors that occur before or
outside of Flask. All proxy error pages are configured to return JSON.

### Error Pages

| Status | Named Location         | Response Body                                              | Trigger                               |
|--------|------------------------|------------------------------------------------------------|---------------------------------------|
| 404    | `@not_found`           | `{"error":"Not found","status":404}`                       | No matching route in Nginx            |
| 502    | `@bad_gateway`         | `{"error":"Service temporarily unavailable","status":502}` | Upstream (app container) unreachable  |
| 503    | `@service_unavailable` | `{"error":"Service unavailable","status":503}`             | Upstream returns 503                  |
| 504    | `@gateway_timeout`     | `{"error":"Gateway timeout","status":504}`                 | Upstream exceeds `proxy_connect_timeout` (3 s) |

### Timeout Configuration

| Parameter                | Value | Purpose                                       |
|--------------------------|-------|-----------------------------------------------|
| `proxy_connect_timeout`  | 3 s   | Maximum wait to establish upstream connection  |
| `proxy_read_timeout`     | 30 s  | Maximum wait for upstream response body        |
| `proxy_send_timeout`     | 30 s  | Maximum wait to send request to upstream       |

---

## 8. Error Propagation Flow

The diagram below shows how an error at any layer reaches the client.

```
Client Request
      |
      v
  [ Nginx ]
      |
      |--- upstream unreachable ---------> 502 JSON
      |--- upstream timeout -------------> 504 JSON
      |--- no matching Nginx route ------> 404 JSON
      |
      v
  [ Flask / Gunicorn ]
      |
      |--- DB connection failed ---------> 503 JSON  (before_request hook)
      |--- route validation failure -----> 400 / 404 / 409 JSON
      |--- resource not found -----------> 404 JSON
      |--- unregistered HTTP method -----> 405 JSON  (global handler)
      |--- unhandled exception ----------> 500 JSON  (catch-all handler, logged)
      |
      v
  [ Normal Response ]
      |
      v
  200 / 201 / 204
```

At no point in this flow does the client receive an HTML page, a raw stack
trace, or an empty body (except for the intentional 204 on DELETE).

---

## Related Documentation

- [FAILURE_MODES.md](FAILURE_MODES.md) -- Failure scenarios, recovery
  procedures, and chaos testing runbook.
