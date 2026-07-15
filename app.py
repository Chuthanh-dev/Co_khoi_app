import os
import json
import base64
import time
import requests
import webbrowser
import subprocess
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory
from playwright.sync_api import sync_playwright
import sys
from PIL import Image
import qrcode
from io import BytesIO

# Helper function to generate and overlay QR code on generated image
def overlay_qr_code(main_image_bytes, qr_data, position="center", size_percent=25, x_percent=None, y_percent=None):
    try:
        # Load main image
        main_img = Image.open(BytesIO(main_image_bytes))
        main_w, main_h = main_img.size
        
        # Generate QR code with High error correction (H)
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_H,
            box_size=10,
            border=1
        )
        qr.add_data(qr_data)
        qr.make(fit=True)
        qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGBA")
        
        # Resize QR based on size_percent
        qr_size = int(min(main_w, main_h) * (size_percent / 100.0))
        qr_img = qr_img.resize((qr_size, qr_size), Image.Resampling.LANCZOS)
        
        # Calculate coordinate offsets
        if x_percent is not None and y_percent is not None:
            # Explicit coordinate offsets
            x = int(main_w * (x_percent / 100.0))
            y = int(main_h * (y_percent / 100.0))
        else:
            # Fallback to position names
            if position == "center":
                x = (main_w - qr_size) // 2
                y = (main_h - qr_size) // 2
            elif position == "bottom_right":
                x = main_w - qr_size - int(main_w * 0.05)
                y = main_h - qr_size - int(main_h * 0.05)
            elif position == "bottom_left":
                x = int(main_w * 0.05)
                y = main_h - qr_size - int(main_h * 0.05)
            elif position == "top_right":
                x = main_w - qr_size - int(main_w * 0.05)
                y = int(main_h * 0.05)
            elif position == "top_left":
                x = int(main_w * 0.05)
                y = int(main_h * 0.05)
            else:
                x = (main_w - qr_size) // 2
                y = (main_h - qr_size) // 2
                
        # Make sure boundaries are safe
        x = max(0, min(x, main_w - qr_size))
        y = max(0, min(y, main_h - qr_size))
            
        # Paste QR code onto main image using alpha channel mask
        if main_img.mode != "RGBA":
            main_img = main_img.convert("RGBA")
            
        combined = Image.new("RGBA", main_img.size)
        combined.paste(main_img, (0, 0))
        combined.paste(qr_img, (x, y), qr_img)
        
        # Save combined image back to bytes
        combined = combined.convert("RGB")
        out_io = BytesIO()
        combined.save(out_io, format="JPEG", quality=95)
        return out_io.getvalue()
    except Exception as e:
        print(f"Error overlaying QR code: {e}")
        return main_image_bytes

# Override built-in print to safely handle Windows console encoding errors
_original_print = print
def print(*args, **kwargs):
    kwargs['flush'] = True
    try:
        _original_print(*args, **kwargs)
    except UnicodeEncodeError:
        new_args = []
        encoding = getattr(sys.stdout, 'encoding', 'utf-8') or 'utf-8'
        for arg in args:
            if isinstance(arg, str):
                new_args.append(arg.encode(encoding, errors='replace').decode(encoding))
            else:
                new_args.append(arg)
        try:
            _original_print(*new_args, **kwargs)
        except Exception:
            new_args = [str(arg).encode('ascii', errors='replace').decode('ascii') for arg in args]
            _original_print(*new_args, **kwargs)

app = Flask(__name__)

# Default config path
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')

DEFAULT_CONFIG = {
    "api_key": "",
    "api_type": "official",
    "custom_url": "",
    "custom_headers": "{\n  \"Content-Type\": \"application/json\"\n}",
    "custom_body": "{\n  \"prompt\": \"{prompt}\"\n}",
    "save_dir": os.path.join(os.path.dirname(os.path.abspath(__file__)), 'generated_images'),
    "model": "imagen-3.0-generate-002",
    "aspect_ratio": "1:1",
    "quality": "standard",
    "zalo_sync_enabled": False,
    "zalo_contact_name": "Cô Trinh _Khôi",
    "zalo_auto_generate": False
}


def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
                # Ensure all default keys exist
                for k, v in DEFAULT_CONFIG.items():
                    if k not in config:
                        config[k] = v
                return config
        except Exception:
            return DEFAULT_CONFIG
    return DEFAULT_CONFIG

def save_config(config):
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"Error saving config: {e}")
        return False

import threading
import re

# Zalo Integration Global Variables
zalo_monitor_active = False
zalo_monitor_thread = None
zalo_login_status = "Disconnected"  # "Disconnected", "Waiting for login", "Active", "Error"
latest_zalo_message = None  # Dict: {"prompt": "...", "qr_link": "...", "processed": False, "timestamp": "..."}

playwright_manager = None
global_browser = None

def get_shared_browser():
    global playwright_manager, global_browser
    if global_browser is None:
        try:
            from playwright.sync_api import sync_playwright
            if playwright_manager is None:
                playwright_manager = sync_playwright().start()
            global_browser = playwright_manager.chromium.connect_over_cdp("http://127.0.0.1:9222")
            print("[Playwright] Connected to Chrome over CDP on port 9222 successfully.")
        except Exception as e:
            print(f"[Playwright] Error connecting to Chrome: {e}")
            if playwright_manager:
                try:
                    playwright_manager.stop()
                except Exception:
                    pass
                playwright_manager = None
            global_browser = None
    else:
        try:
            # Check connection
            _ = global_browser.contexts
        except Exception:
            print("[Playwright] Connection lost, reconnecting...")
            global_browser = None
            if playwright_manager:
                try:
                    playwright_manager.stop()
                except Exception:
                    pass
                playwright_manager = None
            return get_shared_browser()
            
    return global_browser


