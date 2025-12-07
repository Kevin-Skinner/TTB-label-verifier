// Global state
let currentImageFile = null;
let currentVerificationResult = null;
let currentImageUrl = null;
let hoveredField = null;
let activeField = null;
let editableBox = null;
let isDragging = false;
let isResizing = false;
let dragStart = null;
let resizeHandle = null;
let imageSize = null;
let displayedSize = null;

// Handle file selection
function handleFileChange(event) {
    const file = event.target.files[0];
    if (file) {
        document.getElementById('file-name').textContent = `Selected: ${file.name}`;
        document.getElementById('file-name').style.display = 'block';
        currentImageFile = file;
    }
}

// Handle ABV mode toggle - called when any radio button in the group changes
function updateAbvMode() {
    const checkedRadio = document.querySelector('input[name="abv_mode"]:checked');
    if (!checkedRadio) return;
    
    const mode = checkedRadio.value;
    const abvInput = document.getElementById('abv');
    const abvHidden = document.getElementById('abv_hidden');
    
    if (mode === 'na') {
        // N/A is selected - disable and clear input, set hidden to 'n/a'
        abvInput.disabled = true;
        abvInput.value = '';
        abvInput.removeAttribute('required');
        abvHidden.value = 'n/a';
    } else {
        // Value option is selected - enable input, clear hidden (will be set on submit)
        abvInput.disabled = false;
        abvInput.setAttribute('required', 'required');
        abvHidden.value = ''; // Will be set during form submission
        if (mode === 'decimal') {
            abvInput.step = '0.001';
        } else {
            abvInput.step = '0.1';
        }
    }
}

// Validate net contents input - only allow numbers and decimal point
function validateNetContents(input) {
    let value = input.value;
    // Only allow numbers and a single decimal point
    const filtered = value.replace(/[^0-9.]/g, '');
    // Ensure only one decimal point
    const parts = filtered.split('.');
    const sanitized = parts.length > 2 
        ? parts[0] + '.' + parts.slice(1).join('')
        : filtered;
    input.value = sanitized;
}

// Update net contents mode when unit changes - called when any radio button in the group changes
function updateNetContentsMode() {
    const checkedRadio = document.querySelector('input[name="volume_unit"]:checked');
    if (!checkedRadio) return;
    
    const mode = checkedRadio.value;
    const netContentsInput = document.getElementById('net_contents');
    
    if (mode === 'na') {
        // N/A is selected - disable and clear input
        netContentsInput.disabled = true;
        netContentsInput.value = ''; // Keep empty, don't put "n/a"
        netContentsInput.removeAttribute('required');
    } else {
        // Value option is selected - enable input
        netContentsInput.disabled = false;
        netContentsInput.setAttribute('required', 'required');
    }
}

// Update warning value
function updateWarningValue(checkbox) {
    const hiddenInput = document.getElementById('warning_hidden');
    if (checkbox.checked) {
        hiddenInput.value = 'true';
    } else {
        hiddenInput.value = 'false';
    }
}

// Store original values to restore after submission
let originalAbvValue = '';
let originalNetContentsValue = '';

