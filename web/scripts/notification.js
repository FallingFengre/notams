function showNotification(message, type = 'info') {
    // 移除旧的
    const old = document.querySelector('.notification');
    if (old) old.remove();

    const div = document.createElement('div');
    div.className = 'notification';
    div.textContent = message;
    document.body.appendChild(div);

    // 触发 reflow
    requestAnimationFrame(() => div.classList.add('show'));

    // 根据类型设置不同的显示时间
    const duration = type === 'success' ? 4000 : 2000;
    
    setTimeout(() => {
        div.classList.remove('show');
        setTimeout(() => div.remove(), 400);
    }, duration);
}