import os
import json
import urllib.request
import urllib.error
import boto3

API_URL = os.environ["API_URL"]
SNS_TOPIC_ARN = os.environ["SNS_TOPIC_ARN"]

sns = boto3.client("sns")

def publish_sns(subject: str, message: str) -> None:
    sns.publish(
        TopicArn=SNS_TOPIC_ARN,
        Subject=subject[:100],
        Message=message
    )

def lambda_handler(event, context):
    payload = {
        "interest_rate": os.environ["INTEREST_RATE"],
        "current_payment": os.environ["CURRENT_PAYMENT"],
        "mortgage_balance": os.environ["MORTGAGE_BALANCE"]
    }

    data = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(
        url=API_URL,
        data=data,
        method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = resp.read().decode("utf-8")

            resp_json = json.loads(body)                      
            recommendation = resp_json.get("recommendation")

            # Send the email!
            publish_sns(
                "RefiAI: Daily Recommendation",
                f"{recommendation}"
            )

        return {"statusCode": resp.status, "body": body}

    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        publish_sns(
            "RefiAI: Daily POST FAILED (HTTPError)",
            f"HTTP status: {e.code}\nResponse (first 2000 chars):\n{error_body[:2000]}",
        )
        raise

    except Exception as e:
        publish_sns(
            "RefiAI: Daily POST FAILED (Exception)",
            f"Error: {repr(e)}",
        )
        raise