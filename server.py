#!/usr/bin/env python3
"""
GPlay Downloader - Local Python Server
Downloads APKs from Google Play Store with direct browser downloads
Uses gpapi for proper protobuf parsing
"""

import os
# Fix protobuf compatibility issue with gpapi
os.environ['PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION'] = 'python'

import json
import base64
import re
import logging
from flask import Flask, request, jsonify, send_file, Response
from flask_cors import CORS
import requests
import cloudscraper
import urllib3
import ssl
from pathlib import Path

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Create custom SSL context that doesn't verify certificates
class NoVerifyHTTPAdapter(requests.adapters.HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        kwargs['ssl_context'] = ssl._create_unverified_context()
        return super().init_poolmanager(*args, **kwargs)

# Create scraper with SSL verification disabled
def create_scraper_no_verify():
    scraper = cloudscraper.create_scraper()
    scraper.verify = False
    adapter = NoVerifyHTTPAdapter()
    scraper.mount('https://', adapter)
    scraper.mount('http://', adapter)
    return scraper

# Reusable scraper instance
SCRAPER = create_scraper_no_verify()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# Import gpapi protobuf
try:
    from gpapi import googleplay_pb2
    HAS_GPAPI = True
except (ImportError, TypeError) as e:
    HAS_GPAPI = False
    print(f"Warning: gpapi not available ({e}). Using fallback parser.")

DISPENSER_URL = 'https://auroraoss.com/api/auth'
FDFE_URL = 'https://android.clients.google.com/fdfe'
PURCHASE_URL = f'{FDFE_URL}/purchase'
DELIVERY_URL = f'{FDFE_URL}/delivery'
DETAILS_URL = f'{FDFE_URL}/details'

# --- CONFIGURATION & PROFILES ---

# Region Settings
REGIONS = {
    'il': {
        'country': 'IL',
        'language': 'he_IL',
        'timezone': 'Asia/Jerusalem',
        'sim_operator': '42501',  # Partner Israel
        'cell_operator': '42501',
    },
    'us': {
        'country': 'US',
        'language': 'en_US',
        'timezone': 'America/New_York',
        'sim_operator': '310260', # T-Mobile US
        'cell_operator': '310260',
    }
}

# Default Region - CHANGED TO ISRAEL
DEFAULT_REGION = 'il'

# Hardware Profiles
# Using Samsung Galaxy S23 for better compatibility (AliExpress often prefers Samsung fingerprints)
HARDWARE_S23_ARM64 = {
    'UserReadableName': 'Samsung Galaxy S23',
    'Build.HARDWARE': 'kalama',
    'Build.RADIO': 'unknown',
    'Build.FINGERPRINT': 'samsung/kalama/kalama:14/UP1A.231005.007/S911BXXU3BWK5:user/release-keys',
    'Build.BRAND': 'samsung',
    'Build.DEVICE': 'kalama',
    'Build.VERSION.SDK_INT': '34',
    'Build.VERSION.RELEASE': '14',
    'Build.MODEL': 'SM-S911B',
    'Build.MANUFACTURER': 'samsung',
    'Build.PRODUCT': 'kalama',
    'Build.ID': 'UP1A.231005.007',
    'Build.BOOTLOADER': 'S911BXXU3BWK5',
    'TouchScreen': '3',
    'Keyboard': '1',
    'Navigation': '1',
    'ScreenLayout': '2',
    'HasHardKeyboard': 'false',
    'HasFiveWayNavigation': 'false',
    'Screen.Density': '480',
    'Screen.Width': '1080',
    'Screen.Height': '2340',
    'Platforms': 'arm64-v8a,armeabi-v7a,armeabi',
    'Features': 'android.hardware.sensor.proximity,android.hardware.touchscreen,android.hardware.wifi,android.hardware.camera,android.hardware.bluetooth,android.hardware.nfc,android.hardware.location.gps',
    'SharedLibraries': 'android.ext.shared,org.apache.http.legacy,com.google.android.camera',
    'GL.Version': '196610',
    'GL.Extensions': 'GL_OES_EGL_image',
    'Client': 'android-google',
    'GSF.version': '223616055',
    'Vending.version': '84122900',
    'Vending.versionString': '41.2.29-23 [0] [PR] 639844241',
}

# Legacy device for ARMv7
HARDWARE_J7_ARMV7 = {
    'UserReadableName': 'Samsung Galaxy J7',
    'Build.HARDWARE': 'samsungexynos7870',
    'Build.RADIO': 'unknown',
    'Build.FINGERPRINT': 'samsung/j7xeltexx/j7xelte:8.1.0/M1AJQ/J710FXXU6CSH1:user/release-keys',
    'Build.BRAND': 'samsung',
    'Build.DEVICE': 'j7xelte',
    'Build.VERSION.SDK_INT': '27',
    'Build.VERSION.RELEASE': '8.1.0',
    'Build.MODEL': 'SM-J710F',
    'Build.MANUFACTURER': 'samsung',
    'Build.PRODUCT': 'j7xeltexx',
    'Build.ID': 'M1AJQ',
    'Build.BOOTLOADER': 'J710FXXU6CSH1',
    'TouchScreen': '3',
    'Keyboard': '1',
    'Navigation': '1',
    'ScreenLayout': '2',
    'HasHardKeyboard': 'false',
    'HasFiveWayNavigation': 'false',
    'Screen.Density': '320',
    'Screen.Width': '720',
    'Screen.Height': '1280',
    'Platforms': 'armeabi-v7a,armeabi',
    'Features': 'android.hardware.sensor.proximity,android.hardware.touchscreen,android.hardware.wifi,android.hardware.camera,android.hardware.bluetooth',
    'SharedLibraries': 'android.ext.shared,org.apache.http.legacy',
    'GL.Version': '196609',
    'GL.Extensions': 'GL_OES_EGL_image',
    'Client': 'android-google',
    'GSF.version': '203615037',
    'Vending.version': '82041300',
    'Vending.versionString': '20.4.13-all [0] [PR] 312295870',
}

SUPPORTED_ARCHS = ['arm64-v8a', 'armeabi-v7a']
AUTH_CACHE_DIR = Path.home()
AUTH_CACHE_FILES = {
    'arm64-v8a': AUTH_CACHE_DIR / '.gplay-auth.json',
    'armeabi-v7a': AUTH_CACHE_DIR / '.gplay-auth-armv7.json',
}

def get_device_config(arch='arm64-v8a', region_code=None):
    """Construct a device config merging hardware profile with region settings."""
    if not region_code:
        region_code = DEFAULT_REGION
    
    region_data = REGIONS.get(region_code, REGIONS[DEFAULT_REGION])
    
    # Select hardware base
    if arch == 'armeabi-v7a':
        config = HARDWARE_J7_ARMV7.copy()
    else:
        config = HARDWARE_S23_ARM64.copy()
    
    # Apply region specific settings
    config['Locales'] = f"{region_data['language']},en_US"
    config['TimeZone'] = region_data['timezone']
    config['SimOperator'] = region_data['sim_operator']
    config['CellOperator'] = region_data['cell_operator']
    
    # Roaming checks (disable roaming for home region to look authentic)
    config['Roaming'] = 'mobile-notroaming'
    
    return config

# --- HELPER FUNCTIONS ---

def merge_apks(base_apk_bytes, split_apks_bytes_list):
    """Merge base APK with split APKs into a single installable APK."""
    import subprocess
    import tempfile
    import shutil

    apkeditor_jar = os.path.join(os.path.dirname(__file__), 'APKEditor.jar')
    
    if os.path.exists(apkeditor_jar):
        work_dir = tempfile.mkdtemp(prefix='apk_merge_')
        try:
            # Write base APK
            base_path = os.path.join(work_dir, 'base.apk')
            with open(base_path, 'wb') as f:
                f.write(base_apk_bytes)

            # Write split APKs
            for i, (name, data) in enumerate(split_apks_bytes_list):
                split_path = os.path.join(work_dir, f'split{i}.apk')
                with open(split_path, 'wb') as f:
                    f.write(data)

            # Run APKEditor merge
            output_path = os.path.join(work_dir, 'merged.apk')
            result = subprocess.run(
                ['java', '-jar', apkeditor_jar, 'm', '-i', work_dir, '-o', output_path],
                capture_output=True, text=True, timeout=300
            )

            if result.returncode == 0 and os.path.exists(output_path):
                with open(output_path, 'rb') as f:
                    return f.read()
            else:
                logger.error(f"APKEditor failed: {result.stderr}")
                # Fallback to simple zip merge if APKEditor fails
                return merge_apks_simple(base_apk_bytes, split_apks_bytes_list)
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)
    else:
        return merge_apks_simple(base_apk_bytes, split_apks_bytes_list)

