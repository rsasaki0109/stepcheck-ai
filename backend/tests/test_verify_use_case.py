import pytest

from stepcheck_providers import (
    ImagePayload,
    StepStatus,
    StepVerdict,
    VerificationInput,
    VisionProvider,
)

from app.application import VerifyProcedureUseCase


class _StubProvider(VisionProvider):
    name = "stub"

    def __init__(self, verdicts):
        self._verdicts = verdicts
        self.received: VerificationInput | None = None

    async def verify(self, request):
        self.received = request
        return self._verdicts


async def test_builds_report_with_summary():
    verdicts = [
        StepVerdict(1, StepStatus.COMPLETED, 0.9, "done"),
        StepVerdict(2, StepStatus.NOT_DONE, 0.8, "missing"),
    ]
    use_case = VerifyProcedureUseCase(_StubProvider(verdicts))

    report = await use_case.execute(
        markdown="1. a\n2. b",
        images=[ImagePayload(data=b"x")],
    )

    assert report.provider == "stub"
    assert report.summary.total == 2
    assert report.summary.completed == 1
    assert report.summary.not_done == 1
    assert report.results[0].step.text == "a"


async def test_missing_verdict_is_filled_with_unknown():
    # Provider only returns a verdict for step 1; step 2 must default to unknown.
    use_case = VerifyProcedureUseCase(
        _StubProvider([StepVerdict(1, StepStatus.COMPLETED, 0.9, "done")])
    )
    report = await use_case.execute(markdown="1. a\n2. b", images=[ImagePayload(b"x")])
    assert report.results[1].status is StepStatus.UNKNOWN
    assert report.summary.unknown == 1


async def test_context_is_forwarded_to_provider():
    provider = _StubProvider([])
    use_case = VerifyProcedureUseCase(provider)
    await use_case.execute(markdown="1. a", images=[ImagePayload(b"x")], context="hint")
    assert provider.received.context == "hint"
