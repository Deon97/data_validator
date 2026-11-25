import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
version = (ROOT / "VERSION.txt").read_text(encoding="utf-8").strip()

dist = ROOT / "dist"
dist.mkdir(exist_ok=True)
zip_path = dist / f"app_v{version}.zip"

items = [ROOT / "app.py", ROOT / "VERSION.txt"]
for folder in ("core", "assets"):
    items += [p for p in (ROOT / folder).rglob("*")
              if p.is_file() and "__pycache__" not in p.parts]

with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
    for p in items:
        z.write(p, p.relative_to(ROOT))

(dist / "latest.txt").write_text(version, encoding="utf-8")
print(f"Created {zip_path}")