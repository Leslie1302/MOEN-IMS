"""
Does this release fall within the Bill of Quantity?

The approval memo asks the Ag. Director to authorise a release. Until now it
asked him to do that on trust: the memo listed what was being released and said
nothing about whether the contract had room for it. The BoQ balance lived on a
different page, and checking it was a thing a careful officer did and a busy one
did not.

This computes the answer so the memo can state it. Per material line:

    contract quantity - already drawn down = balance before
    balance before - this release        = balance after

A negative balance after is an **over-issuance**: the release would draw more
than the contract allows. That does not stop the release. The Ministry already
has a process for it — `BoQOverissuanceJustification` — and a release can be
legitimately over-issued (a pole replaced after storm damage is not in the BoQ).
So this names the exception on the document and leaves the decision with the
signatory, which is the right place for it. Software that silently blocked a
release the Ministry had good reason to make would be worked around within a
week, and the workaround would be off the record.

**Unmatched lines are reported, never hidden.** A material with no BoQ line at
all is the more interesting failure — it means either a data problem or a
release against no contract — and the memo says so rather than quietly
reconciling the lines that happen to match.
"""

import logging
from decimal import Decimal, InvalidOperation

logger = logging.getLogger(__name__)


def _dec(value):
    """Coerce a float/str/Decimal/None to Decimal without float noise.

    BoQ quantities are FloatFields and MaterialOrder.quantity is a Decimal;
    subtracting one from the other directly raises TypeError, and going via
    float reintroduces the rounding the Decimal was there to avoid.
    """
    if value is None:
        return Decimal('0')
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal('0')


def _boq_for(order):
    """The BoQ line this order draws against, or None.

    Prefers the explicit link when the BoQ re-match has set one — that is a
    decision someone made and it must win over any guess made here. Otherwise
    match on item code plus community, case-insensitively: the two tables now
    agree on casing, but `iexact` costs nothing and a future import that
    disagrees should degrade to a match rather than to a silent blank.

    Package number narrows further when the order carries one, because the same
    material appears against many packages and the community alone can be
    ambiguous.
    """
    from Inventory.models import BillOfQuantity

    if getattr(order, 'linked_boq_item_id', None):
        return order.linked_boq_item

    code = (order.code or '').strip()
    community = (order.community or '').strip()
    if not code or not community:
        return None

    qs = BillOfQuantity.objects.filter(item_code__iexact=code,
                                       community__iexact=community)
    package = (order.package_number or '').strip()
    if package:
        narrowed = qs.filter(package_number__iexact=package)
        # Only narrow if it finds something. A package mismatch is a data
        # problem worth surfacing, but reporting "no BoQ line" for a material
        # that plainly has one would send the officer hunting the wrong fault.
        if narrowed.exists():
            qs = narrowed
    return qs.first()


def _is_justified(boq):
    """True when an APPROVED over-issuance justification exists for this line.

    'Approved' specifically — a justification sitting at Pending or Under Review
    is a request, not a decision, and treating it as clearance would make the
    gate ceremonial. Rejected obviously does not clear it either.

    `ponytail:` the model records `reviewed_by` but does not constrain *who* may
    approve. The Ministry's rule is that the Director of Power clears an
    over-issuance, and nothing here enforces that — any user with access to the
    review screen can. Enforcing it belongs in the review view, not in this gate,
    and is a separate change.
    """
    if boq is None:
        return False
    try:
        return boq.overissuance_justifications.filter(status='Approved').exists()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Justification lookup failed for BoQ %s: %s",
                       getattr(boq, 'pk', '?'), exc)
        return False


def generation_blockers(release_letter):
    """→ (blockers, result). Everything that must stop document generation.

        blockers = {'over_issued': [...], 'unmatched': [...]}

    Two kinds, because they have two different remedies and lumping them
    together would send officers to the wrong one.

    **Over-issued, unjustified.** The release draws more than its contract
    allows and nobody has said why. Remedy: raise a BoQ over-issuance
    justification and have the Director of Power approve it. Blocking here does
    not prevent the release — it routes it through the control built for exactly
    this case.

    **Unmatched.** The material has no Bill of Quantity entry at all for this
    community. This was originally left unblocked on the reasoning that a line
    with no contract has not exceeded one, and may be a legitimate emergency or
    replacement issue. That was wrong, and in the more dangerous direction: an
    over-issuance is a known quantity drawn against a known contract, whereas an
    unmatched line means the system cannot say what authorises this release at
    all. Silently letting it through produces exactly the release nobody can
    account for afterwards. The officer cannot fix it himself either — the BoQ
    may need importing, correcting, or the item code may be wrong — so the
    remedy is to contact a system administrator, and `services.boq_assistance`
    provides that route.

    An over-issued line that is also somehow unmatched cannot occur — the
    over-issuance is computed from a matched BoQ row — so the two lists are
    disjoint by construction.
    """
    result = reconcile(release_letter)
    return {
        'over_issued': [line for line in result['exceptions'] if not line['justified']],
        'unmatched': list(result['unmatched']),
    }, result


