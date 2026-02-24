import tkinter as tk

class InventoryTab(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent)

        tk.Label(self, text="Inventory Section", font=("Arial", 16)).pack(pady=20)
