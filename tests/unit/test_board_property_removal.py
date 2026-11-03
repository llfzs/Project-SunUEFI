"""Reviewed board-DT property removal; folds the real vendored board only."""
import shutil
import struct
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
import package_release as release
from compose_piano_dtb import read_fdt, write_fdt

BOARD = ROOT / 'vendor/piano-linux/board.dtb'
REMOVAL = ('/wcn7850-pmu', 'clocks')


def tree_diff(before, after):
    changes = set()
    for path in set(before) | set(after):
        left, right = before.get(path), after.get(path)
        if left is None or right is None:
            changes.add(path + ':node')
            continue
        for key in set(left) | set(right):
            if left.get(key) != right.get(key):
                changes.add(path + ':' + key)
    return changes


@unittest.skipUnless(BOARD.is_file(), 'vendored board DTB unavailable')
class BoardPropertyRemovalTests(unittest.TestCase):
    def folded(self, removals, edit=None):
        with tempfile.TemporaryDirectory(prefix='piano-board-') as temporary:
            board = Path(temporary) / 'board.dtb'
            shutil.copyfile(BOARD, board)
            if edit:
                parsed = read_fdt(board.read_bytes())
                edit(parsed['tree'])
                board.write_bytes(write_fdt(parsed))
            return release.normalize_mainline_bindings(board, removals), board.read_bytes()

    def test_wcn_rf_clock_is_a_single_rpmh_specifier(self):
        tree = read_fdt(BOARD.read_bytes())['tree']
        raw = tree[REMOVAL[0]]['clocks']
        self.assertEqual(len(raw), 8)
        handle, index = struct.unpack('>II', raw)
        self.assertEqual(handle, struct.unpack('>I', tree[release.RPMH_CLOCK_CONTROLLER]['phandle'])[0])
        self.assertEqual(index, 6, 'RPMH_RF_CLK1 index changed in the folded board')
        self.assertNotIn('nvmem-cells', tree['/soc/qcom,spmi@c42d000/qcom,pmk8550@0/rtc@6100'])

    def test_removal_only_drops_the_declared_property(self):
        baseline, baseline_bytes = self.folded([])
        removed, removed_bytes = self.folded([REMOVAL])
        self.assertEqual(set(removed['changes']) - set(baseline['changes']),
                         {REMOVAL[0] + ':' + REMOVAL[1]})
        self.assertEqual(set(baseline['changes']) - set(removed['changes']), set())
        diff = tree_diff(read_fdt(baseline_bytes)['tree'], read_fdt(removed_bytes)['tree'])
        self.assertEqual(diff, {REMOVAL[0] + ':' + REMOVAL[1]})
        self.assertNotEqual(removed['sha256'], baseline['sha256'])

    def test_empty_removal_list_keeps_the_existing_fold(self):
        baseline, baseline_bytes = self.folded([])
        again, again_bytes = self.folded([])
        self.assertEqual(baseline['sha256'], again['sha256'])
        self.assertEqual(baseline_bytes, again_bytes)

    def test_missing_node_or_property_fails_loudly(self):
        with self.assertRaises(ValueError):
            self.folded([('/wcn7850-pmux', 'clocks')])
        with self.assertRaises(ValueError):
            self.folded([('/wcn7850-pmu', 'clock')])

    def test_foreign_clock_provider_is_rejected(self):
        def retarget(tree):
            other = tree['/soc/rsc@adc8000']
            raw = tree[REMOVAL[0]]['clocks']
            tree[REMOVAL[0]]['clocks'] = struct.pack('>I', struct.unpack('>I', other['phandle'])[0]) + raw[4:]

        with self.assertRaises(ValueError):
            self.folded([REMOVAL], edit=retarget)

    def test_specifier_shape_is_enforced(self):
        def split(tree):
            raw = tree[REMOVAL[0]]['clocks']
            tree[REMOVAL[0]]['clocks'] = raw + raw

        with self.assertRaises(ValueError):
            self.folded([REMOVAL], edit=split)

    def test_argument_parsing(self):
        self.assertEqual(release.parse_board_property_removal('/wcn7850-pmu:clocks'), REMOVAL)
        for value in ('wcn7850-pmu:clocks', '/wcn7850-pmu:', '/a:b:clocks', ''):
            with self.assertRaises(ValueError):
                release.parse_board_property_removal(value)

    def test_release_config_declares_removals(self):
        import json
        kernel = json.loads((ROOT / 'config/release.json').read_text())['kernel']
        self.assertIn('board_property_removals', kernel)
        self.assertIsInstance(kernel['board_property_removals'], list)
        for entry in kernel['board_property_removals']:
            self.assertEqual(set(entry), {'node', 'property'})


if __name__ == '__main__':
    unittest.main()
