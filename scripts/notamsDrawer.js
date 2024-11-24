let expanded = false;
let warningCount = 0;

function toggleDrawer() {
    const drawer = document.getElementById('drawer');
    const content = document.getElementById('drawerContent');
    const arrow = document.getElementById('toggleArrow');

    if (expanded) {
        drawer.classList.remove('expanded');
        content.style.display = 'none';
        arrow.textContent = ' '; 
    } else {
        drawer.classList.add('expanded');
        content.style.display = 'block';
        arrow.textContent = '收起';
        // modeInitial(); // 调用初始化函数
    }

    expanded = !expanded;
}

function drawWarning() {
    const text = document.getElementById('inputText').value.trim();
    const color = document.getElementById('colorSelect').value;
    const coordPattern = /N\d{4,6}E\d{5,7}/;
    if (!coordPattern.test(text)) {
        alert("请输入正确的航警，格式应包含有效的坐标\n（如：N394838E1005637-N391617E1005933-N392001E1021555-N395223E1021334）");
        return;
    }

    if (!text) {
        alert("请填写内容！");
        return;
    }
    warningCount++;
    const num = warningCount;

    selfDrawNot(text, color, num);

    const warningItem = document.createElement('div');
    warningItem.className = 'warning-item';
    warningItem.style.borderLeft = `5px solid ${color}`;
    warningItem.innerHTML = `
        <span>航警${num}</span>
        <button onclick="removeWarning(${num}, this)">移除</button>
    `;

    const warningList = document.getElementById('warningList');
    warningList.appendChild(warningItem);

    document.getElementById('inputText').value = '';
}

function removeWarning(num, button) {

    notRemove(num);

    const warningItem = button.parentElement;
    warningItem.parentElement.removeChild(warningItem);
}

function removeObj() {
    const warningList = document.getElementById('warningList');
    while (warningList.firstChild) {
        warningList.removeChild(warningList.firstChild);
    }
}

function selfDrawNot(text, color, num) {
    text = text.replace(/{[^}]+}/g, ''); 
    text = text.replace(/%[^%]+%/g, ''); 
    text = text.replace(/[\r\n]+/g, '');
    const coorRegex = /N\d{4,6}E\d{5,7}(?:-N\d{4,6}E\d{5,7})*/g;
    // const timeRegex = /(\d{2} [A-Z]{3} \d{2}:\d{2} \d{4} UNTIL \d{2} [A-Z]{3} \d{2}:\d{2} \d{4})/;
    const codeRegex = /A\d{4}\/\d{2}/g;
    const coor = text.match(coorRegex);
    // const time = text.match(timeRegex);
    const code = text.match(codeRegex);
    // alert(coor[0]);
    drawNot(coor[0], "TechnicalIssue", code, num, color, 1);
}

function notRemove(num) {
    map.removeOverlay(polygon[num]);
}

function modeInitial(){
    map.clearOverlays();
    siteInit();
}