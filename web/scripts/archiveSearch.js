// 历史航警检索功能
let archiveDict = null;
let polygonArchive = [];
let archiveGroupColors = {};
let archiveVisibleState = {};
let currentRegionOverlay = null;
let regionOverlayTimer = null; // 保存定时器ID

// ICAO区域边界定义（简化的矩形范围）
const ICAO_REGIONS = {
    'VVTS': { name: 'VVTS', bounds: [[17.443177, 108.705916], [14.486029, 112.001814], [14.486029, 114.001326], [10.518348, 113.979353], [7.000875, 108.002791], [8.828915, 102.531599]], center: [11.937392, 110.429643] },
    'RPHI': { name: 'RPHI', bounds: [[21.031461, 117.538924], [16.750126, 113.979353], [10.475138, 113.979353], [4.070596, 119.955916], [4.070596, 132.48033], [6.913632, 130.019392], [20.949403, 130.019392]], center: [13.052888, 122.64644] },
    'RJJJ': { name: 'RJJJ', bounds: [[20.990493, 121.458344], [23.552227, 124.007173], [29.98189, 124.051118], [29.98189, 125.325532], [42.995264, 146.81479], [27.008554, 154.988618], [21.031517, 154.988618]], center: [25.229942, 130.117143] },
    'KZAK': { name: 'KZAK', bounds: [[21.031517, 154.988618], [21.028268, 154.99019], [3.760284, 179.960982], [3.584864, 133.105424], [7.433451, 129.941362], [21.028268, 130.029252]], center: [13.480612, 138.818315] },
    'VCCF': { name: 'VCCF', bounds: [[6.036942, 78.085893], [-1.861686, 78.085893], [-2.037365, 91.884721], [6.036942, 91.972612], [10.125876, 81.777299]], center: [2.970639, 84.67769] },
    'internal': { name: '内陆及近海', bounds: [[45, 100], [45, 135], [18, 135], [18, 100]], center: [36, 106] }
};

// VVTS[17.443177   108.705916],[14.486029   112.001814],[14.486029  114.001326],[10.518348  113.979353],[7.000875   108.002791],[8.828915   102.531599]
// RPHI[21.031461	117.538924],[16.750126	113.979353],[10.475138	113.979353],[4.070596	119.955916],[4.070596	132.48033],[6.913632	130.019392],[20.949403	130.019392]
// RJJJ[20.990493	121.458344],[23.552227	124.007173],[29.98189	124.051118],[29.98189	125.325532],[42.995264	146.81479],[27.008554	154.988618],[21.031517	154.988618]
// KZAK[21.031517	154.988618],[21.028268	154.99019],[3.760284	-179.960982],[3.584864	133.105424],[7.433451	129.941362]
// VCCF[6.036942	78.085893],[-1.861686	78.085893],[-2.037365	91.884721],[6.036942	91.972612],[10.125876	81.777299]







// 切换历史检索侧边栏
function toggleArchiveSidebar() {
    const sidebar = document.getElementById('archiveSidebar');
    const isOpening = !sidebar.classList.contains('open');
    
    sidebar.classList.toggle('open');
    
    // 如果是打开面板，重置到初始位置
    if (isOpening && window.resetArchivePosition) {
        window.resetArchivePosition();
    }
    
    console.log('历史检索面板状态:', sidebar.classList.contains('open') ? '打开' : '关闭');
}

