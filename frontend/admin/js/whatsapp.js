/* frontend/admin/js/whatsapp.js
   WhatsApp Template Messaging Manager
   Handles: Settings, Template Management, Inbox (Conversations + Chat)
*/

class WhatsAppManager {
    constructor() {
        this._eventsBound = false;   // guard for event listeners (bind once)
        this._initialized = false;   // guard for first-time load
        this.conversations = [];
        this.activeConvId = null;
        this.templates = [];
        this.config = null;
        this.pollInterval = null;
    }

    /* ─────────────────────────────────────────
       INIT
    ───────────────────────────────────────── */
    init() {
        if (!this._eventsBound) {
            this._eventsBound = true;
            this._bindTabs();
            this._bindConfigForm();
            this._bindTemplateActions();
            this._bindInboxActions();
            this._bindCreateTemplateModal();
        }

        // Always reload config/status when user navigates to this section
        this.loadConfig();
    }

    /* ─────────────────────────────────────────
       TAB SWITCHING
    ───────────────────────────────────────── */
    _bindTabs() {
        const tabs = ['Settings', 'Templates', 'Inbox', 'Automations'];
        tabs.forEach(tab => {
            const btn = document.getElementById(`waTab${tab}`);
            if (btn) {
                btn.addEventListener('click', () => this._switchTab(tab.toLowerCase()));
            }
        });
    }

    _switchTab(tab) {
        ['settings', 'templates', 'inbox', 'automations'].forEach(t => {
            const pane = document.getElementById(`waPane${t.charAt(0).toUpperCase() + t.slice(1)}`);
            const btn = document.getElementById(`waTab${t.charAt(0).toUpperCase() + t.slice(1)}`);
            if (pane) pane.classList.add('hidden');
            if (btn) { btn.classList.remove('wa-tab--active'); }
        });

        const activePane = document.getElementById(`waPane${tab.charAt(0).toUpperCase() + tab.slice(1)}`);
        const activeBtn = document.getElementById(`waTab${tab.charAt(0).toUpperCase() + tab.slice(1)}`);
        if (activePane) activePane.classList.remove('hidden');
        if (activeBtn) { activeBtn.classList.add('wa-tab--active'); }

        if (tab === 'templates') this.loadTemplates();
        if (tab === 'inbox') this.loadInbox();
        if (tab === 'automations') this.loadLeadAssignConfig();
    }

    /* ─────────────────────────────────────────
       SETTINGS TAB
    ───────────────────────────────────────── */
    async loadConfig() {
        try {
            const res = await this._api('GET', '/api/whatsapp/config');
            const data = await res.json();
            this.config = data.config;
            this._renderConfigStatus(data.config);
        } catch (e) {
            console.error('WA config load error', e);
            // Show error state instead of staying stuck on 'Loading...'
            this._renderConfigStatus(null);
            const badge = document.getElementById('waConnectionStatus');
            if (badge) { badge.textContent = 'Connection Error'; badge.style.color = '#f87171'; }
        }
    }

    _renderConfigStatus(cfg) {
        const statusBadge = document.getElementById('waConnectionStatus');
        const statusDot = document.getElementById('waStatusDot');
        const phoneEl = document.getElementById('waDisplayPhone');
        const phonePill = document.getElementById('waPhonePill');
        if (!statusBadge) return;

        if (cfg && cfg.is_connected) {
            statusBadge.textContent = 'Connected';
            statusBadge.style.color = '#6ee7b7';
            if (statusDot) statusDot.classList.add('online');
            if (phoneEl) phoneEl.textContent = cfg.phone_number_id || '-';
            if (phonePill) phonePill.style.display = 'flex';
        } else {
            statusBadge.textContent = 'Not Connected';
            statusBadge.style.color = '#fcd34d';
            if (statusDot) statusDot.classList.remove('online');
            if (phonePill) phonePill.style.display = 'none';
        }
    }

