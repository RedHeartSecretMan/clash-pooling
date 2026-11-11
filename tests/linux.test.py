"""Linux platform and systemd lifecycle regressions; no live config changes."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from clashctl import platform, scheduler


@unittest.skipUnless(sys.platform.startswith('linux'), 'Linux deployment tests')
class LinuxTests(unittest.TestCase):
    def setUp(self):
        self.platform = patch.multiple(platform, IS_MAC=False, IS_WIN=False,
                                       IS_LINUX=True, create=True)
        self.platform.start()
        self.addCleanup(self.platform.stop)

    def test_xdg_data_path(self):
        with patch.dict(os.environ, {"XDG_DATA_HOME": "/tmp/clash-pooling-data"}):
            self.assertEqual(platform.config_root(), "/tmp/clash-pooling-data/" + platform.APP_DIR)

    def test_default_data_path(self):
        with patch.dict(os.environ, {"XDG_DATA_HOME": ""}):
            self.assertEqual(platform.config_root(), os.path.expanduser("~/.local/share/") + platform.APP_DIR)

    def test_restart_uses_linux_application(self):
        with patch.object(platform.shutil, "which", return_value="/usr/bin/clash-verge"), \
                patch.object(platform.subprocess, "run") as run, \
                patch.object(platform.subprocess, "Popen") as launch, \
                patch.object(platform.time, "sleep"):
            self.assertTrue(platform.restart_app())
        self.assertEqual(run.call_args.args[0], ["pkill", "-TERM", "-u", str(os.getuid()), "-x", "clash-verge"])
        self.assertEqual(launch.call_args.args[0], ["/usr/bin/clash-verge"])

    def test_restart_missing_executable_does_not_kill_running_app(self):
        with patch.object(platform.shutil, "which", return_value=None), \
                patch.object(platform.subprocess, "run") as run:
            self.assertFalse(platform.restart_app())
        run.assert_not_called()

    def test_scheduler_systemd_lifecycle(self):
        with tempfile.TemporaryDirectory() as tmp, \
                patch.dict(os.environ, {"XDG_CONFIG_HOME": tmp}), \
                patch.object(scheduler, "PLIST_DIR", str(Path(tmp) / "launchagents")), \
                patch.object(platform, "marker_path", return_value=str(Path(tmp) / "marker")), \
                patch.object(platform, "profile_file", return_value=""), \
                patch.object(sys, "argv", ["/tmp/path with spaces/clashctl"]), \
                patch.object(scheduler.subprocess, "run") as run:
            run.return_value = subprocess.CompletedProcess([], 0, stdout="active\n")
            scheduler.enable()
            root = Path(tmp) / "systemd/user"
            daily = (root / (scheduler.TASK_DAILY + ".service")).read_text()
            watch = (root / (scheduler.TASK_WATCH + ".service")).read_text()
            self.assertIn('"/tmp/path with spaces/clashctl" "auto" "run" "--full"', daily)
            self.assertNotIn('"--full"', watch)
            self.assertIn('OnCalendar=*-*-* 01:00:00', (root / (scheduler.TASK_DAILY + ".timer")).read_text())
            self.assertIn('OnUnitActiveSec=1h', (root / (scheduler.TASK_WATCH + ".timer")).read_text())
            scheduler.status()
            scheduler.disable()
            self.assertEqual(list(root.glob('*')), [])
            calls = [call.args[0] for call in run.call_args_list]
            self.assertTrue(all(cmd[:2] == ['systemctl', '--user'] for cmd in calls))
            self.assertTrue(any('enable' in cmd and '--now' in cmd for cmd in calls))
            self.assertTrue(any('disable' in cmd and '--now' in cmd for cmd in calls))

    def test_macos_and_windows_config_paths(self):
        with patch.multiple(platform, IS_LINUX=False, IS_MAC=True, IS_WIN=False):
            self.assertEqual(platform.config_root(), os.path.expanduser('~/Library/Application Support/') + platform.APP_DIR)
        with patch.multiple(platform, IS_LINUX=False, IS_MAC=False, IS_WIN=True), \
                patch.dict(os.environ, {'APPDATA': '/tmp/clash-pooling-appdata'}):
            self.assertEqual(platform.config_root(), '/tmp/clash-pooling-appdata/' + platform.APP_DIR)

    def test_unavailable_service_core_falls_back_to_path(self):
        with patch.object(platform.os, 'access', return_value=False), \
                patch.object(platform.shutil, 'which', return_value='/usr/bin/verge-mihomo'):
            self.assertEqual(platform.core_binary(), '/usr/bin/verge-mihomo')

    def test_gnome_proxy(self):
        with patch.object(platform.subprocess, 'check_output', side_effect=["'manual'\n", "'localhost'\n", '7897\n']):
            self.assertEqual(platform.system_proxy(), {'enabled': True, 'host': 'localhost', 'port': 7897})
        with patch.object(platform.subprocess, 'check_output', side_effect=FileNotFoundError):
            self.assertIsNone(platform.system_proxy())

    def test_systemd_escapes_path_expansion(self):
        with patch.object(sys, 'argv', ['/tmp/price$usd%20/clashctl']):
            unit = scheduler._systemd_service()
        self.assertIn('price$$usd%%20', unit)


if __name__ == '__main__':
    unittest.main()