// 初始化历史检索功能
(function initArchiveSearch() {
    const btnSearch = document.getElementById('btnSearchArchive');
    const btnClear = document.getElementById('btnClearArchive');
    const btnSelectDate = document.getElementById('btnSelectDate');
    const selectedDateText = document.getElementById('selectedDateText');
    const calendarPopup = document.getElementById('calendarPopup');
    const yearSelect = document.getElementById('archiveYear');
    const monthSelect = document.getElementById('archiveMonth');
    const calendarGrid = document.getElementById('calendarGrid');
    const regionSelect = document.getElementById('archiveRegion');
    
    let selectedDay = null;
    let selectedYear = null;
    let selectedMonth = null;

    // 生成年份选项（近20年）
    const currentYear = new Date().getFullYear();
    for (let y = currentYear; y >= currentYear - 20; y--) {
        const option = document.createElement('option');
        option.value = y;
        option.textContent = y + '年';
        yearSelect.appendChild(option);
    }

    // 生成日历网格
    function renderCalendar() {
        const year = parseInt(yearSelect.value);
        const month = parseInt(monthSelect.value);
        
        // 清空日历
        calendarGrid.innerHTML = '';
        
        // 添加星期标题
        const weekdays = ['日', '一', '二', '三', '四', '五', '六'];
        weekdays.forEach(day => {
            const weekdayEl = document.createElement('div');
            weekdayEl.className = 'calendar-weekday';
            weekdayEl.textContent = day;
            calendarGrid.appendChild(weekdayEl);
        });
        
        // 获取月份第一天是星期几（0=星期日）
        const firstDay = new Date(year, month - 1, 1).getDay();
        // 获取这个月有多少天
        const daysInMonth = new Date(year, month, 0).getDate();
        
        // 添加空白格子（月份开始前的日子）
        for (let i = 0; i < firstDay; i++) {
            const emptyEl = document.createElement('div');
            emptyEl.className = 'calendar-day empty';
            calendarGrid.appendChild(emptyEl);
        }
        
        // 获取今天的日期
        const today = new Date();
        const isCurrentMonth = today.getFullYear() === year && (today.getMonth() + 1) === month;
        
        // 添加每一天
        for (let day = 1; day <= daysInMonth; day++) {
            const dayEl = document.createElement('div');
            dayEl.className = 'calendar-day';
            dayEl.textContent = day;
            dayEl.dataset.day = day;
            
            // 标记今天
            if (isCurrentMonth && day === today.getDate()) {
                dayEl.classList.add('today');
            }
            
            // 如果是当前选中的日期
            if (selectedDay === day) {
                dayEl.classList.add('selected');
            }
            
            // 点击事件
            dayEl.addEventListener('click', () => {
                // 移除之前的选中状态
                calendarGrid.querySelectorAll('.calendar-day.selected').forEach(el => {
                    el.classList.remove('selected');
                });
                // 添加新的选中状态
                dayEl.classList.add('selected');
                selectedDay = day;
                selectedYear = parseInt(yearSelect.value);
                selectedMonth = parseInt(monthSelect.value);
                
                // 更新显示文本
                updateDateText();
                
                // 关闭日历
                calendarPopup.classList.remove('show');
                btnSelectDate.classList.remove('open');
            });
            
            calendarGrid.appendChild(dayEl);
        }
    }

    // 更新日期显示文本
    function updateDateText() {
        if (selectedYear && selectedMonth && selectedDay) {
            selectedDateText.textContent = `${selectedYear}年${selectedMonth}月${selectedDay}日`;
        } else {
            selectedDateText.textContent = '选择日期';
        }
    }

    // 日期选择按钮点击事件
    btnSelectDate.addEventListener('click', (e) => {
        e.stopPropagation();
        calendarPopup.classList.toggle('show');
        btnSelectDate.classList.toggle('open');
    });

    // 点击外部关闭日历
    document.addEventListener('click', (e) => {
        if (!calendarPopup.contains(e.target) && e.target !== btnSelectDate) {
            calendarPopup.classList.remove('show');
            btnSelectDate.classList.remove('open');
        }
    });

    // 设置默认日期为昨天
    const yesterday = new Date();
    yesterday.setDate(yesterday.getDate() - 1);
    yearSelect.value = yesterday.getFullYear();
    monthSelect.value = yesterday.getMonth() + 1;
    selectedDay = yesterday.getDate();
    selectedYear = yesterday.getFullYear();
    selectedMonth = yesterday.getMonth() + 1;
    renderCalendar();
    updateDateText();

    // 年份或月份变化时重新渲染日历
    yearSelect.addEventListener('change', () => {
        selectedDay = null; // 重置选中的日期
        renderCalendar();
    });
    monthSelect.addEventListener('change', () => {
        selectedDay = null;
        renderCalendar();
    });

    // 检索按钮
    btnSearch.addEventListener('click', async () => {
        if (!selectedYear || !selectedMonth || !selectedDay) {
            showNotification('请选择日期');
            return;
        }
        
        const year = String(selectedYear);
        const month = String(selectedMonth).padStart(2, '0');
        const day = String(selectedDay).padStart(2, '0');
        const date = `${year}-${month}-${day}`;
        const region = regionSelect.value;

        console.log('点击检索按钮，日期:', date, '区域:', region);

        await searchArchiveNotams(date, region);
    });

    // 清除按钮
    btnClear.addEventListener('click', () => {
        clearArchiveNotams();
        showNotification('已清除历史航警');
    });

    // 区域选择变化时显示区域
    regionSelect.addEventListener('change', () => {
        showRegionOnMap(regionSelect.value);
    });

    // 初始化拖动功能
    initArchiveDraggable();
})();

