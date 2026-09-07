"""Deterministic factories for policy corpora and labelled invoices.

**No model calls.** Everything here is templates plus seeded randomness, so
generating a dataset costs nothing and the same seed gives the same corpus
every time. An eval set that is expensive to rebuild is one nobody rebuilds.

**Invoices are generated backwards.** Pick the outcome and the reason first,
then synthesize a document that has that property. Labelling documents after
the fact is slow, needs a human, and produces exactly the labels the labeller
happened to think of. Generating from the label makes ground truth free and
the distribution controllable: you decide how many cases are over-threshold,
how many have an unknown supplier, how many do not add up.

**The corpus needs distractors or it proves nothing.** Retrieval over ten
clauses with top_k=8 returns most of the policy and cannot fail. What makes
ranking miss things is a corpus full of clauses that look relevant and are
not: a travel policy with its own threshold table, a superseded version of a
rule, a capex approval matrix shaped like the procurement one. Those are
generated on purpose.
"""

import random
import zlib
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

# --- vocabulary ---------------------------------------------------------

APPROVED_SUPPLIERS = [
    "Contoso Cleaning Services BV",
    "Fabrikam Office Supplies BV",
    "Northwind IT Partners BV",
    "Tailspin Facilities BV",
    "Woodgrove Legal BV",
    "Proseware Print & Signage BV",
    "Adventure Works Catering BV",
    "Coho Vineyard Hospitality BV",
    "Lucerne Publishing BV",
    "Trey Research BV",
]

UNKNOWN_SUPPLIERS = [
    "Litware Consulting Group BV",
    "Wingtip Toys Trading BV",
    "Fourth Coffee Supplies BV",
    "Graphic Design Institute BV",
    "Blue Yonder Logistics BV",
]

COST_CENTRES = ["FAC-01", "OPS-04", "IT-01", "STR-02", "MKT-03", "HR-02", "FIN-01"]

LINE_ITEMS = [
    ("Office cleaning, monthly", Decimal("620.00")),
    ("Consumables restock", Decimal("22.50")),
    ("Height-adjustable desk", Decimal("480.00")),
    ("Desk chair, ergonomic", Decimal("265.00")),
    ("Monitor arm, dual", Decimal("95.00")),
    ("HVAC maintenance visit", Decimal("410.00")),
    ("Filter replacement set", Decimal("48.00")),
    ("Cloud hosting, quarterly", Decimal("8400.00")),
    ("Strategy workshop facilitation", Decimal("1750.00")),
    ("Legal review, hourly", Decimal("295.00")),
    ("Printed brochures, per 500", Decimal("340.00")),
    ("Catering, per head", Decimal("28.50")),
    ("Laptop, developer spec", Decimal("2150.00")),
    ("Security audit, fixed fee", Decimal("14500.00")),
    ("Translation, per 1000 words", Decimal("115.00")),
]

DUTCH_CITIES = [
    ("Amsterdam", "1017 CB"), ("Rotterdam", "3012 NJ"), ("Utrecht", "3511 ED"),
    ("Eindhoven", "5628 DH"), ("Groningen", "9711 AB"), ("Den Haag", "2511 CV"),
]

VAT_RATES = [Decimal("0.21"), Decimal("0.09"), Decimal("0")]


# --- the labelled scenarios ---------------------------------------------


@dataclass(frozen=True)
class Scenario:
    """One way an invoice can go, and what a correct decision must consider."""

    key: str
    expected: str
    dimensions: tuple[str, ...]
    note: str
    weight: int = 1
    """Relative frequency. Real intake is mostly clean, so clean cases are
    common and nasties are rare; an eval set with an even split would tune
    the pipeline for a world that does not exist."""


