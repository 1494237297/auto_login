import requests
import os
import sys
import subprocess
import platform
import argparse
import re
import json
import ctypes
import time
import random
import string
from urllib.parse import urljoin

VERSION = "1.0.0-beta"

DEFAULT_SERVER_URL = "http://192.168.202.253"
CONFIG_FILE = None

def get_config_path():
    if platform.system() == "Windows":
        config_dir = os.path.join(os.environ.get('USERPROFILE', ''), 'AppData', 'Local', 'AutoLogin')
    else:
        config_dir = os.path.join(os.path.expanduser('~'), '.autologin')
    
    if not os.path.exists(config_dir):
        try:
            os.makedirs(config_dir)
        except Exception as e:
            print(f"创建配置目录失败: {e}")
            if getattr(sys, 'frozen', False):
                config_dir = os.path.dirname(sys.executable)
            else:
                config_dir = os.path.dirname(os.path.abspath(__file__))
    
    return os.path.join(config_dir, 'config.json')

def is_admin():
    try:
        if platform.system() == "Windows":
            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        elif platform.system() in ["Linux", "Darwin"]:
            return os.geteuid() == 0
        else:
            return False
    except Exception:
        return False

def run_as_admin():
    try:
        if getattr(sys, 'frozen', False):
            current_executable = sys.executable
            cmd_args = f"--setup_action={check_autostart_status() and 'disable_autostart' or 'setup_autostart'} --config_path={os.path.abspath(CONFIG_FILE)}"
            
            result = ctypes.windll.shell32.ShellExecuteW(
                None,  
                "runas",  
                current_executable,  
                cmd_args, 
                None,  
                1     
            )
        else:
            script_path = os.path.abspath(__file__)
            python_exe = sys.executable
            action = "disable_autostart" if check_autostart_status() else "setup_autostart"
            config_path = os.path.abspath(CONFIG_FILE)
            cmd_args = f"{script_path} --setup_action={action} --config_path={config_path}"
            
            result = ctypes.windll.shell32.ShellExecuteW(
                None,  
                "runas",  
                python_exe,  
                cmd_args, 
                None,  
                1     
            )
        return result > 32
        
    except Exception as e:
        print(f"请求管理员权限失败: {e}")
        return False

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
                return config
        except Exception as e:
            print(f"加载配置文件失败: {e}")
    
    return {}

def save_config(config):
    try:
        config_dir = os.path.dirname(CONFIG_FILE)
        if not os.path.exists(config_dir):
            os.makedirs(config_dir)
            
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=4)
        return True
    except Exception as e:
        print(f"保存配置文件失败: {e}")
        return False

def get_server_url():
    config = load_config()
    return config.get("server_url", DEFAULT_SERVER_URL)


def check_campus_network():
    server_url = get_server_url()
    response = requests.get(server_url, timeout=5)
    return response.status_code == 200

def check_login_status():
    server_url = get_server_url()
    status_url = urljoin(server_url, "/drcom/chkstatus")
    v = str(random.randint(1000, 9999))
    status_params = {
        "callback": "dr1002",
        "jsVersion": "4.2.1",
        "v": v,
        "lang": "zh"
    }

    response = requests.get(status_url, params=status_params, timeout=5)
    response.encoding = 'utf-8'
    response_text = response.text
    
    json_str = re.search(r'dr1002\((.*?)\)', response_text)
    if json_str:
        status_data = json.loads(json_str.group(1))
        if status_data.get("result") == 1:
            print(f"已登录，用户: {status_data.get('uid', '未知')}")
            return True
    
    return False

def get_network_code(network):
    network_codes = {
        "校园网": "0",
        "中国联通": "1",
        "中国移动": "2",
        "中国电信": "3"
    }
    return network_codes.get(network, "0") 

def login():
    
    config = load_config()
    
    if not config or not config.get("username") or not config.get("password"):
        print("账户配置不完整，请先设置账户信息")
        return False
    
    print("正在登录...")

    username = config.get("username")
    password = config.get("password")
    network = config.get("network")
    server_url = config.get("server_url")
    login_url = urljoin(server_url, "/drcom/login")
    
    if not check_campus_network():
        print("未检测到校园网环境，无法登录")
        return False
    
    if check_login_status():
        return True
    
    try:
        r3 = get_network_code(network)
        rcn = ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(8))
        is_page_new = str(random.randint(1000, 9999))
        v = str(random.randint(1000, 9999))
        login_data = {
            "callback": "dr1005",
            "DDDDD": username,
            "upass": password,
            "0MKKey": "123456",
            "R1": "0",
            "R2": "",
            "R3": r3,
            "R6": "0",
            "para": "00",
            "v6ip": "",
            "login_t": "0",
            "js_status": "0",
            "is_page": "1",
            "is_page_new": is_page_new,
            "terminal_type": "1",
            "lang": "zh-cn",
            "rcn": rcn,
            "jsVersion": "4.2.1",
            "v": v
        }
        
        response = requests.get(login_url, params=login_data, timeout=10)
        response.encoding = 'utf-8'
        response_text = response.text
        
        json_str = re.search(r'dr1005\((.*?)\)', response_text)
        login_data = json.loads(json_str.group(1))

        if(check_login_status()):
            print("登录成功!")
            return True
        else:
            error_code = login_data.get("msga", "")
            get_error_details(error_code, server_url)
            return False
            
    except Exception as e:
        print(f"登录异常: {e}")
        return False

