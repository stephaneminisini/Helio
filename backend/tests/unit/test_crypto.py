import pytest
from helio.core.crypto import encrypt, decrypt


def test_encrypt_decrypt_roundtrip():
    key = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
    plaintext = "my-secret-token"
    ciphertext = encrypt(plaintext, key)
    assert ciphertext != plaintext
    assert decrypt(ciphertext, key) == plaintext


def test_encrypt_produces_different_ciphertexts():
    key = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
    plaintext = "my-secret-token"
    assert encrypt(plaintext, key) != encrypt(plaintext, key)


def test_decrypt_wrong_key_raises():
    key1 = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
    key2 = "BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB="
    ciphertext = encrypt("secret", key1)
    with pytest.raises(Exception):
        decrypt(ciphertext, key2)
