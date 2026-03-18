"""
sentinel.py
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

import subprocess
import threading, json
import urllib.request
from kivy.app import App
from kivy.clock import Clock, mainthread
from http.server import BaseHTTPRequestHandler, HTTPServer

from Interface import SentinelApp

alarm_playing = False
alarm_process = None

def _send_detect_command(path, data=None):
    """Send a command to the detection process on port 5001"""
    def _post():
        payload = json.dumps(data or {}).encode("utf-8")
        req = urllib.request.Request(
            f"http://127.0.0.1:5001{path}",
            data=payload,
            headers={"Content-Type": "application/json"}
        )
        try:
            urllib.request.urlopen(req, timeout=1.0)
        except Exception:
            pass
    threading.Thread(target=_post, daemon=True).start()

class _WakeUpHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("content-length", 0))
        body = self.rfile.read(length) if length else b""
        try:
            data = json.loads(body.decode("utf-8") or "{}")
        except Exception:
            data = {}
            
        if self.path == "/wake_up":
            Clock.schedule_once(lambda dt: _do_play(data), 0)
            self.send_response(200)
            self.end_headers()
        elif self.path == "/alert_cleared":
            Clock.schedule_once(lambda dt: _do_stop(), 0)
            self.send_response(200)
            self.end_headers()
        elif self.path == "/voice_command":
            cmd = data.get("command")
            if cmd:
                Clock.schedule_once(lambda dt: execute_voice_command(cmd), 0)
            self.send_response(200)
            self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()
            
    def log_message(self, format, *args):
        return

@mainthread
def _do_play(data):
    global alarm_playing, alarm_process

    if alarm_playing:
        return

    app = App.get_running_app()
    if not app:
        return
        
    path = None
    if getattr(app, "audio_manager", None):
        path = getattr(app.audio_manager, "selected_file", None)
        
    if not path:
        try:
            path = app.config.get("Audio", "default_sound")
        except Exception:
            path = None
            
    if path and not alarm_playing:
        if not os.path.isabs(path):
            base_dir = os.path.dirname(os.path.abspath(__file__))
            path = os.path.normpath(os.path.join(base_dir, path))
            
        print(f"[Sentinel] Bypassing Kivy audio, playing via mpg123: {path}", flush=True)
        alarm_process = subprocess.Popen(
            ["mpg123", "--loop", "-1", path], 
            stdout=subprocess.DEVNULL, 
            stderr=subprocess.DEVNULL
        )
        alarm_playing = True

@mainthread
def _do_stop():
    global alarm_playing, alarm_process
    alarm_playing = False
    
    if alarm_process:
        alarm_process.terminate()
        alarm_process = None

def _start_server():
    server = HTTPServer(("127.0.0.1", 5000), _WakeUpHandler)
    server.serve_forever()

def execute_voice_command(command):
    app = App.get_running_app()
    if command == "VOICE_ACTIVATED":
        if app and hasattr(app, 'show_voice_popup'):
            app.show_voice_popup()
        return
        
    if command == "STOP_ALARM":
        if app:
            app.trigger_failsafe()
        Clock.schedule_once(lambda dt: _do_stop(), 0)
    elif command == "DEACTIVATE_LISTENING":
        print("Sentinel is no longer listening. Say 'Hey Sent' to activate again.\n")
        if app and hasattr(app, 'hide_voice_popup'):
            app.hide_voice_popup()
    elif command == "DISABLE_DETECTION":
        print("Disabling detection features.")
        if app:
            if getattr(app, 'detection_active', False):
                app.toggle_detection()
            else:
                print("Detection is already disabled.")
    elif command == "ENABLE_DETECTION":
        print("Enabling detection features.")
        if app:
            if not getattr(app, 'detection_active', False):
                app.toggle_detection()
            else:
                print("Detection is already enabled.")
    elif command == "SHUT_DOWN_DEVICE":
        print("Shutting down Sentinel. Goodbye!")
        if app:
            if hasattr(app, 'hide_voice_popup'):
                app.hide_voice_popup()
            app.stop()
    elif command in ("SENSITIVITY_CONSERVATIVE", "SENSITIVITY_DEFAULT", "SENSITIVITY_AGGRESSIVE"):
        preset_map = {
            "SENSITIVITY_CONSERVATIVE": "conservative",
            "SENSITIVITY_DEFAULT":      "default",
            "SENSITIVITY_AGGRESSIVE":   "aggressive",
        }
        preset = preset_map[command]
        _send_detect_command("/set_sensitivity", {"preset": preset})
        if app and hasattr(app, 'set_sensitivity'):
            Clock.schedule_once(lambda dt: app.set_sensitivity(preset), 0)
    elif command == "RESET_ALERT":
        print("Resetting drowsiness alert via voice command.")
        _send_detect_command("/request_reset")
        Clock.schedule_once(lambda dt: _do_stop(), 0)

if __name__ == "__main__":
    print('Welcome to Sentinel')

    detect_script = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 '..', 'detection', 'detect.py')
    detect_proc = subprocess.Popen(
        [sys.executable, detect_script, "--headless"],
        stdout=None, stderr=None
    )

    threading.Thread(target=_start_server, daemon=True).start()

    voice_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'voice_activation.py')
    voice_proc = subprocess.Popen(
        [sys.executable, voice_script],
        stdout=None, stderr=None
    )

    def _apply_saved_settings(dt):
        app = App.get_running_app()
        if app:
            saved_sensitivity = app.config.get('System', 'sensitivity')
            _send_detect_command("/set_sensitivity", {"preset": saved_sensitivity})
            saved_detection = app.config.get('System', 'drowsiness_detection')
            enabled = saved_detection == 'True'
            _send_detect_command("/set_detection_enabled", {"enabled": enabled})
    Clock.schedule_once(_apply_saved_settings, 3)

    SentinelApp().run()

    detect_proc.terminate()
    voice_proc.terminate()
    detect_proc.wait(timeout=5)