// 历史检索面板拖动功能
function initArchiveDraggable() {
    const sidebar = document.getElementById('archiveSidebar');
    const header = document.getElementById('archiveSidebarHeader');
    
    let isDragging = false;
    let currentX = 0;
    let currentY = 0;
    let initialX = 0;
    let initialY = 0;
    let xOffset = 0;
    let yOffset = 0;

    // 获取客户端坐标（兼容鼠标和触摸）
    function getClientCoords(e) {
        if (e.touches && e.touches.length > 0) {
            return { x: e.touches[0].clientX, y: e.touches[0].clientY };
        }
        return { x: e.clientX, y: e.clientY };
    }

    // 开始拖动
    function dragStart(e) {
        // 如果点击的是按钮或输入框，不触发拖动
        if (e.target.tagName === 'BUTTON' || e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT') {
            return;
        }

        const coords = getClientCoords(e);
        initialX = coords.x - xOffset;
        initialY = coords.y - yOffset;
        isDragging = true;
        
        header.style.cursor = 'grabbing';
        e.preventDefault();
    }

    // 拖动中
    function drag(e) {
        if (!isDragging) return;
        
        e.preventDefault();
        const coords = getClientCoords(e);
        currentX = coords.x - initialX;
        currentY = coords.y - initialY;
        xOffset = currentX;
        yOffset = currentY;

        // 完全自由拖动，无边界限制
        setTranslate(xOffset, yOffset, sidebar);
    }

    // 结束拖动
    function dragEnd(e) {
        if (!isDragging) return;
        
        initialX = currentX;
        initialY = currentY;
        isDragging = false;
        
        header.style.cursor = 'grab';
    }

    // 设置位置
    function setTranslate(xPos, yPos, el) {
        el.style.transform = `translate(${xPos}px, ${yPos}px)`;
    }

    // 重置到初始位置
    function resetPosition() {
        xOffset = 0;
        yOffset = 0;
        currentX = 0;
        currentY = 0;
        setTranslate(0, 0, sidebar);
    }

    // 将重置函数暴露到全局，供 toggleArchiveSidebar 调用
    window.resetArchivePosition = resetPosition;

    // 鼠标事件
    header.addEventListener('mousedown', dragStart);
    document.addEventListener('mousemove', drag);
    document.addEventListener('mouseup', dragEnd);

    // 触摸事件
    header.addEventListener('touchstart', dragStart, { passive: false });
    document.addEventListener('touchmove', drag, { passive: false });
    document.addEventListener('touchend', dragEnd);

    // 设置标题栏样式
    header.style.cursor = 'grab';
    header.style.userSelect = 'none';
}

