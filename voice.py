import tkinter as tk
import mysql.connector
from tkinter import ttk, messagebox, font
import threading, math, tempfile, os, time, webbrowser
from datetime import datetime
from escpos.printer import Serial
from db_helper import get_connection
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By


try:
    import keyboard
except Exception:
    keyboard = None

try:
    import json, queue
    import sounddevice as sd
    from vosk import Model, KaldiRecognizer
except Exception:
    json, queue, sd, Model, KaldiRecognizer = None, None, None, None, None


MODEL_PATH = "vosk-model-hi-0.22"
CHROMEDRIVER_PATH = None


class VoiceTab(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent)

        # ----- Database -----
        self.conn = get_connection()
        self.cursor = self.conn.cursor()

        # ----- Fonts / Style -----
        self.global_font = font.Font(family="Arial", size=13)
        self.button_font = font.Font(family="Arial", size=13, weight="bold")

        style = ttk.Style()
        style.configure("Treeview", font=("Arial", 12))
        heading_font = font.Font(family="Arial", size=12, weight="bold")
        style.configure("Treeview.Heading", font=heading_font)

        # ----- State -----
        self.active_bill = None
        self.product_names = []
        self.all_products = []
        self.editing_entry = None

        # Voice state
        self.listening = False
        self.model = None
        self.rec = None
        self.q = queue.Queue() if queue else None
        self.current_user = 1

        # ----- Build UI -----
        self.build_layout()

        # ----- Load products into product_tree + suggestions -----
        self.fetch_products()
        self.init_suggestions()
        self.start_printer_keepalive(devfile="COM30", interval=30)
        # ----- Start keyboard listener for CapsLock (if available) -----
        if keyboard:
            threading.Thread(target=self.keyboard_listener, daemon=True).start()

    # =========================================================
    # UI LAYOUT
    # =========================================================
    def build_layout(self):
        # ================= LEFT PANEL =================
        left_panel = tk.Frame(self, bd=2, relief="groove")
        left_panel.pack(side=tk.LEFT, fill=tk.Y, padx=10, pady=10)

        # Control (top)
        control_frame = tk.Frame(left_panel)
        control_frame.pack(fill=tk.X, pady=10)

        self.load_btn = tk.Button(
            control_frame,
            text="Load Model",
            font=self.button_font,
            command=self.load_model_click,
            width=25,
            height=2
        )
        self.load_btn.pack(pady=(0, 5))

        light_frame = tk.Frame(control_frame)
        light_frame.pack(pady=5)

        self.light1 = tk.Label(light_frame, width=4, height=2, bg="red")
        self.light1.pack(side=tk.LEFT, padx=10)

        self.light2 = tk.Label(light_frame, width=4, height=2, bg="red")
        self.light2.pack(side=tk.LEFT, padx=10)

        self.user_btn = tk.Button(
            control_frame,
            text="User 1",
            font=self.button_font,
            command=self.cycle_user,
            width=25,
            height=2
        )
        self.user_btn.pack(pady=(5, 5))

        # Suggestions
        tk.Label(left_panel, text="SUGGESTIONS", font=("Arial", 16, "bold")).pack(pady=5)

        self.suggestion_box = tk.Listbox(
            left_panel,
            font=self.global_font,
            height=30,
            width=30
        )
        self.suggestion_box.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # ================= RIGHT PANEL =================
        right_panel = tk.Frame(self)
        right_panel.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Product tree (top)
        self.product_tree = ttk.Treeview(
            right_panel,
            columns=("ID", "Name_EN", "Name_HI", "Price"),
            show="headings",
            height=6
        )
        for col, text in zip(
            ("ID", "Name_EN", "Name_HI", "Price"),
            ("ID", "Name (English)", "Name (Hindi)", "Price")
        ):
            self.product_tree.heading(col, text=text)
            self.product_tree.column(col, anchor="w", width=160)
        self.product_tree.pack(fill=tk.X, padx=10, pady=(0, 10))

        # Click fills active entry; double-click adds to bill
        self.product_tree.bind("<ButtonRelease-1>", self.select_product)
        self.product_tree.bind("<Double-1>", self.product_tree_double_click_add)

        # Bills (below product tree)
        bills_frame = tk.Frame(right_panel)
        bills_frame.pack(fill=tk.BOTH, expand=True)

        self.left_bill = self.create_bill_panel(bills_frame)
        self.right_bill = self.create_bill_panel(bills_frame)

        self.left_bill["frame"].pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5)
        self.right_bill["frame"].pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=5)

        self.active_bill = self.left_bill

        # ----- Bindings after bills exist -----
        for bill in (self.left_bill, self.right_bill):
            # focus tracking
            bill["entry"].bind("<FocusIn>", lambda e, w=bill["entry"]: self.set_active_bill_by_widget(w))
            bill["cust_entry"].bind("<FocusIn>", lambda e, w=bill["cust_entry"]: self.set_active_bill_by_widget(w))
            bill["tree"].bind("<FocusIn>", lambda e, w=bill["tree"]: self.set_active_bill_by_widget(w))

            # entry suggestions + add
            bill["entry"].bind("<KeyRelease>", self.update_suggestions_for_widget)
            bill["entry"].bind("<KeyPress>", self.on_entry_key_nav)
            bill["entry"].bind("<Return>", lambda e, b=bill: self.add_to_bill(e, b))

            # buttons
            bill["clear_btn"].config(command=lambda b=bill: self.clear_bill(b))
            bill["copy_btn"].config(command=lambda b=bill: self.copy_bill_to_clipboard(b))
            bill["paste_btn"].config(command=lambda b=bill: self.paste_bill_to_pos(b))
            bill["print_btn"].config(command=lambda b=bill: self.print_bill(b))

            # tree actions
            bill["tree"].bind("<Delete>", lambda e, b=bill: self.delete_selected_bill_item(e, b))
            bill["tree"].bind("<Double-1>", lambda e, t=bill["tree"], items=bill["items"]: self.on_tree_double_click(e, t, items))

        # suggestion box events
        self.suggestion_box.bind("<<ListboxSelect>>", self.suggestion_click_select)
        self.suggestion_box.bind("<Double-Button-1>", self.suggestion_double_click)
        self.suggestion_box.bind("<Key>", self.suggestion_box_key)
        self.suggestion_box.bind("<ButtonRelease-1>", self.suggestion_click_select)

        # focus starting point
        self.left_bill["entry"].focus_set()

    # =========================================================
    # BILL PANEL UI (same as main.py style)
    # =========================================================
    def create_bill_panel(self, parent):
        frame = tk.Frame(parent, relief=tk.GROOVE, borderwidth=2)

        # Customer row
        top = tk.Frame(frame)
        tk.Label(top, text="Customer:", font=self.button_font).pack(side=tk.LEFT, padx=(5, 2))
        cust_entry = tk.Entry(top, font=self.global_font)
        cust_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
        top.pack(fill=tk.X, pady=6, padx=6)

        # Product row
        product_row = tk.Frame(frame)
        tk.Label(product_row, text="Product Name", font=self.button_font).pack(side=tk.LEFT)
        entry = tk.Entry(product_row, font=self.global_font)
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(10, 0))
        product_row.pack(fill=tk.X, padx=6)

        # Bill tree
        tree = ttk.Treeview(frame, columns=("Name", "Qty", "Price", "Total"), show="headings", height=18)
        for col, width in zip(("Name", "Qty", "Price", "Total"), (260, 60, 90, 100)):
            tree.heading(col, text=col)
            tree.column(col, width=width, anchor="center")
        tree.pack(fill=tk.BOTH, padx=6, pady=6, expand=True)

        # Bottom totals
        bottom = tk.Frame(frame)
        items_label = tk.Label(bottom, text="Items: 0", font=("Arial", 14, "bold"))
        items_label.pack(side=tk.LEFT)
        total_label = tk.Label(bottom, text="Grand Total: 0", font=("Arial", 16, "bold"))
        total_label.pack(side=tk.LEFT, padx=(180, 0))
        bottom.pack(fill=tk.X, pady=(0, 6), padx=(90, 0))

        # Buttons row
        btn_row = tk.Frame(frame)
        clear_btn = tk.Button(btn_row, text="Clear Bill", font=self.button_font, width=15, height=2)
        clear_btn.pack(side=tk.LEFT, padx=15)
        copy_btn = tk.Button(btn_row, text="Copy Bill", font=self.global_font, width=8, height=2)
        copy_btn.pack(side=tk.LEFT, padx=2)
        paste_btn = tk.Button(btn_row, text="Paste Bill", font=self.global_font, width=8, height=2)
        paste_btn.pack(side=tk.LEFT, padx=2)
        print_btn = tk.Button(btn_row, text="Print Bill", font=self.button_font, width=15, height=2)
        print_btn.pack(side=tk.LEFT, padx=15)
        btn_row.pack(pady=(0, 10))

        return {
            "frame": frame,
            "cust_entry": cust_entry,
            "entry": entry,
            "tree": tree,
            "total_label": total_label,
            "items_label": items_label,
            "clear_btn": clear_btn,
            "print_btn": print_btn,
            "copy_btn": copy_btn,
            "paste_btn": paste_btn,
            "items": {}
        }

    # =========================================================
    # PRODUCTS: Fetch / Populate tree + cache
    # =========================================================
    def fetch_products(self):
        self.cursor.execute("SELECT id, name_en, name_hi, price FROM products ORDER BY name_en ASC")
        rows = self.cursor.fetchall()

        self.all_products = rows[:]
        self.product_names = [r[1] for r in rows]

        # Fill product tree
        try:
            self.product_tree.delete(*self.product_tree.get_children())
            for r in rows:
                self.product_tree.insert("", tk.END, values=r)
        except Exception:
            pass

    def init_suggestions(self):
        self.suggestion_box.delete(0, tk.END)
        for name in self.product_names:
            self.suggestion_box.insert(tk.END, name)

    # =========================================================
    # ACTIVE BILL
    # =========================================================
    def set_active_bill_by_widget(self, widget):
        if widget in (self.left_bill["entry"], self.left_bill["cust_entry"], self.left_bill["tree"]):
            self.active_bill = self.left_bill
        elif widget in (self.right_bill["entry"], self.right_bill["cust_entry"], self.right_bill["tree"]):
            self.active_bill = self.right_bill

    def focus_active_product_entry(self):
        try:
            if self.active_bill:
                self.active_bill["entry"].focus_set()
        except Exception:
            pass

    # =========================================================
    # SUGGESTIONS + NAV
    # =========================================================
    def update_suggestions_for_widget(self, event):
        if event.keysym in ("Up", "Down", "Return"):
            return

        widget = event.widget
        self.set_active_bill_by_widget(widget)

        typed = widget.get().strip().lower()

        # left suggestion list
        self.suggestion_box.delete(0, tk.END)
        if typed == "":
            for name in self.product_names:
                self.suggestion_box.insert(tk.END, name)
        else:
            for name in self.product_names:
                if typed in name.lower():
                    self.suggestion_box.insert(tk.END, name)

        # top product tree filter
        filtered = self.all_products if typed == "" else [r for r in self.all_products if typed in r[1].lower()]
        self.product_tree.delete(*self.product_tree.get_children())
        for r in filtered:
            self.product_tree.insert("", tk.END, values=r)

    def on_entry_key_nav(self, event):
        if event.keysym not in ("Down", "Up"):
            return  # do not touch Enter here

        widget = event.widget
        self.set_active_bill_by_widget(widget)

        size = self.suggestion_box.size()
        if size == 0:
            return

        cur = self.suggestion_box.curselection()
        idx = cur[0] if cur else -1

        if event.keysym == "Down":
            new_idx = 0 if idx == -1 else (idx + 1) % size
        else:
            new_idx = size - 1 if idx == -1 else (idx - 1) % size

        self.suggestion_box.selection_clear(0, tk.END)
        self.suggestion_box.selection_set(new_idx)
        self.suggestion_box.activate(new_idx)
        self.suggestion_box.see(new_idx)
        self.suggestion_box.focus_set()

        if event.keysym == "Return":
            cur = self.suggestion_box.curselection()
            if cur:
                val = self.suggestion_box.get(cur)
                widget.delete(0, tk.END)
                widget.insert(0, val)
            if self.active_bill:
                self.add_to_bill(None, self.active_bill)

    def suggestion_box_key(self, event):
        size = self.suggestion_box.size()
        if size == 0:
            return

        cur = self.suggestion_box.curselection()
        idx = cur[0] if cur else -1

        if event.keysym == "Down":
            new_idx = 0 if idx == -1 else (idx + 1) % size
        elif event.keysym == "Up":
            new_idx = size - 1 if idx == -1 else (idx - 1) % size
        elif event.keysym == "Return":
            if idx == -1 and size > 0:
                idx = 0
            if idx == -1:
                return "break"

            selected = self.suggestion_box.get(idx)
            if self.active_bill is None:
                self.active_bill = self.left_bill

            self.active_bill["entry"].delete(0, tk.END)
            self.active_bill["entry"].insert(0, selected)
            self.add_to_bill(None, self.active_bill)
            self.active_bill["entry"].focus_set()
            return "break"
        else:
            return

        self.suggestion_box.selection_clear(0, tk.END)
        self.suggestion_box.selection_set(new_idx)
        self.suggestion_box.activate(new_idx)
        self.suggestion_box.see(new_idx)
        return "break"

    def suggestion_click_select(self, event):
        cur = self.suggestion_box.curselection()
        if not cur:
            return
        selected = self.suggestion_box.get(cur)
        if self.active_bill is None:
            self.active_bill = self.left_bill
        self.active_bill["entry"].delete(0, tk.END)
        self.active_bill["entry"].insert(0, selected)

    def suggestion_double_click(self, event):
        cur = self.suggestion_box.curselection()
        if not cur:
            return
        selected = self.suggestion_box.get(cur)
        if self.active_bill is None:
            self.active_bill = self.left_bill
        self.active_bill["entry"].delete(0, tk.END)
        self.active_bill["entry"].insert(0, selected)
        self.add_to_bill(None, self.active_bill)

    # =========================================================
    # PRODUCT TREE: select -> fill, double click -> add
    # =========================================================
    def select_product(self, event):
        iid = self.product_tree.focus()
        if not iid:
            return
        values = self.product_tree.item(iid, "values")
        if not values:
            return
        name_en = values[1]

        if self.active_bill is None:
            self.active_bill = self.left_bill

        self.active_bill["entry"].delete(0, tk.END)
        self.active_bill["entry"].insert(0, name_en)
        self.active_bill["entry"].focus_set()

    def product_tree_double_click_add(self, event):
        self.select_product(event)
        if self.active_bill:
            self.add_to_bill(None, self.active_bill)

    # =========================================================
    # BILL OPS: add / clear / delete
    # =========================================================
    def add_to_bill(self, event=None, bill=None, qty_override=None, price_override=None):
        if bill is None:
            return

        cur = self.suggestion_box.curselection()
        if cur:
            name_text = self.suggestion_box.get(cur[0]).strip()
        else:
            name_text = bill["entry"].get().strip()

        if not name_text:
            return
        
        self.cursor.execute(
            """
            SELECT id, name_en, name_hi, price
            FROM products
            WHERE LOWER(name_en)=LOWER(%s) OR name_hi=%s
            LIMIT 1
            """,
            (name_text.lower(), name_text)
        )
        product = self.cursor.fetchone()
        
        if not product:
            messagebox.showerror("Error", "Product not found")
            bill["entry"].delete(0, tk.END)
            bill["entry"].focus_set()
            return
        
        product_id, name_en_db, name_hi, db_price = product
        db_price = float(db_price)

        if qty_override is not None and price_override is not None:
            bill["items"][product_id] = [name_hi, float(price_override), int(qty_override)]
        else:
            if product_id in bill["items"]:
                bill["items"][product_id][2] += 1
            else:
                bill["items"][product_id] = [name_hi, db_price, 1]

        self.refresh_bill_for_tree(bill["tree"], bill["items"])
        bill["entry"].delete(0, tk.END)

        # auto focus qty cell
        self.after(60, lambda b=bill, pid=product_id: self.start_edit_cell(b["tree"], b["items"], str(pid), 1))

    def clear_bill(self, bill):
        bill["items"].clear()
        self.refresh_bill_for_tree(bill["tree"], bill["items"])
        bill["entry"].focus_set()

    def delete_selected_bill_item(self, event=None, bill=None):
        if bill is None:
            return
        sel = bill["tree"].selection()
        for iid in sel:
            pid = int(iid)
            if pid in bill["items"]:
                del bill["items"][pid]
        self.refresh_bill_for_tree(bill["tree"], bill["items"])

    # =========================================================
    # COPY / PASTE
    # =========================================================
    def copy_bill_to_clipboard(self, bill):
        try:
            lines = []
            for pid, (name_hi, price, qty) in bill["items"].items():
                lines.append(f"{int(pid)}|{float(price)}|{qty}")
            text = "\n".join(lines)
            self.clipboard_clear()
            self.clipboard_append(text)
        except Exception as e:
            messagebox.showerror("Copy Error", str(e))

    def paste_bill_to_pos(self, bill):
        try:
            data = self.clipboard_get().strip()
        except Exception:
            messagebox.showwarning("Paste Error", "Clipboard empty or unavailable.")
            return

        if not data:
            messagebox.showwarning("Paste Error", "Clipboard has no bill data.")
            return

        pasted_any = False

        for line in data.splitlines():
            parts = [p.strip() for p in line.split("|")]
            if len(parts) < 3:
                continue

            try:
                pid = int(parts[0])
                price = float(parts[1])
                qty = float(parts[2]) if "." in parts[2] else int(parts[2])
            except Exception:
                continue

            try:
                self.cursor.execute("SELECT name_hi FROM products WHERE id=%s", (pid,))
                row = self.cursor.fetchone()
                if not row:
                    continue
                name_hi = row[0]
            except Exception:
                continue

            if pid in bill["items"]:
                existing_qty = bill["items"][pid][2]
                if isinstance(existing_qty, int) and isinstance(qty, int):
                    new_qty = existing_qty + qty
                else:
                    new_qty = round(float(existing_qty) + float(qty), 2)
                bill["items"][pid][2] = new_qty
                bill["items"][pid][1] = float(price)
            else:
                bill["items"][pid] = [name_hi, float(price), int(qty) if isinstance(qty, int) else round(float(qty), 2)]

            pasted_any = True

        if pasted_any:
            self.refresh_bill_for_tree(bill["tree"], bill["items"])
        else:
            messagebox.showwarning("Paste Error", "No valid bill lines found in clipboard.")

    # =========================================================
    # HELPERS: formatting / refresh
    # =========================================================
    def format_qty_display(self, qty):
        try:
            if isinstance(qty, int):
                return str(qty)
            q = float(qty)
            if q.is_integer():
                return str(int(q))
            return f"{round(q,2):.2f}".rstrip("0").rstrip(".")
        except Exception:
            return str(qty)

    def format_price(self, p):
        try:
            return f"{float(p):.2f}"
        except Exception:
            return str(p)

    def refresh_bill_for_tree(self, tree, bill_items):
        tree.delete(*tree.get_children())
        total = 0.0

        for pid, item in bill_items.items():
            name_hi, price, qty = item
            line_total = math.ceil(float(price) * float(qty))
            total += line_total

            tree.insert(
                "",
                tk.END,
                iid=str(pid),
                values=(name_hi, self.format_qty_display(qty), self.format_price(price), f"{line_total:,}")
            )

        # update the right labels for the correct bill
        for b in (self.left_bill, self.right_bill):
            if b["tree"] is tree:
                b["items_label"].config(text=f"Items: {len(bill_items)}")
                b["total_label"].config(text=f"Grand Total: {int(round(total)):,}")
                if bill_items:
                    last_item = list(bill_items.keys())[-1]
                    try:
                        tree.see(str(last_item))
                    except Exception:
                        pass
                break

    def filter_products_by_text(self, text):
        """Returns list of products (id,name_en,name_hi,price) that match text in EN or HI."""
        t = (text or "").strip().lower()
        if not t:
            return self.all_products

        matched = []
        for pid, name_en, name_hi, price in self.all_products:
            en = (name_en or "").lower()
            hi = (name_hi or "").lower()
            if t in en or t in hi:
                matched.append((pid, name_en, name_hi, price))
        return matched

    # =========================================================
    # INLINE EDITING
    # =========================================================
    def start_edit_cell(self, tree, bill_items, item, col_index):
        try:
            if self.editing_entry:
                self.editing_entry.destroy()
        except Exception:
            pass
        self.editing_entry = None

        col_id = f"#{col_index+1}"
        try:
            x, y, width, height = tree.bbox(item, col_id)
        except Exception:
            return
        if width <= 0:
            return

        cur_val = tree.set(item, tree["columns"][col_index])
        entry = tk.Entry(tree, font=self.global_font)
        entry.insert(0, cur_val)
        entry.place(x=x + 2, y=y + 2, width=width - 4, height=height - 4)
        entry.focus()
        entry.select_range(0, tk.END)

        def save_and_next(_=None):
            new_val = entry.get().strip()
            try:
                pid = int(item)
                if col_index == 0:
                    bill_items[pid][0] = new_val
                elif col_index == 1:
                    val = float(new_val)
                    new_qty = int(val) if val.is_integer() else round(val, 2)
                    bill_items[pid][2] = max(0.01, new_qty)
                elif col_index == 2:
                    new_price = round(float(new_val), 2)
                    bill_items[pid][1] = max(0.0, new_price)
            except Exception:
                pass

            try:
                entry.destroy()
            except Exception:
                pass

            self.refresh_bill_for_tree(tree, bill_items)

            if col_index == 1:
                self.after(50, lambda: self.start_edit_cell(tree, bill_items, item, 2))
            else:
                self.after(40, self.focus_active_product_entry)

        entry.bind("<Return>", save_and_next)
        entry.bind("<Escape>", lambda e: entry.destroy())
        self.editing_entry = entry

    def on_tree_double_click(self, event, tree, bill_items):
        region = tree.identify("region", event.x, event.y)
        if region != "cell":
            return
        item = tree.identify_row(event.y)
        col = tree.identify_column(event.x)
        if not item:
            return
        col_num = int(col.replace("#", "")) - 1
        if col_num in (0, 1, 2):
            self.start_edit_cell(tree, bill_items, item, col_num)


    # =========================================================
    # VOICE: load / user / capslock (optional)
    # =========================================================
    def build_receipt_html(self, bill, customer_name, total):
        rows_html = ""
        for item in bill["items"].values():
            name_hi, price, qty = item
            line_total = math.ceil(price * qty)
            rows_html += f"""
            <tr>
                <td class="item">{name_hi}</td>
                <td class="qty">{qty}</td>
                <td class="price">{price:.2f}</td>
                <td class="total">{line_total:,}</td>
            </tr>
            """
    
        html = f"""
        <html><head><meta charset="utf-8">
        <style>
          @font-face {{
            font-family: 'Mangal';
            src: url('file:///C:/Windows/Fonts/mangal.ttf');
          }}
        body {{ font-family:"Noto Sans Devanagari","Mangal","Nirmala UI",sans-serif; }}
        .receipt {{ width:576px;padding:4px 8px 4px 6px;}}
        table{{width:100%;border-collapse:collapse;font-size:22px;}}
        td,th{{padding:6px 4px;vertical-align:top;}}
        .item{{width:55%;}}
        .qty{{width:11%;text-align:left;}}
        .price,.total{{width:17%;text-align:left;}}
        hr{{border:none;border-top:1px solid #000;}}
        </style>
            </head>
                <body>
                    <div id="receipt" class="receipt">
                        <h3 style="text-align:center;font-size:24px">***** ESTIMATE *****</h3>
                        <div style="font-size:22px">{ "Welcome " + customer_name if customer_name else "Customer" }</div>
                        <hr/>
                        <table>
                        <thead style="text-align:left">
                            <tr><th>Item</th><th>Qty</th><th>Price</th><th>Total</th></tr>
                        </thead>
                        <tbody>{rows_html}</tbody>
                        </table>
                        <hr/>
                        <div style="font-size:22px;font-weight:bold">
                            Items: {len(bill['items'])}
                            &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;
                            Grand Total: {int(round(total)):,}
                        </div>
                        <div style="font-size:22px">
                            Thank You!
                            &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;
                            {datetime.now().strftime('%d-%m-%Y %I:%M %p')}
                        </div>
                        <div style="text-align:center;margin-top:6px;font-size:22px">- Developed By Nayan Parihar -</div>
                    </div>
                </body>
            </html> """
        return html
    
    
    def start_printer_keepalive(self, devfile="COM30", interval=30):
        """Start keepalive thread once."""
        if getattr(self, "_printer_keepalive_started", False):
            return
        self._printer_keepalive_started = True
    
        def keep_printer_alive():
            while True:
                try:
                    p = Serial(devfile=devfile, baudrate=9600, timeout=1)
                    try:
                        p._raw(b"\x1B\x40")  # ESC @ initialize
                        p.close()
                    except Exception:
                        try:
                            p.close()
                        except Exception:
                            pass
                except Exception:
                    pass
                time.sleep(interval)
    
        threading.Thread(target=keep_printer_alive, daemon=True).start()
    
    
    def print_bill(self, bill, devfile="COM30"):
        def do_print():
            driver = None
            tmp_dir = None
            try:
                # Customer name
                raw_name = bill["cust_entry"].get().strip()
                customer_name = raw_name if raw_name else "Customer"
    
                # Total
                total = sum(math.ceil(p * q) for _, p, q in bill["items"].values())
    
                # HTML
                html = self.build_receipt_html(bill, customer_name, total)
    
                # Temp files
                tmp_dir = tempfile.mkdtemp()
                html_path = os.path.join(tmp_dir, "receipt.html")
                with open(html_path, "w", encoding="utf-8") as f:
                    f.write(html)
    
                num_items = len(bill["items"])
                window_height = max(6000, 400 + num_items * 45)
    
                chrome_opts = Options()
                chrome_opts.add_argument("--headless=new")
                chrome_opts.add_argument(f"--window-size=800,{window_height}")
    
                driver = (
                    webdriver.Chrome(executable_path=CHROMEDRIVER_PATH, options=chrome_opts)
                    if CHROMEDRIVER_PATH
                    else webdriver.Chrome(options=chrome_opts)
                )
    
                driver.get("file:///" + html_path.replace("\\", "/"))
                driver.implicitly_wait(1)
    
                elem = driver.find_element(By.ID, "receipt")
    
                tmp_png = os.path.join(tmp_dir, "bill.png")
                elem.screenshot(tmp_png)
    
                try:
                    driver.quit()
                except Exception:
                    pass
                driver = None
    
                # Print bitmap
                p = Serial(devfile=devfile, baudrate=9600, timeout=1)
                p._raw(b"\x1B\x37\x08\xF0\x02")   # density
                p._raw(b"\x1B\x33\x08")           # line spacing
                p.image(tmp_png)
                p.text("\n\n\n")
                p.cut()
                p.close()
    
                messagebox.showinfo("Printed", "Bill printed successfully.")
    
            except Exception as e:
                if driver:
                    try:
                        driver.quit()
                    except Exception:
                        pass
                messagebox.showerror("Print Error", str(e))
    
            finally:
                # Cleanup temp files
                if tmp_dir:
                    try:
                        for fn in ("bill.png", "receipt.html"):
                            fp = os.path.join(tmp_dir, fn)
                            if os.path.exists(fp):
                                os.remove(fp)
                        os.rmdir(tmp_dir)
                    except Exception:
                        pass
                    
        threading.Thread(target=do_print, daemon=True).start()

    def load_model_click(self):
        if Model is None or KaldiRecognizer is None or sd is None:
            messagebox.showwarning("Voice", "Voice libraries not installed (vosk/sounddevice).")
            return

        if self.model:
            return

        self.load_btn.config(text="Loading...", state="disabled")
        threading.Thread(target=self.load_model_background, daemon=True).start()

    def load_model_background(self):
        try:
            self.model = Model(MODEL_PATH)
            self.rec = KaldiRecognizer(self.model, 16000)
            self.after(0, lambda: self.load_btn.config(text="Model Loaded", state="normal"))
            self.after(0, lambda: self.light1.config(bg="green"))
        except Exception:
            self.after(0, lambda: self.load_btn.config(text="Load Failed", state="normal"))

    def cycle_user(self):
        self.current_user += 1
        if self.current_user > 4:
            self.current_user = 1
        self.user_btn.config(text=f"User {self.current_user}")

    def keyboard_listener(self):
        # CapsLock toggles listening
        while True:
            keyboard.wait("caps lock")
            if self.listening:
                self.stop_listening()
            else:
                self.start_listening()

    def start_listening(self):
        if not sd or not self.rec or not self.q:
            return
        if self.listening:
            return
        self.listening = True
        self.light2.config(bg="green")
        threading.Thread(target=self.listen_voice, daemon=True).start()

    def stop_listening(self):
        self.listening = False
        self.light2.config(bg="red")

    def listen_voice(self):
        def callback(indata, frames, t, status):
            if self.listening and self.q:
                self.q.put(bytes(indata))

        try:
            with sd.RawInputStream(
                samplerate=16000,
                blocksize=000,
                dtype="int16",
                channels=1,
                callback=callback
            ):
                while self.listening:
                    data = self.q.get()
                    if self.rec.AcceptWaveform(data):
                        result = json.loads(self.rec.Result())
                        text = result.get("text", "").strip()
                        if text:
                            self.after(0, lambda t=text: self._apply_voice_text(t))
                    else:
                        partial = json.loads(self.rec.PartialResult())
                        ptxt = partial.get("partial", "").strip()
                        if ptxt:
                            self.after(0, lambda t=ptxt: self._apply_voice_partial(t))
        except Exception:
            pass


    def _apply_voice_partial(self, text):
        if self.active_bill is None:
            self.active_bill = self.left_bill
        self.active_bill["entry"].delete(0, tk.END)
        self.active_bill["entry"].insert(0, text)
        self.active_bill["entry"].focus_set()


    def _apply_voice_final(self, text):
        self._apply_voice_text(text)


    def _apply_voice_text(self, text):
        if self.active_bill is None:
            self.active_bill = self.left_bill

        spoken = (text or "").strip()
        if not spoken:
            return
        # Put what voice heard into entry (so user sees it)
        self.active_bill["entry"].delete(0, tk.END)
        self.active_bill["entry"].insert(0, spoken)
        self.active_bill["entry"].focus_set()

        # Filter products by BOTH name_en and name_hi (contains match)
        matches = self.filter_products_by_text(spoken)

        # Update suggestion list with EN names of matches
        self.suggestion_box.delete(0, tk.END)
        for _, name_en, _, _ in matches:
            self.suggestion_box.insert(tk.END, name_en)

        # Update top product_tree with full matched rows
        self.product_tree.delete(*self.product_tree.get_children())
        for row in matches:
            self.product_tree.insert("", tk.END, values=row)

        # Auto-highlight first suggestion (so Enter can use it)
        if self.suggestion_box.size() > 0:
            self.suggestion_box.selection_clear(0, tk.END)
            self.suggestion_box.selection_set(0)
            self.suggestion_box.activate(0)