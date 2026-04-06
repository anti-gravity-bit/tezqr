from __future__ import annotations

from io import BytesIO

import qrcode
from PIL import Image, ImageDraw, ImageFont
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


def render_payment_card_png(
    *,
    provider_name: str,
    payment_reference: str,
    description: str,
    amount: str,
    upi_uri: str,
    branding: dict[str, str],
    qr_bytes: bytes,
    print_ready: bool,
) -> bytes:
    primary = _hex_to_rgb(branding.get("primary_color", "#104252"))
    secondary = _hex_to_rgb(branding.get("secondary_color", "#FAF6F0"))
    accent = _hex_to_rgb(branding.get("accent_color", "#D97706"))
    logo_text = (branding.get("logo_text") or provider_name[:2]).strip().upper()[:8]

    width = 1600 if print_ready else 1400
    height = 1000 if print_ready else 900
    canvas = Image.new("RGB", (width, height), secondary if not print_ready else (255, 255, 255))
    draw = ImageDraw.Draw(canvas)
    title_font = _load_font(52)
    body_font = _load_font(28)
    small_font = _load_font(20)

    if not print_ready:
        draw.rounded_rectangle(
            (40, 40, width - 40, height - 40),
            radius=36,
            fill=secondary,
            outline=primary,
            width=6,
        )

    draw.rounded_rectangle(
        (70, 70, 250, 220),
        radius=32,
        fill=primary,
    )
    draw.text((125, 127), logo_text, fill=secondary, font=title_font, anchor="mm")
    draw.text((300, 100), provider_name, fill=primary, font=title_font)
    draw.text(
        (300, 165),
        "Print-ready payment QR" if print_ready else "Branded payment card",
        fill=accent,
        font=body_font,
    )

    qr_image = Image.open(BytesIO(qr_bytes)).convert("RGB").resize((420, 420))
    canvas.paste(qr_image, (width - 520, 220))

    y = 270
    for line in [
        f"Amount: Rs {amount}",
        f"Description: {description}",
        f"Reference: {payment_reference}",
    ]:
        draw.text((90, y), line, fill=primary, font=body_font)
        y += 70

    draw.rounded_rectangle(
        (80, 520, width - 560, height - 120),
        radius=30,
        fill=(255, 255, 255),
        outline=accent,
        width=4,
    )
    draw.text((110, 555), "UPI link", fill=accent, font=body_font)
    draw.multiline_text(
        (110, 610),
        _wrap_text(upi_uri, 40 if print_ready else 34),
        fill=primary,
        font=small_font,
        spacing=10,
    )
    footer = "Scan to pay or use the UPI link above."
    draw.text((90, height - 90), footer, fill=primary, font=body_font)

    output = BytesIO()
    canvas.save(output, format="PNG")
    return output.getvalue()


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    normalized = value.lstrip("#")
    if len(normalized) != 6:
        normalized = "104252"
    return tuple(int(normalized[i : i + 2], 16) for i in range(0, 6, 2))


def _load_font(size: int) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype("DejaVuSans.ttf", size)
    except OSError:
        return ImageFont.load_default()


def _wrap_text(value: str, width: int) -> str:
    chunks = [value[index : index + width] for index in range(0, len(value), width)]
    return "\n".join(chunks)