// Handle form submission - prepare form data before HTMX sends it
document.getElementById('verify-form').addEventListener('submit', function(e) {
    // Don't prevent default - let HTMX handle it, but prepare the data first
    
    // Show loading indicator immediately (before HTMX processes)
    const indicator = document.getElementById('processing-indicator');
    if (indicator) {
        indicator.style.display = 'flex';
    }
    
    // Also add htmx-request class to form for CSS
    this.classList.add('htmx-request');
    
    // Handle ABV - save original value and create processed value
    const abvInput = document.getElementById('abv');
    const abvHidden = document.getElementById('abv_hidden');
    const checkedAbvMode = document.querySelector('input[name="abv_mode"]:checked');
    const abvNA = checkedAbvMode && checkedAbvMode.value === 'na';
    originalAbvValue = abvInput.value; // Save original
    
    if (abvNA) {
        // N/A is selected - set hidden input to 'n/a', disable visible input
        abvHidden.value = 'n/a';
        abvInput.disabled = true; // Keep disabled to prevent submission
    } else {
        // Calculate ABV value based on mode
        const abvValue = parseFloat(abvInput.value) || 0;
        const abvMode = checkedAbvMode ? checkedAbvMode.value : '%';
        let finalAbvValue;
        if (abvMode === 'decimal') {
            // Validate decimal mode: values should be between 0 and 1
            if (abvValue < 0 || abvValue > 1) {
                alert('Decimal mode requires a value between 0 and 1 (e.g., 0.145 for 14.5%)');
                e.preventDefault();
                return;
            }
            finalAbvValue = (abvValue * 100).toString();
        } else {
            finalAbvValue = abvValue.toString();
        }
        abvHidden.value = finalAbvValue;
        abvInput.disabled = false;
    }
    
    // Handle net contents - strip any existing units first, then save original
    const netContentsInput = document.getElementById('net_contents');
    const checkedVolumeUnit = document.querySelector('input[name="volume_unit"]:checked');
    const netContentsNA = checkedVolumeUnit && checkedVolumeUnit.value === 'na';
    
    if (netContentsNA) {
        // N/A is selected - send "n/a" but keep input empty and disabled
        netContentsInput.value = 'n/a';
        netContentsInput.disabled = false; // Temporarily enable for submission
        originalNetContentsValue = ''; // Save empty as original
    } else {
        // Strip any existing units (ml, oz, etc.) before saving - be more aggressive
        let netContentsValue = netContentsInput.value.trim();
        // Remove units at the end (case-insensitive, with or without space)
        netContentsValue = netContentsValue.replace(/\s*(ml|mL|ML|oz|fl\s*oz|floz|l|L)\s*$/i, '').trim();
        // Also remove if there's a space and then unit
        netContentsValue = netContentsValue.replace(/\s+(ml|mL|ML|oz|fl\s*oz|floz|l|L)\s*$/i, '').trim();
        
        originalNetContentsValue = netContentsValue; // Save original (just the number)
        
        const volumeUnit = checkedVolumeUnit ? checkedVolumeUnit.value : 'ml';
        // Set the value with unit for submission, but we'll restore the original after
        netContentsInput.value = `${netContentsValue} ${volumeUnit}`;
        netContentsInput.disabled = false;
    }
    
    // Handle warning - remove checkbox, use hidden input
    const warningCheckbox = document.getElementById('warning');
    const warningHidden = document.getElementById('warning_hidden');
    warningHidden.value = warningCheckbox.checked ? 'true' : 'false';
    warningCheckbox.disabled = true; // Prevent it from being submitted
    
    // Disable N/A radio buttons so they don't interfere with submission
    // (The actual value is already set in the input field)
    if (abvNA) {
        const abvModeInputs = document.querySelectorAll('input[name="abv_mode"]:not([value="na"])');
        abvModeInputs.forEach(input => input.disabled = true);
    } else {
        const abvNARadio = document.getElementById('abv_na_radio');
        if (abvNARadio) abvNARadio.disabled = true;
    }
    
    if (netContentsNA) {
        const volumeUnitInputs = document.querySelectorAll('input[name="volume_unit"]:not([value="na"])');
        volumeUnitInputs.forEach(input => input.disabled = true);
    } else {
        const netContentsNARadio = document.getElementById('net_contents_na_radio');
        if (netContentsNARadio) netContentsNARadio.disabled = true;
    }
});

// Show loading indicator when HTMX request starts (backup in case submit handler doesn't fire)
document.body.addEventListener('htmx:beforeRequest', function(event) {
    const form = event.detail.elt;
    if (form && (form.id === 'verify-form' || form.closest('#verify-form'))) {
        const indicator = document.getElementById('processing-indicator');
        if (indicator) {
            indicator.style.display = 'flex';
        }
        const verifyForm = document.getElementById('verify-form');
        if (verifyForm) {
            verifyForm.classList.add('htmx-request');
        }
    }
});

// Hide loading indicator when HTMX request completes or errors
document.body.addEventListener('htmx:afterRequest', function(event) {
    const form = event.detail.elt;
    if (form && (form.id === 'verify-form' || form.closest('#verify-form'))) {
        const indicator = document.getElementById('processing-indicator');
        if (indicator) {
            indicator.style.display = 'none';
        }
        const verifyForm = document.getElementById('verify-form');
        if (verifyForm) {
            verifyForm.classList.remove('htmx-request');
        }
    }
});