def merge_apks_simple(base_apk_bytes, split_apks_bytes_list):
    """Fallback simple merge."""
    import zipfile
    import io
    merged_files = {}
    
    def should_skip(name):
        return name.startswith('META-INF/') and name.endswith(('.SF', '.RSA', '.DSA', '.EC', '.MF'))

    with zipfile.ZipFile(io.BytesIO(base_apk_bytes), 'r') as base_zip:
        for name in base_zip.namelist():
            if not should_skip(name):
                merged_files[name] = base_zip.read(name)

    for _, split_bytes in split_apks_bytes_list:
        with zipfile.ZipFile(io.BytesIO(split_bytes), 'r') as split_zip:
            for name in split_zip.namelist():
                if not should_skip(name) and name != 'AndroidManifest.xml':
                    if name.startswith('lib/') or name not in merged_files:
                        merged_files[name] = split_zip.read(name)

    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as merged_zip:
        for name, data in sorted(merged_files.items()):
            merged_zip.writestr(name, data)
    return output.getvalue()

def sign_apk(apk_bytes):
    """Sign an APK using apksigner."""
    import subprocess
    import tempfile
    import shutil

    keystore = Path.home() / '.android' / 'debug.keystore'
    if not keystore.exists() or not shutil.which('apksigner'):
        return apk_bytes

    try:
        with tempfile.NamedTemporaryFile(suffix='.apk', delete=False) as tmp_in:
            tmp_in.write(apk_bytes)
            tmp_in_path = tmp_in.name
        
        tmp_out_path = tmp_in_path + '.signed'
        
        cmd = [
            'apksigner', 'sign', '--ks', str(keystore),
            '--ks-pass', 'pass:android', '--key-pass', 'pass:android',
            '--out', tmp_out_path, tmp_in_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        
        if result.returncode == 0 and os.path.exists(tmp_out_path):
            with open(tmp_out_path, 'rb') as f:
                signed_bytes = f.read()
            return signed_bytes
        return apk_bytes
    except Exception as e:
        logger.error(f"Signing failed: {e}")
        return apk_bytes
    finally:
        for p in [tmp_in_path, tmp_out_path]:
            if os.path.exists(p):
                os.unlink(p)

def format_size(bytes_size):
    if not bytes_size: return 'Unknown'
    size = float(bytes_size)
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024: return f'{size:.2f} {unit}'
        size /= 1024
    return f'{size:.2f} TB'

def get_cached_auth(arch='arm64-v8a'):
    env_token = os.environ.get('GPLAY_AUTH_TOKEN')
    if env_token:
        try:
            auth = json.loads(env_token)
            if auth.get('authToken') and auth.get('gsfId'):
                return auth
        except: pass
    
    cache_file = AUTH_CACHE_FILES.get(arch, AUTH_CACHE_FILES['arm64-v8a'])
    if cache_file.exists():
        try:
            return json.loads(cache_file.read_text())
        except: pass
    return None

def save_cached_auth(auth_data, arch='arm64-v8a'):
    try:
        AUTH_CACHE_FILES.get(arch, AUTH_CACHE_FILES['arm64-v8a']).write_text(json.dumps(auth_data, indent=2))
    except: pass

def get_auth_headers(auth, region=DEFAULT_REGION):
    """Build headers with region-specific language."""
    device_info = auth.get('deviceInfoProvider', {})
    region_data = REGIONS.get(region, REGIONS[DEFAULT_REGION])
    locale = region_data['language'].replace('_', '-') # he_IL -> he-IL
    
    return {
        'Authorization': f"Bearer {auth.get('authToken', '')}",
        'User-Agent': device_info.get('userAgentString', 'Android-Finsky/41.2.29-23'),
        'X-DFE-Device-Id': auth.get('gsfId', ''),
        'Accept-Language': locale,
        'X-DFE-Client-Id': 'am-android-google',
        'X-DFE-Network-Type': '4',
        'X-DFE-Content-Filters': '',
        'X-Limit-Ad-Tracking-Enabled': 'false',
        'X-DFE-Cookie': auth.get('dfeCookie', ''),
        'X-DFE-No-Prefetch': 'true',
    }

def get_download_info(pkg, auth, region=DEFAULT_REGION):
    if not HAS_GPAPI: return {'error': 'gpapi missing'}
    
    headers = {
        **get_auth_headers(auth, region),
        'Content-Type': 'application/x-protobuf',
        'Accept': 'application/x-protobuf',
    }

    # DETAILS
    try:
        resp = requests.get(f'{DETAILS_URL}?doc={pkg}', headers=headers, timeout=30, verify=False)
        wrapper = googleplay_pb2.ResponseWrapper()
        wrapper.ParseFromString(resp.content)
        
        doc = wrapper.payload.detailsResponse.docV2
        if not doc.docid: return {'error': 'App not found (check region)'}
        
        title = doc.title
        vc = doc.details.appDetails.versionCode
        vs = doc.details.appDetails.versionString
        
        # Check compatibility/restrictions
        if vc == 0: 
            return {'error': 'App incompatible with device profile or region restricted'}

    except Exception as e:
        return {'error': f'Details error: {str(e)}'}

    # PURCHASE
    try:
        requests.post(PURCHASE_URL, headers={**headers, 'Content-Type': 'application/x-www-form-urlencoded'}, 
                     data=f'doc={pkg}&ot=1&vc={vc}', timeout=30, verify=False)
    except: pass

    # DELIVERY
    try:
        resp = requests.get(f'{DELIVERY_URL}?doc={pkg}&ot=1&vc={vc}', headers=headers, timeout=30, verify=False)
        wrapper = googleplay_pb2.ResponseWrapper()
        wrapper.ParseFromString(resp.content)
        data = wrapper.payload.deliveryResponse.appDeliveryData
        
        if not data.downloadUrl:
            return {'error': 'No download URL (App may be paid or restricted)'}
            
        return {
            'docid': pkg,
            'title': title,
            'versionCode': vc,
            'versionString': vs,
            'downloadUrl': data.downloadUrl,
            'downloadSize': data.downloadSize,
            'cookies': [{'name': c.name, 'value': c.value} for c in data.downloadAuthCookie],
            'splits': [{'name': s.name or f'split{i}', 'downloadUrl': s.downloadUrl} for i, s in enumerate(data.split) if s.downloadUrl],
            'filename': f'{pkg}-{vc}.apk'
        }
    except Exception as e:
        return {'error': f'Delivery error: {str(e)}'}

# --- ROUTES ---

@app.route('/')
def index():
    return send_file('index.html')

@app.route('/api/search')
def search():
    query = request.args.get('q', '')
    if not query: return jsonify({'error': 'Query required'}), 400
    
    # Simple web scraping search (less sensitive to auth than API)
    try:
        html = SCRAPER.get(f'https://play.google.com/store/search?q={query}&c=apps&hl=he', timeout=10).text
        results = []
        seen = set()
        
        # Regex to find apps
        matches = re.findall(r'\[\["(com\.[a-zA-Z0-9_.]+)",7\].*?\]\,"([^"]+)"', html)
        for pkg, title in matches:
            if pkg not in seen and len(results) < 5:
                seen.add(pkg)
                results.append({'package': pkg, 'title': title})
        
        if not results:
            # Fallback regex
            matches = re.findall(r'href="/store/apps/details\?id=([^"]+)"[^>]*><div[^>]*>([^<]+)</div>', html)
            for pkg, title in matches:
                if pkg not in seen and len(results) < 5:
                    seen.add(pkg)
                    results.append({'package': pkg, 'title': title})

        return jsonify({'results': results})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/info/<path:pkg>')
def info(pkg):
    try:
        resp = SCRAPER.get(f'https://play.google.com/store/apps/details?id={pkg}&hl=he', timeout=30)
        if resp.status_code == 404: return jsonify({'error': 'App not found'}), 404
        
        title = re.search(r'<h1[^>]*>([^<]+)</h1>', resp.text).group(1)
        dev = re.search(r'<div[^>]*class="Vbfug "[^>]*><span[^>]*>([^<]+)</span>', resp.text)
        developer = dev.group(1) if dev else "Unknown"
        
        return jsonify({'package': pkg, 'title': title, 'developer': developer})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/download-info-stream/<path:pkg>')
def download_info_stream(pkg):
    import time
    arch = request.args.get('arch', 'arm64-v8a')
    region = request.args.get('region', DEFAULT_REGION)
    
    if arch not in SUPPORTED_ARCHS: arch = 'arm64-v8a'
    if region not in REGIONS: region = DEFAULT_REGION

    device_config = get_device_config(arch, region)

    def generate():
        attempt = 0
        cached = get_cached_auth(arch)
        
        # Try cached first
        if cached:
            yield f"data: {json.dumps({'type': 'progress', 'attempt': 0, 'message': f'Trying cached token ({region})...'})}\n\n"
            info = get_download_info(pkg, cached, region)
            if 'error' not in info:
                yield f"data: {json.dumps({'type': 'success', **info, 'attempt': 0})}\n\n"
                return
            yield f"data: {json.dumps({'type': 'progress', 'attempt': 0, 'message': 'Cached token failed (Region mismatch?), getting new...'})}\n\n"

        # Try new tokens
        while True:
            attempt += 1
            yield f"data: {json.dumps({'type': 'progress', 'attempt': attempt, 'message': f'Getting token #{attempt} for {region}...'})}\n\n"
            
            try:
                resp = create_scraper_no_verify().post(DISPENSER_URL, json=device_config, headers={'Content-Type': 'application/json'}, timeout=30)
                if not resp.ok:
                    time.sleep(1)
                    continue
                
                auth = resp.json()
                yield f"data: {json.dumps({'type': 'progress', 'attempt': attempt, 'message': f'Token #{attempt} - checking app...'})}\n\n"
                
                info = get_download_info(pkg, auth, region)
                if 'error' in info:
                    logger.warning(f"Attempt {attempt} failed: {info['error']}")
                    yield f"data: {json.dumps({'type': 'progress', 'attempt': attempt, 'message': f'Error: {info["error"]}'})}\n\n"
                    time.sleep(0.5)
                    continue
                
                save_cached_auth(auth, arch)
                yield f"data: {json.dumps({'type': 'success', **info, 'attempt': attempt})}\n\n"
                return

            except Exception as e:
                yield f"data: {json.dumps({'type': 'progress', 'attempt': attempt, 'message': f'Error: {str(e)[:50]}'})}\n\n"
                time.sleep(1)

    return Response(generate(), mimetype='text/event-stream', headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})

