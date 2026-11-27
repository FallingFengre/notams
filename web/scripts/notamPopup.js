function mapIcon(name) {
    const ns = 'http://www.w3.org/2000/svg';
    const svg = document.createElementNS(ns, 'svg');
    svg.classList.add('map-icon');
    svg.setAttribute('aria-hidden', 'true');
    const use = document.createElementNS(ns, 'use');
    use.setAttribute('href', '/statics/map-icons.svg#' + name);
    svg.append(use);
    return svg;
}

function mapButton(label, icon, action) {
    const button = document.createElement('button');
    button.type = 'button';
    button.title = label;
    button.setAttribute('aria-label', label);
    button.append(mapIcon(icon));
    button.addEventListener('click', action);
    return button;
}

function popupField(parent, label, value) {
    const row = L.DomUtil.create('div', 'popup-info-row', parent);
    L.DomUtil.create('span', 'popup-label', row).textContent = label;
    const content = L.DomUtil.create('span', 'popup-value', row);
    content.textContent = value;
    return row;
}

function bindNotamPopup(layer, data) {
    layer.isNotam = true;
    if (map.hasLayer(layer)) map.fire('notamready');
    let popup;
    let pinned = false;
    function dismiss() {
        if (!pinned && popup) popup.remove();
    }
    layer.on('remove', () => popup?.remove());
    layer.on('click', event => {
        if (popup) {
            popup.setLatLng(event.latlng).bringToFront();
            return;
        }
        pinned = false;
        const raw = data.raw || '';
        const noun = data.marine ? '海警' : '航警';
        const root = L.DomUtil.create('section', 'notam-popup');
        const header = L.DomUtil.create('div', 'notam-popup-header', root);
        L.DomUtil.create('h4', '', header).textContent = data.title;
        const copy = mapButton('复制原始' + noun, 'copy', () => handleCopy(raw));
        copy.classList.add('popup-icon-button');
        copy.disabled = !raw;
        const pin = mapButton('固定弹窗', 'bookmark', () => {
            pinned = !pinned;
            pin.setAttribute('aria-pressed', String(pinned));
            pin.title = pinned ? '取消固定' : '固定弹窗';
            pin.setAttribute('aria-label', pin.title);
        });
        pin.classList.add('popup-icon-button');
        pin.setAttribute('aria-pressed', 'false');
        const close = mapButton('关闭弹窗', 'x', () => popup.remove());
        close.classList.add('popup-icon-button', 'popup-close-button');
        header.append(copy, pin, close);
        const summary = L.DomUtil.create('div', 'notam-popup-body', root);
        if (data.time) {
            const times = data.time.split(';').map(s => s.trim()).filter(Boolean).map(convertTime);
            const row = popupField(summary, '持续时间', times[0] || '时间未知');
            if (times.length > 1) {
                const more = L.DomUtil.create('details', 'notam-alternates', row);
                L.DomUtil.create('summary', '', more).textContent = `备用窗口 (${times.length - 1})`;
                times.slice(1).forEach(t => { L.DomUtil.create('div', '', more).textContent = t; });
                more.addEventListener('toggle', () => popup?.update());
            }
        }
        const fields = L.DomUtil.create('div', 'notam-fields', summary);
        popupField(fields, noun + '编号', data.code || '未知');
        if (!data.marine) {
            const fir = raw.match(/\bQ\s*\)\s*([A-Z]{4})\s*\//i)?.[1]?.toUpperCase();
            popupField(fields, '飞航情报区', data.fir || fir || '未知');
        }
        const original = L.DomUtil.create('pre', 'notam-original', root);
        original.textContent = raw.replace(/\r+\n|\r/g, '\n');
        original.hidden = true;
        original.tabIndex = 0;
        L.DomEvent.disableScrollPropagation(root);
        const footer = L.DomUtil.create('div', 'notam-popup-buttons', root);
        const coords = L.DomUtil.create('button', 'copy copy-coord', footer);
        coords.textContent = '复制坐标';
        coords.onclick = () => handleCopy(data.coordinates);
        const toggle = L.DomUtil.create('button', 'copy copy-raw', footer);
        toggle.textContent = '查看原始' + noun;
        toggle.disabled = !raw;
        toggle.onclick = () => {
            const showRaw = original.hidden;
            summary.hidden = coords.hidden = showRaw;
            original.hidden = !showRaw;
            toggle.textContent = showRaw ? '返回' : '查看原始' + noun;
            popup.update();
        };
        popup = L.popup({className: 'notam-info-popup', closeButton: false, closeOnClick: false,
            autoClose: false, maxWidth: 300, autoPanPadding: [12, 16]})
            .setLatLng(event.latlng).setContent(root);
        map.on('preclick', dismiss);
        popup.on('remove', () => {
            map.off('preclick', dismiss);
            popup = null;
        }).addTo(map);
    });
}
