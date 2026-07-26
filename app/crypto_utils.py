# -*- coding: utf-8 -*-
"""
crypto_utils.py — payslip QR code payload: encrypt, decrypt, render.

The QR code stamped on every PDF encodes a Fernet-encrypted JSON payload of
{CIN, Full Name, Net Pay, Date}. Anyone with the app's .env key can scan and
decrypt it to confirm a payslip is genuine and unaltered (Fernet is
authenticated encryption — a tampered token fails to decrypt rather than
silently decoding to wrong data).
"""
from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path
from typing import Optional

import qrcode
from cryptography.fernet import Fernet, InvalidToken
from qrcode.image.pil import PilImage


class PayslipQRCodec:
    def __init__(self, key: bytes):
        self._fernet = Fernet(key)

    def build_payload(self, cin: str, full_name: str, net_pay: float, pay_date: str) -> dict:
        return {"cin": cin, "full_name": full_name, "net_pay": round(net_pay, 2), "date": pay_date}

    def encrypt(self, payload: dict) -> str:
        raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        return self._fernet.encrypt(raw).decode("utf-8")

    def decrypt(self, token: str) -> Optional[dict]:
        """Returns the payload dict, or None if the token is invalid/tampered."""
        try:
            raw = self._fernet.decrypt(token.encode("utf-8"))
            return json.loads(raw.decode("utf-8"))
        except (InvalidToken, ValueError, json.JSONDecodeError):
            return None

    @staticmethod
    def render_qr_png(data: str, box_size: int = 8, border: int = 2) -> BytesIO:
        """Renders `data` as a QR PNG in memory (no temp file needed)."""
        qr = qrcode.QRCode(
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=box_size,
            border=border,
        )
        qr.add_data(data)
        qr.make(fit=True)
        img = qr.make_image(image_factory=PilImage, fill_color="#0F1F3D", back_color="white")
        buf = BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        return buf

    def build_and_encode_qr(self, cin: str, full_name: str, net_pay: float, pay_date: str) -> tuple[str, BytesIO]:
        """Convenience: payload -> encrypted token -> QR PNG bytes, in one call."""
        payload = self.build_payload(cin, full_name, net_pay, pay_date)
        token = self.encrypt(payload)
        png = self.render_qr_png(token)
        return token, png
