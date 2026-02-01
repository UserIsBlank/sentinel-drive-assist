import speech_recognition as sr

activate_word = "hey sentinel"

# possible commands dictionary:
VOICE__COMMANDS = {
    # mute alarm commands
    "stop alarm": "STOP_ALARM",
    "mute": "STOP_ALARM",
    "silence": "STOP_ALARM",
    "stop": "STOP_ALARM",
    "quiet": "STOP_ALARM",
    "shut up": "STOP_ALARM",
    "no sound": "STOP_ALARM",
    "no alarm": "STOP_ALARM",

    # deactivate listening commands
    "deactivate": "DEACTIVATE_LISTENING",
    "stop listening": "DEACTIVATE_LISTENING",
    "sleep": "DEACTIVATE_LISTENING",

    # shut down device commands
    "shut down": "SHUT_DOWN_DEVICE",
    "power off": "SHUT_DOWN_DEVICE",
    "turn off": "SHUT_DOWN_DEVICE",
}

def voice_activate(command): #argument is a function in main program to execute commands
    r = sr.Recognizer()
    r.dynamic_energy_threshold = False
    r.energy_threshold = 400
    is_active = False # sentinel's default setting is inactive (not listening); True = actively listening for commands

    with sr.Microphone(sample_rate=16000) as source: #update to correct microphone source when hardware arrives
        r.adjust_for_ambient_noise(source, duration=2) #take 2 seconds to calibrate and adapt for background noise
        print("Say \'Hey Sentinel\' to activate\n")

        while True:
            try:
                if is_active:
                    print("Please say a command.") #activate word (hey sentinel) is said, can give commands

                #listen for activate word or command
                audio = r.listen(source, timeout=None, phrase_time_limit=5)

                try:
                    audio_text = r.recognize_google(audio).lower().strip() #use Google Web Speech API to convert audio into text
                    print(f"You said: {audio_text}")
                except sr.UnknownValueError: #heard audio input, but API doesn't understand/transcribe
                    print("Come again?")
                    continue
                except sr.RequestError as e:
                    print(f"Error: {e}")
                    continue

                # "hey sentinel" not said yet
                if not is_active:
                    if activate_word in audio_text:
                        is_active = True
                        print("Sentinel is now listening.")
                        # --- todo: update to connect to rest of device --- #
                    else:
                        print("Sentinel is waiting for activation word.")
                    continue

                # "hey sentinel" has been said (can say commands)
                match_input = None
                for phrase, cmd in VOICE__COMMANDS.items():
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
