// Frontend logic for Banana Pro AI Image Generator

document.addEventListener('DOMContentLoaded', () => {
    // DOM Elements
    const apiTypeSelect = document.getElementById('api-type');
    const apiKeyInput = document.getElementById('api-key');
    const toggleApiKeyBtn = document.getElementById('toggle-api-key');
    const customApiFields = document.getElementById('custom-api-fields');
    const customUrlInput = document.getElementById('custom-url');
    const customHeadersInput = document.getElementById('custom-headers');
    const customBodyInput = document.getElementById('custom-body');
    const browserApiFields = document.getElementById('browser-api-fields');
    const apiKeyGroup = document.getElementById('api-key-group');
    const saveDirInput = document.getElementById('save-dir');
    const btnOpenFolder = document.getElementById('btn-open-folder');
    const btnSaveConfig = document.getElementById('btn-save-config');
    const btnLaunchBrowser = document.getElementById('btn-launch-browser');
    
    const promptInput = document.getElementById('prompt-input');
    const charCounter = document.getElementById('char-counter');
    const modelSelect = document.getElementById('model-select');
    const modelSelectCard = document.getElementById('model-select-card');
    const btnGenerate = document.getElementById('btn-generate');
    
    const previewSection = document.getElementById('preview-section');
    const statusCard = document.getElementById('status-card');
    const statusTitle = document.getElementById('status-title');
    const statusDesc = document.getElementById('status-desc');
    const progressBarFill = document.querySelector('.progress-bar-fill');
    
    const resultCard = document.getElementById('result-card');
    const resultImage = document.getElementById('result-image');
    const savedPathText = document.getElementById('saved-path-text');
    const btnCopyPath = document.getElementById('btn-copy-path');
    const resultTime = document.getElementById('result-time');
    const resultRatio = document.getElementById('result-ratio');
    const resultModel = document.getElementById('result-model');
    const btnOpenResultFolder = document.getElementById('btn-open-result-folder');
    const btnReusePromptResult = document.getElementById('btn-reuse-prompt-result');
    
    const historyCount = document.getElementById('history-count');
    const historyGrid = document.getElementById('history-grid');
    const noHistoryPlaceholder = document.getElementById('no-history-placeholder');
    
    // Lightbox modal elements
    const lightboxModal = document.getElementById('lightbox-modal');
    const lightboxImg = document.getElementById('lightbox-img');
    const lightboxCaption = document.getElementById('lightbox-caption');
    const modalClose = document.querySelector('.modal-close');
    
    const toastContainer = document.getElementById('toast-container');
    
    // QR Adjust Elements
    const qrAdjustSection = document.getElementById('qr-adjust-section');
    const qrPreviewOverlay = document.getElementById('qr-preview-overlay');
    const adjustQrX = document.getElementById('adjust-qr-x');
    const adjustQrY = document.getElementById('adjust-qr-y');
    const adjustQrSize = document.getElementById('adjust-qr-size');
    const qrXVal = document.getElementById('qr-x-val');
    const qrYVal = document.getElementById('qr-y-val');
    const qrSizeVal = document.getElementById('qr-size-val');
    const btnApplyQrAdjust = document.getElementById('btn-apply-qr-adjust');
    
    let currentImageFilename = '';
    let currentQrLink = '';

    function updateQrPreview() {
        if (!currentQrLink) {
            qrPreviewOverlay.classList.add('hidden');
            return;
        }
        const x = parseFloat(adjustQrX.value);
        const y = parseFloat(adjustQrY.value);
        const size = parseFloat(adjustQrSize.value);
        
        qrXVal.innerText = `${x.toFixed(1)}%`;
        qrYVal.innerText = `${y.toFixed(1)}%`;
        qrSizeVal.innerText = `${size.toFixed(1)}%`;
        
        const imgW = resultImage.clientWidth;
        const imgH = resultImage.clientHeight;
        if (imgW > 0 && imgH > 0) {
            const minDim = Math.min(imgW, imgH);
            const qrPxSize = minDim * (size / 100);
            const wPercent = (qrPxSize / imgW) * 100;
            const hPercent = (qrPxSize / imgH) * 100;
            
            qrPreviewOverlay.style.width = `${wPercent}%`;
            qrPreviewOverlay.style.height = `${hPercent}%`;
            qrPreviewOverlay.style.left = `${x}%`;
            qrPreviewOverlay.style.top = `${y}%`;
            qrPreviewOverlay.classList.remove('hidden');
        }
    }

    // Set up listeners for adjustment sliders
    adjustQrX.addEventListener('input', updateQrPreview);
    adjustQrY.addEventListener('input', updateQrPreview);
    adjustQrSize.addEventListener('input', updateQrPreview);
    
    // Sync main panel positioning inputs with sliders
    const qrPositionSelect = document.getElementById('qr-position-select');
    const qrSizeSelect = document.getElementById('qr-size-select');
    
    qrPositionSelect.addEventListener('change', () => {
        const pos = qrPositionSelect.value;
        const size = parseFloat(qrSizeSelect.value) || 43.0;
        
        let x = 38.0;
        let y = 28.5;
        
        if (pos === 'bottom_right') {
            x = 100 - size - 5;
            y = 100 - size - 5;
        } else if (pos === 'bottom_left') {
            x = 5;
            y = 100 - size - 5;
        } else if (pos === 'top_right') {
            x = 100 - size - 5;
            y = 5;
        } else if (pos === 'top_left') {
            x = 5;
            y = 5;
        }
        
        adjustQrX.value = x;
        adjustQrY.value = y;
        adjustQrSize.value = size;
        
        if (currentQrLink) {
            updateQrPreview();
        }
    });

    qrSizeSelect.addEventListener('change', () => {
        const size = parseFloat(qrSizeSelect.value) || 43.0;
        adjustQrSize.value = size;
        
        // Auto center coordinates if position is center
        const pos = qrPositionSelect.value;
        if (pos === 'center') {
            adjustQrX.value = 38.0;
            adjustQrY.value = 28.5;
        }
        
        if (currentQrLink) {
            updateQrPreview();
        }
    });
    
    // Auto align overlay when image finishes loading
    resultImage.addEventListener('load', () => {
        if (currentQrLink) {
            updateQrPreview();
        }
    });

    // Handle resize events to keep QR preview square and correctly positioned
    window.addEventListener('resize', () => {
        if (currentQrLink && !resultCard.classList.contains('hidden')) {
            updateQrPreview();
        }
    });

    // Send updated QR coordinates to backend for re-baking
    btnApplyQrAdjust.addEventListener('click', async () => {
        if (!currentImageFilename) return;
        
        btnApplyQrAdjust.disabled = true;
        btnApplyQrAdjust.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> ĐANG ÁP DỤNG...`;
        
        const payload = {
            filename: currentImageFilename,
            qr_link: currentQrLink,
            qr_x: parseFloat(adjustQrX.value),
            qr_y: parseFloat(adjustQrY.value),
            qr_size: parseFloat(adjustQrSize.value)
        };
        
        try {
            const response = await fetch('/api/adjust-qr', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            
            if (response.ok) {
                const data = await response.json();
                if (data.status === 'success') {
                    // Force refresh preview by appending cache-busting timestamp
                    resultImage.src = `${data.image.url}?t=${Date.now()}`;
                    showToast('Đã cập nhật vị trí mã QR thành công!');
                    loadHistory();
                } else {
                    showToast(`Lỗi: ${data.message}`, 'error');
                }
            } else {
                showToast('Lỗi kết nối máy chủ khi căn chỉnh QR.', 'error');
            }
        } catch (e) {
            showToast(`Lỗi: ${e.message}`, 'error');
        } finally {
            btnApplyQrAdjust.disabled = false;
            btnApplyQrAdjust.innerHTML = `<i class="fa-solid fa-square-check"></i> ÁP DỤNG & LƯU LẠI ẢNH MỚI`;
        }
    });

    let isGenerating = false;
    let progressInterval = null;

    // Toast Notification helper
    function showToast(message, type = 'success') {
        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        
        const icon = type === 'success' ? 'fa-circle-check' : 'fa-circle-exclamation';
        const iconColor = type === 'success' ? '#10b981' : '#ef4444';
        
        toast.innerHTML = `
            <i class="fa-solid ${icon}" style="color: ${iconColor}"></i>
            <div class="toast-message">${message}</div>
            <i class="fa-solid fa-xmark toast-close"></i>
        `;
        
        toastContainer.appendChild(toast);
        
        // Remove toast on click of close button
        toast.querySelector('.toast-close').addEventListener('click', () => {
            toast.style.animation = 'slideIn 0.3s reverse forwards';
            setTimeout(() => toast.remove(), 300);
        });
        
        // Auto remove toast
        setTimeout(() => {
            if (toast.parentNode) {
                toast.style.animation = 'slideIn 0.3s reverse forwards';
                setTimeout(() => toast.remove(), 300);
            }
        }, 5000);
    }

    // Toggle API Key visibility
    toggleApiKeyBtn.addEventListener('click', () => {
        const type = apiKeyInput.type === 'password' ? 'text' : 'password';
        apiKeyInput.type = type;
        const icon = toggleApiKeyBtn.querySelector('i');
        if (type === 'password') {
            icon.className = 'fa-solid fa-eye';
        } else {
            icon.className = 'fa-solid fa-eye-slash';
        }
    });

    // Toggle custom fields on API type change
    apiTypeSelect.addEventListener('change', () => {
        if (apiTypeSelect.value === 'custom') {
            customApiFields.classList.remove('hidden');
            browserApiFields.classList.add('hidden');
            apiKeyGroup.classList.remove('hidden');
            modelSelectCard.classList.remove('hidden');
            document.getElementById('api-key-label').innerText = 'API Key / Token';
            apiKeyInput.placeholder = 'Nhập Token ủy quyền của bên thứ 3 (nếu có)...';
        } else if (apiTypeSelect.value === 'browser') {
            customApiFields.classList.add('hidden');
            browserApiFields.classList.remove('hidden');
            apiKeyGroup.classList.add('hidden');
            modelSelectCard.classList.add('hidden');
        } else {
            customApiFields.classList.add('hidden');
            browserApiFields.classList.add('hidden');
            apiKeyGroup.classList.remove('hidden');
            modelSelectCard.classList.remove('hidden');
            document.getElementById('api-key-label').innerText = 'API Key';
            apiKeyInput.placeholder = 'Nhập API Key của bạn...';
        }
    });

    // Launch chrome for browser automation
    btnLaunchBrowser.addEventListener('click', async () => {
        btnLaunchBrowser.disabled = true;
        btnLaunchBrowser.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Đang khởi chạy Chrome...`;
        try {
            const response = await fetch('/api/launch-browser', { method: 'POST' });
            const data = await response.json();
            if (response.ok) {
                showToast('Đã khởi chạy cửa sổ Google Chrome gỡ lỗi. Vui lòng kiểm tra màn hình và đăng nhập Google.');
            } else {
                showToast(`Không thể khởi chạy Chrome: ${data.message}`, 'error');
            }
        } catch (e) {
            showToast('Lỗi kết nối khi khởi chạy Chrome.', 'error');
        } finally {
            btnLaunchBrowser.disabled = false;
            btnLaunchBrowser.innerHTML = `<i class="fa-brands fa-chrome"></i> Mở trình duyệt điều khiển`;
        }
    });

    // Handle prompt length counter
    promptInput.addEventListener('input', () => {
        const length = promptInput.value.length;
        charCounter.innerText = `${length} / 1000`;
    });

    // Load configs from server
    async function loadConfig() {
        try {
            const response = await fetch('/api/config');
            if (response.ok) {
                const config = await response.json();
                
                apiTypeSelect.value = config.api_type;
                apiKeyInput.value = config.api_key;
                saveDirInput.value = config.save_dir;
                customUrlInput.value = config.custom_url;
                customHeadersInput.value = config.custom_headers;
                customBodyInput.value = config.custom_body;
                modelSelect.value = config.model;
                
                // Select proper aspect ratio in UI
                const ratioInput = document.querySelector(`input[name="aspect-ratio"][value="${config.aspect_ratio}"]`);
                if (ratioInput) ratioInput.checked = true;
                
                // Trigger change event to show/hide custom fields
                apiTypeSelect.dispatchEvent(new Event('change'));
            }
        } catch (e) {
            showToast('Không thể tải cấu hình từ server.', 'error');
        }
    }

    // Save configurations
    async function saveConfig(quiet = false) {
        const checkedRatio = document.querySelector('input[name="aspect-ratio"]:checked');
        const config = {
            api_type: apiTypeSelect.value,
            api_key: apiKeyInput.value,
            save_dir: saveDirInput.value,
            custom_url: customUrlInput.value,
            custom_headers: customHeadersInput.value,
            custom_body: customBodyInput.value,
            model: modelSelect.value,
            aspect_ratio: checkedRatio ? checkedRatio.value : '1:1'
        };

        try {
            const response = await fetch('/api/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(config)
            });
            
            if (response.ok) {
                const data = await response.json();
                saveDirInput.value = data.config.save_dir; // Update with resolved absolute path
                if (!quiet) showToast('Cấu hình đã được lưu thành công!');
                return true;
            } else {
                const err = await response.json();
                showToast(`Không thể lưu cấu hình: ${err.message}`, 'error');
                return false;
            }
        } catch (e) {
            showToast('Lỗi kết nối khi lưu cấu hình.', 'error');
            return false;
        }
    }

    btnSaveConfig.addEventListener('click', () => saveConfig());

    // Open Save directory
    async function openFolder() {
        try {
            const response = await fetch('/api/open-folder', { method: 'POST' });
            const data = await response.json();
            if (data.status === 'success') {
                showToast('Đang mở thư mục lưu ảnh...');
            } else {
                showToast(`Không thể mở thư mục: ${data.message}`, 'error');
            }
        } catch (e) {
            showToast('Lỗi kết nối khi yêu cầu mở thư mục.', 'error');
        }
    }

    btnOpenFolder.addEventListener('click', openFolder);
    btnOpenResultFolder.addEventListener('click', openFolder);

    // Copy Path to Clipboard
    btnCopyPath.addEventListener('click', () => {
        navigator.clipboard.writeText(savedPathText.innerText);
        showToast('Đã sao chép đường dẫn file vào Clipboard!');
        const icon = btnCopyPath.querySelector('i');
        icon.className = 'fa-solid fa-check';
        setTimeout(() => icon.className = 'fa-regular fa-copy', 2000);
    });

    // Populate history items
    async function loadHistory() {
        try {
            const response = await fetch('/api/history');
            if (response.ok) {
                const history = await response.json();
                historyCount.innerText = `${history.length} ảnh`;
                
                if (history.length === 0) {
                    noHistoryPlaceholder.classList.remove('hidden');
                    // Remove any old items
                    const items = historyGrid.querySelectorAll('.history-card');
                    items.forEach(el => el.remove());
                    return;
                }
                
                noHistoryPlaceholder.classList.add('hidden');
                
                // Clear old cards
                const oldCards = historyGrid.querySelectorAll('.history-card');
                oldCards.forEach(el => el.remove());
                
                // Render list
                history.forEach(item => {
                    const imageUrl = item.url || ('/images/' + item.filename);
                    const card = document.createElement('div');
                    card.className = 'history-card';
                    card.innerHTML = `
                        <div class="card-image-wrapper">
                            <img src="${imageUrl}" alt="${item.prompt.substring(0, 30)}" loading="lazy">
                            <div class="card-overlay">
                                <p class="overlay-prompt">${escapeHtml(item.prompt)}</p>
                                <div class="overlay-meta">
                                    <span>${item.aspect_ratio}</span>
                                    <span>${item.model.split('/').pop().substring(0, 15)}</span>
                                </div>
                                <div class="overlay-actions">
                                    <button class="btn-primary btn-reuse" data-prompt="${escapeHtml(item.prompt)}"><i class="fa-solid fa-rotate-right"></i> Dùng lại</button>
                                    <button class="btn-secondary btn-zoom" data-url="${imageUrl}" data-prompt="${escapeHtml(item.prompt)}"><i class="fa-solid fa-expand"></i> Phóng to</button>
                                </div>
                            </div>
                        </div>
                        <div class="card-info">
                            <span class="card-timestamp">${item.timestamp}</span>
                            <span class="card-badge">${item.api_type === 'official' ? 'Official' : 'Banana'}</span>
                        </div>
                    `;
                    
                    // Attach card actions
                    card.querySelector('.btn-reuse').addEventListener('click', (e) => {
                        e.stopPropagation();
                        promptInput.value = item.prompt;
                        promptInput.dispatchEvent(new Event('input'));
                        window.scrollTo({ top: 0, behavior: 'smooth' });
                        showToast('Đã sao chép prompt lên khung soạn thảo!');
                    });
                    
                    card.querySelector('.btn-zoom').addEventListener('click', (e) => {
                        e.stopPropagation();
                        openLightbox(imageUrl, item.prompt);
                    });
                    
                    // Clicking card itself opens lightbox
                    card.addEventListener('click', () => {
                        openLightbox(imageUrl, item.prompt);
                    });
                    
                    historyGrid.appendChild(card);
                });
            }
        } catch (e) {
            console.error(e);
        }
    }

    // Lightbox modal operations
    function openLightbox(url, prompt) {
        lightboxImg.src = url;
        lightboxCaption.innerText = prompt;
        lightboxModal.classList.remove('hidden');
    }
    
    modalClose.addEventListener('click', () => {
        lightboxModal.classList.add('hidden');
    });
    
    lightboxModal.addEventListener('click', (e) => {
        if (e.target === lightboxModal) {
            lightboxModal.classList.add('hidden');
        }
    });

    // Helper: Escape HTML string to prevent injection
    function escapeHtml(unsafe) {
        return unsafe
             .replace(/&/g, "&amp;")
             .replace(/</g, "&lt;")
             .replace(/>/g, "&gt;")
             .replace(/"/g, "&quot;")
             .replace(/'/g, "&#039;");
    }

    // Reuse prompt from generation results
    btnReusePromptResult.addEventListener('click', () => {
        promptInput.value = promptInput.value; // It is already there, but just scroll up
        window.scrollTo({ top: 0, behavior: 'smooth' });
        showToast('Hãy chỉnh sửa prompt và nhấn Bắt đầu tạo ảnh.');
    });

    // Start loading state animation
    function startLoadingAnimation() {
        previewSection.classList.remove('hidden');
        statusCard.classList.remove('hidden');
        resultCard.classList.add('hidden');
        
        statusTitle.innerText = 'Đang kết nối tới API Banana Pro...';
        statusDesc.innerText = 'Vui lòng chờ trong giây lát, đang gửi yêu cầu tạo ảnh lên máy chủ AI...';
        progressBarFill.style.width = '10%';
        
        let progress = 10;
        
        // Custom progress stepping
        progressInterval = setInterval(() => {
            if (progress < 90) {
                // Slower increment as it approaches 90%
                const step = progress < 50 ? 5 : 2;
                progress += step;
                progressBarFill.style.width = `${progress}%`;
                
                if (progress === 40) {
                    statusTitle.innerText = 'AI đang thực hiện vẽ tranh...';
                    statusDesc.innerText = 'Đang sinh khối dữ liệu hình ảnh dựa theo mô tả của bạn. Quá trình này cần khoảng 5-10 giây.';
                } else if (progress === 70) {
                    statusTitle.innerText = 'Đang tối ưu hóa chất lượng hình ảnh...';
                    statusDesc.innerText = 'Hình ảnh đã vẽ xong. Đang nén dữ liệu và chuẩn bị gửi file ảnh về máy tính của bạn.';
                } else if (progress === 85) {
                    statusTitle.innerText = 'Đang tải ảnh xuống máy tính...';
                    statusDesc.innerText = 'Nhận dữ liệu từ máy chủ API. Đang ghi file hình ảnh cục bộ vào đĩa cứng.';
                }
            }
        }, 800);
    }

    // Stop loading animation
    function stopLoadingAnimation(success = true) {
        clearInterval(progressInterval);
        progressBarFill.style.width = success ? '100%' : '0%';
        if (!success) {
            previewSection.classList.add('hidden');
        }
    }

    // Generate action
    async function generateImage() {
        const prompt = promptInput.value.trim();
        if (!prompt) {
            showToast('Vui lòng nhập mô tả ảnh (Prompt) trước!', 'error');
            promptInput.focus();
            return;
        }

        if (isGenerating) return;
        
        // Auto-save configuration silently first
        const configSaved = await saveConfig(true);
        if (!configSaved) return;

        isGenerating = true;
        btnGenerate.disabled = true;
        btnGenerate.querySelector('.btn-content').innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> ĐANG XỬ LÝ...`;
        
        startLoadingAnimation();

        const checkedRatio = document.querySelector('input[name="aspect-ratio"]:checked');
        const qrLink = document.getElementById('qr-link-input').value.trim();
        const qrPosition = document.getElementById('qr-position-select').value;
        
        // Grab current coordinates directly from the sliders so any user adjustment is preserved for the next runs
        const qrX = parseFloat(adjustQrX.value);
        const qrY = parseFloat(adjustQrY.value);
        const qrSize = parseFloat(adjustQrSize.value);
        
        const payload = {
            prompt: prompt,
            model: modelSelect.value,
            aspect_ratio: checkedRatio ? checkedRatio.value : '1:1',
            qr_link: qrLink,
            qr_position: qrPosition,
            qr_size: qrSize,
            qr_x: qrX,
            qr_y: qrY
        };

        try {
            const response = await fetch('/api/generate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            if (response.ok) {
                const data = await response.json();
                if (data.status === 'success') {
                    stopLoadingAnimation(true);
                    
                    // Show result details
                    statusCard.classList.add('hidden');
                    resultCard.classList.remove('hidden');
                    
                    // Store state for adjustment
                    currentImageFilename = data.image.filename;
                    currentQrLink = (data.qr && data.qr.has_qr) ? data.qr.qr_link : '';
                    
                    // Configure QR sliders if QR code is enabled
                    if (data.qr && data.qr.has_qr) {
                        adjustQrX.value = data.qr.qr_x;
                        adjustQrY.value = data.qr.qr_y;
                        adjustQrSize.value = data.qr.qr_size;
                        qrXVal.innerText = `${data.qr.qr_x.toFixed(1)}%`;
                        qrYVal.innerText = `${data.qr.qr_y.toFixed(1)}%`;
                        qrSizeVal.innerText = `${data.qr.qr_size.toFixed(1)}%`;
                        qrAdjustSection.classList.remove('hidden');
                        qrPreviewOverlay.classList.remove('hidden');
                    } else {
                        qrAdjustSection.classList.add('hidden');
                        qrPreviewOverlay.classList.add('hidden');
                    }
                    
                    // Set image source (use cache-busting timestamp to prevent caching when overriding)
                    resultImage.src = `${data.image.url}?t=${Date.now()}`;
                    savedPathText.innerText = data.image.local_path;
                    
                    resultTime.innerText = data.image.timestamp;
                    resultRatio.innerText = checkedRatio ? checkedRatio.value : '1:1';
                    resultModel.innerText = modelSelect.options[modelSelect.selectedIndex].text;
                    
                    showToast('Đã tạo ảnh và lưu cục bộ thành công!');
                    
                    // Refresh gallery history
                    loadHistory();
                } else {
                    stopLoadingAnimation(false);
                    showToast(`Tạo ảnh thất bại: ${data.message}`, 'error');
                }
            } else {
                const err = await response.json();
                stopLoadingAnimation(false);
                showToast(`Lỗi máy chủ (${response.status}): ${err.message || response.statusText}`, 'error');
            }
        } catch (e) {
            stopLoadingAnimation(false);
            showToast(`Lỗi mạng: Không thể kết nối tới máy chủ Flask.`, 'error');
        } finally {
            isGenerating = false;
            btnGenerate.disabled = false;
            btnGenerate.querySelector('.btn-content').innerHTML = `<i class="fa-solid fa-wand-magic-sparkles"></i> BẮT ĐẦU TẠO ẢNH`;
        }
    }

    btnGenerate.addEventListener('click', generateImage);

    // Initial load
    loadConfig();
    loadHistory();
});
