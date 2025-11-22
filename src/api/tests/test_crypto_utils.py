from cryptography.fernet import Fernet

from chatbot.utils.crypto import decrypt_dict, encrypt_dict


def test_encrypt_decrypt_roundtrip(monkeypatch):
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("GOOGLE_TOKEN_ENC_KEY", key)

    original = {"token": "abc", "refresh_token": "def"}
    encrypted = encrypt_dict(original)

    assert encrypted != ""
    decrypted = decrypt_dict(encrypted)
    assert decrypted == original


def test_decrypt_invalid_returns_empty_dict(monkeypatch):
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("GOOGLE_TOKEN_ENC_KEY", key)

    assert decrypt_dict("invalid-token") == {}
