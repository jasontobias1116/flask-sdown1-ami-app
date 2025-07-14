from flask import Flask, request, send_file
from shotgun_api3 import Shotgun
import requests
from io import BytesIO
from zipfile import ZipFile
from urllib.parse import urlparse, unquote
import re

app = Flask(__name__)

# --- CONFIGURATION ---
SERVER_PATH = "https://beef.shotgrid.autodesk.com/"
SCRIPT_NAME = "python_script_one"
SCRIPT_KEY = "ksoaxey(d9ynAruumhkccqebr"

# --- CONNECT TO SHOTGRID ---
sg = Shotgun(SERVER_PATH, SCRIPT_NAME, SCRIPT_KEY)

# --- HEALTH CHECK ROUTE ---
@app.route("/", methods=["GET"])
def index():
    return "Shot-level download script is running!"

# --- MAIN DOWNLOAD ROUTE ---
@app.route("/download_shot_assets", methods=["GET", "POST"])
def download_shot_assets():
    shot_id_str = (
        request.args.get("entity_id") or
        request.form.get("entity_id") or
        request.form.get("ids")
    )

    if not shot_id_str:
        return "No shot ID provided.", 400

    shot_id = int(shot_id_str.split(",")[0].strip())

    assets = sg.find("Asset", [["shots", "is", {"type": "Shot", "id": shot_id}]], ["id", "code"])

    if not assets:
        return f"No assets found for Shot {shot_id}", 404

    # Prepare in-memory ZIP file
    zip_buffer = BytesIO()

    with ZipFile(zip_buffer, 'w') as zip_file:
        for asset in assets:
            asset_id = asset["id"]
            asset_name = asset["code"]

            versions = sg.find("Version", [["entity", "is", {"type": "Asset", "id": asset_id}]],
                               ["id", "code", "sg_uploaded_movie"])

            for version in versions:
                version_name = version["code"]
                movie = version.get("sg_uploaded_movie")

                if movie and "url" in movie:
                    url = movie["url"]

                    # Safe filename
                    def safe_name(name):
                        return re.sub(r'[^A-Za-z0-9._-]', '_', name)

                    parsed_url = urlparse(url)
                    filename_from_url = unquote(parsed_url.path.split("/")[-1])
                    ext = filename_from_url.split(".")[-1] if "." in filename_from_url else "mov"

                    filename = f"{safe_name(asset_name)}_{safe_name(version_name)}.{ext}"

                    try:
                        resp = requests.get(url, stream=True)
                        resp.raise_for_status()

                        # Read content into memory
                        file_bytes = BytesIO(resp.content)
                        zip_file.writestr(filename, file_bytes.getvalue())

                    except Exception as e:
                        print(f"Failed to download {url}: {e}")

    zip_buffer.seek(0)

    # Send the ZIP file to client for download
    return send_file(
        zip_buffer,
        mimetype='application/zip',
        as_attachment=True,
        download_name=f"shot_{shot_id}_assets.zip"
    )

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
