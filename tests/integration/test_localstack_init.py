"""infra/localstack/init.sh against a real LocalStack: bucket, ingest queue, DLQ and redrive policy.

This checks the infrastructure the ingestion pipeline will rely on (arc42: SQS with a DLQ after 3
receives) without waiting for the application's queue/storage adapters to exist. Plain HTTP (the
AWS query protocol) is used so no AWS SDK is needed.
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from dataclasses import dataclass

import pytest
from support.repo import REPO_ROOT

from .conftest import _docker_ok

IMAGE = "localstack/localstack:3.8.1"
ACCOUNT = "000000000000"
BUCKET, QUEUE, DLQ = "ragassist-docs", "ragassist-ingest", "ragassist-ingest-dlq"
INIT_PATH = "/etc/localstack/init/ready.d/init.sh"


@dataclass
class LocalStack:
    base: str
    container: object

    def request(
        self, method: str, path: str = "/", data: dict[str, str] | None = None, service: str = "sqs"
    ) -> ET.Element:
        body = urllib.parse.urlencode(data).encode() if data else None
        req = urllib.request.Request(f"{self.base}{path}", data=body, method=method)
        if body:
            req.add_header("Content-Type", "application/x-www-form-urlencoded")
        # LocalStack routes by the credential scope: it must name the service being called.
        req.add_header(
            "Authorization",
            f"AWS4-HMAC-SHA256 Credential=test/20260101/us-east-1/{service}/aws4_request, SignedHeaders=host, Signature=x",
        )
        with urllib.request.urlopen(req, timeout=15) as response:  # noqa: S310
            text = response.read().decode()
        return ET.fromstring(re.sub(r'\sxmlns="[^"]+"', "", text, count=1))

    def sqs(self, **params: str) -> ET.Element:
        return self.request("POST", "/", {"Version": "2012-11-05", **params})

    def queue_url(self, name: str) -> str:
        return f"{self.base}/{ACCOUNT}/{name}"

    def attributes(self, name: str) -> dict[str, str]:
        root = self.sqs(
            Action="GetQueueAttributes", QueueUrl=self.queue_url(name), **{"AttributeName.1": "All"}
        )
        return {a.findtext("Name"): a.findtext("Value") for a in root.iter("Attribute")}

    def receive(self, name: str) -> list[str]:
        root = self.sqs(
            Action="ReceiveMessage",
            QueueUrl=self.queue_url(name),
            VisibilityTimeout="0",
            MaxNumberOfMessages="1",
        )
        return [m.findtext("Body") for m in root.iter("Message")]

    def buckets(self) -> list[str]:
        return [name.text for name in self.request("GET", service="s3").iter("Name")]

    def queue_names(self) -> list[str]:
        root = self.sqs(Action="ListQueues")
        return [url.text.rsplit("/", 1)[-1] for url in root.iter("QueueUrl")]


@pytest.fixture(scope="module")
def localstack() -> Iterator[LocalStack]:
    if not _docker_ok():
        pytest.skip("Docker is not available: integration tier skipped")
    from testcontainers.core.container import DockerContainer

    container = (
        DockerContainer(IMAGE)
        .with_env("SERVICES", "s3,sqs")
        .with_env("DEBUG", "0")
        .with_exposed_ports(4566)
        .with_volume_mapping(str(REPO_ROOT / "infra" / "localstack" / "init.sh"), INIT_PATH, "ro")
    )
    container.start()
    try:
        stack = LocalStack(
            f"http://{container.get_container_host_ip()}:{container.get_exposed_port(4566)}",
            container,
        )
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:  # wait until the init script has created its resources
            try:
                if (
                    BUCKET in stack.buckets()
                    and DLQ in stack.queue_names()
                    and QUEUE in stack.queue_names()
                ):
                    break
            except (urllib.error.URLError, OSError, ET.ParseError):
                pass
            time.sleep(1)
        else:
            logs = container.get_logs()
            pytest.fail(
                "init.sh did not create its resources in 120 s.\n"
                + (logs[0] or b"").decode()[-2000:]
            )
        yield stack
    finally:
        container.stop()


class TestInitScript:
    def test_the_documents_bucket_exists(self, localstack: LocalStack) -> None:
        assert BUCKET in localstack.buckets()

    def test_ingest_queue_and_dead_letter_queue_exist(self, localstack: LocalStack) -> None:
        assert {QUEUE, DLQ} <= set(localstack.queue_names())

    def test_ingest_queue_redrives_to_the_dlq_after_three_receives(
        self, localstack: LocalStack
    ) -> None:
        policy = json.loads(localstack.attributes(QUEUE)["RedrivePolicy"])
        assert policy["deadLetterTargetArn"] == f"arn:aws:sqs:us-east-1:{ACCOUNT}:{DLQ}"
        assert int(policy["maxReceiveCount"]) == 3

    def test_the_dlq_itself_does_not_redrive(self, localstack: LocalStack) -> None:
        assert "RedrivePolicy" not in localstack.attributes(DLQ)

    def test_the_script_is_idempotent(self, localstack: LocalStack) -> None:
        before = (
            localstack.buckets(),
            sorted(localstack.queue_names()),
            localstack.attributes(QUEUE)["RedrivePolicy"],
        )
        exit_code, _ = localstack.container.exec(["bash", INIT_PATH])  # type: ignore[attr-defined]
        after = (
            localstack.buckets(),
            sorted(localstack.queue_names()),
            localstack.attributes(QUEUE)["RedrivePolicy"],
        )
        assert exit_code == 0 and before == after

    def test_a_poison_message_lands_in_the_dlq_after_three_failed_receives(
        self, localstack: LocalStack
    ) -> None:
        body = f"poison-{time.time_ns()}"
        localstack.sqs(Action="SendMessage", QueueUrl=localstack.queue_url(QUEUE), MessageBody=body)
        for attempt in range(3):  # a worker that keeps failing: receive, never delete
            assert localstack.receive(QUEUE) == [body], f"receive #{attempt + 1}"
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            localstack.receive(QUEUE)  # the 4th receive triggers the move
            if localstack.receive(DLQ) == [body]:
                break
            time.sleep(0.5)
        else:
            pytest.fail("message never reached the dead-letter queue")
        assert localstack.receive(QUEUE) == []
