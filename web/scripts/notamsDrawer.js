let expanded = false;
let warningCount = 0;
let manualNotams = []; // 存储手动绘制的航警信息（统一数据结构）
let manualVisibleState = {}; // 存储每个手动航警的显示/隐藏状态

/**
 * 创建统一的航警数据对象
 * @param {Object} params - 航警参数
 * @returns {Object} 标准化的航警对象
 */
function createNotamData(params) {
    return {
        id: params.id || '',                    // 唯一标识符
        CODE: params.CODE || '',                // 航警编号
        COORDINATES: params.COORDINATES || '',  // 坐标字符串
        TIME: params.TIME || '',                // 时间窗口
        PLATID: params.PLATID || '',            // 平台ID
        SOURCE: params.SOURCE || 'MANUAL',      // 来源（MANUAL表示手动绘制）
        RAWMESSAGE: params.RAWMESSAGE || '',    // 原始文本
        ALTITUDE: params.ALTITUDE || '',        // 高度
        ROCKET: params.ROCKET || '',            // 火箭型号
        LAUNCH: params.LAUNCH || '',            // 发射场
        // 前端显示相关
        color: params.color || '#0078ff',       // 显示颜色
        polygon: params.polygon || null         // Leaflet多边形对象
    };
}

// 切换到手动绘制页面
function toggleManualDrawer() {
    const sidebar = document.getElementById('notamSidebar');
    const listPage = document.getElementById('notamListPage');
    const manualPage = document.getElementById('manualDrawPage');
    
    // 根据屏幕宽度设置或清除高度
    if (window.innerWidth <= 768) {
        // 窄屏模式：设置高度
        if (!sidebar.classList.contains('open')) {
            sidebar.style.height = '35vh';
        }
    } else {
        // 宽屏模式：清除高度设置
        sidebar.style.height = '';
    }
    
    if (sidebar.classList.contains('open') && manualPage.style.display === 'block') {
        // 如果手动绘制页面已打开，则关闭侧边栏
        sidebar.classList.remove('open');
    } else {
        // 打开侧边栏并切换到手动绘制页面
        sidebar.classList.add('open');
        listPage.style.display = 'none';
        manualPage.style.display = 'block';
        updateManualList();
        initColorPicker();
    }
}

// 初始化颜色选择器
function initColorPicker() {
    const colorPicker = document.getElementById('manualColorPicker');
    const colorPreview = document.getElementById('manualColorPreview');
    
    if (colorPicker && colorPreview) {
        // 初始化颜色
        colorPreview.style.background = colorPicker.value;
        
        // 监听颜色变化
        colorPicker.addEventListener('input', function() {
            colorPreview.style.background = this.value;
        });
    }
}

// 切换到航警列表页面
function switchToListPage() {
    const listPage = document.getElementById('notamListPage');
    const manualPage = document.getElementById('manualDrawPage');
    
    listPage.style.display = 'block';
    manualPage.style.display = 'none';
}

// 从航警列表页切换到手动绘制页
function switchToManualPage() {
    const listPage = document.getElementById('notamListPage');
    const manualPage = document.getElementById('manualDrawPage');
    
    listPage.style.display = 'none';
    manualPage.style.display = 'block';
    updateManualList();
}

// 旧的toggleDrawer函数保留兼容性
function toggleDrawer() {
    toggleManualDrawer();
}

async function drawWarning() {
    const input = document.getElementById('warningInput');
    const text = input.value.trim();
    if (!text) {
        showNotification('请填写航警正文或坐标', 'error');
        return;
    }

    const button = document.getElementById('btnDrawManual');
    const color = document.getElementById('manualColorPicker')?.value || '#0078ff';
    button.disabled = true;
    try {
        const response = await fetch('/parse_areas', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({text})
        });
        const result = await response.json();
        if (!response.ok) {
            showNotification(result.error || '无法解析航警区域', 'error');
            return;
        }
        const style = {color, fillColor: color, fillOpacity: 0.3, weight: 2};
        const layers = result.areas.map(area => createNotamLayer(area, area.coordinates, style));
        const polygon = L.featureGroup(layers).addTo(map);
        const notamId = `MANUAL-${++warningCount}`;
        layers.forEach((layer, i) => bindNotamPopup(layer, {
            title: '手动航警', code: notamId, raw: text, coordinates: result.areas[i].coordinates
        }));
        manualNotams.push(createNotamData({
            id: notamId,
            CODE: notamId,
            COORDINATES: result.areas.map(area => area.coordinates).join('\n'),
            RAWMESSAGE: text,
            color,
            polygon
        }));
        manualVisibleState[notamId] = true;
        updateManualList();
        if (input.value.trim() === text) input.value = '';
        map.fitBounds(polygon.getBounds());
        showNotification(`已添加手动航警 ${notamId}`, 'success');
    } catch (error) {
        console.error('解析手动航警失败', error);
        showNotification('无法连接本地解析服务', 'error');
    } finally {
        button.disabled = false;
    }
}

