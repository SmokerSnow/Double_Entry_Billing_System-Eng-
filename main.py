import tkinter as tk
import mysql.connector
from tkinter import ttk, messagebox, font
import threading, math, tempfile, os, time
from datetime import datetime

from escpos.printer import Serial
from db_helper import get_connection

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By


# ---------------- Chrome Driver Path (for HTML bill) ----------------
CHROMEDRIVER_PATH = None  # set full path if needed


# ---------------- Main App Window ----------------
class TypingTab(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent)

        # Uses global DB cursor created in main()
        global conn, cursor

        # Local "root" reference for clipboard + after()
        global root, global_font, Button_font
        root = self

        global_font = font.Font(family="Arial", size=13)
        Button_font = font.Font(family="Arial", size=13, weight="bold")

        style = ttk.Style()
        style.configure("Treeview", font=("Arial", 12))

        # ---------------- Product Management ----------------
        product_names = []  # cached name_en list for suggestions

        def fetch_products():
            cursor.execute("SELECT id, name_en, name_hi, price FROM products ORDER BY name_en ASC")
            rows = cursor.fetchall()

            product_tree.delete(*product_tree.get_children())
            for row in rows:
                product_tree.insert("", tk.END, values=row)

            product_names.clear()
            product_names.extend([r[1] for r in rows])

        def init_suggestions():
            suggestion_box.delete(0, tk.END)
            for name in product_names:
                suggestion_box.insert(tk.END, name)

        def add_product():
            name_en, name_hi = name_en_entry.get().strip(), name_hi_entry.get().strip()
            try:
                price = float(price_entry.get())
            except:
                return messagebox.showerror("Error", "Price must be a number")

            if not (name_en and name_hi):
                return messagebox.showerror("Error", "Fill all fields")

            try:
                cursor.execute(
                    "INSERT INTO products (name_en, name_hi, price) VALUES (%s,%s,%s)",
                    (name_en, name_hi, price)
                )
                conn.commit()
                fetch_products()
                init_suggestions()
                clear_inputs()
            except mysql.connector.IntegrityError:
                messagebox.showerror("Error", "Product must be unique")

        def update_product():
            selected = product_tree.selection()
            if not selected:
                return messagebox.showerror("Error", "Select a product to update")

            item = product_tree.item(selected[0])
            product_id = item["values"][0]

            name_en, name_hi = name_en_entry.get().strip(), name_hi_entry.get().strip()
            try:
                price = float(price_entry.get())
            except:
                return messagebox.showerror("Error", "Price must be a number")

            if not (name_en and name_hi):
                return messagebox.showerror("Error", "Fill all fields")

            try:
                cursor.execute(
                    "UPDATE products SET name_en=%s, name_hi=%s, price=%s WHERE id=%s",
                    (name_en, name_hi, price, product_id)
                )
                conn.commit()
                fetch_products()
                init_suggestions()
                clear_inputs()
            except mysql.connector.IntegrityError:
                messagebox.showerror("Error", "Product must be unique")

        def delete_product():
            selected = product_tree.selection()
            if not selected:
                return messagebox.showerror("Error", "Select a product to delete")

            item = product_tree.item(selected[0])
            product_id = item["values"][0]

            if messagebox.askyesno("Confirm Delete", "Are you sure?"):
                cursor.execute("DELETE FROM products WHERE id=%s", (product_id,))
                conn.commit()
                fetch_products()
                init_suggestions()
                clear_inputs()

        def clear_inputs():
            for e in (name_en_entry, name_hi_entry, price_entry):
                e.delete(0, tk.END)

        def select_product(event):
            sel = product_tree.selection()
            if not sel:
                return
            item = product_tree.item(sel[0])
            name_en_entry.delete(0, tk.END)
            name_hi_entry.delete(0, tk.END)
            price_entry.delete(0, tk.END)
            name_en_entry.insert(0, item["values"][1])
            name_hi_entry.insert(0, item["values"][2])
            price_entry.insert(0, item["values"][3])

        # ---------------- Product Management UI ----------------
        pm_frame = tk.Frame(self, bd=2, relief="groove")
        pm_frame.pack(side=tk.LEFT, padx=10, pady=10, fill=tk.Y)

        tk.Label(pm_frame, text="Product Management", font=("Arial", 18, "bold")) \
            .grid(row=0, column=0, columnspan=2, pady=5)

        tk.Label(pm_frame, text="Name (English)", font=global_font).grid(row=1, column=0, pady=5)
        tk.Label(pm_frame, text="Name (Hindi)", font=global_font).grid(row=2, column=0, pady=5)
        tk.Label(pm_frame, text="Price", font=global_font).grid(row=3, column=0, pady=5)

        name_en_entry = tk.Entry(pm_frame, font=global_font)
        name_hi_entry = tk.Entry(pm_frame, font=global_font)
        price_entry = tk.Entry(pm_frame, font=global_font)

        name_en_entry.grid(row=1, column=1, padx=(0, 10))
        name_hi_entry.grid(row=2, column=1, padx=(0, 10))
        price_entry.grid(row=3, column=1, padx=(0, 10))

        tk.Button(pm_frame, text="Add", font=Button_font, width=12, command=add_product) \
            .grid(row=4, column=0, pady=5, padx=(35, 5))
        tk.Button(pm_frame, text="Update", font=Button_font, width=12, command=update_product) \
            .grid(row=4, column=1, pady=5)
        tk.Button(pm_frame, text="Delete", font=Button_font, width=12, command=delete_product) \
            .grid(row=5, column=0, pady=5, padx=(35, 5))
        tk.Button(pm_frame, text="Clear", font=Button_font, width=12, command=clear_inputs) \
            .grid(row=5, column=1, pady=5)

        suggestion_box = tk.Listbox(pm_frame, font=global_font, height=25, width=35)
        suggestion_box.grid(row=6, column=0, columnspan=2, pady=5)

        # Product tree (top)
        heading_font = font.Font(family="Arial", size=12, weight="bold")
        style.configure("Treeview.Heading", font=heading_font)

        product_tree = ttk.Treeview(self, columns=("ID", "Name_EN", "Name_HI", "Price"), show="headings", height=6)
        for col, text in zip(("ID", "Name_EN", "Name_HI", "Price"),
                             ("ID", "Name (English)", "Name (Hindi)", "Price")):
            product_tree.heading(col, text=text)
        product_tree.pack(side=tk.TOP, fill=tk.X, padx=30, pady=8)
        product_tree.bind("<ButtonRelease-1>", select_product)

        # ---------------- Helpers ----------------
        def format_qty_display(qty):
            try:
                if isinstance(qty, int):
                    return str(qty)
                q = float(qty)
                if q.is_integer():
                    return str(int(q))
                return f"{round(q, 2):.2f}".rstrip("0").rstrip(".")
            except:
                return str(qty)

        def format_price(p):
            try:
                return f"{float(p):.2f}"
            except:
                return str(p)

        # ---------------- Inline Editing ----------------
        editing_entry = None

        def start_edit_cell(tree, bill_items, item, col_index):
            nonlocal editing_entry
            try:
                if editing_entry:
                    editing_entry.destroy()
            except:
                pass
            editing_entry = None

            col_id = f"#{col_index + 1}"
            try:
                x, y, width, height = tree.bbox(item, col_id)
            except Exception:
                return
            if width <= 0:
                return

            cur_val = tree.set(item, tree["columns"][col_index])
            entry = tk.Entry(tree, font=global_font)
            entry.insert(0, cur_val)
            entry.place(x=x + 2, y=y + 2, width=width - 4, height=height - 4)
            entry.focus()
            entry.select_range(0, tk.END)

            def save_and_next(event=None):
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
                except:
                    pass

                try:
                    entry.destroy()
                except:
                    pass

                refresh_bill_for_tree(tree, bill_items)
                if col_index == 1:
                    root.after(50, lambda: start_edit_cell(tree, bill_items, item, 2))
                else:
                    root.after(40, focus_active_product_entry)

            entry.bind("<Return>", save_and_next)
            entry.bind("<Escape>", lambda e: entry.destroy())
            editing_entry = entry

        def on_tree_double_click_factory(tree, bill_items):
            def handler(event):
                if tree.identify("region", event.x, event.y) != "cell":
                    return
                item = tree.identify_row(event.y)
                col = tree.identify_column(event.x)
                if not item:
                    return
                col_num = int(col.replace("#", "")) - 1
                if col_num in (0, 1, 2):
                    start_edit_cell(tree, bill_items, item, col_num)
            return handler

        # ---------------- Bill Panel Creator ----------------
        def create_bill_panel(parent):
            frame = tk.Frame(parent, relief=tk.GROOVE, borderwidth=2)

            top = tk.Frame(frame)
            tk.Label(top, text="Customer:", font=Button_font).pack(side=tk.LEFT, padx=(5, 2))
            cust_entry = tk.Entry(top, font=global_font)
            cust_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
            top.pack(fill=tk.X, pady=6, padx=6)

            product_row = tk.Frame(frame)
            tk.Label(product_row, text="Product Name", font=Button_font).pack(side=tk.LEFT)
            entry = tk.Entry(product_row, font=global_font)
            entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(10, 0))
            product_row.pack(fill=tk.X, padx=6)

            tree = ttk.Treeview(frame, columns=("Name", "Qty", "Price", "Total"), show="headings", height=18)
            for col, width in zip(("Name", "Qty", "Price", "Total"), (260, 60, 90, 100)):
                tree.heading(col, text=col)
                tree.column(col, width=width, anchor="center")
            tree.pack(fill=tk.BOTH, padx=6, pady=6, expand=True)

            bottom = tk.Frame(frame)
            items_label = tk.Label(bottom, text="Items: 0", font=("Arial", 14, "bold"))
            items_label.pack(side=tk.LEFT)
            total_label = tk.Label(bottom, text="Grand Total: 0", font=("Arial", 16, "bold"))
            total_label.pack(side=tk.LEFT, padx=(180, 0))
            bottom.pack(fill=tk.X, pady=(0, 6), padx=(90, 0))

            btn_row = tk.Frame(frame)
            clear_btn = tk.Button(btn_row, text="Clear Bill", font=Button_font, width=15, height=2)
            clear_btn.pack(side=tk.LEFT, padx=15)
            copy_btn = tk.Button(btn_row, text="Copy Bill", font=global_font, width=8, height=2)
            copy_btn.pack(side=tk.LEFT, padx=2)
            paste_btn = tk.Button(btn_row, text="Paste Bill", font=global_font, width=8, height=2)
            paste_btn.pack(side=tk.LEFT, padx=2)
            print_btn = tk.Button(btn_row, text="Print Bill", font=Button_font, width=15, height=2)
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

        # ---------------- Both Bills ----------------
        billing_container = tk.Frame(self)
        billing_container.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=10, pady=10)

        left_bill = create_bill_panel(billing_container)
        right_bill = create_bill_panel(billing_container)

        left_bill["frame"].pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5)
        right_bill["frame"].pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=5)

        # ---------------- Refresh helper ----------------
        def refresh_bill_for_tree(tree, bill_items):
            tree.delete(*tree.get_children())
            total = 0.0

            for pid, item in bill_items.items():
                name_hi, price, qty = item
                line_total = math.ceil(float(price) * float(qty))
                total += line_total
                tree.insert(
                    "", tk.END, iid=str(pid),
                    values=(name_hi, format_qty_display(qty), format_price(price), f"{line_total:,}")
                )

            for b in (left_bill, right_bill):
                if b["tree"] is tree:
                    b["items_label"].config(text=f"Items: {len(bill_items)}")
                    b["total_label"].config(text=f"Grand Total: {int(round(total)):,}")
                    if bill_items:
                        try:
                            tree.see(str(list(bill_items.keys())[-1]))
                        except:
                            pass
                    break

        # ---------------- Active bill + suggestion logic ----------------
        active_bill = left_bill

        def set_active_bill_by_widget(widget):
            nonlocal active_bill
            if widget in (left_bill["entry"], left_bill["cust_entry"], left_bill["tree"]):
                active_bill = left_bill
            elif widget in (right_bill["entry"], right_bill["cust_entry"], right_bill["tree"]):
                active_bill = right_bill

        def focus_active_product_entry():
            try:
                if active_bill:
                    active_bill["entry"].focus_set()
            except:
                pass

        def update_suggestions_for_widget(event):
            if event.keysym in ("Up", "Down", "Return"):
                return

            widget = event.widget
            set_active_bill_by_widget(widget)

            typed = widget.get().strip().lower()
            suggestion_box.delete(0, tk.END)

            if typed == "":
                for name in product_names:
                    suggestion_box.insert(tk.END, name)
            else:
                for name in product_names:
                    if typed in name.lower():
                        suggestion_box.insert(tk.END, name)

            cursor.execute("SELECT id, name_en, name_hi, price FROM products ORDER BY name_en ASC")
            all_rows = cursor.fetchall()
            product_tree.delete(*product_tree.get_children())

            filtered = all_rows if typed == "" else [row for row in all_rows if typed in row[1].lower()]
            for row in filtered:
                product_tree.insert("", tk.END, values=row)

        def on_entry_key_nav(event):
            widget = event.widget
            set_active_bill_by_widget(widget)

            size = suggestion_box.size()
            if event.keysym in ("Down", "Up"):
                if size == 0:
                    return
                cur = suggestion_box.curselection()
                idx = cur[0] if cur else -1

                if event.keysym == "Down":
                    new_idx = 0 if idx == -1 else (idx + 1) % size
                else:
                    new_idx = size - 1 if idx == -1 else (idx - 1) % size

                suggestion_box.selection_clear(0, tk.END)
                suggestion_box.selection_set(new_idx)
                suggestion_box.activate(new_idx)
                suggestion_box.see(new_idx)
                suggestion_box.focus_set()

            elif event.keysym == "Return":
                cur = suggestion_box.curselection()
                if cur:
                    val = suggestion_box.get(cur)
                    widget.delete(0, tk.END)
                    widget.insert(0, val)
                if active_bill:
                    add_to_bill(None, active_bill)

        def suggestion_box_key(event):
            nonlocal active_bill
            size = suggestion_box.size()
            if size == 0:
                return

            cur = suggestion_box.curselection()
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

                selected = suggestion_box.get(idx)
                if active_bill is None:
                    active_bill = left_bill

                active_bill["entry"].delete(0, tk.END)
                active_bill["entry"].insert(0, selected)
                add_to_bill(None, active_bill)
                active_bill["entry"].focus_set()
                return "break"
            else:
                return

            suggestion_box.selection_clear(0, tk.END)
            suggestion_box.selection_set(new_idx)
            suggestion_box.activate(new_idx)
            suggestion_box.see(new_idx)
            return "break"

        def suggestion_click_select(event):
            cur = suggestion_box.curselection()
            if not cur:
                return
            selected = suggestion_box.get(cur)
            focused = root.focus_get()
            if isinstance(focused, tk.Entry):
                focused.delete(0, tk.END)
                focused.insert(0, selected)
                focused.focus()
            else:
                if active_bill is None:
                    active_bill = left_bill
                active_bill["entry"].delete(0, tk.END)
                active_bill["entry"].insert(0, selected)
                active_bill["entry"].focus_set()

        def suggestion_double_click(event):
            cur = suggestion_box.curselection()
            if not cur:
                return
            selected = suggestion_box.get(cur)
            if active_bill is None:
                active_bill = left_bill
            active_bill["entry"].delete(0, tk.END)
            active_bill["entry"].insert(0, selected)
            add_to_bill(None, active_bill)

        suggestion_box.bind("<<ListboxSelect>>", suggestion_click_select)
        suggestion_box.bind("<Double-Button-1>", suggestion_double_click)
        suggestion_box.bind("<Key>", suggestion_box_key)
        suggestion_box.bind("<ButtonRelease-1>", suggestion_click_select)

        def copy_bill_to_clipboard(bill):
            try:
                lines = []
                for pid, (name_hi, price, qty) in bill["items"].items():
                    lines.append(f"{int(pid)}|{float(price)}|{qty}")
                text = "\n".join(lines)
                root.clipboard_clear()
                root.clipboard_append(text)
            except Exception as e:
                messagebox.showerror("Copy Error", str(e))

        def paste_bill_to_pos(bill):
            try:
                data = root.clipboard_get().strip()
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
                    cursor.execute("SELECT name_hi FROM products WHERE id=%s", (pid,))
                    row = cursor.fetchone()
                    if not row:
                        continue
                    name_hi = row[0]
                except Exception:
                    continue

                if pid in bill["items"]:
                    existing_qty = bill["items"][pid][2]
                    new_qty = (int(existing_qty) + int(qty)) if isinstance(existing_qty, int) and isinstance(qty, int) \
                        else round(float(existing_qty) + float(qty), 2)
                    bill["items"][pid][2] = new_qty
                    bill["items"][pid][1] = float(price)
                else:
                    bill["items"][pid] = [name_hi, float(price), int(qty) if isinstance(qty, int) else round(float(qty), 2)]

                pasted_any = True

            if pasted_any:
                refresh_bill_for_tree(bill["tree"], bill["items"])
            else:
                messagebox.showwarning("Paste Error", "No valid bill lines found in clipboard.")

        def add_to_bill(event=None, bill=None, qty_override=None, price_override=None):
            if bill is None:
                return

            name_en = bill["entry"].get().strip()
            if not name_en:
                return

            cursor.execute(
                "SELECT id, name_hi, price FROM products WHERE LOWER(name_en)=LOWER(%s)",
                (name_en.lower(),)
            )
            product = cursor.fetchone()
            if not product:
                messagebox.showerror("Error", "Product not found")
                bill["entry"].delete(0, tk.END)
                bill["entry"].focus_set()
                return

            product_id, name_hi, price = product
            price = float(price)

            if qty_override is not None and price_override is not None:
                bill["items"][product_id] = [name_hi, float(price_override), int(qty_override)]
            else:
                if product_id in bill["items"]:
                    bill["items"][product_id][2] += 1
                else:
                    bill["items"][product_id] = [name_hi, price, 1]

            refresh_bill_for_tree(bill["tree"], bill["items"])
            bill["entry"].delete(0, tk.END)

            root.after(60, lambda b=bill, pid=product_id: start_edit_cell(b["tree"], b["items"], str(pid), 1))

        def clear_bill(bill):
            bill["items"].clear()
            refresh_bill_for_tree(bill["tree"], bill["items"])
            bill["entry"].focus_set()

        def delete_selected_bill_item(event=None, bill=None):
            if bill is None:
                return
            for iid in bill["tree"].selection():
                pid = int(iid)
                if pid in bill["items"]:
                    del bill["items"][pid]
            refresh_bill_for_tree(bill["tree"], bill["items"])

        # ---------------- Print Bill ----------------
        def build_receipt_html(bill, customer_name, total):
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
                            <div style="font-size:22px;font-weight:bold">Items: {len(bill['items'])}
                            &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;
                            Grand Total: {int(round(total)):,}</div>
                            <div style="font-size:22px">Thank You!
                            &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;
                            {datetime.now().strftime('%d-%m-%Y %I:%M %p')}</div>
                            <div style="text-align:center;margin-top:6px;font-size:22px">- Developed By Nayan Parihar -</div>
                        </div>
                    </body>
                </html> """
            return html

        def keep_printer_alive(devfile="COM30", interval=30):
            while True:
                try:
                    p = Serial(devfile=devfile, baudrate=9600, timeout=1)
                    try:
                        p._raw(b"\x1B\x40")
                        p.close()
                    except:
                        try:
                            p.close()
                        except:
                            pass
                except:
                    pass
                time.sleep(interval)

        threading.Thread(target=keep_printer_alive, args=("COM30", 30), daemon=True).start()

        def print_bill(bill):
            def do_print():
                driver = None
                tmp_dir = None
                try:
                    raw_name = bill["cust_entry"].get().strip()
                    customer_name = raw_name if raw_name else "Customer"

                    total = sum(math.ceil(p * q) for _, p, q in bill["items"].values())
                    html = build_receipt_html(bill, customer_name, total)

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
                    except:
                        pass
                    driver = None

                    p = Serial(devfile="COM30", baudrate=9600, timeout=1)
                    p._raw(b"\x1B\x37\x08\xF0\x02")
                    p._raw(b"\x1B\x33\x08")
                    p.image(tmp_png)
                    p.text("\n\n\n")
                    p.cut()
                    p.close()

                    messagebox.showinfo("Printed", "Bill printed successfully.")

                except Exception as e:
                    if driver:
                        try:
                            driver.quit()
                        except:
                            pass
                    messagebox.showerror("Print Error", str(e))
                finally:
                    if tmp_dir:
                        try:
                            for fn in ("bill.png", "receipt.html"):
                                fp = os.path.join(tmp_dir, fn)
                                if os.path.exists(fp):
                                    os.remove(fp)
                            os.rmdir(tmp_dir)
                        except:
                            pass

            threading.Thread(target=do_print, daemon=True).start()

        # ---------------- Bindings & startup ----------------
        for b in (left_bill, right_bill):
            b["entry"].bind("<FocusIn>", lambda e: set_active_bill_by_widget(e.widget))
            b["entry"].bind("<KeyRelease>", update_suggestions_for_widget)
            b["entry"].bind("<Key>", on_entry_key_nav)
            b["entry"].bind("<Return>", lambda e, bill=b: add_to_bill(e, bill))

            b["clear_btn"].config(command=lambda bill=b: clear_bill(bill))
            b["copy_btn"].config(command=lambda bill=b: copy_bill_to_clipboard(bill))
            b["paste_btn"].config(command=lambda bill=b: paste_bill_to_pos(bill))
            b["print_btn"].config(command=lambda bill=b: print_bill(bill))

            b["tree"].bind("<Double-1>", on_tree_double_click_factory(b["tree"], b["items"]))
            b["tree"].bind("<Delete>", lambda e, bill=b: delete_selected_bill_item(e, bill))

        def product_tree_fill(event):
            sel = product_tree.selection()
            if not sel:
                return
            item = product_tree.item(sel[0])
            name_en_entry.delete(0, tk.END)
            name_hi_entry.delete(0, tk.END)
            price_entry.delete(0, tk.END)
            name_en_entry.insert(0, item["values"][1])
            name_hi_entry.insert(0, item["values"][2])
            price_entry.insert(0, item["values"][3])

        product_tree.bind("<Double-1>", product_tree_fill)

        fetch_products()
        init_suggestions()
        left_bill["entry"].focus_set()


# ---------------- Main Entry ----------------
def main():
    global conn, cursor
    conn = get_connection()
    cursor = conn.cursor()

    root = tk.Tk()
    root.state("zoomed")
    root.title("Wholesale Shop POS - CASH TRADER")
    root.iconbitmap("New_Logo.ico")

    notebook = ttk.Notebook(root)

    # Typing Tab
    typing_tab = TypingTab(notebook)
    notebook.add(typing_tab, text="Typing POS")

    # Placeholders (lazy load)
    voice_placeholder = tk.Frame(notebook)
    notebook.add(voice_placeholder, text="Voice POS")

    analyze_placeholder = tk.Frame(notebook)
    notebook.add(analyze_placeholder, text="Analyze")

    inventory_placeholder = tk.Frame(notebook)
    notebook.add(inventory_placeholder, text="Inventory")

    def load_tab(event):
        selected = notebook.tab(notebook.select(), "text")

        if selected == "Voice POS" and not hasattr(voice_placeholder, "loaded"):
            from voice import VoiceTab
            tab = VoiceTab(voice_placeholder)
            tab.pack(fill="both", expand=True)
            voice_placeholder.loaded = True

        elif selected == "Analyze" and not hasattr(analyze_placeholder, "loaded"):
            from analyze import AnalyzeTab
            tab = AnalyzeTab(analyze_placeholder)
            tab.pack(fill="both", expand=True)
            analyze_placeholder.loaded = True

        elif selected == "Inventory" and not hasattr(inventory_placeholder, "loaded"):
            from inventory import InventoryTab
            tab = InventoryTab(inventory_placeholder)
            tab.pack(fill="both", expand=True)
            inventory_placeholder.loaded = True

    notebook.bind("<<NotebookTabChanged>>", load_tab)
    notebook.pack(fill="both", expand=True)

    # Optional: preload voice module import only
    def preload_voice():
        from voice import VoiceTab

    threading.Thread(target=preload_voice, daemon=True).start()

    root.mainloop()


if __name__ == "__main__":
    main()