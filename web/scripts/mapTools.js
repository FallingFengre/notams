// All readouts share the map's coordinates; only the ruler consumes map clicks.
(function installMapTools() {
    const container = map.getContainer();
    const control = L.control({position: 'topleft'});
    const panel = L.DomUtil.create('div', 'map-tools');
    control.onAdd = () => panel;
    control.addTo(map);
    L.DomEvent.disableClickPropagation(panel);
    L.DomEvent.disableScrollPropagation(panel);
    const toolbar = L.DomUtil.create('div', 'map-tools-bar', panel);
    const coords = L.DomUtil.create('output', 'map-coordinate-tooltip', container);
    const ruler = L.DomUtil.create('div', 'map-tool-readout measure-readout', panel);
    coords.hidden = ruler.hidden = true;
    const distance = L.DomUtil.create('ol', 'measure-segments', ruler);
    const actions = L.DomUtil.create('div', 'measure-actions', ruler);
    const colors = ['#315b78', '#6d586f', '#39716a'];
    // A route is a sequence of node references. Snapping to a measured node
    // shares the junction, so moving it updates every incident segment.
    const routes = [];
    let picking = false;
    let pointDrag = null;
    let activeRoute = null;
    let editing = null;
    let draft = null;
    let incident = [];
    let segmentCount = 0;
    const status = L.DomUtil.create('div', 'measure-status', ruler);
    status.setAttribute('role', 'status');
    ruler.insertBefore(status, distance);
    const drawings = L.layerGroup();
    const measurePane = map.createPane('measurement');
    measurePane.style.zIndex = 620;
    measurePane.style.pointerEvents = 'none';
    const measureLabelPane = map.createPane('measureLabels');
    measureLabelPane.style.zIndex = 650;
    measureLabelPane.style.pointerEvents = 'none';
    const passive = {pane: 'measurement', interactive: false, keyboard: false};
    let snapHint = null;
    let previewLayers = null;
    let previewFrame = 0;
    let labelFrame = 0;
    let pendingPointer = null;
    let coordsOn = false;
    let candidates = null;
    let lastPointer = null;
    let grid = null;
    function toggle(label, icon, change) {
        const button = mapButton(label, icon, () => {
            const on = button.getAttribute('aria-pressed') === 'false';
            button.setAttribute('aria-pressed', String(on));
            change(on);
        });
        button.setAttribute('aria-pressed', 'false');
        toolbar.append(button);
        return button;
    }
    toggle('显示经纬度', 'crosshair', on => {
        coordsOn = on;
        coords.hidden = true;
    });
    toggle('测距', 'ruler', on => {
        ruler.hidden = !on;
        releasePointDrag();
        activeRoute = editing = draft = null;
        picking = on && routes.length === 0;
        if (on) {
            drawings.addTo(map);
            previewLayers = L.layerGroup().addTo(map);
            renderMeasurement();
        } else {
            clearTracking();
            previewLayers.remove();
            previewLayers = null;
            drawings.remove();
            container.classList.remove('measure-picking', 'measure-editable', 'measure-dragging');
        }
    });
    toggle('显示经纬网', 'grid-3x3', on => {
        if (on) grid = addGraticule();
        else grid.remove();
    });
    const undo = mapButton('撤销上一点', 'undo-2', () => {
        if (editing) { finishPicking(); return; }
        const route = routes[routes.length - 1];
        route.pop();
        if (!route.length) { routes.pop(); activeRoute = null; }
        renderMeasurement();
    });
    const clear = mapButton('清除测距', 'trash-2', () => { routes.length = 0; finishPicking(); });
    const resume = L.DomUtil.create('button', 'measure-resume', actions);
    resume.type = 'button';
    resume.textContent = '继续测量';
    resume.onclick = () => { picking = true; renderMeasurement(); };
    actions.append(undo, clear);

    function deleteSegment(route, endIndex) {
        const parts = [route.slice(0, endIndex), route.slice(endIndex)].filter(part => part.length >= 2);
        routes.splice(routes.indexOf(route), 1, ...parts);
        if (route === activeRoute) {
            activeRoute = parts.find(part => part[part.length - 1] === route[route.length - 1]) || null;
            if (!activeRoute) picking = false;
        }
        if (editing) finishPicking();
        else renderMeasurement();
    }

    function updateCoords(p, e, touch) {
        if (!coordsOn) return;
        const {lat, lng} = p.wrap();
        coords.textContent = Math.abs(lat).toFixed(5) + '°' + (lat < 0 ? 'S' : 'N') + '  ' +
            Math.abs(lng).toFixed(5) + '°' + (lng < 0 ? 'W' : 'E');
        coords.hidden = false;
        coords.classList.toggle('touch-coordinates', !!touch);
        if (touch) {
            coords.style.left = coords.style.top = '';
            return;
        }
        const at = map.mouseEventToContainerPoint(e), size = map.getSize();
        const x = at.x + 16 + coords.offsetWidth > size.x ? at.x - coords.offsetWidth - 12 : at.x + 16;
        const y = at.y + 16 + coords.offsetHeight > size.y ? at.y - coords.offsetHeight - 12 : at.y + 16;
        coords.style.left = Math.max(3, x) + 'px';
        coords.style.top = Math.max(3, y) + 'px';
    }
    function clearHint() {
        if (snapHint) snapHint.remove();
        snapHint = null;
    }
    function getCandidates() {
        if (candidates) return candidates;
        candidates = [];
        map.eachLayer(layer => {
            if (!layer.isNotam) return;
            candidates.push(layer instanceof L.Circle ? layer.getLatLng() : layer.getCenter());
            for (const v of layer.snapVertices || []) candidates.push(L.latLng(v));
        });
        return candidates;
    }
    function nearest(p, radius) {
        const cursor = map.latLngToContainerPoint(p);
        let best = null;
        function consider(value, node = null) {
            const wrapped = L.latLng(value.lat, longitudeNear(value.lng, p.lng));
            const d = cursor.distanceTo(map.latLngToContainerPoint(wrapped));
            if (d <= radius && (!best || d < best.d)) best = {value: wrapped, node, d};
        }
        // Prefer measured nodes on an exact tie, especially the current endpoint.
        const tail = activeRoute?.[activeRoute.length - 1];
        if (tail) consider(tail.value, tail);
        for (const route of routes) for (const node of route) {
            if (node !== editing && node !== tail) consider(node.value, node);
        }
        // In idle mode a click near an existing point picks it up for editing.
        if (!picking && !editing) return best;
        for (const target of getCandidates()) consider(target);
        for (const site of [...launchSiteMarkers, ...landingZoneMarkers]) {
            if (map.hasLayer(site)) consider(site.getLatLng());
        }
        if (hainanMergedMarker && map.hasLayer(hainanMergedMarker)) {
            for (const site of hainanSeparateMarkers) consider(site.getLatLng());
        }
        return best;
    }
    function markerIcon(className, size) {
        return L.divIcon({className, iconSize: [size, size], iconAnchor: [size / 2, size / 2]});
    }
    const targetIcon = markerIcon('measure-target', 18);
    function showHint(target) {
        if (!target) return clearHint();
        if (snapHint) snapHint.setLatLng(target);
        else snapHint = L.marker(target, {...passive, icon: targetIcon}).addTo(map);
    }
    // Try the opposite side of a short segment before moving the label farther away.
    function layoutLabels() {
        labelFrame = 0;
        const viewport = container.getBoundingClientRect();
        const placed = [];
        for (const label of measureLabelPane.querySelectorAll('.measure-label span')) {
            const anchor = label.parentElement.getBoundingClientRect();
            if (anchor.x < viewport.left || anchor.x > viewport.right ||
                anchor.y < viewport.top || anchor.y > viewport.bottom) continue;
            const w = label.offsetWidth, h = label.offsetHeight;
            const left = Math.max(viewport.left + 2, Math.min(anchor.x - w / 2, viewport.right - w - 2));
            for (let slot = 0; slot <= placed.length * 2 + 1; slot++) {
                const offset = 5 + Math.floor(slot / 2) * (h + 3);
                const top = slot % 2 ? anchor.y + offset : anchor.y - offset - h;
                if (top < viewport.top || top + h > viewport.bottom) continue;
                if (placed.some(r => left < r.right + 2 && left + w > r.left - 2 &&
                    top < r.bottom + 2 && top + h > r.top - 2)) continue;
                label.style.transform = 'translate(' + (left - anchor.x) + 'px,' + (top - anchor.y) + 'px)';
                placed.push({left, right: left + w, top, bottom: top + h});
                break;
            }
        }
    }
    function queueLabelLayout() {
        if (!labelFrame && !ruler.hidden) labelFrame = requestAnimationFrame(layoutLabels);
    }
    map.on('moveend resize', queueLabelLayout);
    function addSegment(start, end, index, group, preview = false) {
        const {meters, parts, anchor} = measureGeodesic(start, end);
        const color = colors[index % colors.length];
        const label = (index + 1) + ' · ' + (meters / 1000).toFixed(2) + ' km';
        const options = {...passive, color, weight: preview ? 2 : 2.8, opacity: .95,
            dashArray: preview ? '6 5' : null, smoothFactor: .5,
            className: preview ? 'measure-preview-line' : 'measure-segment-line'};
        if (parts.length) {
            const line = L.polyline(parts, options);
            repeatWorldLayer(line, line.getBounds(), (offset, style) => L.polyline(
                parts.map(run => run.map(p => [p.lat, p.lng + offset])), style)).addTo(group);
        }
        if (anchor) {
            // Label sits just above the geodesic midpoint, with no hit target.
            const icon = L.divIcon({className: 'measure-label' + (preview ? ' preview' : ''),
                html: '<span style="--segment-color:' + color + '">' + label + '</span>',
                iconSize: [0, 0], iconAnchor: [0, 0]});
            worldMarker(anchor, {...passive, pane: 'measureLabels', icon}).addTo(group);
            queueLabelLayout();
        }
        return label;
    }
    function clearTracking() {
        cancelAnimationFrame(previewFrame);
        previewFrame = 0;
        pendingPointer = null;
        clearHint();
        previewLayers?.clearLayers();
    }
    function finishPicking() {
        releasePointDrag();
        picking = false;
        activeRoute = editing = draft = null;
        renderMeasurement();
    }
    function drawEdit(value) {
        draft = value;
        previewLayers.clearLayers();
        worldMarker(value, {...passive, icon: markerIcon('measure-point editing', 10)}).addTo(previewLayers);
        for (const {a, b, index, length} of incident) {
            length.textContent = addSegment(a === editing ? value : a.value, b === editing ? value : b.value,
                index, previewLayers, true);
        }
    }
    function renderMeasurement() {
        clearTracking();
        drawings.clearLayers();
        distance.replaceChildren();
        incident = [];
        segmentCount = 0;
        const nodes = new Set();
        for (const route of routes) {
            route.forEach((b, i) => {
                nodes.add(b);
                if (!i) return;
                const a = route[i - 1];
                const index = segmentCount++;
                const row = L.DomUtil.create('li', 'measure-segment-row', distance);
                row.style.setProperty('--segment-color', colors[index % colors.length]);
                const length = L.DomUtil.create('span', '', row);
                if (editing === a || editing === b) incident.push({a, b, index, length});
                else length.textContent = addSegment(a.value, b.value, index, drawings);
                row.append(mapButton('删除第 ' + (index + 1) + ' 段', 'x', () => deleteSegment(route, i)));
            });
        }
        for (const node of nodes) {
            if (node !== editing) worldMarker(node.value, {...passive, icon: markerIcon('measure-point', 8)}).addTo(drawings);
        }
        if (editing) drawEdit(draft || editing.value);
        const touch = window.matchMedia('(pointer: coarse)').matches;
        if (editing) status.textContent = lastPointer.touch ? '松开确定位置' : '松开确定，Esc 取消';
        else if (!picking) status.textContent = routes.length ? '拖动测点调整位置' : '测量已暂停';
        else if (activeRoute) status.textContent = touch ? '再点末点结束' : '末点、右键或 Esc 结束';
        else status.textContent = '选择起点';
        resume.hidden = picking || !!editing;
        container.classList.toggle('measure-picking', picking);
        container.classList.toggle('measure-dragging', !!pointDrag);
        container.classList.remove('measure-editable');
        distance.scrollTop = distance.scrollHeight;
        undo.disabled = clear.disabled = !routes.length;
    }
    function invalidateCandidates() {
        candidates = null;
        clearTracking();
        if (editing) drawEdit(draft);
    }
    map.on('layeradd layerremove', e => { if (e.layer.isNotam) invalidateCandidates(); });
    map.on('notamready', invalidateCandidates);
    map.on('zoomend', () => { invalidateCandidates(); if (!ruler.hidden) renderMeasurement(); });
    function leaveMap() {
        if (!coords.classList.contains('touch-coordinates')) coords.hidden = true;
        clearTracking();
        container.classList.remove('measure-editable');
        if (editing) drawEdit(draft);
    }
    map.on('movestart', leaveMap);
    const outsideMap = e => e.target.closest('.leaflet-control, .leaflet-popup');
    container.addEventListener('pointermove', e => {
        if (outsideMap(e) || e.buttons || e.pointerType === 'touch') return leaveMap();
        const p = map.mouseEventToLatLng(e);
        updateCoords(p, e, false);
        if (ruler.hidden) return;
        pendingPointer = p;
        if (previewFrame) return;
        previewFrame = requestAnimationFrame(() => {
            previewFrame = 0;
            const target = nearest(pendingPointer, 15);
            const end = target?.value || pendingPointer;
            showHint(target?.value);
            container.classList.toggle('measure-editable', !!target?.node && !picking && !editing);
            previewLayers.clearLayers();
            if (activeRoute) {
                const tail = activeRoute[activeRoute.length - 1];
                if (target?.node !== tail) addSegment(tail.value, end, segmentCount, previewLayers, true);
            }
        });
    });
    container.addEventListener('pointerleave', leaveMap);
    // Leaflet filters dragged clicks internally. Capture before its layer handlers
    // so tapping a polygon in ruler mode commits exactly one measurement point.
    function releasePointDrag() {
        if (!pointDrag) return;
        const {id, handlers} = pointDrag;
        pointDrag = null;
        if (container.hasPointerCapture(id)) container.releasePointerCapture(id);
        handlers.forEach(handler => handler.enable());
    }
    function commitEdit(target, value) {
        if (target?.node) {
            for (const route of routes) route.forEach((node, i) => {
                if (node === editing) route[i] = target.node;
            });
        } else editing.value = value;
        finishPicking();
    }
    container.addEventListener('pointerdown', e => {
        if (pointDrag) { e.stopImmediatePropagation(); return; }
        if (!e.isPrimary) { if (lastPointer) lastPointer.dragged = true; return; }
        lastPointer = {id: e.pointerId, x: e.clientX, y: e.clientY, touch: e.pointerType === 'touch', dragged: false, handled: false};
        if (e.button !== 0 || ruler.hidden || picking || editing || outsideMap(e)) return;
        const target = nearest(map.mouseEventToLatLng(e), lastPointer.touch ? 22 : 15);
        if (!target?.node) return;
        e.preventDefault();
        e.stopImmediatePropagation();
        lastPointer.dragged = true; // Ignore the compatibility click after releasing the point.
        const handlers = [map.dragging, map.touchZoom, map.tapHold].filter(h => h?.enabled());
        pointDrag = {id: e.pointerId, handlers, moved: false};
        lastPointer.handled = true;
        handlers.forEach(handler => handler.disable());
        container.setPointerCapture(e.pointerId);
        editing = target.node;
        draft = target.value;
        renderMeasurement();
    }, true);
    container.addEventListener('pointermove', e => {
        if (pointDrag?.id === e.pointerId) {
            e.preventDefault();
            e.stopImmediatePropagation();
            if (Math.hypot(e.clientX - lastPointer.x, e.clientY - lastPointer.y) < 3 && !pointDrag.moved) return;
            pointDrag.moved = true;
            const p = map.mouseEventToLatLng(e);
            const target = nearest(p, lastPointer.touch ? 26 : 15);
            updateCoords(p, e, lastPointer.touch);
            drawEdit(target?.value || p);
            showHint(target?.value);
            return;
        }
        if (lastPointer && e.buttons && Math.hypot(e.clientX - lastPointer.x, e.clientY - lastPointer.y) > 6) lastPointer.dragged = true;
    }, true);
    container.addEventListener('pointerup', e => {
        if (pointDrag?.id !== e.pointerId) {
            // A browser can suppress the next compatibility click after a drag.
            // Commit a stationary touch on release; let Leaflet finish its gesture.
            if (picking && !ruler.hidden && e.pointerType === 'touch' && lastPointer?.id === e.pointerId &&
                !lastPointer.dragged && !outsideMap(e) && map.dragging.enabled() &&
                Math.hypot(e.clientX - lastPointer.x, e.clientY - lastPointer.y) <= 6) {
                const p = map.mouseEventToLatLng(e);
                updateCoords(p, e, true);
                selectPoint(p, nearest(p, 26));
                lastPointer.handled = true;
            }
            return;
        }
        e.preventDefault();
        e.stopImmediatePropagation();
        if (!pointDrag.moved) { finishPicking(); return; }
        const p = map.mouseEventToLatLng(e);
        const target = nearest(p, lastPointer.touch ? 26 : 15);
        commitEdit(target, target?.value || p);
    }, true);
    function cancelPointDrag(e) {
        if (pointDrag?.id === e.pointerId) finishPicking();
    }
    container.addEventListener('lostpointercapture', cancelPointDrag);
    container.addEventListener('pointercancel', e => {
        if (lastPointer) lastPointer.dragged = true;
        cancelPointDrag(e);
    }, true);
    container.addEventListener('click', e => {
        if (!outsideMap(e) && lastPointer?.handled) {
            e.preventDefault();
            e.stopImmediatePropagation();
            return;
        }
        if (outsideMap(e) || !e.detail || lastPointer?.dragged || !map.dragging.enabled()) return;
        const p = map.mouseEventToLatLng(e);
        updateCoords(p, e, lastPointer?.touch);
        if (ruler.hidden || !picking) return;
        const target = nearest(p, lastPointer?.touch ? 26 : 15);
        e.stopImmediatePropagation();
        e.preventDefault();
        selectPoint(p, target);
    }, true);
    function selectPoint(p, target) {
        const value = target?.value || p;
        if (activeRoute && target?.node === activeRoute[activeRoute.length - 1]) {
            finishPicking();
        } else {
            if (!activeRoute) { activeRoute = []; routes.push(activeRoute); }
            activeRoute.push(target?.node || {value});
            renderMeasurement();
            showHint(target?.value);
        }
    }
    document.addEventListener('keydown', e => {
        if (e.key !== 'Escape' || ruler.hidden || (!picking && !editing)) return;
        if (e.target.closest?.('input, textarea, select, [contenteditable="true"]')) return;
        e.preventDefault();
        e.stopPropagation();
        finishPicking();
    }, true);
    container.addEventListener('contextmenu', e => {
        if (pointDrag) { e.preventDefault(); return; }
        if (ruler.hidden || outsideMap(e) || (!activeRoute && !editing)) return;
        e.preventDefault();
        e.stopImmediatePropagation();
        finishPicking();
    }, true);
    container.addEventListener('dblclick', e => {
        if (!ruler.hidden && !outsideMap(e)) {
            e.stopImmediatePropagation();
            e.preventDefault();
        }
    }, true);
})();

