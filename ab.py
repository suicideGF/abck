"""
ABCK Token Generator - Headless Railway Edition with Flask
"""

import os, sys, time, random, subprocess, threading, shutil, re, gc, platform, io, warnings, logging
from datetime import datetime
from flask import Flask, jsonify, request

app = Flask(__name__)

_generation_thread = None
_generation_running = False
_generation_stats = {"generated": 0, "total": 0, "status": "idle"}

os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
os.environ['TF_ENABLE_ONEDNN_OPTS'] = '0'
os.environ['WDM_LOG_LEVEL'] = '0'
os.environ['WDM_PRINT_FIRST_LINE'] = 'False'

warnings.filterwarnings('ignore')
logging.getLogger('selenium').setLevel(logging.CRITICAL)
logging.getLogger('urllib3').setLevel(logging.CRITICAL)

class _FilteredStderr(io.TextIOBase):
    DROP_PATTERNS = (
        "DevTools listening on",
        "GetGpuDriverOverlayInfo",
        "registration_request.cc",
        "TensorFlow Lite XNNPACK delegate",
    )

    def __init__(self, wrapped):
        self._wrapped = wrapped
        self._buf = ""

    def write(self, s):
        try:
            self._buf += s
            while '\n' in self._buf:
                line, self._buf = self._buf.split('\n', 1)
                if any(p in line for p in self.DROP_PATTERNS):
                    continue
                self._wrapped.write(line + '\n')
            return len(s)
        except Exception:
            return 0

    def flush(self):
        try:
            if self._buf:
                line = self._buf
                self._buf = ""
                if not any(p in line for p in self.DROP_PATTERNS):
                    self._wrapped.write(line)
            self._wrapped.flush()
        except Exception:
            pass

if not isinstance(sys.stderr, _FilteredStderr):
    sys.stderr = _FilteredStderr(sys.stderr)

def install_dependencies():
    dependencies = [
        "selenium",
        "requests",
        "webdriver-manager",
    ]
    missing = []
    for dep in dependencies:
        try:
            __import__(dep.replace('-', '_'))
        except ImportError:
            missing.append(dep)

    if missing:
        subprocess.check_call([sys.executable, "-m", "pip", "install"] + missing)

try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.action_chains import ActionChains
    from selenium.common.exceptions import (
        TimeoutException, NoSuchElementException,
        WebDriverException, StaleElementReferenceException
    )
    from webdriver_manager.chrome import ChromeDriverManager
    import requests
except ImportError:
    install_dependencies()

try:
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
except Exception:
    pass

IS_LINUX = platform.system() == 'Linux'
IS_WINDOWS = platform.system() == 'Windows'

# Device identification for spoofing
_DEVICE_IDS = [
    'and_cd9e459ea708a948d5c2f5a6ca8838cf648efdbc9a8c3ce703fa556d-34a4-4cde-a061-34938d08a26e',
    'and_cd9e459ea708a948d5c2f5a6ca8838cfb0128abe9641e3b40eb5c04c-8454-4afa-9cce-6214563d4100',
    'and_cd9e459ea708a948d5c2f5a6ca8838cffe70db6eb86cdceea5a6fff7-4ae8-4b70-94ba-9d1a3b0e19fa',
    'and_cd9e459ea708a948d5c2f5a6ca8838cf4504f1fc6e0437de4e9e5d3a-714d-4c20-9779-f5041dac458d',
    'and_cd9e459ea708a948d5c2f5a6ca8838cf0ab2a698aa9e3fc1acec02f5-e7b1-47a8-b2b3-70a8142bf069',
]