document.body.addEventListener('htmx:responseError', function(event) {
    const form = event.detail.elt;
    if (form && (form.id === 'verify-form' || form.closest('#verify-form'))) {
        const indicator = document.getElementById('processing-indicator');
        if (indicator) {
            indicator.style.display = 'none';
        }
        const verifyForm = document.getElementById('verify-form');
        if (verifyForm) {
            verifyForm.classList.remove('htmx-request');
        }
    }
});

// Handle verification response
function handleVerifyResponse(event) {
    // Hide loading indicator
    const indicator = document.getElementById('processing-indicator');
    if (indicator) {
        indicator.style.display = 'none';
    }
    
    // Re-enable helper fields after submission
    const abvModeInputs = document.querySelectorAll('input[name="abv_mode"]');
    abvModeInputs.forEach(input => input.disabled = false);
    const volumeUnitInputs = document.querySelectorAll('input[name="volume_unit"]');
    volumeUnitInputs.forEach(input => input.disabled = false);
    const warningCheckbox = document.getElementById('warning');
    if (warningCheckbox) {
        warningCheckbox.disabled = false;
    }
    
    // Re-apply disabled state based on current radio selections
    const abvNARadio = document.getElementById('abv_na_radio');
    if (abvNARadio && abvNARadio.checked) {
        const abvInput = document.getElementById('abv');
        abvInput.disabled = true;
        abvInput.value = '';
    }
    
    const netContentsNARadio = document.getElementById('net_contents_na_radio');
    if (netContentsNARadio && netContentsNARadio.checked) {
        const netContentsInput = document.getElementById('net_contents');
        netContentsInput.disabled = true;
        netContentsInput.value = '';
    }
    
    // Restore original input values (remove units that were added for submission)
    const abvInput = document.getElementById('abv');
    const checkedAbvMode = document.querySelector('input[name="abv_mode"]:checked');
    const abvNA = checkedAbvMode && checkedAbvMode.value === 'na';
    
    if (!abvNA && originalAbvValue !== '') {
        abvInput.value = originalAbvValue;
        abvInput.disabled = false;
    } else if (abvNA) {
        abvInput.value = '';
        abvInput.disabled = true;
    }
    
    const netContentsInput = document.getElementById('net_contents');
    const checkedVolumeUnit = document.querySelector('input[name="volume_unit"]:checked');
    const netContentsNA = checkedVolumeUnit && checkedVolumeUnit.value === 'na';
    
    if (!netContentsNA && originalNetContentsValue !== '') {
        // Restore the original value (just the number, no units)
        netContentsInput.value = originalNetContentsValue;
        netContentsInput.disabled = false;
    } else if (netContentsNA) {
        // Keep empty and disabled when N/A is selected
        netContentsInput.value = '';
        netContentsInput.disabled = true;
    }
    
    if (event.detail.xhr && event.detail.xhr.status === 200) {
        let result;
        try {
            result = JSON.parse(event.detail.xhr.responseText);
        } catch (e) {
            console.error('Failed to parse response:', e);
            return;
        }
        currentVerificationResult = result;
        
        // Display results
        displayResults(result);
        
        // Load image and draw boxes
        if (currentImageFile) {
            loadImageAndDrawBoxes(currentImageFile, result);
        }
    } else if (event.detail.xhr && event.detail.xhr.status !== 200) {
        alert('Verification failed. Please try again.');
        console.error('Verification failed:', event.detail.xhr.status, event.detail.xhr.responseText);
    }
}

