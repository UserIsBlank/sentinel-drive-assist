import kivy
from kivy.app import App
from kivy.properties import get_color_from_hex
from kivy.uix.label import Label
from kivy.core.window import Window
from kivy.core.text import LabelBase
from kivy.uix.button import Button
from kivy.uix.widget import Widget
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.slider import Slider

import os
kivy.require('1.11.1')

font_path = os.path.join(os.path.dirname(__file__), 'fonts')
LabelBase.register(name="SentinelFont", fn_regular="../fonts/Roboto_Slab/RobotoSlab-VariableFont_wght.ttf")

class Interface(App):
    def build(self):
        Window.clearcolor = get_color_from_hex("#6D6F7A")
        layout = FloatLayout()

        # Create Text
        label = Label(text='Sentinel Drive-Assist', font_name="SentinelFont", font_size='36sp',
                      pos_hint={'center_x': 0.5, 'center_y': 0.8})
        layout.add_widget(label)

        # Create failsafe button
        button1 = Button(text="Fail safe", background_normal='', background_color=get_color_from_hex("7096D1"), size_hint=(None, None), size=(200, 200), pos_hint={"center_x": 0.5, "center_y": 0.5})
        button1.bind(on_press=lambda _: Window.clearcolor)
        layout.add_widget(button1)

        # Create slider
        self.slider = Slider(min = 0, max = 100, value=0, step=1, size_hint=(None, None), size=(500, 100), pos_hint={"center_x": 0.2, "center_y": 0.2})
        self.slider.bind(value=self.on_slider_value_change)
        layout.add_widget(self.slider)

        return layout

    def on_slider_value_change(self, instance, value):
        print(f"Slider value is: {value}")


if __name__ == '__main__':
    Interface().run()