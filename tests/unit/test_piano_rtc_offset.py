"""Draft RTC offset overlay: SDAM2 allocation audit against the folded board."""
import json
import re
import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from compose_piano_dtb import read_fdt

OVERLAY = ROOT / 'linux/dts/drafts/piano-rtc-offset.dtso'
BOARD = ROOT / 'vendor/piano-linux/board.dtb'
RTC = '/soc/qcom,spmi@c42d000/qcom,pmk8550@0/rtc@6100'
SDAM2 = '/soc/qcom,spmi@c42d000/qcom,pmk8550@0/sdam@7100'


def sdam2_ranges(tree):
    ranges = {}
    for path, props in tree.items():
        if path.startswith(SDAM2 + '/'):
            reg = props.get('reg')
            if reg and len(reg) == 8:
                begin, length = struct.unpack('>II', reg)
                ranges[path.rsplit('/', 1)[-1]] = (begin, begin + max(length, 1))
    return ranges


@unittest.skipUnless(BOARD.is_file(), 'vendored board DTB unavailable')
class PianoRtcOffsetTests(unittest.TestCase):
    def setUp(self):
        self.text = OVERLAY.read_text()
        self.tree = read_fdt(BOARD.read_bytes())['tree']

    def test_overlay_targets_exist_in_the_folded_board(self):
        targets = re.findall(r'target-path = "([^"]+)";', self.text)
        self.assertEqual(sorted(targets), sorted([RTC, SDAM2]))
        for target in targets:
            self.assertIn(target, self.tree)

    def test_offset_cell_fits_the_free_window(self):
        match = re.search(r'rtc-offset@([0-9a-f]+)\s*\{\s*reg = <0x([0-9a-f]+) 0x([0-9a-f]+)>;', self.text)
        self.assertIsNotNone(match, 'rtc-offset node or its reg changed shape')
        begin, length = int(match.group(2), 16), int(match.group(3), 16)
        self.assertEqual(int(match.group(1), 16), begin, 'node unit address and reg disagree')
        self.assertEqual(length, 4, 'the pm8xxx offset cell is a signed 32-bit value')
        for name, (low, high) in sdam2_ranges(self.tree).items():
            self.assertFalse(begin < high and low < begin + length,
                             'offset cell overlaps ' + name)
        self.assertIn('alarm-log@76', sdam2_ranges(self.tree))

    def test_board_still_lacks_the_offset_cell(self):
        self.assertNotIn('nvmem-cells', self.tree[RTC])
        self.assertFalse([p for p in self.tree if p.startswith(SDAM2 + '/') and 'rtc' in p],
                         'the folded board already describes an RTC offset cell')

    def test_overlay_declares_the_offset_cell_name(self):
        self.assertIn('nvmem-cell-names = "offset";', self.text)

    def test_draft_is_not_yet_a_release_input(self):
        kernel = json.loads((ROOT / 'config/release.json').read_text())['kernel']
        self.assertNotIn('linux/dts/drafts/piano-rtc-offset.dtso',
                         kernel['additional_dtb_overlays'])

    def test_overlay_is_lf_only_with_spdx(self):
        self.assertTrue(self.text.startswith('// SPDX-License-Identifier:'))
        self.assertNotIn('\r', OVERLAY.read_bytes().decode('utf-8'))


if __name__ == '__main__':
    unittest.main()
