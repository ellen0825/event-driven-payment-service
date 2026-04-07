# Payment Processing Service

Async payment microservice that accepts payment requests, processes them through an emulated gateway, and notifies clients via webhook.

## Stack

- **FastAPI** + Pydantic v2
- **SQLAlchemy 2.0** (async mode)
- **PostgreSQL** — persistent storage
- **RabbitMQ** via FastStream — message broker
- **Alembic** — database migrations
- **Docker + docker-compose**

## Architecture

```
POST /api/v1/payments
        │
        ▼
  Save Payment (pending)
  Save OutboxEvent          ← atomic DB transaction
        │
        ▼
  Outbox Relay (background)
  publishes to RabbitMQ
        │
        ▼
  payments.new queue
        │
        ▼
  Consumer (handle_payment)
  ├── emulate gateway (2-5s, 90% success)
  ├── update payment status in DB
  ├── send webhook (3 retries, exponential backoff)
  └── on failure × 3 → nack → payments.dead (DLQ)
```

**Outbox pattern** guarantees at-least-once delivery: the event is written to the DB in the same transaction as the payment, then a background relay publishes it to RabbitMQ. If the service crashes before publishing, the relay picks it up on restart.

**Idempotency** is enforced via a unique `idempotency_key` constraint. Duplicate requests return the existing payment without creating a new one.

**DLQ**: `payments.new` is configured with `x-dead-letter-exchange = payments.dlx`. After 3 failed processing attempts the message is nacked and routed to `payments.dead`.

## Project Structure

```
payment-service/
├── alembic/                  # migrations
│   └── versions/
│       └── 0001_initial.py
├── app/
│   ├── auth.py               # X-API-Key dependency
│   ├── broker.py             # RabbitMQ exchanges and queues
│   ├── config.py             # settings from env
│   ├── consumer.py           # FastStream subscriber
│   ├── database.py           # async SQLAlchemy engine
│   ├── main.py               # FastAPI app + outbox relay
│   ├── models.py             # Payment, OutboxEvent
│   ├── outbox.py             # outbox relay loop
│   ├── routers/
│   │   └── payments.py       # API endpoints
│   └── schemas.py            # Pydantic schemas
├── consumer_main.py          # consumer entrypoint
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── alembic.ini
├── .env
└── .env.example
```

## Getting Started

### Prerequisites

- Docker + Docker Compose

### Run

```bash
cd payment-service
cp .env.example .env   # adjust values if needed
docker-compose up --build
```

Services:
| Service | URL |
|---|---|
| API | http://localhost:8000 |
| API docs (Swagger) | http://localhost:8000/docs |
| RabbitMQ management | http://localhost:15672 (guest / guest) |

Migrations run automatically on API startup via `alembic upgrade head`.

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://postgres:postgres@db:5432/payments` | Async DB connection string |
| `RABBITMQ_URL` | `amqp://guest:guest@rabbitmq:5672/` | RabbitMQ connection string |
| `API_KEY` | `secret-api-key` | Static API key for `X-API-Key` header |

## Authentication

All endpoints require the `X-API-Key` header:

```
X-API-Key: secret-api-key
```

Returns `401 Unauthorized` if missing or invalid.

## API Reference

### Create Payment

```
POST /api/v1/payments
```

**Headers:**
```
X-API-Key: secret-api-key
Idempotency-Key: <unique-string>
Content-Type: application/json
```

**Body:**
```json
{
  "amount": 150.00,
  "currency": "RUB",
  "description": "Order #42",
  "metadata": {"order_id": "42", "user_id": "99"},
  "webhook_url": "https://example.com/webhook"
}
```

`currency` accepts: `RUB`, `USD`, `EUR`

**Response `202 Accepted`:**
```json
{
  "payment_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "status": "pending",
  "created_at": "2026-04-07T10:00:00Z"
}
```

Repeating the request with the same `Idempotency-Key` returns the same response without creating a duplicate.

---

### Get Payment

```
GET /api/v1/payments/{payment_id}
```

**Headers:**
```
X-API-Key: secret-api-key
```

**Response `200 OK`:**
```json
{
  "payment_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "amount": "150.00",
  "currency": "RUB",
  "description": "Order #42",
  "metadata": {"order_id": "42", "user_id": "99"},
  "status": "succeeded",
  "idempotency_key": "my-unique-key",
  "webhook_url": "https://example.com/webhook",
  "created_at": "2026-04-07T10:00:00Z",
  "processed_at": "2026-04-07T10:00:03Z"
}
```

Returns `404` if payment not found.

## Webhook Notification

When processing completes the service POSTs to `webhook_url`:

```json
{
  "payment_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "status": "succeeded"
}
```

Delivery is retried up to 3 times with exponential backoff (1s, 2s, 4s) on 5xx or network errors.

## Quick Test

```bash
# 1. Create a payment
curl -X POST http://localhost:8000/api/v1/payments \
  -H "X-API-Key: secret-api-key" \
  -H "Idempotency-Key: test-001" \
  -H "Content-Type: application/json" \
  -d '{"amount": 99.99, "currency": "USD", "description": "Test"}'

# 2. Check status (replace with actual payment_id)
curl http://localhost:8000/api/v1/payments/<payment_id> \
  -H "X-API-Key: secret-api-key"

# 3. Test idempotency — same key returns same payment
curl -X POST http://localhost:8000/api/v1/payments \
  -H "X-API-Key: secret-api-key" \
  -H "Idempotency-Key: test-001" \
  -H "Content-Type: application/json" \
  -d '{"amount": 99.99, "currency": "USD", "description": "Test"}'
```


## Running Migrations Manually

```bash
docker-compose exec api alembic upgrade head      # apply
docker-compose exec api alembic downgrade -1      # rollback one
docker-compose exec api alembic revision --autogenerate -m "description"  # new migration
```
