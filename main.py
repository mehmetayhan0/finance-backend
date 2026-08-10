from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse
import os

app = FastAPI()

# Sunucudaki projenin tam ana klasör yolu (Render / Linux Uyumlu)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Ana Sayfa (index.html)
@app.get("/", response_class=HTMLResponse)
def read_root():
    index_path = os.path.join(BASE_DIR, "index.html")
    with open(index_path, "r", encoding="utf-8") as f:
        return f.read()

# Manifest Servisi (PWABuilder İçin)
@app.get("/manifest.json")
def get_manifest():
    manifest_path = os.path.join(BASE_DIR, "manifest.json")
    return FileResponse(manifest_path, media_type="application/json")

# Service Worker Servisi
@app.get("/sw.js")
def get_sw():
    sw_path = os.path.join(BASE_DIR, "sw.js")
    return FileResponse(sw_path, media_type="application/javascript")

# APK İndirme Rotası
@app.get("/download-apk")
def download_apk():
    # GitHub ve sunucudaki olası tüm büyük/küçük harf ve Türkçe karakter çeşitlemeleri
    possible_names = [
        "FinansAsistani.apk",
        "Finansasistani.apk",
        "FinansAsistanı.apk",
        "finansAsistanı.apk",
        "finansasistani.apk",
        "Finansım.apk",
        "finansim.apk"
    ]
    
    for name in possible_names:
        file_path = os.path.join(BASE_DIR, name)
        if os.path.exists(file_path):
            return FileResponse(
                path=file_path, 
                filename="FinansAsistani.apk", 
                media_type="application/vnd.android.package-archive"
            )
            
    # Eğer hiçbir isimle eşleşme sağlanamazsa sunucudaki mevcut dosyaları listeler
    present_files = os.listdir(BASE_DIR)
    return {
        "status": "error",
        "message": "APK dosyası sunucuda bulunamadı.",
        "sunucudaki_mevcut_dosyalar": present_files
    }
