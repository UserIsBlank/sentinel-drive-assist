import kivy
from kivy.app import App
from kivy.uix.label import Label
kivy.require('1.11.1')

class Interface(App):
    def build(self):
        return Label(text='Welcome to Sentinel', font_size='24sp', color=(1.0, 0.75, 1.0, 1))


if __name__ == '__main__':
    Interface().run()