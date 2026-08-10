from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
import sqlite3
import yfinance as yf
from jose import jwt, JWTError
import hashlib
import os

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SECRET_KEY = "finans_gizli_anahtar_degistirin"
ALGORITHM = "HS256"

def hash_password(password: str) -> str:
    return hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), b'static_salt_finans', 100000).hex()

def verify_password(password: str, hashed: str) -> bool:
    return hash_password(password) == hashed

DB_PATH = "/opt/render/project/src/finans.db" if os.path.exists("/opt/render/project/src") else "finans.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS portfolio (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            symbol TEXT,
            amount REAL,
            buy_price REAL DEFAULT 0.0
        )
    """)
    try:
        cursor.execute("ALTER TABLE portfolio ADD COLUMN buy_price REAL DEFAULT 0.0")
    except sqlite3.OperationalError:
        pass
        
    conn.commit()
    conn.close()

init_db()

class UserAuth(BaseModel):
    username: str
    password: str

class Asset(BaseModel):
    symbol: str
    amount: float
    buy_price: float = 0.0

# Akıllı Sembol ve Fiyat Dönüştürücü
def resolve_symbol_and_price(symbol_input: str):
    clean = symbol_input.strip().upper()
    
    # Altın Türleri (Gram Altın GAUTRY=X baz alınarak katsayı ile hesaplanır)
    if clean in ["GRAM ALTIN", "ALTIN", "GRAM", "GAUTRY=X"]:
        return "GAUTRY=X", 1.0, "GRAM ALTIN"
    elif "ÇEYREK" in clean or "CEYREK" in clean:
        return "GAUTRY=X", 1.63, "ÇEYREK ALTIN"
    elif "YARIM" in clean:
        return "GAUTRY=X", 3.26, "YARIM ALTIN"
    elif "TAM" in clean or "ZİYNET" in clean or "ZIYNET" in clean:
        return "GAUTRY=X", 6.52, "TAM ALTIN"
    elif clean in ["DOLAR", "USD"]:
        return "USDTRY=X", 1.0, "USD/TRY"
    elif clean in ["EURO", "EUR"]:
        return "EURTRY=X", 1.0, "EUR/TRY"
    
    # Borsa İstanbul Hisseleri (Eğer .IS yoksa ve yabancı sembol değilse ekler)
    if not clean.endswith(".IS") and not "=" in clean and len(clean) <= 6:
        return f"{clean}.IS", 1.0, clean
        
    return clean, 1.0, clean

@app.post("/register")
def register(user: UserAuth):
    if not user.username or not user.password:
        raise HTTPException(status_code=400, detail="Kullanıcı adı ve şifre gereklidir.")
        
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    hashed_pwd = hash_password(user.password)
    try:
        cursor.execute("INSERT INTO users (username, password) VALUES (?, ?)", (user.username, hashed_pwd))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(status_code=400, detail="Bu kullanıcı adı zaten alınmış.")
    conn.close()
    return {"message": "Kayıt başarılı!"}

@app.post("/login")
def login(user: UserAuth):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, password FROM users WHERE username = ?", (user.username,))
    db_user = cursor.fetchone()
    conn.close()
    
    if not db_user or not verify_password(user.password, db_user[1]):
        raise HTTPException(status_code=400, detail="Hatalı kullanıcı adı veya şifre.")
    
    token = jwt.encode({"user_id": db_user[0], "username": user.username}, SECRET_KEY, algorithm=ALGORITHM)
    return {"access_token": token, "token_type": "bearer"}

def get_current_user(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload["user_id"]
    except JWTError:
        raise HTTPException(status_code=401, detail="Geçersiz oturum.")

@app.get("/portfolio")
def get_portfolio(token: str):
    user_id = get_current_user(token)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, symbol, amount, buy_price FROM portfolio WHERE user_id = ?", (user_id,))
    items = cursor.fetchall()
    conn.close()
    
    result = []
    for item in items:
        asset_id, raw_symbol, amount, buy_price = item
        
        # Sembolü çöz ve katsayıyı al
        yf_symbol, multiplier, display_name = resolve_symbol_and_price(raw_symbol)
        
        current_price = buy_price
        try:
            ticker = yf.Ticker(yf_symbol)
            live_price = ticker.fast_info.last_price
            if live_price:
                # Katsayı ile çarparak (örn: gram fiyatı * 1.63 = çeyrek altın fiyatı) hesaplar
                current_price = round(live_price * multiplier, 2)
        except:
            pass
            
        total_cost = round(amount * buy_price, 2)
        current_value = round(amount * current_price, 2)
        profit_loss = round(current_value - total_cost, 2)
        profit_loss_percent = round((profit_loss / total_cost * 100), 2) if total_cost > 0 else 0.0

        result.append({
            "id": asset_id,
            "symbol": display_name,
            "amount": amount,
            "buy_price": buy_price,
            "current_price": current_price,
            "total_cost": total_cost,
            "current_value": current_value,
            "profit_loss": profit_loss,
            "profit_loss_percent": profit_loss_percent
        })
    return result

@app.post("/portfolio/add")
def add_asset(asset: Asset, token: str):
    user_id = get_current_user(token)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO portfolio (user_id, symbol, amount, buy_price) VALUES (?, ?, ?, ?)",
                   (user_id, asset.symbol.strip(), asset.amount, asset.buy_price))
    conn.commit()
    conn.close()
    return {"message": "Varlık eklendi!"}

@app.delete("/portfolio/delete/{asset_id}")
def delete_asset(asset_id: int, token: str):
    user_id = get_current_user(token)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM portfolio WHERE id = ? AND user_id = ?", (asset_id, user_id))
    conn.commit()
    conn.close()
    return {"message": "Varlık silindi!"}

@app.get("/")
def read_root():
    return FileResponse("index.html")
