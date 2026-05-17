"""
ULTIMATE GITHUB REPOSITORY MANAGER - WITH CRYPTOGRAPHIC SESSION STORAGE
======================================================================
• Cryptographic token storage (Fernet + machine ID)
• Manual token entry fallback (no gh CLI required)
• Full repository management (visibility, rename, delete, star, clone)
• Real‑time file explorer: browse, edit, create, delete, upload
• Markdown / HTML preview (no image preview)
• All changes applied directly to GitHub
"""

import base64
import csv
import os
import requests
import subprocess
import sys
import time
import tkinter as tk
import webbrowser
import json
import shutil
import tempfile
import hashlib
import getpass
from pathlib import Path
from tkinter import ttk, messagebox, simpledialog, filedialog
from datetime import datetime

import markdown

# =========================================================
# CRYPTOGRAPHY (Fernet) for session storage
# =========================================================
try:
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False
    print("Warning: 'cryptography' not installed. Token storage will be plain text.")

# =========================================================
# Helper: get machine unique ID (for key derivation)
# =========================================================
def get_machine_id():
    """Return a stable machine identifier (hostname + system UUID)."""
    try:
        if sys.platform == "win32":
            import winreg
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography")
            machine_guid, _ = winreg.QueryValueEx(key, "MachineGuid")
            return machine_guid
        elif sys.platform == "linux" or sys.platform == "darwin":
            with open("/etc/machine-id", "r") as f:
                return f.read().strip()
    except:
        pass
    return hashlib.sha256(f"{os.uname().nodename}{getpass.getuser()}".encode()).hexdigest()

def get_encryption_key():
    """Derive a Fernet key from the machine ID (so key is not stored in a file)."""
    if not CRYPTO_AVAILABLE:
        return None
    machine_id = get_machine_id()
    kdf = PBKDF2(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"github_manager_salt_2025",
        iterations=100000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(machine_id.encode()))
    return key

def encrypt_token(token):
    if not CRYPTO_AVAILABLE:
        return token
    key = get_encryption_key()
    if key is None:
        return token
    f = Fernet(key)
    return f.encrypt(token.encode()).decode()

def decrypt_token(encrypted_token):
    if not CRYPTO_AVAILABLE:
        return encrypted_token
    key = get_encryption_key()
    if key is None:
        return encrypted_token
    try:
        f = Fernet(key)
        return f.decrypt(encrypted_token.encode()).decode()
    except:
        return None

# =========================================================
# GLOBAL AUTH & USER INFO
# =========================================================

TOKEN = None
HEADERS = None
USERNAME = "Not logged in"
TOKEN_CACHE_FILE = Path.home() / ".github_manager_token"

def save_token_to_cache(token):
    if token:
        encrypted = encrypt_token(token)
        with open(TOKEN_CACHE_FILE, "w") as f:
            f.write(encrypted)
    else:
        if TOKEN_CACHE_FILE.exists():
            TOKEN_CACHE_FILE.unlink()

def load_token_from_cache():
    if TOKEN_CACHE_FILE.exists():
        try:
            encrypted = TOKEN_CACHE_FILE.read_text().strip()
            token = decrypt_token(encrypted)
            if token and token.startswith(("ghp_", "github_pat_")):
                return token
        except:
            pass
    return None

def refresh_auth(manual_token=None):
    global TOKEN, HEADERS, USERNAME
    token = None

    if manual_token:
        token = manual_token
    else:
        # Try gh CLI first
        try:
            token = subprocess.check_output(["gh", "auth", "token"], text=True).strip()
        except:
            pass

    if not token:
        token = load_token_from_cache()

    if not token:
        USERNAME = "Not logged in"
        TOKEN = None
        HEADERS = None
        return False

    TOKEN = token
    HEADERS = {"Authorization": f"Bearer {TOKEN}", "Accept": "application/vnd.github+json"}
    try:
        resp = requests.get("https://api.github.com/user", headers=HEADERS, timeout=10)
        if resp.status_code == 200:
            USERNAME = resp.json().get("login", "unknown")
            save_token_to_cache(token)
            return True
        else:
            USERNAME = "Not logged in"
            TOKEN = None
            HEADERS = None
            if TOKEN_CACHE_FILE.exists():
                TOKEN_CACHE_FILE.unlink()
            return False
    except:
        USERNAME = "Not logged in"
        TOKEN = None
        HEADERS = None
        return False

API = "https://api.github.com"

# =========================================================
# API HELPERS
# =========================================================

def api_get(url, retries=3):
    for attempt in range(retries):
        if not HEADERS:
            raise Exception("Not authenticated. Please login first.")
        response = requests.get(url, headers=HEADERS)
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 403 and "rate limit" in response.text.lower():
            reset_time = int(response.headers.get("X-RateLimit-Reset", 0))
            wait = max(reset_time - time.time(), 5)
            time.sleep(wait)
            continue
        else:
            raise Exception(f"GitHub API Error ({response.status_code}):\n{response.text}")
    raise Exception("Max retries exceeded.")

def api_patch(url, payload):
    if not HEADERS:
        raise Exception("Not authenticated.")
    response = requests.patch(url, headers=HEADERS, json=payload)
    return response.status_code == 200

def api_delete(url, payload=None):
    if not HEADERS:
        raise Exception("Not authenticated.")
    if payload:
        response = requests.delete(url, headers=HEADERS, json=payload)
    else:
        response = requests.delete(url, headers=HEADERS)
    return response.status_code == 204

def api_put(url, payload=None):
    if not HEADERS:
        raise Exception("Not authenticated.")
    if payload:
        response = requests.put(url, headers=HEADERS, json=payload)
    else:
        response = requests.put(url, headers=HEADERS)
    return response.status_code == 204

def api_post(url, payload):
    if not HEADERS:
        raise Exception("Not authenticated.")
    response = requests.post(url, headers=HEADERS, json=payload)
    return response.status_code == 201

# =========================================================
# REPOSITORY DATA FETCHING & MANAGEMENT
# =========================================================

def fetch_repositories():
    repos = []
    page = 1
    while True:
        url = f"{API}/user/repos?visibility=all&affiliation=owner&sort=updated&per_page=100&page={page}"
        data = api_get(url)
        if not data:
            break
        repos.extend(data)
        page += 1
    return repos

def set_visibility(owner, repo, private):
    return api_patch(f"{API}/repos/{owner}/{repo}", {"private": private})

def rename_repository(owner, old_name, new_name):
    return api_patch(f"{API}/repos/{owner}/{old_name}", {"name": new_name})

def delete_repository(owner, repo):
    return api_delete(f"{API}/repos/{owner}/{repo}")

def star_repository(owner, repo):
    return api_put(f"{API}/user/starred/{owner}/{repo}")

def unstar_repository(owner, repo):
    return api_delete(f"{API}/user/starred/{owner}/{repo}")

def download_repository(repo):
    branch = repo["default_branch"]
    zip_url = f"{repo['html_url']}/archive/refs/heads/{branch}.zip"
    response = requests.get(zip_url)
    filename = f"{repo['name']}.zip"
    with open(filename, "wb") as f:
        f.write(response.content)
    return filename

def fetch_tree(owner, repo, branch):
    url = f"{API}/repos/{owner}/{repo}/git/trees/{branch}?recursive=1"
    try:
        return api_get(url).get("tree", [])
    except:
        return []

def fetch_readme(owner, repo):
    try:
        url = f"{API}/repos/{owner}/{repo}/readme"
        data = api_get(url)
        content = base64.b64decode(data["content"]).decode("utf-8")
        return markdown.markdown(content)
    except:
        return "<p>No README Found.</p>"

