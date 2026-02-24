import tkinter as tk

class TypingTab(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent)

        tk.Label(self, text="Typing Billing Section", font=("Arial", 16)).pack(pady=20)