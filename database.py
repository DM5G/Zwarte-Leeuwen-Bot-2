import sqlite3

DB_PATH = "database.sqlite"

def get_connection():
    """Returns a connection to the SQLite database."""
    return sqlite3.connect(DB_PATH)

def init_db():
    """Initializes the database schema."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # --- Welcome System ---
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS welcome_settings (
            guild_id INTEGER PRIMARY KEY,
            channel_id INTEGER,
            banner_url TEXT,
            message TEXT
        )
    ''')

    # --- Ticket System ---
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ticket_settings (
            guild_id INTEGER PRIMARY KEY,
            banner_url TEXT,
            title TEXT,
            description TEXT,
            staff_roles TEXT,
            form_postulacion TEXT,
            form_reporte TEXT
        )
    ''')

    # --- Warning System ---
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS warn_settings (
            guild_id INTEGER PRIMARY KEY,
            log_channel_id INTEGER,
            staff_roles TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS warnings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER,
            user_id INTEGER,
            points REAL,
            reason TEXT
        )
    ''')

    # --- Activities System ---
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS activities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER,
            channel_id INTEGER,
            name TEXT,
            description TEXT,
            action_time TEXT,
            days TEXT,
            banner_url TEXT
        )
    ''')
    
    conn.commit()
    conn.close()
    print("Base de datos inicializada correctamente.")

if __name__ == "__main__":
    init_db()