// Display results in the results panel
function displayResults(result) {
    const resultsPanel = document.getElementById('results-panel');
    
    const getStatusColor = (status) => {
        switch (status) {
            case 'pass': return '#4caf50';
            case 'fail': return '#f44336';
            case 'review': return '#ff9800';
            default: return '#666';
        }
    };
    
    const getResultColor = (result) => {
        switch (result) {
            case 'pass': return '#4caf50';
            case 'fail': return '#f44336';
            case 'review': return '#ff9800';
            default: return '#666';
        }
    };
    
    let html = `
        <section class="results-panel">
            <h2 style="color: #ffffff; margin-top: 0; margin-bottom: 20px;">Verification Results</h2>
            <div class="results-content">
                <div style="margin-bottom: 20px;">
                    <strong style="color: #ffffff;">Overall Status: </strong>
                    <span style="color: ${getStatusColor(result.status)}; font-weight: bold; text-transform: uppercase;">
                        ${result.status}
                    </span>
                </div>
                <h3 style="color: #ffffff; margin-bottom: 12px;">Field Checks</h3>
                <table style="width: 100%; border-collapse: collapse;">
                    <thead>
                        <tr>
                            <th style="border: 1px solid #ddd; padding: 8px; background-color: #455A64; color: #ffffff;">Field</th>
                            <th style="border: 1px solid #ddd; padding: 8px; background-color: #455A64; color: #ffffff;">Form Value</th>
                            <th style="border: 1px solid #ddd; padding: 8px; background-color: #455A64; color: #ffffff;">Label Value</th>
                            <th style="border: 1px solid #ddd; padding: 8px; background-color: #455A64; color: #ffffff;">Result</th>
                            <th style="border: 1px solid #ddd; padding: 8px; background-color: #455A64; color: #ffffff;">Notes</th>
                        </tr>
                    </thead>
                    <tbody>
    `;
    
    result.field_checks.forEach((check, index) => {
        const isActive = activeField === check.field;
        html += `
            <tr
                data-field="${check.field}"
                onmouseenter="setHoveredField('${check.field}')"
                onmouseleave="setHoveredField(null)"
                onclick="${check.field === 'brand' ? `setActiveField('${check.field}')` : ''}"
                style="cursor: ${check.field === 'brand' ? 'pointer' : 'default'}; background-color: ${isActive ? '#546E7A' : '#37474F'};"
            >
                <td style="border: 1px solid #ddd; padding: 8px; background-color: inherit; color: #ffffff;">${check.field}</td>
                <td style="border: 1px solid #ddd; padding: 8px; background-color: inherit; color: #ffffff;">${String(check.form_value)}</td>
                <td style="border: 1px solid #ddd; padding: 8px; background-color: inherit; color: #ffffff;">${String(check.label_value || '-')}</td>
                <td style="border: 1px solid #ddd; padding: 8px; background-color: inherit; color: #ffffff;">
                    <span style="color: ${getResultColor(check.result)}; font-weight: bold; text-transform: uppercase;">
                        ${check.result}
                    </span>
                </td>
                <td style="border: 1px solid #ddd; padding: 8px; background-color: inherit; color: #ffffff;">${check.notes || '-'}</td>
            </tr>
        `;
    });
    
    html += `
                    </tbody>
                </table>
            </div>
        </section>
    `;
    
    resultsPanel.innerHTML = html;
}

// Set hovered field
function setHoveredField(field) {
    hoveredField = field;
    if (currentVerificationResult && currentImageFile) {
        drawBoxes();
    }
}

// Set active field
function setActiveField(field) {
    activeField = field === activeField ? null : field;
    if (activeField === 'brand' && currentVerificationResult?.field_boxes?.brand?.boxes) {
        initializeEditableBox();
    } else {
        editableBox = null;
    }
    if (currentVerificationResult && currentImageFile) {
        drawBoxes();
        displayResults(currentVerificationResult);
    }
}

// Load image and draw boxes
function loadImageAndDrawBoxes(file, result) {
    const reader = new FileReader();
    reader.onload = function(e) {
        currentImageUrl = e.target.result;
        const img = new Image();
        img.onload = function() {
            const canvas = document.getElementById('label-canvas');
            const ctx = canvas.getContext('2d');
            
            // Set canvas size
            const maxWidth = 800;
            const scale = Math.min(maxWidth / img.width, 1);
            canvas.width = img.width * scale;
            canvas.height = img.height * scale;
            
            // Draw image
            ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
            
            // Store sizes
            imageSize = result.image_size || { width: img.width, height: img.height };
            displayedSize = { width: canvas.width, height: canvas.height };
            
            // Show viewer container
            const viewerContainer = document.getElementById('label-viewer-container');
            if (viewerContainer) {
                viewerContainer.style.display = 'block';
                // Ensure legend is visible
                const legend = document.getElementById('color-legend');
                if (legend) {
                    legend.style.display = 'block';
                }
            }
            
            // Update legend opacity based on which fields have boxes
            updateLegendOpacity(result);
            
            // Draw boxes
            drawBoxes();
        };
        img.src = currentImageUrl;
    };
    reader.readAsDataURL(file);
}

