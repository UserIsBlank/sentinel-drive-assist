from voice_activation import voice_activate

print('Welcome to Sentinel')

alarm_on = True  # alarm is default on -- update once connected to actual alarm

def execute_voice_command(command):
    global alarm_on
    if command == "STOP_ALARM":
        if alarm_on:
            print("Stopping Alarm")
            alarm_on = False
        else:
            print("Alarm is not active.")
        # Add logic to stop the alarm
    elif command == "DEACTIVATE_LISTENING":
        print("Sentinel is no longer listening. Say \'Hey Sentinel\' to activate again.\n")
        # Add logic to deactivate listening
        # Add flags as needed
    elif command == "SHUT_DOWN_DEVICE":
        print("Shutting down Sentinel. Goodbye!")
        # Add logic to shut down the device
        # clean up resources

if __name__ == "__main__":
    voice_activate(execute_voice_command)