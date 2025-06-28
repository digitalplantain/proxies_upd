import base64
import json
import os
import re
import socket
import subprocess
import tempfile
import time
import urllib.parse
import argparse
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from tqdm import tqdm

# --- НАСТРОЙКА ЛОГИРОВАНИЯ ---
DEBUG = os.environ.get('DEBUG', 'false').lower() == 'true'
def log_debug(message):
    if DEBUG: print(message, flush=True)

# --- КОНСТАНТЫ ---
# ... (весь блок констант GEMINI, YT_MUSIC остается без изменений) ...
GEMINI_ALLOWED_COUNTRY_CODES = {'AL', 'DZ', 'AS', 'AO', 'AI', 'AQ', 'AG', 'AR', 'AM', 'AW', 'AU', 'AT', 'AZ', 'BS', 'BH', 'BD', 'BB', 'BE', 'BZ', 'BJ', 'BM', 'BT', 'BO', 'BA', 'BW', 'BR', 'IO', 'VG', 'BN', 'BG', 'BF', 'BI', 'CV', 'KH', 'CM', 'CA', 'BQ', 'KY', 'CF', 'TD', 'CL', 'CX', 'CC', 'CO', 'KM', 'CK', 'CI', 'CR', 'HR', 'CW', 'CZ', 'CD', 'DK', 'DJ', 'DM', 'DO', 'EC', 'EG', 'SV', 'GQ', 'ER', 'EE', 'SZ', 'ET', 'FK', 'FO', 'FJ', 'FI', 'FR', 'GA', 'GM', 'GE', 'DE', 'GH', 'GI', 'GR', 'GL', 'GD', 'GU', 'GT', 'GG', 'GN', 'GW', 'GY', 'HT', 'HM', 'HN', 'HU', 'IS', 'IN', 'ID', 'IQ', 'IE', 'IM', 'IL', 'IT', 'JM', 'JP', 'JE', 'JO', 'KZ', 'KE', 'KI', 'XK', 'KG', 'KW', 'LA', 'LV', 'LB', 'LS', 'LR', 'LY', 'LI', 'LT', 'LU', 'MG', 'MW', 'MY', 'MV', 'ML', 'MT', 'MH', 'MR', 'MU', 'MX', 'FM', 'MN', 'ME', 'MS', 'MA', 'MZ', 'NA', 'NR', 'NP', 'NL', 'NC', 'NZ', 'NI', 'NE', 'NG', 'NU', 'NF', 'MK', 'MP', 'NO', 'OM', 'PK', 'PW', 'PS', 'PA', 'PG', 'PY', 'PE', 'PH', 'PN', 'PL', 'PT', 'PR', 'QA', 'CY', 'CG', 'RO', 'RW', 'BL', 'KN', 'LC', 'PM', 'VC', 'SH', 'WS', 'ST', 'SA', 'SN', 'RS', 'SC', 'SL', 'SG', 'SK', 'SI', 'SB', 'SO', 'ZA', 'GS', 'KR', 'SS', 'ES', 'LK', 'SD', 'SR', 'SE', 'CH', 'TW', 'TJ', 'TZ', 'TH', 'TL', 'TG', 'TK', 'TO', 'TT', 'TN', 'TR', 'TM', 'TC', 'TV', 'UG', 'UA', 'GB', 'AE', 'US', 'UM', 'VI', 'UY', 'UZ', 'VU', 'VE', 'VN', 'WF', 'EH', 'YE', 'ZM', 'ZW'}
YT_MUSIC_ALLOWED_COUNTRY_CODES = {'DZ', 'AS', 'AR', 'AW', 'AU', 'AT', 'AZ', 'BH', 'BD', 'BY', 'BE', 'BM', 'BO', 'BA', 'BR', 'BG', 'KH', 'CA', 'KY', 'CL', 'CO', 'CR', 'HR', 'CY', 'CZ', 'DK', 'DO', 'EC', 'EG', 'SV', 'EE', 'FI', 'FR', 'GF', 'PF', 'GE', 'DE', 'GH', 'GR', 'GP', 'GU', 'GT', 'HN', 'HK', 'HU', 'IS', 'IN', 'ID', 'IQ', 'IE', 'IL', 'IT', 'JM', 'JP', 'JO', 'KZ', 'KE', 'KW', 'LA', 'LV', 'LB', 'LY', 'LI', 'LT', 'LU', 'MY', 'MT', 'MX', 'MA', 'NP', 'NL', 'NZ', 'NI', 'NG', 'MK', 'MP', 'NO', 'OM', 'PK', 'PA', 'PG', 'PY', 'PE', 'PH', 'PL', 'PT', 'PR', 'QA', 'RE', 'RO', 'RU', 'SA', 'SN', 'RS', 'SG', 'SK', 'SI', 'ZA', 'KR', 'ES', 'LK', 'SE', 'CH', 'TW', 'TZ', 'TH', 'TN', 'TR', 'TC', 'VI', 'UG', 'UA', 'AE', 'GB', 'US', 'UY', 'VE', 'VN', 'YE', 'ZW'}
XRAY_PATH = "./xray"
MAX_WORKERS = 100
REQUEST_TIMEOUT = 12
TARGETS = {"ping_url": "http://cp.cloudflare.com/","ip_api_url": "http://ip-api.com/json/?fields=status,country,countryCode,isp","discord_url": "https://discord.com/api/v9/gateway"}

