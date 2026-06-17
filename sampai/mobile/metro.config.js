const { getDefaultConfig } = require('expo/metro-config');
const { withNativeWind } = require('nativewind/metro');

const config = getDefaultConfig(__dirname);

// markdown-it (via react-native-markdown-display) requires Node's built-in
// `punycode`, which Metro can't resolve — alias it to the userland package.
config.resolver.extraNodeModules = {
  ...(config.resolver.extraNodeModules ?? {}),
  punycode: require.resolve('punycode/'),
};

module.exports = withNativeWind(config, { input: './src/global.css' });
