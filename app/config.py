class Config:
    SECRET_KEY = '91f594b33a0c6e72223bd60f04fe0c3525d5759b19dfd44c'
    SQLITE_FILE="certdns.sqlite3"
    SQLALCHEMY_DATABASE_URI=f"sqlite:///{ SQLITE_FILE}"


