import json
import os
from pathlib import Path
from flask import Flask, request, jsonify, render_template_string

app = Flask(__name__)

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
LEADS_FILE = DATA_DIR / "leads.json"
STATS_FILE = DATA_DIR / "stats.json"

DATA_DIR.mkdir(exist_ok=True)

if not LEADS_FILE.exists():
    LEADS_FILE.write_text("[]")

if not STATS_FILE.exists():
    STATS_FILE.write_text(json.dumps({
        "total_leads": 0,
        "total_content_generated": 0,
        "total_posts": 0
    }, indent=2))

LANDING_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>The Faceless Income Engine</title>
<meta name="description" content="Automated Content to Warm Traffic to Silent Sales. Zero face, zero voice, zero overhead.">
<meta property="og:title" content="The Faceless Income Engine">
<meta property="og:description" content="Automated Content to Warm Traffic to Silent Sales. Zero face, zero voice, zero overhead.">
<meta property="og:type" content="website">
<meta property="og:url" content="https://yourdomain.com">
<meta name="twitter:card" content="summary_large_image">
<!-- Google Analytics placeholder: GA_MEASUREMENT_ID -->
<!-- Plausible placeholder: https://plausible.io/js/script.js -->
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Oxygen,Ubuntu,sans-serif;background:#0a0a0b;color:#e4e4e7;min-height:100vh;display:flex;align-items:center;justify-content:center}
.container{max-width:520px;width:100%;padding:2rem 1.5rem;text-align:center}
.logo{font-size:2.5rem;margin-bottom:.5rem}
h1{font-size:2rem;font-weight:800;line-height:1.2;margin-bottom:.5rem;background:linear-gradient(135deg,#f59e0b,#e879f9);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text}
.subhead{font-size:1.1rem;color:#a1a1aa;margin-bottom:2rem;font-weight:500}
.bullets{text-align:left;margin-bottom:2rem;list-style:none}
.bullets li{padding:.6rem 0;padding-left:1.8rem;position:relative;font-size:.95rem;color:#d4d4d8}
.bullets li::before{content:"\\2713";position:absolute;left:0;color:#22c55e;font-weight:700}
.form-group{margin-bottom:1rem}
input[type=email]{width:100%;padding:.85rem 1rem;border-radius:8px;border:1px solid #27272a;background:#18181b;color:#e4e4e7;font-size:1rem;outline:none;transition:border-color .2s}
input[type=email]:focus{border-color:#a855f7}
.btn{display:inline-block;width:100%;padding:.85rem 1rem;border-radius:8px;border:none;font-size:1rem;font-weight:600;cursor:pointer;text-decoration:none;transition:opacity .2s,transform .1s}
.btn:active{transform:scale(.98)}
.btn-primary{background:linear-gradient(135deg,#a855f7,#6366f1);color:#fff}
.btn-secondary{background:#27272a;color:#e4e4e7;margin-top:.75rem}
.btn-checkout{background:linear-gradient(135deg,#f59e0b,#e879f9);color:#fff;margin-top:1rem}
.btn:hover{opacity:.9}
.or-divider{margin:1.25rem 0;color:#52525b;font-size:.85rem;display:flex;align-items:center;gap:.75rem}
.or-divider::before,.or-divider::after{content:"";flex:1;height:1px;background:#27272a}
.footer{margin-top:2rem;font-size:.75rem;color:#52525b}
.success{display:none;padding:1rem;background:#052e16;border:1px solid #166534;border-radius:8px;color:#bbf7d0;margin-bottom:1rem}
@media(max-width:480px){h1{font-size:1.6rem}.container{padding:1.5rem 1rem}}
</style>
</head>
<body>
<div class="container" id="app">
<div class="logo">&#9889;</div>
<h1>The Faceless Income Engine</h1>
<p class="subhead">Automated Content &rarr; Warm Traffic &rarr; Silent Sales</p>

<ul class="bullets">
<li>AI writes your content while you sleep</li>
<li>Posts automatically to 3 platforms</li>
<li>Zero face, zero voice, zero overhead</li>
</ul>

<div id="success-msg" class="success">Thanks! Your checklist is on the way.</div>

<form id="subscribe-form" action="/subscribe" method="POST">
<div class="form-group">
<input type="email" name="email" placeholder="Your best email" required>
</div>
<button type="submit" class="btn btn-primary">Get the Launch Checklist</button>
</form>

<div class="or-divider">or</div>

<a href="/checkout" class="btn btn-checkout">Full System Access &mdash; $47 one-time</a>

<div class="footer">
<a href="/download/checklist" style="color:#52525b;text-decoration:underline;font-size:.75rem">Download Checklist</a>
</div>
</div>

<script>
document.getElementById('subscribe-form').addEventListener('submit', async function(e){
e.preventDefault();
const email = this.email.value.trim();
if(!email) return;
try{
const res = await fetch('/subscribe', {
method:'POST',
headers:{'Content-Type':'application/json'},
body:JSON.stringify({email})
});
const data = await res.json();
if(data.status==='ok'){
document.getElementById('success-msg').style.display='block';
this.reset();
}
}catch(err){}
});
</script>
</body>
</html>"""

def load_leads():
    return json.loads(LEADS_FILE.read_text())

def save_leads(leads):
    LEADS_FILE.write_text(json.dumps(leads, indent=2))

def load_stats():
    return json.loads(STATS_FILE.read_text())

def save_stats(stats):
    STATS_FILE.write_text(json.dumps(stats, indent=2))

@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def landing(path):
    if path and path != "checkout":
        return render_template_string(LANDING_HTML)
    return render_template_string(LANDING_HTML)

@app.route("/subscribe", methods=["POST"])
def subscribe():
    data = request.get_json(silent=True) or request.form
    email = (data.get("email") or "").strip()
    if not email or "@" not in email:
        return jsonify({"status": "error", "message": "Invalid email"}), 400
    leads = load_leads()
    if any(l["email"] == email for l in leads):
        return jsonify({"status": "ok", "message": "Already subscribed"})
    leads.append({"email": email, "timestamp": __import__("datetime").datetime.utcnow().isoformat() + "Z"})
    save_leads(leads)
    stats = load_stats()
    stats["total_leads"] += 1
    save_stats(stats)
    return jsonify({"status": "ok", "message": "Subscribed"})

@app.route("/download/checklist")
def download_checklist():
    return "<h1>Checklist PDF</h1><p>Your launch checklist would be served here.</p>", 404

@app.route("/api/stats")
def api_stats():
    return jsonify(load_stats())

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
