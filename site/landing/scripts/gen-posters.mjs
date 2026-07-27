// gen-posters.mjs — 构建期图片优化
// 1) 从 tests/golden/ 读 14 张金标准 PNG
// 2) 用 sharp 生成 540×960 webp 缩略图（双尺寸 srcset）
// 3) 输出到 site/landing/public/posters/{theme}-{page}.webp
// 4) 顺便生成 public/og-image.png（1200×630）
//
// 跳过：如果 public/posters/ 已有文件且 mtime 更新（缓存）
//
// 用法：node scripts/gen-posters.mjs

import sharp from 'sharp';
import { readdir, mkdir, stat } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '../../..');        // 项目根
const GOLDEN = path.join(ROOT, 'tests/golden');
const OUT = path.join(__dirname, '..', 'public/posters');

// 主题中英文映射表
const THEME_MAP = {
  '海洋柔光': 'ocean',
  '梦幻海洋': 'dream',
  '奶油花园': 'cream',
  '青提气泡': 'green',
  '卡通音符': 'note',
  '奶油玻璃': 'glass',
  '轻复古唱片': 'retro',
};

async function ensureDir(dir) {
  if (!existsSync(dir)) await mkdir(dir, { recursive: true });
}

async function processOne(srcPath, outName) {
  const out540  = path.join(OUT, `${outName}-540.webp`);
  const out1080 = path.join(OUT, `${outName}-1080.webp`);
  // 跳过：如果都已存在
  if (existsSync(out540) && existsSync(out1080)) {
    const srcStat = await stat(srcPath);
    const outStat = await stat(out540);
    if (outStat.mtimeMs >= srcStat.mtimeMs) {
      console.log(`  skip (cached): ${outName}`);
      return;
    }
  }
  await ensureDir(OUT);

  // 540 宽（移动端）
  await sharp(srcPath)
    .resize(540, null, { fit: 'inside', withoutEnlargement: true })
    .webp({ quality: 78 })
    .toFile(out540);

  // 1080 宽（高清）
  await sharp(srcPath)
    .resize(1080, null, { fit: 'inside', withoutEnlargement: true })
    .webp({ quality: 85 })
    .toFile(out1080);

  console.log(`  ✓ ${outName}`);
}

async function genOG() {
  const ogOut = path.join(__dirname, '..', 'public', 'og-image.png');
  if (existsSync(ogOut)) {
    const stat1 = await stat(ogOut);
    if (Date.now() - stat1.mtimeMs < 7 * 24 * 3600 * 1000) {
      console.log('  skip og-image.png (fresh)');
      return;
    }
  }

  // 取第一张主题海报作为 OG 底图
  const files = (await readdir(GOLDEN)).filter(f => f.endsWith('.png'));
  const first = files.sort().find(f => f.includes('-全屏p1')) || files[0];
  if (!first) {
    console.warn('  no poster for og-image');
    return;
  }
  await sharp(path.join(GOLDEN, first))
    .resize(1200, 630, { fit: 'cover', position: 'top' })
    .png({ quality: 90 })
    .toFile(ogOut);
  console.log(`  ✓ og-image.png`);
}

async function main() {
  console.log('🎨 生成海报缩略图 →');
  const files = (await readdir(GOLDEN)).filter(f => f.endsWith('.png'));
  let count = 0;
  for (const f of files) {
    // 解析文件名：{中文主题名}-{全屏|标准}p{1|2}.png
    const m = f.match(/^(.+)-(全屏|标准)p([12])\.png$/);
    if (!m) continue;
    const [, cnName, , page] = m;
    const slug = THEME_MAP[cnName];
    if (!slug) continue;
    await processOne(path.join(GOLDEN, f), `${slug}-${page}`);
    count++;
  }
  console.log(`  共 ${count} 张海报`);
  await genOG();
  console.log('🎨 完成');
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});