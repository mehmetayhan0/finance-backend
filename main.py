import os
from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.responses import FileResponse
from pydantic import BaseModel
import sqlite3
import hashlib
from datetime import datetime, timedelta
from typing import Optional
from jose import jwt, JWTError
import yfinance as yf

# --- UYGULAMA VE GÜVENLİK AYARLARI ---
app = FastAPI(title="Finans Asistanı Mobil API", version="1.1")

SECRET_KEY = "finans_gizli_anahtar_buraya_gelecek_ve_cok_guvenli"
ALGORITHM = "HS256"

# --- VERİTABANI OLUŞTURMA (SQLite) ---
def init_db():
    conn = sqlite3.connect("finans.db")
    cursor = conn.cursor()
    
    # Kullanıcılar Tablosu
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """)
    
    # Kullanıcı Portföyü Tablosu (Dinamik Hisse/Varlık)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS portfolios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        symbol TEXT NOT NULL,
        amount REAL NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )
    """)
    
    conn.commit()
    conn.close()

init_db()

# --- YARDIMCI FONKSİYONLAR ---
def hash_password(password: str) -> str:
    return hashlib.pbkdf2_hmac('sha256', password.encode(), b'finans_salt', 100000).hex()

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=30)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user_id(authorization: Optional[str] = Header(None)) -> int:
    """ Kullanıcının Gönderdiği Token'dan Kimliğini Doğrular """
    if not authorization:
        raise HTTPException(status_code=401, detail="Yetkilendirme başlığı eksik! Giriş yapmalısınız.")
    try:
        token = authorization.replace("Bearer ", "")
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: int = payload.get("user_id")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Geçersiz jeton.")
        return user_id
    except JWTError:
        raise HTTPException(status_code=401, detail="Jeton doğrulanamadı veya süresi doldu.")

def get_live_price(symbol: str) -> float:
    """ Girilen Sembolün Canlı Fiyatını yfinance İle Çeker """
    sym = symbol.upper().strip()
    
    # Özel Tanımlı Sembol Dönüştürmeleri
    if sym in ["ALTIN", "GOLD", "GRAM_ALTIN"]:
        try:
            tickers = yf.Tickers('GC=F USDTRY=X')
            ons = tickers.tickers['GC=F'].fast_info.last_price or 2500.0
            usd = tickers.tickers['USDTRY=X'].fast_info.last_price or 33.0
            return round((ons * usd) / 31.1035, 2)
        except Exception:
            return 3150.00
    elif sym in ["EURO", "EUR"]:
        ticker_str = "EURTRY=X"
    elif not (sym.endswith(".IS") or "=" in sym or "-" in sym):
        # Varsayılan BIST hisseleri için .IS ekle (Örn: THYAO -> THYAO.IS)
        ticker_str = f"{sym}.IS"
    else:
        ticker_str = sym

    try:
        ticker = yf.Ticker(ticker_str)
        price = ticker.fast_info.last_price
        if price is not None:
            return round(price, 2)
        return 0.0
    except Exception:
        return 0.0

# --- VERİ MODELLERİ ---
class UserAuth(BaseModel):
    username: str
    password: str

class AssetAdd(BaseModel):
    symbol: str   # Örn: THYAO, EREGL, ALTIN, EURO, BTC-USD, AAPL
    amount: float # Örn: 100 Lot, 15.5 Gram

# --- API ENDPOINT'LERİ ---

@app.get("/")
def home():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    html_path = os.path.join(base_dir, "index.html")
    return FileResponse(html_path)
# 1. KAYIT
@app.post("/register")
def register(user: UserAuth):
    conn = sqlite3.connect("finans.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE username = ?", (user.username,))
    if cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=400, detail="Bu kullanıcı adı zaten alınmış!")
    
    hashed_pwd = hash_password(user.password)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
                   (user.username, hashed_pwd, now))
    conn.commit()
    conn.close()
    return {"durum": "Başarılı", "mesaj": f"'{user.username}' kullanıcısı oluşturuldu."}

