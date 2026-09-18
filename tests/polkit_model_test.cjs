// Deterministic model tests: no Polkit, PAM, or authentication calls.
const assert = require('node:assert/strict');
const path = require('node:path');
const { test } = require('node:test');

const model = require(path.resolve(
  __dirname,
  '../components/desktop/plugins/atlas.polkit/PolkitModel.js'
));

test('recognizes common fingerprint prompts', () => {
  for (const prompt of [
    'Place your right index finger on the fingerprint reader',
    'Swipe your finger across the sensor',
    'Verify your fingerprint',
    'fprintd: verification in progress'
  ]) {
    assert.equal(model.promptLooksFingerprint(prompt), true, prompt);
  }
});

test('does not mistake unrelated prompts for fingerprint prompts', () => {
  for (const prompt of [
    '',
    'Password:',
    'Keep your fingers crossed',
    'Swipe to continue'
  ]) {
    assert.equal(model.promptLooksFingerprint(prompt), false, prompt);
  }
});

test('finds pam_fprintd in any position in an auth stack', () => {
  const config = `
auth required pam_env.so
auth optional pam_exec.so expose_authtok /usr/lib/pam/check-lid
auth sufficient pam_fprintd.so max-tries=3
auth required pam_unix.so
`;
  assert.equal(model.fingerprintConfiguredFromPamConfig(config), true);
});

test('accepts PAM extended controls, optional auth types, and absolute module paths', () => {
  for (const rule of [
    'auth [success=done default=ignore] pam_fprintd.so',
    '-AUTH [success=1 default=ignore] /usr/lib/security/pam_fprintd.so debug',
    'auth [success=done \\\n      default=ignore] /lib64/security/pam_fprintd.so'
  ]) {
    assert.equal(model.fingerprintConfiguredFromPamConfig(rule), true, rule);
  }
});

test('ignores comments, module arguments, and lookalike module names', () => {
  for (const config of [
    '# auth sufficient pam_fprintd.so',
    'auth required pam_exec.so # pam_fprintd.so',
    'auth required pam_exec.so helper=pam_fprintd.so',
    'auth sufficient pam_fprintd.so.disabled',
    'auth sufficient /tmp/pam_fprintd.so.backup'
  ]) {
    assert.equal(model.fingerprintConfiguredFromPamConfig(config), false, config);
  }
});

test('requires pam_fprintd to be an authentication module', () => {
  for (const config of [
    '',
    'account required pam_fprintd.so',
    'session optional pam_fprintd.so',
    'auth include pam_fprintd.so',
    'auth [success=done default=ignore pam_fprintd.so'
  ]) {
    assert.equal(model.fingerprintConfiguredFromPamConfig(config), false, config);
  }
});

test('shortens known command authorization messages', () => {
  assert.equal(
    model.authorizationLabel("Authentication is required to run `/usr/bin/example' as the super user"),
    "Authorize running '/usr/bin/example' as the super user"
  );
  assert.equal(
    model.authorizationLabel("authentication is needed to run 'example --safe' as root"),
    "Authorize running 'example --safe' as root"
  );
});

test('shortens known service actions and removes only a service suffix', () => {
  const cases = new Map([
    ["Authentication is required to start 'demo.service'", "Authorize starting 'demo'"],
    ['Authentication is needed to stop the demo.service', "Authorize stopping 'demo'"],
    ['Authentication is required to restart `demo.service`', "Authorize restarting 'demo'"],
    ['Authentication is needed to reload demo', "Authorize reloading 'demo'"]
  ]);
  for (const [message, expected] of cases) {
    assert.equal(model.authorizationLabel(message), expected);
  }
});

test('preserves unfamiliar and untrusted messages verbatim', () => {
  for (const message of [
    '<img src=x onerror=alert(1)>',
    'Authentication is required to mount the filesystem',
    "Authentication is required to run 'example' as root\nAdditional detail",
    "Authentication is required to run 'example' as root\n",
    "Authentication is required to run 'example\nAdditional detail' as root",
    "Authentication is required to run 'example\r\nAdditional detail' as root",
    "Authentication is required to restart 'demo.service'\n",
    "Authentication is required to restart demo.service\nAdditional detail",
    "Authentication is required to start demo.service\r\nAdditional detail",
    "Authentication is required to run 'example'",
    'restart demo.service',
    ''
  ]) {
    assert.equal(model.authorizationLabel(message), message);
  }
});