def has_blockers(blockers):
    """True when anything at all stops generation. Reads better than two `or`s."""
    return bool(blockers['over_issued'] or blockers['unmatched'])


def reconcile(release_letter):
    """→ dict describing this release against the BoQ.

    {
      'lines':       [ {...per material...} ],
      'exceptions':  [ lines that over-draw the contract ],
      'unmatched':   [ lines with no BoQ row ],
      'reconciles':  True when nothing over-draws and nothing is unmatched,
      'checked':     True when there was anything to check at all,
    }

    Never raises. The memo has to render even when the BoQ is incomplete — a
    reconciliation that crashes the document generator would take the release
    down with it, which is a far worse outcome than a memo that says the
    position could not be established.
    """
    lines, exceptions, unmatched = [], [], []

    try:
        orders = list(release_letter.material_orders.all())
    except Exception as exc:  # noqa: BLE001
        logger.warning("Reconciliation could not read orders for ReleaseLetter %s: %s",
                       release_letter.pk, exc)
        return {'lines': [], 'exceptions': [], 'unmatched': [],
                'reconciles': False, 'checked': False}

    for order in orders:
        requested = _dec(order.quantity)
        unit = order.unit.name if order.unit_id else ''

        try:
            boq = _boq_for(order)
        except Exception as exc:  # noqa: BLE001
            logger.warning("BoQ lookup failed for order %s: %s", order.pk, exc)
            boq = None

        line = {
            'material': order.name or '',
            'item_code': order.code or '',
            'community': order.community or '',
            'package_number': order.package_number or '',
            'unit': unit,
            'requested': requested,
            'matched': boq is not None,
            # Carried so the generation gate can ask this line's BoQ row whether
            # an over-issuance justification has been approved against it.
            'boq': boq,
            'contract': None,
            'drawn': None,
            'balance_before': None,
            'balance_after': None,
            'exceeds_by': None,
            'justified': False,
        }

        if boq is None:
            unmatched.append(line)
            lines.append(line)
            continue

        contract = _dec(boq.contract_quantity)
        drawn = _dec(boq.quantity_received)
        before = contract - drawn
        after = before - requested

        line.update({
            'contract': contract,
            'drawn': drawn,
            'balance_before': before,
            'balance_after': after,
        })
        if after < 0:
            line['exceeds_by'] = -after
            line['justified'] = _is_justified(boq)
            exceptions.append(line)

        lines.append(line)

    # Split, because the two say completely different things on a document. A
    # cleared over-issuance is a decision already taken and recorded; an
    # uncleared one is a document that should not have been produced. Collapsing
    # them into one list is what let the memo claim a justification existed for a
    # line that had none.
    justified_exceptions = [line for line in exceptions if line['justified']]
    unjustified_exceptions = [line for line in exceptions if not line['justified']]

    return {
        'lines': lines,
        'exceptions': exceptions,
        'justified_exceptions': justified_exceptions,
        'unjustified_exceptions': unjustified_exceptions,
        'unmatched': unmatched,
        # Both conditions matter. A release whose materials have no BoQ line is
        # not "reconciled" just because nothing came back negative — there was
        # nothing to compare it against.
        'reconciles': not exceptions and not unmatched and bool(lines),
        'checked': bool(lines),
    }


def summary_sentence(result):
    """One line for the memo body, in the register the memo is written in.

    The memo is a document a Minister's office may read. It should state the
    position in a sentence, not make the reader parse a table to find out
    whether anything is wrong.
    """
    if not result['checked']:
        return ("The Bill of Quantity position for these materials could not be "
                "established from the records available.")

    total = len(result['lines'])
    if result['reconciles']:
        return (f"All {total} material line(s) in this release fall within the "
                f"approved Bill of Quantity for the community concerned.")

    parts = []
    # Cleared and uncleared over-issuances are different facts and must not be
    # summarised as one. "Requires a justification" over a line that already has
    # an approved one reads as an outstanding action that is not outstanding;
    # "approved" over a line that has none is simply untrue.
    if result['justified_exceptions']:
        parts.append(f"{len(result['justified_exceptions'])} line(s) exceed the "
                     f"approved Bill of Quantity under an approved over-issuance "
                     f"justification")
    if result['unjustified_exceptions']:
        parts.append(f"{len(result['unjustified_exceptions'])} line(s) exceed the "
                     f"approved Bill of Quantity with no approved justification on "
                     f"record")
    if result['unmatched']:
        parts.append(f"{len(result['unmatched'])} line(s) could not be matched to "
                     f"any Bill of Quantity entry")
    return ("Reconciliation against the Bill of Quantity shows "
            + "; ".join(parts) + ". Details are set out below.")