_ANDROID_DEVICES = [
    ("SM-S928B",  "AP3A.241005.015"),  ("SM-S926B",  "AP2A.240905.003"),
    ("SM-S918B",  "UP1A.231005.007"),  ("SM-S911B",  "UP1A.231005.007"),
    ("SM-S906B",  "SP1A.210812.016"),  ("SM-S901B",  "SP1A.210812.016"),
    ("SM-G991B",  "UP1A.231005.007"),  ("SM-A546B",  "UP1A.231005.007"),
    ("SM-A156B",  "AP2A.240805.005"),  ("SM-A536B",  "SP1A.210812.016"),
    ("SM-A346B",  "TP1A.220624.014"),  ("SM-A245F",  "TP1A.220624.014"),
    ("SM-A235F",  "TP1A.220624.014"),  ("SM-A135F",  "TP1A.220624.014"),
    ("Pixel 9 Pro",  "AP4A.250205.002"), ("Pixel 8",   "AP2A.240905.003"),
    ("Pixel 7a",     "UP1A.231005.007"), ("Pixel 7",   "TQ3A.230901.001"),
    ("Pixel 6a",     "TP1A.220905.004"), ("Pixel 5",   "RD1A.200810.022"),
    ("Pixel 4",      "PQ3A.190801.002"),
    ("23127PN0CG",  "AP2A.240905.003"),  ("23049PCD8G", "UKQ1.230804.001"),
    ("2312DRA50G",  "UKQ1.230804.001"),  ("23021RAAEG", "AQ3A.240829.003"),
    ("2201116SG",   "UP1A.231005.007"),  ("22041219PG", "AP1A.240505.005"),
    ("22021211RG",  "TP1A.220624.014"),  ("2211133G",   "UP1A.231005.007"),
    ("21091116AI",  "TKQ1.221114.001"),  ("M2102J20SG", "RKQ1.211001.001"),
    ("M2101K6G",    "AP1A.240405.002"),  ("23053RN02A", "UKQ1.230804.001"),
    ("22120RN86G",  "TKQ1.221114.001"),  ("21121119SG", "TKQ1.221114.001"),
    ("220333QAG",   "TKQ1.221114.001"),
    ("CPH2609",  "TP1A.220624.014"),  ("CPH2591",  "AP2A.240805.005"),
    ("CPH2551",  "TP1A.220624.014"),  ("CPH2385",  "SP1A.210812.016"),
    ("CPH2269",  "RP1A.200720.011"),  ("V2307",    "TP1A.220624.014"),
    ("V2254A",   "UP1A.231005.007"),  ("V2219",    "SP1A.210812.016"),
    ("V2109",    "RP1A.200720.011"),  ("V2038",    "RP1A.200720.011"),
    ("RMX3771",  "AP1A.240405.002"),  ("RMX3686",  "TP1A.220624.014"),
    ("RMX3521",  "SP1A.210812.016"),  ("RMX3393",  "SP1A.210812.016"),
    ("RMX3031",  "RP1A.200720.011"),  ("RMX2195",  "RP1A.200720.011"),
    ("CPH2449",  "TP1A.220624.014"),
    ("LE2125",   "AP1A.240505.005"),  ("LE2115",   "SP1A.210812.016"),
    ("IN2025",   "UP1A.231005.007"),  ("IN2013",   "RP1A.200720.011"),
    ("KB2003",   "AP2A.240805.005"),
    ("POCO X5 Pro",  "TKQ1.221114.001"), ("POCO F4",      "TKQ1.221114.001"),
    ("POCO M4 Pro",  "SP1A.210812.016"), ("POCO X4 GT",   "TP1A.220624.014"),
    ("moto g84 5G",  "UKQ1.230917.001"), ("moto g72",     "T2RLS33.69-23-6"),
    ("moto e32",     "SRPWS31.Q3-46-39"),("XT2153-1",     "RPBS31.Q3-46-37"),
    ("Lenovo TB-9707F", "AP3A.240905.015.A2"), ("Lenovo K13 Note", "RP1A.200720.011"),
    ("Nokia G60",  "TP1A.220624.014"),  ("Nokia X30",  "TP1A.220624.014"),
    ("Nokia C32",  "TP1A.220624.014"),
    ("X6833B",    "TP1A.220624.014"),  ("X6515",    "SP1A.210812.016"),
    ("X669C",     "RP1A.200720.011"),
    ("TECNO KI7",   "TP1A.220624.014"), ("TECNO LG7n",  "TP1A.220624.014"),
    ("XQ-BE52",   "TP1A.220624.014"),  ("XQ-DC54",  "UP1A.231005.007"),
    ("ASUS_AI2205",  "TKQ1.221114.001"), ("ASUS_I006D",   "SP1A.210812.016"),
    ("ZTE Blade A73 5G", "SP1A.210812.016"), ("nubia Z50S Pro", "TP1A.220624.014"),
    ("ELS-NX9",   "HUAWEIELS-NX9"),    ("MAR-LX1B",  "HUAWEIMAR-LX1B"),
    ("VOG-L29",   "HUAWEIVOG-L29"),
]

_CHROME_VERSIONS = [
    "130.0.6723.86",  "131.0.6778.104", "132.0.6834.110",
    "133.0.6917.92",  "134.0.6998.85",  "135.0.7049.100",
    "136.0.7103.60",  "137.0.7151.78",  "138.0.7204.100",
    "139.0.7258.60",  "140.0.7294.92",  "141.0.7328.86",
    "142.0.7381.100", "143.0.7440.50",  "144.0.7559.59",
]

_ANDROID_VERSIONS = [11, 12, 13, 14, 15]

TARGET_URL             = "https://mtacc.mobilelegends.com"
ABCK_FILE              = os.path.join(os.path.dirname(os.path.abspath(__file__)), "abck.txt")
SERVER_HOST            = "abck-production.up.railway.app"
SERVER_PORT            = "443"
SERVER_URL             = f"https://{SERVER_HOST}"
SERVER_SAVE_ENDPOINT   = f"{SERVER_URL}/api/save-token"
MAX_THREADS            = 2
NUM_BROWSERS           = 2
MAX_TOKENS_PER_BROWSER = 15
MAX_CONSECUTIVE_FAILS  = 5
SOLVE_TIMEOUT          = 45
CHECK_INTERVAL         = 0.12
DELAY_BETWEEN_TOKENS   = (0.3, 0.8)
DELAY_BROWSER_RELAUNCH = (1.0, 2.0)
DEFAULT_TOKEN_COUNT    = 50
MAX_TOKENS_IN_MEMORY   = 5000
CLEANUP_INTERVAL       = 100
SAVE_TO_FILE           = False
WIN_W, WIN_H           = 1280, 720

