import base64
from config import Config

class SimpleCrypto:
    def __init__(self, key=None):
        self.key = key or Config.ENCRYPTION_KEY
    
    def encrypt(self, text):
        """Simple XOR encryption"""
        encrypted = ''.join(chr(ord(c) ^ ord(self.key[i % len(self.key)])) for i, c in enumerate(text))
        return base64.b64encode(encrypted.encode()).decode()
    
    def decrypt(self, encrypted_text):
        """Simple XOR decryption"""
        try:
            decoded = base64.b64decode(encrypted_text.encode()).decode()
            return ''.join(chr(ord(c) ^ ord(self.key[i % len(self.key)])) for i, c in enumerate(decoded))
        except:
            return None

# Global crypto instance
crypto = SimpleCrypto()

def test_encryption():
    """Test fungsi encryption/decryption"""
    test_password = "myjuniperpass123"
    encrypted = crypto.encrypt(test_password)
    decrypted = crypto.decrypt(encrypted)
    
    print(f"🔐 Encryption Test:")
    print(f"Original: {test_password}")
    print(f"Encrypted: {encrypted}")
    print(f"Decrypted: {decrypted}")
    print(f"Match: {test_password == decrypted}")
    
    return test_password == decrypted