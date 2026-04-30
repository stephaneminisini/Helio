from cryptography.fernet import Fernet


def encrypt(plaintext: str, key: str) -> str:
    """Encrypt a plaintext string using Fernet symmetric encryption.

    Args:
        plaintext: The string to encrypt.
        key: A URL-safe base64-encoded 32-byte Fernet key.

    Returns:
        The encrypted token as a UTF-8 string.
    """
    f = Fernet(key.encode())
    return f.encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str, key: str) -> str:
    """Decrypt a Fernet-encrypted token back to plaintext.

    Args:
        ciphertext: The encrypted token string.
        key: The same Fernet key used to encrypt.

    Returns:
        The original plaintext string.

    Raises:
        cryptography.fernet.InvalidToken: If key is wrong or token is corrupted.
    """
    f = Fernet(key.encode())
    return f.decrypt(ciphertext.encode()).decode()
