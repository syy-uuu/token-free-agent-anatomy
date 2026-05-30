import tkinter as tk
from tkinter import END, DISABLED, NORMAL, Tk, Entry, Text, Button, Grid, StringVar, messagebox
class Calculator(Tk):
    def __init__(self):
        super().__init__()
        self.title('Calculator')
        self.geometry('400x500')
        self.resizable(False, False)

        # Initialize string variables for inputs and outputs.
        self.equation = StringVar()
        self.result = StringVar()

        # Create the main display area
        self.label_display = tk.Label(self, textvariable=self.equation)
        self.label_display.grid(row=0, column=0, columnspan=4, padx=10, pady=5)  # Adjust grid positioning as necessary

        # Initialize current expression in the class scope
        self.current_expression = ''

    def create_ui(self):
        # Adding buttons for digits 0-9
        for i in range(3):
            for j in range(3):
                button = tk.Button(self, text=str((i*3)+j), width=5, height=2,
                                   command=lambda x=(i*3)+j: self.press(x))
                button.grid(row=i+1, column=j, padx=10, pady=5)

        # Adding operator buttons (+,-,*, /)
        for i in range(4):
            if i != 3:
                button = tk.Button(self, text='+' if (i == 3) else '-', width=6, height=2,
                                   command=lambda x='+': self.press(x))
                button.grid(row=i+1, column=3, padx=5, pady=5)
            else:
                button = tk.Button(self, text='/', width=6, height=2,
                                   command=lambda: self.press('/'))
                button.grid(row=i+1, column=4, padx=5, pady=5)  # Adjust grid positioning as necessary

    def press(self, key):
        current_expression = self.equation.get()
        try:
            result = eval(current_expression) + str(key)
        except Exception as e:
            messagebox.showerror('Error', str(e))
        else:
            self.equation.set(result)

    def button_click(self, value):  # Ensuring correct method signature
        if len(self.current_expression) < 24:
            self.current_expression += value
            self.label_display.config(text=self.current_expression)
def main():
    calc = Calculator()
    calc.create_ui()
    calc.mainloop()

if __name__ == '__main__':
    main()