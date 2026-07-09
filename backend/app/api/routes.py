"""HTTP routes for StepCheck AI."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from stepcheck_providers import ImagePayload, available_providers

from ..application import VerifyProcedureUseCase
from ..application.markdown_parser import ProcedureParseError
from ..config import Settings, get_settings
from .dependencies import get_verify_use_case
from .schemas import ProvidersOut, VerificationReportOut

router = APIRouter()


@router.get("/health", tags=["meta"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/providers", response_model=ProvidersOut, tags=["meta"])
async def providers(settings: Settings = Depends(get_settings)) -> ProvidersOut:
    return ProvidersOut(active=settings.provider, available=available_providers())


@router.post(
    "/verify",
    response_model=VerificationReportOut,
    tags=["verification"],
    summary="Verify a Markdown procedure against uploaded images",
)
async def verify(
    procedure: str = Form(..., description="The work procedure in Markdown"),
    images: list[UploadFile] = File(..., description="One or more work images"),
    context: str | None = Form(None, description="Optional free-form hint"),
    use_case: VerifyProcedureUseCase = Depends(get_verify_use_case),
    settings: Settings = Depends(get_settings),
) -> VerificationReportOut:
    if len(images) > settings.max_images:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Too many images (max {settings.max_images}).",
        )

    payloads: list[ImagePayload] = []
    for upload in images:
        data = await upload.read()
        if not data:
            continue
        if len(data) > settings.max_image_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"Image '{upload.filename}' exceeds the size limit.",
            )
        payloads.append(
            ImagePayload(data=data, media_type=upload.content_type or "image/png")
        )

    if not payloads:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one non-empty image is required.",
        )

    try:
        report = await use_case.execute(
            markdown=procedure, images=payloads, context=context
        )
    except ProcedureParseError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    return VerificationReportOut.from_domain(report)