    _bindConfigForm() {
        const form = document.getElementById('waConfigForm');
        if (!form) return;
        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            await this.saveConfig();
        });

        const disconnectBtn = document.getElementById('waDisconnectBtn');
        if (disconnectBtn) {
            disconnectBtn.addEventListener('click', () => this.disconnectWA());
        }
    }

    async saveConfig() {
        const token = document.getElementById('waAccessToken')?.value?.trim();
        const phoneId = document.getElementById('waPhoneNumberId')?.value?.trim();
        const wabaId = document.getElementById('waWabaId')?.value?.trim();

        if (!token || !phoneId || !wabaId) {
            this._toast('Please fill in all required fields.', 'error');
            return;
        }

        const btn = document.getElementById('waSaveConfigBtn');
        if (btn) { btn.disabled = true; btn.textContent = 'Saving…'; }

        try {
            const res = await this._api('POST', '/api/whatsapp/config', {
                access_token: token, phone_number_id: phoneId, waba_id: wabaId
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.error || 'Save failed');
            this.config = data.config;
            this._renderConfigStatus(data.config);
            this._toast('WhatsApp connected successfully! 🎉', 'success');

            // Clear token field for security
            const tokenEl = document.getElementById('waAccessToken');
            if (tokenEl) tokenEl.value = '';
        } catch (e) {
            this._toast(e.message, 'error');
        } finally {
            if (btn) { btn.disabled = false; btn.textContent = 'Save & Connect'; }
        }
    }

    async disconnectWA() {
        if (!confirm('Disconnect WhatsApp? This will stop all messaging.')) return;
        try {
            await this._api('DELETE', '/api/whatsapp/config');
            this.config = null;
            this._renderConfigStatus(null);
            this._toast('WhatsApp disconnected.', 'info');
        } catch (e) {
            this._toast('Failed to disconnect.', 'error');
        }
    }

    /* ─────────────────────────────────────────
       AUTOMATIONS TAB
    ───────────────────────────────────────── */
    async loadLeadAssignConfig() {
        try {
            await this._ensureTemplatesLoaded(true);
        } catch (e) {
            this._toast(e.message || 'Failed to load templates', 'error');
            return;
        }

        const panes = ['Agent', 'Lead'];
        panes.forEach(p => {
            const select = document.getElementById(`waAuto${p}Tpl`);
            if (select) {
                const approved = this.templates.filter(t => String(t.status || '').trim().toUpperCase() === 'APPROVED');
                select.innerHTML = '<option value="">-- No Message --</option>' +
                    approved.map(t => `<option value="${t.name}" data-vars="${t.variable_count}" data-header-type="${t.header_type}">${this._esc(t.name)}</option>`).join('');
                select.onchange = () => this._onAutoTemplateChange(p.toLowerCase(), select);
            }
        });

        try {
            const res = await this._api('GET', '/api/whatsapp/lead-assign-config');
            const data = await res.json();
            if (data.config) {
                this._renderLeadAssignConfig(data.config);
            }
        } catch (e) {
            console.error('Lead assign config load error', e);
        }

        const saveBtn = document.getElementById('waSaveAutoBtn');
        if (saveBtn && !saveBtn._bound) {
            saveBtn._bound = true;
            saveBtn.onclick = () => this.saveLeadAssignConfig();
        }
    }

    _onAutoTemplateChange(type, select) {
        const opt = select.options[select.selectedIndex];
        const varCount = parseInt(opt?.dataset?.vars || '0');
        const headerType = opt?.dataset?.headerType || 'NONE';

        const typeTitle = type.charAt(0).toUpperCase() + type.slice(1);
        const headerWrap = document.getElementById(`waAuto${typeTitle}HeaderWrap`);
        const headerLabel = document.getElementById(`waAuto${typeTitle}HeaderType`);
        const varsContainer = document.getElementById(`waAuto${typeTitle}Vars`);

        if (headerWrap) {
            if (['IMAGE', 'VIDEO', 'DOCUMENT'].includes(headerType)) {
                headerWrap.classList.remove('hidden');
                if (headerLabel) headerLabel.textContent = headerType;
            } else {
                headerWrap.classList.add('hidden');
            }
        }

        if (varsContainer) {
            varsContainer.innerHTML = '';
            for (let i = 1; i <= varCount; i++) {
                varsContainer.innerHTML += `
                    <div class="wa-field-group">
                        <label class="wa-label text-[10px]">Variable {{${i}}}</label>
                        <input type="text" id="waAuto${typeTitle}Var${i}" placeholder="Enter parameter for {{${i}}}" class="wa-input text-xs">
                    </div>`;
            }
        }
    }

    _renderLeadAssignConfig(cfg) {
        const enableCheck = document.getElementById('waAutoEnable');
        if (enableCheck) enableCheck.checked = cfg.is_enabled;

        const setSide = (type, prefix) => {
            const tplSelect = document.getElementById(`waAuto${type}Tpl`);
            if (tplSelect) {
                tplSelect.value = cfg[`${prefix}_template_name`] || '';
                this._onAutoTemplateChange(prefix, tplSelect);

                const headerUrl = document.getElementById(`waAuto${type}HeaderUrl`);
                if (headerUrl) headerUrl.value = cfg[`${prefix}_header_url`] || '';

                const params = cfg[`${prefix}_params`] || [];
                params.forEach((p, idx) => {
                    const input = document.getElementById(`waAuto${type}Var${idx + 1}`);
                    if (input) input.value = p;
                });
            }
        };

        setSide('Agent', 'agent');
        setSide('Lead', 'lead');
    }

    async saveLeadAssignConfig() {
        const btn = document.getElementById('waSaveAutoBtn');
        const is_enabled = document.getElementById('waAutoEnable')?.checked;

        const getSide = (type, prefix) => {
            const tplSelect = document.getElementById(`waAuto${type}Tpl`);
            const template_name = tplSelect?.value || null;
            const header_url = document.getElementById(`waAuto${type}HeaderUrl`)?.value || null;

            const params = [];
            if (tplSelect) {
                const opt = tplSelect.options[tplSelect.selectedIndex];
                const varCount = parseInt(opt?.dataset?.vars || '0');
                for (let i = 1; i <= varCount; i++) {
                    params.push(document.getElementById(`waAuto${type}Var${i}`)?.value || '');
                }
            }
            return { template_name, header_url, params };
        };

        const agent = getSide('Agent', 'agent');
        const lead = getSide('Lead', 'lead');

        const payload = {
            is_enabled,
            agent_template_name: agent.template_name,
            agent_header_url: agent.header_url,
            agent_params: agent.params,
            lead_template_name: lead.template_name,
            lead_header_url: lead.header_url,
            lead_params: lead.params
        };

        if (btn) { btn.disabled = true; btn.innerHTML = '<i class="fas fa-spinner fa-spin mr-2"></i>Saving...'; }

        try {
            const res = await this._api('POST', '/api/whatsapp/lead-assign-config', payload);
            if (!res.ok) throw new Error('Failed to save automation settings');
            this._toast('Automation settings saved! 🤖', 'success');
        } catch (e) {
            this._toast(e.message, 'error');
        } finally {
            if (btn) { btn.disabled = false; btn.innerHTML = '<i class="fas fa-save mr-2"></i>Save Automation Settings'; }
        }
    }

    /* ─────────────────────────────────────────
       TEMPLATES TAB
    ───────────────────────────────────────── */
    _bindTemplateActions() {
        const syncBtn = document.getElementById('waSyncTemplatesBtn');
        if (syncBtn) syncBtn.addEventListener('click', () => this.syncTemplates());

        const createBtn = document.getElementById('waCreateTemplateBtn');
        if (createBtn) createBtn.addEventListener('click', () => this._showCreateModal());

        const tableBody = document.getElementById('waTemplatesTableBody');
        if (tableBody && !tableBody._boundDelete) {
            tableBody._boundDelete = true;
            tableBody.addEventListener('click', (e) => {
                const btn = e.target.closest('.wa-delete-template-btn');
                if (!btn) return;
                const id = parseInt(btn.dataset.templateId || '0', 10);
                const name = btn.dataset.templateName || '';
                if (!id) return;
                this.deleteTemplate(id, name);
            });
        }
    }

    async loadTemplates(statusFilter = '') {
        const tbody = document.getElementById('waTemplatesTableBody');
        if (!tbody) return;
        tbody.innerHTML = '<tr><td colspan="7" class="text-center py-8 text-gray-400"><i class="fas fa-spinner fa-spin mr-2"></i>Loading templates…</td></tr>';

        try {
            const params = statusFilter ? `?status=${statusFilter}` : '';
            const res = await this._api('GET', `/api/whatsapp/templates${params}`);
            const data = await res.json();
            this.templates = data.templates || [];
            this._renderTemplatesTable(this.templates);
        } catch (e) {
            tbody.innerHTML = `<tr><td colspan="7" class="text-center py-6 text-red-400">${e.message}</td></tr>`;
        }
    }

    _renderTemplatesTable(templates) {
        const tbody = document.getElementById('waTemplatesTableBody');
        if (!tbody) return;

        if (!templates.length) {
            tbody.innerHTML = `<tr><td colspan="7" class="text-center py-12 text-gray-400">
                <i class="fab fa-whatsapp text-4xl mb-3 block text-green-500 opacity-30"></i>
                No templates found. Click <strong>Sync</strong> to fetch from Brandmo.
            </td></tr>`;
            return;
        }

        tbody.innerHTML = templates.map(t => {
            const statusColors = {
                APPROVED: 'bg-green-100 text-green-700',
                PENDING: 'bg-yellow-100 text-yellow-700',
                REJECTED: 'bg-red-100 text-red-700',
            };
            const badge = statusColors[t.status] || 'bg-gray-100 text-gray-600';
            const bodyPreview = (t.body_text || '').substring(0, 80) + (t.body_text?.length > 80 ? '…' : '');

            return `<tr class="border-b border-gray-100 hover:bg-gray-50 transition-colors">
                <td class="px-4 py-3 font-mono text-sm text-green-700">${this._esc(t.name)}</td>
                <td class="px-4 py-3">
                    <span class="px-2 py-0.5 rounded text-xs font-medium ${badge}">${t.status}</span>
                </td>
                <td class="px-4 py-3 text-xs text-gray-500 uppercase">${t.category || '—'}</td>
                <td class="px-4 py-3 text-xs text-gray-600">${this._esc(t.language)}</td>
                <td class="px-4 py-3 text-sm text-gray-700 max-w-xs truncate" title="${this._esc(t.body_text || '')}">${this._esc(bodyPreview)}</td>
                <td class="px-4 py-3 text-xs text-gray-500">${t.variable_count} var(s)</td>
                <td class="px-4 py-3">
                    <button
                        type="button"
                        class="wa-delete-template-btn text-red-500 hover:text-red-700 text-xs px-2 py-1 rounded hover:bg-red-50 transition"
                        data-template-id="${t.id}"
                        data-template-name="${this._esc(t.name)}">
                        <i class="fas fa-trash mr-1"></i>Delete
                    </button>
                </td>
            </tr>`;
        }).join('');
    }

    async syncTemplates() {
        const btn = document.getElementById('waSyncTemplatesBtn');
        if (btn) { btn.disabled = true; btn.innerHTML = '<i class="fas fa-spinner fa-spin mr-1"></i>Syncing…'; }

        try {
            const res = await this._api('POST', '/api/whatsapp/templates/sync');
            const data = await res.json();
            if (!res.ok) throw new Error(data.error || 'Sync failed');
            this._toast(`✅ Synced ${data.synced} templates`, 'success');
            await this.loadTemplates();
        } catch (e) {
            this._toast(e.message, 'error');
        } finally {
            if (btn) { btn.disabled = false; btn.innerHTML = '<i class="fas fa-sync mr-1"></i>Sync from Brandmo'; }
        }
    }

    async deleteTemplate(id, name) {
        if (!confirm(`Delete template "${name}"? This will also remove it from Meta.`)) return;
        try {
            const res = await this._api('DELETE', `/api/whatsapp/templates/${id}`);
            const data = await res.json();
            if (!res.ok) throw new Error(data.error || 'Delete failed');
            this._toast('Template deleted.', 'success');
            this.loadTemplates();
        } catch (e) {
            this._toast(e.message, 'error');
        }
    }

    /* ─────────────────────────────────────────
       CREATE TEMPLATE MODAL
    ───────────────────────────────────────── */
    _bindCreateTemplateModal() {
        const closeBtn = document.getElementById('waCreateModalClose');
        if (closeBtn) closeBtn.addEventListener('click', () => this._hideCreateModal());

        const form = document.getElementById('waCreateTemplateForm');
        if (form) form.addEventListener('submit', async (e) => {
            e.preventDefault();
            await this.submitCreateTemplate();
        });

        const bodyInput = document.getElementById('waTplBody');
        if (bodyInput) {
            bodyInput.addEventListener('input', () => {
                const varCount = (bodyInput.value.match(/\{\{\d+\}\}/g) || []).length;
                const counter = document.getElementById('waTplVarCount');
                if (counter) counter.textContent = `${varCount} variable(s) detected`;
            });
        }
    }

    _showCreateModal() {
        const modal = document.getElementById('waCreateTemplateModal');
        if (modal) modal.classList.remove('hidden');
    }

    _hideCreateModal() {
        const modal = document.getElementById('waCreateTemplateModal');
        if (modal) modal.classList.add('hidden');
        const form = document.getElementById('waCreateTemplateForm');
        if (form) form.reset();
    }

    async submitCreateTemplate() {
        const name = document.getElementById('waTplName')?.value?.trim();
        const category = document.getElementById('waTplCategory')?.value;
        const language = document.getElementById('waTplLanguage')?.value;
        const header = document.getElementById('waTplHeader')?.value?.trim();
        const body = document.getElementById('waTplBody')?.value?.trim();
        const footer = document.getElementById('waTplFooter')?.value?.trim();

        if (!name || !body) { this._toast('Template name and body are required.', 'error'); return; }

        const submitBtn = document.getElementById('waCreateSubmitBtn');
        if (submitBtn) { submitBtn.disabled = true; submitBtn.textContent = 'Submitting…'; }

        try {
            const res = await this._api('POST', '/api/whatsapp/templates/create', {
                name, category, language, header_text: header, body_text: body, footer_text: footer
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.error || 'Create failed');
            this._toast('Template submitted for Meta review! It may take up to 24 hours.', 'success');
            this._hideCreateModal();
            this.loadTemplates();
        } catch (e) {
            this._toast(e.message, 'error');
        } finally {
            if (submitBtn) { submitBtn.disabled = false; submitBtn.textContent = 'Submit Template'; }
        }
    }

    /* ─────────────────────────────────────────
       INBOX TAB — CONVERSATION LIST
    ───────────────────────────────────────── */
    _bindInboxActions() {
        const refreshBtn = document.getElementById('waRefreshInboxBtn');
        if (refreshBtn) refreshBtn.addEventListener('click', () => this.loadInbox());

        const sendBtn = document.getElementById('waChatSendBtn');
        if (sendBtn) sendBtn.addEventListener('click', () => this._sendChatMessage());

        const msgInput = document.getElementById('waChatMsgInput');
        if (msgInput) {
            msgInput.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); this._sendChatMessage(); }
            });
        }

        const sendTplBtn = document.getElementById('waChatSendTemplateBtn');
        if (sendTplBtn) sendTplBtn.addEventListener('click', () => this._openSendTemplatePanel());

        // New: Bind Direct Media Panel Send Button
        const sendMediaBtn = document.getElementById('waDirectMediaSendBtn');
        if (sendMediaBtn) sendMediaBtn.addEventListener('click', () => this._sendDirectMediaMessage());
    }

    async loadInbox() {
        const listEl = document.getElementById('waConversationList');
        if (!listEl) return;
        listEl.innerHTML = '<div class="text-center py-6 text-gray-400"><i class="fas fa-spinner fa-spin"></i></div>';

        try {
            const res = await this._api('GET', '/api/whatsapp/conversations?status=all&per_page=50');
            const data = await res.json();
            this.conversations = data.conversations || [];
            this._renderConversationList(this.conversations);
        } catch (e) {
            listEl.innerHTML = `<div class="p-4 text-red-400">${e.message}</div>`;
        }
    }

    _renderConversationList(convs) {
        const listEl = document.getElementById('waConversationList');
        if (!listEl) return;

        if (!convs.length) {
            listEl.innerHTML = `<div class="text-center py-12 text-gray-400">
                <i class="fab fa-whatsapp text-4xl mb-3 block text-green-500 opacity-30"></i>
                No conversations yet. Incoming messages will appear here.
            </div>`;
            return;
        }

        listEl.innerHTML = convs.map(c => {
            const contact = c.contact || {};
            const name = contact.name || contact.phone_number || 'Unknown';
            const phone = contact.phone_number || '';
            const lastMsg = c.last_message ? (c.last_message.message_text || c.last_message.message_type || '') : '';
            const lastAt = c.last_message_at ? this._timeAgo(c.last_message_at) : '';
            const unread = c.unread_count || 0;
            const windowOk = c.within_24h_window;
            const isActive = this.activeConvId === c.id;

            return `<div onclick="window.whatsappManager.openConversation(${c.id})"
                class="flex items-center gap-3 px-4 py-3 cursor-pointer border-b border-gray-100 hover:bg-gray-50 transition-colors ${isActive ? 'bg-gray-50' : ''}"
                data-conv-id="${c.id}">
                <div class="relative flex-shrink-0">
                    <div class="w-10 h-10 rounded-full bg-green-500 flex items-center justify-center text-white font-bold text-sm">
                        ${name.charAt(0).toUpperCase()}
                    </div>
                    <span class="absolute bottom-0 right-0 w-3 h-3 rounded-full border-2 border-white ${windowOk ? 'bg-green-400' : 'bg-gray-300'}"></span>
                </div>
                <div class="flex-1 min-w-0">
                    <div class="flex justify-between items-center">
                        <p class="font-medium text-sm text-gray-900 truncate">${this._esc(name)}</p>
                        <span class="text-xs text-gray-400 flex-shrink-0">${lastAt}</span>
                    </div>
                    <p class="text-xs text-gray-500 truncate">${this._esc(lastMsg.substring(0, 50))}</p>
                </div>
                ${unread ? `<span data-unread-badge="1" class="bg-green-500 text-white text-xs rounded-full px-1.5 py-0.5 flex-shrink-0">${unread}</span>` : ''}
            </div>`;
        }).join('');
    }

    async openConversation(convId) {
        this.activeConvId = convId;

        // Highlight active conversation
        document.querySelectorAll('[data-conv-id]').forEach(el => {
            el.classList.toggle('bg-gray-50', parseInt(el.dataset.convId) === convId);
            el.classList.remove('bg-gray-800');
        });

        const chatPanel = document.getElementById('waChatPanel');
        const emptyState = document.getElementById('waChatEmpty');
        if (chatPanel) chatPanel.classList.remove('hidden');
        if (emptyState) emptyState.classList.add('hidden');

        try {
            const res = await this._api('GET', `/api/whatsapp/conversations/${convId}/messages?per_page=100`);
            const data = await res.json();

            const conv = data.conversation || {};
            const contact = conv.contact || {};
            const msgs = data.messages || [];

            // Set header
            const headerName = document.getElementById('waChatContactName');
            const headerPhone = document.getElementById('waChatContactPhone');
            if (headerName) headerName.textContent = contact.name || contact.phone_number || 'Customer';
            if (headerPhone) headerPhone.textContent = contact.phone_number || '';

            // Check 24h window
            const windowRes = await this._api('GET', `/api/whatsapp/conversations/${convId}/window`);
            const windowData = await windowRes.json();
            this._updateChatWindowUI(windowData);

            // Render messages
            this._renderMessages(msgs);

            // Reload the conversation item to reset unread badge
            this._updateConvItemUnread(convId, 0);
        } catch (e) {
            console.error('Open conversation error', e);
        }
    }

    _updateConvItemUnread(convId, count) {
        const item = document.querySelector(`[data-conv-id="${convId}"]`);
        if (!item) return;
        const badge = item.querySelector('[data-unread-badge="1"]');
        if (badge) badge.remove();
    }

    _updateChatWindowUI(windowData) {
        const withinWindow = windowData.within_window;
        const windowBanner = document.getElementById('waChatWindowBanner');
        const windowChip = document.getElementById('waChatWindowChip');
        const textInput = document.getElementById('waChatMsgInput');
        const sendBtn = document.getElementById('waChatSendBtn');
        const tplBtn = document.getElementById('waChatSendTemplateBtn');

        if (!withinWindow) {
            if (windowChip) {
                windowChip.classList.remove('wa-window-chip--open');
                windowChip.classList.add('wa-window-chip--closed');
                windowChip.innerHTML = '<span style="width:6px;height:6px;border-radius:50%;background:#9ca3af;display:inline-block"></span><span class="text-xs">Window Closed</span>';
            }
            if (windowBanner) {
                windowBanner.innerHTML = `<i class="fas fa-clock mr-2"></i>
                    <span>24-hour window expired. Send a template to re-open this conversation.</span>
                    <button id="waBannerSendTemplateBtn" type="button" class="ml-auto text-xs font-semibold underline hover:no-underline">Send Template</button>`;
                windowBanner.classList.remove('hidden');
                const bannerBtn = document.getElementById('waBannerSendTemplateBtn');
                if (bannerBtn) {
                    bannerBtn.onclick = () => this._openSendTemplatePanel();
                }
            }
            if (textInput) { textInput.disabled = true; textInput.placeholder = 'Send a template to re-open the conversation…'; }
            if (sendBtn) sendBtn.disabled = true;
            if (tplBtn) tplBtn.classList.add('wa-btn-pulse');
        } else {
            if (windowChip) {
                windowChip.classList.remove('wa-window-chip--closed');
                windowChip.classList.add('wa-window-chip--open');
                windowChip.innerHTML = '<span style="width:6px;height:6px;border-radius:50%;background:#4ade80;display:inline-block"></span><span class="text-xs">Window Open</span>';
            }
            if (windowBanner) windowBanner.classList.add('hidden');
            if (textInput) { textInput.disabled = false; textInput.placeholder = 'Type a message…'; }
            if (sendBtn) sendBtn.disabled = false;
            if (tplBtn) tplBtn.classList.remove('wa-btn-pulse');
        }
    }

    _renderMessages(msgs) {
        const container = document.getElementById('waChatMessages');
        if (!container) return;
        container.innerHTML = '';

        if (!msgs.length) {
            container.innerHTML = '<div class="text-center text-gray-500 py-8">No messages yet. Start the conversation with a template.</div>';
            return;
        }

        msgs.forEach(m => {
            const isAgent = m.sender_type === 'agent';
            const isSystem = m.sender_type === 'system';
            const isTemplate = m.message_type === 'template';
            const timeStr = m.created_at ? new Date(m.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '';
            const statusIcon = isAgent ? this._statusIcon(m.status) : '';

            let msgContent = this._esc(m.message_text || '');
            if (isTemplate) {
                msgContent = `<span class="inline-block mr-1 text-green-400"><i class="fas fa-file-alt"></i></span>${msgContent}`;
            }
            if (m.message_type === 'image') msgContent = '<i class="fas fa-image mr-1 text-blue-400"></i> Image';
            if (m.message_type === 'audio') msgContent = '<i class="fas fa-microphone mr-1 text-purple-400"></i> Voice message';
            if (m.message_type === 'video') msgContent = '<i class="fas fa-video mr-1 text-red-400"></i> Video';
            if (m.message_type === 'document') msgContent = `<i class="fas fa-file mr-1 text-orange-400"></i> ${this._esc(m.media_filename || 'Document')}`;

            const bubble = document.createElement('div');
            bubble.className = `flex ${isAgent ? 'justify-end' : 'justify-start'} mb-2`;
            bubble.innerHTML = `
                <div class="max-w-xs lg:max-w-md px-3 py-2 rounded-2xl text-sm shadow-md break-words
                    ${isAgent
                    ? 'bg-green-600 text-white rounded-br-sm'
                    : isSystem
                        ? 'bg-gray-100 text-gray-500 italic text-xs'
                        : 'bg-white text-gray-800 rounded-bl-sm border border-gray-100 shadow-sm'}">
                    ${msgContent}
                    <div class="text-right text-xs mt-1 ${isAgent ? 'text-green-200' : 'text-gray-400'}">
                        ${timeStr} ${statusIcon}
                    </div>
                </div>`;
            container.appendChild(bubble);
        });

        // Scroll to bottom
        container.scrollTop = container.scrollHeight;
    }

    _statusIcon(status) {
        if (status === 'read') return '<i class="fas fa-check-double text-blue-300"></i>';
        if (status === 'delivered') return '<i class="fas fa-check-double text-green-200"></i>';
        if (status === 'sent') return '<i class="fas fa-check text-green-200"></i>';
        if (status === 'failed') return '<i class="fas fa-times text-red-400"></i>';
        return '';
    }

    async _sendChatMessage() {
        if (!this.activeConvId) return;
        const input = document.getElementById('waChatMsgInput');
        const text = input?.value?.trim();
        if (!text) return;

        input.value = '';
        input.disabled = true;

        try {
            const res = await this._api('POST', `/api/whatsapp/conversations/${this.activeConvId}/send`, {
                type: 'text', text
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.error || 'Send failed');
            // Refresh messages
            await this.openConversation(this.activeConvId);
        } catch (e) {
            this._toast(e.message, 'error');
        } finally {
            if (input) input.disabled = false;
            if (input) input.focus();
        }
    }

    async _sendDirectMediaMessage() {
        if (!this.activeConvId) return;
        const typeSelect = document.getElementById('waDirectMediaType');
        const urlInput = document.getElementById('waDirectMediaUrl');
        const captionInput = document.getElementById('waDirectMediaCaption');

        const type = typeSelect?.value || 'image';
        const media_link = urlInput?.value?.trim();
        const caption = captionInput?.value?.trim();
        const filename = (type === 'document' && media_link) ? media_link.split('/').pop() : undefined;

        if (!media_link) { this._toast('Media URL is required', 'error'); return; }

        const btn = document.getElementById('waDirectMediaSendBtn');
        if (btn) { btn.disabled = true; btn.textContent = 'Sending...'; }

        try {
            const payload = { type, media_link, caption };
            if (filename) payload.filename = filename;

            const res = await this._api('POST', `/api/whatsapp/conversations/${this.activeConvId}/send`, payload);
            const data = await res.json();
            if (!res.ok) throw new Error(data.error || 'Media send failed');

            this._toast('Media sent! ✅', 'success');

            // Clean up UI
            document.getElementById('waDirectMediaPanel').classList.add('hidden');
            urlInput.value = '';
            captionInput.value = '';

            // Refresh messages
            await this.openConversation(this.activeConvId);
        } catch (e) {
            this._toast(e.message, 'error');
        } finally {
            if (btn) { btn.disabled = false; btn.textContent = 'Send Media'; }
        }
    }

    /* ─────────────────────────────────────────
       SEND TEMPLATE FROM INBOX
    ───────────────────────────────────────── */
    async _openSendTemplatePanel() {
        try {
            await this._ensureTemplatesLoaded(true);
        } catch (e) {
            this._toast(e.message || 'Failed to load templates', 'error');
            return;
        }

        const panel = document.getElementById('waSendTemplatePanel');
        if (!panel) return;
        panel.classList.toggle('hidden');

        // Populate template dropdown
        const select = document.getElementById('waSendTplSelect');
        if (select) {
            const approved = this.templates.filter(t => String(t.status || '').trim().toUpperCase() === 'APPROVED');
            select.innerHTML = `<option value="">— Select Template —</option>` +
                approved.map(t => `<option value="${t.id}" data-name="${this._esc(t.name)}" data-vars="${t.variable_count}" data-body="${this._esc(t.body_text || '')}" data-lang="${t.language}" data-header-type="${t.header_type}">${this._esc(t.name)} (${t.variable_count} var)</option>`).join('');

            select.onchange = () => this._onTemplateSelectChange(select);
            if (!approved.length) {
                this._toast('No APPROVED templates found. Go to Templates tab and Sync from Brandmo.', 'warning');
            }
        }

        const sendBtn = document.getElementById('waSendTemplateConfirmBtn');
        if (sendBtn) {
            sendBtn.onclick = () => this._sendTemplateFromInbox();
        }
    }

    _onTemplateSelectChange(select) {
        const opt = select.options[select.selectedIndex];
        const varCount = parseInt(opt.dataset.vars || '0');
        const body = opt.dataset.body || '';
        const headerType = opt.dataset.headerType || 'NONE';
        const container = document.getElementById('waSendTplVarsContainer');
        const headerWrap = document.getElementById('waSendTplHeaderWrap');
        const headerLabel = document.getElementById('waSendTplHeaderType');

        if (!container) return;

        // Toggle media header box
        if (headerWrap && headerType && ['IMAGE', 'VIDEO', 'DOCUMENT'].includes(headerType)) {
            headerWrap.classList.remove('hidden');
            if (headerLabel) headerLabel.textContent = headerType;
        } else if (headerWrap) {
            headerWrap.classList.add('hidden');
        }

        container.innerHTML = '';
        if (varCount > 0) {
            for (let i = 1; i <= varCount; i++) {
                container.innerHTML += `<div class="mb-2">
                    <label class="text-xs text-gray-400 block mb-1">Variable {{${i}}}</label>
                    <input type="text" id="waSendVar${i}" placeholder="Value for {{${i}}}"
                        class="bg-gray-700 text-white text-sm rounded px-3 py-1.5 w-full border border-gray-600 focus:border-green-500 focus:outline-none" />
                </div>`;
            }
        }

        const preview = document.getElementById('waSendTplPreview');
        if (preview) preview.textContent = body || '(select a template to preview)';
    }

    async _sendTemplateFromInbox() {
        if (!this.activeConvId) return;
        const select = document.getElementById('waSendTplSelect');
        const tplId = select?.value;
        if (!tplId) { this._toast('Please select a template.', 'error'); return; }

        const opt = select.options[select.selectedIndex];
        // Use data-name attribute (robust — avoids splitting on '(')
        const tplName = opt.dataset.name;
        const language = opt.dataset.lang || 'en';
        const varCount = parseInt(opt.dataset.vars || '0');
        const headerType = opt.dataset.headerType || 'NONE';
        const params = [];

        for (let i = 1; i <= varCount; i++) {
            const val = document.getElementById(`waSendVar${i}`)?.value?.trim();
            if (!val) { this._toast(`Please fill in variable {{${i}}}`, 'error'); return; }
            params.push(val);
        }

        // Build header
        let header = null;
        if (['IMAGE', 'VIDEO', 'DOCUMENT'].includes(headerType)) {
            const urlNode = document.getElementById('waSendTplHeaderUrl');
            const urlVal = urlNode?.value?.trim();
            if (!urlVal) { this._toast(`Please provide a media URL for the ${headerType} header`, 'error'); return; }
            header = {
                type: headerType.toLowerCase(),
                [headerType.toLowerCase()]: { link: urlVal }
            };
        }

        const btn = document.getElementById('waSendTemplateConfirmBtn');
        if (btn) { btn.disabled = true; btn.textContent = 'Sending…'; }

        try {
            const payload = {
                type: 'template', template_name: tplName, parameters: params, language
            };
            if (header) payload.header = header;

            const res = await this._api('POST', `/api/whatsapp/conversations/${this.activeConvId}/send`, payload);
            const data = await res.json();
            if (!res.ok) throw new Error(data.error || 'Send failed');
            this._toast('Template sent! ✅', 'success');

            // Close panel, refresh window check + messages
            document.getElementById('waSendTemplatePanel')?.classList.add('hidden');
            await this.openConversation(this.activeConvId);
        } catch (e) {
            this._toast(e.message, 'error');
        } finally {
            if (btn) { btn.disabled = false; btn.textContent = 'Send Template'; }
        }
    }

    /* ─────────────────────────────────────────
       SEND TEMPLATE FROM LEADS / EXTERNAL
    ───────────────────────────────────────── */
    async sendTemplateToPhone(phone, templateName, parameters) {
        try {
            const res = await this._api('POST', '/api/whatsapp/send-template', {
                phone, template_name: templateName, parameters
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.error || 'Send failed');
            this._toast(`Template sent to ${phone} ✅`, 'success');
            return data;
        } catch (e) {
            this._toast(e.message, 'error');
            throw e;
        }
    }

    /* ─────────────────────────────────────────
       UTILITIES
    ───────────────────────────────────────── */
    async _api(method, path, body = null) {
        const opts = { method };
        if (body) opts.body = JSON.stringify(body);
        // Use auth.makeAuthenticatedRequest for proper 401/403/5xx handling
        const res = await auth.makeAuthenticatedRequest(path, opts);
        if (!res) throw new Error('Request failed or session expired');
        return res;
    }

    _esc(str) {
        if (!str) return '';
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    async _ensureTemplatesLoaded(force = false) {
        if (!force && this.templates && this.templates.length) return;
        const qs = force ? `?_=${Date.now()}` : '';
        const res = await this._api('GET', `/api/whatsapp/templates${qs}`);
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Failed to load templates');
        this.templates = data.templates || [];
    }

    _timeAgo(dateStr) {
        if (!dateStr) return '';
        const diff = Math.floor((Date.now() - new Date(dateStr)) / 1000);
        if (diff < 60) return 'just now';
        if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
        if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
        return new Date(dateStr).toLocaleDateString();
    }

    _toast(msg, type = 'info') {
        const colors = { success: '#22c55e', error: '#ef4444', info: '#3b82f6', warning: '#f59e0b' };
        const toast = document.createElement('div');
        toast.style.cssText = `
            position:fixed; bottom:24px; right:24px; z-index:9999; padding:12px 20px;
            background:${colors[type] || colors.info}; color:#fff; border-radius:8px;
            font-size:14px; font-weight:500; box-shadow:0 4px 16px rgba(0,0,0,0.3);
            transform:translateY(10px); opacity:0; transition:all .3s;
        `;
        toast.textContent = msg;
        document.body.appendChild(toast);
        requestAnimationFrame(() => { toast.style.transform = 'translateY(0)'; toast.style.opacity = '1'; });
        setTimeout(() => {
            toast.style.opacity = '0';
            setTimeout(() => toast.remove(), 300);
        }, 4000);
    }
}

// Global singleton
window.whatsappManager = new WhatsAppManager();

// Fallback initialization in case section is opened before main nav init wiring.
document.addEventListener('DOMContentLoaded', () => {
    if (window.whatsappManager && !window.whatsappManager._eventsBound) {
        window.whatsappManager.init();
    }
});
