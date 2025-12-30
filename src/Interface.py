import kivy
from kivy.app import App
from kivy.uix.label import Label
from kivy.core.window import Window
from kivy.core.text import LabelBase
import os
kivy.require('1.11.1')

font_path = os.path.join(os.path.dirname(__file__), 'fonts')
LabelBase.register(name="SentinelFont", fn_regular="../fonts/Roboto_Slab/RobotoSlab-VariableFont_wght.ttf")

class Interface(App):
    def build(self):
        Window.clearcolor = (0.2, 0.2, 0.2, 1)

        return Label(text='Sentinel Drive Assist', font_name="SentinelFont",font_size='24sp')


if __name__ == '__main__':
    Interface().run()