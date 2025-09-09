import base64
import re
from io import BytesIO
from typing import Any

import httpx
import numpy as np
from PIL import Image, ImageOps

# Optional OCR (if pytesseract is installed, we'll use it; otherwise we skip text)
# Define symbol to avoid "possibly unbound" in type-checkers
pytesseract: Any | None = None
try:
    import pytesseract

    _HAS_TESS = True
    # Try to auto-configure the Tesseract binary if available
    try:
        import os
        import shutil

        tess_env = os.environ.get('TESSERACT_CMD')
        if tess_env:
            pytesseract.pytesseract.tesseract_cmd = tess_env
        else:
            _tess_path = shutil.which('tesseract')
            if _tess_path:
                pytesseract.pytesseract.tesseract_cmd = _tess_path
    except Exception:
        # Best-effort only; if this fails we fall back to pytesseract defaults
        pass
except Exception:
    _HAS_TESS = False


def _center_crop(img: Image.Image, ratio: float) -> Image.Image:
    if not (0 < ratio <= 1):
        return img
    w, h = img.size
    nw, nh = int(w * ratio), int(h * ratio)
    left = (w - nw) // 2
    top = (h - nh) // 2
    return img.crop((left, top, left + nw, top + nh))


def _dhash(img: Image.Image, hash_size: int = 16) -> int:
    # grayscale, resize to (hash_size+1, hash_size), then compute horizontal gradients
    img = ImageOps.grayscale(img).resize(
        (hash_size + 1, hash_size), Image.Resampling.BILINEAR
    )
    arr = np.asarray(img, dtype=np.int16)
    diff = arr[:, 1:] > arr[:, :-1]
    # pack bits into int
    bits = 0
    for v in diff.flatten():
        bits = (bits << 1) | int(v)
    return bits


def _hamming(a: int, b: int) -> int:
    return (a ^ b).bit_count()


def _hist_cosine_sim(imgA: Image.Image, imgB: Image.Image, bins: int = 64) -> float:
    # RGB histograms concatenated, L1-normalized then cosine similarity
    A = np.asarray(imgA.convert('RGB'))
    B = np.asarray(imgB.convert('RGB'))
    hA = []
    hB = []
    for ch in range(3):
        hA.append(
            np.histogram(A[..., ch], bins=bins, range=(0, 255))[0].astype(np.float64)
        )
        hB.append(
            np.histogram(B[..., ch], bins=bins, range=(0, 255))[0].astype(np.float64)
        )
    hA = np.concatenate(hA)
    hB = np.concatenate(hB)
    # normalize
    if hA.sum() > 0:
        hA /= hA.sum()
    if hB.sum() > 0:
        hB /= hB.sum()
    num = float(np.dot(hA, hB))
    den = float(np.linalg.norm(hA) * np.linalg.norm(hB))
    return (num / den) if den > 0 else 0.0


_word_re = re.compile(r'[A-Za-zÄÖÜäöüß0-9]+')


def _ocr_wordset(img: Image.Image):
    if not _HAS_TESS or pytesseract is None:
        return None
    try:
        pt = pytesseract  # local alias for type narrowing
        assert pt is not None
        txt = pt.image_to_string(img)
    except Exception:
        # If Tesseract isn't installed or not discoverable, skip OCR gracefully
        return None
    words = {w.lower() for w in _word_re.findall(txt)}
    return words