// 更新手动航警列表
function updateManualList() {
    const container = document.getElementById('manualListContainer');
    const countSpan = document.getElementById('manualCount');
    
    if (!container) return;
    
    // 更新计数
    if (countSpan) {
        countSpan.textContent = manualNotams.length;
    }
    
    container.innerHTML = '';
    
    if (manualNotams.length === 0) {
        container.innerHTML = '<div style="padding: 20px; text-align: center; color: #7f8c8d;">暂无手动绘制的航警</div>';
        return;
    }
    
    // 添加批量操作按钮 - 样式与自动航警一致
    let html = '<div style="font-weight: bold; padding: 10px 15px; background: #ecf0f1; display: flex; justify-content: space-between; align-items: center;">' +
        '<span>手动绘制 (' + manualNotams.length + ')</span>' +
        '<div style="display: flex; gap: 5px;">' +
        '<button onclick="event.stopPropagation(); showAllManual()" title="全部显示" style="padding: 3px 8px; font-size: 12px; background: #3498db; color: white; border: none; border-radius: 3px; cursor: pointer; transition: all 0.2s;" onmouseenter="this.style.background=\'#2980b9\'; this.style.transform=\'translateY(-1px)\'; this.style.boxShadow=\'0 2px 5px rgba(0,0,0,0.2)\'" onmouseleave="this.style.background=\'#3498db\'; this.style.transform=\'translateY(0)\'; this.style.boxShadow=\'none\'" onmousedown="this.style.transform=\'translateY(0)\'; this.style.boxShadow=\'0 1px 2px rgba(0,0,0,0.2)\'" onmouseup="this.style.transform=\'translateY(-1px)\'; this.style.boxShadow=\'0 2px 5px rgba(0,0,0,0.2)\'">全部显示</button>' +
        '<button onclick="event.stopPropagation(); hideAllManual()" title="全部隐藏" style="padding: 3px 8px; font-size: 12px; background: #3498db; color: white; border: none; border-radius: 3px; cursor: pointer; transition: all 0.2s;" onmouseenter="this.style.background=\'#2980b9\'; this.style.transform=\'translateY(-1px)\'; this.style.boxShadow=\'0 2px 5px rgba(0,0,0,0.2)\'" onmouseleave="this.style.background=\'#3498db\'; this.style.transform=\'translateY(0)\'; this.style.boxShadow=\'none\'" onmousedown="this.style.transform=\'translateY(0)\'; this.style.boxShadow=\'0 1px 2px rgba(0,0,0,0.2)\'" onmouseup="this.style.transform=\'translateY(-1px)\'; this.style.boxShadow=\'0 2px 5px rgba(0,0,0,0.2)\'">全部隐藏</button>' +
        '<button onclick="event.stopPropagation(); removeAllManual()" title="清空全部" style="padding: 3px 8px; font-size: 12px; background: #e74c3c; color: white; border: none; border-radius: 3px; cursor: pointer; transition: all 0.2s;" onmouseenter="this.style.background=\'#c0392b\'; this.style.transform=\'translateY(-1px)\'; this.style.boxShadow=\'0 2px 5px rgba(0,0,0,0.2)\'" onmouseleave="this.style.background=\'#e74c3c\'; this.style.transform=\'translateY(0)\'; this.style.boxShadow=\'none\'" onmousedown="this.style.transform=\'translateY(0)\'; this.style.boxShadow=\'0 1px 2px rgba(0,0,0,0.2)\'" onmouseup="this.style.transform=\'translateY(-1px)\'; this.style.boxShadow=\'0 2px 5px rgba(0,0,0,0.2)\'">清空</button>' +
        '</div>' +
        '</div>';
    
    // 渲染每个手动航警 - 紧凑布局：标题在上，横排按钮在下
    manualNotams.forEach((notam, index) => {
        const visible = manualVisibleState[notam.id] !== false;
        html += `
        <div class="manual-notam-item" style="--group-color:${notam.color}; cursor:pointer; margin-bottom: 8px; padding: 10px; border-radius: 6px; background: #f8f9fa; border-left: 5px solid ${notam.color}; ${visible ? '' : 'opacity:0.5;'}"
            onclick="locateToManualNotam('${notam.id}')"
            onmouseenter="this.style.background='rgba(0,0,0,0.06)'; hoverHighlightManual('${notam.id}');"
            onmouseleave="this.style.background='#f8f9fa'; hoverUnhighlightManual('${notam.id}');">
            <div style="display:flex; align-items:center; gap:10px; margin-bottom: 8px;">
                <div class="color-picker-wrapper" onclick="event.stopPropagation();">
                    <div class="color-preview" style="background:${notam.color}">
                        <input type="color" class="color-picker" value="${notam.color.substring(0, 7)}"
                            onchange="event.stopPropagation(); changeManualColor('${notam.id}', this.value); this.parentElement.style.background=this.value;">
                    </div>
                </div>
                <span style="font-weight: bold; color: #2c3e50;">${notam.id}</span>
            </div>
            <div style="display:flex; gap:8px;">
                <button class="icon-btn" onclick="event.stopPropagation(); copyManualCoords('${notam.id}')" title="复制坐标">
                    <svg width="16" height="16" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M13 12.4316V7.8125C13 6.2592 14.2592 5 15.8125 5H40.1875C41.7408 5 43 6.2592 43 7.8125V32.1875C43 33.7408 41.7408 35 40.1875 35H35.5163" stroke="#333" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/><path d="M32.1875 13H7.8125C6.2592 13 5 14.2592 5 15.8125V40.1875C5 41.7408 6.2592 43 7.8125 43H32.1875C33.7408 43 35 41.7408 35 40.1875V15.8125C35 14.2592 33.7408 13 32.1875 13Z" fill="none" stroke="#333" stroke-width="4" stroke-linejoin="round"/></svg>
                </button>
                <button class="icon-btn" onclick="event.stopPropagation(); toggleManualVisibility('${notam.id}')" title="${visible ? '隐藏' : '显示'}">
                    ${visible ?
                        '<svg width="16" height="16" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M9.85786 18C6.23858 21 4 24 4 24C4 24 12.9543 36 24 36C25.3699 36 26.7076 35.8154 28 35.4921M20.0318 12.5C21.3144 12.1816 22.6414 12 24 12C35.0457 12 44 24 44 24C44 24 41.7614 27 38.1421 30" stroke="#333" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/><path d="M20.3142 20.6211C19.4981 21.5109 19 22.6972 19 23.9998C19 26.7612 21.2386 28.9998 24 28.9998C25.3627 28.9998 26.5981 28.4546 27.5 27.5705" stroke="#333" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/><path d="M42 42L6 6" stroke="#333" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/></svg>' :
                        '<svg width="16" height="16" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M24 36C35.0457 36 44 24 44 24C44 24 35.0457 12 24 12C12.9543 12 4 24 4 24C4 24 12.9543 36 24 36Z" fill="none" stroke="#333" stroke-width="4" stroke-linejoin="round"/><path d="M24 29C26.7614 29 29 26.7614 29 24C29 21.2386 26.7614 19 24 19C21.2386 19 19 21.2386 19 24C19 26.7614 21.2386 29 24 29Z" fill="none" stroke="#333" stroke-width="4" stroke-linejoin="round"/></svg>'
                    }
                </button>
                <button class="icon-btn" onclick="event.stopPropagation(); removeManual('${notam.id}')" title="删除">
                    <svg width="16" height="16" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M9 10V44H39V10H9Z" fill="none" stroke="#333" stroke-width="4" stroke-linejoin="round"/><path d="M20 20V33" stroke="#333" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/><path d="M28 20V33" stroke="#333" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/><path d="M4 10H44" stroke="#333" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/><path d="M16 10L19.289 4H28.7771L32 10H16Z" fill="none" stroke="#333" stroke-width="4" stroke-linejoin="round"/></svg>
                </button>
            </div>
        </div>`;
    });
    
    container.innerHTML = html;
}