def clean_zalo_message(text):
    if not text:
        return ""
    # Remove introductory phrases (case-insensitive, with variations)
    patterns = [
        r"(?i)ba\s+làm\s+(giùm|giúp)\s+cô\s+mã\s+này\.?",
        r"(?i)ba\s+làm\s+(giùm|giúp)\s+cô\.?",
        r"(?i)ba\s+làm\s+(giùm|giúp)\.?\s*"
    ]
    cleaned = text
    for pattern in patterns:
        cleaned = re.sub(pattern, "", cleaned)
    
    # Strip URL from the prompt text
    url_pattern = r"https?://[^\s]+"
    cleaned = re.sub(url_pattern, "", cleaned)
    
    # Clean leading/trailing spaces and punctuation
    cleaned = cleaned.strip(" .,;-\n")
    return cleaned

def extract_zalo_url(text):
    if not text:
        return ""
    url_pattern = r"(https?://[^\s]+)"
    match = re.search(url_pattern, text)
    if match:
        return match.group(1).strip()
    return ""

def zalo_monitor_loop():
    global zalo_monitor_active, latest_zalo_message, zalo_login_status
    print("Zalo monitor background loop started.")
    last_processed_text = None
    
    while zalo_monitor_active:
        try:
            config = load_config()
            contact_name = config.get("zalo_contact_name", "Cô Trinh _Khôi")
            
            with sync_playwright() as p:
                try:
                    browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
                except Exception:
                    zalo_login_status = "Disconnected"
                    time.sleep(5)
                    continue
                
                context = browser.contexts[0]
                zalo_page = None
                
                for page in context.pages:
                    if "chat.zalo.me" in page.url:
                        zalo_page = page
                        break
                
                if not zalo_page:
                    try:
                        # Create Zalo page in background
                        zalo_page = context.new_page()
                        zalo_page.goto("https://chat.zalo.me")
                    except Exception as e:
                        print(f"[Zalo] Lỗi mở trang Zalo Web: {e}")
                        zalo_login_status = "Error"
                        time.sleep(5)
                        continue
                
                # Check for login redirection
                if "id.zalo.me" in zalo_page.url:
                    zalo_login_status = "Waiting for login"
                    time.sleep(5)
                    continue
                
                zalo_login_status = "Active"
                
                # Find contact in sidebar and click
                try:
                    contact_locator = zalo_page.locator(f'text="{contact_name}"').first
                    if contact_locator.is_visible():
                        contact_locator.click()
                    else:
                        # Use search box
                        search_selectors = [
                            'input[placeholder*="Tìm kiếm"]',
                            'input[placeholder*="Search"]',
                            '#contact-search-input'
                        ]
                        search_el = None
                        for sel in search_selectors:
                            try:
                                el = zalo_page.locator(sel).first
                                if el.is_visible():
                                    search_el = el
                                    break
                            except Exception:
                                pass
                        
                        if search_el:
                            search_el.click()
                            search_el.fill("")
                            search_el.type(contact_name)
                            time.sleep(1.5)
                            first_result = zalo_page.locator(f'div.search-result-item:has-text("{contact_name}")').first
                            if first_result.is_visible():
                                first_result.click()
                            else:
                                zalo_page.locator(f'text="{contact_name}"').first.click()
                                
                    time.sleep(1.0)
                    
                    # Read the most recent incoming message containing a link or text via JS evaluation
                    js_get_last_url_message = """
                    () => {
                        const items = Array.from(document.querySelectorAll('.chat-item'))
                            .filter(item => !item.classList.contains('me'));
                        
                        items.reverse(); // check from newest to oldest
                        
                        for (const item of items) {
                            const anchor = item.querySelector('a');
                            const textWrapper = item.querySelector('.link-message__text-wrapper, .text-message__container');
                            const textEl = item.querySelector('.text, .message-content-render');
                            
                            let text = "";
                            if (textWrapper) {
                                text = textWrapper.innerText;
                            } else if (textEl) {
                                text = textEl.innerText;
                            }
                            
                            if (anchor || text.includes('http://') || text.includes('https://')) {
                                let url = anchor ? anchor.href : '';
                                if (!url) {
                                    const match = text.match(/https?:\\/\\/[^\\s]+/);
                                    url = match ? match[0] : '';
                                }
                                return {
                                    found: true,
                                    text: text,
                                    url: url
                                };
                            }
                        }
                        return { found: false, text: null, url: null };
                    }
                    """
                    
                    res = zalo_page.evaluate(js_get_last_url_message)
                    if res and res.get('found'):
                        raw_text = res.get('text', '').strip()
                        raw_url = res.get('url', '').strip()
                        
                        # We use raw_text + raw_url as unique key to avoid reprocessing
                        msg_unique_key = f"{raw_text}||{raw_url}"
                        
                        if msg_unique_key != last_processed_text:
                            prompt = clean_zalo_message(raw_text)
                            
                            latest_zalo_message = {
                                "prompt": prompt,
                                "qr_link": raw_url,
                                "processed": False,
                                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            }
                            last_processed_text = msg_unique_key
                            print(f"[Zalo] Nhận tin nhắn mới - Prompt: '{prompt}', Link: '{raw_url}'")
                except Exception as e:
                    print(f"[Zalo] Lỗi đọc tin nhắn cuộc trò chuyện: {e}")
                    
            time.sleep(5)
        except Exception as e:
            print(f"[Zalo] Lỗi vòng lặp giám sát: {e}")
            time.sleep(5)
    print("Zalo monitor background loop stopped.")

def start_zalo_monitor():
    global zalo_monitor_active, zalo_monitor_thread
    if not zalo_monitor_active:
        zalo_monitor_active = True
        zalo_monitor_thread = threading.Thread(target=zalo_monitor_loop, daemon=True)
        zalo_monitor_thread.start()
        print("Zalo monitor started successfully.")

