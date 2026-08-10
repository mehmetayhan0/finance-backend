from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse
import os

app = FastAPI()

# Ana Sayfa
@app.get("/", response_class=HTMLResponse)
def read_root():
    with open("index.html", "r", encoding="utf-8") as f:
        return f.read()

# Manifest ve Service Worker Servisleri
@app.get("/manifest.json")
def get_manifest():
    return FileResponse("manifest.json", media_type="application/json")

@app.get("/sw.js")
def get_sw():
    return FileResponse("sw.js", media_type="application/javascript")

# APK İndirme Rotası (Güncellendi)
@app.get("/download-apk")
def download_apk():
    # Sunucudaki olası APK dosya adlarını kontrol et
    possible_names = ["FinansAsistani.apk", "finansasistani.apk", "Finansım.apk"]
    
    for apk_name in possible_names:
        if os.path.exists(apk_name):
            return FileResponse(
                path=apk_name, 
                filename="FinansAsistani.apk", 
                media_type="application/vnd.android.package-archive"
            )
            
    return {"message": "APK dosyası henüz sunucuya yüklenmedi."}
