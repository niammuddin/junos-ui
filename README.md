# Junos UI

**Junos UI** adalah aplikasi berbasis **Python** yang dirancang untuk mempermudah monitoring dan manajemen router **Juniper** melalui **REST API** dan **gRPC**.  

Aplikasi ini sudah diuji dengan perangkat **Juniper MX204**, serta mendukung **multi-device** (lebih dari satu router dapat dipantau secara bersamaan).

---

## ✨ Fitur Utama

- 🔎 **System Information** – Menampilkan informasi sistem dasar router  
- ⚙️ **Route Engine** – Monitoring status dan performa route engine  
- 📡 **BGP Summary** – Ringkasan informasi sesi BGP  
- 🔍 **BGP Neighbor Detail** – Informasi detail setiap neighbor BGP  
- 📝 **Policy Option - Policy Statement** – Melihat konfigurasi policy statement  
- 🛣️ **Static Route** – Monitoring static route yang dikonfigurasi  
- 🌐 **View Interface** – Melihat daftar interface dan statusnya  
- 📊 **Live Traffic Monitoring (gRPC)** – Memantau trafik secara real-time berdasarkan interface menggunakan gRPC  

---

## 🚀 Roadmap

Fitur akan terus bertambah seiring berkembangnya kebutuhan dan jumlah pengguna.  
Jika aplikasi ini mendapat banyak peminat, maka akan dilakukan pengembangan lebih lanjut (fitur baru, optimasi performa, dan integrasi tambahan).

---

## 🖥️ Kompatibilitas

- ✅ Sudah diuji dengan **Juniper MX204**  
- 🔄 Potensial mendukung perangkat Juniper lain dengan fitur serupa  

---

## 📢 Kontribusi & Feedback

Aplikasi ini masih dalam tahap pengembangan aktif.  
Feedback, request fitur, atau kontribusi sangat terbuka untuk meningkatkan fungsionalitas **Junos UI**.

<br/><br/>
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
EnvironmentFile=-/home/junos-ui/.env
Environment="GUNICORN_BIND=0.0.0.0:8000"

ExecStart=/home/junos-ui/.venv/bin/gunicorn -c /home/junos-ui/gunicorn.conf.py "app:create_app()"

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

#### Opsi Tuning Gunicorn

Gunicorn kini menggunakan file konfigurasi `gunicorn.conf.py`. Anda bisa mengatur perilaku worker melalui environment variable tanpa mengubah file service:

- `GUNICORN_TIMEOUT`: batas waktu request (default `90` detik)
- `GUNICORN_GRACEFUL_TIMEOUT`: waktu tunggu shutdown worker (default `30`)
- `GUNICORN_WORKERS`: override jumlah worker (default `CPU * 2 + 1`)
- `GUNICORN_BIND`: alamat bind (default `0.0.0.0:PORT`)

Contoh menambah timeout di file service:

```
Environment="GUNICORN_TIMEOUT=120"
```

<br/><br/>

# 🚀 Konfig Perangkat Juniper

```bash
set system services extension-service request-response grpc clear-text port 9339
set system services extension-service request-response grpc max-connections 8
set system services extension-service request-response grpc skip-authentication
set system services rest http port 3443
```
Sesuaikan rest API menggunakan http/https dan PORT

---

### Add User

```bash
usage: create_user.py [-h] [--email EMAIL] username

Buat user baru untuk sistem login

positional arguments:
  username              Username untuk user baru

options:
  -h, --help            show this help message and exit
  --email EMAIL         Email untuk user baru
```

```bash
python3 src/cli/create_user.py username
```

