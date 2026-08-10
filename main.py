from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
import psycopg2
from psycopg2.extras import RealDictCursor
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

# Render Environment Variable üzerinden veritabanı adresi çekilir
DATABASE_URL = os.environ.get("DATABASE_URL")

def get_db_connection():
    if DATABASE_URL:
        return psycopg2.connect(DATABASE_URL)
    else:
        raise Exception("DATABASE_URL tanımlanmamış!")

def hash_password(password: str) -> str:
    return hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), b'static_salt_finans', 100000).hex()

def verify_password(password: str, hashed: str) -> bool:
    return hash_password(password) == hashed

def init_db():
    if not DATABASE_URL:
        return
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username VARCHAR(255) UNIQUE NOT NULL,
            password VARCHAR(255) NOT NULL
        );
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS portfolio (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id),
            symbol VARCHAR(100) NOT NULL,
            amount DOUBLE PRECISION NOT NULL,
            buy_price DOUBLE PRECISION DEFAULT 0.0
        );
    """)
    conn.commit()
    cursor.close()
    conn.close()

try:
    init_db()
except Exception as e:
    print("DB Bağlantı Hatası:", e)

class UserAuth(BaseModel):
    username: str
    password: str

class Asset(BaseModel):
    symbol: str
    amount: float
    buy_price: float = 0.0

def get_live_gram_gold_price():
    try:
        price = yf.Ticker("GAUTRY=X").fast_info.last_price
        if price and price > 0:
            return float(price)
    except:
        pass
    try:
        ons = yf.Ticker("GC=F").fast_info.last_price
        usd = yf.Ticker("USDTRY=X").fast_info.last_price
        if ons and usd:
            return float((ons * usd) / 31.1034768)
    except:
        pass
    return None

def resolve_asset_details(symbol_input: str):
    clean = symbol_input.strip().lower()
    clean_ascii = clean.replace("ı", "i").replace("ğ", "g").replace("ü", "u").replace("ş", "s").replace("ö", "o").replace("ç", "c")
    
    if clean_ascii in ["gram altın", "gram altin", "altin", "altın", "gram", "gautry=x"]:
        return "GOLD", 1.0, "GRAM ALTIN"
    elif "ceyrek" in clean_ascii or "çeyrek" in clean:
        return "GOLD", 1.63, "ÇEYREK ALTIN"
    elif "yarim" in clean_ascii or "yarım" in clean:
        return "GOLD", 3.26, "YARIM ALTIN"
    elif "tam" in clean_ascii or "ziynet" in clean_ascii:
        return "GOLD", 6.52, "TAM ALTIN"
    elif clean_ascii in ["dolar", "usd"]:
        return "USDTRY=X", 1.0, "USD/TRY"
    elif clean_ascii in ["euro", "eur"]:
        return "EURTRY=X", 1.0, "EUR/TRY"
    
    raw_upper = symbol_input.strip().upper()
    if not raw_upper.endswith(".IS") and not "=" in raw_upper and len(raw_upper) <= 6:
        return f"{raw_upper}.IS", 1.0, raw_upper
        
    return raw_upper, 1.0, raw_upper

@app.post("/register")
def register(user: UserAuth):
    if not user.username or not user.password:
        raise HTTPException(status_code=400, detail="Kullanıcı adı ve şifre gereklidir.")
        
    conn = get_db_connection()
    cursor = conn.cursor()
    hashed_pwd = hash_password(user.password)
    try:
        cursor.execute("INSERT INTO users (username, password) VALUES (%s, %s)", (user.username, hashed_pwd))
        conn.commit()
    except psycopg2.IntegrityError:
        conn.close()
        raise HTTPException(status_code=400, detail="Bu kullanıcı adı zaten alınmış.")
    cursor.close()
    conn.close()
    return {"message": "Kayıt başarılı!"}

@app.post("/login")
def login(user: UserAuth):
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("SELECT id, password FROM users WHERE username = %s", (user.username,))
    db_user = cursor.fetchone()
    cursor.close()
    conn.close()
    
    if not db_user or not verify_password(user.password, db_user['password']):
        raise HTTPException(status_code=400, detail="Hatalı kullanıcı adı veya şifre.")
    
    token = jwt.encode({"user_id": db_user['id'], "username": user.username}, SECRET_KEY, algorithm=ALGORITHM)
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
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("SELECT id, symbol, amount, buy_price FROM portfolio WHERE user_id = %s", (user_id,))
    items = cursor.fetchall()
    cursor.close()
    conn.close()
    
    result = []
    gram_gold_cache = None
    
    for item in items:
        asset_id = item['id']
        raw_symbol = item['symbol']
        amount = item['amount']
        buy_price = item['buy_price']
        
        yf_symbol, multiplier, display_name = resolve_asset_details(raw_symbol)
        current_price = buy_price
        
        if yf_symbol == "GOLD":
            if gram_gold_cache is None:
                gram_gold_cache = get_live_gram_gold_price()
            if gram_gold_cache:
                current_price = round(gram_gold_cache * multiplier, 2)
        else:
            try:
                ticker = yf.Ticker(yf_symbol)
                live_price = ticker.fast_info.last_price
                if live_price:
                    current_price = round(float(live_price) * multiplier, 2)
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
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO portfolio (user_id, symbol, amount, buy_price) VALUES (%s, %s, %s, %s)",
                   (user_id, asset.symbol.strip(), asset.amount, asset.buy_price))
    conn.commit()
    cursor.close()
    conn.close()
    return {"message": "Varlık eklendi!"}

@app.delete("/portfolio/delete/{asset_id}")
def delete_asset(asset_id: int, token: str):
    user_id = get_current_user(token)
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM portfolio WHERE id = %s AND user_id = %s", (asset_id, user_id))
    conn.commit()
    cursor.close()
    conn.close()
    return {"message": "Varlık silindi!"}

@app.get("/")
def read_root():
    return FileResponse("index.html")
