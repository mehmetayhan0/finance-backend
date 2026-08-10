from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse
import os

app = FastAPI()

@app.get("/", response_class=HTMLResponse)
def read_root():
    with open("index.html", "r", encoding="utf-8") as f:
        return f.read()

# APK İndirme İsteği
@app.get("/download-apk")
def download_apk():
    apk_path = "FinansAsistani.apk"
    # Eğer dizinde apk dosyası varsa indir, yoksa yönlendir
    if os.path.exists(apk_path):
        return FileResponse(
            path=apk_path, 
            filename="FinansAsistani.apk", 
            media_type="application/vnd.android.package-archive"
        )
    return {"message": "APK dosyası sunucuya eklendiğinde buradan indirilebilecek."}