_print_lock = threading.Lock()
_file_lock  = threading.Lock()

def cprint(msg):
    with _print_lock:
        print(msg)

def ts():
    return datetime.now().strftime("%H:%M:%S")

def log_info(idx, msg):
    cprint(f"[{ts()}] [B{idx+1}] › {msg}")

def log_status(idx, attempt, gen, fcount, remaining, slot):
    cprint(f"[{ts()}] [B{idx+1}] #{attempt} ↑{gen} ◉{fcount} ◎{remaining} [{slot}/{MAX_TOKENS_PER_BROWSER}]")

def log_solving(idx, elapsed):
    cprint(f"[{ts()}] [B{idx+1}] Bypass Akamai... {elapsed}s")

def log_success(idx, num, tokens, extra=""):
    tok_preview = tokens[:40]
    cprint(f"[{ts()}] [B{idx+1}] ✔ #{num} {tok_preview}... {extra}")

def log_fail(idx, fail, maxf):
    cprint(f"[{ts()}] [B{idx+1}] ✗ FAIL [{fail}/{maxf}]")

def log_warn(idx, msg):
    cprint(f"[{ts()}] [B{idx+1}] ⚠ {msg}")

def log_relaunch(idx, reason):
    cprint(f"[{ts()}] [B{idx+1}] ↻ RELAUNCH {reason}")

