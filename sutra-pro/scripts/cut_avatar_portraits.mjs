// Cut the five handoff portraits into transparent-subject WebP files: node cut_portraits.mjs <handoff assets dir> <out dir> [size]
// The subject contour and placement come from portrait-masks.json. The mask is the contour (one closed polygon of M/L points in a 64-unit box)
// inside the avatar disc, drawn here with 4x4 supersampling, so nothing shows outside the circle and the edge is smooth. Needs ffmpeg with libwebp.
import {execFileSync} from "node:child_process";
import {mkdirSync, readFileSync, writeFileSync, statSync, rmSync} from "node:fs";
import path from "node:path";

const [src, out, sizeArg] = process.argv.slice(2);
const size = Number(sizeArg || 224), SS = 4;
mkdirSync(out, {recursive: true});
const masks = JSON.parse(readFileSync(path.join(src, "portrait-masks.json"), "utf8"));

function points(d) {
  if (/[^MLZ0-9.\s-]/.test(d) || (d.match(/M/g) || []).length !== 1) throw new Error("the contour must be one M/L/Z polygon");
  const nums = d.match(/-?\d+(?:\.\d+)?/g).map(Number), pts = [];
  for (let i = 0; i < nums.length; i += 2) pts.push([nums[i], nums[i + 1]]);
  return pts;
}

function maskOf(m) {
  const p = m.placement, k = p.width / 64, cx = (32 - p.x) / k, cy = (32 - p.y) / k, r = 32 / k;      // the avatar disc in the image's own 64-unit box
  const pts = points(m.subjectClipPath), n = size * SS, unit = 64 / n, acc = new Uint16Array(size * size);
  for (let y = 0; y < n; y++) {
    const fy = (y + 0.5) * unit, xs = [];
    for (let i = 0; i < pts.length; i++) {
      const [x1, y1] = pts[i], [x2, y2] = pts[(i + 1) % pts.length];
      if ((y1 <= fy && y2 > fy) || (y2 <= fy && y1 > fy)) xs.push(x1 + (fy - y1) / (y2 - y1) * (x2 - x1));
    }
    xs.sort((a, b) => a - b);
    for (let j = 0; j + 1 < xs.length; j += 2) {
      for (let x = Math.max(0, Math.ceil(xs[j] / unit - 0.5)); x < n && (x + 0.5) * unit < xs[j + 1]; x++) {
        const fx = (x + 0.5) * unit;
        if ((fx - cx) * (fx - cx) + (fy - cy) * (fy - cy) <= r * r) acc[(y / SS | 0) * size + (x / SS | 0)]++;
      }
    }
  }
  const body = Buffer.alloc(size * size);
  for (let i = 0; i < acc.length; i++) body[i] = Math.round(acc[i] * 255 / (SS * SS));
  return Buffer.concat([Buffer.from(`P5\n${size} ${size}\n255\n`, "ascii"), body]);
}

for (const m of masks) {
  const maskFile = path.join(out, m.id + ".mask.pgm"), outFile = path.join(out, m.id + ".webp");
  writeFileSync(maskFile, maskOf(m));
  execFileSync("ffmpeg", ["-v", "error", "-y", "-i", path.join(src, m.image), "-i", maskFile, "-filter_complex",
    `[0:v]scale=${size}:${size}:flags=lanczos,format=rgba[a];[1:v]format=gray[m];[a][m]alphamerge`,
    "-frames:v", "1", "-c:v", "libwebp", "-quality", "88", "-compression_level", "6", outFile], {stdio: "inherit"});
  rmSync(maskFile);
  console.log(m.id, statSync(outFile).size, JSON.stringify(m.placement));
}
