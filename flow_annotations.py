"""Anotações visuais como base de edição, conforme o canvas do frontend Flow."""

import base64
import math
import re
import tempfile
from pathlib import Path


def validate_annotations(selection, drawings):
    def points(value, minimum):
        if (type(value) is not list or not minimum <= len(value) <= 500
                or any(type(p) is not list or len(p) != 2
                       or any(type(v) not in {int, float} or not math.isfinite(v)
                              or not 0 <= v <= 1 for v in p) for p in value)):
            raise ValueError("Pontos devem ser pares [x, y] entre 0 e 1.")

    if selection is not None:
        points(selection, 3)
        area = sum(p[0] * q[1] - q[0] * p[1]
                   for p, q in zip(selection, selection[1:] + selection[:1]))
        if abs(area) < 1e-8:
            raise ValueError("Seleção deve ter área positiva.")
    if drawings is not None:
        if type(drawings) is not list or not 1 <= len(drawings) <= 20:
            raise ValueError("Informe de 1 a 20 traços.")
        for drawing in drawings:
            if type(drawing) is not dict or set(drawing) - {"points", "color", "width"}:
                raise ValueError("Traço aceita somente points, color e width.")
            points(drawing.get("points"), 2)
            color, width = drawing.get("color", "#ff0000"), drawing.get("width", 4)
            if (not isinstance(color, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", color)
                    or type(width) not in {int, float} or not math.isfinite(width)
                    or not 1 <= width <= 100):
                raise ValueError("Cor deve ser #RRGGBB e largura deve estar entre 1 e 100 pixels.")


RENDER_ANNOTATIONS = """async ({image, selection, drawings}) => {
    const source = new Image();
    source.src = image;
    await source.decode();
    const width = source.naturalWidth, height = source.naturalHeight;
    if (!width || !height || width * height > 16777216)
        throw new Error('Image dimensions unavailable or too large');
    const canvas = document.createElement('canvas');
    canvas.width = width; canvas.height = height;
    const ctx = canvas.getContext('2d');
    ctx.drawImage(source, 0, 0);
    const path = points => {
        ctx.beginPath();
        points.forEach(([x, y], i) => i ? ctx.lineTo(x * width, y * height)
                                             : ctx.moveTo(x * width, y * height));
    };
    if (selection) {
        path(selection); ctx.closePath();
        ctx.fillStyle = 'rgba(218, 220, 224, 0.25)'; ctx.fill();
        ctx.lineWidth = 1; ctx.strokeStyle = 'white'; ctx.stroke();
        ctx.setLineDash([8, 4]); ctx.strokeStyle = 'black'; ctx.stroke();
        ctx.setLineDash([]);
    }
    for (const drawing of drawings || []) {
        path(drawing.points); ctx.lineWidth = drawing.width || 4;
        ctx.strokeStyle = drawing.color || '#ff0000';
        ctx.lineCap = 'round'; ctx.lineJoin = 'round'; ctx.stroke();
    }
    return canvas.toDataURL('image/png').split(',')[1];
}"""


async def upload_annotated_image(client, project_id, body, selection, drawings):
    from flow_assets import upload_image
    from flow_browser import account_page
    from flow_video import image_suffix

    if len(body) > 20 * 1024 * 1024:
        raise ValueError("Imagem de anotação acima de 20 MB.")
    mime = {".png": "image/png", ".jpg": "image/jpeg", ".webp": "image/webp"}[image_suffix(body)]
    pages = client.browser.page() if client.browser is not None else account_page(client.account_id)
    async with pages as page:
        encoded = await page.evaluate(RENDER_ANNOTATIONS, {
            "image": f"data:{mime};base64," + base64.b64encode(body).decode("ascii"),
            "selection": selection, "drawings": drawings,
        })
    annotated = base64.b64decode(encoded, validate=True)
    image_suffix(annotated)
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "flow-annotated.png"
        path.write_bytes(annotated)
        return await upload_image(client.account_id, project_id, str(path), client=client)