def _jaccard(a, b) -> float | None:
    if a is None or b is None or len(a) == 0 and len(b) == 0:
        return None
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def same_window_state(
    imgA: Image.Image,
    imgB: Image.Image,
    *,
    hash_size: int = 16,
    hist_bins: int = 64,
    center_crop: float = 0.95,
    threshold: float = 0.75,
):
    """
    Returns a dict with component scores, combined score, and boolean 'same_state'.
    threshold: decision cutoff on combined score in [0,1].
    """

    # print images to terminal
    imgA.show()
    imgB.show()

    # Focus on the center to reduce cursor/OS chrome noise
    A = _center_crop(imgA, center_crop)
    B = _center_crop(imgB, center_crop)

    # Perceptual hash similarity
    hA = _dhash(A, hash_size=hash_size)
    hB = _dhash(B, hash_size=hash_size)
    dh_bits = hash_size * hash_size
    dh_dist = _hamming(hA, hB)
    dh_sim = 1.0 - (dh_dist / dh_bits)

    # Color histogram similarity
    hist_sim = _hist_cosine_sim(A, B, bins=hist_bins)

    # OCR text overlap (optional)
    tA = _ocr_wordset(A)
    tB = _ocr_wordset(B)
    text_sim = _jaccard(tA, tB)

    # Combine with weights; renormalize if OCR missing
    w_phash, w_hist, w_text = 0.5, 0.3, 0.2
    if text_sim is None:
        w_sum = w_phash + w_hist
        combined = (w_phash * dh_sim + w_hist * hist_sim) / w_sum
    else:
        combined = w_phash * dh_sim + w_hist * hist_sim + w_text * text_sim

    return {
        'dhash_similarity': dh_sim,  # 1.0 = identical by pHash
        'histogram_similarity': hist_sim,  # 1.0 = identical color distribution
        'text_similarity': text_sim,  # None if OCR unavailable
        'combined_score': combined,  # 0..1
        'same_state': combined >= threshold,  # boolean decision
    }


if __name__ == '__main__':
    img_a = Image.open('./screenshots/Mahnungen0.png')
    img_b = Image.open('./screenshots/Mahnungen0.png')

    result = same_window_state(img_a, img_b)
    print('\nResult:', result)


def same_state_with_ground_truths_per_score(
    gt_a: Image.Image, gt_b: Image.Image, cand: Image.Image, margin=0.05
):
    # scores between ground truths
    ab = same_window_state(gt_a, gt_b)

    # return false if the diff between the two ground truths is greater than the margin
    if abs(1 - ab['dhash_similarity']) > margin:
        print(
            f'Diff between dhash_similarity is greater than the margin: {abs(ab["dhash_similarity"])}'
        )
        return {'per_score': ab, 'decision': False}
    if abs(1 - ab['histogram_similarity']) > margin:
        print(
            f'Diff between histogram_similarity is greater than the margin: {abs(ab["histogram_similarity"])}'
        )
        return {'per_score': ab, 'decision': False}

    # not checking text_similarity because it is not that reliable

    # scores between candidate and each reference
    ac = same_window_state(gt_a, cand)
    bc = same_window_state(gt_b, cand)

    result = {}
    decision = True

    for key in ['dhash_similarity', 'histogram_similarity', 'text_similarity']:
        if ab[key] is None:  # skip if text_similarity is None
            result[key] = {
                'ref_sim': None,
                'candA': None,
                'candB': None,
                'required': None,
                'pass': None,
            }
            continue

        ref_sim = ab[key]
        candA = ac[key]
        candB = bc[key]

        # required threshold = ref similarity - (margin * (1 - ref similarity))
        # interpret margin as a percentage of the gap to a perfect match
        required = min(ref_sim, max(0.0, ref_sim - (margin * (1.0 - ref_sim))))
        passed = (candA >= required) or (candB >= required)

        result[key] = {
            'ref_sim': ref_sim,
            'candA': candA,
            'candB': candB,
            'required': required,
            'pass': passed,
        }

        if not passed:
            # break and return False if any component fails
            decision = False
            break

    return {'per_score': result, 'decision': decision}


def base64_to_image(base64_image: str) -> Image.Image:
    img_bytes = base64.b64decode(base64_image)
    return Image.open(BytesIO(img_bytes))


async def get_screenshot_from_job(container_ip):
    timeout = httpx.Timeout(60.0, connect=10.0)
    payload = {
        'api_type': 'computer_20250124',
    }

    api_url = f'http://{container_ip}:8088/tool_use/screenshot'
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(api_url, json=payload)
        if not response.is_success:
            print(f'Failed to take screenshot: {response.text}')
        else:
            result = response.json()
            base64_image = result.get('base64_image')

            return base64_to_image(base64_image)