SCENARIOS: tuple[Scenario, ...] = (
    Scenario(
        "clean_under_threshold", "auto_approve",
        ("amount", "supplier", "purchase_order"),
        "Approved supplier, PO present, under the cost centre limit.",
        weight=8,
    ),
    Scenario(
        "over_threshold", "route_for_approval",
        ("amount",),
        "Above the cost centre limit, so somebody senior has to sign.",
        weight=5,
    ),
    Scenario(
        "no_purchase_order", "route_for_approval",
        ("purchase_order", "amount"),
        "Above EUR 500 with no PO: retrospective authorisation.",
        weight=4,
    ),
    Scenario(
        "unknown_supplier", "route_for_approval",
        ("supplier",),
        "Not on the approved list, so Procurement checks it first.",
        weight=3,
    ),
    Scenario(
        "arithmetic_wrong", "reject",
        ("vat",),
        "Lines do not sum to the subtotal. Return to supplier.",
        weight=2,
    ),
    Scenario(
        "illegal_vat_rate", "reject",
        ("vat",),
        "Implied VAT rate is not a Dutch statutory rate.",
        weight=1,
    ),
    Scenario(
        "foreign_currency", "route_for_approval",
        ("currency", "amount"),
        "Not in euro: Finance converts and records the rate.",
        weight=2,
    ),
    Scenario(
        "short_payment_terms", "route_for_approval",
        ("payment_terms", "supplier"),
        "Payment demanded inside 14 days, which policy calls a fraud indicator.",
        weight=2,
    ),
    Scenario(
        "duplicate_invoice", "reject",
        ("duplicate",),
        "Same supplier and invoice number as one already paid.",
        weight=2,
    ),
    Scenario(
        "over_board_threshold", "route_for_approval",
        ("amount",),
        "Above EUR 50,000: two board members, minuted.",
        weight=1,
    ),
)


@dataclass
class Invoice:
    """A generated invoice and the label it was generated from."""

    filename: str
    markdown: str
    scenario: Scenario
    supplier: str
    total_incl_vat: Decimal
    currency: str
    invoice_number: str
    duplicate_of: str | None = None
    tags: list[str] = field(default_factory=list)


def _stable(text: str) -> int:
    """A hash that survives a restart.

    `hash()` on a str is salted per process, so using it would make the
    "deterministic" corpus different on every run and quietly invalidate any
    comparison between eval passes.
    """
    return zlib.crc32(text.encode())


def _money(value: Decimal) -> str:
    return f"{value:.2f}"


def _lines(rng: random.Random, target_subtotal: Decimal) -> list[tuple[str, int, Decimal, Decimal]]:
    """Line items that sum to roughly `target_subtotal`, exactly."""
    picks = rng.sample(LINE_ITEMS, k=rng.randint(1, 3))
    lines: list[tuple[str, int, Decimal, Decimal]] = []
    remaining = target_subtotal

    for index, (description, unit) in enumerate(picks):
        last = index == len(picks) - 1
        if last:
            # Absorb the remainder into a quantity of one, so the lines add up
            # exactly. An eval set whose "clean" invoices fail the arithmetic
            # check would be testing the wrong thing.
            amount = remaining.quantize(Decimal("0.01"))
            lines.append((description, 1, amount, amount))
        else:
            quantity = rng.randint(1, 6)
            amount = (unit * quantity).quantize(Decimal("0.01"))
            if amount >= remaining:
                continue
            remaining -= amount
            lines.append((description, quantity, unit, amount))

    return lines or [("Services rendered", 1, target_subtotal, target_subtotal)]


