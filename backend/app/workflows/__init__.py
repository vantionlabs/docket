"""Workflow package: importing it registers every workflow.

Add new workflows here so the worker sees them:

    from app.workflows import document_ingest  # noqa: F401
"""

from app.workflows import (  # noqa: F401
    decision_execute,
    document_decide,
    document_ingest,
    webhook_document,
    webhook_example,
)
