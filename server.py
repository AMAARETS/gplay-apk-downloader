#!/usr/bin/env python3
"""
GPlay Downloader - Server
Restored Env Var Priority + Region Support
"""
import os
# Fix protobuf compatibility
os.environ['PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION'] = 'python'

import json
import re
import logging
import time
import uuid
from pathlib import Path
from flask import Flask, request, jsonify, send_file, Response
from flask_cors import CORS
import requests
import cloudscraper
import urllib3
import ssl

# --- 1. SSL & Scraper Setup ---
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class NoVerifyHTTPAdapter(requests.adapters.HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        kwargs['ssl_context'] = ssl._create_unverified_context()
        return super().init_poolmanager(*args, **kwargs)

def create_scraper_no_verify():
    scraper = cloudscraper.create_scraper()
    scraper.verify = False
    adapter = NoVerifyHTTPAdapter()
    scraper.mount('https://', adapter)
    scraper.mount('http://', adapter)
    return scraper

SCRAPER = create_scraper_no_verify()

app = Flask(__name__)
CORS(app)

try:
    from gpapi import googleplay_pb2
    HAS_GPAPI = True
except:
    HAS_GPAPI = False
    logger.warning("gpapi library missing! Downloads will fail.")

# Constants
DISPENSER_URL = "https://auroraoss.com/api/auth"
FDFE_URL = "https://android.clients.google.com/fdfe"
PURCHASE_URL = f"{FDFE_URL}/purchase"
DELIVERY_URL = f"{FDFE_URL}/delivery"
DETAILS_URL = f"{FDFE_URL}/details"
AUTH_CACHE_DIR = Path.home()

# --- 2. CONFIGURATION PROFILES ---

REGIONS = {
    'il': {'lang': 'he_IL', 'tz': 'Asia/Jerusalem', 'sim': '42501', 'cc': 'IL'}, # Partner Israel
    'us': {'lang': 'en_US', 'tz': 'America/New_York', 'sim': '310260', 'cc': 'US'}, # T-Mobile US
    'de': {'lang': 'de_DE', 'tz': 'Europe/Berlin', 'sim': '26201', 'cc': 'DE'}, # Telekom.de
}

BASE_DEVICES = {
    's23': {
        'UserReadableName': 'Samsung Galaxy S23',
        'Build.HARDWARE': 'kalama', 'Build.PRODUCT': 'kalama', 'Build.DEVICE': 'kalama',
        'Build.MANUFACTURER': 'samsung', 'Build.MODEL': 'SM-S911B',
        'Build.ID': 'UP1A.231005.007', 'Build.BOOTLOADER': 'S911BXXU3BWK5',
        'Build.VERSION.SDK_INT': '34', 'Build.VERSION.RELEASE': '14',
        'Build.FINGERPRINT': 'samsung/kalama/kalama:14/UP1A.231005.007/S911BXXU3BWK5:user/release-keys',
        'GL.Version': '196610', 'Platforms': 'arm64-v8a,armeabi-v7a,armeabi',
        'Screen.Density': '480', 'Screen.Width': '1080', 'Screen.Height': '2340',
    },
    'pixel7': {
        'UserReadableName': 'Google Pixel 7a',
        'Build.HARDWARE': 'lynx', 'Build.PRODUCT': 'lynx', 'Build.DEVICE': 'lynx',
        'Build.MANUFACTURER': 'Google', 'Build.MODEL': 'Pixel 7a',
        'Build.ID': 'UQ1A.231205.015', 'Build.BOOTLOADER': 'lynx-1.0-9716681',
        'Build.VERSION.SDK_INT': '34', 'Build.VERSION.RELEASE': '14',
        'Build.FINGERPRINT': 'google/lynx/lynx:14/UQ1A.231205.015/11084887:user/release-keys',
        'GL.Version': '196610', 'Platforms': 'arm64-v8a,armeabi-v7a,armeabi',
        'Screen.Density': '420', 'Screen.Width': '1080', 'Screen.Height': '2400',
    }
}

DEFAULT_PROPS = {
    'TouchScreen': '3', 'Keyboard': '1', 'Navigation': '1', 'ScreenLayout': '2',
    'HasHardKeyboard': 'false', 'HasFiveWayNavigation': 'false',
    'SharedLibraries': 'android.ext.shared,org.apache.http.legacy',
    'Client': 'android-google',
    'GSF.version': '223616055',
    'Vending.version': '84122900',
    'Vending.versionString': '41.2.29-23 [0] [PR] 639844241',
    'Roaming': 'mobile-notroaming',
}

# --- 3. HELPER FUNCTIONS ---

def get_device_config(dev_key, reg_key):
    if dev_key not in BASE_DEVICES: dev_key = 's23'
    if reg_key not in REGIONS: reg_key = 'il'
    
    reg_data = REGIONS[reg_key]
    hw_data = BASE_DEVICES[dev_key]
    
    config = DEFAULT_PROPS.copy()
    config.update(hw_data)
    config['Locales'] = f"{reg_data['lang']},en_US"
    config['TimeZone'] = reg_data['tz']
    config['SimOperator'] = reg_data['sim']
    config['CellOperator'] = reg_data['sim']
    
    return config

def get_headers(auth, reg_key):
    reg = REGIONS.get(reg_key, REGIONS['il'])
    locale = reg['lang'].replace('_', '-')
    device_info = auth.get('deviceInfoProvider', {})
    
    return {
        'Authorization': f"Bearer {auth.get('authToken')}",
        'User-Agent': device_info.get('userAgentString', 'Android-Finsky/41.2.29-23'),
        'X-DFE-Device-Id': auth.get('gsfId', ''),
        'Accept-Language': locale,
        'X-DFE-Client-Id': 'am-android-google',
        'X-DFE-Network-Type': '4',
        'X-DFE-Content-Filters': '',
        'X-Limit-Ad-Tracking-Enabled': 'false',
        'X-DFE-Cookie': auth.get('dfeCookie', ''),
    }

def get_cached_auth(cache_key):
    # 1. PRIORITY: Check Environment Variable (Restored!)
    env_token = os.environ.get('GPLAY_AUTH_TOKEN')
    if env_token:
        try:
            auth = json.loads(env_token)
            if auth.get('authToken'):
                logger.info("Using auth token from Environment Variable")
                return auth
        except: 
            logger.warning("Failed to parse GPLAY_AUTH_TOKEN")

    # 2. Check File Cache
    path = AUTH_CACHE_DIR / f".gplay-auth-{cache_key}.json"
    if path.exists():
        try:
            return json.loads(path.read_text())
        except: pass
    return None

def save_cached_auth(auth, cache_key):
    try:
        (AUTH_CACHE_DIR / f".gplay-auth-{cache_key}.json").write_text(json.dumps(auth))
    except: pass

# --- 4. CORE DOWNLOAD LOGIC ---

def get_download_info_internal(pkg, auth, reg_key):
    if not HAS_GPAPI: return {'error': 'GPAPI missing'}
    
    headers = {
        **get_headers(auth, reg_key),
        'Content-Type': 'application/x-protobuf',
        'Accept': 'application/x-protobuf'
    }

    # A. DETAILS
    try:
        r = requests.get(f'{DETAILS_URL}?doc={pkg}', headers=headers, timeout=15, verify=False)
        wrapper = googleplay_pb2.ResponseWrapper()
        wrapper.ParseFromString(r.content)
        
        doc = wrapper.payload.detailsResponse.docV2
        if not doc.docid: return {'error': 'App not found'}
        
        vc = doc.details.appDetails.versionCode
        if vc == 0: return {'error': 'Incompatible/Restricted'}
        
    except Exception as e:
        return {'error': f'Details failed: {e}'}

    # B. PURCHASE
    try:
        requests.post(PURCHASE_URL, headers={**headers, 'Content-Type': 'application/x-www-form-urlencoded'},
                     data=f'doc={pkg}&ot=1&vc={vc}', timeout=10, verify=False)
    except: pass

    # C. DELIVERY
    try:
        r = requests.get(f'{DELIVERY_URL}?doc={pkg}&ot=1&vc={vc}', headers=headers, timeout=15, verify=False)
        wrapper = googleplay_pb2.ResponseWrapper()
        wrapper.ParseFromString(r.content)
        data = wrapper.payload.deliveryResponse.appDeliveryData
        
        if not data.downloadUrl: return {'error': 'No URL returned'}
        
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
        return {'error': f'Delivery failed: {e}'}

# --- 5. ROUTES ---

@app.route('/')
def index(): return send_file('index.html')

@app.route('/api/search')
def search():
    q = request.args.get('q')
    reg = request.args.get('region', 'il')
    hl = REGIONS.get(reg, REGIONS['il'])['lang'].split('_')[0]
    
    try:
        html = SCRAPER.get(f'https://play.google.com/store/search?q={q}&c=apps&hl={hl}&gl={reg}', timeout=10).text
        results = []
        for m in re.finditer(r'href="/store/apps/details\?id=([^"]+)"[^>]*><div[^>]*>([^<]+)</div>', html):
            if m.group(1) not in [x['package'] for x in results]:
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
        
        title_m = re.search(r'<h1[^>]*>([^<]+)</h1>', r.text)
        title = title_m.group(1) if title_m else pkg
        
        dev_m = re.search(r'<div[^>]*class="Vbfug "[^>]*><span[^>]*>([^<]+)</span>', r.text)
        dev = dev_m.group(1) if dev_m else "Unknown"
        
        return jsonify({'package': pkg, 'title': title, 'developer': dev})
    except:
        return jsonify({'package': pkg, 'title': pkg, 'developer': 'Unknown'})

@app.route('/api/download-info-stream/<path:pkg>')
def stream(pkg):
    dev_key = request.args.get('device', 's23')
    reg_key = request.args.get('region', 'il')
    config = get_device_config(dev_key, reg_key)
    cache_key = f"{dev_key}_{reg_key}"
    
    def generate():
        # 1. Try Cached (Env Var or File)
        cached = get_cached_auth(cache_key)
        if cached:
            yield f"data: {json.dumps({'type':'progress','msg':'Using cached/env token...'})}\n\n"
            res = get_download_info_internal(pkg, cached, reg_key)
            if 'error' not in res:
                yield f"data: {json.dumps({'type':'success', **res})}\n\n"
                return
            yield f"data: {json.dumps({'type':'progress','msg':'Cached token failed, trying new...'})}\n\n"

        # 2. Get New Token Loop
        scraper = create_scraper_no_verify()
        headers = {'User-Agent': 'com.aurora.store-4.6.1-70', 'Content-Type': 'application/json'}
        
        for i in range(1, 8):
            yield f"data: {json.dumps({'type':'progress','msg':f'Generating Token #{i}...'})}\n\n"
            try:
                r = scraper.post(DISPENSER_URL, json=config, headers=headers, timeout=30)
                if r.status_code == 200:
                    auth = r.json()
                    res = get_download_info_internal(pkg, auth, reg_key)
                    if 'error' not in res:
                        save_cached_auth(auth, cache_key)
                        yield f"data: {json.dumps({'type':'success', **res})}\n\n"
                        return
                    else:
                        yield f"data: {json.dumps({'type':'progress','msg':f'Error: {res["error"]}'})}\n\n"
                else:
                    yield f"data: {json.dumps({'type':'progress','msg':f'Dispenser Err: {r.status_code}'})}\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'type':'progress','msg':f'Net Err: {str(e)[:20]}'})}\n\n"
            time.sleep(1.5)
            
        yield f"data: {json.dumps({'type':'error', 'msg':'Failed to find working token'})}\n\n"

    return Response(generate(), mimetype='text/event-stream')

@app.route('/proxy-download')
def proxy_dl():
    url = request.args.get('url')
    cookie = request.args.get('cookie')
    name = request.args.get('name', 'file.apk')
    headers = {'Cookie': cookie} if cookie else {}
    try:
        r = requests.get(url, headers=headers, stream=True, verify=False, timeout=120)
        return Response(r.iter_content(chunk_size=8192), 
                        headers={'Content-Disposition': f'attachment; filename="{name}"'},
                        content_type='application/vnd.android.package-archive')
    except Exception as e:
        return str(e), 500

@app.route('/api/download-url', methods=['POST'])
def download_url():
    """Download any file from URL via server"""
    data = request.json
    url = data.get('url')
    filename = data.get('filename', 'download.apk')
    
    if not url:
        return jsonify({'error': 'URL required'}), 400
    
    try:
        # Download file to server
        logger.info(f"Downloading from URL: {url}")
        r = requests.get(url, stream=True, verify=False, timeout=60)
        r.raise_for_status()
        
        # Get filename from headers if not provided
        if filename == 'download.apk':
            content_disp = r.headers.get('content-disposition', '')
            if 'filename=' in content_disp:
                filename = content_disp.split('filename=')[-1].strip('"')
            else:
                # Extract from URL
                filename = url.split('/')[-1].split('?')[0] or 'download.apk'
        
        # Stream back to client
        return Response(
            r.iter_content(chunk_size=8192),
            headers={
                'Content-Disposition': f'attachment; filename="{filename}"',
                'Content-Type': r.headers.get('content-type', 'application/octet-stream')
            }
        )
    except Exception as e:
        logger.error(f"Download failed: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)