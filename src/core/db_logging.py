import os
import boto3
from decimal import Decimal
from datetime import datetime
from zoneinfo import ZoneInfo

dynamodb = boto3.resource(
    "dynamodb",
    region_name=os.getenv("AWS_REGION", "us-east-1"),
)

table = dynamodb.Table(os.environ["LOG_TABLE"])

# Max recommendations per visitor IP per day (Eastern), enforced by the API.
DAILY_IP_LIMIT = 5


def _d(x):
    return Decimal(str(x)) if x is not None else None

def log_event(interest_rate, current_payment, mortgage_balance, timestamp, primary_key, ip=None):

    item = {
        "interest_rate": _d(interest_rate),
        "current_payment": _d(current_payment),
        "mortgage_balance": _d(mortgage_balance),
        "timestamp": timestamp,
        "primary_key": primary_key,
        "ip": ip,
    }

    table.put_item(Item=item)
    print("Successfully logged to DB!")


def increment_ip_usage(ip: str) -> int:
    """Atomically bump today's request count for this IP and return the new count.

    Counters live in the same log table under primary_key "ratelimit#<ip>#<date>",
    so the limit resets at midnight Eastern and no extra table is needed.
    """
    today = datetime.now(ZoneInfo("US/Eastern")).date().isoformat()
    resp = table.update_item(
        Key={"primary_key": f"ratelimit#{ip}#{today}"},
        # "count" is a DynamoDB reserved word, hence the name placeholder
        UpdateExpression="ADD #c :one",
        ExpressionAttributeNames={"#c": "count"},
        ExpressionAttributeValues={":one": Decimal(1)},
        ReturnValues="UPDATED_NEW",
    )
    return int(resp["Attributes"]["count"])
