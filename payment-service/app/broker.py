from faststream.rabbit import RabbitBroker, RabbitQueue, RabbitExchange, ExchangeType
from app.config import settings

broker = RabbitBroker(settings.rabbitmq_url)

# Main exchange and queue — DLX configured so nacked messages go to DLQ
PAYMENTS_EXCHANGE = RabbitExchange("payments", type=ExchangeType.DIRECT, durable=True)

PAYMENTS_NEW_QUEUE = RabbitQueue(
    "payments.new",
    durable=True,
    routing_key="payments.new",
    arguments={
        "x-dead-letter-exchange": "payments.dlx",
        "x-dead-letter-routing-key": "payments.dead",
    },
)

# Dead Letter Exchange and Queue — receives messages after all retries exhausted
DLX_EXCHANGE = RabbitExchange("payments.dlx", type=ExchangeType.DIRECT, durable=True)

PAYMENTS_DLQ = RabbitQueue(
    "payments.dead",
    durable=True,
    routing_key="payments.dead",
)
