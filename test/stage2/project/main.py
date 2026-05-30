# main.py
import tkinter as tk
from tkinter_calculator import Calculator  # Direct import
def main():
    root = tk.Tk()
    calc = Calculator(root)
    root.mainloop()

if __name__ == '__main__':
    from tkinter_calculator import Calculator
    main()