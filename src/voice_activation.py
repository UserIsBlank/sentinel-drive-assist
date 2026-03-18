"""
voice_activation.py
"""

from vosk import Model, KaldiRecognizer
import sounddevice as sd
import queue
import json
import urllib.request
import time

MODEL_PATH = "vosk-model-small-en-us-0.15"
SAMPLE_RATE = 16000
activate_word = "hey sent"
ACTIVE_TIMEOUT = 10

# Possible commands dictionary:
VOICE_COMMANDS = {
    # mute alarm commands
    "stop alarm": "STOP_ALARM",
    "mute": "STOP_ALARM",
    "silence": "STOP_ALARM",
    "quiet": "STOP_ALARM",
    "shut up": "STOP_ALARM",
    "no sound": "STOP_ALARM",
    "no alarm": "STOP_ALARM",

    # deactivate listening commands
    "deactivate": "DEACTIVATE_LISTENING",
    "stop listening": "DEACTIVATE_LISTENING",
    "sleep": "DEACTIVATE_LISTENING",

    # disable detection commands
    "disable detection": "DISABLE_DETECTION",
    "stop detection": "DISABLE_DETECTION",
    "turn off detection": "DISABLE_DETECTION",
    "disable drowsiness detection": "DISABLE_DETECTION",
    "turn off drowsiness detection": "DISABLE_DETECTION",

    # enable detection commands
    "enable detection": "ENABLE_DETECTION",
    "start detection": "ENABLE_DETECTION",
    "turn on detection": "ENABLE_DETECTION",
    "enable drowsiness detection": "ENABLE_DETECTION",
    "turn on drowsiness detection": "ENABLE_DETECTION",
    
    # shut down device commands
    "shut down": "SHUT_DOWN_DEVICE",
    "power off": "SHUT_DOWN_DEVICE",
    "turn off": "SHUT_DOWN_DEVICE",

    # reset alert commands
    "i'm awake": "RESET_ALERT",
    "i am awake": "RESET_ALERT",
    "reset alert": "RESET_ALERT",
    "clear alert": "RESET_ALERT",
    "cancel alert": "RESET_ALERT",
    "dismiss alert": "RESET_ALERT",

    # sensitivity commands
    "use lower sensitivity": "SENSITIVITY_CONSERVATIVE",
    "use low sensitivity": "SENSITIVITY_CONSERVATIVE",
    "lower sensitivity": "SENSITIVITY_CONSERVATIVE",
    "low sensitivity": "SENSITIVITY_CONSERVATIVE",
    "sensitivity low": "SENSITIVITY_CONSERVATIVE",
    "use higher sensitivity": "SENSITIVITY_AGGRESSIVE",
    "use high sensitivity": "SENSITIVITY_AGGRESSIVE",
    "high sensitivity": "SENSITIVITY_AGGRESSIVE",
    "sensitivity high": "SENSITIVITY_AGGRESSIVE",
    "use default sensitivity": "SENSITIVITY_DEFAULT",
    "use medium sensitivity": "SENSITIVITY_DEFAULT",
    "use normal sensitivity": "SENSITIVITY_DEFAULT",
    "default sensitivity": "SENSITIVITY_DEFAULT",
    "sensitivity default": "SENSITIVITY_DEFAULT",
    "medium sensitivity": "SENSITIVITY_DEFAULT",
    "normal sensitivity": "SENSITIVITY_DEFAULT",
}

def send_command_to_ui(cmd_string):
    """Sends the recognized command to the main Kivy UI process via HTTP"""
    try:
        payload = json.dumps({"command": cmd_string}).encode("utf-8")
        req = urllib.request.Request(
            "http://127.0.0.1:5000/voice_command", 
            data=payload, 
            headers={"Content-Type": "application/json"}
        )
        urllib.request.urlopen(req, timeout=1.0)
    except Exception as e:
        print(f"[Voice] Failed to send command to UI: {e}")

def voice_activate():
    is_active = False
    last_active_time = None

    phrases = [activate_word] + list(VOICE_COMMANDS.keys())

    model = Model(MODEL_PATH)
    rec = KaldiRecognizer(model, SAMPLE_RATE, json.dumps(phrases))

    q = queue.Queue()

    def audio_callback(indata, frames, time_info, status):
        if status:
            print(status, flush=True)
        q.put(bytes(indata))

    print("Say 'Hey Sent' to activate\n")

    with sd.RawInputStream(samplerate=SAMPLE_RATE, blocksize = 8000, dtype='int16', channels=1, callback=audio_callback):
        while True:
            try:
                try:
                    data = q.get(timeout=0.25 if is_active else None)
                except queue.Empty:
                    if is_active and last_active_time is not None:
                        if (time.time() - last_active_time) >= ACTIVE_TIMEOUT:
                            is_active = False
                            last_active_time = None
                            print("Auto-deactivated due to inactivity.")
                            send_command_to_ui("DEACTIVATE_LISTENING")
                    continue

                if rec.AcceptWaveform(data):
                    result = rec.Result()
                    result_dict = json.loads(result)
                    audio_text = result_dict.get("text", "").lower().strip()
                    if not audio_text:
                        print("Come Again?")
                        continue
                    print(f"You said: {audio_text}")

                    # passive mode: "hey sentinel" not said yet
                    if not is_active:
                        if activate_word in audio_text:
                            is_active = True
                            last_active_time = time.time()
                            print("Sentinel is now listening.")
                            send_command_to_ui("VOICE_ACTIVATED")
                        else:
                            print("Sentinel is waiting for activation word.")
                        continue

                    last_active_time = time.time()
                            
                    # active mode: "hey sentinel" has been said (can say commands)
                    match_input = None
                    for phrase, cmd in VOICE_COMMANDS.items():
                        if phrase in audio_text:
                            match_input = cmd
                            break
                    if match_input is None:
                        print("Command not recognized. Please try again.")
                        continue

                    # execute matched command (send to main program)
                    send_command_to_ui(match_input)

                    # deactivate listening or shut down device to stop script
                    if match_input == "DEACTIVATE_LISTENING":
                        is_active = False
                    elif match_input == "SHUT_DOWN_DEVICE":
                        break
            except KeyboardInterrupt:
                break

if __name__ == "__main__":
    print("[Voice] Starting standalone voice activation process...")
    voice_activate()