// 悬停高亮手动航警
function hoverHighlightManual(notamId) {
    const notam = manualNotams.find(n => n.id === notamId);
    if (notam && notam.polygon && manualVisibleState[notamId]) {
        notam.polygon.setStyle({
            weight: 4,
            opacity: 1,
            fillOpacity: 0.5
        });
    }
}

// 取消悬停高亮
function hoverUnhighlightManual(notamId) {
    const notam = manualNotams.find(n => n.id === notamId);
    if (notam && notam.polygon && manualVisibleState[notamId]) {
        notam.polygon.setStyle({
            weight: 2,
            opacity: 1,
            fillOpacity: 0.3
        });
    }
}

// 定位到手动航警
function locateToManualNotam(notamId) {
    const notam = manualNotams.find(n => n.id === notamId);
    if (notam && notam.polygon) {
        map.fitBounds(notam.polygon.getBounds());
    }
}

// 更改手动航警颜色
function changeManualColor(notamId, newColor) {
    const notam = manualNotams.find(n => n.id === notamId);
    if (notam) {
        notam.color = newColor;
        if (notam.polygon) {
            notam.polygon.setStyle({
                color: newColor,
                fillColor: newColor
            });
        }
        // 立即更新列表显示
        updateManualList();
    }
}

// 切换手动航警显示/隐藏
function toggleManualVisibility(notamId) {
    const notam = manualNotams.find(n => n.id === notamId);
    if (notam && notam.polygon) {
        const newState = !manualVisibleState[notamId];
        manualVisibleState[notamId] = newState;
        
        if (newState) {
            notam.polygon.addTo(map);
        } else {
            map.removeLayer(notam.polygon);
        }
        
        updateManualList();
    }
}

