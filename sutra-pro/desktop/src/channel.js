'use strict';
/* The two kinds of build of this app (D242): the STABLE app people download from a release, and the BETA app a developer (or an AI agent) builds from a working
   tree and installs on one Mac to try a change before it is released. Both can be installed and open at the same time, so every name a second copy could
   collide on is different: the app's name and bundle id, the data folder, Chromium's own state (it follows the app's name), the icon. The identity of
   each is data (channels.json, read by the packager and by scripts/build_desktop_app.py as well), so there is one place to look.

   A build's channel is fixed when it is packaged: the packager writes `sutraChannel` into the package.json inside the app. Nothing in the environment
   can turn a stable app into a beta one (a data folder of the stable app must never be reached by a beta build, or the other way round), and a checkout
   (`npm start`) is always stable. */
const channels = require('./channels.json');

const CHANNELS = Object.freeze(Object.fromEntries(Object.entries(channels).map(([id, channel]) => [id, Object.freeze({ ...channel })])));

/* The channel a package.json names: stable when it names none, an error when it names one that does not exist (a typo must not fall back to the stable
   app's data folder). */
function channelOf(pkg) {
  const named = pkg && typeof pkg === 'object' ? pkg.sutraChannel : undefined;
  if (named === undefined || named === null || named === '') return CHANNELS.stable;
  if (typeof named !== 'string' || !Object.prototype.hasOwnProperty.call(CHANNELS, named)) {
    throw new Error(`package.json names the channel ${JSON.stringify(named)}; the channels are ${Object.keys(CHANNELS).join(', ')}`);
  }
  return CHANNELS[named];
}

/* What the packager writes into the package.json inside the app of `channel`: the names Electron derives its own state from (userData follows the
   app's name), and the channel itself. */
function packageFields(channel) {
  return { name: channel.packageName, productName: channel.appName, sutraChannel: channel.id };
}

/* "0.6.1" for the stable app, "0.6.1 beta 1a2b3c4" for a beta build that says which commit it was built from (build-info.json: `build`). */
function versionLabel(channel, version, buildInfo) {
  if (channel.id === 'stable') return version;
  const build = buildInfo && typeof buildInfo.build === 'string' ? buildInfo.build.trim() : '';
  return `${version} ${channel.id}${build ? ` ${build}` : ''}`;
}

/* The updater of a build that does not update itself (a beta): the same calls as src/updater.js, none of which does anything, and the check on demand says
   why. `info({ message, detail })` shows a dialog. */
function inertUpdates({ info, channel }) {
  const nothing = () => {};
  return {
    start: nothing,
    stop: nothing,
    announce: nothing,
    applyOnQuit: async () => {},
    autoEligible: () => false,
    checkNow: async () => info({
      message: `${channel.appName} does not update itself.`,
      detail: 'A beta is built from a working tree and installed by the developer (scripts/install_app.py beta). The released Sutra Pro, the one without "Beta" in its name, is the app that updates itself.',
    }),
  };
}

module.exports = { CHANNELS, channelOf, packageFields, versionLabel, inertUpdates };
