"""Decrypt TrueNAS pwenc-encrypted database fields.

The encryption scheme is derived from the TrueNAS Core middleware, file
    sources/middleware/src/middlewared/middlewared/plugins/pwenc.py
(functions ``encrypt``/``decrypt``). It is AES-256-CTR:

  * key   = the 32 raw bytes of ``pwenc_secret`` (shipped in the export tar when
            "Export Secret Seed" is enabled),
  * the stored value is base64(nonce || ciphertext) with an 8-byte random nonce,
  * the CTR counter is 64 bits wide and prefixed by the nonce; pycryptodome's
    ``Counter.new(64, prefix=nonce)`` starts at initial value 1, so the 128-bit
    IV is ``nonce || (1).to_bytes(8, "big")``,
  * plaintext is padded with the byte ``{`` to a 32-byte boundary before
    encryption and stripped again on decrypt.

Decryption is performed by shelling out to openssl(1) to avoid a third-party
Python crypto dependency.
"""
import base64
import json
import subprocess

PADDING = b"{"


class PwencError(RuntimeError):
    pass


def decrypt(secret, encrypted):
    """Decrypt a single pwenc value. Returns the plaintext string ('' if empty)."""
    if not encrypted:
        return ""
    raw = base64.b64decode(encrypted)
    nonce, ciphertext = raw[:8], raw[8:]
    iv = nonce + (1).to_bytes(8, "big")
    try:
        result = subprocess.run(
            [
                "openssl", "enc", "-aes-256-ctr", "-d", "-nopad",
                "-K", secret.hex(),
                "-iv", iv.hex(),
            ],
            input=ciphertext,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
    except FileNotFoundError as exc:
        raise PwencError("openssl(1) is required to decrypt pwenc fields") from exc
    except subprocess.CalledProcessError as exc:
        raise PwencError(f"openssl failed to decrypt pwenc field: {exc.stderr!r}") from exc
    return result.stdout.rstrip(PADDING).decode("utf8")


def decrypt_json(secret, encrypted):
    """Decrypt a pwenc value that holds a JSON document and parse it."""
    plaintext = decrypt(secret, encrypted)
    return json.loads(plaintext) if plaintext else {}