def get_error_details(error_code, server_url):
    error_url = f"{server_url}:801/eportal/portal/err_code/loadErrorPrompt"
    random_v = str(random.randint(1000, 9999))
    
    error_params = {
        "callback": "dr1006",
        "error_code": error_code,
        "jsVersion": "4.2.1",
        "v": random_v,
        "lang": "zh"
    }
    
    response = requests.get(error_url, params=error_params, timeout=5)
    response.encoding = 'utf-8'
    response_text = response.text
    
    json_str = re.search(r'dr1006\((.*?)\)', response_text)
    if json_str:
        error_data = json.loads(json_str.group(1))
        error_message = error_data.get("error_prompt_zh", "未知错误")
        print(f"登录失败: {error_message}")

#TODO: 账户设置
def setup_account():
    print("\n===== 账户设置 =====")
    
    config = load_config()
    print(f"当前用户名: {config.get('username', '未设置')}")
    print(f"当前密码: {'*' * len(config.get('password', '未设置'))}")
    print(f"当前服务商: {config.get('network', '未设置')}")
    
    print("\n请输入新的配置信息(直接回车保持不变):")
    
    current_username = config.get('username', '')
    new_username = input(f"用户名 [{current_username}]: ").strip()
    if not new_username and not current_username:
        print("错误: 用户名不能为空")
        return False
    elif not new_username:
        new_username = current_username
    
    current_password = config.get('password', '')
    new_password = input(f"密码 [{'*' * 8}]: ").strip()
    if not new_password and not current_password:
        print("错误: 密码不能为空")
        return False
    elif not new_password:
        new_password = current_password
    
    print("服务商选项: 1.中国移动 2.中国电信 3.中国联通 4.校园网")
    network_choice = input(f"选择服务商 [当前: {config.get('network', '未设置')}]: ").strip()
    
    network_mapping = {
        '1': "中国移动",
        '2': "中国电信",
        '3': "中国联通",
        '4': "校园网"
    }
    new_network = network_mapping.get(network_choice, config.get('network', "校园网"))
    
    server_url = config.get('server_url', DEFAULT_SERVER_URL)
    
    new_config = {
        "username": new_username,
        "password": new_password,
        "network": new_network,
        "server_url": server_url
    }
    
    if save_config(new_config):
        print("账户设置已保存")
        return True
    else:
        print("保存账户设置失败")
        return False

def create_windows_task():
    try:
        if getattr(sys, 'frozen', False):
            executable_path = sys.executable
            command = ['schtasks', '/Create', '/TN', "CampusNetworkAutoLogin", 
                      '/TR', f'"{executable_path}" --auto', 
                      '/SC', 'ONLOGON', '/RL', 'HIGHEST', '/F']
        else:
            script_path = os.path.abspath(__file__)
            python_exe = sys.executable
            command = ['schtasks', '/Create', '/TN', "CampusNetworkAutoLogin", 
                      '/TR', f'"{python_exe}" "{script_path}" --auto', 
                      '/SC', 'ONLOGON', '/RL', 'HIGHEST', '/F']
        
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        if result.returncode == 0:
            print("已成功设置Windows开机自启（任务计划）")
            return True
        else:
            try:
                error_msg = result.stderr.decode('gbk', errors='replace')
            except:
                error_msg = "未知错误"
            print(f"设置任务计划失败: {error_msg}")
            return False
    except Exception as e:
        print(f"创建Windows自启动任务失败: {e}")
        return False

def create_macOS_autostart():
    try:
        if getattr(sys, 'frozen', False):
            executable_path = sys.executable
            script_cmd = executable_path
            script_args = ["--auto"]
        else:
            script_path = os.path.abspath(__file__)
            python_exe = sys.executable
            script_cmd = python_exe
            script_args = [script_path, "--auto"]
            
        output_dir = os.path.join(os.path.expanduser('~'), '.autologin', 'logs')
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
            
        program_args = ['<string>{}</string>'.format(arg) for arg in [script_cmd] + script_args]
        plist_content = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.campus.autologin</string>
    <key>ProgramArguments</key>
    <array>
        {program_args}
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <false/>
    <key>StandardOutPath</key>
    <string>{output_dir}/stdout.log</string>
    <key>StandardErrorPath</key>
    <string>{output_dir}/stderr.log</string>
