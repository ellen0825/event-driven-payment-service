from faststream.rabbit import RabbitBroker, RabbitQueue, RabbitExchange, ExchangeType
from app.config import settings

broker = RabbitBroker(settings.rabbitmq_url)

PAYMENTS_EXCHANGE = RabbitExchange("payments", type=ExchangeType.DIRECT, durable=True)

PAYMENTS_NEW_QUEUE = RabbitQueue(
    "payments.new",
    durable=True,
    arguments={
        "x-dead-letter-exchange": "payments.dlx",
        "x-dead-letter-routing-key": "payments.dead",
    },
)

PAYMENTS_DLQ = RabbitQueue("payments.dead", durable=True)
DLX_EXCHANGE = RabbitExchange("payments.dlx", type=ExchangeType.DIRECT, durable=True)
