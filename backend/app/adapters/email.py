"""EmailAdapter: send the approved instruction to a person.

The lowest-tech real adapter, and the one most clients can actually use on
day one: no integration project, no API credentials, just the decision and
its citations in somebody's inbox. Uses the Resend client the template
already wires up, which no-ops when RESEND_API_KEY is unset.
"""

from html import escape

from app.adapters.base import AdapterRequest, AdapterResponse, register_adapter
from app.config import settings
from app.logging import get_logger

log = get_logger(__name__)


class EmailAdapter:
    name = "email"

    def execute(self, request: AdapterRequest) -> AdapterResponse:
        from app.email.client import send_email

        to = settings.execution_email_to or settings.email_from
        subject = f"{request.action}: {request.supplier} {request.reference}"
        rows = [
            ("Action", request.action),
            ("Supplier", request.supplier),
            ("Reference", request.reference),
            ("Amount", f"{request.amount} {request.currency}"),
            ("Assign to", request.assignee_hint or "not specified"),
        ]
        html = "".join(
            [
                "<table>",
                *(f"<tr><td><b>{label}</b></td><td>{escape(str(value))}</td></tr>"
                  for label, value in rows),
                "</table>",
                f"<p>{escape(request.note)}</p>" if request.note else "",
                f"<p><small>Decision {request.decision_id}</small></p>",
            ]
        )
        sent = send_email(to=to, subject=subject, html=html)
        # A skipped send (no RESEND_API_KEY) is not a success. Reporting it as
        # one would record an instruction nobody received.
        return AdapterResponse(
            ok=sent,
            external_reference=f"email-{request.decision_id}",
            detail={"to": to, "subject": subject, "dispatched": sent},
        )


register_adapter(EmailAdapter())