def get_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s: s.bind(("", 0)); return s.getsockname()[1]
def country_code_to_flag(code):
    if not isinstance(code, str) or len(code) != 2: return "🏁"; return "".join(chr(0x1F1E6 + ord(char.upper()) - ord('A')) for char in code)

def parse_proxy_link(link):
    try:
        if link.startswith('vmess://'): data = json.loads(base64.b64decode(link[8:]).decode('utf-8')); data['protocol'] = 'vmess'; return data
        parsed_url = urllib.parse.urlparse(link); protocol = parsed_url.scheme
        if not protocol or not parsed_url.hostname or not parsed_url.port: log_debug(f"[PARSE_FAIL] Неполная ссылка: {link[:50]}..."); return None
        if protocol == 'ss' and '@' not in parsed_url.netloc: user_info, host_info = base64.b64decode(parsed_url.netloc).decode('utf-8').split('@'); address, port = host_info.split(':'); method, password = user_info.split(':'); return {'protocol': 'shadowsocks', 'address': address, 'port': int(port), 'method': method, 'password': password}
        data = {'protocol': protocol, 'address': parsed_url.hostname, 'port': parsed_url.port}
        if protocol == 'shadowsocks': user_info = urllib.parse.unquote(parsed_url.username or ''); data['method'], data['password'] = user_info.split(':', 1)
        elif protocol in ['trojan', 'vless']: data['id'] = data['password'] = parsed_url.username; query = urllib.parse.parse_qs(parsed_url.query); [data.update({k.lower().replace('-', ''): v[0]}) for k, v in query.items()]; data['sni'] = data.get('sni', data.get('host', ''))
        return data
    except Exception as e: log_debug(f"[PARSE_ERROR] Ошибка парсинга '{link[:50]}...': {e}"); return None

# --- ИЗМЕНЕНО: Добавляем путь к лог-файлу в конфиг ---
def generate_xray_config(proxy_data, local_port, log_path):
    try:
        protocol = proxy_data['protocol']
        config = {
            "log": {
                "loglevel": "warning", # Логируем только важные события
                "access": log_path, # Путь к файлу логов доступа
                "error": log_path,  # Путь к файлу логов ошибок
            },
            "inbounds": [{"port": local_port,"listen": "127.0.0.1","protocol": "socks","settings": {"auth": "noauth", "udp": True, "ip": "127.0.0.1"}}],
            "outbounds": [{"protocol": protocol, "settings": {}, "streamSettings": {}}]
        }
        # ... остальная часть функции без изменений ...
        outbound, settings, stream_settings = config['outbounds'][0], config['outbounds'][0]['settings'], config['outbounds'][0]['streamSettings']
        port = int(proxy_data['port'])
        if protocol == 'vmess': settings['vnext'] = [{"address": proxy_data['add'],"port": port,"users": [{"id": proxy_data['id'], "alterId": int(proxy_data.get('aid', 0)), "security": proxy_data.get('scy', 'auto')}]}]
        elif protocol == 'vless': settings['vnext'] = [{"address": proxy_data['address'],"port": port,"users": [{"id": proxy_data['id'], "flow": proxy_data.get('flow', ''), "encryption": proxy_data.get('encryption', 'none')}]}]
        elif protocol == 'trojan': settings['servers'] = [{"address": proxy_data['address'],"port": port,"password": proxy_data['password']}]
        elif protocol == 'shadowsocks': settings['servers'] = [{"address": proxy_data['address'],"port": port,"method": proxy_data['method'],"password": proxy_data['password']}]
        stream_settings['network'] = proxy_data.get('net', proxy_data.get('type', 'tcp'))
        stream_settings['security'] = proxy_data.get('tls', proxy_data.get('security', ''))
        if stream_settings['security'] in ['tls', 'reality']:
            sni = proxy_data.get('sni', proxy_data.get('host', '')) or proxy_data.get('add', proxy_data.get('address'))
            tls_settings = {"serverName": sni, "allowInsecure": True}
            if stream_settings['security'] == 'reality': tls_settings["reality"] = {"publicKey": proxy_data.get('pbk', ''), "shortId": proxy_data.get('sid', '')}
            if 'fp' in proxy_data and proxy_data['fp']: tls_settings['fingerprint'] = proxy_data['fp']
            stream_settings['tlsSettings'] = tls_settings
        if stream_settings['network'] == 'ws':
            host = proxy_data.get('host', '') or proxy_data.get('sni', proxy_data.get('add', proxy_data.get('address')))
            stream_settings['wsSettings'] = {"path": proxy_data.get('path', '/'), "headers": {"Host": host}}
        elif stream_settings['network'] == 'grpc': stream_settings['grpcSettings'] = {"serviceName": proxy_data.get('serviceName', '')}
        return json.dumps(config)
    except Exception as e:
        log_debug(f"[CONFIG_ERROR] Ошибка генерации конфига для {proxy_data.get('address')}: {e}")
        return None

