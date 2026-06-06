"""
Management command: fix_rl_order_links

Detects and corrects two classes of ReleaseLetter / MaterialOrder link problems
caused by the now-fixed auto_link_orders_to_release_letter signal running on
every RL save instead of only on creation.

═══ Problem class A — wrong prefix ═══════════════════════════════════════════
An order's request_code does NOT match the RL it is linked to (neither exact
nor prefix). These are clearly stolen from an unrelated RL.

═══ Problem class B — stolen from a more-specific RL ════════════════════════
An order IS correctly matched by the parent RL's prefix (e.g. order code
REQ-BASE-3 starts with REQ-BASE-) BUT a dedicated RL exists whose request_code
is exactly the order's request_code (REQ-BASE-3). The signal bug re-assigned
such orders to the most-recently-saved parent RL, pulling them away from their
own dedicated RLs. The parent RL ends up with too many orders (and a
total_quantity that no longer reflects reality), and the individual RLs end up
empty.

═══ Problem class C — date-only RL request_code ════════════════════════════
The fallback in CreateReleaseLetterFromRequestView used to strip the last
segment of the request code (e.g. REQ-20260604-XXXXXX → REQ-20260604) and
query startswith='REQ-20260604-', which matches every order created that day.
An RL created from this path ends up with a date-only request_code and absorbs
all same-day orders. Every linked order here is wrongly linked; they are
unlinked so they can be re-assigned to the correct dedicated RLs.

After relinking, each RL's total_quantity is recalculated to match the sum of
its remaining orders so the balance validator reflects true figures.

Usage:
    python manage.py fix_rl_order_links              # dry run — shows what would change
    python manage.py fix_rl_order_links --apply      # fix everything
    python manage.py fix_rl_order_links --apply --rl RL-20260604-B0D7D2
"""

import re
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Sum

# request_code pattern that is only a date prefix — REQ-YYYYMMDD with nothing after.
# These RLs were created by the now-fixed fallback bug and are too broad.
_DATE_ONLY_RC = re.compile(r'^REQ-\d{8}$')


