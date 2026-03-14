"""
voice_activation.py
"""

from vosk import Model, KaldiRecognizer # add vosk import for offline model
import sounddevice as sd
import queue
import json
import time # add time import for inactivity timeout

MODEL_PATH = "vosk-model-small-en-us-0.15"
SAMPLE_RATE = 16000
activate_word = "hey sent" # make activation word shorter for better recognition

ACTIVE_TIMEOUT = 10 # auto-deactivate listening after 10 seconds of inactivity

# possible commands dictionary:
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

def voice_activate(command): #argument is a function in main program to execute commands
    is_active = False # sentinel's default setting is inactive (not listening)
    last_active_time = None # track last time a command was recognized

    # restrict Vosk to only listen for phrases specified (ignore random noise/speech)
    phrases = [activate_word] + list(VOICE_COMMANDS.keys())

    # initialize Vosk model and recognizer
    model = Model(MODEL_PATH)
    rec = KaldiRecognizer(model, SAMPLE_RATE, json.dumps(phrases))

    q = queue.Queue() # create thread-safe queue for real-time audio data

    # callback function to capture continuous audio data (called every time new audio arrives)
    def audio_callback(indata, frames, time, status):
        if status:
            print(status, flush=True)
        q.put(bytes(indata)) # add audio data to queue

    print("Say 'Hey Sent' to activate\n")

    with sd.RawInputStream(samplerate=SAMPLE_RATE, blocksize = 8000, dtype='int16', channels=1, callback=audio_callback):
        while True:
            try:
                try:
                    data = q.get(timeout=0.25 if is_active else None) # use short timeout to check for inactivity when active 
                except queue.Empty:
                    # no audio received in last 0.25 s (check timeout)
                    if is_active and last_active_time is not None:
                        if (time.time() - last_active_time) >= ACTIVE_TIMEOUT:
                            is_active = False
                            last_active_time = None
                            print("Auto-deactivated due to inactivity.")
                            try:
                                command('DEACTIVATE_LISTENING') # notify main program to stop listening and hide mic popup
                            except Exception as e:
                                print("Auto-deactivation callback error:", e)
                    continue

                # feed audio block to recognizer
                if rec.AcceptWaveform(data): # becomes true once complete phrase is recognized
                    result = rec.Result()
                    result_dict = json.loads(result) # parse JSON result
                    audio_text = result_dict.get("text", "").lower().strip() # extract recognized text
                    if not audio_text:
                        print("Come Again?")
                        continue
                    print(f"You said: {audio_text}")

                    # passive mode: "hey sentinel" not said yet
                    if not is_active:
                        if activate_word in audio_text:
                            is_active = True
                            last_active_time = time.time() # reset inactivity timer
                            print("Sentinel is now listening.")
                            # notify main program to show mic popup (listening)
                            try:
                                command('VOICE_ACTIVATED')
                            except Exception as e:
                                print("Activation callback error:", e)
                        else:
                            print("Sentinel is waiting for activation word.")
                        continue

                    last_active_time = time.time() # reset inactivity timer on any recognized command
                            
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
                    command(match_input)

                    # deactivate listening or shut down device to stop script
                    if match_input == "DEACTIVATE_LISTENING":
                        is_active = False
                    elif match_input == "SHUT_DOWN_DEVICE":
                        break
            except KeyboardInterrupt:
                break