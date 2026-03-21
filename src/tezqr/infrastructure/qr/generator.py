from __future__ import annotations

from io import BytesIO

import qrcode
from qrcode.constants import ERROR_CORRECT_M
from qrcode.image.styledpil import StyledPilImage
from qrcode.image.styles.colormasks import SolidFillColorMask
from qrcode.image.styles.moduledrawers.pil import RoundedModuleDrawer

from tezqr.application.ports import QrCodeGenerator


class QRCodeGeneratorService(QrCodeGenerator):
    async def generate_png(self, data: str) -> bytes:
        qr_code = qrcode.QRCode(
            box_size=10,
            border=3,
            error_correction=ERROR_CORRECT_M,
        )
        qr_code.add_data(data)
        qr_code.make(fit=True)
        image = qr_code.make_image(
            image_factory=StyledPilImage,
            module_drawer=RoundedModuleDrawer(radius_ratio=1),
            color_mask=SolidFillColorMask(
                front_color=(16, 66, 82),
                back_color=(250, 246, 240),
            ),
        )
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()