def generate_html(repos):
    html_content = """<html><head><title>GitHub Intelligence Dashboard</title>
    <style>
        body{background:#0f1117;color:#e6edf3;font-family:Segoe UI;padding:25px;}
        .repo{background:#161b22;border:1px solid #2d333b;border-radius:14px;padding:20px;margin-bottom:25px;}
        h1,h2{color:#00c8ff;}
        a{color:#00c8ff;text-decoration:none;}
        .file{margin-left:20px;padding:2px;}
    </style></head><body><h1>GitHub Repository Intelligence Report</h1>"""
    for repo in repos:
        owner, name = repo["owner"]["login"], repo["name"]
        branch = repo["default_branch"]
        tree = fetch_tree(owner, name, branch)
        readme = fetch_readme(owner, name)
        visibility = "Private" if repo["private"] else "Public"
        html_content += f"""
        <div class="repo">
            <h2>{name}</h2>
            <p><b>Visibility:</b> {visibility}</p>
            <p><b>Language:</b> {repo['language']}</p>
            <p><b>Stars:</b> {repo['stargazers_count']}</p>
            <p><b>Forks:</b> {repo['forks_count']}</p>
            <a href="{repo['html_url']}">Open Repository</a>
            <h3>README</h3>{readme}<h3>Files</h3>
        """
        for item in tree:
            if item["type"] == "blob":
                html_content += f"<div class='file'>• {item['path']}</div>"
        html_content += "</div>"
    html_content += f"<hr><p>Generated: {datetime.now()}</p></body></html>"
    path = Path("github_intelligence_report.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(html_content)
    return path

# =========================================================
# REPOSITORY FILE EXPLORER (Real-time editing + Preview)
# =========================================================

class RepoExplorer:
    def __init__(self, parent, owner, repo, branch, headers):
        self.parent = parent
        self.owner = owner
        self.repo = repo
        self.branch = branch
        self.headers = headers
        self.current_path = ""
        self.window = tk.Toplevel(parent)
        self.window.title(f"Explorer: {owner}/{repo} ({branch})")
        self.window.geometry("1000x750")
        self.window.minsize(700, 500)

        self.bg = "#0f1117"
        self.panel = "#161b22"
        self.text_fg = "#e6edf3"
        self.cyan = "#00c8ff"
        self.danger = "#ff5c5c"

        self.window.configure(bg=self.bg)

        # Top frame
        top_frame = tk.Frame(self.window, bg=self.panel)
        top_frame.pack(fill="x", padx=5, pady=5)

        tk.Label(top_frame, text="Path:", bg=self.panel, fg=self.text_fg, font=("Segoe UI", 10)).pack(side="left", padx=5)
        self.path_var = tk.StringVar(value="/")
        path_entry = tk.Entry(top_frame, textvariable=self.path_var, bg=self.panel, fg=self.text_fg,
                              insertbackground=self.text_fg, relief="flat", bd=0, width=50, font=("Segoe UI", 10))
        path_entry.pack(side="left", padx=5, fill="x", expand=True)
        path_entry.bind("<Return>", lambda e: self.navigate_to_path())

        btn_frame = tk.Frame(top_frame, bg=self.panel)
        btn_frame.pack(side="right", padx=5)
        tk.Button(btn_frame, text="Go", command=self.navigate_to_path, bg=self.cyan, fg="#000", relief="flat", padx=10, pady=4).pack(side="left", padx=2)
        tk.Button(btn_frame, text="Refresh", command=self.refresh_current, bg=self.panel, fg=self.cyan, relief="flat", padx=10, pady=4).pack(side="left", padx=2)

        # Tree frame
        tree_frame = tk.Frame(self.window, bg=self.bg)
        tree_frame.pack(fill="both", expand=True, padx=5, pady=5)

        self.tree = ttk.Treeview(tree_frame, columns=("type", "size"), show="tree headings")
        self.tree.heading("#0", text="Name")
        self.tree.heading("type", text="Type")
        self.tree.heading("size", text="Size")
        self.tree.column("#0", width=450)
        self.tree.column("type", width=100)
        self.tree.column("size", width=120)

        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)

        self.tree.bind("<Double-1>", self.on_double_click)
        self.context_menu = tk.Menu(self.window, tearoff=0, bg=self.panel, fg=self.text_fg)
        self.context_menu.add_command(label="Open", command=self.open_selected)
        self.context_menu.add_command(label="Edit File", command=self.edit_file)
        self.context_menu.add_command(label="Preview", command=self.preview_selected)
        self.context_menu.add_command(label="Delete", command=self.delete_selected)
        self.context_menu.add_command(label="Download", command=self.download_selected)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="New File", command=self.new_file)
        self.context_menu.add_command(label="New Folder", command=self.new_folder)
        self.context_menu.add_command(label="Upload File", command=self.upload_file)
        self.tree.bind("<Button-3>", self.show_context_menu)

        # Bottom bar
        bottom_frame = tk.Frame(self.window, bg=self.panel)
        bottom_frame.pack(fill="x", padx=5, pady=5)
        for txt, cmd in [("📄 New File", self.new_file), ("📁 New Folder", self.new_folder),
                         ("⬆ Upload File", self.upload_file), ("🔄 Refresh", self.refresh_current),
                         ("✏ Edit Selected", self.edit_file), ("🔍 Preview", self.preview_selected),
                         ("🗑 Delete Selected", self.delete_selected)]:
            tk.Button(bottom_frame, text=txt, command=cmd, bg=self.panel, fg=self.cyan if txt != "🗑 Delete Selected" else self.danger,
                      relief="flat", padx=12, pady=4).pack(side="left", padx=2)

        # Log area
        log_frame = tk.LabelFrame(self.window, text="Actions Log", bg=self.panel, fg=self.cyan, font=("Segoe UI", 9))
        log_frame.pack(fill="x", padx=5, pady=(0,5))
        self.log_text = tk.Text(log_frame, height=6, bg="#1e242d", fg=self.text_fg, wrap="word", font=("Consolas", 8))
        self.log_text.pack(fill="both", expand=True, padx=3, pady=3)

        self.navigate("")

    def log(self, message, is_error=False):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        if is_error:
            self.log_text.tag_add("error", "end-2l", "end-1l")
            self.log_text.tag_config("error", foreground=self.danger)
        self.log_text.see(tk.END)

    def api_get_contents(self, path):
        url = f"{API}/repos/{self.owner}/{self.repo}/contents/{path}"
        params = {"ref": self.branch}
        resp = requests.get(url, headers=self.headers, params=params)
        if resp.status_code == 200:
            return resp.json()
        elif resp.status_code == 404:
            return None
        else:
            raise Exception(f"API error {resp.status_code}: {resp.text}")

    def navigate(self, path):
        self.current_path = path.rstrip("/")
        display_path = "/" + self.current_path if self.current_path else "/"
        self.path_var.set(display_path)
        self.load_directory()

    def navigate_to_path(self):
        path = self.path_var.get().strip()
        if path.startswith("/"):
            path = path[1:]
        self.navigate(path)

    def load_directory(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        try:
            contents = self.api_get_contents(self.current_path)
            if contents is None:
                self.log(f"Path not found: /{self.current_path}", is_error=True)
                return
            if not isinstance(contents, list):
                self.log(f"Path is a file, not directory: /{self.current_path}", is_error=True)
                return
            dirs = [c for c in contents if c["type"] == "dir"]
            files = [c for c in contents if c["type"] == "file"]
            for item in dirs + files:
                name = item["name"]
                item_type = "Dir" if item["type"] == "dir" else "File"
                size = item.get("size", 0)
                if size < 1024:
                    size_str = f"{size} B"
                elif size < 1024*1024:
                    size_str = f"{size/1024:.1f} KB"
                else:
                    size_str = f"{size/(1024*1024):.1f} MB"
                oid = self.tree.insert("", "end", text=name, values=(item_type, size_str))
                self.tree.item(oid, tags=(item["type"], item["path"], item.get("sha", "")))
            self.log(f"Loaded {len(dirs)+len(files)} items from /{self.current_path}")
        except Exception as e:
            self.log(f"Failed to load directory: {e}", is_error=True)

    def refresh_current(self):
        self.load_directory()

    def on_double_click(self, event):
        self.open_selected()

    def open_selected(self):
        selected = self.tree.selection()
        if not selected: return
        item = selected[0]
        item_type = self.tree.item(item, "tags")[0]
        item_path = self.tree.item(item, "tags")[1]
        if item_type == "dir":
            self.navigate(item_path)
        else:
            # For any file, default to edit (since we removed image preview)
            self.edit_file()

    def preview_selected(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo("Info", "Select a file to preview.")
            return
        item = selected[0]
        item_type = self.tree.item(item, "tags")[0]
        if item_type != "file":
            messagebox.showinfo("Info", "Preview is only available for files.")
            return
        item_path = self.tree.item(item, "tags")[1]
        self.preview_file(item_path)

    def preview_file(self, file_path):
        """Detect file type and preview accordingly (markdown, html, or text)."""
        ext = os.path.splitext(file_path)[1].lower()

        if ext == '.md':
            self.preview_markdown(file_path)
        elif ext in ['.html', '.htm']:
            self.preview_html(file_path)
        else:
            # For any other file, show a simple text preview (if it looks like text)
            self.preview_text_file(file_path)

    def preview_markdown(self, file_path):
        try:
            url = f"{API}/repos/{self.owner}/{self.repo}/contents/{file_path}"
            params = {"ref": self.branch}
            resp = requests.get(url, headers=self.headers, params=params)
            if resp.status_code != 200:
                self.log(f"Failed to fetch Markdown: {resp.status_code}", is_error=True)
                return
            data = resp.json()
            content = base64.b64decode(data["content"]).decode("utf-8", errors="replace")
            html_content = markdown.markdown(content)
            full_html = f"""<!DOCTYPE html>
            <html><head><meta charset="utf-8"><title>Preview: {file_path}</title>
            <style>
                body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
                       line-height: 1.6; padding: 2rem; max-width: 900px; margin: 0 auto; background: #f6f8fa; color: #24292e; }}
                pre {{ background: #f6f8fa; padding: 1rem; border-radius: 6px; overflow: auto; }}
                code {{ background: #f1f1f1; padding: 0.2rem 0.4rem; border-radius: 4px; }}
                h1,h2,h3 {{ border-bottom: 1px solid #e1e4e8; }}
            </style></head><body>{html_content}</body></html>"""
            with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as f:
                f.write(full_html)
                tmp_path = f.name
            webbrowser.open(f"file://{os.path.abspath(tmp_path)}")
            self.log(f"Previewed Markdown file: {file_path}")
        except Exception as e:
            self.log(f"Markdown preview error: {e}", is_error=True)
            messagebox.showerror("Preview Error", str(e))

    def preview_html(self, file_path):
        try:
            url = f"{API}/repos/{self.owner}/{self.repo}/contents/{file_path}"
            params = {"ref": self.branch}
            resp = requests.get(url, headers=self.headers, params=params)
            if resp.status_code != 200:
                self.log(f"Failed to fetch HTML: {resp.status_code}", is_error=True)
                return
            data = resp.json()
            content = base64.b64decode(data["content"]).decode("utf-8", errors="replace")
            with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as f:
                f.write(content)
                tmp_path = f.name
            webbrowser.open(f"file://{os.path.abspath(tmp_path)}")
            self.log(f"Previewed HTML file: {file_path}")
        except Exception as e:
            self.log(f"HTML preview error: {e}", is_error=True)
            messagebox.showerror("Preview Error", str(e))

    def preview_text_file(self, file_path):
        try:
            url = f"{API}/repos/{self.owner}/{self.repo}/contents/{file_path}"
            params = {"ref": self.branch}
            resp = requests.get(url, headers=self.headers, params=params)
            if resp.status_code != 200:
                self.log(f"Failed to fetch text file: {resp.status_code}", is_error=True)
                return
            data = resp.json()
            content = base64.b64decode(data["content"]).decode("utf-8", errors="replace")
            win = tk.Toplevel(self.window)
            win.title(f"Preview: {file_path}")
            win.geometry("800x600")
            win.configure(bg=self.bg)
            text_widget = tk.Text(win, wrap="word", font=("Consolas", 10), bg="#1e242d", fg=self.text_fg)
            text_widget.insert("1.0", content)
            text_widget.pack(fill="both", expand=True, padx=5, pady=5)
            scroll = tk.Scrollbar(text_widget)
            scroll.pack(side="right", fill="y")
            text_widget.config(yscrollcommand=scroll.set, scrollcommand=scroll.set)
            self.log(f"Previewed text file: {file_path}")
        except Exception as e:
            self.log(f"Text preview error: {e}", is_error=True)
            messagebox.showerror("Preview Error", str(e))

    def edit_file(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo("Info", "Select a file to edit.")
            return
        item = selected[0]
        item_type = self.tree.item(item, "tags")[0]
        if item_type != "file":
            messagebox.showinfo("Info", "Select a file, not a directory.")
            return
        item_path = self.tree.item(item, "tags")[1]
        self.open_file_editor(item_path)

    def open_file_editor(self, file_path):
        try:
            url = f"{API}/repos/{self.owner}/{self.repo}/contents/{file_path}"
            params = {"ref": self.branch}
            resp = requests.get(url, headers=self.headers, params=params)
            if resp.status_code != 200:
                self.log(f"Failed to fetch file: {resp.status_code}", is_error=True)
                messagebox.showerror("Error", f"Failed to fetch file: HTTP {resp.status_code}")
                return
            data = resp.json()
            content = base64.b64decode(data["content"]).decode("utf-8", errors="replace")
            sha = data["sha"]

            editor = tk.Toplevel(self.window)
            editor.title(f"Editing: {file_path}")
            editor.geometry("900x700")
            editor.configure(bg=self.bg)

            text_widget = tk.Text(editor, wrap="none", font=("Consolas", 11), bg="#1e242d", fg=self.text_fg, insertbackground=self.text_fg)
            text_widget.insert("1.0", content)
            text_widget.pack(fill="both", expand=True, padx=5, pady=5)

            btn_frame = tk.Frame(editor, bg=self.bg)
            btn_frame.pack(fill="x", pady=5)

            def save_changes():
                new_content = text_widget.get("1.0", "end-1c")
                new_content_b64 = base64.b64encode(new_content.encode("utf-8")).decode("utf-8")
                commit_msg = simpledialog.askstring("Commit Message", "Enter commit message:", initialvalue=f"Update {file_path}")
                if not commit_msg:
                    return
                payload = {"message": commit_msg, "content": new_content_b64, "sha": sha, "branch": self.branch}
                put_url = f"{API}/repos/{self.owner}/{self.repo}/contents/{file_path}"
                resp = requests.put(put_url, headers=self.headers, json=payload)
                if resp.status_code in (200, 201):
                    self.log(f"Updated {file_path}")
                    editor.destroy()
                    self.refresh_current()
                else:
                    self.log(f"Update failed: {resp.text}", is_error=True)
                    messagebox.showerror("Error", f"Failed to update:\n{resp.text}")

            def preview_current():
                new_content = text_widget.get("1.0", "end-1c")
                ext = os.path.splitext(file_path)[1].lower()
                try:
                    if ext == ".md":
                        html_content = markdown.markdown(new_content)
                        full_html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>Preview (unsaved)</title>
                        <style>body {{ font-family: sans-serif; padding: 2rem; max-width: 900px; margin: auto; background: #f6f8fa; }}</style>
                        </head><body>{html_content}</body></html>"""
                        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as f:
                            f.write(full_html)
                            temp_path = f.name
                        webbrowser.open(f"file://{os.path.abspath(temp_path)}")
                    elif ext in [".html", ".htm"]:
                        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as f:
                            f.write(new_content)
                            temp_path = f.name
                        webbrowser.open(f"file://{os.path.abspath(temp_path)}")
                    else:
                        messagebox.showinfo("Preview", "Preview only for .md, .html, .htm")
                except Exception as e:
                    self.log(f"Preview error: {e}", is_error=True)
                    messagebox.showerror("Preview Error", str(e))

            tk.Button(btn_frame, text="Save", command=save_changes, bg=self.cyan, fg="#000", padx=15).pack(side="left", padx=5)
            tk.Button(btn_frame, text="Preview", command=preview_current, bg=self.panel, fg=self.cyan, padx=15).pack(side="left", padx=5)
            tk.Button(btn_frame, text="Cancel", command=editor.destroy, bg=self.panel, fg=self.text_fg, padx=15).pack(side="left", padx=5)
        except Exception as e:
            self.log(f"Error opening file: {e}", is_error=True)
            messagebox.showerror("Error", str(e))

    def delete_selected(self):
        selected = self.tree.selection()
        if not selected: return
        item = selected[0]
        item_type = self.tree.item(item, "tags")[0]
        item_path = self.tree.item(item, "tags")[1]
        sha = self.tree.item(item, "tags")[2] if len(self.tree.item(item, "tags")) > 2 else None

        if item_type == "dir":
            if not messagebox.askyesno("Delete Directory", f"Permanently delete '{item_path}' and all contents?"):
                return
            try:
                self.delete_directory_recursive(item_path)
                self.log(f"Deleted directory {item_path}")
                self.refresh_current()
            except Exception as e:
                self.log(f"Failed to delete directory: {e}", is_error=True)
                messagebox.showerror("Error", str(e))
        else:
            if not messagebox.askyesno("Confirm Delete", f"Delete file '{item_path}' permanently?"):
                return
            try:
                commit_msg = simpledialog.askstring("Commit Message", "Enter commit message:", initialvalue=f"Delete {item_path}")
                if not commit_msg: return
                payload = {"message": commit_msg, "sha": sha, "branch": self.branch}
                url = f"{API}/repos/{self.owner}/{self.repo}/contents/{item_path}"
                resp = requests.delete(url, headers=self.headers, json=payload)
                if resp.status_code == 204:
                    self.log(f"Deleted {item_path}")
                    self.refresh_current()
                else:
                    self.log(f"Delete failed: {resp.text}", is_error=True)
            except Exception as e:
                self.log(f"Error deleting: {e}", is_error=True)

    def delete_directory_recursive(self, dir_path):
        contents = self.api_get_contents(dir_path)
        if not contents or not isinstance(contents, list):
            return
        for item in contents:
            if item["type"] == "file":
                payload = {"message": f"Delete {item['path']}", "sha": item["sha"], "branch": self.branch}
                url = f"{API}/repos/{self.owner}/{self.repo}/contents/{item['path']}"
                resp = requests.delete(url, headers=self.headers, json=payload)
                if resp.status_code != 204:
                    raise Exception(f"Failed to delete {item['path']}")
            elif item["type"] == "dir":
                self.delete_directory_recursive(item["path"])

    def download_selected(self):
        selected = self.tree.selection()
        if not selected: return
        item = selected[0]
        item_type = self.tree.item(item, "tags")[0]
        item_path = self.tree.item(item, "tags")[1]
        if item_type == "dir":
            messagebox.showinfo("Info", "Download directory not implemented. Use git clone.")
            return
        try:
            url = f"{API}/repos/{self.owner}/{self.repo}/contents/{item_path}"
            params = {"ref": self.branch}
            resp = requests.get(url, headers=self.headers, params=params)
            if resp.status_code != 200:
                self.log(f"Failed to fetch file: {resp.status_code}", is_error=True)
                return
            data = resp.json()
            content = base64.b64decode(data["content"])
            save_path = filedialog.asksaveasfilename(initialfile=os.path.basename(item_path))
            if save_path:
                with open(save_path, "wb") as f:
                    f.write(content)
                self.log(f"Downloaded {item_path} to {save_path}")
        except Exception as e:
            self.log(f"Download error: {e}", is_error=True)

    def new_file(self):
        filename = simpledialog.askstring("New File", "Enter file name (including extension):")
        if not filename: return
        file_path = f"{self.current_path}/{filename}".lstrip("/")
        try:
            url = f"{API}/repos/{self.owner}/{self.repo}/contents/{file_path}"
            params = {"ref": self.branch}
            resp = requests.get(url, headers=self.headers, params=params)
            if resp.status_code == 200:
                messagebox.showerror("Error", "File already exists.")
                return
            content = "# New file\n"
            content_b64 = base64.b64encode(content.encode("utf-8")).decode("utf-8")
            commit_msg = simpledialog.askstring("Commit Message", "Enter commit message:", initialvalue=f"Create {file_path}")
            if not commit_msg: return
            payload = {"message": commit_msg, "content": content_b64, "branch": self.branch}
            put_url = f"{API}/repos/{self.owner}/{self.repo}/contents/{file_path}"
            resp = requests.put(put_url, headers=self.headers, json=payload)
            if resp.status_code in (200, 201):
                self.log(f"Created {file_path}")
                self.refresh_current()
                if messagebox.askyesno("Open Editor", "Open editor now?"):
                    self.open_file_editor(file_path)
            else:
                self.log(f"Create failed: {resp.text}", is_error=True)
        except Exception as e:
            self.log(f"Error creating file: {e}", is_error=True)

    def new_folder(self):
        foldername = simpledialog.askstring("New Folder", "Enter folder name:")
        if not foldername: return
        folder_path = f"{self.current_path}/{foldername}".lstrip("/")
        gitkeep_path = f"{folder_path}/.gitkeep"
        content = ""
        content_b64 = base64.b64encode(content.encode("utf-8")).decode("utf-8")
        commit_msg = simpledialog.askstring("Commit Message", "Enter commit message:", initialvalue=f"Create folder {foldername}")
        if not commit_msg: return
        payload = {"message": commit_msg, "content": content_b64, "branch": self.branch}
        try:
            url = f"{API}/repos/{self.owner}/{self.repo}/contents/{gitkeep_path}"
            resp = requests.put(url, headers=self.headers, json=payload)
            if resp.status_code in (200, 201):
                self.log(f"Created folder {folder_path}")
                self.refresh_current()
            else:
                self.log(f"Failed to create folder: {resp.text}", is_error=True)
        except Exception as e:
            self.log(f"Error creating folder: {e}", is_error=True)

    def upload_file(self):
        local_path = filedialog.askopenfilename(title="Select file to upload")
        if not local_path: return
        filename = os.path.basename(local_path)
        target_path = f"{self.current_path}/{filename}".lstrip("/")
        sha = None
        try:
            url = f"{API}/repos/{self.owner}/{self.repo}/contents/{target_path}"
            params = {"ref": self.branch}
            resp = requests.get(url, headers=self.headers, params=params)
            if resp.status_code == 200:
                if not messagebox.askyesno("Overwrite", f"File {target_path} already exists. Overwrite?"):
                    return
                sha = resp.json()["sha"]
        except:
            pass
        with open(local_path, "rb") as f:
            file_content = f.read()
        content_b64 = base64.b64encode(file_content).decode("utf-8")
        commit_msg = simpledialog.askstring("Commit Message", "Enter commit message:", initialvalue=f"Upload {filename}")
        if not commit_msg: return
        payload = {"message": commit_msg, "content": content_b64, "branch": self.branch}
        if sha:
            payload["sha"] = sha
        try:
            put_url = f"{API}/repos/{self.owner}/{self.repo}/contents/{target_path}"
            resp = requests.put(put_url, headers=self.headers, json=payload)
            if resp.status_code in (200, 201):
                self.log(f"Uploaded {filename} to {target_path}")
                self.refresh_current()
            else:
                self.log(f"Upload failed: {resp.text}", is_error=True)
        except Exception as e:
            self.log(f"Upload error: {e}", is_error=True)

    def show_context_menu(self, event):
        try:
            self.tree.selection_set(self.tree.identify_row(event.y))
            self.context_menu.post(event.x_root, event.y_root)
        finally:
            self.context_menu.grab_release()


# =========================================================
# MAIN APPLICATION (GitHubManager)
# =========================================================

class GitHubManager:
    def __init__(self, root):
        self.root = root
        self.root.title("Ultimate GitHub Repository Manager")
        self.root.geometry("1600x1000")
        self.root.minsize(1200, 800)

        self.repos = []
        self.pub_checks = {}
        self.priv_checks = {}
        self.upload_dirs = []

        self.build_ui()
        self.bind_shortcuts()
        self.update_login_display()

        if not refresh_auth():
            self.manual_token_login()

    def manual_token_login(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("GitHub Login")
        dialog.geometry("500x250")
        dialog.configure(bg="#0f1117")
        dialog.transient(self.root)
        dialog.grab_set()

        tk.Label(dialog, text="Enter GitHub Personal Access Token (classic)", bg="#0f1117", fg="#e6edf3",
                 font=("Segoe UI", 11)).pack(pady=(20,5))
        tk.Label(dialog, text="Token must have 'repo' and 'workflow' scopes", bg="#0f1117", fg="#9da7b3",
                 font=("Segoe UI", 9)).pack()
        token_entry = tk.Entry(dialog, width=50, show="*", bg="#1e242d", fg="#e6edf3", insertbackground="#e6edf3")
        token_entry.pack(pady=10, padx=20)
        show_var = tk.BooleanVar()
        tk.Checkbutton(dialog, text="Show token", variable=show_var, command=lambda: token_entry.config(show="" if show_var.get() else "*"),
                       bg="#0f1117", fg="#e6edf3", selectcolor="#0f1117").pack()
        save_var = tk.BooleanVar(value=True)
        tk.Checkbutton(dialog, text="Save token encrypted", variable=save_var, bg="#0f1117", fg="#e6edf3", selectcolor="#0f1117").pack()

        def do_login():
            token = token_entry.get().strip()
            if not token:
                messagebox.showerror("Error", "Token cannot be empty")
                return
            if refresh_auth(token):
                if save_var.get():
                    save_token_to_cache(token)
                dialog.destroy()
                self.load_repositories()
            else:
                messagebox.showerror("Error", "Invalid token. Please check scopes (repo, workflow).")

        tk.Button(dialog, text="Login", command=do_login, bg="#00c8ff", fg="#000", relief="flat", padx=20, pady=5).pack(pady=15)

    def build_ui(self):
        self.C = {
            "bg": "#0f1117", "panel": "#161b22", "panel2": "#1e242d",
            "border": "#2d333b", "text": "#e6edf3", "muted": "#9da7b3",
            "cyan": "#00c8ff", "cyan_hover": "#00a6d6", "danger": "#ff5c5c", "select": "#093b49"
        }
        self.root.configure(bg=self.C["bg"])

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Treeview", background=self.C["panel"], foreground=self.C["text"],
                        fieldbackground=self.C["panel"], borderwidth=0, rowheight=36,
                        font=("Segoe UI", 10))
        style.map("Treeview", background=[("selected", self.C["select"])],
                  foreground=[("selected", "#ffffff")])
        style.configure("Treeview.Heading", background=self.C["panel2"], foreground=self.C["cyan"],
                        relief="flat", borderwidth=0, font=("Segoe UI Semibold", 10))

        main_canvas = tk.Canvas(self.root, bg=self.C["bg"], highlightthickness=0)
        main_canvas.grid(row=0, column=0, sticky="nsew")
        v_scroll = tk.Scrollbar(self.root, orient="vertical", command=main_canvas.yview)
        v_scroll.grid(row=0, column=1, sticky="ns")
        main_canvas.configure(yscrollcommand=v_scroll.set)

        main_frame = tk.Frame(main_canvas, bg=self.C["bg"])
        main_canvas.create_window((0, 0), window=main_frame, anchor="nw")

        def on_frame_configure(event):
            main_canvas.configure(scrollregion=main_canvas.bbox("all"))
        main_frame.bind("<Configure>", on_frame_configure)

        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=1)

        # Top title & user
        top = tk.Frame(main_frame, bg=self.C["bg"])
        top.pack(fill="x", padx=15, pady=(10, 5))

        left_title = tk.Frame(top, bg=self.C["bg"])
        left_title.pack(side="left")
        tk.Label(left_title, text="GITHUB REPOSITORY MANAGER", bg=self.C["bg"], fg=self.C["cyan"],
                 font=("Segoe UI Semibold", 22)).pack(anchor="w")
        self.user_label = tk.Label(left_title, text=f"Logged in as: {USERNAME}", bg=self.C["bg"],
                                   fg=self.C["cyan"] if USERNAME != "Not logged in" else self.C["danger"],
                                   font=("Segoe UI", 11))
        self.user_label.pack(anchor="w", pady=(0, 5))

        login_frame = tk.Frame(top, bg=self.C["bg"])
        login_frame.pack(side="right")
        tk.Button(login_frame, text="Manual Login", command=self.manual_token_login,
                  bg=self.C["cyan"], fg="#000", relief="flat", padx=12, pady=6,
                  font=("Segoe UI Semibold", 10)).pack(side="left", padx=5)
        tk.Button(login_frame, text="Refresh Auth", command=self.refresh_auth_ui,
                  bg=self.C["panel2"], fg=self.C["cyan"], relief="flat", padx=12, pady=6,
                  font=("Segoe UI Semibold", 10)).pack(side="left")

        # Button bars
        btn_frame1 = tk.Frame(main_frame, bg=self.C["bg"])
        btn_frame1.pack(fill="x", padx=15, pady=5)
        btn_frame2 = tk.Frame(main_frame, bg=self.C["bg"])
        btn_frame2.pack(fill="x", padx=15, pady=5)

        def btn(parent, text, cmd, color=None):
            bg_c = color if color else self.C["cyan"]
            fg_c = "#ffffff" if color else "#000000"
            b = tk.Button(parent, text=text, command=cmd, bg=bg_c, fg=fg_c,
                          activebackground=self.C["cyan_hover"], activeforeground="#fff",
                          relief="flat", bd=0, padx=18, pady=8, cursor="hand2",
                          font=("Segoe UI Semibold", 9))
            b.pack(side="left", padx=4)
            return b

        btn(btn_frame1, "Fetch Repos", self.load_repositories)
        btn(btn_frame1, "Make Private", self.make_private)
        btn(btn_frame1, "Make Public", self.make_public)
        btn(btn_frame1, "Rename", self.rename_repo)
        btn(btn_frame1, "Download ZIP", self.download_repo)
        btn(btn_frame1, "Clone Selected", self.clone_repos)
        btn(btn_frame1, "Open Explorer", self.open_repo_explorer)

        btn(btn_frame2, "Star Selected", self.star_selected)
        btn(btn_frame2, "Unstar Selected", self.unstar_selected)
        btn(btn_frame2, "Export CSV", self.export_csv)
        btn(btn_frame2, "Generate Report", self.generate_report)
        btn(btn_frame2, "Delete", self.delete_repo, self.C["danger"])

        # Search & filter
        filter_frame = tk.Frame(main_frame, bg=self.C["panel"], highlightbackground=self.C["border"], highlightthickness=1)
        filter_frame.pack(fill="x", padx=15, pady=(10, 10))

        tk.Label(filter_frame, text="Search:", bg=self.C["panel"], fg=self.C["text"],
                 font=("Segoe UI Semibold", 10)).pack(side="left", padx=(12, 8), pady=8)
        self.search_var = tk.StringVar()
        search_entry = tk.Entry(filter_frame, textvariable=self.search_var, bg=self.C["panel2"], fg=self.C["text"],
                                insertbackground=self.C["text"], relief="flat", bd=0, font=("Segoe UI", 10), width=30)
        search_entry.pack(side="left", padx=5, pady=6, ipady=4)
        search_entry.bind("<KeyRelease>", lambda e: self.filter_repos())

        tk.Label(filter_frame, text="Min Stars:", bg=self.C["panel"], fg=self.C["text"],
                 font=("Segoe UI Semibold", 10)).pack(side="left", padx=(20, 8), pady=8)
        self.stars_var = tk.IntVar(value=0)
        stars_spin = tk.Spinbox(filter_frame, from_=0, to=100000, textvariable=self.stars_var, width=8,
                                bg=self.C["panel2"], fg=self.C["text"], relief="flat", bd=0)
        stars_spin.pack(side="left", padx=5, pady=6)
        stars_spin.bind("<KeyRelease>", lambda e: self.filter_repos())

        # Upload panel
        upload_frame = tk.LabelFrame(main_frame, text="📁 UPLOAD PROJECTS TO GITHUB", bg=self.C["panel"],
                                     fg=self.C["cyan"], font=("Segoe UI Semibold", 11),
                                     highlightbackground=self.C["border"], highlightthickness=1)
        upload_frame.pack(fill="x", padx=15, pady=(5, 10))

        list_frame = tk.Frame(upload_frame, bg=self.C["panel"])
        list_frame.pack(fill="x", padx=10, pady=10)
        self.dir_listbox = tk.Listbox(list_frame, height=4, bg=self.C["panel2"], fg=self.C["text"],
                                      selectmode=tk.EXTENDED, relief="flat", bd=0)
        self.dir_listbox.pack(side="left", fill="both", expand=True, padx=(0,10))
        scroll_dir = tk.Scrollbar(list_frame, orient="vertical", command=self.dir_listbox.yview)
        scroll_dir.pack(side="right", fill="y")
        self.dir_listbox.configure(yscrollcommand=scroll_dir.set)

        upload_btn_frame = tk.Frame(upload_frame, bg=self.C["panel"])
        upload_btn_frame.pack(fill="x", padx=10, pady=(0,10))
        tk.Button(upload_btn_frame, text="➕ Add Directory", command=self.add_directory,
                  bg=self.C["panel2"], fg=self.C["cyan"], relief="flat", padx=12, pady=5).pack(side="left", padx=5)
        tk.Button(upload_btn_frame, text="❌ Remove Selected", command=self.remove_selected_dirs,
                  bg=self.C["panel2"], fg=self.C["danger"], relief="flat", padx=12, pady=5).pack(side="left", padx=5)
        tk.Button(upload_btn_frame, text="🚀 Upload All (as new repos)", command=self.upload_all_directories,
                  bg=self.C["cyan"], fg="#000", relief="flat", padx=15, pady=5).pack(side="left", padx=20)
        self.repo_visibility = tk.StringVar(value="private")
        tk.Radiobutton(upload_btn_frame, text="Public", variable=self.repo_visibility, value="public",
                       bg=self.C["panel"], fg=self.C["text"], selectcolor=self.C["panel"]).pack(side="left", padx=10)
        tk.Radiobutton(upload_btn_frame, text="Private", variable=self.repo_visibility, value="private",
                       bg=self.C["panel"], fg=self.C["text"], selectcolor=self.C["panel"]).pack(side="left")

        # Repositories panels (public / private)
        panels_container = tk.Frame(main_frame, bg=self.C["bg"])
        panels_container.pack(fill="both", expand=True, padx=15, pady=(5, 10))

        # Public panel
        public_frame = tk.Frame(panels_container, bg=self.C["panel"], highlightbackground=self.C["border"], highlightthickness=1)
        public_frame.pack(fill="both", expand=True, side="left", padx=(0, 6))
        header_pub = tk.Frame(public_frame, bg=self.C["panel"])
        header_pub.pack(fill="x", padx=10, pady=(8, 5))
        tk.Label(header_pub, text="PUBLIC REPOSITORIES", bg=self.C["panel"], fg=self.C["cyan"],
                 font=("Segoe UI Semibold", 12)).pack(side="left")
        tk.Button(header_pub, text="Select All", command=self.select_all_public,
                  bg=self.C["panel2"], fg=self.C["cyan"], relief="flat", padx=8, pady=2).pack(side="right", padx=2)
        tk.Button(header_pub, text="Clear All", command=self.clear_all_public,
                  bg=self.C["panel2"], fg=self.C["cyan"], relief="flat", padx=8, pady=2).pack(side="right", padx=2)

        tree_container_pub = tk.Frame(public_frame, bg=self.C["panel"])
        tree_container_pub.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        columns = ("Select", "Repository", "Language", "Stars", "Forks", "Size (MB)")
        self.public_tree = ttk.Treeview(tree_container_pub, columns=columns, show="headings", selectmode="none")
        self._setup_tree_columns(self.public_tree, columns)
        self.public_tree.pack(side="left", fill="both", expand=True)
        pub_scroll = ttk.Scrollbar(tree_container_pub, orient="vertical", command=self.public_tree.yview)
        pub_scroll.pack(side="right", fill="y")
        self.public_tree.configure(yscrollcommand=pub_scroll.set)
        self.public_tree.bind("<ButtonRelease-1>", self.on_public_check_click)
        self.public_tree.bind("<Double-1>", self.on_repo_double_click)
        for col in columns[1:]:
            self.public_tree.heading(col, text=col, command=lambda c=col, tree=self.public_tree: self.sort_treeview(tree, c))

        # Private panel
        private_frame = tk.Frame(panels_container, bg=self.C["panel"], highlightbackground=self.C["border"], highlightthickness=1)
        private_frame.pack(fill="both", expand=True, side="right", padx=(6, 0))
        header_priv = tk.Frame(private_frame, bg=self.C["panel"])
        header_priv.pack(fill="x", padx=10, pady=(8, 5))
        tk.Label(header_priv, text="PRIVATE REPOSITORIES", bg=self.C["panel"], fg=self.C["cyan"],
                 font=("Segoe UI Semibold", 12)).pack(side="left")
        tk.Button(header_priv, text="Select All", command=self.select_all_private,
                  bg=self.C["panel2"], fg=self.C["cyan"], relief="flat", padx=8, pady=2).pack(side="right", padx=2)
        tk.Button(header_priv, text="Clear All", command=self.clear_all_private,
                  bg=self.C["panel2"], fg=self.C["cyan"], relief="flat", padx=8, pady=2).pack(side="right", padx=2)

        tree_container_priv = tk.Frame(private_frame, bg=self.C["panel"])
        tree_container_priv.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.private_tree = ttk.Treeview(tree_container_priv, columns=columns, show="headings", selectmode="none")
        self._setup_tree_columns(self.private_tree, columns)
        self.private_tree.pack(side="left", fill="both", expand=True)
        priv_scroll = ttk.Scrollbar(tree_container_priv, orient="vertical", command=self.private_tree.yview)
        priv_scroll.pack(side="right", fill="y")
        self.private_tree.configure(yscrollcommand=priv_scroll.set)
        self.private_tree.bind("<ButtonRelease-1>", self.on_private_check_click)
        self.private_tree.bind("<Double-1>", self.on_repo_double_click)
        for col in columns[1:]:
            self.private_tree.heading(col, text=col, command=lambda c=col, tree=self.private_tree: self.sort_treeview(tree, c))

        # Action log
        log_frame = tk.Frame(main_frame, bg=self.C["panel"], highlightbackground=self.C["border"], highlightthickness=1)
        log_frame.pack(fill="x", padx=15, pady=(5, 10))
        tk.Label(log_frame, text="ACTION LOG", bg=self.C["panel"], fg=self.C["cyan"],
                 font=("Segoe UI Semibold", 10)).pack(anchor="w", padx=10, pady=(5,0))
        self.log_text = tk.Text(log_frame, height=5, bg=self.C["panel2"], fg=self.C["text"],
                                relief="flat", wrap="word", font=("Consolas", 9))
        self.log_text.pack(fill="x", padx=10, pady=(5,8))
        log_scroll = tk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        log_scroll.pack(side="right", fill="y", padx=(0,10), pady=(5,8))
        self.log_text.configure(yscrollcommand=log_scroll.set)

        # Status bar & progress
        self.status_bar = tk.Label(main_frame, text="Ready", bd=1, relief="sunken", anchor="w",
                                   bg=self.C["panel2"], fg=self.C["text"])
        self.status_bar.pack(fill="x", side="bottom")
        self.progress_frame = tk.Frame(main_frame, bg=self.C["bg"])
        self.progress_frame.pack(fill="x", padx=15, pady=(0,5))
        self.progress = ttk.Progressbar(self.progress_frame, mode='determinate', length=300)
        self.progress.pack(side="left", padx=5)
        self.progress_label = tk.Label(self.progress_frame, text="", bg=self.C["bg"], fg=self.C["text"])
        self.progress_label.pack(side="left", padx=5)
        self.progress_frame.pack_forget()

        main_frame.update_idletasks()
        main_canvas.configure(scrollregion=main_canvas.bbox("all"))

        def _on_mousewheel(event):
            main_canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        main_canvas.bind_all("<MouseWheel>", _on_mousewheel)

    def _setup_tree_columns(self, tree, columns):
        tree.heading("Select", text="☐")
        tree.column("Select", width=50, anchor="center", minwidth=40)
        tree.heading("Repository", text="Repository")
        tree.column("Repository", width=220, anchor="w", minwidth=150)
        tree.heading("Language", text="Language")
        tree.column("Language", width=120, anchor="center", minwidth=80)
        tree.heading("Stars", text="Stars")
        tree.column("Stars", width=80, anchor="center", minwidth=60)
        tree.heading("Forks", text="Forks")
        tree.column("Forks", width=80, anchor="center", minwidth=60)
        tree.heading("Size (MB)", text="Size (MB)")
        tree.column("Size (MB)", width=90, anchor="center", minwidth=70)

    def sort_treeview(self, tree, col):
        data = [(tree.set(child, col), child) for child in tree.get_children('')]
        if col in ("Stars", "Forks", "Size (MB)"):
            data.sort(key=lambda x: float(x[0]) if x[0].replace('.','',1).isdigit() else 0, reverse=False)
        else:
            data.sort(key=lambda x: x[0].lower())
        for index, (val, child) in enumerate(data):
            tree.move(child, '', index)

    # Checkbox handlers
    def set_check(self, tree, item_id, checked):
        tree.set(item_id, "Select", "☑" if checked else "☐")
        if tree == self.public_tree:
            self.pub_checks[item_id] = checked
        else:
            self.priv_checks[item_id] = checked

    def toggle_check(self, tree, item_id):
        current = self.is_checked(tree, item_id)
        self.set_check(tree, item_id, not current)

    def is_checked(self, tree, item_id):
        if tree == self.public_tree:
            return self.pub_checks.get(item_id, False)
        else:
            return self.priv_checks.get(item_id, False)

    def on_public_check_click(self, event):
        region = self.public_tree.identify_region(event.x, event.y)
        if region == "cell":
            col = self.public_tree.identify_column(event.x)
            if col == "#1":
                item = self.public_tree.identify_row(event.y)
                if item:
                    self.toggle_check(self.public_tree, item)

    def on_private_check_click(self, event):
        region = self.private_tree.identify_region(event.x, event.y)
        if region == "cell":
            col = self.private_tree.identify_column(event.x)
            if col == "#1":
                item = self.private_tree.identify_row(event.y)
                if item:
                    self.toggle_check(self.private_tree, item)

    def select_all_public(self):
        for item in self.public_tree.get_children():
            self.set_check(self.public_tree, item, True)

    def clear_all_public(self):
        for item in self.public_tree.get_children():
            self.set_check(self.public_tree, item, False)

    def select_all_private(self):
        for item in self.private_tree.get_children():
            self.set_check(self.private_tree, item, True)

    def clear_all_private(self):
        for item in self.private_tree.get_children():
            self.set_check(self.private_tree, item, False)

    def log_action(self, message, level="info"):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_text.see(tk.END)
        self.status_bar.config(text=message)

    def show_progress(self, total, label=""):
        self.progress_frame.pack(fill="x", padx=15, pady=(0,5))
        self.progress['maximum'] = total
        self.progress['value'] = 0
        self.progress_label.config(text=label)
        self.root.update_idletasks()

    def update_progress(self, value, label=None):
        self.progress['value'] = value
        if label:
            self.progress_label.config(text=label)
        self.root.update_idletasks()

    def hide_progress(self):
        self.progress_frame.pack_forget()

    def refresh_auth_ui(self):
        if refresh_auth():
            self.log_action(f"Authentication refreshed. Logged in as {USERNAME}")
            self.update_login_display()
            if messagebox.askyesno("Reload", "Reload repositories now?"):
                self.load_repositories()
        else:
            self.log_action("Not authenticated. Please login.", "error")
            self.manual_token_login()

    def update_login_display(self):
        self.user_label.config(text=f"Logged in as: {USERNAME}")
        if USERNAME == "Not logged in":
            self.user_label.config(foreground=self.C["danger"])
        else:
            self.user_label.config(foreground=self.C["cyan"])

    def load_repositories(self):
        if not HEADERS:
            messagebox.showerror("Not Authenticated", "Please login first.")
            return
        try:
            self.log_action("Fetching repositories...")
            self.repos = fetch_repositories()
            self.render_repositories(self.repos)
            self.log_action(f"Loaded {len(self.repos)} repositories.")
        except Exception as e:
            self.log_action(f"Error: {str(e)}", "error")
            messagebox.showerror("Error", str(e))

    def render_repositories(self, repos):
        for tree in (self.public_tree, self.private_tree):
            for item in tree.get_children():
                tree.delete(item)
        self.pub_checks.clear()
        self.priv_checks.clear()

        for repo in repos:
            size_mb = round(repo["size"] / 1024, 1)
            values = ("☐", repo["name"], repo["language"] or "-",
                      repo["stargazers_count"], repo["forks_count"], size_mb)
            target = self.private_tree if repo["private"] else self.public_tree
            item_id = target.insert("", "end", values=values)
            target.item(item_id, tags=(repo["owner"]["login"], repo["default_branch"]))
            if target == self.public_tree:
                self.pub_checks[item_id] = False
            else:
                self.priv_checks[item_id] = False

    def filter_repos(self, event=None):
        keyword = self.search_var.get().lower()
        min_stars = self.stars_var.get()
        filtered = []
        for r in self.repos:
            if keyword and keyword not in r["name"].lower():
                continue
            if r["stargazers_count"] < min_stars:
                continue
            filtered.append(r)
        self.render_repositories(filtered)

    def get_selected_repo_names(self):
        selected = []
        for item, checked in self.pub_checks.items():
            if checked:
                name = self.public_tree.item(item, "values")[1]
                selected.append(name)
        for item, checked in self.priv_checks.items():
            if checked:
                name = self.private_tree.item(item, "values")[1]
                selected.append(name)
        return selected

    def get_selected_repo_objects(self):
        selected_names = self.get_selected_repo_names()
        return [r for r in self.repos if r["name"] in selected_names]

    def get_single_selected_repo(self):
        selected = self.get_selected_repo_objects()
        if len(selected) == 1:
            return selected[0]
        return None

    def open_repo_explorer(self):
        repo = self.get_single_selected_repo()
        if not repo:
            messagebox.showwarning("Selection", "Please select exactly one repository to open in explorer.")
            return
        if not HEADERS:
            messagebox.showerror("Not Authenticated", "Please login first.")
            return
        owner = repo["owner"]["login"]
        name = repo["name"]
        branch = repo["default_branch"]
        try:
            RepoExplorer(self.root, owner, name, branch, HEADERS)
        except Exception as e:
            self.log_action(f"Failed to open explorer: {e}", "error")
            messagebox.showerror("Error", str(e))

    def on_repo_double_click(self, event):
        widget = event.widget
        region = widget.identify_region(event.x, event.y)
        if region == "cell":
            col = widget.identify_column(event.x)
            if col == "#1":
                return
            item = widget.identify_row(event.y)
            if item:
                values = widget.item(item, "values")
                if values:
                    repo_name = values[1]
                    repo = next((r for r in self.repos if r["name"] == repo_name), None)
                    if repo:
                        self.open_repo_explorer_for_repo(repo)

    def open_repo_explorer_for_repo(self, repo):
        if not HEADERS:
            messagebox.showerror("Not Authenticated", "Please login first.")
            return
        owner = repo["owner"]["login"]
        name = repo["name"]
        branch = repo["default_branch"]
        try:
            RepoExplorer(self.root, owner, name, branch, HEADERS)
        except Exception as e:
            self.log_action(f"Failed to open explorer: {e}", "error")
            messagebox.showerror("Error", str(e))

    def bulk_operation(self, operation_func, success_msg, action_verb):
        selected = self.get_selected_repo_objects()
        if not selected:
            self.log_action("No repositories selected.")
            return
        total = len(selected)
        self.show_progress(total, f"{action_verb}...")
        for i, repo in enumerate(selected):
            try:
                operation_func(repo)
                self.log_action(f"{action_verb} {repo['name']}")
            except Exception as e:
                self.log_action(f"Failed on {repo['name']}: {e}", "error")
            self.update_progress(i+1, f"{action_verb} ({i+1}/{total})")
        self.hide_progress()
        self.load_repositories()
        self.log_action(f"{success_msg} ({total} repositories).")

    def make_private(self):
        self.bulk_operation(lambda r: set_visibility(r["owner"]["login"], r["name"], True), "Made private", "Making private")

    def make_public(self):
        self.bulk_operation(lambda r: set_visibility(r["owner"]["login"], r["name"], False), "Made public", "Making public")

    def delete_repo(self):
        selected = self.get_selected_repo_objects()
        if not selected:
            return
        if not messagebox.askyesno("Delete", f"Delete {len(selected)} repo(s)?\nTHIS CANNOT BE UNDONE."):
            return
        self.bulk_operation(lambda r: delete_repository(r["owner"]["login"], r["name"]), "Deleted", "Deleting")

    def star_selected(self):
        self.bulk_operation(lambda r: star_repository(r["owner"]["login"], r["name"]), "Starred", "Starring")

    def unstar_selected(self):
        self.bulk_operation(lambda r: unstar_repository(r["owner"]["login"], r["name"]), "Unstarred", "Unstarring")

    def rename_repo(self):
        selected = self.get_selected_repo_names()
        if len(selected) != 1:
            messagebox.showwarning("Warning", "Select exactly ONE repository to rename.")
            return
        old = selected[0]
        new = simpledialog.askstring("Rename", f"New name for '{old}':")
        if not new:
            return
        for repo in self.repos:
            if repo["name"] == old:
                rename_repository(repo["owner"]["login"], old, new)
                break
        self.load_repositories()
        self.log_action(f"Renamed '{old}' to '{new}'.")

    def download_repo(self):
        selected = self.get_selected_repo_objects()
        if len(selected) != 1:
            messagebox.showwarning("Warning", "Select exactly ONE repository to download ZIP.")
            return
        repo = selected[0]
        try:
            filename = download_repository(repo)
            self.log_action(f"Downloaded {filename}")
            messagebox.showinfo("Downloaded", f"{filename} saved.")
        except Exception as e:
            self.log_action(f"Download failed: {e}", "error")

    def clone_repos(self):
        selected = self.get_selected_repo_objects()
        if not selected:
            self.log_action("No repositories selected to clone.")
            return
        dest_dir = filedialog.askdirectory(title="Select destination folder")
        if not dest_dir:
            return
        total = len(selected)
        self.show_progress(total, "Cloning...")
        for i, repo in enumerate(selected):
            clone_url = repo["clone_url"]
            repo_path = os.path.join(dest_dir, repo["name"])
            try:
                self.log_action(f"Cloning {repo['name']}...")
                subprocess.run(["git", "clone", clone_url, repo_path], check=True, capture_output=True)
                self.log_action(f"Cloned {repo['name']}")
            except subprocess.CalledProcessError as e:
                self.log_action(f"Clone failed for {repo['name']}: {e.stderr.decode()}", "error")
            self.update_progress(i+1, f"Cloning ({i+1}/{total})")
        self.hide_progress()
        self.log_action(f"Cloned {total} repositories to {dest_dir}")

    def export_csv(self):
        if not self.repos:
            self.log_action("No repositories to export.")
            return
        filename = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV files", "*.csv")])
        if not filename:
            return
        try:
            with open(filename, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(["Name", "Owner", "Private", "Language", "Stars", "Forks", "Size (MB)", "URL"])
                for r in self.repos:
                    writer.writerow([r["name"], r["owner"]["login"], r["private"], r["language"] or "-",
                                     r["stargazers_count"], r["forks_count"], round(r["size"]/1024,1), r["html_url"]])
            self.log_action(f"Exported to {filename}")
            messagebox.showinfo("Export", f"Exported {len(self.repos)} repositories.")
        except Exception as e:
            self.log_action(f"Export failed: {e}", "error")

    def generate_report(self):
        if not self.repos:
            messagebox.showwarning("Warning", "Load repositories first.")
            return
        try:
            report = generate_html(self.repos)
            webbrowser.open(str(report))
            self.log_action(f"Report generated: {report}")
        except Exception as e:
            self.log_action(f"Report generation failed: {e}", "error")

    def add_directory(self):
        dir_path = filedialog.askdirectory(title="Select project folder (will become a new repo)")
        if dir_path and dir_path not in self.upload_dirs:
            self.upload_dirs.append(dir_path)
            self.dir_listbox.insert(tk.END, dir_path)

    def remove_selected_dirs(self):
        selected = self.dir_listbox.curselection()
        for i in reversed(selected):
            del self.upload_dirs[i]
            self.dir_listbox.delete(i)

    # =========================================================
    # FIXED: Upload via API + Git (no gh CLI)
    # =========================================================
    def upload_all_directories(self):
        if not self.upload_dirs:
            messagebox.showwarning("No directories", "Please add at least one directory first.")
            return
        if not TOKEN:
            messagebox.showerror("Not authenticated", "Please login first.")
            return

        visibility = self.repo_visibility.get()
        total = len(self.upload_dirs)
        self.show_progress(total, "Uploading...")
        success_count = 0

        for idx, dir_path in enumerate(self.upload_dirs):
            repo_name = os.path.basename(dir_path.rstrip("/\\"))
            # sanitise repo name (GitHub rules)
            repo_name = "".join(c for c in repo_name if c.isalnum() or c in "-_.").strip(".-")
            if not repo_name:
                repo_name = f"project_{idx}"

            self.log_action(f"Uploading '{repo_name}' from {dir_path}...")
            try:
                # 1. Create repository via GitHub API
                create_url = f"{API}/user/repos"
                payload = {
                    "name": repo_name,
                    "private": (visibility == "private"),
                    "auto_init": False,
                    "description": f"Uploaded from {dir_path}"
                }
                resp = requests.post(create_url, headers=HEADERS, json=payload)
                if resp.status_code == 422 and "name already exists" in resp.text:
                    self.log_action(f"Repository '{repo_name}' already exists. Skipping.", "warning")
                    continue
                if resp.status_code not in (200, 201):
                    self.log_action(f"Failed to create repo '{repo_name}': {resp.text}", "error")
                    continue
                repo_data = resp.json()
                clone_url = repo_data["clone_url"]          # https://github.com/owner/repo.git
                # 2. Inject token into clone URL for authentication
                auth_url = clone_url.replace("https://", f"https://{TOKEN}@")
                # 3. Prepare temporary directory and push
                with tempfile.TemporaryDirectory() as tmpdir:
                    dest = os.path.join(tmpdir, repo_name)
                    shutil.copytree(dir_path, dest, symlinks=False, ignore_dangling_symlinks=True)
                    # Git commands (all run inside dest)
                    subprocess.run(["git", "init"], cwd=dest, check=True, capture_output=True)
                    subprocess.run(["git", "add", "."], cwd=dest, check=True, capture_output=True)
                    subprocess.run(["git", "commit", "-m", "Initial upload from GitHub Manager"], cwd=dest, check=True, capture_output=True)
                    subprocess.run(["git", "remote", "add", "origin", auth_url], cwd=dest, check=True, capture_output=True)
                    subprocess.run(["git", "push", "-u", "origin", "HEAD:main", "--force"], cwd=dest, check=True, capture_output=True)
                self.log_action(f"Successfully uploaded '{repo_name}'")
                success_count += 1
            except subprocess.CalledProcessError as e:
                error_msg = e.stderr.decode() if e.stderr else str(e)
                self.log_action(f"Upload failed for '{repo_name}': {error_msg}", "error")
            except Exception as e:
                self.log_action(f"Unexpected error for '{repo_name}': {e}", "error")
            self.update_progress(idx+1, f"Uploaded {success_count}/{idx+1} so far...")

        self.hide_progress()
        self.log_action(f"Upload complete. {success_count} out of {total} repositories created.")
        messagebox.showinfo("Upload Finished", f"Successfully uploaded {success_count}/{total} projects.")
        self.load_repositories()

    def bind_shortcuts(self):
        self.root.bind("<Control-f>", lambda e: self.focus_search())
        self.root.bind("<Control-a>", lambda e: self.select_all_current_panel())
        self.root.bind("<Delete>", lambda e: self.delete_repo())
        self.root.bind("<Control-d>", lambda e: self.download_repo())
        self.root.bind("<Control-e>", lambda e: self.open_repo_explorer())

    def focus_search(self):
        for child in self.root.winfo_children():
            if isinstance(child, tk.Tk):
                continue
            for widget in child.winfo_children():
                if isinstance(widget, tk.Entry) and hasattr(widget, 'textvariable') and widget.textvariable == self.search_var:
                    widget.focus_set()
                    return

    def select_all_current_panel(self):
        focused = self.root.focus_get()
        if focused == self.public_tree:
            self.select_all_public()
        elif focused == self.private_tree:
            self.select_all_private()
        else:
            self.select_all_public()
            self.select_all_private()

# =========================================================
# MAIN
# =========================================================

if __name__ == "__main__":
    root = tk.Tk()
    app = GitHubManager(root)
    root.mainloop()