def render_invoice(
    *,
    supplier: str,
    number: str,
    issued: date,
    due: date,
    po: str | None,
    cost_centre: str,
    currency: str,
    lines: list[tuple[str, int, Decimal, Decimal]],
    subtotal: Decimal,
    vat: Decimal,
    total: Decimal,
    terms: str,
) -> str:
    city, postcode = DUTCH_CITIES[_stable(supplier) % len(DUTCH_CITIES)]
    vat_id = (
        f"NL{_stable(supplier) % 9000 + 1000}."
        f"{_stable(number) % 90 + 10}.{_stable(number) % 900 + 100}.B01"
    )
    rows = "\n".join(
        f"| {d} | {q} | {_money(u)} | {_money(a)} |" for d, q, u, a in lines
    )
    return f"""# INVOICE

**{supplier}**
{city}, {postcode}
VAT: {vat_id}

Bill to: Northwind BV, Herengracht 500, 1017 CB Amsterdam

| | |
|---|---|
| Invoice number | {number} |
| Invoice date | {issued:%-d %B %Y} |
| Due date | {due:%-d %B %Y} |
| Purchase order | {po or "not supplied"} |
| Cost centre | {cost_centre} |
| Payment terms | {terms} |

## Items

| Description | Qty | Unit price | Amount |
|---|---|---|---|
{rows}

Subtotal excluding VAT: {currency} {_money(subtotal)}
VAT: {currency} {_money(vat)}
**Total including VAT: {currency} {_money(total)}**
"""


# --- the corpus ---------------------------------------------------------

CATEGORIES = [
    "IT hardware", "IT software and licences", "facilities and maintenance",
    "professional services", "legal services", "marketing and print",
    "catering and hospitality", "training and development", "recruitment",
    "insurance", "telecoms", "logistics and freight", "office consumables",
    "security services", "translation and localisation",
]

ROLES = [
    "the cost centre owner", "a department head", "the Finance Director",
    "the Chief Operating Officer", "two board members",
]

THRESHOLDS = [
    Decimal("500"), Decimal("1000"), Decimal("2500"), Decimal("5000"),
    Decimal("10000"), Decimal("25000"), Decimal("50000"), Decimal("100000"),
]


def _authority_clauses(prefix: str, roles: list[str], thresholds: list[Decimal]) -> list[str]:
    """A threshold ladder. Several documents have one, which is the point."""
    lines = []
    previous = Decimal(0)
    for index, amount in enumerate(thresholds):
        role = roles[min(index, len(roles) - 1)]
        lines.append(
            f"- Above EUR {previous:,.0f} and up to EUR {amount:,.0f}: {role} may approve."
            if previous
            else f"- Up to EUR {amount:,.0f}: {role} may approve."
        )
        previous = amount
    lines.append(f"- Above EUR {previous:,.0f}: {roles[-1]} must approve, and it must be minuted.")
    return [f"## {prefix}\n\n" + "\n".join(lines)]


