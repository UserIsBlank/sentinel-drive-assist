import kivy
from kivy.app import App
from kivy.lang import Builder
from kivy.core.window import Window
from kivy.core.text import LabelBase
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.behaviors import ButtonBehavior
import os

kivy.require('1.11.1')
Window.clearcolor = (0.427, 0.435, 0.478, 1)
Window.size = (900, 550)
font_path = os.path.join(os.path.dirname(__file__), 'fonts')
LabelBase.register(name="SentinelFont", fn_regular="../fonts/Roboto_Slab/RobotoSlab-VariableFont_wght.ttf")

# TODO: Add Fail-safe button functionality
class FailSafeButton(ButtonBehavior, BoxLayout):
    pass


class Interface(FloatLayout):
    # TODO: Change the volume based on the slider
    def on_slider_value_change(self, instance, value):
        print(f"Slider value is: {int(value)}")

    # TODO: Add the mute and unmute functionality
    def on_failsafe_press(self):
        print("Fail-safe activated!")

class SentinelApp(App):
    def build(self):
        Builder.load_file('interface.kv')
        return Interface()


if __name__ == '__main__':
    SentinelApp().run()