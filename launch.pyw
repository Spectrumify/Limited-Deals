"""Desktop launcher: start the dashboard if it isn't running yet, then open it in the browser.

Runs with pythonw.exe (the .pyw extension), so no extra console window flashes up.
"""
import os
import socket
import subprocess
import sys
import time
import webbrowser

PORT = 5000
URL = f"http://127.0.0.1:{PORT}"
PROJECT = os.path.dirname(os.path.abspath(__file__))


def server_running():
    with socket.socket() as sock:
        sock.settimeout(1)
        return sock.connect_ex(("127.0.0.1", PORT)) == 0


def start_server():
    """Start app.py in its own minimized console window (close that window to stop it)."""
    python = os.path.join(PROJECT, "venv", "Scripts", "python.exe")
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = 7  # 7 = minimized, without stealing focus
    subprocess.Popen([python, "app.py"], cwd=PROJECT,
                     creationflags=subprocess.CREATE_NEW_CONSOLE, startupinfo=startup)


if not server_running():
    start_server()
    for _ in range(30):  # wait up to ~30 s for the server to come up
        if server_running():
            break
        time.sleep(1)
    else:
        sys.exit("The dashboard did not start. Check logs/app.log.")

webbrowser.open(URL)
