# Double_Entry_Billing_System-Eng:-
An advanced version of the single-entry system, allowing users to manage two bills simultaneously with dual panels. It includes all previous features, a smoother UI, and improved UX for faster product entry, real-time updates, and accurate English bill printing. Also added a field to enter Customer Name to print on bill.

<img width="1918" height="1018" alt="DB_ENG" src="https://github.com/user-attachments/assets/873263f7-ef1a-457b-87b2-09513ff33b70" />

## ⚙️ How to Use:-

1. **Create a Database** in MySQL.

2. **Run the following SQL commands** to set up the required tables:

   ```sql
   CREATE DATABASE cash_trader;
    CREATE TABLE products (
        id INT AUTO_INCREMENT PRIMARY KEY,
        name_en VARCHAR(100) UNIQUE NOT NULL,
        name_hi VARCHAR(100) NOT NULL,
        price DECIMAL(10,2) NOT NULL
    );
    INSERT INTO products (name_en, name_hi, price) VALUES
    ('Air Freshener', 'एयर फ्रेशनर', 60.00),  // Sample Values
    ('Toothpaste', 'टूथपेस्ट', 40.50),
    ('Soap', 'साबुन', 25.00),
    ('Shampoo', 'शैम्पू', 99.99);

   ```
3. **Download** the project as a `.zip` file → **Extract** it → **Open** the folder in your preferred code editor.

4. **Update Database Credentials**:

    Open the main Python file.
    Replace the database username and password with your own.

5. **Connect Your Thermal Printer** via **USB** or **Bluetooth (BT)**.

6. **Find Your Printer’s Port Number**:

    Go to **Settings → Devices → Printers & Scanners → More Devices and Printer Settings**
    Right-click your printer → **Properties → Hardware → Change Settings → Hardware → Advanced**
    Note the **COM Port Number** (e.g., COM3, COM4).

7. **Update the Code**:
    Scroll to the `do_print()` function (near the end of the code).
    Replace the COM port number with your own.

8. **Run the Code** by pressing **F5** (or using the Run option in your editor).

### 🧾 Notes:-

* This program supports **any thermal printer** that connects via **USB** or **Bluetooth**.
* The print format is optimized for **80mm thermal paper**.
* Entering the Names of Products Must not have space in start or end.
