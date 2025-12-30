import kivy
from kivy.app import App
from kivy.uix.label import Label
from kivy.core.window import Window
kivy.require('1.11.1')

class Interface(App):
    def build(self):
        Window.clearcolor = (0.2, 0.2, 0.2, 1)

        return Label(text='Sentinel Drive Assist', font_size='24sp')


if __name__ == '__main__':
    Interface().run()