// Draw bounding boxes
function drawBoxes() {
    if (!currentVerificationResult?.field_boxes || !imageSize || !displayedSize) return;
    
    const svg = document.getElementById('label-overlay');
    svg.innerHTML = '';
    
    const scaleX = displayedSize.width / imageSize.width;
    const scaleY = displayedSize.height / imageSize.height;
    
    const fieldColors = {
        brand: '#ff9800',
        class_type: '#9c27b0',
        abv: '#4caf50',
        net_contents: '#2196f3',
        warning: '#f44336',
    };
    
    Object.entries(currentVerificationResult.field_boxes).forEach(([field, fieldBox]) => {
        if (!fieldBox?.boxes || fieldBox.boxes.length === 0) return;
        
        const isActive = activeField === field;
        const isHovered = hoveredField === field;
        const strokeColor = fieldColors[field] || '#ffffff';
        const strokeWidth = (isActive || isHovered) ? 3 : 2;
        
        fieldBox.boxes.forEach((bbox, idx) => {
            // Skip first box if it's the editable one
            if (isActive && idx === 0) return;
            
            const xs = bbox.map(p => p[0]);
            const ys = bbox.map(p => p[1]);
            
            const minX = Math.min(...xs);
            const maxX = Math.max(...xs);
            const minY = Math.min(...ys);
            const maxY = Math.max(...ys);
            
            const left = minX * scaleX;
            const top = minY * scaleY;
            const width = (maxX - minX) * scaleX;
            const height = (maxY - minY) * scaleY;
            
            const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
            rect.setAttribute('x', left);
            rect.setAttribute('y', top);
            rect.setAttribute('width', width);
            rect.setAttribute('height', height);
            rect.setAttribute('fill', strokeColor);
            rect.setAttribute('fill-opacity', '0.25');
            rect.setAttribute('stroke', strokeColor);
            rect.setAttribute('stroke-width', strokeWidth);
            svg.appendChild(rect);
        });
    });
    
    // Draw editable box if active
    if (editableBox && activeField === 'brand') {
        const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
        rect.setAttribute('x', editableBox.x);
        rect.setAttribute('y', editableBox.y);
        rect.setAttribute('width', editableBox.width);
        rect.setAttribute('height', editableBox.height);
        rect.setAttribute('fill', '#ff9800');
        rect.setAttribute('fill-opacity', '0.4');
        rect.setAttribute('stroke', '#ff9800');
        rect.setAttribute('stroke-width', '3');
        rect.setAttribute('stroke-dasharray', '5,5');
        svg.appendChild(rect);
        
        // Show adjust panel
        document.getElementById('field-adjust').style.display = 'block';
    } else {
        document.getElementById('field-adjust').style.display = 'none';
    }
}

// Initialize editable box
function initializeEditableBox() {
    if (activeField !== 'brand' || !currentVerificationResult?.field_boxes?.brand?.boxes || !imageSize || !displayedSize) return;
    
    const brandBoxes = currentVerificationResult.field_boxes.brand.boxes;
    if (brandBoxes.length === 0) return;
    
    const firstBox = brandBoxes[0];
    const scaleX = displayedSize.width / imageSize.width;
    const scaleY = displayedSize.height / imageSize.height;
    
    const xs = firstBox.map(p => p[0]);
    const ys = firstBox.map(p => p[1]);
    
    editableBox = {
        x: Math.min(...xs) * scaleX,
        y: Math.min(...ys) * scaleY,
        width: (Math.max(...xs) - Math.min(...xs)) * scaleX,
        height: (Math.max(...ys) - Math.min(...ys)) * scaleY,
    };
}

// Update legend opacity based on which fields have boxes
function updateLegendOpacity(result) {
    const legend = document.getElementById('color-legend');
    if (!legend) {
        console.warn('Legend element not found');
        return;
    }
    
    // Make sure legend is visible
    legend.style.display = 'block';
    
    if (!result?.field_boxes) {
        return;
    }
    
    // Get all legend items using data-field attribute
    const fieldOrder = ['brand', 'class_type', 'abv', 'net_contents', 'warning'];
    
    fieldOrder.forEach((field) => {
        const legendItem = legend.querySelector(`div[data-field="${field}"]`);
        if (legendItem) {
            const hasBoxes = result.field_boxes[field]?.boxes?.length > 0;
            legendItem.style.opacity = hasBoxes ? '1' : '0.5';
        }
    });
}

