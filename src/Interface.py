import kivy
from kivy.app import App
from kivy.lang import Builder
from kivy.core.window import Window
from kivy.core.text import LabelBase
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.behaviors import ButtonBehavior
from kivy.core.audio import SoundLoader
from kivy.properties import StringProperty, NumericProperty, ObjectProperty, BooleanProperty
from kivy.event import EventDispatcher
import os

kivy.require('1.11.1')

# --- Configuration ---
Window.clearcolor = (0.427, 0.435, 0.478, 1)
Window.size = (900, 550)

font_path = os.path.join(os.path.dirname(__file__), '../fonts/Roboto_Slab/RobotoSlab-VariableFont_wght.ttf')
if os.path.exists(font_path):
    LabelBase.register(name="SentinelFont", fn_regular=font_path)

class AudioManager(EventDispatcher):
    current_sound = ObjectProperty(None, allownone=True)
    volume_level = NumericProperty(0.5)  # Default 50%
    is_muted = BooleanProperty(False)

    def play_track(self, path):
        if not path:
            return

        self.stop_track()

        self.current_sound = SoundLoader.load(path)

        if self.current_sound:
            self._apply_volume()
            self.current_sound.play()
            print(f"[Audio] Playing: {path}")
        else:
            print(f"[Audio] Error: Could not load {path}")

    def stop_track(self):
        if self.current_sound:
            self.current_sound.stop()

    def set_volume(self, value_0_to_100):
        self.volume_level = value_0_to_100 / 100.0
        self._apply_volume()

    def toggle_mute(self):
        self.is_muted = not self.is_muted
        self._apply_volume()

    def _apply_volume(self):
        if self.current_sound:
            if self.is_muted:
                self.current_sound.volume = 0
            else:
                self.current_sound.volume = self.volume_level


class SoundItem(ButtonBehavior, BoxLayout):
    sound_file = StringProperty(None)

    def on_press(self):
        self.opacity = 0.5

    def on_release(self):
        self.opacity = 1.0
        app = App.get_running_app()
        if app and app.audio_manager:
            app.audio_manager.play_track(self.sound_file)


class ImageButton(ButtonBehavior, BoxLayout):
    pass


class FailSafeButton(ButtonBehavior, BoxLayout):
    pass


class Interface(FloatLayout):
    audio_manager = ObjectProperty(None)
    def on_failsafe_press(self):
        print("Fail-safe activated!")
        app = App.get_running_app()
        if app and app.audio_manager:
            app.audio_manager.stop_track()


class SentinelApp(App):
        audio_manager = ObjectProperty(None)

        def build(self):
            self.audio_manager = AudioManager()
            Builder.load_file('interface.kv')

            return Interface()


if __name__ == '__main__':
    SentinelApp().run()