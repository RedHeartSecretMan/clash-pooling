#!/usr/bin/env python3
"""Linux 相关回归：路径、控制接口、应用重启、systemd 用户定时器。

这些用例都用打补丁的方式模拟平台，因此在 macOS / Linux 上都能跑，
能在非 Linux 开发机上发现 Linux 分支的回归。
"""

import io
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import ExitStack, redirect_stdout
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

from clashctl import platform, scheduler, setup_console

setup_console()


def quiet(func, *args, **kwargs):
    """调用会打印进度的函数，但把输出吞掉，保持测试报告干净"""
    with redirect_stdout(io.StringIO()):
        return func(*args, **kwargs)


class LinuxTests(unittest.TestCase):
    def setUp(self):
        patch.multiple(platform, IS_MAC=False, IS_WIN=False, IS_LINUX=True,
                       create=True).start()
        self.addCleanup(patch.stopall)

    # ---------------------------------------------------------------- 路径
    def test_xdg_data_path(self):
        with patch.dict(os.environ, {"XDG_DATA_HOME": "/tmp/clash-pooling-data"}):
            self.assertEqual(platform.config_root(),
                             os.path.join("/tmp/clash-pooling-data", platform.APP_DIR))

    def test_default_data_path(self):
        with patch.dict(os.environ, {"XDG_DATA_HOME": ""}):
            self.assertEqual(platform.config_root(),
                             os.path.join(os.path.expanduser("~/.local/share"), platform.APP_DIR))

    def test_macos_and_windows_config_paths(self):
        with patch.multiple(platform, IS_LINUX=False, IS_MAC=True, IS_WIN=False):
            self.assertEqual(platform.config_root(),
                             os.path.join(os.path.expanduser("~/Library/Application Support"),
                                          platform.APP_DIR))
        with patch.multiple(platform, IS_LINUX=False, IS_MAC=False, IS_WIN=True), \
                patch.dict(os.environ, {"APPDATA": "/tmp/clash-pooling-appdata"}):
            self.assertEqual(platform.config_root(),
                             os.path.join("/tmp/clash-pooling-appdata", platform.APP_DIR))

    # ---------------------------------------------------------- 控制接口
    def test_control_uses_generated_unix_socket(self):
        with patch.object(platform, "_parse_generated",
                          return_value={"controller": "", "secret": "s",
                                        "mixed_port": 7897, "unix": "/run/user/1000/mihomo.sock"}), \
                patch.object(platform.os.path, "exists", return_value=True):
            self.assertEqual(platform.control(), ("unix", "/run/user/1000/mihomo.sock", "s"))

    def test_control_falls_back_to_tcp_when_socket_missing(self):
        """配置里的 socket 已失效（文件不在）时不要拿它去连"""
        with patch.object(platform, "_parse_generated",
                          return_value={"controller": "127.0.0.1:9097", "secret": "s",
                                        "mixed_port": 7897, "unix": "/run/user/1000/gone.sock"}), \
                patch.object(platform.os.path, "exists", return_value=False):
            self.assertEqual(platform.control(), ("tcp", ("127.0.0.1", 9097), "s"))

    def test_control_honours_explicit_overrides(self):
        cfg = {"controller": "127.0.0.1:9097", "secret": "s", "mixed_port": 7897, "unix": "/run/x.sock"}
        with patch.object(platform, "_parse_generated", return_value=cfg), \
                patch.object(platform.os.path, "exists", return_value=True):
            with patch.dict(os.environ, {"CLASH_CONTROLLER": "127.0.0.1:9999"}):
                self.assertEqual(platform.control()[1], ("127.0.0.1", 9999))
            with patch.dict(os.environ, {"CLASH_SOCK": "/tmp/custom.sock"}):
                self.assertEqual(platform.control(), ("unix", "/tmp/custom.sock", "s"))

    def test_core_binary_override(self):
        with patch.dict(os.environ, {"CLASH_CORE": "/opt/mihomo"}):
            self.assertEqual(platform.core_binary(), "/opt/mihomo")

    # -------------------------------------------------------------- 重启
    def test_restart_uses_linux_application(self):
        with patch.object(platform.shutil, "which", return_value="/usr/bin/clash-verge"), \
                patch.object(platform.subprocess, "run") as run, \
                patch.object(platform.subprocess, "Popen") as launch, \
                patch.object(platform.time, "sleep"), \
                patch.object(platform.os, "getuid", return_value=1000, create=True):
            self.assertTrue(platform.restart_app())
        self.assertEqual(run.call_args.args[0],
                         ["pkill", "-TERM", "-u", "1000", "-x", "clash-verge"])
        self.assertEqual(launch.call_args.args[0], ["/usr/bin/clash-verge"])

    def test_restart_missing_executable_does_not_kill_running_app(self):
        with patch.object(platform.shutil, "which", return_value=None), \
                patch.object(platform.subprocess, "run") as run:
            self.assertFalse(platform.restart_app())
        run.assert_not_called()

    # -------------------------------------------------------------- 内核
    def test_core_binary_falls_back_to_path(self):
        with patch.object(platform.os, "access", return_value=False), \
                patch.object(platform.shutil, "which", return_value="/usr/bin/verge-mihomo"):
            self.assertEqual(platform.core_binary(), "/usr/bin/verge-mihomo")

    def test_core_binary_prefers_service_copy(self):
        with patch.object(platform.os, "access", return_value=True):
            self.assertEqual(platform.core_binary(),
                             "/var/lib/clash-verge-service/cores/verge-mihomo")

    # ---------------------------------------------------------- 系统代理
    def test_gnome_proxy(self):
        with patch.object(platform.subprocess, "check_output",
                          side_effect=["'manual'\n", "'localhost'\n", "7897\n"]):
            self.assertEqual(platform.system_proxy(),
                             {"enabled": True, "host": "localhost", "port": 7897})
        with patch.object(platform.subprocess, "check_output", side_effect=FileNotFoundError):
            self.assertIsNone(platform.system_proxy())

    # ------------------------------------------------------------ 调度
    def _systemd_env(self, tmp):
        """把 systemd 相关路径与 systemctl 调用都指向临时环境"""
        stack = ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(patch.dict(os.environ, {"XDG_CONFIG_HOME": tmp}))
        stack.enter_context(patch.object(platform, "marker_path",
                                         return_value=str(Path(tmp) / "marker")))
        stack.enter_context(patch.object(platform, "profile_file", return_value=""))
        stack.enter_context(patch.object(scheduler, "_launcher",
                                         return_value="/tmp/路径 含空格/clashctl"))
        return stack.enter_context(patch.object(scheduler.subprocess, "run"))

    def test_systemd_lifecycle(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = self._systemd_env(tmp)
            run.return_value = subprocess.CompletedProcess([], 0, stdout="active\n")
            self.assertTrue(quiet(scheduler.enable))

            root = Path(tmp) / "systemd/user"
            daily = (root / (scheduler.TASK_DAILY + ".service")).read_text(encoding="utf-8")
            watch = (root / (scheduler.TASK_WATCH + ".service")).read_text(encoding="utf-8")
            self.assertIn('"/tmp/路径 含空格/clashctl" "auto" "run" "--full"', daily)
            self.assertIn("KillMode=process", daily)             # 否则 oneshot 结束会杀掉刚重启的 GUI
            self.assertNotIn('"--full"', watch)

            daily_timer = (root / (scheduler.TASK_DAILY + ".timer")).read_text(encoding="utf-8")
            self.assertIn("OnCalendar=*-*-* 01:00:00", daily_timer)
            self.assertIn("Persistent=true", daily_timer)          # 关机错过要补跑
            watch_timer = (root / (scheduler.TASK_WATCH + ".timer")).read_text(encoding="utf-8")
            self.assertIn("OnActiveSec=1min", watch_timer)        # 与另两个平台一样，启用后很快跑第一次
            self.assertIn("OnUnitActiveSec=1h", watch_timer)

            quiet(scheduler.status)
            self.assertTrue(quiet(scheduler.disable))
            self.assertEqual(list(root.glob("*")), [])

            commands = [call.args[0] for call in run.call_args_list]
            self.assertTrue(all(cmd[:2] == ["systemctl", "--user"] for cmd in commands))
            self.assertTrue(any("enable" in cmd and "--now" in cmd for cmd in commands))
            self.assertTrue(any("disable" in cmd and "--now" in cmd for cmd in commands))

    def test_systemd_failure_reports_hint_without_raising(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = self._systemd_env(tmp)
            run.return_value = subprocess.CompletedProcess([], 1, stderr="Failed to connect to bus")
            self.assertFalse(quiet(scheduler.enable))      # 不抛异常，返回失败
            commands = [call.args[0] for call in run.call_args_list]
            self.assertTrue(any("daemon-reload" in cmd for cmd in commands))
            self.assertFalse(any("enable" in cmd for cmd in commands))   # 失败后不再往下执行

    def test_systemd_escapes_path_specifiers(self):
        with patch.object(scheduler, "_launcher", return_value="/tmp/price$usd%20/clashctl"):
            unit = scheduler._systemd_service()
        self.assertIn("price$$usd%%20", unit)

    def test_launcher_prefers_windows_install_path(self):
        with patch.multiple(platform, IS_WIN=True, IS_LINUX=False), \
                patch.object(scheduler.os.environ, "get", return_value="C:/Users/x/AppData/Local"), \
                patch.object(sys, "argv", ["-c"]), \
                patch.object(scheduler.os.path, "isfile", side_effect=lambda p: "clash-pooling" in p):
            self.assertIn("clash-pooling", scheduler._launcher())

    def test_launcher_rejects_python_dash_c(self):
        with patch.object(sys, "argv", ["-c"]), \
                patch.object(scheduler.os.path, "isfile", side_effect=lambda p: p.endswith(".local/bin/clashctl")):
            self.assertTrue(scheduler._launcher().endswith(".local/bin/clashctl"))


if __name__ == "__main__":
    unittest.main()
