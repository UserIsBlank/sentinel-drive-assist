import speech_recognition as sr

activate_word = "hey sentinel"

def voice_activate():
    r = sr.Recognizer()

    is_active = False # sentinel's default setting is inactive (not listening); True = actively listening for commands
    alarm_on = True # alarm is default on -- update once connected to actual alarm

    with sr.Microphone() as source:
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
                        
                # "hey sentinel" has been said (can say commands)
                else:
                    if (alarm_on) and ("stop alarm" in audio_text or "mute" in audio_text): # turn off alarm if it's playing
                        alarm_on = False
                        print("Alarm off.")
                        # --- todo: update to connect to alarm --- #
                    elif "deactivate" in audio_text or "stop listening" in audio_text: # turn off voice activation
                        is_active = False
                        print("Listening deactivated. Waiting for activation word.")
                    elif "shut down" in audio_text: # shut down whole device
                        print("Sentinel shutting down.")
                        break
                        # -- todo: update to connect to rest of device -- #
                    else:
                        print("Command not recognized.")
            except KeyboardInterrupt:
                break


if __name__ == "__main__":
    voice_activate()