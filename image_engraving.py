"""Trace uploaded artwork into engraving contours, never mechanical cut geometry."""
import math
import base64
import io
from functools import lru_cache
import numpy as np
from PIL import Image, ImageOps
from shapely.geometry import MultiLineString
from image_trace import _decode_image, _otsu, _marching_segments, _stitch

@lru_cache(maxsize=2)
def _trace(encoded, crop, foreground, threshold, ink_color):
    if len(encoded) > 16_000_000:
        raise ValueError('Image base64 exceeds allowed size')
    raw = encoded.split(',',1)[1] if encoded.startswith('data:') else encoded
    data = base64.b64decode(raw,validate=True)
    if len(data) > 12_000_000:
        raise ValueError('Image exceeds 12 MB')
    image = Image.open(io.BytesIO(data))
    if image.width * image.height > 20_000_000:
        raise ValueError('Image exceeds 20 megapixels')
    image = ImageOps.exif_transpose(image)
    if crop:
        if len(crop) != 4 or not all(math.isfinite(v) and 0 <= v <= 1 for v in crop) or crop[0] >= crop[2] or crop[1] >= crop[3]:
            raise ValueError('crop must be normalized [left,top,right,bottom] in 0..1')
        image = image.crop((int(crop[0]*image.width),int(crop[1]*image.height),int(crop[2]*image.width),int(crop[3]*image.height)))
    if min(image.size) < 2:
        raise ValueError('Image crop is empty or too small')
    image.thumbnail((1400,1400),Image.Resampling.LANCZOS)
    alpha = np.asarray(image.convert('RGBA'))[:,:,3]
    transparent = float((alpha < 16).mean()) > .1
    array = alpha if transparent else np.asarray(ImageOps.grayscale(image.convert('RGB')))
    if ink_color:
        if ink_color != 'yellow':
            raise ValueError('ink_color currently supports yellow only; omit for monochrome artwork')
        rgb = np.asarray(image.convert('RGB'))
        selected = (rgb[:,:,0] > 128) & (rgb[:,:,1] > 128) & (rgb[:,:,2] < 128)
        array = np.where(selected,alpha,0).astype(np.uint8)
        transparent = True
    if int(array.max()) - int(array.min()) < 10:
        raise ValueError('No contrasting artwork found')
    boundary = np.concatenate((array[0],array[-1],array[:,0],array[:,-1]))
    if foreground == 'auto':
        foreground = 'light' if np.median(boundary) < 128 else 'dark'
    if transparent:
        foreground = 'light'
    if foreground not in {'light','dark'}:
        raise ValueError('foreground must be auto, light or dark')
    cutoff = _otsu(array) if threshold is None else int(threshold)
    if not 0 <= cutoff <= 255:
        raise ValueError('threshold must be 0..255')
    mask = (array > cutoff) if foreground == 'light' else (array <= cutoff)
    if not 0 < float(mask.mean()) < .85:
        raise ValueError('No usable foreground; crop the logo or select light/dark')
    lines = _stitch(_marching_segments(mask.astype(np.uint8)))
    if not lines or sum(len(line) for line in lines) > 200000:
        raise ValueError('Artwork is empty or too complex; crop or resize it')
    # Image Y-down to part-local Y-up; keep all separate contours and fine details.
    return MultiLineString([[(x,-y) for x,y in line] for line in lines])

def image_geometry(mark):
    encoded = mark.get('image_base64')
    if not isinstance(encoded,str) or not encoded:
        raise ValueError('Image marking requires image_base64 (PNG/JPEG/WebP or data URL)')
    crop = tuple(float(v) for v in mark.get('crop', []))
    return _trace(encoded,crop,str(mark.get('foreground','auto')).lower(),mark.get('threshold'),str(mark.get('ink_color','')).lower())