# TEMP STORAGE
import uuid
TEMP_APKS = {}

@app.route('/api/download-merged-stream/<path:pkg>')
def download_merged_stream(pkg):
    import time
    arch = request.args.get('arch', 'arm64-v8a')
    region = request.args.get('region', DEFAULT_REGION)
    if arch not in SUPPORTED_ARCHS: arch = 'arm64-v8a'
    if region not in REGIONS: region = DEFAULT_REGION

    def generate():
        yield f"data: {json.dumps({'type': 'progress', 'step': 'auth', 'message': 'Authenticating...'})}\n\n"
        
        # Auth Logic (simplified vs info stream)
        auth = get_cached_auth(arch)
        info = get_download_info(pkg, auth, region) if auth else {'error': 'No token'}
        
        if 'error' in info:
            # Get fresh token
            device_config = get_device_config(arch, region)
            for attempt in range(10):
                try:
                    r = create_scraper_no_verify().post(DISPENSER_URL, json=device_config, headers={'Content-Type': 'application/json'}, timeout=30)
                    if r.ok:
                        auth = r.json()
                        info = get_download_info(pkg, auth, region)
                        if 'error' not in info:
                            save_cached_auth(auth, arch)
                            break
                except: pass
                time.sleep(1)

        if 'error' in info:
            yield f"data: {json.dumps({'type': 'error', 'message': f'Failed to get info: {info["error"]}'})}\n\n"
            return

        # Download
        splits = info.get('splits', [])
        total = 1 + len(splits)
        cookies = '; '.join([f"{c['name']}={c['value']}" for c in info.get('cookies', [])])
        headers = {'Cookie': cookies} if cookies else {}

        try:
            yield f"data: {json.dumps({'type': 'progress', 'step': 'download', 'message': 'Downloading Base...', 'current': 1, 'total': total})}\n\n"
            base_apk = requests.get(info['downloadUrl'], headers=headers, timeout=120, verify=False).content
            
            if not splits:
                fid = str(uuid.uuid4())
                TEMP_APKS[fid] = {'data': base_apk, 'filename': info['filename']}
                yield f"data: {json.dumps({'type': 'success', 'download_id': fid, 'filename': info['filename'], 'original': True})}\n\n"
                return

            split_data = []
            for i, split in enumerate(splits):
                yield f"data: {json.dumps({'type': 'progress', 'step': 'download', 'message': f'Downloading {split["name"]}...', 'current': i+2, 'total': total})}\n\n"
                split_content = requests.get(split['downloadUrl'], headers=headers, timeout=120, verify=False).content
                split_data.append((split['name'], split_content))

            yield f"data: {json.dumps({'type': 'progress', 'step': 'merge', 'message': 'Merging APKs...'})}\n\n"
            merged = merge_apks(base_apk, split_data)
            
            yield f"data: {json.dumps({'type': 'progress', 'step': 'sign', 'message': 'Signing APK...'})}\n\n"
            signed = sign_apk(merged)

            fid = str(uuid.uuid4())
            TEMP_APKS[fid] = {'data': signed, 'filename': f"{pkg}-{info['versionCode']}-merged.apk"}
            yield f"data: {json.dumps({'type': 'success', 'download_id': fid, 'filename': TEMP_APKS[fid]['filename']})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return Response(generate(), mimetype='text/event-stream', headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})

@app.route('/api/download-temp/<fid>')
def download_temp(fid):
    if fid not in TEMP_APKS: return jsonify({'error': 'Expired'}), 404
    d = TEMP_APKS.pop(fid)
    return Response(d['data'], content_type='application/vnd.android.package-archive', 
                   headers={'Content-Disposition': f'attachment; filename="{d["filename"]}"'})

if __name__ == '__main__':
    print(f'Starting GPlay Downloader (Region: {DEFAULT_REGION}, Device: S23/J7)')
    app.run(host='0.0.0.0', port=5000, debug=True)