(function initA2uiRenderer(global) {
  const STANDARD_CATALOG_ID = 'https://a2ui.org/specification/v0_8/standard_catalog_definition.json';

  function tryParseProtocolPayload(raw) {
    if (!raw) return null;
    try {
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed)) return parsed;
      if (parsed && typeof parsed === 'object') {
        if (Array.isArray(parsed.messages)) return parsed.messages;
        if (parsed.a2ui && Array.isArray(parsed.a2ui.messages)) return parsed.a2ui.messages;
        if (parsed.surfaceUpdate || parsed.dataModelUpdate || parsed.beginRendering || parsed.deleteSurface) {
          return [parsed];
        }
      }
      if (typeof parsed === 'string') {
        return tryParseProtocolPayload(parsed);
      }
      return null;
    } catch (e) {
      return null;
    }
  }

  function render(ai, protocolPayload, options) {
    if (!ai?.a2ui) return false;
    const messages = Array.isArray(protocolPayload) ? protocolPayload : tryParseProtocolPayload(protocolPayload);
    if (!messages || messages.length === 0) return false;
    const rendered = renderProtocol(messages, options || {});
    if (!rendered) return false;
    ai.a2ui.classList.add('active');
    ai.a2ui.innerHTML = rendered.html;
    rendered.bind(ai.a2ui);
    return true;
  }

  function renderProtocol(messages, options) {
    const surfaces = new Map();

    function ensureSurface(surfaceId) {
      if (!surfaces.has(surfaceId)) {
        surfaces.set(surfaceId, {
          components: new Map(),
          dataModel: {},
          root: '',
          catalogId: STANDARD_CATALOG_ID
        });
      }
      return surfaces.get(surfaceId);
    }

    for (const msg of messages) {
      if (msg?.surfaceUpdate) {
        const surface = ensureSurface(msg.surfaceUpdate.surfaceId || 'default-surface');
        const components = Array.isArray(msg.surfaceUpdate.components) ? msg.surfaceUpdate.components : [];
        components.forEach(component => {
          if (component?.id && component?.component) {
            surface.components.set(component.id, component.component);
          }
        });
      }
      if (msg?.dataModelUpdate) {
        const surface = ensureSurface(msg.dataModelUpdate.surfaceId || 'default-surface');
        applyDataModelUpdate(surface.dataModel, msg.dataModelUpdate.path || '', msg.dataModelUpdate.contents || []);
      }
      if (msg?.beginRendering) {
        const surface = ensureSurface(msg.beginRendering.surfaceId || 'default-surface');
        surface.root = msg.beginRendering.root || '';
        surface.catalogId = msg.beginRendering.catalogId || STANDARD_CATALOG_ID;
      }
      if (msg?.deleteSurface) {
        surfaces.delete(msg.deleteSurface.surfaceId || '');
      }
    }

    const firstSurfaceEntry = Array.from(surfaces.entries()).find(([, surface]) => surface.root);
    if (!firstSurfaceEntry) return null;
    const [surfaceId, surface] = firstSurfaceEntry;
    if (surface.catalogId !== STANDARD_CATALOG_ID) return null;

    const bindings = [];
    const html = renderComponent(surface, surface.root, bindings, {
      ...options,
      surfaceId,
      modalStack: []
    });
    return {
      html,
      bind(rootEl) {
        bindings.forEach(fn => fn(rootEl));
      }
    };
  }

  function renderComponent(surface, componentId, bindings, options, scopePath) {
    const componentWrapper = surface.components.get(componentId);
    if (!componentWrapper || typeof componentWrapper !== 'object') return '';
    const entries = Object.entries(componentWrapper);
    if (entries.length !== 1) return '';
    const [type, props] = entries[0];

    switch (type) {
      case 'Column':
      case 'Row':
      case 'List':
        return renderContainer(surface, componentId, type, props || {}, bindings, options, scopePath);
      case 'Card':
        return `<section class="a2ui-card" data-card-child="${escapeHtml(props?.child || '')}" data-component-id="${escapeHtml(componentId)}">${renderComponent(surface, props?.child, bindings, options, scopePath)}</section>`;
      case 'Text':
        return renderText(surface, props || {}, scopePath);
      case 'Image':
        return renderImage(surface, props || {}, scopePath);
      case 'Icon':
        return renderIcon(surface, props || {}, scopePath);
      case 'Video':
        return renderVideo(surface, props || {}, scopePath);
      case 'AudioPlayer':
        return renderAudio(surface, props || {}, scopePath);
      case 'Divider':
        return '<hr class="a2ui-divider" />';
      case 'Tabs':
        return renderTabs(surface, componentId, props || {}, bindings, options, scopePath);
      case 'Modal':
        return renderModal(surface, componentId, props || {}, bindings, options, scopePath);
      case 'Button':
        return renderButton(surface, componentId, props || {}, bindings, options, scopePath);
      case 'CheckBox':
        return renderCheckBox(surface, componentId, props || {}, bindings, scopePath);
      case 'TextField':
        return renderTextField(surface, componentId, props || {}, bindings, scopePath);
      case 'DateTimeInput':
        return renderDateTimeInput(surface, componentId, props || {}, bindings, scopePath);
      case 'MultipleChoice':
        return renderMultipleChoice(surface, componentId, props || {}, bindings, scopePath);
      case 'Slider':
        return renderSlider(surface, componentId, props || {}, bindings, scopePath);
      default:
        return '';
    }
  }

  function renderContainer(surface, componentId, type, props, bindings, options, scopePath) {
    const className = type === 'Row' ? 'a2ui-row' : type === 'List' ? 'a2ui-list-wrap' : 'a2ui-column';
    const template = props?.children?.template;
    let childIds = Array.isArray(props?.children?.explicitList) ? props.children.explicitList : [];

    if (template?.componentId && template?.dataBinding) {
      const items = resolveModelPath(surface.dataModel, template.dataBinding, scopePath);
      childIds = Array.isArray(items) ? items.map((_, index) => `${template.componentId}::${index}`) : [];
      return `<div class="${className}" data-component-id="${escapeHtml(componentId)}">${childIds.map((derivedId, index) =>
        renderComponent(surface, template.componentId, bindings, options, appendScope(scopePath, template.dataBinding, index))
      ).join('')}</div>`;
    }

    return `<div class="${className}" data-component-id="${escapeHtml(componentId)}">${childIds.map(id =>
      renderComponent(surface, id, bindings, options, scopePath)
    ).join('')}</div>`;
  }

  function renderText(surface, props, scopePath) {
    const value = getBoundValue(surface.dataModel, props.text, scopePath);
    const usageHint = props.usageHint || 'body';
    const rendered = escapeHtml(String(value ?? '')).replace(/\n/g, '<br>');
    return `<div class="a2ui-text a2ui-text-${escapeHtml(usageHint)}">${rendered}</div>`;
  }

  function renderImage(surface, props, scopePath) {
    const url = String(getBoundValue(surface.dataModel, props.url, scopePath) || '').trim();
    if (!url) return '';
    const altText = String(getBoundValue(surface.dataModel, props.altText, scopePath) || '').trim();
    const fit = String(props.fit || 'cover');
    return `<div class="a2ui-thumb"><img src="${escapeHtml(url)}" alt="${escapeHtml(altText)}" loading="lazy" style="object-fit:${escapeHtml(fit)}" /></div>`;
  }

  function renderIcon(surface, props, scopePath) {
    const name = String(getBoundValue(surface.dataModel, props.name, scopePath) || '').trim();
    return `<span class="a2ui-icon material-symbols-outlined">${escapeHtml(name || 'info')}</span>`;
  }

  function renderVideo(surface, props, scopePath) {
    const url = String(getBoundValue(surface.dataModel, props.url, scopePath) || '').trim();
    if (!url) return '';
    return `<video class="a2ui-video" controls preload="metadata" src="${escapeHtml(url)}"></video>`;
  }

  function renderAudio(surface, props, scopePath) {
    const url = String(getBoundValue(surface.dataModel, props.url, scopePath) || '').trim();
    if (!url) return '';
    const description = String(getBoundValue(surface.dataModel, props.description, scopePath) || '').trim();
    return `<div class="a2ui-audio">${description ? `<div class="a2ui-text a2ui-text-body">${escapeHtml(description)}</div>` : ''}<audio controls preload="metadata" src="${escapeHtml(url)}"></audio></div>`;
  }

  function renderTabs(surface, componentId, props, bindings, options, scopePath) {
    const items = Array.isArray(props.tabItems) ? props.tabItems : [];
    if (items.length === 0) return '';
    const tabButtons = items.map((item, index) => {
      const title = getBoundValue(surface.dataModel, item.title, scopePath);
      return `<button type="button" class="a2ui-tab${index === 0 ? ' active' : ''}" data-tab-button="${escapeHtml(componentId)}" data-tab-index="${index}">${escapeHtml(String(title || `Tab ${index + 1}`))}</button>`;
    }).join('');
    const tabPanels = items.map((item, index) => {
      const content = renderComponent(surface, item.child, bindings, options, scopePath);
      return `<div class="a2ui-tab-panel${index === 0 ? ' active' : ''}" data-tab-panel="${escapeHtml(componentId)}" data-tab-index="${index}">${content}</div>`;
    }).join('');
    bindings.push(rootEl => {
      rootEl.querySelectorAll(`[data-tab-button="${componentId}"]`).forEach(button => {
        button.addEventListener('click', () => {
          const index = button.getAttribute('data-tab-index');
          rootEl.querySelectorAll(`[data-tab-button="${componentId}"]`).forEach(btn => {
            btn.classList.toggle('active', btn.getAttribute('data-tab-index') === index);
          });
          rootEl.querySelectorAll(`[data-tab-panel="${componentId}"]`).forEach(panel => {
            panel.classList.toggle('active', panel.getAttribute('data-tab-index') === index);
          });
        });
      });
    });
    return `<div class="a2ui-tabs"><div class="a2ui-tab-bar">${tabButtons}</div>${tabPanels}</div>`;
  }

  function renderModal(surface, componentId, props, bindings, options, scopePath) {
    const trigger = renderComponent(surface, props.entryPointChild, bindings, options, scopePath);
    const content = renderComponent(surface, props.contentChild, bindings, options, scopePath);
    bindings.push(rootEl => {
      const wrapper = rootEl.querySelector(`[data-modal-id="${componentId}"]`);
      if (!wrapper) return;
      const opener = wrapper.querySelector('[data-modal-open]');
      const closer = wrapper.querySelector('[data-modal-close]');
      const overlay = wrapper.querySelector('.a2ui-modal-overlay');
      const toggle = open => wrapper.classList.toggle('active', open);
      if (opener) opener.addEventListener('click', () => toggle(true));
      if (closer) closer.addEventListener('click', () => toggle(false));
      if (overlay) overlay.addEventListener('click', event => {
        if (event.target === overlay) toggle(false);
      });
    });
    return `<div class="a2ui-modal" data-modal-id="${escapeHtml(componentId)}"><div data-modal-open>${trigger}</div><div class="a2ui-modal-overlay"><div class="a2ui-modal-content"><button type="button" class="a2ui-modal-close" data-modal-close>x</button>${content}</div></div></div>`;
  }

  function renderButton(surface, componentId, props, bindings, options, scopePath) {
    const label = renderComponent(surface, props.child, bindings, options, scopePath);
    const primary = props.primary ? ' a2ui-action-primary' : '';
    bindings.push(rootEl => {
      const button = rootEl.querySelector(`[data-action-id="${componentId}"]`);
      if (!button) return;
      button.addEventListener('click', event => {
        event.preventDefault();
        dispatchAction(surface, componentId, props.action, options, scopePath);
      });
    });
    return `<button type="button" class="a2ui-action${primary}" data-action-id="${escapeHtml(componentId)}"><span class="a2ui-action-label">${label}</span></button>`;
  }

  function renderCheckBox(surface, componentId, props, bindings, scopePath) {
    const label = String(getBoundValue(surface.dataModel, props.label, scopePath) || '');
    const checked = !!getBoundValue(surface.dataModel, props.value, scopePath);
    bindings.push(rootEl => {
      const input = rootEl.querySelector(`[data-checkbox-id="${componentId}"]`);
      if (!input) return;
      input.addEventListener('change', event => {
        setBoundValue(surface.dataModel, props.value, event.target.checked, scopePath);
      });
    });
    return `<label class="a2ui-checkbox"><input type="checkbox" data-checkbox-id="${escapeHtml(componentId)}" ${checked ? 'checked' : ''} /><span>${escapeHtml(label)}</span></label>`;
  }

  function renderTextField(surface, componentId, props, bindings, scopePath) {
    const label = String(getBoundValue(surface.dataModel, props.label, scopePath) || '');
    const value = String(getBoundValue(surface.dataModel, props.text, scopePath) || '');
    const inputType = mapTextFieldType(props.textFieldType);
    initializeBoundValue(surface.dataModel, props.text, value, scopePath);
    bindings.push(rootEl => {
      const input = rootEl.querySelector(`[data-field-id="${componentId}"]`);
      if (!input) return;
      input.addEventListener('input', event => {
        setBoundValue(surface.dataModel, props.text, event.target.value, scopePath);
      });
    });
    if (props.textFieldType === 'longText') {
      return `<label class="a2ui-field"><span>${escapeHtml(label)}</span><textarea class="a2ui-input" data-field-id="${escapeHtml(componentId)}">${escapeHtml(value)}</textarea></label>`;
    }
    return `<label class="a2ui-field"><span>${escapeHtml(label)}</span><input class="a2ui-input" data-field-id="${escapeHtml(componentId)}" type="${escapeHtml(inputType)}" value="${escapeHtml(value)}" /></label>`;
  }

  function renderDateTimeInput(surface, componentId, props, bindings, scopePath) {
    const value = String(getBoundValue(surface.dataModel, props.value, scopePath) || '');
    initializeBoundValue(surface.dataModel, props.value, value, scopePath);
    const type = props.enableDate && props.enableTime ? 'datetime-local' : props.enableDate ? 'date' : 'time';
    bindings.push(rootEl => {
      const input = rootEl.querySelector(`[data-datetime-id="${componentId}"]`);
      if (!input) return;
      input.addEventListener('input', event => {
        setBoundValue(surface.dataModel, props.value, event.target.value, scopePath);
      });
    });
    return `<label class="a2ui-field"><span>날짜/시간</span><input class="a2ui-input" data-datetime-id="${escapeHtml(componentId)}" type="${escapeHtml(type)}" value="${escapeHtml(value)}" /></label>`;
  }

  function renderMultipleChoice(surface, componentId, props, bindings, scopePath) {
    const selections = getBoundValue(surface.dataModel, props.selections, scopePath);
    const selectedValues = Array.isArray(selections) ? selections.slice() : [];
    initializeBoundValue(surface.dataModel, props.selections, selectedValues, scopePath);
    const optionsHtml = (Array.isArray(props.options) ? props.options : []).map((option, index) => {
      const label = getBoundValue(surface.dataModel, option.label, scopePath);
      const checked = selectedValues.includes(option.value);
      const type = props.variant === 'checkbox' || !props.maxAllowedSelections || props.maxAllowedSelections > 1 ? 'checkbox' : 'radio';
      return `<label class="a2ui-checkbox"><input type="${type}" data-multi-id="${escapeHtml(componentId)}" data-option-value="${escapeHtml(option.value)}" ${checked ? 'checked' : ''} /><span>${escapeHtml(String(label || option.value))}</span></label>`;
    }).join('');
    bindings.push(rootEl => {
      rootEl.querySelectorAll(`[data-multi-id="${componentId}"]`).forEach(input => {
        input.addEventListener('change', () => {
          const values = Array.from(rootEl.querySelectorAll(`[data-multi-id="${componentId}"]:checked`))
            .map(node => node.getAttribute('data-option-value'));
          setBoundValue(surface.dataModel, props.selections, values, scopePath);
        });
      });
    });
    return `<div class="a2ui-column">${optionsHtml}</div>`;
  }

  function renderSlider(surface, componentId, props, bindings, scopePath) {
    const label = String(getBoundValue(surface.dataModel, props.label, scopePath) || '');
    const value = Number(getBoundValue(surface.dataModel, props.value, scopePath) || props.minValue || 0);
    initializeBoundValue(surface.dataModel, props.value, value, scopePath);
    bindings.push(rootEl => {
      const input = rootEl.querySelector(`[data-slider-id="${componentId}"]`);
      const output = rootEl.querySelector(`[data-slider-output="${componentId}"]`);
      if (!input) return;
      input.addEventListener('input', event => {
        const numeric = Number(event.target.value);
        setBoundValue(surface.dataModel, props.value, numeric, scopePath);
        if (output) output.textContent = String(numeric);
      });
    });
    return `<label class="a2ui-field"><span>${escapeHtml(label)}</span><input type="range" class="a2ui-slider" data-slider-id="${escapeHtml(componentId)}" min="${escapeHtml(props.minValue ?? 0)}" max="${escapeHtml(props.maxValue ?? 100)}" value="${escapeHtml(value)}" /><span class="a2ui-text a2ui-text-caption" data-slider-output="${escapeHtml(componentId)}">${escapeHtml(value)}</span></label>`;
  }

  function dispatchAction(surface, componentId, action, options, scopePath) {
    if (!action || typeof action !== 'object') return;
    const context = {};
    (Array.isArray(action.context) ? action.context : []).forEach(entry => {
      if (!entry?.key) return;
      context[entry.key] = getBoundValue(surface.dataModel, entry.value, scopePath);
    });
        if (typeof options?.onUserAction === 'function') {
          options.onUserAction({
            userAction: {
              name: action.name || '',
              surfaceId: options.surfaceId || '',
              sourceComponentId: componentId,
          timestamp: new Date().toISOString(),
          context
        }
      });
    }
  }

  function initializeBoundValue(model, boundValue, fallback, scopePath) {
    if (!boundValue?.path) return;
    const current = resolveModelPath(model, boundValue.path, scopePath);
    if (current === undefined && fallback !== undefined) {
      setBoundValue(model, boundValue, fallback, scopePath);
    }
  }

  function setBoundValue(model, boundValue, value, scopePath) {
    const path = normalizePath(boundValue?.path, scopePath);
    if (!path) return;
    setModelValue(model, path, value);
  }

  function getBoundValue(model, boundValue, scopePath) {
    if (boundValue == null) return '';
    if (typeof boundValue !== 'object') return boundValue;
    if (boundValue.path) {
      const resolved = resolveModelPath(model, boundValue.path, scopePath);
      if (resolved !== undefined) return resolved;
    }
    if (Object.prototype.hasOwnProperty.call(boundValue, 'literalString')) return boundValue.literalString;
    if (Object.prototype.hasOwnProperty.call(boundValue, 'literalNumber')) return boundValue.literalNumber;
    if (Object.prototype.hasOwnProperty.call(boundValue, 'literalBoolean')) return boundValue.literalBoolean;
    if (Object.prototype.hasOwnProperty.call(boundValue, 'literalArray')) return boundValue.literalArray;
    return '';
  }

  function applyDataModelUpdate(model, path, contents) {
    const target = ensureModelPath(model, path);
    (Array.isArray(contents) ? contents : []).forEach(entry => {
      if (!entry?.key) return;
      if (Object.prototype.hasOwnProperty.call(entry, 'valueString')) target[entry.key] = entry.valueString;
      else if (Object.prototype.hasOwnProperty.call(entry, 'valueNumber')) target[entry.key] = entry.valueNumber;
      else if (Object.prototype.hasOwnProperty.call(entry, 'valueBoolean')) target[entry.key] = entry.valueBoolean;
      else if (Object.prototype.hasOwnProperty.call(entry, 'valueArray')) target[entry.key] = entry.valueArray;
      else if (Object.prototype.hasOwnProperty.call(entry, 'valueMap')) {
        const nested = {};
        applyDataModelUpdate(nested, '', entry.valueMap || []);
        target[entry.key] = nested;
      }
    });
  }

  function ensureModelPath(model, path) {
    const normalized = String(path || '').replace(/^\/+/, '');
    if (!normalized) return model;
    return normalized.split('/').filter(Boolean).reduce((acc, key) => {
      if (!acc[key] || typeof acc[key] !== 'object') acc[key] = {};
      return acc[key];
    }, model);
  }

  function resolveModelPath(model, path, scopePath) {
    const normalized = normalizePath(path, scopePath);
    if (!normalized) return model;
    return normalized.split('/').filter(Boolean).reduce((acc, key) => {
      if (acc == null) return undefined;
      return acc[key];
    }, model);
  }

  function normalizePath(path, scopePath) {
    const raw = String(path || '').trim();
    if (!raw) return '';
    if (raw.startsWith('/')) return raw.replace(/^\/+/, '');
    const prefix = String(scopePath || '').replace(/^\/+|\/+$/g, '');
    const suffix = raw.replace(/^\/+/, '');
    return [prefix, suffix].filter(Boolean).join('/');
  }

  function appendScope(baseScope, bindingPath, index) {
    const normalized = normalizePath(bindingPath, baseScope);
    return `/${[normalized, index].filter(v => v !== '').join('/')}`;
  }

  function setModelValue(model, path, value) {
    const normalized = String(path || '').replace(/^\/+/, '');
    if (!normalized) return;
    const parts = normalized.split('/').filter(Boolean);
    let cursor = model;
    for (let i = 0; i < parts.length - 1; i += 1) {
      const key = parts[i];
      const nextKey = parts[i + 1];
      if (!cursor[key] || typeof cursor[key] !== 'object') {
        cursor[key] = /^\d+$/.test(nextKey) ? [] : {};
      }
      cursor = cursor[key];
    }
    const last = parts[parts.length - 1];
    if (Array.isArray(cursor) && /^\d+$/.test(last)) {
      cursor[Number(last)] = value;
    } else {
      cursor[last] = value;
    }
  }

  function mapTextFieldType(type) {
    switch (type) {
      case 'number':
        return 'number';
      case 'date':
        return 'date';
      case 'obscured':
        return 'password';
      default:
        return 'text';
    }
  }

  function escapeHtml(value) {
    return String(value ?? '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  global.A2uiRenderer = {
    STANDARD_CATALOG_ID,
    tryParseProtocolPayload,
    render
  };
}(window));
