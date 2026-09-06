"""Workflow package: importing it registers every workflow.

Add new workflows here so the worker sees them:

    from app.workflows import document_ingest  # noqa: F401
"""

from app.workflows import document_ingest, webhook_example  # noqa: F401