// One passive canvas per overlay; coalesce drag, resize and data events in one frame.
function viewportCanvas(name, zIndex, paint) {
    const pane = map.getPane(name) || map.createPane(name);
    pane.style.zIndex = zIndex;
    pane.style.pointerEvents = 'none';
    const canvas = L.DomUtil.create('canvas', 'leaflet-zoom-hide', pane);
    let frame;
    function draw() {
        frame = null;
        const {x: w, y: h} = map.getSize();
        if (!w || !h) return;
        const scale = window.devicePixelRatio || 1;
        const width = Math.round(w * scale), height = Math.round(h * scale);
        if (canvas.width !== width || canvas.height !== height) {
            canvas.width = width;
            canvas.height = height;
            canvas.style.width = w + 'px';
            canvas.style.height = h + 'px';
        }
        L.DomUtil.setPosition(canvas, map.containerPointToLayerPoint([0, 0]));
        const ctx = canvas.getContext('2d');
        ctx.setTransform(scale, 0, 0, scale, 0, 0);
        ctx.clearRect(0, 0, w, h);
        paint(ctx, w, h);
    }
    function refresh() { if (frame == null) frame = requestAnimationFrame(draw); }
    map.on('move zoomend resize', refresh);
    draw();
    return {refresh, remove() {
        cancelAnimationFrame(frame);
        map.off('move zoomend resize', refresh);
        canvas.remove();
    }};
}