// Run self-test
async function runSelftest() {
    const spinner = document.getElementById('selftest-spinner');
    const resultDiv = document.getElementById('selftest-result');
    const btn = document.getElementById('selftest-btn');
    
    spinner.style.display = 'block';
    resultDiv.innerHTML = '';
    btn.disabled = true;
    
    try {
        const response = await fetch('/api/selftest/ocr');
        if (!response.ok) {
            throw new Error('Self-test request failed');
        }
        const result = await response.json();
        
        if (result.failed === 0) {
            alert(`OCR self-test passed: ${result.passed}/${result.total_cases} cases.`);
            resultDiv.innerHTML = `<div style="color: #4caf50; padding: 8px; background-color: #1B5E20; border-radius: 4px; margin-top: 10px;">
                ✓ OCR self-test passed: ${result.passed}/${result.total_cases} cases.
            </div>`;
        } else {
            const firstFailure = result.cases.find(c => !c.passed);
            const failedFields = firstFailure?.failed_fields.join(', ') || 'unknown';
            alert(
                `OCR self-test FAILED: ${result.failed}/${result.total_cases} cases failed.\n` +
                `First failure: ${firstFailure?.image || 'unknown'}, fields: ${failedFields}`
            );
            resultDiv.innerHTML = `<div style="color: #f44336; padding: 8px; background-color: #B71C1C; border-radius: 4px; margin-top: 10px;">
                ✗ OCR self-test FAILED: ${result.failed}/${result.total_cases} cases failed.<br>
                First failure: ${firstFailure?.image || 'unknown'}, fields: ${failedFields}
            </div>`;
        }
    } catch (error) {
        console.error('Self-test error:', error);
        alert('Failed to run self-test. Please check the console for details.');
        resultDiv.innerHTML = `<div style="color: #f44336; padding: 8px; background-color: #B71C1C; border-radius: 4px; margin-top: 10px;">
            Error: Failed to run self-test. Please check the console for details.
        </div>`;
    } finally {
        spinner.style.display = 'none';
        btn.disabled = false;
    }
}

// Initialize form state on page load
document.addEventListener('DOMContentLoaded', function() {
    // Set initial state based on default radio selections
    updateAbvMode();
    updateNetContentsMode();
});

// Re-OCR button handler
document.getElementById('reocr-btn')?.addEventListener('click', async function() {
    if (!editableBox || !currentImageFile || !currentVerificationResult) return;
    
    // Convert displayed coordinates back to image coordinates
    const scaleX = imageSize.width / displayedSize.width;
    const scaleY = imageSize.height / displayedSize.height;
    
    const bbox = [
        [editableBox.x * scaleX, editableBox.y * scaleY],
        [(editableBox.x + editableBox.width) * scaleX, editableBox.y * scaleY],
        [(editableBox.x + editableBox.width) * scaleX, (editableBox.y + editableBox.height) * scaleY],
        [editableBox.x * scaleX, (editableBox.y + editableBox.height) * scaleY],
    ];
    
    const formData = new FormData();
    formData.append('field', 'brand');
    formData.append('box', JSON.stringify(bbox));
    formData.append('image', currentImageFile);
    
    try {
        const response = await fetch('/api/verify/adjust_field', {
            method: 'POST',
            body: formData,
        });
        
        if (response.ok) {
            const result = await response.json();
            if (result.success && result.text) {
                // Update the result
                const fieldCheck = currentVerificationResult.field_checks.find(c => c.field === 'brand');
                if (fieldCheck) {
                    fieldCheck.label_value = result.text;
                }
                if (currentVerificationResult.field_boxes?.brand) {
                    currentVerificationResult.field_boxes.brand.text = result.text;
                }
                displayResults(currentVerificationResult);
                setActiveField(null);
            }
        }
    } catch (error) {
        console.error('Re-OCR failed:', error);
        alert('Failed to re-OCR region. Please try again.');
    }
});

