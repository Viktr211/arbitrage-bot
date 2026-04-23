import sqlite3
conn = sqlite3.connect("arbitrage.db")
cursor = conn.cursor()
admin_email = "cb777899@gmail.com"
new_password = "Viktr211@"
cursor.execute("UPDATE users SET password_hash = ? WHERE email = ?", (new_password, admin_email))
if cursor.rowcount == 0:
    cursor.execute('''
        INSERT INTO users (email, password_hash, full_name, registration_status, trade_balance)
        VALUES (?, ?, ?, ?, ?)
    ''', (admin_email, new_password, "Администратор", "approved", 1000))
conn.commit()
conn.close()
print("✅ Готово. Теперь можно входить с паролем Viktr211@")