// 搜索历史航警
async function searchArchiveNotams(date, region) {
    console.log('开始搜索历史航警...', { date, region });
    
    const btnSearch = document.getElementById('btnSearchArchive');
    const originalText = btnSearch.textContent;

    // 显示加载状态
    btnSearch.innerHTML = '正在检索<span class="btn-spinner"></span>';
    btnSearch.disabled = true;
    btnSearch.style.opacity = '0.8';

    // 开始轮询日志以显示进度
    let lastLogCount = 0;
    let progressInterval = null;
    
    const updateProgress = async () => {
        try {
            const logsResponse = await fetch('/logs');
            if (logsResponse.ok) {
                const logs = await logsResponse.json();
                // 只显示新的进度日志
                const newLogs = logs.slice(lastLogCount);
                const progressLogs = newLogs.filter(log => {
                    if (!log.message || !log.message.includes('[进度]')) return false;
                    // 排除包含完整dict数据的消息（通常包含大量的引号和大括号）
                    const msg = log.message;
                    if (msg.includes('{"CODE"') || msg.includes("{'CODE'")) return false;
                    if ((msg.match(/'/g) || []).length > 10) return false;  // 超过10个引号可能是数据
                    if ((msg.match(/{/g) || []).length > 3) return false;   // 超过3个大括号可能是dict
                    return true;
                });
                
                if (progressLogs.length > 0) {
                    const latestProgress = progressLogs[progressLogs.length - 1].message;
                    // 提取进度信息并显示在按钮上
                    const progressText = latestProgress.replace('[进度]', '').trim();
                    // 限制显示长度
                    const displayText = progressText.length > 30 
                        ? progressText.substring(0, 30) + '...' 
                        : progressText;
                    btnSearch.innerHTML = displayText + '<span class="btn-spinner"></span>';
                }
                lastLogCount = logs.length;
            }
        } catch (e) {
            console.error('获取进度日志失败:', e);
        }
    };

    // 每500ms更新一次进度
    progressInterval = setInterval(updateProgress, 500);

    try {
        console.log('发送请求到 /fetch_archive');
        
        const response = await fetch('/fetch_archive', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ date, region })
        });

        // 停止进度轮询
        if (progressInterval) {
            clearInterval(progressInterval);
            progressInterval = null;
        }

        console.log('收到响应，状态码:', response.status);

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        const data = await response.json();
        console.log('解析响应数据:', data);

        if (data.error) {
            throw new Error(data.error);
        }

        // 清除旧的历史航警
        clearArchiveNotams();

        // 保存数据
        archiveDict = data;

        if (data.NUM === 0) {
            // 显示未找到状态
            btnSearch.innerHTML = '未找到相关航警';
            btnSearch.disabled = false;
            btnSearch.style.opacity = '1';
            btnSearch.style.background = 'linear-gradient(135deg, #95a5a6, #7f8c8d)';
            
            // 3秒后恢复
            setTimeout(() => {
                btnSearch.innerHTML = originalText;
                btnSearch.style.background = '';
            }, 3000);
            
            showNotification('未找到相关航警');
            return;
        }

        // 调试：打印时间数据
        console.log('历史航警数据:', data);

        // 分配颜色
        assignArchiveGroupColors(data.CLASSIFY || {});

        // 绘制历史航警
        drawAllArchiveNotams();

        // 更新航警列表（主列表）
        updateSidebar();

        // 显示成功状态
        btnSearch.innerHTML = `找到 ${data.NUM} 条航警`;
        btnSearch.disabled = false;
        btnSearch.style.opacity = '1';
        btnSearch.style.background = 'linear-gradient(135deg, #27ae60, #229954)';

        // 3秒后恢复
        setTimeout(() => {
            btnSearch.innerHTML = originalText;
            btnSearch.style.background = '';
        }, 3000);

        showNotification(`检索成功：找到 ${data.NUM} 条航警`);

    } catch (error) {
        // 停止进度轮询
        if (progressInterval) {
            clearInterval(progressInterval);
            progressInterval = null;
        }
        
        console.error('历史航警检索失败:', error);
        
        // 显示失败状态
        btnSearch.innerHTML = '检索失败，重新检索';
        btnSearch.disabled = false;
        btnSearch.style.opacity = '1';
        btnSearch.style.background = 'linear-gradient(135deg, #e74c3c, #c0392b)';
        
        // 3秒后恢复
        setTimeout(() => {
            btnSearch.innerHTML = originalText;
            btnSearch.style.background = '';
        }, 3000);
        
        showNotification('检索失败，请重试');
    }
}

// 分配历史航警分组颜色
function assignArchiveGroupColors(classify) {
    archiveGroupColors = {};
    Object.keys(classify).forEach(key => {
        archiveGroupColors[key] = randomColor();
    });
}

// 获取历史航警的颜色
function getColorForArchiveCode(code) {
    if (!archiveDict || !archiveDict.CLASSIFY) return currentColorPool[0];
    for (const [group, codes] of Object.entries(archiveDict.CLASSIFY)) {
        if (codes.includes(code)) {
            return archiveGroupColors[group] || currentColorPool[0];
        }
    }
    return currentColorPool[0];
}

// 绘制所有历史航警
function drawAllArchiveNotams() {
    if (!archiveDict || archiveDict.NUM === 0) return;

    // 先清除旧的多边形
    polygonArchive.forEach(p => p && map.removeLayer(p));
    polygonArchive = [];

    for (let i = 0; i < archiveDict.NUM; i++) {
        const col = getColorForArchiveCode(archiveDict.CODE[i]);
        drawArchiveNotam(
            archiveDict.COORDINATES[i],
            archiveDict.TIME[i],
            archiveDict.CODE[i],
            i,
            col,
            archiveDict.RAWMESSAGE?.[i] || ""
        );
        // 保持之前的可见状态
        if (archiveVisibleState[i] === false) {
            const poly = polygonArchive[i];
            if (poly) map.removeLayer(poly);
        } else {
            archiveVisibleState[i] = true;
        }
    }
}

// 绘制单个历史航警
function drawArchiveNotam(COORstrin, timee, codee, numm, col, rawmessage) {
    var pos = COORstrin;
    console.log(timee);
    var timestr = convertTime(timee);
    console.log(timestr);
    var stPos = 0;
    var arr = [];
    
    for (var i = 0; i < pos.length; i++) {
        if (pos[i] == "-") {
            var tmp = pos.substring(stPos, i);
            arr.push(tmp);
            stPos = i + 1;
        }
    }
    arr.push(pos.substring(stPos, pos.length));
    
    var _TheArray = [];
    for (var i = 0; i < arr.length; i++) {
        _TheArray.push(pullOut(arr[i]));
    }
    
    var latlngs = [];
    for (var i = 0; i < _TheArray.length; i++) {
        if (_TheArray[i]) {
            latlngs.push([_TheArray[i][1], _TheArray[i][0]]);
        }
    }

    if (latlngs.length < 3) return;

    // 创建多边形
    var tmpPolygon = L.polygon(latlngs, {
        color: col,
        weight: 2,
        opacity: 0.8,
        fillColor: col,
        fillOpacity: 0.5,
        dashArray: '3, 3'  // 虚线样式，区分历史航警
    }).addTo(map);

    // 创建弹出窗口
    var popupContent = "<div class='notam-popup'>" +
        "<div class='notam-popup-header' style='background: linear-gradient(135deg, #1e9613ff 0%, #127209ff 100%);'>" +
        "<h4>历史NOTAM信息</h4>" +
        "</div>" +
        "<div class='notam-popup-body'>" +
        "<div class='popup-info-row'>" +
        "<span class='popup-label'>持续时间:</span>" +
        "<span class='popup-value'>" + timestr + "</span>" +
        "</div>" +
        "<div class='popup-info-row'>" +
        "<span class='popup-label'>航警编号:</span>" +
        "<span class='popup-value'>" + codee + "</span>" +
        "</div>" +
        "</div>" +
        "<div class='notam-popup-buttons'>" +
        "<button class='copy copy-coord' onclick=\"handleCopy('" + COORstrin + "')\">复制坐标</button>" +
        "<button class='copy copy-raw' onclick=\"handleCopy('" + (rawmessage || '').replace(/'/g, "\\'").replace(/\n/g, '\\n') + "')\">复制原始航警</button>" +
        "</div>" +
        "</div>";

    tmpPolygon.bindPopup(popupContent, {
        maxWidth: 300,
        className: 'notam-info-popup'
    });

    polygonArchive[numm] = tmpPolygon;
}

// 清除所有历史航警
function clearArchiveNotams() {
    polygonArchive.forEach(p => p && map.removeLayer(p));
    polygonArchive = [];
    archiveVisibleState = {};
    archiveDict = null;
    updateSidebar(); // 更新主航警列表
}

// 定位到历史航警
function locateToArchiveNotam(index) {
    if (!archiveDict || index >= archiveDict.NUM) return;
    try {
        const points = parseCoordinatesToPoints(archiveDict.COORDINATES[index]);
        if (points && points.length > 0) {
            const bounds = L.latLngBounds(points);
            map.fitBounds(bounds, { padding: [80, 80], maxZoom: 6 });
        }
    } catch (e) {
        console.error(e);
    }
}

// 在地图上显示选中的区域
function showRegionOnMap(regionCode) {
    // 清除旧的定时器
    if (regionOverlayTimer) {
        clearTimeout(regionOverlayTimer);
        regionOverlayTimer = null;
    }
    
    // 移除旧的区域覆盖层和标签
    if (currentRegionOverlay) {
        try {
            map.removeLayer(currentRegionOverlay);
        } catch (e) {
            console.warn('移除覆盖层失败:', e);
        }
        
        if (currentRegionOverlay.label) {
            try {
                map.removeLayer(currentRegionOverlay.label);
            } catch (e) {
                console.warn('移除标签失败:', e);
            }
        }
        
        currentRegionOverlay = null;
    }

    if (!regionCode || !ICAO_REGIONS[regionCode]) return;

    const region = ICAO_REGIONS[regionCode];

    // 对于内陆及近海区域，只显示标签不显示边界
    if (regionCode === 'internal') {
        // 只添加标签
        const label = L.marker(region.center, {
            icon: L.divIcon({
                className: 'region-label',
                html: `<div style="background: rgba(52, 152, 219, 0.9); color: white; padding: 5px 10px; border-radius: 5px; font-weight: bold; white-space: nowrap;">${region.name}</div>`,
                iconSize: [100, 30]
            })
        }).addTo(map);

        // 创建一个虚拟的覆盖层对象，只存储label
        currentRegionOverlay = { label: label };

        // 缩放到中国区域
        map.setView(region.center, 4);
    } else {
        // 其他区域正常显示边界和标签
        currentRegionOverlay = L.polygon(region.bounds, {
            color: '#1c7700ff',
            weight: 2,
            opacity: 0.8,
            fillColor: '#2dc435ff',
            fillOpacity: 0.1,
            dashArray: '10, 5'
        }).addTo(map);
        
        // 添加标签
        const label = L.marker(region.center, {
            icon: L.divIcon({
                className: 'region-label',
                html: `<div style="background: rgba(22, 110, 37, 1); color: white; padding: 5px 10px; border-radius: 5px; font-weight: bold; white-space: nowrap;">${region.name}</div>`,
                iconSize: [100, 30]
            })
        }).addTo(map);

        // 将标签也存储，方便一起删除
        currentRegionOverlay.label = label;

        // 缩放到区域
        map.fitBounds(region.bounds, { padding: [50, 50] });
    }

    // 5秒后自动移除区域显示
    regionOverlayTimer = setTimeout(() => {
        if (currentRegionOverlay) {
            try {
                if (currentRegionOverlay.removeFrom) {
                    map.removeLayer(currentRegionOverlay);
                }
            } catch (e) {
                console.warn('定时移除覆盖层失败:', e);
            }
            
            if (currentRegionOverlay.label) {
                try {
                    map.removeLayer(currentRegionOverlay.label);
                } catch (e) {
                    console.warn('定时移除标签失败:', e);
                }
            }
            
            currentRegionOverlay = null;
        }
        regionOverlayTimer = null;
    }, 5000);
}
