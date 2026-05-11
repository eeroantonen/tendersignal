from __future__ import annotations

from typing import Any

from tendersignal.text import first_text


def first_available(raw: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = first_text(raw.get(key))
        if value:
            return value
    return ""


def build_hilma_notice_url(raw: dict[str, Any], language: str = "fi") -> str:
    notice_id = first_available(raw, "noticeId", "notice_id", "hilmaNoticeId")
    procedure_id = first_available(raw, "procedureId", "eNoticeProcedureId")
    old_project_id = first_available(raw, "oldProcurementProjectId", "procurementProjectId", "projectId")
    app_url = "https://www.hankintailmoitukset.fi"
    lang = (language or "fi").lower()[:2]

    is_eforms = bool(raw.get("isEForms")) or str(first_available(raw, "id") or "").startswith("EF-")
    if is_eforms and procedure_id and notice_id:
        return f"{app_url}/{lang}/public/procedure/{procedure_id}/enotice/{notice_id}"
    if old_project_id and notice_id and str(old_project_id) != "0":
        return f"{app_url}/{lang}/public/procurement/{old_project_id}/notice/{notice_id}"

    explicit_url = first_available(raw, "url", "sourceUrl", "noticeUrl", "hilmaUrl")
    if explicit_url:
        return explicit_url
    if notice_id:
        return f"{app_url}/{lang}/search?text={notice_id}"
    notice_number = first_available(raw, "noticeNumber", "id") or ""
    return f"{app_url}/{lang}/search?text={notice_number}"
