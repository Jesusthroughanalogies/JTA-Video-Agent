"""Usage: qc.py '{"SHOT": "url", ...}'  -> downloads to /tmp/ep2/raw and builds a 3-frame strip per clip."""
import json, os, subprocess, sys
from PIL import Image
urls = json.loads(sys.argv[1])
os.makedirs('/tmp/ep2/raw', exist_ok=True); os.makedirs('/tmp/ep2/qc', exist_ok=True)
rows = []
for shot, url in urls.items():
    out = f'/tmp/ep2/raw/{shot}.mp4'
    if not os.path.exists(out):
        subprocess.run(['curl', '-sS', '-o', out, url], check=True)
    ims = []
    for t in (0.3, 2.5, 4.7):
        f = f'/tmp/ep2/qc/{shot}_{t}.jpg'
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-ss', str(t), '-i', out, '-frames:v', '1', '-vf', 'scale=480:270', f], check=True)
        ims.append(Image.open(f))
    row = Image.new('RGB', (1440, 270)); [row.paste(im, (i * 480, 0)) for i, im in enumerate(ims)]
    rows.append((shot, row))
for k in range(0, len(rows), 4):
    chunk = rows[k:k + 4]
    sheet = Image.new('RGB', (1440, 270 * len(chunk)))
    for i, (s, r) in enumerate(chunk): sheet.paste(r, (0, i * 270))
    name = '_'.join(s for s, _ in chunk)
    sheet.save(f'/tmp/ep2/qc/sheet_{name}.jpg'); print(f'/tmp/ep2/qc/sheet_{name}.jpg')
