// 自定义区域选择功能
(function() {
    let selectionBox = null;
    let isSelecting = false;
    let startPoint = null;
    let customBounds = null;
    let customPixelBounds = null; // 保存选择框的像素坐标

    // 初始化
    function init() {
        const rangeSelect = document.getElementById('exportRange');
        const selectBtn = document.getElementById('selectAreaBtn');

        // 监听导出范围变化
        rangeSelect.addEventListener('change', function() {
            if (this.value === 'custom') {
                selectBtn.style.display = 'block';
                if (!customBounds) {
                    selectBtn.textContent = '选择区域';
                    selectBtn.className = 'select-area-btn';
                } else {
                    selectBtn.textContent = '重新选择';
                    selectBtn.className = 'select-area-btn selecting';
                }
            } else {
                selectBtn.style.display = 'none';
                removeSelectionBox();
            }
        });

        // 触发初始检查
        rangeSelect.dispatchEvent(new Event('change'));

        // 选择区域按钮点击事件
        selectBtn.addEventListener('click', function() {
            startSelection();
        });
    }

    // 开始选择
    function startSelection() {
        const mapContainer = document.getElementById('allmap');
        mapContainer.style.cursor = 'crosshair';
        
        // 禁用地图拖动
        map.dragging.disable();
        map.touchZoom.disable();
        map.doubleClickZoom.disable();
        map.scrollWheelZoom.disable();
        map.boxZoom.disable();
        map.keyboard.disable();
        
        // 添加事件监听
        mapContainer.addEventListener('mousedown', onMouseDown);
        mapContainer.addEventListener('touchstart', onTouchStart);
        
        showNotification('请在地图上拖拽选择区域', 'info');
    }

    // 鼠标按下
    function onMouseDown(e) {
        if (isSelecting) return;
        
        isSelecting = true;
        startPoint = {
            x: e.clientX,
            y: e.clientY
        };

        removeSelectionBox();
        createSelectionBox(startPoint.x, startPoint.y);

        const mapContainer = document.getElementById('allmap');
        mapContainer.addEventListener('mousemove', onMouseMove);
        mapContainer.addEventListener('mouseup', onMouseUp);
    }

    // 触摸开始
    function onTouchStart(e) {
        if (isSelecting) return;
        
        const touch = e.touches[0];
        isSelecting = true;
        startPoint = {
            x: touch.clientX,
            y: touch.clientY
        };

        removeSelectionBox();
        createSelectionBox(startPoint.x, startPoint.y);

        const mapContainer = document.getElementById('allmap');
        mapContainer.addEventListener('touchmove', onTouchMove);
        mapContainer.addEventListener('touchend', onTouchEnd);
    }

    // 鼠标移动
    function onMouseMove(e) {
        if (!isSelecting || !selectionBox) return;
        
        updateSelectionBox(e.clientX, e.clientY);
    }

    // 触摸移动
    function onTouchMove(e) {
        if (!isSelecting || !selectionBox) return;
        
        const touch = e.touches[0];
        updateSelectionBox(touch.clientX, touch.clientY);
        e.preventDefault();
    }

    // 鼠标松开
    function onMouseUp(e) {
        if (!isSelecting) return;
        
        finishSelection(e.clientX, e.clientY);
        
        const mapContainer = document.getElementById('allmap');
        mapContainer.removeEventListener('mousemove', onMouseMove);
        mapContainer.removeEventListener('mouseup', onMouseUp);
    }

    // 触摸结束
    function onTouchEnd(e) {
        if (!isSelecting) return;
        
        const touch = e.changedTouches[0];
        finishSelection(touch.clientX, touch.clientY);
        
        const mapContainer = document.getElementById('allmap');
        mapContainer.removeEventListener('touchmove', onTouchMove);
        mapContainer.removeEventListener('touchend', onTouchEnd);
    }

    // 创建选择框
    function createSelectionBox(x, y) {
        selectionBox = document.createElement('div');
        selectionBox.className = 'custom-selection-box';
        selectionBox.style.left = x + 'px';
        selectionBox.style.top = y + 'px';
        selectionBox.style.width = '0px';
        selectionBox.style.height = '0px';
        document.body.appendChild(selectionBox);
    }

    // 更新选择框
    function updateSelectionBox(x, y) {
        const width = Math.abs(x - startPoint.x);
        const height = Math.abs(y - startPoint.y);
        const left = Math.min(x, startPoint.x);
        const top = Math.min(y, startPoint.y);

        selectionBox.style.left = left + 'px';
        selectionBox.style.top = top + 'px';
        selectionBox.style.width = width + 'px';
        selectionBox.style.height = height + 'px';
    }

    // 完成选择
    function finishSelection(x, y) {
        isSelecting = false;
        
        const mapContainer = document.getElementById('allmap');
        mapContainer.style.cursor = '';
        mapContainer.removeEventListener('mousedown', onMouseDown);
        mapContainer.removeEventListener('touchstart', onTouchStart);
        
        // 恢复地图功能
        map.dragging.enable();
        map.touchZoom.enable();
        map.doubleClickZoom.enable();
        map.scrollWheelZoom.enable();
        map.boxZoom.enable();
        map.keyboard.enable();

        // 计算选区的地图坐标
        const width = Math.abs(x - startPoint.x);
        const height = Math.abs(y - startPoint.y);

        if (width < 10 || height < 10) {
            showNotification('选区太小，请重新选择', 'info');
            removeSelectionBox();
            return;
        }

        const left = Math.min(x, startPoint.x);
        const top = Math.min(y, startPoint.y);

        // 获取地图容器的位置
        const rect = mapContainer.getBoundingClientRect();
        
        // 转换为地图容器内的坐标
        const containerLeft = left - rect.left;
        const containerTop = top - rect.top;
        
        // 保存像素坐标（用于后续裁剪）
        customPixelBounds = {
            minX: containerLeft,
            minY: containerTop,
            maxX: containerLeft + width,
            maxY: containerTop + height,
            width: width,
            height: height
        };

        // 转换为Leaflet坐标
        const point1 = map.containerPointToLatLng([containerLeft, containerTop]);
        const point2 = map.containerPointToLatLng([containerLeft + width, containerTop + height]);
        
        customBounds = L.latLngBounds(point1, point2);

        // 移除选择框
        removeSelectionBox();

        // 更新按钮状态
        const selectBtn = document.getElementById('selectAreaBtn');
        selectBtn.textContent = '重新选择';
        selectBtn.className = 'select-area-btn selecting';

        showNotification('区域已选择', 'success');
    }

    // 移除选择框
    function removeSelectionBox() {
        if (selectionBox) {
            selectionBox.remove();
            selectionBox = null;
        }
    }

    // 获取自定义边界
    window.getCustomBounds = function() {
        return customBounds;
    };
    
    // 获取自定义区域的像素坐标（用于裁剪）
    window.getCustomPixelBounds = function() {
        return customPixelBounds;
    };

    // 重置自定义选择
    window.resetCustomSelection = function() {
        customBounds = null;
        customPixelBounds = null;
        removeSelectionBox();
        const selectBtn = document.getElementById('selectAreaBtn');
        if (selectBtn) {
            selectBtn.textContent = '选择区域';
            selectBtn.className = 'select-area-btn';
        }
    };

    // 页面加载完成后初始化
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
