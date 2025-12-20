// 检测是否在 PyWebView 环境中
const isPyWebView = typeof window.pywebview !== 'undefined';

// 主导出函数 (使用 leaflet-image)
async function exportMapAsImage() {
  const exportBtn = document.getElementById('btnExportImage');
  const originalText = exportBtn.innerHTML;
  const originalBg = exportBtn.style.background;
  exportBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 导出中... 0%';
  exportBtn.disabled = true;
  exportBtn.style.background = 'linear-gradient(to right, #2980b9 0%, #e0e0e0 0%)';

  try {
    const range = document.getElementById('exportRange').value;
    const format = document.getElementById('exportFormat').value;
    const quality = parseInt(document.getElementById('exportQuality').value) || 3;

    // 处理不同的导出范围
    let cropBounds = null;
    if (range === 'custom') {
      // 自定义区域 - 保存裁剪坐标，不调整视图
      const customBounds = window.getCustomBounds ? window.getCustomBounds() : null;
      const customPixelBounds = window.getCustomPixelBounds ? window.getCustomPixelBounds() : null;
      if (!customBounds || !customPixelBounds) {
        showNotification('请先选择导出区域', 'info');
        exportBtn.innerHTML = originalText;
        exportBtn.disabled = false;
        exportBtn.style.background = originalBg;
        return;
      }
      cropBounds = customPixelBounds;
    } else if (range === 'full') {
      // 包含所有落区
      const visiblePolygons = [];

      const visibleManualPolygons = manualNotams
        .filter(notam => manualVisibleState[notam.id] !== false && notam.polygon)
        .map(notam => notam.polygon);
      visiblePolygons.push(...visibleManualPolygons);

      const visibleAutoPolygons = polygonAuto
        .filter((poly, idx) => visibleState[idx] !== false && poly);
      visiblePolygons.push(...visibleAutoPolygons);

      if (visiblePolygons.length > 0) {
        const tempGroup = L.featureGroup(visiblePolygons);
        const bounds = tempGroup.getBounds();
        map.fitBounds(bounds, { padding: [10, 10] });
        await new Promise(resolve => setTimeout(resolve, 500));
      }
    }
    // 如果是 current 则不需要调整视图

    // 使用增强版 leaflet-image（支持高DPI和SVG）
    leafletImageEnhanced(map, async (err, canvas) => {
      exportBtn.innerHTML = originalText;
      exportBtn.disabled = false;
      exportBtn.style.background = originalBg;

      if (err) {
        console.error('导出失败:', err);
        alert('导出失败：' + (err.message || '未知错误'));
        return;
      }

      // 如果是自定义区域，裁剪canvas
      if (cropBounds) {
        const scale = quality; // 高DPI缩放
        const croppedCanvas = document.createElement('canvas');
        croppedCanvas.width = cropBounds.width * scale;
        croppedCanvas.height = cropBounds.height * scale;
        const ctx = croppedCanvas.getContext('2d');
        
        // 从原始canvas裁剪
        ctx.drawImage(
          canvas,
          cropBounds.minX * scale, cropBounds.minY * scale,  // 源起点
          cropBounds.width * scale, cropBounds.height * scale,  // 源大小
          0, 0,  // 目标起点
          cropBounds.width * scale, cropBounds.height * scale   // 目标大小
        );
        
        canvas = croppedCanvas; // 替换为裁剪后的canvas
      }

      // 导出完成后，如果是自定义区域，重置按钮状态
      if (range === 'custom' && window.resetCustomSelection) {
        window.resetCustomSelection();
      }

      // 生成文件名
      const now = new Date();
      const dateStr = now.toISOString().split('T')[0].replace(/-/g, '');
      const timeStr = now.toTimeString().split(' ')[0].replace(/:/g, '').substring(0, 6);
      const fileName = `NOTAM_落区_${dateStr}_${timeStr}.${format}`;

      if (isPyWebView) {
        try {
          const dataURL = canvas.toDataURL(`image/${format}`, format === 'jpeg' ? 0.92 : 1.0);
          const response = await fetch('/save_image', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ default_name: fileName, data_url: dataURL })
          });
          const result = await response.json();

          if (result.success) {
            showNotification(`已保存至：${result.filePath}\n图片已同时复制到剪贴板`, 'success');
          } else if (result.message) {
            showNotification(result.message, 'info');
          } else {
            throw new Error(result.error || '保存失败');
          }
        } catch (e) {
          console.error('保存失败:', e);
          const link = document.createElement('a');
          link.download = fileName;
          link.href = canvas.toDataURL(`image/${format}`, format === 'jpeg' ? 0.92 : 1.0);
          document.body.appendChild(link);
          link.click();
          document.body.removeChild(link);
          showNotification('保存失败，已直接下载', 'warning');
        }
      } else {
        const link = document.createElement('a');
        link.download = fileName;
        link.href = canvas.toDataURL(`image/${format}`, format === 'jpeg' ? 0.92 : 1.0);
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        showNotification('导出成功！', 'success');
      }
    }, {
      scale: quality, // 使用用户选择的质量
      quality: format === 'jpeg' ? 0.92 : 1.0,
      onProgress: function(progress) {
        exportBtn.style.background = `linear-gradient(to right, #2980b9 ${progress}%, #7eb6db ${progress}%)`;
        exportBtn.innerHTML = `<i class="fas fa-spinner fa-spin"></i> 导出中... ${progress}%`;
      }
    });

  } catch (error) {
    console.error('导出过程出错:', error);
    alert('导出过程中发生错误: ' + error.message);
    exportBtn.innerHTML = originalText;
    exportBtn.disabled = false;
    exportBtn.style.background = originalBg;
  }
}

// 绑定导出按钮
document.getElementById('btnExportImage')?.addEventListener('click', exportMapAsImage);