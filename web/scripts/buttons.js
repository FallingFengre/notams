const helpButton = document.getElementById('helpButton');
const exportButton = document.getElementById('exportButton');
const expandableArea = document.getElementById('expandableArea');
const exportArea = document.getElementById('exportArea');
const logPanel = document.getElementById('logPanel');
let logPanelExpanded = false;
let logUpdateInterval = null;
let userScrolledUp = false;
let lastLogCount = 0;
const customButton = document.getElementById('customButton');
let isHelpExpanded = false;
let isExportExpanded = false;

// 可调试的高度变量
const HELP_AREA_HEIGHT = 320;  // 帮助区域高度
const EXPORT_AREA_HEIGHT = 230; // 导出区域高度

helpButton.addEventListener('click', () => {
    if (isExportExpanded) {
        // 先收起导出页
        closeExportArea();
        // 稍微延迟后展开帮助页
        setTimeout(() => {
            openHelpArea();
        }, 100);
    } else {
        // 切换帮助页状态
        if (isHelpExpanded) {
            closeHelpArea();
        } else {
            openHelpArea();
        }
    }
});

exportButton.addEventListener('click', () => {
    if (isHelpExpanded) {
        // 先收起帮助页
        closeHelpArea();
        // 稍微延迟后展开导出页
        setTimeout(() => {
            openExportArea();
        }, 100);
    } else {
        // 切换导出页状态
        if (isExportExpanded) {
            closeExportArea();
        } else {
            openExportArea();
        }
    }
});

function openHelpArea() {
    isHelpExpanded = true;
    expandableArea.style.maxHeight = HELP_AREA_HEIGHT + 'px';
    const isMobile = window.innerWidth <= 768;
    expandableArea.style.bottom = isMobile ? '60px' : '10px';
    // 等待 DOM 更新后获取实际高度
    setTimeout(() => {
        helpButton.style.transform = `translateY(-${HELP_AREA_HEIGHT }px)`;
        exportButton.style.transform = `translateY(-${HELP_AREA_HEIGHT }px)`;
        if (customButton) customButton.style.transform = `translateY(-${HELP_AREA_HEIGHT }px)`;
    }, 10);
    helpButton.textContent = '收起';
}

function closeHelpArea() {
    isHelpExpanded = false;
    expandableArea.style.maxHeight = '0';
    const isMobile = window.innerWidth <= 768;
    expandableArea.style.bottom = isMobile ? '90px' : '40px';
    helpButton.style.transform = 'translateY(0)';
    exportButton.style.transform = 'translateY(0)';
    if (customButton) customButton.style.transform = 'translateY(0)';
    helpButton.textContent = '帮助';
}

function openExportArea() {
    isExportExpanded = true;
    exportArea.style.maxHeight = EXPORT_AREA_HEIGHT + 'px';
    const isMobile = window.innerWidth <= 768;
    exportArea.style.bottom = isMobile ? '60px' : '10px';
    // 等待 DOM 更新后获取实际高度
    setTimeout(() => {
        helpButton.style.transform = `translateY(-${EXPORT_AREA_HEIGHT }px)`;
        exportButton.style.transform = `translateY(-${EXPORT_AREA_HEIGHT }px)`;
        if (customButton) customButton.style.transform = `translateY(-${EXPORT_AREA_HEIGHT }px)`;
    }, 10);
    exportButton.textContent = '收起';
}

function closeExportArea() {
    isExportExpanded = false;
    exportArea.style.maxHeight = '0';
    const isMobile = window.innerWidth <= 768;
    exportArea.style.bottom = isMobile ? '90px' : '40px';
    helpButton.style.transform = 'translateY(0)';
    exportButton.style.transform = 'translateY(0)';
    if (customButton) customButton.style.transform = 'translateY(0)';
    exportButton.textContent = '导出';
}

// 日志面板功能
function toggleLogPanel() {
    logPanelExpanded = !logPanelExpanded;
    
    if (logPanelExpanded) {
        logPanel.classList.add('show');
        userScrolledUp = false;
        lastLogCount = 0;
        updateLogs();
        
        logUpdateInterval = setInterval(updateLogs, 500);
    } else {
        logPanel.classList.remove('show');
        if (logUpdateInterval) {
            clearInterval(logUpdateInterval);
            logUpdateInterval = null;
        }
    }
}

