import pytest

from stepcheck_providers import (
    ImagePayload,
    ProcedureStep,
    StepStatus,
    VerificationInput,
    create_provider,
)


def _input(n_steps: int, n_images: int) -> VerificationInput:
    return VerificationInput(
        steps=[ProcedureStep(index=i + 1, text=f"step {i + 1}") for i in range(n_steps)],
        images=[ImagePayload(data=b"x", media_type="image/png") for _ in range(n_images)],
    )


async def test_returns_one_verdict_per_step():
    provider = create_provider("mock")
    verdicts = await provider.verify(_input(5, 1))
    assert [v.index for v in verdicts] == [1, 2, 3, 4, 5]


async def test_is_deterministic():
    provider = create_provider("mock")
    first = await provider.verify(_input(4, 2))
    second = await provider.verify(_input(4, 2))
    assert [(v.status, v.confidence) for v in first] == [
        (v.status, v.confidence) for v in second
    ]


async def test_no_images_yields_unknown():
    provider = create_provider("mock")
    verdicts = await provider.verify(_input(3, 0))
    assert all(v.status is StepStatus.UNKNOWN for v in verdicts)
    assert all(v.confidence == 0.0 for v in verdicts)


def test_confidence_bounds_are_enforced():
    from stepcheck_providers import StepVerdict

    with pytest.raises(ValueError):
        StepVerdict(index=1, status=StepStatus.COMPLETED, confidence=1.5, reason="x")