def build_corpus(seed: int = 7) -> dict[str, str]:
    """A policy corpus with enough in it for ranking to fail.

    Seven documents. One of them is the policy that actually governs supplier
    invoices; the rest exist to be plausibly wrong. The travel policy and the
    capex matrix both carry threshold ladders that look exactly like the
    procurement one and apply to something else, and a superseded version of
    the procurement policy carries the *old* thresholds. Those are the
    retrievals that produce a confident wrong answer, which is what the
    coverage layer is there to survive.
    """
    rng = random.Random(seed)
    docs: dict[str, list[str]] = {}

    # 1. The policy that governs supplier invoices.
    procurement = [
        "# Northwind BV procurement policy\n\nVersion 4.0, in force from 1 January 2026. "
        "This policy governs the approval and payment of supplier invoices. Where a clause "
        "conflicts with a signed contract, the signed contract prevails and the case goes "
        "to Finance.",
        "## 1. Scope\n\nThis policy applies to every invoice for goods or services delivered "
        "to Northwind BV or any of its subsidiaries. It does not apply to employee expense "
        "claims, which are governed by the travel and expenses policy, or to intercompany "
        "recharges.",
        "## 2. Purchase orders\n\nEvery purchase above EUR 500 excluding VAT requires a "
        "purchase order raised before the goods or services are ordered. An invoice above "
        "EUR 500 that carries no purchase order number may not be approved for payment and "
        "must be routed to the cost centre owner for retrospective authorisation.\n\n"
        "Purchases at or below EUR 500 excluding VAT do not require a purchase order.",
    ]
    procurement += _authority_clauses(
        "3. Spend thresholds and approval authority", ROLES, THRESHOLDS[1:6]
    )
    procurement += [
        "### 3.1 Self-approval\n\nNo individual may approve an invoice that they themselves "
        "submitted or that names them as the requester.",
        "## 4. Approved suppliers\n\nInvoices from suppliers on the approved supplier list "
        "may be processed normally. An invoice from a supplier not on the approved list must "
        "be routed to Procurement for a supplier check before payment, whatever the amount.",
        "## 5. Payment terms\n\nThe standard payment term is 30 days from the invoice date. "
        "A supplier demanding payment in fewer than 14 days must be referred to Finance, as "
        "shortened terms are a common indicator of invoice fraud.\n\nEarly settlement "
        "discounts may be taken where the contract provides for them.",
        "## 6. VAT and arithmetic\n\nAn invoice whose stated totals do not add up may not be "
        "approved. It must be returned to the supplier for a corrected invoice. Only the "
        "Dutch statutory VAT rates of 0 percent, 9 percent and 21 percent are acceptable on "
        "a domestic invoice.",
        "## 7. Duplicate invoices\n\nAn invoice bearing a supplier and invoice number already "
        "recorded against a paid invoice is a duplicate and must be rejected. Where a supplier "
        "has reissued a corrected invoice, the original must be credited first.",
        "## 8. Currency\n\nInvoices are payable in euro. An invoice presented in another "
        "currency must be routed to Finance, which converts at the rate on the invoice date "
        "and records the rate used.",
        "## 9. Escalation\n\nWhere this policy does not settle a case, or where two clauses "
        "appear to conflict, the invoice is routed to Finance rather than approved. An "
        "approver who is unsure escalates. Escalation is never a fault.",
    ]
    docs["procurement-policy.md"] = procurement

    # 2. Delegation of authority: one clause per category, all near-identical.
    doa = ["# Delegation of authority matrix\n\nApproval limits by category, in force from "
           "1 January 2026. Read together with the procurement policy, which governs "
           "supplier invoices."]
    for index, category in enumerate(CATEGORIES):
        limit = THRESHOLDS[index % len(THRESHOLDS)]
        role = ROLES[index % len(ROLES)]
        doa.append(
            f"## {index + 1}. {category.title()}\n\nCommitted spend on {category} up to "
            f"EUR {limit:,.0f} per order may be approved by {role}. Above that limit the "
            f"next authority in the ladder approves. Recurring commitments are assessed on "
            f"their annual value, not the value of a single invoice."
        )
    docs["delegation-of-authority.md"] = doa

    # 3. THE DISTRACTOR. Its own threshold ladder, for something else entirely.
    travel = [
        "# Travel and expenses policy\n\nVersion 2.2. This policy governs employee expense "
        "claims. It does NOT govern supplier invoices, which are covered by the procurement "
        "policy.",
    ]
    travel += _authority_clauses(
        "2. Expense claim approval limits",
        ["the line manager", "a department head", "the Finance Director"],
        [Decimal("250"), Decimal("1500"), Decimal("7500")],
    )
    travel += [
        "## 3. Receipts\n\nEvery expense claim above EUR 25 requires an itemised receipt. A "
        "claim without a receipt may not be approved and must be returned to the claimant.",
        "## 4. Currency on expense claims\n\nExpenses incurred in another currency are "
        "reimbursed in euro at the corporate card rate on the transaction date.",
        "## 5. Payment of claims\n\nApproved claims are paid with the next payroll run, "
        "normally within 30 days.",
    ]
    for index, category in enumerate(CATEGORIES[:8]):
        travel.append(
            f"### 5.{index + 1} {category.title()}\n\nExpenditure on {category} may not be "
            f"claimed as an expense where a purchase order route exists. Claims of this kind "
            f"are returned to the claimant and raised as a purchase instead."
        )
    docs["travel-and-expenses.md"] = travel

    # 4. Another ladder, for capital rather than operating spend.
    capex = ["# Capital expenditure approval\n\nVersion 1.4. Governs capitalised assets. "
             "Operating spend follows the procurement policy."]
    capex += _authority_clauses(
        "2. Capital approval limits",
        ["a department head", "the Finance Director", "the board"],
        [Decimal("5000"), Decimal("50000"), Decimal("250000")],
    )
    capex += [
        "## 3. Business case\n\nAny capital request above EUR 25,000 requires a written "
        "business case with a payback calculation.",
        "## 4. Asset register\n\nCapitalised items are entered in the asset register within "
        "30 days of delivery.",
    ]
    docs["capital-expenditure.md"] = capex

    # 5. The nastiest distractor: the OLD thresholds, still in the corpus.
    superseded = [
        "# Northwind BV procurement policy (SUPERSEDED)\n\nVersion 3.1, in force from "
        "1 January 2024 until 31 December 2025. Retained for audit of invoices paid in that "
        "period. Do not apply to current invoices.",
    ]
    superseded += _authority_clauses(
        "3. Spend thresholds and approval authority (2024 to 2025)",
        ROLES,
        [Decimal("2500"), Decimal("15000"), Decimal("75000")],
    )
    superseded += [
        "## 2. Purchase orders (2024 to 2025)\n\nEvery purchase above EUR 1,000 excluding "
        "VAT required a purchase order raised before the goods or services were ordered.",
        "## 5. Payment terms (2024 to 2025)\n\nThe standard payment term was 45 days from "
        "the invoice date.",
    ]
    docs["procurement-policy-2024-superseded.md"] = superseded

    # 6. Contracting standards: overlaps on terms and currency.
    contracting = [
        "# Contracting standards\n\nVersion 1.9. How Northwind BV contracts with suppliers.",
        "## 1. Standard terms\n\nNorthwind BV contracts on 30 day payment terms unless the "
        "Finance Director agrees otherwise in writing.",
        "## 2. Currency of contract\n\nContracts are denominated in euro. A contract in "
        "another currency requires Finance approval at signature and carries an agreed "
        "conversion mechanism.",
        "## 3. Indexation\n\nMulti-year contracts may carry annual indexation capped at CBS "
        "consumer price inflation.",
        "## 4. Termination\n\nStandard notice is three months. Auto-renewal clauses require "
        "explicit Finance sign-off before signature.",
        "## 5. Liability\n\nSupplier liability is capped at the contract value unless the "
        "supplier holds professional indemnity cover.",
    ]
    for index, category in enumerate(CATEGORIES[:10]):
        contracting.append(
            f"### 5.{index + 1} {category.title()}\n\nContracts for {category} carry the "
            f"standard terms above. Deviations are recorded in the contract register with "
            f"the reason and the approver."
        )
    docs["contracting-standards.md"] = contracting

    # 7. The approved supplier list.
    suppliers = [
        "# Approved supplier list\n\nMaintained by Procurement. In force from 1 January 2026. "
        "An invoice from a supplier not on this list is routed to Procurement for a supplier "
        "check before payment.",
    ]
    for index, supplier in enumerate(APPROVED_SUPPLIERS):
        category = CATEGORIES[index % len(CATEGORIES)]
        suppliers.append(
            f"## {index + 1}. {supplier}\n\nApproved for {category}. Contracted on standard "
            f"30 day terms. Reviewed annually by Procurement."
        )
    docs["approved-suppliers.md"] = suppliers

    # No rng.shuffle(CATEGORIES) here. It used to be, and it mutated a
    # module-level list in place, so build_corpus() returned something
    # different on its second call in the same process: a deterministic
    # generator that was not. `rng` stays for callers that pass a seed to
    # vary the invoice set, which is where variation belongs.
    del rng
    return {name: "\n\n".join(sections) + "\n" for name, sections in docs.items()}


