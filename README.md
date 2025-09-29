# 🚀 Panduan Deploy Junos UI

## 1. Clone Repository
Clone project dari GitHub:

```bash
mkdir /home/junos-ui
git clone https://github.com/niammuddin/junos-ui.git
cd junos-ui
````

---

## 2. Install Python Virtual Environment

Pastikan Python 3 sudah terinstall.
Buat virtual environment:

```bash
python3 -m venv .venv
```

---

## 3. Aktifkan Virtual Environment

* **Linux / macOS**

  ```bash
  source .venv/bin/activate
  ```
* **Windows (PowerShell)**

  ```powershell
  .venv\Scripts\Activate
  ```

---

## 4. Install Dependencies

Install semua paket dari `requirements.txt`:

```bash
pip install -r requirements.txt
```

---

## 5. Testing Jalankan Aplikasi

Untuk menjalankan secara langsung (tanpa gunicorn/systemd):

```bash
python app.py
```

Aplikasi akan berjalan di `http://127.0.0.1:5000` (atau sesuai setting di `app.py`).

---
<br/>
<br/>

# 🚀 Menjalankan Junos UI dengan systemd

### 1. Buat User Service
Jalankan perintah berikut untuk membuat user khusus:

```bash
sudo useradd -r -s /usr/sbin/nologin -d /home/junos-ui junos
sudo chown -R junos:junos /home/junos-ui
````

### 2. Buat File Service systemd

Buat file service:

```bash
sudo nano /etc/systemd/system/junos-ui.service
```

Isi dengan konfigurasi berikut:

```ini
[Unit]
Description=Junos UI
After=network.target

[Service]
User=junos
Group=junos

# Path ke direktori proyek
WorkingDirectory=/home/junos-ui
Environment="PATH=/home/junos-ui/.venv/bin"
EnvironmentFile=/home/junos-ui/.env

ExecStart=/home/junos-ui/.venv/bin/gunicorn --workers 2 --bind 0.0.0.0:8000 "app:create_app()"

Restart=always

[Install]
WantedBy=multi-user.target
```

### 3. Reload & Enable Service

```bash
sudo systemctl daemon-reload
sudo systemctl enable junos-ui
sudo systemctl start junos-ui
```

### 4. Cek Status Service

```bash
sudo systemctl status junos-ui
```
---

Aplikasi akan berjalan di `http://127.0.0.1:8000`

<br/>


