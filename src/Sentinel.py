import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

import threading, json
from kivy.app import App
from kivy.clock import Clock
from http.server import BaseHTTPRequestHandler, HTTPServer

import detection.detect as detect
from voice_activation import voice_activate
from Interface import SentinelApp

alarm_playing = False # flag to track if alarm sound is currently playing (prevent multiple triggers)

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
            self.send_response(200); self.end_headers()
        elif self.path == "/alert_cleared":
            Clock.schedule_once(lambda dt: _do_stop(), 0)
            self.send_response(200); self.end_headers()
        else:
            self.send_response(404); self.end_headers()
    def log_message(self, format, *args):
        return # suppress default logging
    
# start HTTP server for wake-up calls from detection module
def _do_play(data):
    global alarm_playing
    print("[Sentinel] _do_play called, alarm_playing=", alarm_playing)

    if alarm_playing:
        print("[Sentinel] alarm_playing is True, returning")
        return

    app = App.get_running_app()
    if not app:
        print("[Sentinel] no app running, returning")
        return
    path = None
    if getattr(app, "audio_manager", None):
        path = getattr(app.audio_manager, "selected_file", None) # path to currently selected audio track in UI (if any)
        print(f"[Sentinel] selected_file={path}")
    if not path:
        try:
            path = app.config.get("Audio", "default_sound") # fallback to default sound if no track
            print(f"[Sentinel] fallback path={path}")
        except Exception as e:
            print(f"[Sentinel] config fallback failed: {e}")
            path = None
    # play track if path exists and app has audio manager with play_track method
    print(f"[Sentinel] final path={path}")
    if path and getattr(app, "audio_manager", None) and hasattr(app.audio_manager, "play_track"):
        app.audio_manager.play_track(path)
        alarm_playing = True # alarm is now playing

# connect stopping track to detect.py's failsafe trigger
def _do_stop():
    global alarm_playing
    alarm_playing = False # reset flag to let future alarms play
    app = App.get_running_app()
    if not app:
        return
    if getattr(app, "audio_manager", None) and hasattr(app.audio_manager, "stop_track"):
        app.audio_manager.stop_track()

def _start_server():
    server = HTTPServer(("127.0.0.1", 5000), _WakeUpHandler)
    server.serve_forever()

def execute_voice_command(command):
    app = App.get_running_app()
    # show UI indicator
    if command == "VOICE_ACTIVATED":
        if app and hasattr(app, 'show_voice_popup'):
            app.show_voice_popup()
        return
    if command == "STOP_ALARM":
        if app:
            app.trigger_failsafe()
        Clock.schedule_once(lambda dt: _do_stop(), 0) # make sure alarm_playing flag is set to false
    elif command == "DEACTIVATE_LISTENING":
        print("Sentinel is no longer listening. Say \'Hey Sent\' to activate again.\n")
        # hide UI indicator
        if app and hasattr(app, 'hide_voice_popup'):
            app.hide_voice_popup()
    elif command == "DISABLE_DETECTION":
        print("Disabling detection features.")
        if app:
            if getattr(app, 'detection_active', False): # check if detection is currently active before toggling
                app.toggle_detection() # toggle detection off in UI)
            else:
                print("Detection is already disabled.")
    elif command == "ENABLE_DETECTION":
        print("Enabling detection features.")
        if app:
            if not getattr(app, 'detection_active', False): # check if detection is currently inactive before toggling
                app.toggle_detection() # toggle detection on in UI
            else:
                print("Detection is already enabled.")
    elif command == "SHUT_DOWN_DEVICE":
        print("Shutting down Sentinel. Goodbye!")
        if app:
            if hasattr(app, 'hide_voice_popup'): # hide voice popup when shutting down
                app.hide_voice_popup()
            app.stop()
    elif command in ("SENSITIVITY_CONSERVATIVE", "SENSITIVITY_DEFAULT", "SENSITIVITY_AGGRESSIVE"):
        preset_map = {
            "SENSITIVITY_CONSERVATIVE": "conservative",
            "SENSITIVITY_DEFAULT":      "default",
            "SENSITIVITY_AGGRESSIVE":   "aggressive",
        }
        preset = preset_map[command]
        detect.set_sensitivity(preset)
        if app and hasattr(app, 'set_sensitivity'):
            Clock.schedule_once(lambda dt: app.set_sensitivity(preset), 0)
    elif command == "RESET_ALERT":
        print("Resetting drowsiness alert via voice command.")
        detect.request_reset()
        Clock.schedule_once(lambda dt: _do_stop(), 0)

def start_voice_listening():
    voice_activate(execute_voice_command)

if __name__ == "__main__":
    print('Welcome to Sentinel')
    detect_thread = threading.Thread(target=lambda: detect.main(headless=True), daemon=True) # run detection in background thread with headless=True to disable OpenCV windows
    detect_thread.start()
    threading.Thread(target=_start_server, daemon=True).start() # start HTTP server in background thread
    voice_thread = threading.Thread(target=start_voice_listening, daemon=True)
    voice_thread.start()
    SentinelApp().run()