function addGraticule() {
    return viewportCanvas('graticule', 330, (ctx, w, h) => {
        const bounds = map.getBounds();
        const stepFor = span => {
            const base = 10 ** Math.floor(Math.log10(Math.max(span, 0.000001)));
            return [1, 2, 5, 10].find(n => n * base >= span) * base;
        };
        const line = (x, y, x2, y2, label, tx, ty) => {
            ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(x2, y2);
            ctx.strokeStyle = 'rgba(34,61,82,.5)'; ctx.lineWidth = 1; ctx.stroke();
            ctx.strokeStyle = '#fff'; ctx.lineWidth = 3; ctx.strokeText(label, tx, ty);
            ctx.fillStyle = '#233d50'; ctx.fillText(label, tx, ty);
        };
        ctx.font = '12px sans-serif'; ctx.lineJoin = 'round';
        const latStep = stepFor((bounds.getNorth() - bounds.getSouth()) * 95 / h);
        const lngStep = stepFor((bounds.getEast() - bounds.getWest()) * 120 / w);
        for (let i = Math.ceil(bounds.getWest() / lngStep); i <= Math.floor(bounds.getEast() / lngStep); i++) {
            const p = L.latLng(0, i * lngStep);
            const x = map.latLngToContainerPoint(p).x;
            const lng = +p.wrap().lng.toFixed(6);
            line(x, 0, x, h, `${Math.abs(lng)}°${lng < 0 ? 'W' : 'E'}`, x + 4, h - 30);
        }
        for (let i = Math.ceil(bounds.getSouth() / latStep); i <= Math.floor(bounds.getNorth() / latStep); i++) {
            const lat = +(i * latStep).toFixed(6);
            if (Math.abs(lat) > 85) continue;
            const y = map.latLngToContainerPoint([lat, 0]).y;
            line(0, y, w, y, `${Math.abs(lat)}°${lat < 0 ? 'S' : 'N'}`, 5, y - 4);
        }
    });
}
