"""Native Windows toast notifications, injection-safe.

Untrusted text (e.g. an email sender's name) is XML-escaped, and the whole toast XML reaches
PowerShell only as base64, so no notification text can ever become PowerShell code.
(We deliberately don't use winotify: it formats raw text into a PowerShell script.)
"""
from __future__ import annotations

import base64
import subprocess
import sys
from xml.sax.saxutils import escape, quoteattr

# Windows PowerShell's registered AppUserModelID: lets unpackaged apps show toasts without registry changes.
APP_ID = r"{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe"

_PS = r"""
$ErrorActionPreference = 'Stop'
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] > $null
$xml = [System.Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('__B64__'))
$doc = New-Object Windows.Data.Xml.Dom.XmlDocument
$doc.LoadXml($xml)
$toast = [Windows.UI.Notifications.ToastNotification]::new($doc)
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('__APP__').Show($toast)
"""


def build_xml(title: str, body: str, url: str | None = None, urgent: bool = False) -> str:
    launch = f" activationType=\"protocol\" launch={quoteattr(url)}" if url else ""
    audio = '<audio src="ms-winsoundevent:Notification.Reminder"/>' if urgent else '<audio silent="true"/>'
    return (f'<toast{launch} duration="short"><visual><binding template="ToastGeneric">'
            f"<text>{escape(title[:120])}</text><text>{escape(body[:300])}</text>"
            f"</binding></visual>{audio}</toast>")


def build_command(xml: str) -> list[str]:
    b64 = base64.b64encode(xml.encode("utf-8")).decode("ascii")  # only [A-Za-z0-9+/=] reach the script
    script = _PS.replace("__B64__", b64).replace("__APP__", APP_ID)
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    return ["powershell.exe", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-EncodedCommand", encoded]


def toast(title: str, body: str, url: str | None = None, urgent: bool = False) -> bool:
    if sys.platform != "win32":
        return False
    try:
        subprocess.Popen(build_command(build_xml(title, body, url, urgent)), stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=0x08000000)  # no window
        return True
    except OSError:
        return False