function updateLogs() {
    fetch('/logs')
        .then(response => response.json())
        .then(logs => {
            const logContent = document.getElementById('logContent');
            
            if (logs.length === 0) {
                logContent.innerHTML = '<div class="log-empty">暂无日志</div>';
                lastLogCount = 0;
                return;
            }
            
            
            const hasNewLogs = logs.length !== lastLogCount;
            lastLogCount = logs.length;
            
            logContent.innerHTML = logs.map(log => {
                return `<div class="log-item">
                    <span class="log-timestamp">[${log.timestamp}]</span>
                    <span class="log-level log-level-${log.level}">${log.level}</span>
                    <span class="log-message">${ansiToHtml(log.message)}</span>
                </div>`;
            }).join('');
            
            //只有在用户没有向上滚动且有新日志时才自动滚动到底部
            if (!userScrolledUp && hasNewLogs) {
                logContent.scrollTop = logContent.scrollHeight;
            }
        })
        .catch(error => {
            console.error('获取日志失败:', error);
        });
}

document.addEventListener('DOMContentLoaded', function() {
    const logContent = document.getElementById('logContent');
    if (logContent) {
        logContent.addEventListener('scroll', function() {
            const isAtBottom = logContent.scrollHeight - logContent.scrollTop <= logContent.clientHeight + 50;
            userScrolledUp = !isAtBottom;
        });
    }
});

function clearLogs() {
    fetch('/logs/clear', {
        method: 'POST'
    })
    .then(response => response.json())
    .then(data => {
        const logContent = document.getElementById('logContent');
        logContent.innerHTML = '<div class="log-empty">日志已清空</div>';
        lastLogCount = 0;
        userScrolledUp = false;
    })
    .catch(error => {
        console.error('清空日志失败:', error);
    });
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// 将ANSI颜色代码转换为HTML
function ansiToHtml(text) {
    // 先转义HTML
    text = escapeHtml(text);
    
    // ANSI颜色映射
    const ansiColors = {
        '30': '#000000', // 黑色
        '31': '#ff6b6b', // 红色
        '32': '#51cf66', // 绿色
        '33': '#ffd93d', // 黄色
        '34': '#4dabf7', // 蓝色
        '35': '#cc5de8', // 品红
        '36': '#22b8cf', // 青色
        '37': '#adb5bd', // 白色
        '90': '#868e96', // 亮黑
        '91': '#ff8787', // 亮红
        '92': '#8ce99a', // 亮绿
        '93': '#ffe066', // 亮黄
        '94': '#74c0fc', // 亮蓝
        '95': '#d0bfff', // 亮品红
        '96': '#66d9e8', // 亮青
        '97': '#f1f3f5'  // 亮白
    };
    
    let result = text;
    let styles = [];
    
    // 处理ANSI转义序列
    result = result.replace(/\x1b\[([0-9;]*)m/g, (match, codes) => {
        if (!codes || codes === '0') {
            // 重置所有样式
            const closeTag = styles.length > 0 ? '</span>' : '';
            styles = [];
            return closeTag;
        }
        
        const codeList = codes.split(';');
        let style = '';
        let closeTag = '';
        
        codeList.forEach(code => {
            if (code === '1') {
                // 粗体
                style += 'font-weight: bold; ';
            } else if (code === '4') {
                // 下划线
                style += 'text-decoration: underline; ';
            } else if (ansiColors[code]) {
                // 前景色
                style += `color: ${ansiColors[code]}; `;
            }
        });
        
        if (styles.length > 0) {
            closeTag = '</span>';
        }
        
        if (style) {
            styles.push(style);
            return closeTag + `<span style="${style}">`;
        }
        
        return closeTag;
    });
    
    // 关闭所有未闭合的span
    if (styles.length > 0) {
        result += '</span>'.repeat(styles.length);
    }
    
    return result;
}

// 动态调整展开区域的位置
window.addEventListener('resize', () => {
    const isMobile = window.innerWidth <= 768;
    if (isHelpExpanded) {
        expandableArea.style.bottom = isMobile ? '60px' : '10px';
    } else {
        expandableArea.style.bottom = isMobile ? '90px' : '40px';
    }
    if (isExportExpanded) {
        exportArea.style.bottom = isMobile ? '60px' : '10px';
    } else {
        exportArea.style.bottom = isMobile ? '90px' : '40px';
    }
});

