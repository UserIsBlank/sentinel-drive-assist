from voice_activation import voice_activate
from kivy.app import App
from Interface import SentinelApp
import threading

print('Welcome to Sentinel')

alarm_on = True  # alarm is default on -- update once connected to actual alarm

def execute_voice_command(command):
    global alarm_on
    app = App.get_running_app()
    if command == "STOP_ALARM":
        if app:
            app.trigger_failsafe()
        if alarm_on:
            print("Stopping Alarm")
            alarm_on = False
        else:
            print("Alarm is not active.")
        # Add logic to stop the alarm
    elif command == "DEACTIVATE_LISTENING":
        print("Sentinel is no longer listening. Say \'Hey Sent\' to activate again.\n")
        # Add logic to deactivate listening
        # Add flags as needed
    elif command == "SHUT_DOWN_DEVICE":
        print("Shutting down Sentinel. Goodbye!")
        if app:
            app.stop()
        # Add logic to shut down the device
        # clean up resources

def start_voice_listening():
    voice_activate(execute_voice_command)

if __name__ == "__main__":
    voice_thread = threading.Thread(target=start_voice_listening, daemon=True)
    voice_thread.start()
    SentinelApp().run()