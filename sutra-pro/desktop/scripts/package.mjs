/* Package the window (D108): Electron plus src/ into "Sutra Pro.app" (macOS) or the "Sutra Pro-win32-x64" folder (Windows).

     node scripts/package.mjs --platform darwin --arch arm64 --out out --version 0.2.0
     node scripts/package.mjs --platform win32 --arch x64 --out out --version 0.2.0

   This puts only the window in the package. The Python the window runs the server on goes in afterwards, copied as it is (the packager would turn
   the relative symlinks of the interpreter into absolute ones that point at the build machine), by scripts/build_desktop_app.py, which also signs.
   The last line printed is "PACKAGED <path>". */
import { packager } from '@electron/packager';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const icons = path.resolve(root, '..', 'assets', 'icon');

export const APP_NAME = 'Sutra Pro';
export const BUNDLE_ID = 'os.sutra.pro';          // the id of the Mac app since 0.1.0, so the new app replaces the old one in place
const VERSION = /^(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)$/;

/* What goes into the app archive: package.json and src/. Nothing else of this folder (tests, scripts, the lock file, node_modules) ships.
   The packager asks about '' (the folder itself) and about every path below it, relative to the folder, with a leading slash. */
export function ignored(relative) {
  return !(relative === '' || relative === '/package.json' || relative === '/src' || relative.startsWith('/src/'));
}

export function packagerOptions({ platform, arch, out, version }) {
  if (!['darwin', 'win32'].includes(platform)) throw new Error(`platform must be darwin or win32, not ${platform}`);
  if (!['arm64', 'x64'].includes(arch)) throw new Error(`arch must be arm64 or x64, not ${arch}`);
  if (platform === 'win32' && arch !== 'x64') throw new Error('the Windows app is x64 only');
  if (!VERSION.test(version || '')) throw new Error(`version must be X.Y.Z, not ${version}`);
  const options = {
    dir: root,
    out: path.resolve(out),
    name: APP_NAME,
    platform,
    arch,
    appVersion: version,
    buildVersion: version,
    appCopyright: 'Copyright © Sutra',
    overwrite: true,
    asar: true,
    quiet: true,
    ignore: ignored,
    extraResource: [path.join(icons, 'sutra-pro-1024.png')],      // the window's icon for the pages it draws itself (src/main.js iconPath)
    icon: path.join(icons, platform === 'darwin' ? 'sutra-pro.icns' : 'sutra-pro.ico'),
  };
  if (platform === 'darwin') {
    Object.assign(options, { appBundleId: BUNDLE_ID, appCategoryType: 'public.app-category.developer-tools', darwinDarkModeSupport: true });
  } else {
    options.win32metadata = {
      CompanyName: 'Sutra', FileDescription: APP_NAME, ProductName: APP_NAME, InternalName: APP_NAME, OriginalFilename: `${APP_NAME}.exe`,
    };
  }
  return options;
}

function parse(argv) {
  const values = {};
  for (let index = 0; index < argv.length; index += 2) {
    const key = argv[index];
    if (!key.startsWith('--') || index + 1 >= argv.length) throw new Error(`unexpected argument ${key}`);
    values[key.slice(2)] = argv[index + 1];
  }
  return values;
}

async function main(argv) {
  const { platform, arch, out, version } = parse(argv);
  const built = await packager(packagerOptions({ platform, arch, out: out || 'out', version }));
  if (built.length !== 1) throw new Error(`expected one package, the packager made ${built.length}`);
  const target = platform === 'darwin' ? path.join(built[0], `${APP_NAME}.app`) : built[0];
  console.log(`PACKAGED ${target}`);
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main(process.argv.slice(2)).catch((error) => {
    console.error(`error: ${error.message}`);
    process.exit(1);
  });
}
