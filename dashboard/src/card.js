import qrcode from 'qrcode-generator';

export function joinLink(host, port, name) {
  return `minecraft://?addExternalServer=${encodeURIComponent(`${name}|${host}:${port}`)}`;
}

class MinecraftCydCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this._servers = [];
    this._connected = false;
    this._busy = false;
  }

  setConfig(config) {
    this.config = { join_host: '', join_port: 19132, join_name: 'Family Minecraft', refresh_seconds: 15, ...config };
    if (!/^[a-zA-Z0-9.-]+$/.test(this.config.join_host)) throw new Error('Set join_host to your Minecraft address');
    if (!Number.isInteger(this.config.join_port) || this.config.join_port < 1 || this.config.join_port > 65535) throw new Error('Invalid Minecraft port');
    this._render();
    if (this._hass && this.isConnected) this._refresh();
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (first && this.config && this.isConnected) this._refresh();
  }

  connectedCallback() {
    if (this._hass && this.config) this._refresh();
  }

  disconnectedCallback() { clearTimeout(this._timer); }
  getCardSize() { return 16; }
  getGridOptions() { return { columns: 'full', rows: 'auto', min_columns: 6 }; }

  _render() {
    this.shadowRoot.innerHTML = `
      <style>
        :host { display:block; min-width:0; }
        ha-card { overflow:visible; }
        .content { padding:16px; }
        .health,.status { color:var(--secondary-text-color); margin:8px 0 12px; overflow-wrap:anywhere; }
        .health.good { color:var(--success-color,#43a047); }
        .toolbar,.actions { display:flex; align-items:center; gap:8px; flex-wrap:wrap; margin:12px 0; }
        select { flex:1; min-width:140px; max-width:100%; font:inherit; padding:12px; border-radius:8px; color:var(--primary-text-color); background:var(--secondary-background-color); }
        button { cursor:pointer; font:inherit; color:var(--primary-text-color); background:var(--secondary-background-color); border:0; border-radius:10px; padding:12px; }
        button:focus-visible,select:focus-visible { outline:3px solid var(--primary-color); }
        button[disabled],select[disabled] { opacity:.45; cursor:default; }
        .start { background:var(--success-color,#2e7d32); color:white; }
        .stop { background:var(--error-color,#c62828); color:white; }
        .server-list { display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr)); gap:8px; }
        .server { text-align:left; display:grid; gap:6px; overflow-wrap:anywhere; }
        .selected { outline:2px solid var(--primary-color); }
        .server small { color:var(--secondary-text-color); }
        .running { color:var(--success-color,#43a047); }
        .join { border-top:1px solid var(--divider-color); margin-top:20px; padding-top:16px; text-align:center; }
        .join h3 { margin:0 0 12px; }
        .join p { margin:8px 0; overflow-wrap:anywhere; }
        .qr { display:block; width:min(100%,320px); height:auto; aspect-ratio:1; margin:16px auto; image-rendering:pixelated; }
        a { color:var(--primary-color); }
        .help { color:var(--secondary-text-color); font-size:.9em; }
      </style>
      <ha-card header="Minecraft servers"><div class="content">
        <div class="health" aria-live="polite">Connecting through Home Assistant…</div>
        <div class="toolbar"><select aria-label="Choose Minecraft world"></select><button data-action="refresh">Refresh</button></div>
        <div class="server-list"></div>
        <div class="actions"><button class="start" data-action="start" disabled>Make selected world live</button><button class="stop" data-action="stop" disabled>Stop selected world</button></div>
        <div class="status" role="status" aria-live="polite"></div>
        <div class="join"><h3>Shared Minecraft join code</h3><p class="live"></p>
          <p>Address: <code class="host"></code> · Port: <code class="port"></code></p>
          <img class="qr" alt="Scan to add the shared Minecraft server">
          <p><a class="add">Add server on this iPad</a></p>
          <p class="help">The same address and QR work for whichever world is live. On another phone, scan the QR with its camera. Xbox custom-server joining needs its usual console setup.</p>
        </div>
      </div></ha-card>`;
    this.shadowRoot.querySelector('.host').textContent = this.config.join_host;
    this.shadowRoot.querySelector('.port').textContent = this.config.join_port;
    const link = joinLink(this.config.join_host, this.config.join_port, this.config.join_name);
    this.shadowRoot.querySelector('.add').href = link;
    const code = qrcode(0, 'M');
    code.addData(link);
    code.make();
    this.shadowRoot.querySelector('.qr').src = code.createDataURL(6, 24);
    this.shadowRoot.querySelector('select').addEventListener('change', event => { this._selectedId = event.target.value; this._paint(); });
    this.shadowRoot.querySelectorAll('[data-action]').forEach(button => button.addEventListener('click', () => this._action(button.dataset.action)));
    this._paint();
  }

  async _request(message) {
    if (!this._hass) throw new Error('Home Assistant connection is not ready');
    return this._hass.callWS(message);
  }

  _apply(payload) {
    if (!Array.isArray(payload.servers)) throw new Error('Invalid Minecraft server data');
    this._servers = payload.servers;
    if (!this._servers.some(server => server.id === this._selectedId)) {
      this._selectedId = this._servers.find(server => server.state === 'running')?.id || payload.selected_id || this._servers[0]?.id;
    }
    this._connected = true;
    this._lastChecked = new Date();
    this._paint();
  }

  async _refresh() {
    clearTimeout(this._timer);
    if (!this._busy && !this._refreshing) {
      this._refreshing = true;
      try {
        this._apply(await this._request({ type: 'cyd_minecraft/snapshot' }));
        if (!this._actionMessage) this._message('Choose a world, then make it live. Only one world uses the shared join port.');
      } catch (error) {
        this._connected = false;
        this._paint();
        this._message(error.message || 'Minecraft bridge unavailable. Check Devices & Services.');
      } finally { this._refreshing = false; }
    }
    if (this.isConnected) this._timer = setTimeout(() => this._refresh(), Math.max(5, Number(this.config.refresh_seconds) || 15) * 1000);
  }

  async _action(action) {
    if (action === 'refresh') { this._actionMessage = false; return this._refresh(); }
    if (this._busy || !this._connected) return;
    const target = this._servers.find(server => server.id === this._selectedId);
    if (!target) return;
    const running = this._servers.filter(server => server.id !== target.id && server.state === 'running');
    const command = action === 'start' && running.length ? 'rotate' : action;
    if (command === 'stop' && !window.confirm(`Stop ${target.name}? Connected players will leave this world.`)) return;
    if (command === 'rotate' && !window.confirm(`Switch from ${running.map(server => server.name).join(', ')} to ${target.name}? Players will need to reconnect.`)) return;
    this._busy = true;
    this._actionMessage = true;
    this._paint();
    this._message(command === 'rotate' ? 'Stopping the old world, then starting the selected world…' : `${command === 'start' ? 'Starting' : 'Stopping'} ${target.name}…`);
    try {
      const payload = await this._request({ type: 'cyd_minecraft/command', action: command, server_id: target.id, allow_players: command !== 'start' });
      this._apply(payload);
      this._message(`${target.name}: ${payload.message || 'Command complete'}`);
    } catch (error) { this._message(`Command failed: ${error.message || 'Unknown error'}. Refresh to verify the current state.`); }
    finally { this._busy = false; this._paint(); this._refresh(); }
  }

  _paint() {
    if (!this.shadowRoot.querySelector('.health')) return;
    const health = this.shadowRoot.querySelector('.health');
    health.classList.toggle('good', this._connected);
    health.textContent = this._connected ? `CYD + Crafty connected · ${this._servers.length} worlds · checked ${this._lastChecked?.toLocaleTimeString() || 'now'}` : 'Minecraft controls unavailable · manual join code remains available';
    const select = this.shadowRoot.querySelector('select');
    select.innerHTML = this._servers.map(server => `<option value="${this._escape(server.id)}">${this._escape(server.name)} · ${this._escape(server.state)}</option>`).join('') || '<option>No server data</option>';
    select.value = this._selectedId || '';
    select.disabled = this._busy || !this._connected;
    const list = this.shadowRoot.querySelector('.server-list');
    list.innerHTML = this._servers.map(server => `<button class="server ${server.id === this._selectedId ? 'selected' : ''}" data-id="${this._escape(server.id)}" ${this._busy ? 'disabled' : ''}><span>${this._escape(server.name)}</span><small><span class="${server.state === 'running' ? 'running' : ''}">${this._escape(server.state === 'running' ? '● Live' : server.state)}</span> · ${server.online_players == null ? 'players unknown' : `${server.online_players} players`}</small></button>`).join('');
    list.querySelectorAll('button').forEach(button => button.addEventListener('click', () => { this._selectedId = button.dataset.id; this._paint(); }));
    const target = this._servers.find(server => server.id === this._selectedId);
    const start = this.shadowRoot.querySelector('[data-action="start"]');
    start.textContent = this._servers.some(server => server.id !== target?.id && server.state === 'running') ? 'Switch to selected world' : 'Start selected world';
    start.disabled = this._busy || !this._connected || target?.state !== 'stopped';
    this.shadowRoot.querySelector('[data-action="stop"]').disabled = this._busy || !this._connected || target?.state !== 'running';
    const running = this._servers.filter(server => server.state === 'running');
    this.shadowRoot.querySelector('.live').textContent = !this._connected ? 'Live world unknown — refresh controls before joining.' : running.length ? `Live: ${running.map(server => server.name).join(', ')}` : 'No world is live. Start one above before joining.';
  }

  _message(text) { this.shadowRoot.querySelector('.status').textContent = text; }
  _escape(value) { return String(value).replace(/[&<>"']/g, c => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;' }[c])); }
}

if (!customElements.get('minecraft-cyd-card')) customElements.define('minecraft-cyd-card', MinecraftCydCard);
window.customCards = window.customCards || [];
window.customCards.push({ type: 'minecraft-cyd-card', name: 'Minecraft CYD Control', description: 'HA-authenticated parent controls, server rotation, status and local QR' });
