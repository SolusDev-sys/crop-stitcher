import cv2
import numpy as np


def _largest_rect_in_histogram(heights):
    """Largest rectangle in a histogram. Returns (area, start_col, width, height)."""
    stack = []  # (start_index, height)
    best = (0, 0, 0, 0)
    for i, h in enumerate(list(heights) + [0]):
        start = i
        while stack and stack[-1][1] >= h:
            s, sh = stack.pop()
            area = sh * (i - s)
            if area > best[0]:
                best = (area, s, i - s, sh)
            start = s
        stack.append((start, h))
    return best


def largest_inscribed_rect(mask):
    """
    Largest axis-aligned rectangle containing only True pixels in `mask`.
    Returns (x, y, w, h).
    """
    h_img, w_img = mask.shape
    heights = np.zeros(w_img, dtype=np.int32)
    best_area, best = 0, (0, 0, 0, 0)
    for row in range(h_img):
        heights = np.where(mask[row], heights + 1, 0)
        area, x, w, h = _largest_rect_in_histogram(heights)
        if area > best_area:
            best_area = area
            best = (x, row - h + 1, w, h)
    return best


def crop_stitcher(pano, black_thresh=1, max_dim=600, smooth_ksize=5, margin=0):
    """
    Crop black borders from a stitched panorama, even if it is curved or skewed.

    Parameters
    ----------
    pano : np.ndarray
        BGR (or grayscale) stitched image.
    black_thresh : int
        Pixels with intensity < black_thresh are treated as empty.
    max_dim : int
        The search runs on a downscaled mask for speed; the result is scaled
        back to full resolution.
    smooth_ksize : int
        Kernel size used to remove speckles and fill pinholes in the mask.
    margin : int
        Extra pixels trimmed from every side of the result (full-res pixels),
        useful to remove ragged blended edges.

    Returns
    -------
    cropped : np.ndarray
        Cropped image.
    (x, y, w, h) : tuple
        The crop rectangle in the original image's coordinates.
    """
    gray = pano if pano.ndim == 2 else cv2.cvtColor(pano, cv2.COLOR_BGR2GRAY)
    H, W = gray.shape

    # Valid-pixel mask
    mask = (gray >= black_thresh).astype(np.uint8) * 255

    # Clean up: close pinholes, then open to remove thin black/white fringes
    k = cv2.getStructuringElement(cv2.MORPH_RECT, (smooth_ksize, smooth_ksize))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, k)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, k)

    # Keep only the largest connected region and fill its interior holes
    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cnts:
        return pano.copy(), (0, 0, W, H)
    filled = np.zeros_like(mask)
    cv2.drawContours(filled, [max(cnts, key=cv2.contourArea)], -1, 255, -1)

    # Downscale for speed (INTER_NEAREST keeps it binary)
    scale = min(1.0, max_dim / max(H, W))
    small = cv2.resize(filled, None, fx=scale, fy=scale,
                       interpolation=cv2.INTER_NEAREST) if scale < 1.0 else filled

    # Erode slightly so the downscaled rectangle never touches an edge pixel
    small = cv2.erode(small, np.ones((3, 3), np.uint8))

    x, y, w, h = largest_inscribed_rect(small > 0)

    # Scale back to full resolution
    x, y = int(x / scale), int(y / scale)
    w, h = int(np.ceil(w / scale)), int(np.ceil(h / scale))

    # Apply margin and clamp
    x, y = x + margin, y + margin
    w, h = w - 2 * margin, h - 2 * margin
    x, y = max(x, 0), max(y, 0)
    w, h = min(w, W - x), min(h, H - y)

    # Refine at full resolution: shrink until the rect has no empty pixels
    full_valid = filled > 0
    while w > 1 and h > 1 and not full_valid[y:y + h, x:x + w].all():
        x, y, w, h = x + 1, y + 1, w - 2, h - 2

    return pano[y:y + h, x:x + w], (x, y, w, h)


if __name__ == "__main__":
    import sys

    src = sys.argv[1] if len(sys.argv) > 1 else "pano.jpg"
    dst = sys.argv[2] if len(sys.argv) > 2 else "pano_cropped.jpg"
    img = cv2.imread(src)
    if img is None:
        raise SystemExit(f"Could not read {src}")
    out, rect = crop_stitcher(img)
    cv2.imwrite(dst, out)
    print(f"Crop rect (x, y, w, h): {rect} -> saved {dst}")