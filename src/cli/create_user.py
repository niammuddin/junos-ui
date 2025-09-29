import argparse
import getpass
import sys
import os

# Tambahkan path root project ke Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from src.models.user import create_user
from src.utils.database import init_db

def main():
    parser = argparse.ArgumentParser(description='Buat user baru untuk sistem login')
    parser.add_argument('username', help='Username untuk user baru')
    parser.add_argument('--email', help='Email untuk user baru', default=None)
    
    args = parser.parse_args()
    
    print("=== BUAT USER BARU ===")
    print(f"Username: {args.username}")
    if args.email:
        print(f"Email: {args.email}")
    print("-" * 30)
    
    # Input password dengan validasi
    while True:
        password = getpass.getpass('Password: ')
        confirm_password = getpass.getpass('Konfirmasi Password: ')
        
        if password != confirm_password:
            print("❌ Password tidak cocok! Coba lagi.\n")
            continue
            
        if len(password) < 8:
            print("❌ Password minimal 8 karakter!\n")
            continue
            
        break
    
    # Buat user
    success, message = create_user(args.username, password, args.email)
    
    if success:
        print(f"✅ {message}")
    else:
        print(f"❌ {message}")

if __name__ == '__main__':
    init_db()
    main()