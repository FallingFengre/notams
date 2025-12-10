// Enhanced leaflet-image with high-DPI support and SVG path rendering
(function() {
    'use strict';

    function leafletImageEnhanced(map, callback, options) {
        options = options || {};
        var scale = options.scale || window.devicePixelRatio || 1;
        var quality = options.quality || 0.92;

        var dimensions = map.getSize();
        var canvas = document.createElement('canvas');
        canvas.width = dimensions.x * scale;
        canvas.height = dimensions.y * scale;
        var ctx = canvas.getContext('2d');
        ctx.scale(scale, scale);

        var layers = [];
        var completed = 0;
        var total = 0;

        // 收集所有需要绘制的图层
        map.eachLayer(function(layer) {
            if (layer instanceof L.TileLayer) {
                total++;
                layers.push({ type: 'tile', layer: layer });
            } else if (layer instanceof L.Marker) {
                total++;
                layers.push({ type: 'marker', layer: layer });
            } else if (layer instanceof L.Path) {
                total++;
                layers.push({ type: 'path', layer: layer });
            }
        });

        if (total === 0) {
            callback(null, canvas);
            return;
        }

        // 绘制瓦片图层
        function drawTileLayer(layerInfo, done) {
            var layer = layerInfo.layer;
            var tileCanvas = document.createElement('canvas');
            tileCanvas.width = dimensions.x * scale;
            tileCanvas.height = dimensions.y * scale;
            var tileCtx = tileCanvas.getContext('2d');
            tileCtx.scale(scale, scale);

            var bounds = map.getPixelBounds();
            var zoom = map.getZoom();
            var tileSize = layer.options.tileSize || 256;

            var tileBounds = L.bounds(
                bounds.min.divideBy(tileSize)._floor(),
                bounds.max.divideBy(tileSize)._floor()
            );

            var tiles = [];
            for (var j = tileBounds.min.y; j <= tileBounds.max.y; j++) {
                for (var i = tileBounds.min.x; i <= tileBounds.max.x; i++) {
                    tiles.push(new L.Point(i, j));
                }
            }

            var loadedTiles = 0;
            var totalTiles = tiles.length;

            if (totalTiles === 0) {
                done();
                return;
            }

            tiles.forEach(function(tilePoint) {
                var url = layer.getTileUrl(tilePoint);
                var img = new Image();
                img.crossOrigin = 'anonymous';

                var tilePos = tilePoint.scaleBy(new L.Point(tileSize, tileSize)).subtract(bounds.min);

                img.onload = function() {
                    tileCtx.drawImage(img, tilePos.x, tilePos.y, tileSize, tileSize);
                    loadedTiles++;
                    if (loadedTiles === totalTiles) {
                        ctx.save();
                        ctx.setTransform(1, 0, 0, 1, 0, 0); // 重置变换
                        ctx.drawImage(tileCanvas, 0, 0);
                        ctx.restore();
                        done();
                    }
                };

                img.onerror = function() {
                    loadedTiles++;
                    if (loadedTiles === totalTiles) {
                        ctx.save();
                        ctx.setTransform(1, 0, 0, 1, 0, 0);
                        ctx.drawImage(tileCanvas, 0, 0);
                        ctx.restore();
                        done();
                    }
                };

                img.src = url;
            });
        }

        // 绘制SVG路径（多边形、折线等）
        function drawPathLayer(layerInfo, done) {
            var layer = layerInfo.layer;
            
            // 获取路径的坐标点
            var latlngs;
            if (layer instanceof L.Polygon || layer instanceof L.Polyline) {
                latlngs = layer.getLatLngs();
                if (latlngs[0] && Array.isArray(latlngs[0])) {
                    latlngs = latlngs[0]; // 处理多边形的嵌套数组
                }
            } else if (layer instanceof L.Circle || layer instanceof L.CircleMarker) {
                // 圆形需要特殊处理
                var center = map.latLngToContainerPoint(layer.getLatLng());
                var radius = layer instanceof L.Circle ? 
                    map.distance(layer.getLatLng(), map.containerPointToLatLng([center.x + layer.getRadius(), center.y])) :
                    layer.getRadius();
                
                ctx.beginPath();
                ctx.arc(center.x, center.y, radius, 0, Math.PI * 2);
                ctx.fillStyle = layer.options.fillColor || layer.options.color || '#3388ff';
                ctx.globalAlpha = layer.options.fillOpacity || 0.2;
                ctx.fill();
                ctx.globalAlpha = layer.options.opacity || 1;
                ctx.strokeStyle = layer.options.color || '#3388ff';
                ctx.lineWidth = layer.options.weight || 3;
                ctx.stroke();
                ctx.globalAlpha = 1;
                done();
                return;
            } else {
                done();
                return;
            }

            if (!latlngs || latlngs.length === 0) {
                done();
                return;
            }

            // 转换坐标并绘制路径
            ctx.beginPath();
            latlngs.forEach(function(latlng, index) {
                var point = map.latLngToContainerPoint(latlng);
                if (index === 0) {
                    ctx.moveTo(point.x, point.y);
                } else {
                    ctx.lineTo(point.x, point.y);
                }
            });
            ctx.closePath();

            // 应用样式
            if (layer.options.fill !== false) {
                ctx.fillStyle = layer.options.fillColor || layer.options.color || '#3388ff';
                ctx.globalAlpha = layer.options.fillOpacity !== undefined ? layer.options.fillOpacity : 0.2;
                ctx.fill();
            }

            ctx.globalAlpha = layer.options.opacity !== undefined ? layer.options.opacity : 1;
            ctx.strokeStyle = layer.options.color || '#3388ff';
            ctx.lineWidth = layer.options.weight || 3;
            ctx.stroke();
            ctx.globalAlpha = 1;

            done();
        }

        // 绘制标记
        function drawMarkerLayer(layerInfo, done) {
            var marker = layerInfo.layer;
            if (!marker._icon) {
                done();
                return;
            }

            var pixelPoint = map.latLngToContainerPoint(marker.getLatLng());
            var icon = marker.options.icon;
            var size = icon.options.iconSize;
            var anchor = icon.options.iconAnchor || [size[0] / 2, size[1] / 2];

            var x = pixelPoint.x - anchor[0];
            var y = pixelPoint.y - anchor[1];

            var img = new Image();
            img.crossOrigin = 'anonymous';
            
            img.onload = function() {
                ctx.drawImage(img, x, y, size[0], size[1]);
                done();
            };

            img.onerror = function() {
                done();
            };

            img.src = marker._icon.src;
        }

        // 处理每个图层
        function processLayer(index) {
            if (index >= layers.length) {
                callback(null, canvas);
                return;
            }

            var layerInfo = layers[index];
            var doneFn = function() {
                completed++;
                if (options.onProgress) {
                    options.onProgress(Math.round((completed / total) * 100));
                }
                processLayer(index + 1);
            };

            if (layerInfo.type === 'tile') {
                drawTileLayer(layerInfo, doneFn);
            } else if (layerInfo.type === 'path') {
                drawPathLayer(layerInfo, doneFn);
            } else if (layerInfo.type === 'marker') {
                drawMarkerLayer(layerInfo, doneFn);
            } else {
                doneFn();
            }
        }

        processLayer(0);
    }

    // 导出到全局
    if (typeof window !== 'undefined') {
        window.leafletImageEnhanced = leafletImageEnhanced;
    }
    if (typeof module !== 'undefined' && module.exports) {
        module.exports = leafletImageEnhanced;
    }
})();
