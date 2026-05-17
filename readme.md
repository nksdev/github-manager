

# 🚀 Ultimate GitHub Repository Manager

A **professional, feature-rich desktop application** to manage your GitHub repositories with ease. Built with Python and Tkinter, it provides a modern dark UI, bulk operations, multi‑select checkboxes, directory uploads, cloning, CSV export, and more.



---

## ✨ Features

### 🔐 Authentication
- One‑click **GitHub Login** (opens terminal for `gh auth login`)
- **Refresh Auth** button – updates token and username without restart
- Shows currently logged‑in GitHub user

### 📦 Repository Management
- Fetch **public & private** repositories (paginated, 100 per page)
- Separate **Public / Private** panels with checkboxes
- **Sortable columns** – click header to sort by name, stars, forks, size
- **Multi‑select** – checkboxes (☐/☑) with Select All / Clear All per panel
- **Bulk operations** with progress bar:
  - Make Public / Private
  - Star / Unstar
  - Delete (with confirmation)
- **Single repo actions**:
  - Rename
  - Download as ZIP
  - Clone to local folder

### 🔍 Filtering
- Search by repository name
- Minimum stars filter

### 📤 Upload Projects to GitHub
- Select any number of **local directories**
- Each directory becomes a **new repository** (name = folder name)
- Choose visibility: **Public** or **Private**
- Automatically initialises Git, commits all files, and pushes to GitHub

### 📊 Reporting & Export
- **Export full repository list** to CSV (name, owner, visibility, language, stars, forks, size, URL)
- Generate **HTML Intelligence Report** – includes README and file trees for each repo

### ⌨️ Keyboard Shortcuts
| Shortcut | Action |
|----------|--------|
| `Ctrl+F` | Focus search box |
| `Ctrl+A` | Select all repositories in the active panel |
| `Delete` | Delete selected repositories |
| `Ctrl+D` | Download ZIP of selected repo (single selection) |

### 🖥️ User Interface
- **Fully responsive** – resizable window, scrollable main canvas
- **Dark premium theme** – high contrast, modern fonts
- **Action log** – timestamped history of all operations
- **Status bar** & **progress bar** for long tasks

---

## 📋 Requirements

- **Python 3.8+**
- **GitHub CLI** (`gh`) – [Installation guide](https://cli.github.com/)
- **Git** (for cloning & upload features)
- Python packages:
  - `requests`
  - `markdown`

---

## 🔧 Installation

### 1. Install Python packages
```bash
pip install requests markdown
```

### 2. Install GitHub CLI
- **Windows**: `winget install --id GitHub.cli` or download from [releases](https://github.com/cli/cli/releases)
- **macOS**: `brew install gh`
- **Linux**: Follow [official guide](https://github.com/cli/cli#installation)

### 3. Install Git (if not already)
- [Download Git](https://git-scm.com/downloads)

### 4. Clone or download this repository
```bash
git clone https://github.com/yourusername/ultimate-github-manager.git
cd ultimate-github-manager
```

### 5. Run the application
```bash
python github_manager.py
```

---

## 🚀 How to Use

### First run – Authentication
1. The app will check if you are already logged in with `gh`.
2. If not, click the **GitHub Login** button – a terminal window opens.
3. Follow the prompts: authenticate via browser, choose HTTPS, and optionally log in to GitHub.com.
4. After successful login, click **Refresh Auth** (top‑right). The username will appear.
5. Now click **Fetch Repos** – your repositories will load.

### Managing Repositories
- **Select** repositories by clicking the ☐ checkbox in the first column.
- Use **Select All / Clear All** buttons per panel.
- Click any **column header** to sort (Name, Language, Stars, Forks, Size).
- Use the **filter bar** to search or set a minimum star count.

### Bulk Operations
- **Make Private / Public** – changes visibility of all selected repos.
- **Star / Unstar** – stars/unstars selected repos.
- **Delete** – permanently deletes repositories (cannot be undone).
- **Clone Selected** – downloads (clones) selected repos to a chosen local folder.

### Single Repo Actions
- **Rename** – select exactly one repo, then click Rename.
- **Download ZIP** – select exactly one repo, then click Download ZIP (saves to current directory).

### Upload Local Directories
1. In the **📁 UPLOAD PROJECTS TO GITHUB** panel, click **Add Directory**.
2. Choose a folder (each folder becomes a new repository).
3. Repeat to add multiple folders.
4. Select **Public** or **Private**.
5. Click **Upload All (as new repos)**.
   - The app creates a temporary Git repo, commits all files, creates a GitHub repository with the folder name, and pushes.
   - If a repository with the same name already exists, it skips that folder.

### Export & Reporting
- **Export CSV** – saves all repository data (including metadata) to a CSV file.
- **Generate Report** – creates an HTML file with detailed analysis: README content + recursive file list for each repo. Opens automatically in your browser.

### Action Log
All operations are logged with timestamps in the bottom panel, helping you track changes.

---

## 🛠️ Troubleshooting

| Issue | Solution |
|-------|----------|
| `GitHub API Error (401)` | Not authenticated. Click **GitHub Login** and complete the login, then **Refresh Auth**. |
| `Rate limit exceeded` | The app automatically waits and retries. If frequent, reduce manual refresh rate. |
| `Upload fails: repository already exists` | The folder name matches an existing repo. Rename the folder or delete the remote repo first. |
| `git not found` | Install Git and ensure it's in your system PATH. |
| `gh not found` | Install GitHub CLI and add to PATH, then restart the app. |

---

## 📁 Project Structure

```
ultimate-github-manager/
├── github_manager.py        # Main application (this file)
├── README.md                # This file
├── requirements.txt         # Python dependencies
└── (generated files)        # github_intelligence_report.html, *.zip, etc.
```

---

## 📝 Dependencies

- **requests** – GitHub API calls
- **markdown** – Convert README to HTML for the report
- **Python standard libraries**: subprocess, tkinter, csv, base64, pathlib, shutil, tempfile, webbrowser, datetime

---

## 🤝 Contributing

Feel free to submit issues or pull requests. Suggestions:
- Add support for **GitHub Enterprise** (GHE)
- **Light theme** toggle
- **Webhook management** per repository
- **Release & asset management**
- **Dependency graph** viewer

---

## 📄 License

MIT License – use, modify, and distribute freely.

---

## ⭐ Acknowledgements

- Built with [GitHub CLI](https://cli.github.com/) for seamless authentication and repository creation.
- Uses [Markdown](https://python-markdown.github.io/) for rendering READMEs.
- Inspired by the need for a native desktop GitHub manager.

---

**Enjoy managing your GitHub repositories like a pro!**  
If you find this tool useful, don’t forget to star the repository ⭐
```