# 2. GİRİŞ
@app.post("/login")
def login(user: UserAuth):
    conn = sqlite3.connect("finans.db")
    cursor = conn.cursor()
    hashed_pwd = hash_password(user.password)
    cursor.execute("SELECT id, username FROM users WHERE username = ? AND password_hash = ?", 
                   (user.username, hashed_pwd))
    db_user = cursor.fetchone()
    conn.close()
    
    if not db_user:
        raise HTTPException(status_code=401, detail="Kullanıcı adı veya şifre hatalı!")
    
    token = create_access_token({"sub": db_user[1], "user_id": db_user[0]})
    return {
        "access_token": token,
        "token_type": "bearer",
        "user_id": db_user[0],
        "username": db_user[1]
    }

# 3. PORTFÖYE VARLIK/HİSSE EKLE VEYA GÜNCELLE
@app.post("/portfolio/add")
def add_asset(asset: AssetAdd, user_id: int = Depends(get_current_user_id)):
    symbol_upper = asset.symbol.upper().strip()
    conn = sqlite3.connect("finans.db")
    cursor = conn.cursor()
    
    # Kullanıcıda zaten bu hisse var mı kontrol et
    cursor.execute("SELECT id, amount FROM portfolios WHERE user_id = ? AND symbol = ?", 
                   (user_id, symbol_upper))
    existing = cursor.fetchone()
    
    if existing:
        # Varsa miktarını güncelle
        new_amount = asset.amount
        cursor.execute("UPDATE portfolios SET amount = ? WHERE id = ?", (new_amount, existing[0]))
        msg = f"{symbol_upper} miktarı {new_amount} olarak güncellendi."
    else:
        # Yoksa yeni kayıt ekle
        cursor.execute("INSERT INTO portfolios (user_id, symbol, amount) VALUES (?, ?, ?)",
                       (user_id, symbol_upper, asset.amount))
        msg = f"{symbol_upper} portföye eklendi."
        
    conn.commit()
    conn.close()
    return {"durum": "Başarılı", "mesaj": msg}

# 4. KULLANICININ KİŞİSEL PORTFÖYÜNÜ BİRLEŞTİRİP HESAPLAMA
@app.get("/portfolio/my")
def get_my_portfolio(user_id: int = Depends(get_current_user_id)):
    conn = sqlite3.connect("finans.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, symbol, amount FROM portfolios WHERE user_id = ?", (user_id,))
    rows = cursor.fetchall()
    conn.close()
    
    items = []
    total_portfolio_tl = 0.0
    
    for row in rows:
        item_id, symbol, amount = row
        price = get_live_price(symbol)
        total_value = round(price * amount, 2)
        total_portfolio_tl += total_value
        
        items.append({
            "id": item_id,
            "symbol": symbol,
            "amount": amount,
            "unit_price_tl": price,
            "total_value_tl": total_value
        })
        
    return {
        "user_id": user_id,
        "portfolio_total_tl": round(total_portfolio_tl, 2),
        "items": items
    }

# 5. PORTFÖYDEN VARLIK SİLME
@app.delete("/portfolio/delete/{asset_id}")
def delete_asset(asset_id: int, user_id: int = Depends(get_current_user_id)):
    conn = sqlite3.connect("finans.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM portfolios WHERE id = ? AND user_id = ?", (asset_id, user_id))
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    
    if affected == 0:
        raise HTTPException(status_code=404, detail="Silinecek varlık bulunamadı.")
    return {"durum": "Başarılı", "mesaj": "Varlık portföyden silindi."}

# 6. YÖNETİCİ/PANEL İSTATİSTİK
@app.get("/admin/stats")
def get_stats():
    conn = sqlite3.connect("finans.db")
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM portfolios")
    total_assets = cursor.fetchone()[0]
    conn.close()
    return {
        "toplam_kullanici_sayisi": total_users,
        "toplam_kayitli_varlik_sayisi": total_assets,
        "sunucu_durumu": "Aktif"
    }
