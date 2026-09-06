"""Per-vertical extraction schemas. Swapping this is swapping the vertical.

The registry exists so anything that needs to know a schema's shape without
importing the vertical directly can ask for it by name. The first use is
field ordering: Postgres JSONB does not preserve key order, so a stored
extraction comes back alphabetised-by-length and the detail screen would
show `due_on` above `supplier` unless something imposes the schema's own
order back onto it.
"""

from pydantic import BaseModel

from app.extraction.schemas.invoice import SCHEMA_NAME as INVOICE
from app.extraction.schemas.invoice import Invoice

SCHEMAS: dict[str, type[BaseModel]] = {INVOICE: Invoice}


def field_order(schema_name: str) -> list[str]:
    """Top-level field names in the order the schema declares them.

    Empty for an unknown schema, which callers treat as "no opinion" rather
    than as an error: a stored extraction from a schema this build no longer
    has should still be readable.
    """
    model = SCHEMAS.get(schema_name)
    return list(model.model_fields) if model else []
