"""OS adapters: dispatch, key mapping, command construction, per-OS defaults. Runs on any OS (no real system calls)."""
import subprocess
import sys

import pytest
import tomlkit

from corrector import config, osdep
from corrector.osdep import linux, macos, windows, split_keys


@pytest.fixture
def fresh(monkeypatch):
    monkeypatch.setattr(osdep, "_cached", None)
    yield
    monkeypatch.setattr(osdep, "_cached", None)


def test_dispatch_by_platform(fresh, monkeypatch):
    for plat, cls in (("linux", "Linux"), ("darwin", "MacOS"), ("win32", "Windows")):
        monkeypatch.setattr(sys, "platform", plat)
        monkeypatch.setattr(osdep, "_cached", None)
        assert type(osdep.get_platform()).__name__ == cls


def test_split_keys():
    assert split_keys("ctrl+shift+c") == (["ctrl", "shift"], "c")
    assert split_keys("cmd+a") == (["cmd"], "a") and split_keys("return") == ([], "return")


def test_defaults_per_os():
    mac, win, lin = (config.default_apps(p) for p in ("darwin", "win32", "linux"))
    assert (mac["terminal"]["copy_key"], mac["native"]["copy_key"]) == ("cmd+c", "cmd+c")
    assert (win["terminal"]["copy_key"], win["native"]["copy_key"]) == ("ctrl+shift+c", "ctrl+c")
    assert lin["terminal"]["paste_key"] == "ctrl+shift+v"
    assert config.default_hotkey("darwin") == "<cmd>+<shift>+e" and config.default_hotkey("win32") == "<ctrl>+<shift>+e"
    for p in ("darwin", "win32", "linux"):
        assert tomlkit.parse(config.template(p))["apps"]["terminal"]["copy_key"] == config.default_apps(p)["terminal"]["copy_key"]
    assert "windowsterminal" in win["terminal"]["wm_class"] and "com.apple.terminal" in mac["terminal"]["wm_class"]


def test_macos_key_scripts():
    assert macos.key_script("cmd+c") == 'tell application "System Events" to keystroke "c" using {command down}'
    assert macos.key_script("cmd+shift+v") == 'tell application "System Events" to keystroke "v" using {command down, shift down}'
    assert macos.key_script("return") == 'tell application "System Events" to key code 36'


def test_macos_commands_and_window_parsing(monkeypatch):
    calls = []

    def fake_run(cmd, **kw):
        calls.append((cmd, kw))
        out = "Terminal||com.apple.Terminal||bash — 80x24||4242" if cmd[0] == "osascript" else "clip text"
        return subprocess.CompletedProcess(cmd, 0, stdout=out, stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    m = macos.MacOS()
    assert m.get_clipboard() == "clip text" and calls[-1][0] == ["pbpaste"]
    m.set_clipboard("héllo")
    assert calls[-1][0] == ["pbcopy"] and calls[-1][1]["input"] == "héllo"
    w = m.active_window()
    assert (w.wm_class, w.process, w.title) == ("com.apple.Terminal", "Terminal", "bash — 80x24") and m.active_id() == "4242"
    m.notify('say "hi"')
    assert calls[-1][0][-1] == 'display notification "say \\"hi\\"" with title "Elegant Parrot"'
    from corrector.appctx import classify
    assert classify(w, config.default_apps("darwin")) == "terminal"


def test_windows_pure_helpers():
    assert windows.vk_codes("ctrl+c") == [0x11, 0x43]
    assert windows.vk_codes("ctrl+shift+v") == [0x11, 0x10, 0x56]
    assert windows.vk_codes("ctrl+a") == [0x11, 0x41] and windows.vk_codes("return") == [0x0D]
    ps = windows.toast_script("it's done\nok")
    assert "it''s done ok" in ps and "elegant-parrot" in ps and "__MSG__" not in ps


def test_windows_classification_by_exe():
    from corrector.appctx import WindowInfo, classify
    apps = config.default_apps("win32")
    assert classify(WindowInfo("windowsterminal.exe", "PowerShell", "windowsterminal.exe"), apps) == "terminal"
    assert classify(WindowInfo("msedge.exe", "Docs", "msedge.exe"), apps) == "web"
    assert classify(WindowInfo("ms-teams.exe", "Chat | Microsoft Teams", "ms-teams.exe"), apps) == "teams"
    assert classify(WindowInfo("notepad.exe", "x", "notepad.exe"), apps) == "native"


def test_linux_commands(monkeypatch):
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: calls.append(cmd) or subprocess.CompletedProcess(cmd, 0, stdout="", stderr=""))
    p = linux.Linux()
    p.press("ctrl+shift+c")
    assert calls[-1] == ("xdotool", "key", "--clearmodifiers", "ctrl+shift+c")
    p.notify("hi")
    assert calls[-1][0] == "notify-send" and "Elegant Parrot" in calls[-1] and "hi" in calls[-1]


def test_doctor_environment_checks_return_triples():
    for cls in (linux.Linux, macos.MacOS, windows.Windows):
        for ok, label, fix in cls().check_environment():
            assert isinstance(ok, bool) and label