def stop_zalo_monitor():
    global zalo_monitor_active
    zalo_monitor_active = False
    print("Zalo monitor requested to stop.")

@app.route('/api/zalo/status', methods=['GET'])
def get_zalo_status():
    config = load_config()
    return jsonify({
        "status": "success",
        "active": zalo_monitor_active,
        "login_status": zalo_login_status,
        "contact_name": config.get("zalo_contact_name", "Cô Trinh _Khôi"),
        "auto_generate": config.get("zalo_auto_generate", False)
    })

@app.route('/api/zalo/toggle', methods=['POST'])
def toggle_zalo():
    data = request.json or {}
    active = data.get('active', False)
    contact_name = data.get('contact_name', 'Cô Trinh _Khôi').strip()
    auto_generate = data.get('auto_generate', False)
    
    config = load_config()
    config["zalo_contact_name"] = contact_name
    config["zalo_sync_enabled"] = active
    config["zalo_auto_generate"] = auto_generate
    save_config(config)
    
    if active:
        start_zalo_monitor()
    else:
        stop_zalo_monitor()
        
    return jsonify({
        "status": "success",
        "active": zalo_monitor_active,
        "login_status": zalo_login_status
    })

@app.route('/api/zalo/latest', methods=['GET'])
def get_latest_zalo_message():
    global latest_zalo_message
    if latest_zalo_message and not latest_zalo_message.get("processed", False):
        # We clone the message to set processed but keep a copy or mark it
        msg_copy = latest_zalo_message.copy()
        latest_zalo_message["processed"] = True
        return jsonify({
            "status": "success",
            "has_new": True,
            "message": msg_copy
        })
    return jsonify({
        "status": "success",
        "has_new": False
    })

chrome_process = None

def get_chrome_path():
    paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe")
    ]
    for path in paths:
        if os.path.exists(path):
            return path
    return None

def kill_automated_chrome():
    try:
        # Kill only Chrome processes running with our specific automation profile
        script = 'Get-WmiObject Win32_Process -Filter "name=\'chrome.exe\'" | Where-Object { $_.CommandLine -like "*chrome_profile*" } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }'
        subprocess.run(["powershell", "-Command", script], capture_output=True)
        print("Cleaned up orphaned automated Chrome instances.")
    except Exception as e:
        print(f"Error cleaning up automated Chrome: {e}")

def launch_chrome():
    global chrome_process
    chrome_path = get_chrome_path()
    if not chrome_path:
        raise Exception("Không tìm thấy Google Chrome cài đặt trên máy tính của bạn.")
        
    user_data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'chrome_profile')
    os.makedirs(user_data_dir, exist_ok=True)
    
    # Always clean up background automated processes first to ensure a new visible window opens
    kill_automated_chrome()
    time.sleep(1.0)
        
    cmd = [
        chrome_path,
        "--remote-debugging-port=9222",
        f"--user-data-dir={user_data_dir}",
        "https://gemini.google.com"
    ]
    print(f"Launching Chrome: {' '.join(cmd)}")
    chrome_process = subprocess.Popen(cmd)

def get_gemini_page():
    browser = get_shared_browser()
    if not browser:
        print("Chrome is not running, launching it...")
        launch_chrome()
        time.sleep(3.0)
        browser = get_shared_browser()
        if not browser:
            raise Exception("Không thể kết nối tới Google Chrome.")
            
    context = browser.contexts[0]
    for page in context.pages:
        if "gemini.google.com" in page.url:
            page.bring_to_front()
            return page, browser
            
    page = context.new_page()
    page.goto("https://gemini.google.com")
    page.bring_to_front()
    return page, browser

def get_history_file(save_dir):
    return os.path.join(save_dir, 'history.json')

def load_history(save_dir):
    history_file = get_history_file(save_dir)
    if os.path.exists(history_file):
        try:
            with open(history_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_history(save_dir, history):
    history_file = get_history_file(save_dir)
    try:
        os.makedirs(save_dir, exist_ok=True)
        with open(history_file, 'w', encoding='utf-8') as f:
            json.dump(history, f, indent=4, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"Error saving history: {e}")
        return False

@app.route('/')
def index():
    return send_from_directory('templates', 'index.html')

@app.route('/static/<path:path>')
def send_static(path):
    return send_from_directory('static', path)

@app.route('/images/<path:filename>')
def send_image(filename):
    config = load_config()
    save_dir = config.get('save_dir', DEFAULT_CONFIG['save_dir'])
    return send_from_directory(save_dir, filename)

@app.route('/api/config', methods=['GET', 'POST'])
def handle_config():
    if request.method == 'POST':
        new_config = request.json
        current_config = load_config()
        for k in DEFAULT_CONFIG.keys():
            if k in new_config:
                current_config[k] = new_config[k]
        
        # Resolve full path for save_dir if it's relative
        save_dir = current_config['save_dir']
        if not os.path.isabs(save_dir):
            save_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), save_dir))
        current_config['save_dir'] = save_dir
        
        if save_config(current_config):
            # Create folder if it doesn't exist
            os.makedirs(save_dir, exist_ok=True)
            return jsonify({"status": "success", "config": current_config})
        else:
            return jsonify({"status": "error", "message": "Failed to save config"}), 500
    
    return jsonify(load_config())

@app.route('/api/open-folder', methods=['POST'])
def open_folder():
    config = load_config()
    save_dir = config.get('save_dir', DEFAULT_CONFIG['save_dir'])
    os.makedirs(save_dir, exist_ok=True)
    try:
        os.startfile(save_dir)
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/launch-browser', methods=['POST'])
def handle_launch_browser():
    try:
        launch_chrome()
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/history', methods=['GET'])
def get_history():
    config = load_config()
    save_dir = config.get('save_dir', DEFAULT_CONFIG['save_dir'])
    return jsonify(load_history(save_dir))

