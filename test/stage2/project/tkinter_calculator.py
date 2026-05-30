# tkinter_calculator.py
import tkinter as tk
class Calculator(tk.Frame):
    def __init__(self, master=None):
        super().__init__(master)
        self.pack()
        self.create_widgets()
    
    def create_widgets(self):
        self.label = tk.Label(self, text="Calculator")
        self.label.pack(side=tk.TOP)

        self.quit_button = tk.Button(self, text="QUIT", command=self.master.destroy)
        self.quit_button.pack(side=tk.BOTTOM)