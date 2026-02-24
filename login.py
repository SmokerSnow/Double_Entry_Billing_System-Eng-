import tkinter as tk
from tkinter import messagebox
from db_helper import get_connection
from main import main


class LoginApp:
    def __init__(self, root):
        self.root = root
        self.root.title("CT Login")

        # ---------- Window Size + Center ----------
        window_width = 520
        window_height = 420

        screen_width = root.winfo_screenwidth()
        screen_height = root.winfo_screenheight()

        x = (screen_width // 2) - (window_width // 2)
        y = (screen_height // 2) - (window_height // 2)

        root.geometry(f"{window_width}x{window_height}+{x}+{y}")
        root.resizable(False, False)

        # ---------- Background Image ----------
        try:
            self.bg_image = tk.PhotoImage(file="login_bg_img.jpg")
            bg_label = tk.Label(root, image=self.bg_image)
            bg_label.place(relwidth=1, relheight=1)
        except:
            root.configure(bg="#1e1e2f")  # fallback color

        # ---------- Main Login Frame ----------
        login_frame = tk.Frame(root, bg="white", bd=0)
        login_frame.place(relx=0.5, rely=0.5, anchor="center", width=350, height=260)

        # ---------- Title ----------
        tk.Label(
            login_frame,
            text="LOGIN",
            font=("Arial", 20, "bold"),
            bg="white",
            fg="#333"
        ).pack(pady=(20, 10))

        # ---------- Username ----------
        tk.Label(login_frame, text="Username", font=("Arial", 11), bg="white").pack()
        self.username_entry = tk.Entry(login_frame, font=("Arial", 12), width=25)
        self.username_entry.pack(pady=5)

        # ---------- Password ----------
        tk.Label(login_frame, text="Password", font=("Arial", 11), bg="white").pack()
        self.password_entry = tk.Entry(login_frame, font=("Arial", 12), show="*", width=25)
        self.password_entry.pack(pady=5)

        # ---------- Login Button ----------
        tk.Button(
            login_frame,
            text="Login",
            font=("Arial", 12, "bold"),
            bg="#4CAF50",
            fg="white",
            activebackground="#45a049",
            width=15,
            command=self.login
        ).pack(pady=20)

        # ---------- Enter Key Login ----------
        root.bind("<Return>", lambda event: self.login())

        # ---------- Auto Focus Username ----------
        self.username_entry.focus_set()

    # ---------- Login Function ----------
    def login(self):
        username = self.username_entry.get()
        password = self.password_entry.get()

        try:
            conn = get_connection()
            cursor = conn.cursor()

            query = "SELECT * FROM users WHERE username=%s AND password=%s"
            cursor.execute(query, (username, password))
            result = cursor.fetchone()

            conn.close()

            if result:
                self.root.destroy()
                main()
            else:
                messagebox.showerror("Error", "Invalid Credentials")

        except Exception as e:
            messagebox.showerror("DB Error", str(e))


# ---------- Run ----------
if __name__ == "__main__":
    root = tk.Tk()
    root.iconbitmap("New_Logo.ico")
    app = LoginApp(root)
    root.mainloop()