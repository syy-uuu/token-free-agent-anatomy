# Import necessary libraries
import tkinter as tk
from tkinter import messagebox

def perform_calculations(expression):
    try:
        result = eval(expression)
        return str(result)
    except Exception as e:
        return 'Error: ' + str(e)

def button_press(symbol, entry_field):
    current_text = entry_field.get()
    if symbol in ['+', '-', '*', '/']:
        # Clear the field and add operation
        entry_field.delete(0, 'end')
        entry_field.insert(tk.END, current_text + symbol)
    else:
        entry_field.insert(tk.END, symbol)

def calculate(entry_field, output_field):
    try:
        expression = entry_field.get()
        result = perform_calculations(expression)
        output_field.delete('1.0', tk.END)
        output_field.insert(tk.END, result)
    except Exception as e:
        messagebox.showerror('Error', str(e))

def main():
    root = tk.Tk()
    root.title('Calculator App')

    calculator_frame = tk.Frame(root, padx=20, pady=20)
    calculator_frame.grid(row=0, column=0)

    entry_field = tk.Entry(calculator_frame, width=35, borderwidth=4, relief=tk.SOLID, font=('calibri', 18))

    def on_number_press(button_text=button_text):
        global entry_field_value
        entry_field_value += str(button_text)
        root.event_generate('<Return>')

    def on_operator_press(symbol=symbol):
        update_expression(entry_field.get() + symbol)

    # Function for operator buttons
    operators = [
        ('+', 1, 6),
        ('-', 2, 6),
        ('*', 3, 6),
        ('/', 4, 6)
    ]

    def on_operator_press(symbol=symbol):
        update_expression(entry_field.get() + symbol)
    
    root.mainloop()

if __name__ == '__main__':

def update_expression(expression):
    entry_field.insert(tk.END, expression)
