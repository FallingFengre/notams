// Sample the same WGS84 inverse line used for the reported distance. Longitude
// unrolling keeps a date-line crossing in one continuous Leaflet world.
function measureGeodesic(start, end) {
    const G = geodesic.Geodesic;
    const line = G.WGS84.InverseLine(start.lat, start.lng, end.lat, end.lng);
    const meters = line.s13;
    const position = distance => {
        const p = line.Position(distance, G.STANDARD | G.LONG_UNROLL);
        return L.latLng(p.lat2, p.lon2);
    };
    const mid = position(meters / 2);
    const points = [start];
    // Subdivide long spans even if their midpoint falls on the projected chord
    // (an equator crossing may have an inflection). Refine curved spans by pixel error.
    function sample(a, b, aMeters, bMeters, depth) {
        const half = (aMeters + bMeters) / 2;
        const m = position(half);
        const error = L.LineUtil.pointToSegmentDistance(map.project(m), map.project(a), map.project(b));
        if (depth < 13 && (bMeters - aMeters > 250000 || error > 0.65)) {
            sample(a, m, aMeters, half, depth + 1);
            sample(m, b, half, bMeters, depth + 1);
        } else points.push(b);
    }
    sample(start, mid, 0, meters / 2, 0);
    sample(mid, position(meters), meters / 2, meters, 0);
    // Web Mercator omits the polar caps. A path through a pole must leave
    // and re-enter the map instead of acquiring a horizontal edge at its top.
    const limit = L.Projection.SphericalMercator.MAX_LATITUDE;
    const parts = [];
    let part = [];
    for (let i = 0; i < points.length; i++) {
        const p = points[i], prev = points[i - 1];
        const inside = Math.abs(p.lat) <= limit;
        if (prev && inside !== (Math.abs(prev.lat) <= limit)) {
            const lat = Math.sign(inside ? prev.lat : p.lat) * limit;
            const t = (lat - prev.lat) / (p.lat - prev.lat);
            part.push(L.latLng(lat, prev.lng + t * (p.lng - prev.lng)));
            if (!inside) { parts.push(part); part = []; }
        }
        if (inside) part.push(p);
    }
    if (part.length) parts.push(part);
    const longest = parts.reduce((best, run) => run.length > best.length ? run : best, []);
    const anchor = Math.abs(mid.lat) <= limit ? mid : longest[Math.floor(longest.length / 2)];
    return {meters, parts, anchor};
}
