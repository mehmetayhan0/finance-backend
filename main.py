from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse
import os

app = FastAPI()

# Ana Sayfa (index.html)
@app.get("/", response_class=HTMLResponse)
def read_root():
    with open("index.html", "r", encoding="utf-8") as f:
        return f.read()

# PWABuilder için Manifest Dosyası Servisi
@app.get("/manifest.json")
def get_manifest():
    return FileResponse("manifest.json", media_type="application/json")

# Service Worker Dosyası Servisi
@app.get("/sw.js")
def get_sw():
    return FileResponse("sw.js", media_type="application/javascript")

# APK İndirme Rotası
@app.get("/download-apk")
def download_apk():
    apk_path = "FinansAsistani.apk"
    if os.path.exists(apk_path):
        return FileResponse(
            path=apk_path, 
            filename="FinansAsistani.apk", 
            media_type="application/vnd.android.package-archive"
        )
    return {"message": "APK dosyası henüz sunucuya yüklenmedi."}
