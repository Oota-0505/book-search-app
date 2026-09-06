"""VAPID 鍵ペアを生成する。

    .venv/bin/python tools/make_vapid.py

秘密鍵は book_search_app/data/vapid_private.pem に保存する（.gitignore 済み）。
公開鍵はブラウザに渡す文字列として表示する。
"""

from __future__ import annotations

import base64
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

DATA_DIR = Path(__file__).resolve().parent.parent / "book_search_app" / "data"
PRIVATE_KEY_PATH = DATA_DIR / "vapid_private.pem"


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if PRIVATE_KEY_PATH.exists():
        print(f"既に存在します: {PRIVATE_KEY_PATH}")
        print("作り直すと既存の購読がすべて無効になります。消してから再実行してください。")
        private_key = serialization.load_pem_private_key(
            PRIVATE_KEY_PATH.read_bytes(), password=None
        )
    else:
        private_key = ec.generate_private_key(ec.SECP256R1())
        PRIVATE_KEY_PATH.write_bytes(
            private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )
        PRIVATE_KEY_PATH.chmod(0o600)
        print(f"秘密鍵を保存しました: {PRIVATE_KEY_PATH}")

    # ブラウザに渡す applicationServerKey（非圧縮形式の base64url）
    raw = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint,
    )
    public_key = base64.urlsafe_b64encode(raw).decode().rstrip("=")

    print()
    print("VAPID_PUBLIC_KEY（config.py に貼る）:")
    print(f'  "{public_key}"')


if __name__ == "__main__":
    main()