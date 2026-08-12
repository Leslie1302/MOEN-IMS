"""Option A — non-conventional programmes are authorised by the release itself.

An unmatched BoQ line blocks generation for SHEP (a real data fault) but NOT for
Streetlights / Cost-sharing, which have no pre-loaded BoQ. The decision lives in
reconciliation.generation_blockers, so both generation doors get it at once.
"""

from decimal import Decimal

from django.test import TestCase

from Inventory.constants import is_nonconventional, normalize_project_type
from Inventory.models import ReleaseLetter, MaterialOrder, Unit
from Inventory.services.reconciliation import (
    reconcile, generation_blockers, has_blockers, summary_sentence,
)


class ProjectTypeNormalisationTests(TestCase):
    def test_short_codes_and_display_names_agree(self):
        self.assertEqual(normalize_project_type('STREET'), 'STREET')
        self.assertEqual(normalize_project_type('Streetlights'), 'STREET')
        self.assertEqual(normalize_project_type('streetlights'), 'STREET')
        self.assertEqual(normalize_project_type('Cost Sharing'), 'COST')
        self.assertEqual(normalize_project_type('cost_sharing'), 'COST')
        self.assertEqual(normalize_project_type('SHEP'), 'SHEP')
        self.assertEqual(normalize_project_type('nonsense'), '')

    def test_nonconventional_classification(self):
        for v in ('STREET', 'Streetlights', 'COST', 'Cost Sharing'):
            self.assertTrue(is_nonconventional(v), v)
        for v in ('SHEP', 'SPEC', '', None):
            self.assertFalse(is_nonconventional(v), v)


class ReleaseGateTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.unit = Unit.objects.create(name='No.')

    def _release(self, ptype):
        return ReleaseLetter.objects.create(
            request_code=f'REQ-{ptype}', title=f'{ptype} release',
            project_type=ptype, total_quantity=Decimal('1000000'))

    def _order(self, letter, ptype, code='SMM001', community='NSUAEM', qty=150):
        return MaterialOrder.objects.create(
            name='Single Phase Meter', quantity=Decimal(str(qty)), unit=self.unit,
            release_letter=letter, code=code, community=community,
            region='WESTERN', district='TARKWA', project_type=ptype, package_number='')

    def test_streetlights_unmatched_does_not_block(self):
        rl = self._release('STREET')
        self._order(rl, 'STREET')
        blockers, result = generation_blockers(rl)
        self.assertFalse(has_blockers(blockers))          # generation proceeds
        self.assertEqual(blockers['unmatched'], [])       # not a blocker
        self.assertEqual(len(result['authorised_unmatched']), 1)
        self.assertTrue(result['reconciles'])

    def test_cost_sharing_unmatched_does_not_block(self):
        rl = self._release('COST')
        self._order(rl, 'COST', code='BNW005')
        blockers, _ = generation_blockers(rl)
        self.assertFalse(has_blockers(blockers))

    def test_shep_unmatched_still_blocks(self):
        rl = self._release('SHEP')
        self._order(rl, 'SHEP')
        blockers, _ = generation_blockers(rl)
        self.assertTrue(has_blockers(blockers))
        self.assertEqual(len(blockers['unmatched']), 1)

    def test_mixed_release_blocks_only_the_conventional_line(self):
        rl = self._release('SHEP')  # release-level type; per-line project_type decides
        self._order(rl, 'STREET', code='SLA001', community='NSUAEM')
        self._order(rl, 'SHEP', code='SMP999', community='ABOKOBI')
        blockers, result = generation_blockers(rl)
        self.assertTrue(has_blockers(blockers))
        self.assertEqual(len(blockers['unmatched']), 1)                 # only the SHEP line
        self.assertEqual(blockers['unmatched'][0]['item_code'], 'SMP999')
        self.assertEqual(len(result['authorised_unmatched']), 1)        # the STREET line

    def test_wholly_nonconventional_release_omits_reconciliation(self):
        # all_nonconventional drives the memo to drop the reconciliation section
        # entirely — there is no BoQ position to state.
        rl = self._release('STREET')
        self._order(rl, 'STREET', code='A1')
        self._order(rl, 'STREET', code='A2', community='NKWANTA')
        self.assertTrue(reconcile(rl)['all_nonconventional'])

    def test_shep_release_is_not_flagged_nonconventional(self):
        rl = self._release('SHEP')
        self._order(rl, 'SHEP')
        self.assertFalse(reconcile(rl)['all_nonconventional'])

    def test_mixed_release_keeps_reconciliation(self):
        # A mixed release still shows the section (for its conventional line), so
        # it must NOT be flagged wholly non-conventional.
        rl = self._release('SHEP')
        self._order(rl, 'STREET', code='SLA001')
        self._order(rl, 'SHEP', code='SMP999', community='ABOKOBI')
        result = reconcile(rl)
        self.assertFalse(result['all_nonconventional'])
        # The section still states the non-conventional line's basis honestly.
        self.assertIn('authorised by the release order', summary_sentence(result))
