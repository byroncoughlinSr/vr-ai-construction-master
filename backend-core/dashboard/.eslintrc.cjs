/* eslint-env node */
module.exports = {
  root: true,
  extends: [
    'plugin:vue/vue3-essential',
    'eslint:recommended',
    '@vue/eslint-config-typescript'
  ],
  parserOptions: {
    ecmaVersion: 'latest'
  },
  rules: {
    // `window.Android` (the headset WebView bridge) and API payloads are untyped.
    '@typescript-eslint/no-explicit-any': 'off'
  }
}
