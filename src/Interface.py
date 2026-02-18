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
from kivy.uix.popup import Popup
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.event import EventDispatcher
from kivy.clock import mainthread
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
    selected_file = StringProperty(None)

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

    def set_default(self, path):
        self.selected_file = path
        print(f"[System] Default Alert Saved: {path}")

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
    def get_volume(self):
        return self.volume_level


class SoundItem(ButtonBehavior, BoxLayout):
    sound_file = StringProperty(None)
    is_selected = BooleanProperty(False)

    def on_press(self):
        self.opacity = 0.5

    def on_release(self):
        self.opacity = 1.0
        app = App.get_running_app()
        if app and app.audio_manager:
            self.show_confirmation_popup()

    def show_confirmation_popup(self):
        # Create the popup content
        content = BoxLayout(orientation='vertical', padding=10, spacing=10)

        lbl = Label(text=f"Set '{self.text}' as your\ndefault alert sound?",
                    halign='center', font_size='18sp')

        btn_layout = BoxLayout(spacing=10, size_hint_y=None, height="50dp")

        btn_yes = Button(text="Yes, Save", background_color=(0.4, 0.8, 0.4, 1))
        btn_no = Button(text="Cancel", background_color=(0.8, 0.4, 0.4, 1))

        btn_layout.add_widget(btn_yes)
        btn_layout.add_widget(btn_no)
        content.add_widget(lbl)
        content.add_widget(btn_layout)

        popup = Popup(title="Confirm Selection", content=content,
                      size_hint=(None, None), size=("300dp", "200dp"))

        # Bind Button Actions
        btn_yes.bind(on_release=lambda x: self.confirm_selection(popup))
        btn_no.bind(on_release=popup.dismiss)

        popup.open()

    def confirm_selection(self, popup):
        app = App.get_running_app()  # You must get the running app here again
        # 1. Update the AudioManager property
        app.audio_manager.set_default(self.sound_file)
        # 2. Update the config and write to file
        app.config.set('Audio', 'default_sound', self.sound_file)
        app.config.write()
        popup.dismiss()

class ImageButton(ButtonBehavior, BoxLayout):
    pass

class FailSafeButton(ButtonBehavior, BoxLayout):
    pass

class DetectionButton(ButtonBehavior, BoxLayout):
    def on_release(self):
        app = App.get_running_app()
        app.toggle_detection()
        if app.detection_active and app.audio_manager.selected_file:
            print(f"[System] Testing Alarm: {app.audio_manager.selected_file}")
            app.audio_manager.play_track(app.audio_manager.selected_file)

class Interface(FloatLayout):
    audio_manager = ObjectProperty(None)

    def on_failsafe_press(self):
        print("Fail-safe activated!")
        app = App.get_running_app()
        if app and app.audio_manager:
            app.audio_manager.stop_track()


class SentinelApp(App):
        audio_manager = ObjectProperty(None)
        detection_active = BooleanProperty(False)

        def build_config(self, config):
            config.setdefaults('Audio', {'default_sound': '../audio/alert1.mp3'})
            config.setdefaults('System', {'drowsiness_detection': 'false'})

        def build(self):
            self.audio_manager = AudioManager()

            saved_sound = self.config.get('Audio', 'default_sound')

            if not saved_sound or saved_sound == 'None':
                print("[System] Config was empty. Resetting to default.")
                saved_sound = '../audio/alert1.mp3'
                self.config.set('Audio', 'default_sound', saved_sound)
                self.config.write()

            self.audio_manager.selected_file = saved_sound
            print(f"[System] Startup Sound Loaded: {saved_sound}")

            saved_detection = self.config.get('System', 'drowsiness_detection')
            self.detection_active = True if saved_detection == 'True' else False

            Builder.load_file('interface.kv')
            return Interface()

        def set_volume(self, value_0_to_100):
            self.audio_manager.apply_volume(value_0_to_100)

        def toggle_detection(self):
            self.detection_active = not self.detection_active
            self.config.set('System', 'drowsiness_detection', str(self.detection_active))
            self.config.write()
            print(f"[System] Drowsiness Detection: {'Enabled' if self.detection_active else 'Disabled'}")

        @mainthread
        def trigger_failsafe(self):
            if self.audio_manager:
                print("[System] Fail-safe triggered via Voice Command!")
                self.audio_manager.stop_track()