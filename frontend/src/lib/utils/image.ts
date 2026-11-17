/**
 * Shrink/re-encode an image on the device before upload.
 *
 * Phones produce multi-MB photos, and uploading those over a mobile uplink is
 * slow and often aborts mid-transfer. Re-encoding to a size-capped JPEG keeps
 * the receipt readable for OCR (the backend targets the same ~2000px / q85)
 * while cutting the upload to a few hundred KB. It also normalises the MIME to
 * image/jpeg, which sidesteps in-app browsers that post a generic content type.
 *
 * Best-effort: returns the original file unchanged if anything fails or if the
 * re-encoded result isn't actually smaller.
 */
export async function compressImage(
  file: File,
  maxDim = 2000,
  quality = 0.82,
): Promise<File> {
  // Already small enough — uploading as-is is cheap, so don't spend any CPU or
  // memory decoding/re-encoding it on the device.
  if (file.size <= 1_000_000) return file;
  try {
    const url = URL.createObjectURL(file);
    try {
      const img = await new Promise<HTMLImageElement>((resolve, reject) => {
        const image = new Image();
        image.onload = () => resolve(image);
        image.onerror = reject;
        image.src = url;
      });

      let width = img.naturalWidth || img.width;
      let height = img.naturalHeight || img.height;
      if (!width || !height) return file;

      const longest = Math.max(width, height);
      if (longest > maxDim) {
        const scale = maxDim / longest;
        width = Math.round(width * scale);
        height = Math.round(height * scale);
      }

      const canvas = document.createElement('canvas');
      canvas.width = width;
      canvas.height = height;
      const ctx = canvas.getContext('2d');
      if (!ctx) return file;
      ctx.drawImage(img, 0, 0, width, height);

      const blob = await new Promise<Blob | null>((resolve) =>
        canvas.toBlob(resolve, 'image/jpeg', quality),
      );
      if (!blob || blob.size >= file.size) return file;

      const base = file.name.replace(/\.[^.]+$/, '') || 'photo';
      return new File([blob], `${base}.jpg`, { type: 'image/jpeg' });
    } finally {
      URL.revokeObjectURL(url);
    }
  } catch {
    return file;
  }
}
