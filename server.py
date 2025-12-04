#!/usr/bin/env python3
"""
GPlay Downloader - Server
Fixed Regex errors & Added Region Support
"""
import os
os.environ['PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION'] = 'python'

import json
import re
import logging
import uuid
import time
from pathlib import Path
from flask import Flask, request, jsonify, send_file, Response
from flask_cors import CORS
import requests
import cloudscraper
import urllib3
import ssl

# SSL & Logging Setup
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Scraper Setup
class NoVerifyHTTPAdapter(requests.adapters.HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        kwargs['ssl_context'] = ssl._create_unverified_context()
        return super().init_poolmanager(*args, **kwargs)

def create_scraper():
    s = cloudscraper.create_scraper()
    s.verify = False
    s.mount('https://', NoVerifyHTTPAdapter())
    return s

SCRAPER = create_scraper()
app = Flask(__name__)
CORS(app)

# Protobuf Check
try:
    from gpapi import googleplay_pb2
    HAS_GPAPI = True
except:
    HAS_GPAPI = False
    logger.warning("gpapi not found! Downloads will fail.")

# Constants
DISPENSER_URL = 'https://auroraoss.com/api/auth'
FDFE_URL = 'https://android.clients.google.com/fdfe'
PURCHASE_URL = f'{FDFE_URL}/purchase'
DELIVERY_URL = f'{FDFE_URL}/delivery'
DETAILS_URL = f'{FDFE_URL}/details'

# --- CONFIGURATION ---

REGIONS = {
    'il': {'code': 'il', 'lang': 'he_IL', 'tz': 'Asia/Jerusalem', 'sim': '42501', 'cc': 'IL'}, # Israel (Partner)
    'us': {'code': 'us', 'lang': 'en_US', 'tz': 'America/New_York', 'sim': '310260', 'cc': 'US'}, # USA (T-Mobile)
    'de': {'code': 'de', 'lang': 'de_DE', 'tz': 'Europe/Berlin', 'sim': '26201', 'cc': 'DE'}, # Germany (Telekom)
}

# Base profiles without region data
BASE_DEVICES = {
    's23': {
        'name': 'Samsung S23',
        'build_props': {
            'Build.MANUFACTURER': 'samsung',
            'Build.MODEL': 'SM-S911B',
            'Build.PRODUCT': 'kalama',
            'Build.DEVICE': 'kalama',
            'Build.FINGERPRINT': 'samsung/kalama/kalama:14/UP1A.231005.007/S911BXXU3BWK5:user/release-keys',
            'Build.VERSION.SDK_INT': '34',
            'GL.Version': '196610',
            'Platforms': 'arm64-v8a,armeabi-v7a,armeabi'
        }
    },
    'pixel7': {
        'name': 'Pixel 7a',
        'build_props': {
            'Build.MANUFACTURER': 'Google',
            'Build.MODEL': 'Pixel 7a',
            'Build.PRODUCT': 'lynx',
            'Build.DEVICE': 'lynx',
            'Build.FINGERPRINT': 'google/lynx/lynx:14/UQ1A.231205.015/11084887:user/release-keys',
            'Build.VERSION.SDK_INT': '34',
            'GL.Version': '196610',
            'Platforms': 'arm64-v8a,armeabi-v7a,armeabi'
        }
    },
    'j7': {
        'name': 'Galaxy J7 (Old)',
        'build_props': {
            'Build.MANUFACTURER': 'samsung',
            'Build.MODEL': 'SM-J710F',
            'Build.VERSION.SDK_INT': '27',
            'Platforms': 'armeabi-v7a,armeabi'
        }
    }
}

# Defaults
DEFAULT_REGION = 'il'
DEFAULT_DEVICE = 's23'
AUTH_CACHE_DIR = Path.home()
TEMP_APKS = {}

# --- HELPERS ---

def get_device_config(device_key, region_key):
    """Generates a full device config by merging hardware + region."""
    if device_key not in BASE_DEVICES: device_key = DEFAULT_DEVICE
    if region_key not in REGIONS: region_key = DEFAULT_REGION

    base = BASE_DEVICES[device_key]['build_props'].copy()
    reg = REGIONS[region_key]

    # Fill in the standard Aurora format
    config = {
        'UserReadableName': BASE_DEVICES[device_key]['name'],
        'Locales': f"{reg['lang']},en_US",
        'TimeZone': reg['tz'],
        'SimOperator': reg['sim'],
        'CellOperator': reg['sim'],
        'Roaming': 'mobile-notroaming',
        'Client': 'android-google',
        'GSF.version': '223616055',
        'Vending.version': '84122900',
        'Vending.versionString': '41.2.29-23 [0] [PR] 639844241',
        # Merge build props
        **base
    }
    return config

def get_cached_auth(arch_key):
    """Simple file cache for auth tokens."""
    fpath = AUTH_CACHE_DIR / f'.gplay-auth-{arch_key}.json'
    if fpath.exists():
        try:
            return json.loads(fpath.read_text())
        except: pass
    return None

def save_cached_auth(auth, arch_key):
    fpath = AUTH_CACHE_DIR / f'.gplay-auth-{arch_key}.json'
    try:
        fpath.write_text(json.dumps(auth))
    except: pass

def get_headers(auth, region_key):
    """Get API headers with correct locale."""
    reg = REGIONS.get(region_key, REGIONS['il'])
    locale = reg['lang'].replace('_', '-')
    return {
        'Authorization': f"Bearer {auth.get('authToken')}",
        'X-DFE-Device-Id': auth.get('gsfId'),
        'Accept-Language': locale,
        'User-Agent': 'Android-Finsky/41.2.29-23',
        'X-DFE-Client-Id': 'am-android-google',
    }

# --- CORE LOGIC ---

def get_download_info_internal(pkg, auth, region_key):
    if not HAS_GPAPI: return {'error': 'GPAPI missing'}
    
    headers = {
        **get_headers(auth, region_key),
        'Content-Type': 'application/x-protobuf',
        'Accept': 'application/x-protobuf'
    }

    # 1. Details
    try:
        r = requests.get(f'{DETAILS_URL}?doc={pkg}', headers=headers, timeout=15, verify=False)
        wrapper = googleplay_pb2.ResponseWrapper()
        wrapper.ParseFromString(r.content)
        doc = wrapper.payload.detailsResponse.docV2
        
        if not doc.docid:
            return {'error': 'App not found (Region lock or invalid package)'}
        
        vc = doc.details.appDetails.versionCode
        if vc == 0:
            return {'error': 'App is incompatible or not available in this region'}
            
    except Exception as e:
        return {'error': f'Details error: {str(e)}'}

    # 2. Purchase (Free)
    try:
        requests.post(PURCHASE_URL, headers={**headers, 'Content-Type': 'application/x-www-form-urlencoded'},
                     data=f'doc={pkg}&ot=1&vc={vc}', timeout=10, verify=False)
    except: pass

    # 3. Delivery
    try:
        r = requests.get(f'{DELIVERY_URL}?doc={pkg}&ot=1&vc={vc}', headers=headers, timeout=15, verify=False)
        wrapper = googleplay_pb2.ResponseWrapper()
        wrapper.ParseFromString(r.content)
        data = wrapper.payload.deliveryResponse.appDeliveryData

        if not data.downloadUrl:
            return {'error': 'No download URL returned'}

        return {
            'package': pkg,
            'versionCode': vc,
            'version': doc.details.appDetails.versionString,
            'title': doc.title,
            'downloadUrl': data.downloadUrl,
            'size': data.downloadSize,
            'cookies': [{'name': c.name, 'value': c.value} for c in data.downloadAuthCookie],
            'splits': [{'name': s.name or f'split{i}', 'url': s.downloadUrl} for i,s in enumerate(data.split) if s.downloadUrl]
        }
    except Exception as e:
        return {'error': f'Delivery error: {str(e)}'}

# --- ROUTES ---

@app.route('/')
def index(): return send_file('index.html')

@app.route('/api/search')
def search():
    q = request.args.get('q')
    reg = request.args.get('region', 'il')
    hl = REGIONS.get(reg, REGIONS['il'])['lang'].split('_')[0] # he, en...
    
    try:
        html = SCRAPER.get(f'https://play.google.com/store/search?q={q}&c=apps&hl={hl}&gl={reg}', timeout=10).text
        results = []
        # Robust regex
        for m in re.finditer(r'href="/store/apps/details\?id=([^"]+)"[^>]*><div[^>]*>([^<]+)</div>', html):
            if m.group(1) not in [r['package'] for r in results]:
                results.append({'package': m.group(1), 'title': m.group(2)})
                if len(results) >= 5: break
        return jsonify({'results': results})
    except Exception as e:
        return jsonify({'error': str(e)})

@app.route('/api/info/<path:pkg>')
def info(pkg):
    reg = request.args.get('region', 'il')
    hl = REGIONS.get(reg, REGIONS['il'])['lang'].split('_')[0]
    
    try:
        r = SCRAPER.get(f'https://play.google.com/store/apps/details?id={pkg}&hl={hl}&gl={reg}', timeout=15)
        if r.status_code == 404: return jsonify({'error': 'App not found'}), 404
        
        # SAFE REGEX - Fixes the NoneType crash
        title_match = re.search(r'<h1[^>]*>([^<]+)</h1>', r.text)
        title = title_match.group(1) if title_match else pkg

        dev_match = re.search(r'<div[^>]*class="Vbfug "[^>]*><span[^>]*>([^<]+)</span>', r.text)
        dev = dev_match.group(1) if dev_match else "Unknown"

        return jsonify({'title': title, 'developer': dev, 'package': pkg})
    except Exception as e:
        logger.error(f"Info Error: {e}")
        return jsonify({'title': pkg, 'developer': 'Unknown (Error)', 'package': pkg}) # Fallback instead of crash

@app.route('/api/download-info-stream/<path:pkg>')
def stream_info(pkg):
    dev_key = request.args.get('device', DEFAULT_DEVICE)
    reg_key = request.args.get('region', DEFAULT_REGION)
    config = get_device_config(dev_key, reg_key)
    
    def generate():
        cached = get_cached_auth(dev_key + reg_key)
        if cached:
            yield f"data: {json.dumps({'type':'progress','msg':'Trying cached token...'})}\n\n"
            res = get_download_info_internal(pkg, cached, reg_key)
            if 'error' not in res:
                yield f"data: {json.dumps({'type':'success', **res})}\n\n"
                return

        for i in range(1, 10):
            yield f"data: {json.dumps({'type':'progress','msg':f'Generating Token #{i} ({reg_key})...'})}\n\n"
            try:
                r = SCRAPER.post(DISPENSER_URL, json=config, headers={'Content-Type':'application/json'}, timeout=30)
                if r.ok:
                    auth = r.json()
                    res = get_download_info_internal(pkg, auth, reg_key)
                    if 'error' not in res:
                        save_cached_auth(auth, dev_key + reg_key)
                        yield f"data: {json.dumps({'type':'success', **res})}\n\n"
                        return
                    else:
                        yield f"data: {json.dumps({'type':'progress','msg':f'Error: {res["error"]}'})}\n\n"
            except: pass
            time.sleep(1)
        
        yield f"data: {json.dumps({'type':'error', 'msg':'Failed to find working token'})}\n\n"

    return Response(generate(), mimetype='text/event-stream')

# --- PROXY FOR ZIP DOWNLOAD ---
# This is critical for the "Download ZIP" button to work
@app.route('/proxy-download')
def proxy_download():
    url = request.args.get('url')
    cookie_str = request.args.get('cookie')
    name = request.args.get('name', 'file.apk')
    
    if not url: return "Missing URL", 400
    
    headers = {}
    if cookie_str: headers['Cookie'] = cookie_str
    
    try:
        r = requests.get(url, headers=headers, stream=True, verify=False, timeout=60)
        return Response(r.iter_content(chunk_size=8192), 
                        headers={'Content-Disposition': f'attachment; filename="{name}"'},
                        content_type='application/vnd.android.package-archive')
    except Exception as e:
        return str(e), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)