</dict>
</plist>
""".format(
            program_args='\n        '.join(program_args),
            output_dir=output_dir
        )
        
        plist_path = os.path.expanduser("~/Library/LaunchAgents/com.campus.autologin.plist")
        with open(plist_path, 'w') as f:
            f.write(plist_content)
            
        subprocess.run(['launchctl', 'load', plist_path])
        print("已成功设置macOS开机自启")
        return True
    except Exception as e:
        print(f"创建macOS自启动配置失败: {e}")
        return False

def setup_autostart():
    if platform.system() == "Windows" and not is_admin():
        print("设置开机自启需要管理员权限，正在请求...")
        
        if run_as_admin():
            time.sleep(0.5)
            if check_autostart_status():
                print("开机自启已成功设置！")
            else:
                print("开机自启设置失败")
            return True
        else:
            print("用户拒绝了管理员权限请求，无法设置开机自启")
            return False
    
    try:
        if platform.system() == "Windows":
            return create_windows_task()
        elif platform.system() == "Darwin": 
            return create_macOS_autostart()
        else:
            print("当前系统不支持自动设置开机自启")
            return False
    except Exception as e:
        print(f"设置开机自启失败: {e}")
        return False

def check_autostart_status():
    try:
        if platform.system() == "Windows":
            task_name = "CampusNetworkAutoLogin"
            command = ['schtasks', '/Query', '/TN', task_name, '/FO', 'LIST']
            
            result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            return result.returncode == 0
                
        elif platform.system() == "Darwin":
            plist_path = os.path.expanduser("~/Library/LaunchAgents/com.campus.autologin.plist")
            if os.path.exists(plist_path):
                result = subprocess.run(['launchctl', 'list', 'com.campus.autologin'], 
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                return result.returncode == 0
            return False
            
        return False
    except Exception as e:
        print(f"检查自启状态失败: {e}")
        return False

def delete_windows_task():
    task_name = "CampusNetworkAutoLogin"
    command = ['schtasks', '/Delete', '/TN', task_name, '/F']
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode == 0:
        print("已禁用Windows开机自启")
        return True
    else:
        try:
            error_msg = result.stderr.decode('gbk', errors='replace')
        except:
            error_msg = "未知错误"
        print(f"禁用任务计划失败: {error_msg}")
        return False

def delete_macOS_autostart():
    try:
        plist_path = os.path.expanduser("~/Library/LaunchAgents/com.campus.autologin.plist")
        if os.path.exists(plist_path):
            subprocess.run(['launchctl', 'unload', plist_path])
            os.remove(plist_path)
            print("已禁用macOS开机自启")
            return True
        return False
    except Exception as e:
        print(f"禁用macOS开机自启失败: {e}")
        return False

#TODO: 开机自启
def toggle_autostart():
    current_status = check_autostart_status()
    
    if current_status:
        if platform.system() == "Windows" and not is_admin():
            print("禁用开机自启需要管理员权限，正在请求...")
            if run_as_admin():
                time.sleep(0.5)
                if not check_autostart_status():
                    print("开机自启已成功禁用！")
                else:
                    print("开机自启禁用失败")
                return True
            else:
                print("用户拒绝了管理员权限请求，无法禁用开机自启")
                return False
                
        try:
            if platform.system() == "Windows":
                return delete_windows_task()
            elif platform.system() == "Darwin": 
                return delete_macOS_autostart()
            else:
                print("当前系统不支持自动设置开机自启")
                return False
        except Exception as e:
            print(f"禁用开机自启失败: {e}")
            return False
    else:
        return setup_autostart()

def show_menu():
    print(f"\n===== 校园网自动登录工具 v{VERSION} =====")
    print("1. 设置账户信息")
    
    autostart_status = check_autostart_status()
    if autostart_status:
        print("2. 关闭开机自启")
    else:
        print("2. 开启开机自启")
        
    print("3. 登录")
    print("请输入选项(其他键退出):")
    
    choice = input().strip()
    return choice

def main():
    parser = argparse.ArgumentParser(description=f'校园网自动登录工具 v{VERSION}')
    parser.add_argument('--auto', action='store_true', help='自动模式，用于开机自启')
    parser.add_argument('--setup_action', help='提权后要执行的操作')
    parser.add_argument('--config_path', help='配置文件路径')
    args = parser.parse_args()
    
    global CONFIG_FILE
    CONFIG_FILE = args.config_path if args.config_path else get_config_path()
    
    if args.setup_action == 'setup_autostart':
        print("以管理员权限运行，正在设置开机自启...")
        setup_autostart()
        return
    elif args.setup_action == 'disable_autostart':
        print("以管理员权限运行，正在禁用开机自启...")
        if platform.system() == "Windows":
            delete_windows_task()
        elif platform.system() == "Darwin":
            delete_macOS_autostart()
        return
    
    if args.auto:
        print(f"校园网自动登录程序 v{VERSION} (自动模式)")
        login()
        return
    
    print(f"校园网自动登录程序 v{VERSION} (交互模式)")
    print("项目地址：https://github.com/1494237297/auto_login")
    
    config = load_config()
    if not config or not config.get("username") or not config.get("password"):
        print("未检测到完整配置，请先设置账户信息")
        setup_account()
    else:
        login()
    
    while True:
        choice = show_menu()
        
        if choice == '1':
            setup_account()
        elif choice == '2':
            toggle_autostart()
        elif choice == '3':
            login()
        else:
            print("退出程序")
            break

if __name__ == "__main__":
        main()