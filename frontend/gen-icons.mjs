import { default as sharp } from 'sharp';

const makeSvg = (size) => {
  const r = Math.round(size * 0.42);
  const cx = size / 2;
  const rx = Math.round(size * 0.18);
  const fs = Math.round(size * 0.45);
  // Use plain cricket ball design (no emoji — sharp/librsvg doesn't render emoji)
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}">
    <rect width="${size}" height="${size}" rx="${rx}" fill="#0f172a"/>
    <circle cx="${cx}" cy="${cx}" r="${r}" fill="#dc2626"/>
    <!-- seam lines -->
    <path d="M${cx} ${cx - r} Q${cx + r * 0.3} ${cx - r * 0.5} ${cx + r * 0.3} ${cx} Q${cx + r * 0.3} ${cx + r * 0.5} ${cx} ${cx + r}"
          stroke="#fca5a5" stroke-width="${Math.max(2, size * 0.018)}" fill="none"/>
    <path d="M${cx} ${cx - r} Q${cx - r * 0.3} ${cx - r * 0.5} ${cx - r * 0.3} ${cx} Q${cx - r * 0.3} ${cx + r * 0.5} ${cx} ${cx + r}"
          stroke="#fca5a5" stroke-width="${Math.max(2, size * 0.018)}" fill="none"/>
    <!-- CI text -->
    <text x="${cx}" y="${cx + fs * 0.12}" font-size="${fs}" font-weight="bold"
          text-anchor="middle" dominant-baseline="central"
          font-family="Arial,Helvetica,sans-serif" fill="white" opacity="0.9">CI</text>
  </svg>`;
  return Buffer.from(svg);
};

await Promise.all([
  sharp(makeSvg(192)).png().toFile('public/icons/icon-192.png'),
  sharp(makeSvg(512)).png().toFile('public/icons/icon-512.png'),
  sharp(makeSvg(180)).png().toFile('public/icons/apple-touch-icon.png'),
]).then(() => console.log('✅ PNG icons created')).catch(e => { console.error('❌', e.message); process.exit(1); });
