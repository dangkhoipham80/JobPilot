/* Getting a CV file from the file picker to `POST /cv/master/import`.

   The limits mirror `jobpilot/cv/importer.py` — the server is what enforces
   them; checking here first only means the refusal arrives before a multi-MB
   upload instead of after it, and in the dashboard's language. */

export const IMPORT_TYPES = ["image/png", "image/jpeg", "image/webp", "application/pdf"] as const;
export const MAX_IMPORT_FILES = 6;
export const MAX_IMAGE_BYTES = 3_500_000;
export const MAX_PDF_BYTES = 10_000_000;

export type UploadProblem = "type" | "size" | "decode";

/** A file the import will not take, and why — the caller words it. */
export class UploadError extends Error {
  constructor(
    public problem: UploadProblem,
    public file: string,
  ) {
    super(`${problem}: ${file}`);
    this.name = "UploadError";
  }
}

const isPdf = (file: File) => file.type === "application/pdf";

function toBlob(canvas: HTMLCanvasElement, quality: number): Promise<Blob | null> {
  return new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", quality));
}

/**
 * Bring a photo under the image limit by redrawing it smaller.
 *
 * A phone photo of a page is 4–8 MB and 4000 px on its long edge; the limit is
 * 3.5 MB, and a model reads a page perfectly well at 2400 px. Doing it here
 * rather than refusing is the difference between "upload a photo" working and
 * the user being sent off to find an image editor. Two attempts, because a
 * page of dense text compresses worse than the first size assumes.
 */
async function shrink(file: File): Promise<File> {
  let bitmap: ImageBitmap;
  try {
    bitmap = await createImageBitmap(file);
  } catch {
    throw new UploadError("decode", file.name);
  }
  try {
    for (const edge of [2400, 1700]) {
      const scale = Math.min(1, edge / Math.max(bitmap.width, bitmap.height));
      const canvas = document.createElement("canvas");
      canvas.width = Math.round(bitmap.width * scale);
      canvas.height = Math.round(bitmap.height * scale);
      const ctx = canvas.getContext("2d");
      if (!ctx) break;
      // JPEG has no alpha: a transparent PNG would otherwise come out black.
      ctx.fillStyle = "#fff";
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
      const blob = await toBlob(canvas, 0.85);
      if (blob && blob.size <= MAX_IMAGE_BYTES) {
        const name = file.name.replace(/\.[^.]+$/, "") + ".jpg";
        return new File([blob], name, { type: "image/jpeg" });
      }
    }
  } finally {
    bitmap.close();
  }
  throw new UploadError("size", file.name);
}

/** Check one picked file, shrinking an oversized photo. Throws `UploadError`. */
export async function prepareImportFile(file: File): Promise<File> {
  if (!(IMPORT_TYPES as readonly string[]).includes(file.type)) {
    throw new UploadError("type", file.name);
  }
  if (isPdf(file)) {
    if (file.size > MAX_PDF_BYTES) throw new UploadError("size", file.name);
    return file;
  }
  return file.size > MAX_IMAGE_BYTES ? shrink(file) : file;
}

/** The file as a `data:` URI — the import endpoint takes that as-is. */
export function readAsDataUri(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(new UploadError("decode", file.name));
    reader.readAsDataURL(file);
  });
}

export function formatBytes(size: number): string {
  return size >= 1_000_000 ? `${(size / 1_000_000).toFixed(1)} MB` : `${Math.ceil(size / 1000)} KB`;
}
