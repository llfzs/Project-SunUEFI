"""The GNOME power overlay must stay LF and keep its unit/executable contract."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))

import stage_piano_full_userspace as userspace  # noqa: E402

OVERLAY = ROOT / 'linux/desktops/gnome/power-overlay'


class PowerOverlayTest(unittest.TestCase):
    def test_every_file_is_lf(self):
        # These files land on a Linux rootfs verbatim; a CRLF shebang makes the
        # service fail with status 203/EXEC, which has happened four times.
        for path in sorted(OVERLAY.rglob('*')):
            if not path.is_file():
                continue
            self.assertNotIn(b'\r\n', path.read_bytes(), path)

    def test_executable_set_covers_every_script(self):
        for name in userspace.EXECUTABLES:
            path = OVERLAY / name
            self.assertTrue(path.is_file(), name)
            self.assertTrue(path.read_bytes().startswith(b'#!'), name)
        scripts = {path.relative_to(OVERLAY).as_posix()
                   for path in OVERLAY.rglob('*')
                   if path.is_file() and path.read_bytes().startswith(b'#!')}
        self.assertEqual(scripts, set(userspace.EXECUTABLES))

    def test_user_units_exist_and_are_shipped(self):
        for unit in userspace.USER_UNITS:
            self.assertTrue((OVERLAY / 'usr/lib/systemd/user' / unit).is_file(), unit)

    def test_sensor_rule_limits_itself_to_the_proxy(self):
        rule = (OVERLAY / 'usr/share/polkit-1/rules.d/60-piano-sensor-power.rules').read_text()
        self.assertIn('org.freedesktop.systemd1.manage-units', rule)
        self.assertIn('iio-sensor-proxy.service', rule)


if __name__ == '__main__':
    unittest.main()
