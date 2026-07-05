"""Regression tests for the BoQ material classifier feeding the targets pull.

These lock in the July 2026 fixes:
  * pole checked before meter — "10 Meter Concrete Pole" is a pole, not a meter
  * KVA spec names ("11/0.433, 100KVA. 3-ph") classify as transformers
  * accessory/fitting lines (fuses, insulators, crossarms, stays, clamps,
    pole accessories) contribute to no target
  * pole height resolves HT vs LV when no explicit keyword exists
"""

from unittest import TestCase

from Inventory.services.community_progress import _kind, _POLE_HEIGHT_RE


class KindClassifierTests(TestCase):

    def assertKind(self, name, expected, item_code=''):
        self.assertEqual(_kind(name, item_code), expected, name)

    def test_pole_lengths_are_poles_not_meters(self):
        for name in ('10 Meter Concrete Pole', '11 Meter Concrete Pole',
                     '9M Wooden Pole', '10M Steel Tubular Pole',
                     'No.of 10/11m HT pole'):
            self.assertKind(name, 'pole')

    def test_kva_spec_names_are_transformers(self):
        for name in ('11/0.433, 100KVA. 3-ph', '33/0.433, 50KVA. 3-ph',
                     '33/25KVA, 1-ph', 'Transformer'):
            self.assertKind(name, 'transformer')

    def test_meters(self):
        for name in ('1-phase Meters, 5/60A', '3-phase Meters, 10/100A',
                     'Energy Meter'):
            self.assertKind(name, 'meter')

    def test_conductors(self):
        for name in ('120 sqmm HD AL. Conductor', 'Abc Cable 50Sqmm Conductor'):
            self.assertKind(name, 'conductor')

    def test_accessories_feed_no_target(self):
        for name in ('HT Concrete Pole Accessories', 'Pole-Mounted LV Fuse Unit',
                     'LV Stay Insulator', '11KV Angle Iron Crossarm c/w Straps',
                     '33Kv Pin Insulator - Polymer', 'Al. Binding Wire',
                     'Shackle Insulator Straps c/w Pins', 'HT Distance',
                     '33kV Voltage Level'):
            self.assertKind(name, '')

    def test_pole_height_resolves_voltage(self):
        for name, expected in (('10 Meter Concrete Pole', 'HT'),
                               ('12M Wood Pole', 'HT'),
                               ('9M Wooden Pole', 'LV'),
                               ('7M Wooden Pole', 'LV')):
            m = _POLE_HEIGHT_RE.search(name.lower())
            self.assertIsNotNone(m, name)
            got = 'HT' if int(m.group(1)) >= 10 else 'LV'
            self.assertEqual(got, expected, name)
