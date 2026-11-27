// The sidebar retains the original layer. Additional drawings only exist in
// longitude bands intersecting the viewport, including on multi-world screens.
function longitudeNear(lng, reference) {
    return lng + 360 * Math.round((reference - lng) / 360);
}

function continuousPoints(points) {
    let previous = L.latLng(points[0]).lng;
    return points.map(value => {
        const p = L.latLng(value);
        previous = longitudeNear(p.lng, previous);
        return L.latLng(p.lat, previous);
    });
}

function repeatWorldLayer(owner, bounds, makeCopy) {
    const copies = new Map();
    function update() {
        const view = map.getBounds().pad(0.08);
        const west = Math.ceil((view.getWest() - bounds.getEast()) / 360);
        const east = Math.floor((view.getEast() - bounds.getWest()) / 360);
        for (const [world, copy] of copies) {
            if (world < west || world > east) {
                copy.remove();
                copies.delete(world);
            }
        }
        for (let world = west; world <= east; world++) {
            if (!world || copies.has(world)) continue;
            const copy = makeCopy(360 * world, owner.options);
            copy.on('click', event => {
                const popup = owner.getPopup();
                if (popup) {
                    // Site markers bind their content after being added to the map.
                    if (!copy.getPopup()) {
                        copy.bindPopup(popup.getContent(), popup.options);
                        copy.openPopup();
                    }
                } else {
                    owner.fire('click', {latlng: event.latlng, originalEvent: event.originalEvent});
                }
            });
            copies.set(world, copy);
            copy.addTo(map);
        }
    }
    owner.on('add', () => {
        update();
        map.on('move zoomend resize', update);
    });
    owner.on('remove', () => {
        map.off('move zoomend resize', update);
        copies.forEach(copy => copy.remove());
        copies.clear();
    });
    for (const method of ['setStyle', 'bringToFront']) {
        if (!owner[method]) continue;
        const original = owner[method];
        owner[method] = function (...args) {
            original.apply(this, args);
            copies.forEach(copy => copy[method](...args));
            return this;
        };
    }
    return owner;
}

function worldMarker(value, options) {
    const p = L.latLng(value);
    const marker = L.marker(p, options);
    return repeatWorldLayer(marker, L.latLngBounds(p, p),
        (offset, style) => L.marker([p.lat, p.lng + offset], style));
}

function worldCircle(value, options) {
    const p = L.latLng(value);
    const circle = L.circle(p, options);
    // Metric bounds become available after Leaflet projects the circle.
    const bounds = L.latLngBounds(p, p);
    circle.on('add', () => bounds.extend(circle.getBounds()));
    return repeatWorldLayer(circle, bounds,
        (offset, style) => L.circle([p.lat, p.lng + offset], style));
}

function worldPolygon(values, options, geometry) {
    const points = continuousPoints(values);
    const polygon = L.polygon(points, options);
    polygon.snapVertices = geometry?.vertices ?? (geometry?.type === 'sector'
        ? [points[0], points[1], points[points.length - 1]]
        : geometry?.type === 'arcPath' ? [] : points);
    return repeatWorldLayer(polygon, polygon.getBounds(), (offset, style) =>
        L.polygon(points.map(p => [p.lat, p.lng + offset]), style));
}