def load_existing_tokens():
    if not SAVE_TO_FILE or not os.path.exists(ABCK_FILE):
        return set()
    try:
        with open(ABCK_FILE, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        recent = lines[-MAX_TOKENS_IN_MEMORY:] if len(lines) > MAX_TOKENS_IN_MEMORY else lines
        return {line.strip() for line in recent if line.strip()}
    except Exception:
        return set()

def save_tokens(tokens):
    if not SAVE_TO_FILE:
        return
    with _file_lock:
        with open(ABCK_FILE, 'a', encoding='utf-8') as f:
            f.write(tokens + '\n')

def send_tokens_to_server(tokens, use_server=False):
    if not use_server:
        return None
    try:
        payload = {"token": tokens}
        r = requests.post(SERVER_SAVE_ENDPOINT, json=payload, timeout=5, verify=False)
        if r.status_code in [200, 201]:
            try:
                resp = r.json()
                return resp.get('id') or resp.get('status') or "ok"
            except Exception:
                return "ok"
        else:
            return None
    except:
        return None

_ram_tokens_count = 0
_ram_tokens_count_lock = threading.Lock()

def count_tokens():
    with _ram_tokens_count_lock:
        return _ram_tokens_count

def increment_tokens_count():
    global _ram_tokens_count
    with _ram_tokens_count_lock:
        _ram_tokens_count += 1
        return _ram_tokens_count

_chrome_version_cache = None

def get_chrome_version():
    global _chrome_version_cache
    if _chrome_version_cache is not None:
        return _chrome_version_cache

    if IS_LINUX:
        for cmd in ['google-chrome --version', 'google-chrome-stable --version',
                     'chromium-browser --version', 'chromium --version']:
            try:
                result = subprocess.run(
                    cmd.split(), capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0:
                    match = re.search(r'(\d+)\.', result.stdout)
                    if match:
                        _chrome_version_cache = int(match.group(1))
                        return _chrome_version_cache
            except Exception:
                pass
    else:
        try:
            result = subprocess.run(
                ['reg', 'query', r'HKEY_CURRENT_USER\Software\Google\Chrome\BLBeacon', '/v', 'version'],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if 'version' in line.lower():
                        _chrome_version_cache = int(line.strip().split()[-1].split('.')[0])
                        return _chrome_version_cache
        except Exception:
            pass
        try:
            for base in [
                os.path.join(os.environ.get('PROGRAMFILES', ''), 'Google', 'Chrome', 'Application'),
                os.path.join(os.environ.get('PROGRAMFILES(X86)', ''), 'Google', 'Chrome', 'Application'),
                os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Google', 'Chrome', 'Application'),
            ]:
                if os.path.isdir(base):
                    for name in os.listdir(base):
                        if name[0].isdigit() and '.' in name:
                            _chrome_version_cache = int(name.split('.')[0])
                            return _chrome_version_cache
        except Exception:
            pass
    return None

def cleanup_chrome_garbage():
    base = _get_temp_base()
    cleaned = 0
    prefixes = ('scoped_dir', '.com.google', 'chrome_', 'Crashpad',
                'uc_', '.org.chromium', 'tmp', 'gpu-process')
    try:
        for name in os.listdir(base):
            if any(name.startswith(p) for p in prefixes):
                path = os.path.join(base, name)
                try:
                    if os.path.isdir(path):
                        shutil.rmtree(path, ignore_errors=True)
                    else:
                        os.remove(path)
                    cleaned += 1
                except Exception:
                    pass
    except Exception:
        pass
    gc.collect()
    return cleaned

def kill_chrome():
    if IS_LINUX:
        for proc in ['chrome', 'chromedriver', 'google-chrome', 'chromium']:
            try:
                subprocess.run(['pkill', '-f', proc], capture_output=True, timeout=5)
            except Exception:
                pass
    else:
        for proc in ['chrome.exe', 'chromedriver.exe']:
            try:
                subprocess.run(['taskkill', '/F', '/IM', proc], capture_output=True, timeout=5)
            except Exception:
                pass

def _get_temp_base():
    return os.environ.get('TEMP', os.environ.get('TMP', '/tmp'))

def _cleanup_old_temp_dirs():
    base = _get_temp_base()
    try:
        for name in os.listdir(base):
            if name.startswith('uc_b'):
                path = os.path.join(base, name)
                try:
                    shutil.rmtree(path, ignore_errors=True)
                except Exception:
                    pass
    except Exception:
        pass

def create_driver(chrome_ver=None, browser_index=0):
    for attempt in range(3):
        try:
            options = Options()
            for arg in [
                "--no-first-run",
                "--no-service-autorun",
                "--no-default-browser-check",
                "--disable-blink-features=AutomationControlled",
                "--disable-popup-blocking",
                "--disable-infobars",
                "--disable-gpu",
                "--disable-default-apps",
                "--no-sandbox",
                "--single-process",
                "--disable-logging",
                "--disable-crash-reporter",
                "--disable-component-update",
                "--disable-sync",
                "--disable-translate",
                "--log-level=3",
                "--disable-domain-reliability",
                "--disable-client-side-phishing-detection",
                "--safebrowsing-disable-auto-update",
                "--headless=new",
                f"--window-size={WIN_W},{WIN_H}",
            ]:
                options.add_argument(arg)

            fp = generate_mobile_fingerprint()
            options.add_argument(f"--user-agent={fp['user_agent']}")

            prefs = {}
            options.add_experimental_option("prefs", prefs)
            options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
            options.add_experimental_option("useAutomationExtension", False)

            temp_dir = os.path.join(_get_temp_base(), f'uc_b{browser_index}')
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)
            os.makedirs(temp_dir, exist_ok=True)
            options.add_argument(f"--user-data-dir={temp_dir}")

            binary = None
            try:
                bins = os.environ.get('CHROME_BINARIES')
                if bins:
                    parts = [p.strip() for p in bins.split(',') if p.strip()]
                    if parts:
                        binary = parts[browser_index % len(parts)]
                if not binary:
                    binary = os.environ.get('CHROME_BINARY')
                
                if not binary:
                    if IS_WINDOWS:
                        windows_paths = [
                            os.path.join(os.environ.get('PROGRAMFILES', 'C:\\Program Files'), 'Google', 'Chrome', 'Application', 'chrome.exe'),
                            os.path.join(os.environ.get('PROGRAMFILES(X86)', 'C:\\Program Files (x86)'), 'Google', 'Chrome', 'Application', 'chrome.exe'),
                            os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Google', 'Chrome', 'Application', 'chrome.exe'),
                            'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
                            'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
                        ]
                        for chrome_exe in windows_paths:
                            if chrome_exe and os.path.isfile(chrome_exe):
                                binary = chrome_exe
                                break
                    else:
                        for path in ['/usr/bin/google-chrome-stable', '/usr/bin/google-chrome',
                                     '/usr/bin/chromium-browser', '/usr/bin/chromium',
                                     '/snap/bin/chromium']:
                            if os.path.isfile(path):
                                binary = path
                                break
                
                if binary and os.path.isfile(binary):
                    options.binary_location = binary
            except Exception as e:
                log_warn(browser_index, f"Binary detection error: {str(e)[:50]}")

            driver = webdriver.Chrome(options=options, service=webdriver.chrome.service.Service('/usr/bin/chromedriver'))
            driver.set_page_load_timeout(12)
            driver.set_script_timeout(3)
            try:
                driver.set_window_size(WIN_W, WIN_H)
                driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
                driver.execute_script("Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]})")
                driver.execute_script("Object.defineProperty(navigator, 'languages', {get: () => ['en-US']})")
                inject_fingerprint(driver, {
                    "platform": fp["platform"],
                    "hardware_concurrency": fp["hardware_concurrency"],
                    "device_memory": fp["device_memory"],
                    "dpr": random.choice([3, 3.5]),
                    "webgl_vendor": fp["webgl_vendor"],
                    "webgl_renderer": fp["webgl_renderer"],
                })
            except Exception:
                pass
            return driver
        except Exception as e:
            import traceback
            err_msg = str(e)
            log_warn(browser_index, f"Launch failed ({attempt+1}/3): {err_msg[:150]}")
            if attempt == 2:
                log_warn(browser_index, f"Full error: {err_msg}")
                log_warn(browser_index, f"Traceback: {traceback.format_exc()[:200]}")
            time.sleep(0.5)
    return None

def generate_mobile_fingerprint() -> dict:
    device_model, android_build = random.choice(_ANDROID_DEVICES)
    android_version = random.choice(_ANDROID_VERSIONS)
    chrome_version = random.choice(_CHROME_VERSIONS)
    screen_res = random.choice([
        {"w": 1080, "h": 2400, "dpr": 3},
        {"w": 1080, "h": 2340, "dpr": 3},
        {"w": 1440, "h": 3120, "dpr": 3.5},
    ])
    
    user_agent = (
        f"Mozilla/5.0 (Linux; Android {android_version}; {device_model}) "
        f"AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{chrome_version} Mobile Safari/537.36"
    )
    
    webgl_renderers = [
        "ANGLE (ARM, Mali-G710 MC10, OpenGL ES 3.2)",
        "ANGLE (ARM, Mali-G78 MP20, OpenGL ES 3.2)",
        "ANGLE (Qualcomm, Adreno (TM) 730, OpenGL ES 3.2)",
        "ANGLE (Qualcomm, Adreno (TM) 8 Gen 2, OpenGL ES 3.2)",
    ]
    
    return {
        "screen": f"{screen_res['w']}x{screen_res['h']}x24",
        "user_agent": user_agent,
        "language": "en-US,en;q=0.9",
        "webgl_vendor": "Google Inc. (ARM)",
        "webgl_renderer": random.choice(webgl_renderers),
        "hardware_concurrency": random.choice([8, 12]),
        "device_memory": random.choice([6, 8, 12]),
        "platform": "Android",
        "device_model": device_model,
        "android_version": android_version,
        "android_build": android_build,
    }

def inject_fingerprint(driver, fingerprint_data):
    try:
        nav = {
            "platform": fingerprint_data.get("platform", "Android"),
            "hardwareConcurrency": fingerprint_data.get("hardware_concurrency", 8),
            "deviceMemory": fingerprint_data.get("device_memory", 8),
            "maxTouchPoints": 5,
        }

        script = f"""
        Object.defineProperty(navigator, 'platform', {{ get: () => '{nav['platform']}' }});
        Object.defineProperty(navigator, 'hardwareConcurrency', {{ get: () => {nav['hardwareConcurrency']} }});
        Object.defineProperty(navigator, 'deviceMemory', {{ get: () => {nav['deviceMemory']} }});
        Object.defineProperty(navigator, 'maxTouchPoints', {{ get: () => {nav['maxTouchPoints']} }});

        Object.defineProperty(window, 'devicePixelRatio', {{ get: () => {fingerprint_data.get('dpr', 3)} }});

        const getParameter = WebGLRenderingContext.prototype.getParameter;
        WebGLRenderingContext.prototype.getParameter = function(parameter) {{
            if (parameter === 37445) return '{fingerprint_data.get('webgl_vendor', 'Google Inc. (ARM)')}';
            if (parameter === 37446) return '{fingerprint_data.get('webgl_renderer', 'ANGLE (ARM, Mali-G710 MC10, OpenGL ES 3.2)')}';
            return getParameter.call(this, parameter);
        }};
        """
        driver.execute_script(script)
    except Exception:
        pass

def safe_quit(driver, browser_index=None):
    if driver:
        try:
            driver.quit()
        except Exception:
            pass
        if browser_index is not None:
            temp_dir = os.path.join(_get_temp_base(), f'uc_b{browser_index}')
            shutil.rmtree(temp_dir, ignore_errors=True)
        cleanup_chrome_garbage()

def _bezier_points(x1, y1, x2, y2, steps=12):
    dist = ((x2-x1)**2 + (y2-y1)**2) ** 0.5
    ctrl_scale = max(60, min(150, int(dist * 0.4)))
    
    cx1 = x1 + random.randint(-ctrl_scale, ctrl_scale)
    cy1 = y1 + random.randint(-int(ctrl_scale*0.75), int(ctrl_scale*0.75))
    cx2 = x2 + random.randint(-ctrl_scale, ctrl_scale)
    cy2 = y2 + random.randint(-int(ctrl_scale*0.75), int(ctrl_scale*0.75))
    
    points = []
    for i in range(steps + 1):
        t = i / steps
        u = 1 - t
        px = int(u**3*x1 + 3*u**2*t*cx1 + 3*u*t**2*cx2 + t**3*x2)
        py = int(u**3*y1 + 3*u**2*t*cy1 + 3*u*t**2*cy2 + t**3*y2)
        px = max(5, min(px, WIN_W - 5))
        py = max(5, min(py, WIN_H - 5))
        points.append((px, py))
    return points

def cdp_mouse_move(driver):
    try:
        x1, y1 = random.randint(100, WIN_W-200), random.randint(80, WIN_H-200)
        x2, y2 = random.randint(100, WIN_W-100), random.randint(80, WIN_H-100)
        steps = random.randint(12, 28)
        points = _bezier_points(x1, y1, x2, y2, steps=steps)
        
        for i, (px, py) in enumerate(points):
            driver.execute_cdp_cmd('Input.dispatchMouseEvent', {
                'type': 'mouseMoved', 'x': px, 'y': py
            })
            speed_var = random.uniform(0.003, 0.035)
            if random.random() < 0.15:
                time.sleep(random.uniform(0.08, 0.15))
            else:
                time.sleep(speed_var)
        
        if random.random() < 0.4:
            cx, cy = points[-1]
            driver.execute_cdp_cmd('Input.dispatchMouseEvent', {
                'type': 'mousePressed', 'x': cx, 'y': cy,
                'button': 'left', 'clickCount': 1
            })
            time.sleep(random.uniform(0.04, 0.12))
            driver.execute_cdp_cmd('Input.dispatchMouseEvent', {
                'type': 'mouseReleased', 'x': cx, 'y': cy,
                'button': 'left', 'clickCount': 1
            })
            time.sleep(random.uniform(0.02, 0.06))
    except Exception:
        pass

def cdp_scroll(driver):
    try:
        x = random.randint(200, WIN_W-200)
        y = random.randint(200, WIN_H-200)
        
        scroll_patterns = [
            [-120, -80, -40],
            [80, 120, 160],
            [-200, -100, 50],
            [100, 200],
        ]
        deltas = random.choice(scroll_patterns)
        
        for delta_y in deltas:
            driver.execute_cdp_cmd('Input.dispatchMouseEvent', {
                'type': 'mouseWheel', 'x': x, 'y': y,
                'deltaX': 0, 'deltaY': delta_y
            })
            time.sleep(random.uniform(0.05, 0.15))
    except Exception:
        pass

def cdp_keyboard(driver):
    try:
        driver.execute_script("""
            (function() {
                var events = ['mouseover', 'focus', 'mouseenter'];
                var el = document.elementFromPoint(
                    Math.random() * window.innerWidth,
                    Math.random() * window.innerHeight
                );
                if (el) {
                    events.forEach(function(evt) {
                        el.dispatchEvent(new Event(evt, {bubbles: true}));
                    });
                }
                document.dispatchEvent(new Event('mousemove', {bubbles: true}));
            })();
        """)
        time.sleep(random.uniform(0.03, 0.08))
    except Exception:
        pass

def inject_sensor_triggers(driver):
    try:
        driver.execute_script("""
            (function() {
                var randomX = function() { return Math.random() * window.innerWidth; };
                var randomY = function() { return Math.random() * window.innerHeight; };
                
                ['pointerdown', 'pointermove', 'pointerup', 'pointerover'].forEach(function(evt) {
                    document.dispatchEvent(new PointerEvent(evt, {
                        pointerId: Math.floor(Math.random()*10) + 1,
                        bubbles: true,
                        cancelable: true,
                        clientX: randomX(),
                        clientY: randomY(),
                        isPrimary: true
                    }));
                });
                
                ['mousedown', 'mousemove', 'mouseup', 'mouseover', 'mouseenter'].forEach(function(evt) {
                    document.dispatchEvent(new MouseEvent(evt, {
                        bubbles: true,
                        cancelable: true,
                        clientX: randomX(),
                        clientY: randomY(),
                        buttons: evt.includes('down') ? 1 : 0
                    }));
                });
                
                ['touchstart', 'touchmove', 'touchend'].forEach(function(evt) {
                    var touch = new Touch({
                        identifier: Date.now(),
                        target: document.body,
                        clientX: randomX(),
                        clientY: randomY()
                    });
                    document.dispatchEvent(new TouchEvent(evt, {
                        bubbles: true,
                        cancelable: true,
                        touches: [touch],
                        targetTouches: [touch],
                        changedTouches: [touch]
                    }));
                });
                
                ['keydown', 'keyup'].forEach(function(evt) {
                    var keys = ['a', 'e', 's', 't', 'r'];
                    var key = keys[Math.floor(Math.random() * keys.length)];
                    document.dispatchEvent(new KeyboardEvent(evt, {
                        key: key,
                        code: 'Key' + key.toUpperCase(),
                        keyCode: key.charCodeAt(0),
                        bubbles: true,
                        cancelable: true
                    }));
                });
                
                window.dispatchEvent(new Event('scroll', {bubbles: true}));
                window.dispatchEvent(new WheelEvent('wheel', {bubbles: true, deltaY: Math.random() * 200 - 100}));
                
                document.dispatchEvent(new Event('visibilitychange', {bubbles: true}));
                window.dispatchEvent(new Event('focus', {bubbles: true}));
                document.dispatchEvent(new Event('focusin', {bubbles: true}));
                
                window.dispatchEvent(new Event('devicemotion', {bubbles: true}));
                window.dispatchEvent(new Event('orientationchange', {bubbles: true}));
            })();
        """)
        time.sleep(random.uniform(0.05, 0.12))
    except Exception:
        pass

def get_solved_abck(cookies):
    for c in cookies:
        if c.get('name') == '_abck' and '~0~' in c.get('value', ''):
            return c['value']
    return None

def wait_for_solve(driver, timeout=SOLVE_TIMEOUT, browser_index=0):
    start    = time.time()
    dots     = 0
    last_log = -10

    try:
        time.sleep(random.uniform(1.0, 2.0))
        inject_sensor_triggers(driver)
        time.sleep(random.uniform(0.5, 1.0))
        cdp_mouse_move(driver)
    except Exception:
        return None

    while time.time() - start < timeout:
        try:
            _ = driver.current_url
            cookies = driver.get_cookies()
        except Exception:
            return None
        solved = get_solved_abck(cookies)
        if solved:
            return solved

        action = dots % 5
        try:
            if action == 0:
                cdp_mouse_move(driver)
            elif action == 1:
                cdp_scroll(driver)
            elif action == 2:
                cdp_keyboard(driver)
            elif action == 3:
                cdp_mouse_move(driver)
                inject_sensor_triggers(driver)
        except Exception:
            pass

        dots   += 1
        elapsed = int(time.time() - start)
        if elapsed - last_log >= 8:
            try:
                log_solving(browser_index, elapsed)
            except Exception:
                pass
            last_log = elapsed
        time.sleep(CHECK_INTERVAL)
    return None

class SharedState:
    def __init__(self, target_count, loop_forever):
        self.target_count = target_count
        self.loop_forever = loop_forever
        self.generated    = 0
        self.existing     = load_existing_tokens()
        self.lock         = threading.Lock()
        self.stop_event   = threading.Event()

    def should_continue(self):
        if self.stop_event.is_set():
            return False
        if self.loop_forever:
            return True
        with self.lock:
            return self.generated < self.target_count

    def add_tokens(self, tokens):
        with self.lock:
            if tokens in self.existing:
                return False
            self.existing.add(tokens)
            if len(self.existing) > MAX_TOKENS_IN_MEMORY:
                excess = len(self.existing) - MAX_TOKENS_IN_MEMORY
                for _ in range(excess):
                    self.existing.pop()
            self.generated += 1
            if self.generated % CLEANUP_INTERVAL == 0:
                cleanup_chrome_garbage()
            return True

def browser_worker(idx, shared, use_server, chrome_ver):
    driver = None
    consec_fails = 0
    tok_this_br  = 0
    attempt      = 0

    try:
        while shared.should_continue():
            attempt += 1
            
            driver_alive = False
            if driver is not None:
                try:
                    driver.current_url
                    driver_alive = True
                except Exception:
                    driver_alive = False
            
            need_new = (
                driver is None or
                not driver_alive or
                consec_fails >= MAX_CONSECUTIVE_FAILS or
                tok_this_br  >= MAX_TOKENS_PER_BROWSER
            )

            if need_new:
                if driver is not None:
                    reason = (f"{consec_fails}×"
                              if consec_fails >= MAX_CONSECUTIVE_FAILS
                              else f"{tok_this_br} tokens")
                    log_relaunch(idx, reason)
                    safe_quit(driver, idx)
                    driver = None
                    time.sleep(random.uniform(*DELAY_BROWSER_RELAUNCH))

                log_info(idx, "Opening browser…")
                driver = create_driver(chrome_ver=chrome_ver, browser_index=idx)
                if not driver:
                    log_warn(idx, "Browser failed! Retry in 3s…")
                    time.sleep(3)
                    continue

                consec_fails = 0
                tok_this_br  = 0
                page_load_ok = False
                try:
                    log_info(idx, "loading")
                    driver.get(TARGET_URL)
                    log_info(idx, "page loaded")
                    time.sleep(random.uniform(2.0, 3.5))
                    cdp_mouse_move(driver)
                    time.sleep(random.uniform(0.3, 0.6))
                    inject_sensor_triggers(driver)
                    page_load_ok = True
                except Exception as e:
                    log_warn(idx, f"Page load error: {str(e)[:60]}")
                    safe_quit(driver, idx)
                    driver = None
                    continue
                
                if not page_load_ok:
                    continue
            else:
                try:
                    driver.delete_cookie('_abck')
                    if random.random() < 0.3:
                        driver.refresh()
                    else:
                        driver.get(TARGET_URL)
                    time.sleep(random.uniform(1.5, 2.5))
                    cdp_mouse_move(driver)
                    inject_sensor_triggers(driver)
                except Exception:
                    safe_quit(driver, idx)
                    driver = None
                    continue

            with shared.lock:
                gen_now = shared.generated
            remaining  = "∞" if shared.loop_forever else str(shared.target_count - gen_now)
            file_count = count_tokens()
            try:
                log_status(idx, attempt, gen_now, file_count, remaining, tok_this_br)
            except Exception:
                pass

            token = wait_for_solve(driver, timeout=SOLVE_TIMEOUT, browser_index=idx)

            if token:
                if shared.add_tokens(token):
                    save_tokens(token)
                    increment_tokens_count()
                    server_id  = send_tokens_to_server(token, use_server)
                    tok_this_br  += 1
                    consec_fails  = 0
                    with shared.lock:
                        g = shared.generated
                    extra = f"  [srv:{server_id}]" if use_server and server_id else ""
                    try:
                        log_success(idx, g, token, extra)
                    except Exception:
                        pass
                    time.sleep(random.uniform(*DELAY_BETWEEN_TOKENS))
                else:
                    log_warn(idx, "Duplicate token, skip")
                    try: driver.delete_all_cookies()
                    except Exception: pass
            else:
                consec_fails += 1
                try:
                    log_fail(idx, consec_fails, MAX_CONSECUTIVE_FAILS)
                except Exception:
                    pass
                try:
                    driver.delete_all_cookies()
                except Exception:
                    safe_quit(driver, idx)
                    driver = None

            if shared.should_continue():
                time.sleep(random.uniform(*DELAY_BETWEEN_TOKENS))

    except Exception as e:
        log_warn(idx, f"Error: {e}")
    finally:
        safe_quit(driver, idx)
        log_info(idx, "Worker finished.")

def generate(target_count, loop_forever=False, use_server=False):
    shared  = SharedState(target_count, loop_forever)
    threads = []

    chrome_ver = get_chrome_version()
    for i in range(NUM_BROWSERS):
        t = threading.Thread(
            target=browser_worker,
            args=(i, shared, use_server, chrome_ver),
            daemon=True, name=f"B{i+1}"
        )
        threads.append(t)
        t.start()
        if i < NUM_BROWSERS - 1:
            time.sleep(1.5)

    try:
        while any(t.is_alive() for t in threads):
            if not loop_forever and not shared.should_continue():
                shared.stop_event.set()
            time.sleep(1)
    except KeyboardInterrupt:
        cprint("\n⚠  Stopped by user (Ctrl+C)")
        shared.stop_event.set()

    for t in threads:
        try:
            t.join(timeout=10)
        except KeyboardInterrupt:
            pass

    return shared.generated

def _generation_worker(threads, loop_forever, use_server):
    global _generation_running, _generation_stats
    try:
        _generation_stats["status"] = "running"
        start = time.time()
        generated = generate(50, loop_forever, use_server)
        elapsed = time.time() - start
        total = count_tokens()
        
        _generation_stats["generated"] = generated
        _generation_stats["total"] = total
        _generation_stats["status"] = "completed"
        _generation_stats["elapsed"] = int(elapsed)
        
        cprint(f"[{ts()}] [INFO] Generation complete: {generated} tokens in {int(elapsed)}s")
    except Exception as e:
        _generation_stats["status"] = "error"
        _generation_stats["error"] = str(e)
        cprint(f"[{ts()}] [ERROR] {e}")
    finally:
        _generation_running = False
        kill_chrome()
        cleanup_chrome_garbage()

@app.route('/', methods=['GET'])
def status():
    return jsonify({
        "status": _generation_stats["status"],
        "generated": _generation_stats["generated"],
        "total": _generation_stats["total"],
        "elapsed": _generation_stats.get("elapsed", 0),
        "error": _generation_stats.get("error")
    })

@app.route('/start', methods=['POST'])
def start_generation():
    global _generation_thread, _generation_running, NUM_BROWSERS
    
    if _generation_running:
        return jsonify({"error": "Generation already running"}), 400
    
    data = request.json or {}
    threads = min(data.get("threads", 1), MAX_THREADS)
    use_server = data.get("use_server", True)
    
    NUM_BROWSERS = threads
    _generation_stats["status"] = "starting"
    _generation_stats["generated"] = 0
    _generation_stats["total"] = count_tokens()
    _generation_running = True
    
    _cleanup_old_temp_dirs()
    
    _generation_thread = threading.Thread(
        target=_generation_worker,
        args=(threads, True, use_server),
        daemon=False
    )
    _generation_thread.start()
    
    return jsonify({
        "message": "Generation started",
        "threads": threads,
        "use_server": use_server
    })

@app.route('/stop', methods=['POST'])
def stop_generation():
    global _generation_running
    _generation_running = False
    kill_chrome()
    return jsonify({"message": "Stop signal sent"})

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"ok": True})

def main():
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)

if __name__ == "__main__":
    main()