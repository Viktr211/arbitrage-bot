import sqlite3

DB_PATH = "arbitrage.db"

def reset_admin_password():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Смотрим всех пользователей
    cursor.execute("SELECT id, email, password_hash FROM users")
    users = cursor.fetchall()
    print("=== ПОЛЬЗОВАТЕЛИ В БАЗЕ ===")
    for user in users:
        print(f"ID: {user[0]}, Email: {user[1]}, Hash: {user[2]}")
    
    # Сбрасываем пароль для администратора
    admin_email = "cb777899@gmail.com"
    new_password = "Viktr211@"  # ваш пароль
    
    cursor.execute("UPDATE users SET password_hash = ? WHERE email = ?", (new_password, admin_email))
    conn.commit()
    
    # Проверяем
    cursor.execute("SELECT id, email, password_hash FROM users WHERE email = ?", (admin_email,))
    user = cursor.fetchone()
    if user:
        print(f"\n✅ Пароль для {user[1]} сброшен на: {new_password}")
    else:
        print(f"\n❌ Пользователь {admin_email} не найден!")
    
    conn.close()

if __name__ == "__main__":
    reset_admin_password()