# --- invoices, generated from their label -------------------------------


def build_invoice(rng: random.Random, scenario: Scenario, index: int) -> Invoice:
    """Synthesize an invoice that has the property `scenario` names.

    Everything starts from a clean, compliant invoice and then exactly one
    thing is broken, so a case tests the rule it is labelled for rather than
    an accidental pile-up of three problems.
    """
    supplier = rng.choice(APPROVED_SUPPLIERS)
    currency = "EUR"
    number = f"{supplier.split()[0][:3].upper()}-2026-{4000 + index}"
    issued = date(2026, rng.randint(1, 9), rng.randint(1, 28))
    due = issued.replace(day=min(issued.day, 28)) + timedelta(days=30)
    po = f"PO-2026-{1000 + index}"
    cost_centre = rng.choice(COST_CENTRES)
    terms = "30 days net"
    vat_rate = Decimal("0.21")
    subtotal = Decimal(rng.randrange(20000, 80000)) / Decimal(100)  # 200 - 800
    tags: list[str] = []
    duplicate_of = None

    match scenario.key:
        case "clean_under_threshold":
            pass
        case "over_threshold":
            subtotal = Decimal(rng.randrange(200000, 800000)) / Decimal(100)
        case "no_purchase_order":
            po = None
            subtotal = Decimal(rng.randrange(100000, 400000)) / Decimal(100)
        case "unknown_supplier":
            supplier = rng.choice(UNKNOWN_SUPPLIERS)
            number = f"{supplier.split()[0][:3].upper()}-2026-{4000 + index}"
        case "foreign_currency":
            currency = rng.choice(["USD", "GBP", "CHF"])
            vat_rate = Decimal("0")
            subtotal = Decimal(rng.randrange(100000, 900000)) / Decimal(100)
        case "short_payment_terms":
            due = issued + timedelta(days=rng.choice([5, 7, 10]))
            terms = f"{(due - issued).days} days net, urgent"
        case "over_board_threshold":
            subtotal = Decimal(rng.randrange(6000000, 12000000)) / Decimal(100)
        case "duplicate_invoice":
            # Points at an earlier number in the same run, so the pair is real.
            duplicate_of = f"{supplier.split()[0][:3].upper()}-2026-{4000 + max(index - 1, 0)}"
            number = duplicate_of
            tags.append("duplicate")

    lines = _lines(rng, subtotal)
    vat = (subtotal * vat_rate).quantize(Decimal("0.01"))
    total = subtotal + vat

    if scenario.key == "arithmetic_wrong":
        # Break the sum, not the lines: the stated subtotal disagrees with
        # what the lines add up to, which is what a real bad invoice looks
        # like and what check_invoice is written to catch.
        total = total + Decimal(rng.randrange(10000, 40000)) / Decimal(100)
        tags.append("lines do not sum to the stated total")
    elif scenario.key == "illegal_vat_rate":
        vat = (subtotal * Decimal("0.155")).quantize(Decimal("0.01"))
        total = subtotal + vat
        tags.append("VAT rate is not a Dutch statutory rate")

    markdown = render_invoice(
        supplier=supplier,
        number=number,
        issued=issued,
        due=due,
        po=po,
        cost_centre=cost_centre,
        currency=currency,
        lines=lines,
        subtotal=subtotal,
        vat=vat,
        total=total,
        terms=terms,
    )

    return Invoice(
        filename=f"{index:04d}-{scenario.key}.md",
        markdown=markdown,
        scenario=scenario,
        supplier=supplier,
        total_incl_vat=total,
        currency=currency,
        invoice_number=number,
        duplicate_of=duplicate_of,
        tags=tags,
    )


def build_invoices(count: int, seed: int = 11) -> list[Invoice]:
    """A labelled set, weighted the way real intake actually arrives.

    Mostly clean, with the nasties rare. An evenly split set would tune the
    pipeline for a world where one invoice in ten is fraudulent.
    """
    rng = random.Random(seed)
    population = [s for s in SCENARIOS for _ in range(s.weight)]
    return [build_invoice(rng, rng.choice(population), index) for index in range(count)]