@app.route('/api/generate', methods=['POST'])
def generate_image():
    data = request.json
    prompt = data.get('prompt')
    if not prompt:
        return jsonify({"status": "error", "message": "Prompt is required"}), 400
    
    config = load_config()
    
    # Override config with request params if provided
    api_key = data.get('api_key', config.get('api_key'))
    api_type = data.get('api_type', config.get('api_type'))
    custom_url = data.get('custom_url', config.get('custom_url'))
    custom_headers_str = data.get('custom_headers', config.get('custom_headers'))
    custom_body_str = data.get('custom_body', config.get('custom_body'))
    save_dir = data.get('save_dir', config.get('save_dir'))
    model = data.get('model', config.get('model', 'imagen-3.0-generate-002'))
    aspect_ratio = data.get('aspect_ratio', config.get('aspect_ratio', '1:1'))
    quality = data.get('quality', config.get('quality', 'standard'))

    # Suffix prompt to guide Gemini's generation structure
    qr_link = data.get('qr_link', '').strip()
    qr_position = data.get('qr_position', 'center')
    qr_size = data.get('qr_size', 25)
    
    try:
        qr_size = int(qr_size)
    except Exception:
        qr_size = 25

    # Clean and modify prompt if QR code is enabled
    cleaned_prompt = prompt
    qr_link = data.get('qr_link', '').strip()
    qr_position = data.get('qr_position', 'center')
    qr_size = data.get('qr_size', 25)
    
    try:
        qr_size = int(qr_size)
    except Exception:
        qr_size = 25

    if qr_link:
        # Remove phrases instructing Gemini to draw a QR code to avoid pixel clutter in the background
        remove_phrases = [
            "bên trong là là mã QR",
            "bên trong là mã QR",
            "bên trong là mã qr",
            "ở giữa là mã QR",
            "ở giữa là mã qr",
            "chứa mã QR",
            "chứa mã qr",
            "có mã QR",
            "có mã qr",
            "inside is a QR code",
            "inside is a qr code",
            "containing a QR code",
            "containing a qr code",
            "with a QR code",
            "with a qr code"
        ]
        for phrase in remove_phrases:
            cleaned_prompt = cleaned_prompt.replace(phrase, "")
            # Check common variations
            cleaned_prompt = cleaned_prompt.replace(phrase.upper(), "")
            cleaned_prompt = cleaned_prompt.replace(phrase.capitalize(), "")

    modified_prompt = cleaned_prompt
    if qr_link:
        pos_vi = "chính giữa bức ảnh (Center)"
        pos_en = "exact center of the image (Center)"
        if qr_position == "bottom_right":
            pos_vi = "góc dưới bên phải bức ảnh (Bottom Right)"
            pos_en = "bottom right corner of the image (Bottom Right)"
        elif qr_position == "bottom_left":
            pos_vi = "góc dưới bên trái bức ảnh (Bottom Left)"
            pos_en = "bottom left corner of the image (Bottom Left)"
        elif qr_position == "top_right":
            pos_vi = "góc trên bên phải bức ảnh (Top Right)"
            pos_en = "top right corner of the image (Top Right)"
        elif qr_position == "top_left":
            pos_vi = "góc trên bên trái bức ảnh (Top Left)"
            pos_en = "top left corner of the image (Top Left)"
            
        suffix = (
            f" . QUY ĐỊNH BẮT BUỘC VỀ BỐ CỤC ẢNH: Bạn phải thiết kế một khung hình vuông màu trắng trơn hoàn toàn trống, phẳng, "
            f"tỉ lệ đúng 1:1 (khung hình vuông cân đối, tuyệt đối không bị kéo dãn hay bóp méo thành hình chữ nhật) nằm ở {pos_vi}. "
            f"Khung hình vuông trống này có kích thước rộng chiếm khoảng {qr_size}% bức ảnh. "
            f"CHÚ Ý CỰC KỲ QUAN TRỌNG: KHÔNG ĐƯỢC vẽ bất kỳ nét ô vuông đen trắng giả lập mã QR nào vào trong khung này. "
            f"Khung này phải để trống, màu trắng trơn hoàn toàn, không có nhân vật, hoa lá, chữ viết hay chi tiết nào đè lên. "
            f" (CRITICAL LAYOUT REQUIREMENT: You must design a clean, flat, non-distorted solid white square placeholder frame (perfect 1:1 aspect ratio, NOT stretched or rectangular) at the {pos_en}. "
            f"This square frame must occupy exactly {qr_size}% of the image. "
            f"DO NOT DRAW any black and white QR pixel patterns or simulated QR patterns inside this frame. "
            f"It must remain a completely blank, solid white square area with no overlapping text, characters, or illustrations, so a real QR code can be pasted cleanly on top without background clutter)."
        )
        modified_prompt = cleaned_prompt + suffix

    # Append aspect ratio instructions for browser automation mode
    if api_type == 'browser' and aspect_ratio != '1:1':
        ratio_desc_vi = ""
        ratio_desc_en = ""
        if aspect_ratio == '16:9':
            ratio_desc_vi = "nằm ngang, khổ landscape rộng, tỉ lệ khung hình 16:9"
            ratio_desc_en = "landscape format, widescreen 16:9 aspect ratio"
        elif aspect_ratio == '9:16':
            ratio_desc_vi = "đứng dọc, khổ portrait dài, tỉ lệ khung hình 9:16"
            ratio_desc_en = "portrait format, vertical 9:16 aspect ratio"
        elif aspect_ratio == '4:3':
            ratio_desc_vi = "nằm ngang, tỉ lệ 4:3"
            ratio_desc_en = "landscape format, 4:3 aspect ratio"
        elif aspect_ratio == '3:4':
            ratio_desc_vi = "đứng dọc, tỉ lệ 3:4"
            ratio_desc_en = "portrait format, 3:4 aspect ratio"
            
        if ratio_desc_vi:
            aspect_suffix = f" . BẮT BUỘC VỀ DẠNG ẢNH: Thiết kế bức ảnh ở định dạng {ratio_desc_vi}. (IMAGE LAYOUT REQUIREMENT: Must design and output the image in {ratio_desc_en})."
            modified_prompt = modified_prompt + aspect_suffix

    os.makedirs(save_dir, exist_ok=True)

    if not api_key and api_type == 'official':
        return jsonify({"status": "error", "message": "Google Gemini API Key is required"}), 400

    try:
        img_bytes = None
        content_type = "image/jpeg"
        
        if api_type == 'browser':
            print(f"Browser automation: starting generation for prompt: '{modified_prompt}'...")
            
            with sync_playwright() as p:
                page, browser = get_gemini_page(p)
                
                # Verify page loaded
                if "gemini.google.com" not in page.url:
                    page.goto("https://gemini.google.com")
                    page.wait_for_load_state("networkidle")
                
                # Check for input box. We will try several common selectors
                selectors = [
                    'div.ql-editor[contenteditable="true"]',
                    'div[contenteditable="true"]',
                    'textarea[placeholder*="Nhập"]',
                    'textarea[placeholder*="Ask"]',
                    'rich-textarea textarea',
                    'rich-textarea'
                ]
                
                input_el = None
                for selector in selectors:
                    try:
                        page.wait_for_selector(selector, timeout=3000)
                        input_el = page.locator(selector).first
                        if input_el.is_visible():
                            break
                    except Exception:
                        continue
                        
                if not input_el:
                    return jsonify({"status": "error", "message": "Không tìm thấy khung nhập liệu của Gemini. Hãy chắc chắn trình duyệt đã mở và bạn đã đăng nhập tài khoản Google."}), 400
                
                # Count current googleusercontent images before we send prompt
                old_images = page.evaluate("""() => {
                    return Array.from(document.querySelectorAll("img"))
                        .filter(img => {
                            const src = img.src || "";
                            if (!src.includes("googleusercontent")) return false;
                            if (src.includes("/a/") || src.includes("default-user")) return false;
                            return true;
                        })
                        .map(img => img.src);
                }""")
                print(f"Current count of googleusercontent images: {len(old_images)}")
                
                # Fill prompt and focus
                input_el.click()
                input_el.focus()
                
                # Clear content
                try:
                    input_el.evaluate("el => el.innerHTML = ''")
                except Exception:
                    pass
                
                # Select all and delete (alternative clear)
                page.keyboard.press("Control+A")
                page.keyboard.press("Backspace")
                
                # Insert prompt text via hardware keyboard simulation
                page.keyboard.insert_text(modified_prompt)
                
                # Dispatch DOM/React input events to force Quill/React state sync
                try:
                    input_el.evaluate("""(el) => {
                        el.dispatchEvent(new Event('input', { bubbles: true }));
                        el.dispatchEvent(new Event('change', { bubbles: true }));
                    }""")
                except Exception as e:
                    print(f"Error dispatching input events: {e}")
                    
                time.sleep(1.0)
                
                # Find send button
                send_selectors = [
                    'button[aria-label*="Gửi"]',
                    'button[aria-label*="Send"]',
                    'button.send-button',
                    'div.send-button-container button',
                    'button[class*="send"]'
                ]
                
                send_btn = None
                for selector in send_selectors:
                    try:
                        btn = page.locator(selector).first
                        if btn.is_visible() and btn.is_enabled():
                            send_btn = btn
                            break
                    except Exception:
                        continue
                        
                # Dynamic fallback search over all buttons
                if not send_btn:
                    try:
                        buttons = page.locator('button').all()
                        for btn in buttons:
                            label = btn.get_attribute('aria-label') or ''
                            title = btn.get_attribute('title') or ''
                            html = btn.inner_html() or ''
                            if any(w in label.lower() or w in title.lower() for w in ['send', 'gửi', 'submit']) or 'send' in html.lower() or 'paper-plane' in html.lower():
                                if btn.is_visible() and btn.is_enabled():
                                    send_btn = btn
                                    break
                    except Exception as e:
                        print(f"Error scanning all buttons: {e}")
                        
                if send_btn:
                    print(f"Clicking Send button (enabled: {send_btn.is_enabled()})...")
                    try:
                        send_btn.click(timeout=3000)
                    except Exception as e:
                        print(f"Click failed, trying keyboard Enter: {e}")
                        page.keyboard.press("Enter")
                else:
                    print("Send button not found or disabled, trying keyboard Enter...")
                    page.keyboard.press("Enter")
                    
                # Wait for the image inside the latest response bubble
                print("Waiting for image in the latest response bubble...")
                timeout_sec = 80
                start_time = time.time()
                new_image_url = None
                
                # Count current message bubbles
                initial_bubble_count = page.evaluate("document.querySelectorAll('message-content, .message-content').length")
                print(f"Initial message bubble count: {initial_bubble_count}")
                
                while time.time() - start_time < timeout_sec:
                    try:
                        # Extract bubbles state
                        bubbles_info = page.evaluate("""() => {
                            const bubbles = document.querySelectorAll('message-content, .message-content');
                            if (bubbles.length === 0) return { count: 0, imgs: [], text: "" };
                            const lastBubble = bubbles[bubbles.length - 1];
                            const imgs = Array.from(lastBubble.querySelectorAll('img')).map(img => img.src).filter(Boolean);
                            return {
                                count: bubbles.length,
                                imgs: imgs,
                                text: lastBubble.innerText || ""
                            };
                        }""")
                        
                        if bubbles_info:
                            current_count = bubbles_info['count']
                            imgs = bubbles_info['imgs']
                            last_text = bubbles_info['text']
                            
                            # If there are images in the last bubble, and it's a new bubble or we are generating
                            if current_count > initial_bubble_count and imgs:
                                new_image_url = imgs[0]
                                break
                            elif current_count == initial_bubble_count and imgs:
                                # Fallback: image appeared in the last bubble
                                new_image_url = imgs[0]
                                break
                                
                            # Check if generation has finished
                            stop_btn_visible = False
                            try:
                                stop_btn = page.locator('button[aria-label*="Stop"], button[aria-label*="Dừng"], button:has-text("Stop"), button:has-text("Dừng")').first
                                if stop_btn.is_visible():
                                    stop_btn_visible = True
                            except Exception:
                                pass
                                
                            send_btn_active = False
                            if send_btn:
                                try:
                                    if send_btn.is_visible() and send_btn.is_enabled():
                                        send_btn_active = True
                                except Exception:
                                    pass
                                    
                            # If we are not generating anymore (after at least 8s of wait)
                            if time.time() - start_time > 8 and not stop_btn_visible and (send_btn_active or not send_btn):
                                # Response is complete, but no image!
                                if last_text:
                                    return jsonify({"status": "error", "message": f"Gemini trả về văn bản thay vì hình ảnh: {last_text}"}), 400
                                else:
                                    return jsonify({"status": "error", "message": "Gemini hoàn thành phản hồi nhưng không tạo ra hình ảnh nào."}), 400
                                
                    except Exception as e:
                        print(f"Error checking page state: {e}")
                    time.sleep(1.5)
                    
                if not new_image_url:
                    # Take a screenshot for debugging
                    screenshot_path = os.path.join(save_dir, "error_screenshot.png")
                    try:
                        page.screenshot(path=screenshot_path)
                        print(f"Saved debug screenshot to: {screenshot_path}")
                    except Exception as se:
                        print(f"Failed to take screenshot: {se}")
                    return jsonify({"status": "error", "message": "Đã gửi prompt nhưng quá thời gian chờ (80s) không thấy Gemini trả về hình ảnh mới. Đã chụp ảnh màn hình lỗi."}), 400
                    
                print(f"New image generated: {new_image_url}. Converting to Base64...")
                
                # Convert image to base64 using browser canvas and CORS anonymous bypass
                img_b64 = page.evaluate(f"""
                    async () => {{
                        return new Promise((resolve) => {{
                            const img = new Image();
                            img.crossOrigin = "anonymous";
                            img.src = "{new_image_url}";
                            img.onload = () => {{
                                try {{
                                    const canvas = document.createElement('canvas');
                                    canvas.width = img.naturalWidth;
                                    canvas.height = img.naturalHeight;
                                    const ctx = canvas.getContext('2d');
                                    ctx.drawImage(img, 0, 0);
                                    resolve(canvas.toDataURL('image/jpeg'));
                                }} catch (e) {{
                                    resolve("error:" + e.message);
                                }}
                            }};
                            img.onerror = () => {{
                                resolve("error:load_failed");
                            }};
                        }});
                    }}
                """)
                
                if not img_b64 or img_b64.startswith("error:") or ',' not in img_b64:
                    err_msg = img_b64.split(":", 1)[1] if (img_b64 and img_b64.startswith("error:")) else "Không thể trích xuất dữ liệu ảnh từ trình duyệt."
                    return jsonify({"status": "error", "message": f"Lỗi trích xuất ảnh: {err_msg}"}), 400
                    
                header, encoded = img_b64.split(",", 1)
                img_bytes = base64.b64decode(encoded)
                content_type = "image/jpeg"
                
        elif api_type == 'official':
            headers = {"Content-Type": "application/json"}
            
            # Google AI Studio / Gemini Image Models use generateContent
            if model.startswith('gemini-'):
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
                payload = {
                    "contents": [
                        {
                            "role": "user",
                            "parts": [
                                {
                                    "text": modified_prompt
                                }
                            ]
                        }
                    ],
                    "generationConfig": {
                        "responseModalities": ["IMAGE"]
                    }
                }
                
                print(f"Calling Google Gemini Image REST API: {url}...")
                response = requests.post(url, headers=headers, json=payload, timeout=90)
                
                if response.status_code != 200:
                    try:
                        err_msg = response.json().get('error', {}).get('message', response.text)
                    except Exception:
                        err_msg = response.text
                    return jsonify({"status": "error", "message": f"API Error ({response.status_code}): {err_msg}"}), 400
                    
                resp_data = response.json()
                candidates = resp_data.get('candidates', [])
                if not candidates:
                    return jsonify({"status": "error", "message": "No image candidates returned by model"}), 400
                    
                parts = candidates[0].get('content', {}).get('parts', [])
                img_b64 = None
                mime_type = "image/jpeg"
                
                for part in parts:
                    if 'inlineData' in part:
                        img_b64 = part['inlineData'].get('data')
                        mime_type = part['inlineData'].get('mimeType', 'image/jpeg')
                        break
                        
                if not img_b64:
                    text_msg = "".join([p.get('text', '') for p in parts])
                    return jsonify({"status": "error", "message": f"Could not find image output. Model text output: {text_msg}"}), 400
                    
                img_bytes = base64.b64decode(img_b64)
                content_type = mime_type
                
            else:
                # Imagen models use predict REST API
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:predict?key={api_key}"
                payload = {
                    "instances": [
                        {
                            "prompt": modified_prompt
                        }
                    ],
                    "parameters": {
                        "sampleCount": 1,
                        "aspectRatio": aspect_ratio
                    }
                }
                
                print(f"Calling Google Imagen REST API: {url}...")
                response = requests.post(url, headers=headers, json=payload, timeout=60)
                
                if response.status_code != 200:
                    try:
                        err_msg = response.json().get('error', {}).get('message', response.text)
                    except Exception:
                        err_msg = response.text
                    return jsonify({"status": "error", "message": f"API Error ({response.status_code}): {err_msg}"}), 400
                    
                resp_data = response.json()
                predictions = resp_data.get('predictions', [])
                if not predictions:
                    return jsonify({"status": "error", "message": "No predictions returned in the response"}), 400
                    
                img_b64 = predictions[0].get('bytesBase64Encoded')
                if not img_b64:
                    return jsonify({"status": "error", "message": "Image bytes missing in the prediction response"}), 400
                    
                img_bytes = base64.b64decode(img_b64)
                mime_type = predictions[0].get('mimeType', 'image/jpeg')
                content_type = mime_type
            
        else:
            # Custom/Third-party Endpoint
            if not custom_url:
                return jsonify({"status": "error", "message": "Custom Endpoint URL is required"}), 400
                
            # Parse custom headers
            try:
                headers = json.loads(custom_headers_str)
            except Exception as e:
                return jsonify({"status": "error", "message": f"Invalid Custom Headers JSON: {str(e)}"}), 400
                
            # Inject key in Authorization header if authorization token is provided
            if api_key:
                for k, v in headers.items():
                    if '{api_key}' in v:
                        headers[k] = v.replace('{api_key}', api_key)
                
            # Parse and resolve custom body
            body_template = custom_body_str
            # Simple template replacement
            body_template = body_template.replace('{prompt}', modified_prompt)
            body_template = body_template.replace('{aspect_ratio}', aspect_ratio)
            body_template = body_template.replace('{model}', model)
            
            try:
                payload = json.loads(body_template)
            except Exception as e:
                return jsonify({"status": "error", "message": f"Invalid Custom Body JSON after prompt replacement: {str(e)}"}), 400
            
            print(f"Calling Custom API: {custom_url}...")
            response = requests.post(custom_url, headers=headers, json=payload, timeout=90)
            
            if response.status_code not in (200, 201):
                return jsonify({"status": "error", "message": f"Custom API Error ({response.status_code}): {response.text}"}), 400
                
            # Try to handle response: It could be direct image bytes, a JSON with base64, or a JSON with an image URL
            resp_content_type = response.headers.get('Content-Type', '')
            
            if 'image/' in resp_content_type:
                # Direct image bytes response
                img_bytes = response.content
                content_type = resp_content_type
            else:
                # JSON response
                try:
                    resp_json = response.json()
                except Exception:
                    return jsonify({"status": "error", "message": "Custom API did not return image or valid JSON"}), 400
                
                # Check for common image keys: url, image, data, etc.
                img_url = None
                img_b64 = None
                
                # Dynamic search for image URL or base64 in JSON response
                def find_image_data(obj):
                    if isinstance(obj, str):
                        if obj.startswith('http://') or obj.startswith('https://'):
                            if any(ext in obj.lower() for ext in ['.jpg', '.jpeg', '.png', '.webp', 'images', 'storage']):
                                return 'url', obj
                        elif len(obj) > 1000 and (';base64,' in obj or obj.replace('\n', '').replace('\r', '').isalnum()):
                            b64_str = obj.split(';base64,')[-1]
                            return 'b64', b64_str
                    elif isinstance(obj, dict):
                        for k, v in obj.items():
                            res_type, res_val = find_image_data(v)
                            if res_type:
                                return res_type, res_val
                    elif isinstance(obj, list):
                        for item in obj:
                            res_type, res_val = find_image_data(item)
                            if res_type:
                                return res_type, res_val
                    return None, None
                
                res_type, res_val = find_image_data(resp_json)
                
                if res_type == 'url':
                    img_url = res_val
                elif res_type == 'b64':
                    img_b64 = res_val
                
                # Fallback check for common patterns
                if not img_url and not img_b64:
                    if 'output' in resp_json:
                        output = resp_json['output']
                        if isinstance(output, list) and len(output) > 0:
                            img_url = output[0]
                        elif isinstance(output, str):
                            img_url = output
                    elif 'images' in resp_json and isinstance(resp_json['images'], list) and len(resp_json['images']) > 0:
                        img_url = resp_json['images'][0].get('url') or resp_json['images'][0]
                    elif 'data' in resp_json and isinstance(resp_json['data'], dict):
                        img_url = resp_json['data'].get('url') or resp_json['data'].get('imageUrl')
                
                if img_url:
                    print(f"Downloading image from URL: {img_url}...")
                    img_resp = requests.get(img_url, timeout=30)
                    if img_resp.status_code == 200:
                        img_bytes = img_resp.content
                        content_type = img_resp.headers.get('Content-Type', 'image/jpeg')
                    else:
                        return jsonify({"status": "error", "message": f"Failed to download image from custom URL: {img_url}"}), 400
                elif img_b64:
                    img_bytes = base64.b64decode(img_b64)
                else:
                    return jsonify({"status": "error", "message": "Could not extract image URL or Base64 data from custom API response", "response": resp_json}), 400
        
        # Check image extension and paths
        ext = "jpg"
        if "png" in content_type:
            ext = "png"
        elif "webp" in content_type:
            ext = "webp"
            
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        clean_filename = f"banana_{timestamp}_clean.{ext}"
        clean_filepath = os.path.join(save_dir, clean_filename)
        
        # Always save the clean background image first
        with open(clean_filepath, "wb") as f:
            f.write(img_bytes)
            
        # Check if we need to overlay a real QR code
        qr_link = data.get('qr_link', '').strip()
        qr_x = data.get('qr_x')
        qr_y = data.get('qr_y')
        qr_size = data.get('qr_size', 43.0)
        
        # Convert values to float/int
        if qr_x is not None: qr_x = float(qr_x)
        if qr_y is not None: qr_y = float(qr_y)
        if qr_size is not None: qr_size = float(qr_size)
        
        # Calculate default centered percentages if coordinates not provided
        if qr_link and (qr_x is None or qr_y is None):
            qr_position = data.get('qr_position', 'center')
            if qr_position == "center":
                qr_x = 38.0
                qr_y = 28.5
            elif qr_position == "bottom_right":
                qr_x = 100 - qr_size - 5
                qr_y = 100 - qr_size - 5
            elif qr_position == "bottom_left":
                qr_x = 5
                qr_y = 100 - qr_size - 5
            elif qr_position == "top_right":
                qr_x = 100 - qr_size - 5
                qr_y = 5
            elif qr_position == "top_left":
                qr_x = 5
                qr_y = 5
            else:
                qr_x = 38.0
                qr_y = 28.5
                
        final_img_bytes = img_bytes
        if qr_link:
            print(f"Overlaying real QR code for link '{qr_link}' at coordinates ({qr_x}%, {qr_y}%) with size {qr_size}%...")
            final_img_bytes = overlay_qr_code(img_bytes, qr_link, position="center", size_percent=qr_size, x_percent=qr_x, y_percent=qr_y)

        filename = f"banana_{timestamp}.{ext}"
        filepath = os.path.join(save_dir, filename)
        
        with open(filepath, "wb") as f:
            f.write(final_img_bytes)
            
        # Update history
        history = load_history(save_dir)
        history_item = {
            "id": timestamp,
            "filename": filename,
            "prompt": prompt,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "model": model,
            "aspect_ratio": aspect_ratio,
            "api_type": api_type,
            "qr_link": qr_link,
            "qr_x": qr_x if qr_link else None,
            "qr_y": qr_y if qr_link else None,
            "qr_size": qr_size if qr_link else None
        }
        history.insert(0, history_item) # Add to the beginning
        save_history(save_dir, history)
        
        return jsonify({
            "status": "success",
            "image": {
                "filename": filename,
                "local_path": filepath,
                "url": f"/images/{filename}",
                "timestamp": history_item["timestamp"]
            },
            "qr": {
                "has_qr": bool(qr_link),
                "qr_link": qr_link,
                "qr_x": qr_x,
                "qr_y": qr_y,
                "qr_size": qr_size
            }
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/adjust-qr', methods=['POST'])
def adjust_qr():
    try:
        data = request.json or {}
        filename = data.get('filename')
        qr_link = data.get('qr_link', '').strip()
        qr_x = float(data.get('qr_x', 37.5))
        qr_y = float(data.get('qr_y', 37.5))
        qr_size = float(data.get('qr_size', 25))
        
        if not filename:
            return jsonify({"status": "error", "message": "Filename is required"}), 400
            
        config = load_config()
        save_dir = config.get('save_dir', DEFAULT_CONFIG['save_dir'])
        
        # Build paths
        filepath = os.path.join(save_dir, filename)
        
        # Determine format/extension
        base_name, ext = os.path.splitext(filename)
        # If the file name ends with _clean, use it directly
        if base_name.endswith("_clean"):
            clean_filename = filename
            final_filename = base_name.replace("_clean", "") + ext
        else:
            clean_filename = base_name + "_clean" + ext
            final_filename = filename
            
        clean_filepath = os.path.join(save_dir, clean_filename)
        final_filepath = os.path.join(save_dir, final_filename)
        
        # Check if clean background image exists
        if not os.path.exists(clean_filepath):
            if os.path.exists(final_filepath):
                clean_filepath = final_filepath
            else:
                return jsonify({"status": "error", "message": "Không tìm thấy ảnh nền gốc để chỉnh sửa."}), 404
                
        # Read clean image bytes
        with open(clean_filepath, "rb") as f:
            clean_bytes = f.read()
            
        # Overlay QR code with new settings
        if qr_link:
            print(f"Re-overlaying QR code for link '{qr_link}' at custom coordinates ({qr_x}%, {qr_y}%) with size {qr_size}%...")
            new_bytes = overlay_qr_code(clean_bytes, qr_link, position="center", size_percent=qr_size, x_percent=qr_x, y_percent=qr_y)
        else:
            new_bytes = clean_bytes
            
        # Write to final path
        with open(final_filepath, "wb") as f:
            f.write(new_bytes)
            
        # Update history.json with the adjusted QR coordinates
        history = load_history(save_dir)
        updated = False
        for item in history:
            if item.get("filename") == final_filename:
                item["qr_link"] = qr_link
                item["qr_x"] = qr_x
                item["qr_y"] = qr_y
                item["qr_size"] = qr_size
                updated = True
                break
        if updated:
            save_history(save_dir, history)
            
        return jsonify({
            "status": "success",
            "image": {
                "filename": final_filename,
                "local_path": final_filepath,
                "url": f"/images/{final_filename}"
            },
            "qr": {
                "has_qr": bool(qr_link),
                "qr_link": qr_link,
                "qr_x": qr_x,
                "qr_y": qr_y,
                "qr_size": qr_size
            }
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    # Ensure folders exist
    os.makedirs('templates', exist_ok=True)
    os.makedirs('static', exist_ok=True)
    
    # Save default config if not exists
    if not os.path.exists(CONFIG_FILE):
        save_config(DEFAULT_CONFIG)
        
    config = load_config()
    save_dir = config.get('save_dir', DEFAULT_CONFIG['save_dir'])
    os.makedirs(save_dir, exist_ok=True)
    
    # Auto-start Zalo monitor if enabled in config
    if config.get("zalo_sync_enabled", False):
        start_zalo_monitor()
    
    print("--------------------------------------------------")
    print("Google Banana Pro (Imagen 3) Image Generator Server")
    print("Starting local server...")
    print("--------------------------------------------------")
    
    # Open browser after a small delay
    def open_browser():
        time.sleep(1.5)
        webbrowser.open('http://127.0.0.1:5000')
        
    import threading
    threading.Thread(target=open_browser, daemon=True).start()
    
    app.run(host='127.0.0.1', port=5000, debug=False)
