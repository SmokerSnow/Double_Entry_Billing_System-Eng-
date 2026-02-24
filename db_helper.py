import mysql.connector
from tkinter import messagebox

def get_connection():
    try:
        conn = mysql.connector.connect(
            host="localhost",
            user="root",
            password="root",
            database="pos_db"
        )
        return conn
    except Exception as e:
        messagebox.showerror("DB Connection Error", str(e))
        exit()