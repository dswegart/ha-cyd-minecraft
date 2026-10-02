const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const qrcode = require('qrcode-generator');
const jsQR = require('jsqr');

function cardClass() {
  const classes = {};
  const context = { window: {}, HTMLElement: class {}, customElements: { get: n => classes[n], define: (n,c) => classes[n] = c }, console, setTimeout, clearTimeout };
  vm.runInNewContext(fs.readFileSync('dashboard/minecraft-cyd-card.js', 'utf8'), context);
  return classes['minecraft-cyd-card'];
}

test('card only uses the authenticated HA websocket, never browser fetch', async () => {
  const Card = cardClass();
  let message;
  const instance = Object.create(Card.prototype);
  instance._hass = { callWS: async m => { message = m; return { servers: [] }; } };
  await instance._request({ type: 'cyd_minecraft/snapshot' });
  assert.equal(message.type, 'cyd_minecraft/snapshot');
  const source = fs.readFileSync('dashboard/src/card.js', 'utf8');
  assert.equal(source.includes('fetch('), false);
  assert.equal(source.includes('http://'), false);
  assert.equal(source.includes('Colour Park'), false);
});

test('automatic height, isolated CSS, and responsive QR quiet zone', () => {
  const Card = cardClass();
  const instance = Object.create(Card.prototype);
  assert.equal(instance.getGridOptions().rows, 'auto');
  const source = fs.readFileSync('dashboard/src/card.js', 'utf8');
  assert.ok(source.includes("mode: 'open'"));
  assert.ok(source.includes('width:min(100%,320px)'));
  assert.ok(source.includes('createDataURL(6, 24)'));
});

test('QR round-trip decodes the exact shared Minecraft add-server link', () => {
  const link = 'minecraft://?addExternalServer=' + encodeURIComponent('Family Minecraft|example.com:19132');
  const code = qrcode(0, 'M');
  code.addData(link);
  code.make();
  const cells = code.getModuleCount(), scale = 6, margin = 24;
  const width = cells * scale + margin * 2;
  const pixels = new Uint8ClampedArray(width * width * 4).fill(255);
  for (let row = 0; row < cells; row++) for (let col = 0; col < cells; col++) {
    if (!code.isDark(row, col)) continue;
    for (let dy = 0; dy < scale; dy++) for (let dx = 0; dx < scale; dx++) {
      const index = ((margin + row * scale + dy) * width + margin + col * scale + dx) * 4;
      pixels[index] = pixels[index + 1] = pixels[index + 2] = 0;
    }
  }
  assert.equal(jsQR(pixels, width, width).data, link);
});
