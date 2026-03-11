from voice_activation import voice_activate
from kivy.app import App
from Interface import SentinelApp
from http.server import BaseHTTPRequestHandler, HTTPServer
from kivy.clock import Clock
import threading, json
import os

print('Welcome to Sentinel')

alarm_on = True  # alarm is default on -- update once connected to actual alarm
alarm_playing = False # flag to track if alarm sound is currently playing (prevent multiple triggers)

class _WakeUpHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != "/wake_up":
            self.send_response(404); self.end_headers(); return
        length = int(self.headers.get("content-length", 0))
        body = self.rfile.read(length) if length else b""
        try:
            data = json.loads(body.decode("utf-8") or "{}")
        except Exception:
            data = {}
        Clock.schedule_once(lambda dt: _do_play(data), 0)
        self.send_response(200); self.end_headers()
    def log_message(self, format, *args):
        return # suppress default logging
    
# start HTTP server for wake-up calls from detection module
def _do_play(data):
    global alarm_playing
    print("[Sentinel] _do_play called, alarm_on=", alarm_on, "alarm_playing=", alarm_playing)

    if not alarm_on:
        print("[Sentinel] alarm_on is False, returning")
        return
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
    alarm_playing = False
    app = App.get_running_app()
    if not app:
        return
    if getattr(app, "audio_manager", None) and hasattr(app.audio_manager, "stop_track"):
        app.audio_manager.stop_track()

def _start_server():
    server = HTTPServer(("127.0.0.1", 5000), _WakeUpHandler)
    server.serve_forever()

def execute_voice_command(command):
    global alarm_on
    app = App.get_running_app()
    # show UI indicator
    if command == "VOICE_ACTIVATED":
        if app and hasattr(app, 'show_voice_popup'):
            app.show_voice_popup()
        return
    if command == "STOP_ALARM":
        if app:
            app.trigger_failsafe()
        Clock.schedule_once(lambda dt: _do_stop(), 0)
        if alarm_on:
            print("Stopping Alarm")
            alarm_on = False
        else:
            print("Alarm is not active.")
        # Add logic to stop the alarm
    elif command == "DEACTIVATE_LISTENING":
        print("Sentinel is no longer listening. Say \'Hey Sent\' to activate again.\n")
        # hide UI indicator
        if app and hasattr(app, 'hide_voice_popup'):
            app.hide_voice_popup()
        # Add logic to deactivate listening
        # Add flags as needed
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
        # Add logic to shut down the device
        # clean up resources

def start_voice_listening():
    voice_activate(execute_voice_command)

if __name__ == "__main__":
    threading.Thread(target=_start_server, daemon=True).start() # start HTTP server in background thread
    voice_thread = threading.Thread(target=start_voice_listening, daemon=True)
    voice_thread.start()
    SentinelApp().run()