class Command(BaseCommand):
    help = "Re-link MaterialOrders to their correct ReleaseLetter and recalculate totals"

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply',
            action='store_true',
            default=False,
            help='Actually apply fixes. Without this flag the command only reports.',
        )
        parser.add_argument(
            '--rl',
            dest='rl_ref',
            default=None,
            help='Limit the check to a single ReleaseLetter by reference number.',
        )

    def handle(self, *args, **options):
        from Inventory.models import ReleaseLetter, MaterialOrder

        apply = options['apply']
        rl_ref = options.get('rl_ref')

        # Build a lookup of request_code → RL for quick "is there a dedicated RL?" checks.
        # A dedicated RL for an individual order is one whose request_code exactly equals
        # the order's request_code.
        dedicated_rl_by_code = {}
        for rl in ReleaseLetter.objects.exclude(request_code='').filter(request_code__isnull=False):
            # Keep the most-recently created one per code in case of duplicates.
            if rl.request_code not in dedicated_rl_by_code or rl.pk > dedicated_rl_by_code[rl.request_code].pk:
                dedicated_rl_by_code[rl.request_code] = rl

        rl_qs = ReleaseLetter.objects.filter(request_code__isnull=False).exclude(request_code='')
        if rl_ref:
            rl_qs = rl_qs.filter(reference_number=rl_ref)
            if not rl_qs.exists():
                rl_qs = ReleaseLetter.objects.filter(code=rl_ref)
            if not rl_qs.exists():
                self.stderr.write(self.style.ERROR(f"No ReleaseLetter found: '{rl_ref}'"))
                return

        total_class_a = 0
        total_class_b = 0
        total_class_c = 0
        rls_to_recalculate = set()

        for rl in rl_qs.iterator():
            rc = rl.request_code
            prefix = f"{rc}-"
            is_date_only = bool(_DATE_ONLY_RC.match(rc))
            linked = list(MaterialOrder.objects.filter(release_letter=rl))
            if not linked:
                continue

            class_a = []  # order's code doesn't even match this RL
            class_b = []  # order should be on a more-specific RL
            class_c = []  # RL has a date-only request_code — all linked orders are wrong

            for o in linked:
                code = o.request_code or ''
                if is_date_only:
                    # Class C: date-only RL absorbs every same-day order.
                    # No order can have a date-only code (generate_request_code
                    # always produces REQ-YYYYMMDD-XXXXXX), so every linked
                    # order here is wrongly linked.
                    class_c.append(o)
                elif code != rc and not code.startswith(prefix):
                    class_a.append(o)
                elif code != rc and code.startswith(prefix):
                    specific = dedicated_rl_by_code.get(code)
                    if specific and specific.pk != rl.pk:
                        class_b.append((o, specific))

            if not class_a and not class_b and not class_c:
                continue

            self.stdout.write(
                self.style.WARNING(
                    f"\nRL {rl.reference_number or rl.pk}  "
                    f"(request_code={rc!r}, authorized={rl.total_quantity}, "
                    f"orders={len(linked)}, sum={sum(o.quantity or 0 for o in linked)})"
                )
            )

            for o in class_a:
                total_class_a += 1
                self.stdout.write(
                    f"  [A] WRONG PREFIX — order pk={o.pk} code={o.request_code!r} "
                    f"qty={o.quantity} → will be unlinked"
                )

            for o, specific in class_b:
                total_class_b += 1
                self.stdout.write(
                    f"  [B] STOLEN FROM DEDICATED RL — order pk={o.pk} code={o.request_code!r} "
                    f"qty={o.quantity} → will move to {specific.reference_number or specific.pk}"
                )

            for o in class_c:
                total_class_c += 1
                self.stdout.write(
                    f"  [C] DATE-ONLY RL — order pk={o.pk} code={o.request_code!r} "
                    f"qty={o.quantity} → will be unlinked"
                )

            if apply:
                with transaction.atomic():
                    # Class A + C: unlink
                    pks_unlink = [o.pk for o in class_a] + [o.pk for o in class_c]
                    if pks_unlink:
                        MaterialOrder.objects.filter(pk__in=pks_unlink).update(release_letter=None)
                        rls_to_recalculate.add(rl.pk)

                    # Class B: move to dedicated RL
                    for o, specific in class_b:
                        MaterialOrder.objects.filter(pk=o.pk).update(release_letter=specific)
                        rls_to_recalculate.add(rl.pk)
                        rls_to_recalculate.add(specific.pk)

                self.stdout.write(
                    self.style.SUCCESS(
                        f"  → Applied: {len(class_a) + len(class_c)} unlinked, {len(class_b)} moved"
                    )
                )

        # Recalculate total_quantity for affected RLs so the balance
        # validator reflects the corrected order set.
        if apply and rls_to_recalculate:
            self.stdout.write("\nRecalculating total_quantity for affected RLs...")
            for rl_pk in rls_to_recalculate:
                try:
                    rl = ReleaseLetter.objects.get(pk=rl_pk)
                    new_total = (
                        MaterialOrder.objects.filter(release_letter=rl)
                        .aggregate(s=Sum('quantity'))['s'] or Decimal('0')
                    )
                    old_total = rl.total_quantity
                    # Only update if the linked orders sum differs from the authorized total
                    # and the RL clearly has stale data (i.e. current total is wrong by >0).
                    if old_total != new_total:
                        rl.total_quantity = new_total
                        rl.save(update_fields=['total_quantity'])
                        self.stdout.write(
                            self.style.SUCCESS(
                                f"  {rl.reference_number or rl.pk}: total_quantity "
                                f"{old_total} → {new_total}"
                            )
                        )
                except Exception as exc:
                    self.stderr.write(f"  Could not recalculate RL pk={rl_pk}: {exc}")

        # Summary
        found = total_class_a + total_class_b + total_class_c
        if found == 0:
            self.stdout.write(self.style.SUCCESS(
                "\nNo problems found. All orders are on the correct ReleaseLetter."
            ))
        elif not apply:
            self.stdout.write(self.style.WARNING(
                f"\nDRY RUN: {total_class_a} wrong-prefix, "
                f"{total_class_b} stolen-from-dedicated-RL, "
                f"{total_class_c} date-only-RL order(s). "
                f"Re-run with --apply to fix."
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                f"\nDone. Fixed {found} order link(s)."
            ))
