/* Package the window (D119): Electron plus src/ into "Sutra Pro.app" (macOS) or the "Sutra Pro-win32-x64" folder (Windows).

     node scripts/package.mjs --platform darwin --arch arm64 --out out --version 0.2.0
     node scripts/package.mjs --platform win32 --arch x64 --out out --version 0.2.0
     node scripts/package.mjs --platform darwin --arch arm64 --out out --version 0.2.0 --channel beta     "Sutra Pro Beta.app": a build to try beside the stable app

   This puts only the window in the package. The Python the window runs the server on goes in afterwards, copied as it is (the packager would turn
   the relative symlinks of the interpreter into absolute ones that point at the build machine), by scripts/build_desktop_app.py, which also signs.
   The last line printed is "PACKAGED <path>". */
import { packager, defaultSanitizePackageJson } from '@electron/packager';
import { createRequire } from 'node:module';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const require = createRequire(import.meta.url);
const channels = require('../src/channels.json');            // the identity of the stable app and of the beta (src/channel.js reads the same file)
const { packageFields } = require('../src/channel.js');

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const icons = path.resolve(root, '..', 'assets', 'icon');

export const APP_NAME = channels.stable.appName;
export const BUNDLE_ID = channels.stable.appId;   // 'os.sutra.pro': the id of the Mac app since 0.1.0, so the new app replaces the old one in place
const VERSION = /^(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)$/;

/* What goes into the app archive: package.json and src/. Nothing else of this folder (tests, scripts, the lock file, node_modules) ships.
   The packager asks about '' (the folder itself) and about every path below it, relative to the folder, with a leading slash. */
export function ignored(relative) {
  return !(relative === '' || relative === '/package.json' || relative === '/src' || relative.startsWith('/src/'));
}

export function packagerOptions({ platform, arch, out, version, channel = 'stable' }) {
  if (!Object.prototype.hasOwnProperty.call(channels, channel)) throw new Error(`channel must be ${Object.keys(channels).join(' or ')}, not ${channel}`);
  const identity = channels[channel];
  if (!['darwin', 'win32'].includes(platform)) throw new Error(`platform must be darwin or win32, not ${platform}`);
  if (!['arm64', 'x64'].includes(arch)) throw new Error(`arch must be arm64 or x64, not ${arch}`);
  if (platform === 'win32' && arch !== 'x64') throw new Error('the Windows app is x64 only');
  if (!VERSION.test(version || '')) throw new Error(`version must be X.Y.Z, not ${version}`);
  if (identity.id !== 'stable' && platform !== 'darwin') throw new Error(`the ${identity.id} app is a Mac app: it is built and installed on one Mac`);
  const options = {
    dir: root,
    out: path.resolve(out),
    name: identity.appName,
    platform,
    arch,
    appVersion: version,
    buildVersion: version,
    appCopyright: 'Copyright © Sutra',
    overwrite: true,
    asar: true,
    quiet: true,
    ignore: ignored,
    extraResource: [path.join(icons, identity.iconName)],         // the window's icon for the pages it draws itself (src/main.js iconPath)
    icon: path.join(icons, platform === 'darwin' ? identity.icns : 'sutra-pro.ico'),
  };
  if (identity.id !== 'stable') {
    // the package.json inside the app names the channel (src/channel.js reads it) and gives Electron the name its own state follows. The default
    // sanitizer is kept: giving the packager any list replaces it
    options.sanitizePackageJson = [defaultSanitizePackageJson, (pkg) => ({ ...pkg, ...packageFields(identity) })];
  }
  if (platform === 'darwin') {
    Object.assign(options, { appBundleId: identity.appId, appCategoryType: 'public.app-category.developer-tools', darwinDarkModeSupport: true });
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
  const { platform, arch, out, version, channel = 'stable' } = parse(argv);
  const built = await packager(packagerOptions({ platform, arch, out: out || 'out', version, channel }));
  if (built.length !== 1) throw new Error(`expected one package, the packager made ${built.length}`);
  const target = platform === 'darwin' ? path.join(built[0], `${channels[channel].appName}.app`) : built[0];
  console.log(`PACKAGED ${target}`);
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main(process.argv.slice(2)).catch((error) => {
    console.error(`error: ${error.message}`);
    process.exit(1);
  });
}