// 复制手动航警坐标
function copyManualCoords(notamId) {
    const notam = manualNotams.find(n => n.id === notamId);
    if (notam) {
        // 使用原始输入文本（如果有），否则回退到格式化坐标
        const coordsStr = notam.RAWMESSAGE || notam.COORDINATES;
        
        if (typeof handleCopy === 'function') {
            handleCopy(coordsStr);
        } else {
            navigator.clipboard.writeText(coordsStr).then(() => {
                showNotification('已复制到剪贴板', 'success');
            }).catch(err => {
                console.error('复制失败:', err);
                showNotification('复制失败', 'error');
            });
        }
    }
}

// 删除单个手动航警
function removeManual(notamId) {
    const index = manualNotams.findIndex(n => n.id === notamId);
    if (index !== -1) {
        const notam = manualNotams[index];
        if (notam.polygon) {
            map.removeLayer(notam.polygon);
        }
        manualNotams.splice(index, 1);
        delete manualVisibleState[notamId];
        updateManualList();
        showNotification('已删除手动航警', 'success');
    }
}

// 全部显示手动航警
function showAllManual() {
    manualNotams.forEach(notam => {
        if (notam.polygon) {
            notam.polygon.addTo(map);
            manualVisibleState[notam.id] = true;
        }
    });
    updateManualList();
    showNotification('已显示全部手动航警', 'success');
}

// 全部隐藏手动航警
function hideAllManual() {
    manualNotams.forEach(notam => {
        if (notam.polygon) {
            map.removeLayer(notam.polygon);
            manualVisibleState[notam.id] = false;
        }
    });
    updateManualList();
    showNotification('已隐藏全部手动航警', 'success');
}

// 清空全部手动航警
function removeAllManual() {
    if (manualNotams.length === 0) return;
    
    if (confirm('确定要清空所有手动绘制的航警吗？')) {
        manualNotams.forEach(notam => {
            if (notam.polygon) {
                map.removeLayer(notam.polygon);
            }
        });
        manualNotams = [];
        manualVisibleState = {};
        warningCount = 0;
        updateManualList();
        showNotification('已清空所有手动航警', 'success');
    }
}

function modeInitial(){
    clearAllPolygons();
    siteInit();
}