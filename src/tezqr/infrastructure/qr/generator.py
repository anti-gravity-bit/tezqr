from __future__ import annotations

from io import BytesIO

import qrcode

from tezqr.application.ports import QrCodeGenerator


class QRCodeGeneratorService(QrCodeGenerator):
    async def generate_png(self, data: str) -> bytes:
        qr_code = qrcode.QRCode(box_size=8, border=2)
        qr_code.add_data(data)
        qr_code.make(fit=True)
        image = qr_code.make_image(fill_color="black", back_color="white")
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()