def check_proxy(proxy_link):
    log_debug(f"\n--- Проверяю: {proxy_link[:80]}...")
    proc, config_path, log_path = None, None, None
    try:
        proxy_data = parse_proxy_link(proxy_link)
        if not proxy_data: return None
        log_debug(f"-> Ссылка распарсена: {proxy_data['protocol']} @ {proxy_data['address']}:{proxy_data['port']}")
        
        local_port = get_free_port()
        
        # --- ИЗМЕНЕНО: Создаем пути для временных файлов ---
        with tempfile.NamedTemporaryFile(delete=False) as tf:
            base_path = tf.name
        config_path = base_path + ".json"
        log_path = base_path + ".log"
        
        config_json = generate_xray_config(proxy_data, local_port, log_path)
        if not config_json: return None
        with open(config_path, 'w', encoding='utf-8') as f: f.write(config_json)
        log_debug(f"-> Конфиг для Xray сгенерирован, порт {local_port}.")

        proc = subprocess.Popen([XRAY_PATH, "run", "-c", config_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(2.5) # ИЗМЕНЕНО: Немного увеличиваем задержку
        
        if proc.poll() is not None:
            log_debug(f"-> Xray процесс завершился преждевременно с кодом {proc.poll()}."); return None
        
        proxies = {'http': f'socks5://127.0.0.1:{local_port}', 'https': f'socks5://127.0.0.1:{local_port}'}
        
        log_debug("-> Проверка пинга (Cloudflare)...")
        start_time = time.time()
        try:
            requests.head(TARGETS["ping_url"], proxies=proxies, timeout=REQUEST_TIMEOUT).raise_for_status()
        except requests.exceptions.RequestException as e:
            # --- ИЗМЕНЕНО: Читаем и выводим лог Xray при ошибке ---
            log_debug(f"-> ПИНГ НЕ ПРОШЕЛ. Ошибка Python: {e}")
            if os.path.exists(log_path):
                with open(log_path, 'r', encoding='utf-8') as log_file:
                    xray_log_content = log_file.read().strip()
                    if xray_log_content:
                        log_debug(f"-> XRAY LOG: {xray_log_content}")
            return None
            
        ping = int((time.time() - start_time) * 1000)
        log_debug(f"-> Пинг ОК: {ping}ms.")
        
        # ... Остальная часть функции проверки (IP, Discord и т.д.) без изменений ...
        log_debug("-> Проверка IP (ip-api.com)...")
        try: response_ip = requests.get(TARGETS["ip_api_url"], proxies=proxies, timeout=REQUEST_TIMEOUT).json()
        except requests.exceptions.RequestException as e: log_debug(f"-> ПРОВЕРКА IP НЕ ПРОШЛА. Ошибка: {e}"); return None
        if response_ip.get('status') != 'success': log_debug(f"-> ПРОВЕРКА IP НЕ ПРОШЛА. Ответ API: {response_ip}"); return None
        country_code = response_ip.get('countryCode', 'N/A'); isp = response_ip.get('isp', 'N/A')
        log_debug(f"-> IP ОК: {country_code_to_flag(country_code)} {country_code}, {isp}.")
        gemini_ok = country_code in GEMINI_ALLOWED_COUNTRY_CODES
        yt_music_ok = country_code in YT_MUSIC_ALLOWED_COUNTRY_CODES
        discord_ok = False
        try: log_debug("-> Проверка Discord..."); resp = requests.head(TARGETS["discord_url"], proxies=proxies, timeout=REQUEST_TIMEOUT); discord_ok = (200 <= resp.status_code < 400); log_debug(f"-> Discord ОК: {discord_ok} (статус {resp.status_code}).")
        except requests.RequestException: log_debug("-> Проверка Discord НЕ ПРОШЛА (таймаут/ошибка).")
        log_debug("-> ПРОКСИ РАБОЧИЙ!")
        name = (f"{ping:04d}ms ◈ {country_code_to_flag(country_code)} {country_code} ◈ {isp} | "f"Discord {'✅' if discord_ok else '❌'} | "f"YT_Music {'✅' if yt_music_ok else '❌'} | "f"Gemini {'✅' if gemini_ok else '❌'}")
        final_link_with_new_name = f"{proxy_link.split('#')[0]}#{urllib.parse.quote(name)}"
        return (ping, final_link_with_new_name)
        
    except Exception: log_debug(f"--- НЕПРЕДВИДЕННАЯ ОШИБКА в check_proxy ---\n{traceback.format_exc()}"); return None
    finally:
        if proc: proc.terminate(); proc.wait()
        # --- ИЗМЕНЕНО: Удаляем оба временных файла ---
        if config_path and os.path.exists(config_path): os.remove(config_path)
        if log_path and os.path.exists(log_path): os.remove(log_path)

# ... main() и update_gist() остаются без изменений ...
def update_gist(gist_id, gist_filename, content, token):
    headers = {'Authorization': f'token {token}','Accept': 'application/vnd.github.v3+json'}
    data = {'files': {gist_filename: {'content': content if content else "# Рабочие прокси не найдены."}},'description': f'Рабочие прокси, обновлено: {time.strftime("%Y-%m-%d %H:%M:%S UTC")}'}
    try: response = requests.patch(f'https://api.github.com/gists/{gist_id}', headers=headers, json=data); response.raise_for_status(); print(f"\nGist '{gist_id}' успешно обновлен!")
    except requests.exceptions.RequestException as e: print(f"\nОшибка: Не удалось обновить Gist: {e}"); (e.response is not None) and print(f"Ответ от API: {e.response.text}")
def main():
    parser = argparse.ArgumentParser(description="Проверяет список прокси и обновляет Gist.", formatter_class=argparse.RawTextHelpFormatter); parser.add_argument("input_file", help="Файл со списком прокси-ссылок (каждая на новой строке)."); args = parser.parse_args()
    GIST_ID = os.environ.get('GIST_ID'); GIST_TOKEN = os.environ.get('GIST_TOKEN'); GIST_FILENAME = os.environ.get('GIST_FILENAME', 'working_proxies.txt')
    if not all([GIST_ID, GIST_TOKEN]): print("Ошибка: Переменные окружения GIST_ID и GIST_TOKEN должны быть установлены."); return
    if not os.path.exists(XRAY_PATH): print(f"Ошибка: Не найден исполняемый файл Xray по пути: {XRAY_PATH}"); return
    try:
        with open(args.input_file, 'r', encoding='utf-8') as f: all_links = [line.strip() for line in f]; proxy_links = [link for link in all_links if link and not link.startswith('ssr://')]; ignored_count = len(all_links) - len(proxy_links); print(f"Загружено {len(all_links)} строк. Отфильтровано {ignored_count} (пустые/ssr). В работе {len(proxy_links)} ссылок.")
    except FileNotFoundError: print(f"Ошибка: Входной файл не найден: {args.input_file}"); return
    if not proxy_links: print(f"Файл '{args.input_file}' не содержит подходящих для проверки ссылок."); return
    print(f"Начинаю проверку {len(proxy_links)} прокси в {MAX_WORKERS} потоков..."); working_proxies_with_ping = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_link = {executor.submit(check_proxy, link): link for link in proxy_links}
        for future in tqdm(as_completed(future_to_link), total=len(proxy_links), desc="Проверка прокси"):
            if result := future.result(): working_proxies_with_ping.append(result)
    print("\n" + "="*20 + " ЗАВЕРШЕНО " + "="*20); content_to_save = ""
    if working_proxies_with_ping:
        sorted_proxies = sorted(working_proxies_with_ping, key=lambda x: x[0]); final_proxy_list = [item[1] for item in sorted_proxies]
        content_to_save = "\n".join(final_proxy_list); print(f"\nНайдено {len(final_proxy_list)} рабочих прокси.")
    else: print("\nРабочие прокси не найдены.")
    update_gist(GIST_ID, GIST_FILENAME, content_to_save, GIST_TOKEN)

if __name__ == "__main__":
    main()
