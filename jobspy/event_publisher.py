from __future__ import annotations

import json
import os
from typing import Any

import boto3

from jobspy.util import create_logger


SCRAPE_FINISHED_EVENT_TYPE = "scrape.finished"
DEFAULT_SCRAPE_FINISHED_QUEUE_URL = (
    "https://sqs.eu-north-1.amazonaws.com/032736241895/"
    "job-radar-linked-scrap-finished"
)
DEFAULT_AWS_REGION = "eu-north-1"

log = create_logger("Events")


def _normalize_aws_profile_env() -> None:
    """
    Make empty AWS profile values behave like "unset" so boto3 falls back
    to the default credential chain instead of trying to load profile "".
    """
    profile = os.getenv("AWS_PROFILE")
    if profile is not None and not profile.strip():
        os.environ.pop("AWS_PROFILE", None)

    default_profile = os.getenv("AWS_DEFAULT_PROFILE")
    if default_profile is not None and not default_profile.strip():
        os.environ.pop("AWS_DEFAULT_PROFILE", None)


def _make_boto3_session() -> boto3.session.Session:
    """
    Match the career-agent AWS session handling:
    use AWS_PROFILE only when it is a non-empty value.
    """
    _normalize_aws_profile_env()
    profile = (os.getenv("AWS_PROFILE") or "").strip()
    return boto3.Session(profile_name=profile) if profile else boto3.Session()


def _publish_event(*, event_type: str, payload: dict[str, Any]) -> None:
    queue_url = os.getenv("SCRAPE_FINISHED_QUEUE_URL", DEFAULT_SCRAPE_FINISHED_QUEUE_URL)
    region = os.getenv("AWS_REGION", DEFAULT_AWS_REGION)

    message = {
        "type": event_type,
        **payload,
    }
    body = json.dumps(message, ensure_ascii=False)

    session = _make_boto3_session()
    sqs = session.client("sqs", region_name=region)
    sqs.send_message(
        QueueUrl=queue_url,
        MessageBody=body,
        MessageAttributes={
            "event_type": {
                "DataType": "String",
                "StringValue": event_type,
            },
        },
    )
    log.info("published SQS event %s to %s", event_type, queue_url)


def publish_scrape_finished_event(payload: dict[str, Any]) -> None:
    _publish_event(
        event_type=SCRAPE_FINISHED_EVENT_TYPE,
        payload=payload,
    )
