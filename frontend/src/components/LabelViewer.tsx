import React, { useState, useRef, useEffect } from 'react'
import { VerifyResponse } from '../types/verify'

interface SelftestResponse {
  total_cases: number
  passed: number
  failed: number
  cases: Array<{
    image: string
    passed: boolean
    failed_fields: string[]
  }>
}

type TestStatus = 'idle' | 'running' | 'complete' | 'error'

interface LabelViewerProps {
  imageFile: File | null
  verificationResult: VerifyResponse | null
  hoveredField?: string | null
  activeField?: string | null
  onFieldHover?: (field: string | null) => void
  onFieldClick?: (field: string) => void
  onFieldAdjust?: (field: string, newText: string) => void
  testStatus?: TestStatus
  testSummary?: SelftestResponse | null
  testError?: string | null
}

const LabelViewer: React.FC<LabelViewerProps> = ({
  imageFile,
  verificationResult,
  hoveredField: externalHoveredField,
  activeField: externalActiveField,
  onFieldHover,
  onFieldClick,
  onFieldAdjust,
  testStatus = 'idle',
  testSummary = null,
  testError = null,
}) => {
  const [imageUrl, setImageUrl] = useState<string | null>(null)
  const [imageSize, setImageSize] = useState<{ width: number; height: number } | null>(null)
  const [displayedSize, setDisplayedSize] = useState<{ width: number; height: number } | null>(null)
  const [editableBox, setEditableBox] = useState<{ x: number; y: number; width: number; height: number } | null>(null)
  const [isDragging, setIsDragging] = useState(false)
  const [isResizing, setIsResizing] = useState(false)
  const [dragStart, setDragStart] = useState<{ x: number; y: number } | null>(null)
  const [resizeHandle, setResizeHandle] = useState<string | null>(null)
  const imageRef = useRef<HTMLImageElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)

  // Create object URL from file
  useEffect(() => {
    if (imageFile) {
      const url = URL.createObjectURL(imageFile)
      setImageUrl(url)
      return () => URL.revokeObjectURL(url)
    } else {
      setImageUrl(null)
      setImageSize(null)
      setDisplayedSize(null)
      setEditableBox(null)
    }
  }, [imageFile])

  // Get image dimensions when loaded
  const handleImageLoad = () => {
    if (imageRef.current && containerRef.current) {
      const img = imageRef.current
      const container = containerRef.current
      
      // Wait a tick for layout to settle
      requestAnimationFrame(() => {
        if (!imageRef.current || !containerRef.current) return
        
        // Get natural dimensions
        const natural = { 
          width: imageRef.current.naturalWidth, 
          height: imageRef.current.naturalHeight 
        }
        
        // Calculate displayed size based on actual rendered dimensions
        const rect = imageRef.current.getBoundingClientRect()
        const displayed = { width: rect.width, height: rect.height }
        
        // Get original size from verification result or image natural size
        let originalSize = displayed
        if (verificationResult?.image_size) {
          originalSize = verificationResult.image_size
        } else if (natural.width && natural.height) {
          originalSize = natural
        }
        
        setImageSize(originalSize)
        setDisplayedSize(displayed)
        
        console.log('Image loaded:', {
          naturalSize: natural,
          displayedSize: displayed,
          imageSize: originalSize,
          aspectRatioNatural: natural.width && natural.height ? (natural.width / natural.height).toFixed(3) : 'N/A',
          aspectRatioDisplayed: displayed.width && displayed.height ? (displayed.width / displayed.height).toFixed(3) : 'N/A',
          aspectRatioImageSize: originalSize.width && originalSize.height ? (originalSize.width / originalSize.height).toFixed(3) : 'N/A',
          scaleX: displayed.width / originalSize.width,
          scaleY: displayed.height / originalSize.height,
        })
      })
    }
  }

  // Update imageSize when verificationResult changes (in case result arrives after image loads)
  useEffect(() => {
    if (verificationResult?.image_size && !imageSize) {
      setImageSize(verificationResult.image_size)
    }
  }, [verificationResult, imageSize])

  // Recalculate displayed size on window resize
  useEffect(() => {
    const handleResize = () => {
      if (imageRef.current) {
        const rect = imageRef.current.getBoundingClientRect()
        setDisplayedSize({ width: rect.width, height: rect.height })
      }
    }
    
    window.addEventListener('resize', handleResize)
    return () => window.removeEventListener('resize', handleResize)
  }, [])

  // Initialize editable box when brand field is activated
  useEffect(() => {
    if (externalActiveField === 'brand' && verificationResult?.field_boxes?.brand?.boxes && imageSize && displayedSize) {
      const brandBoxes = verificationResult.field_boxes.brand.boxes
      if (brandBoxes.length > 0) {
        const firstBox = brandBoxes[0]
        const scaleX = displayedSize.width / imageSize.width
        const scaleY = displayedSize.height / imageSize.height
        
        const xs = firstBox.map(p => p[0])
        const ys = firstBox.map(p => p[1])
        const left = Math.min(...xs) * scaleX
        const top = Math.min(...ys) * scaleY
        const width = (Math.max(...xs) - Math.min(...xs)) * scaleX
        const height = (Math.max(...ys) - Math.min(...ys)) * scaleY
        
        setEditableBox({ x: left, y: top, width, height })
      }
    } else if (externalActiveField !== 'brand') {
      setEditableBox(null)
    }
  }, [externalActiveField, verificationResult, imageSize, displayedSize])

  // Only render if we have image URL
  if (!imageUrl) {
    return null
  }
  
  // Debug: log what we have (only once per render cycle)
  if (imageUrl && verificationResult?.field_boxes && imageSize && displayedSize) {
    console.log('LabelViewer render check:', {
      hasImageUrl: !!imageUrl,
      hasVerificationResult: !!verificationResult,
      hasFieldBoxes: !!verificationResult?.field_boxes,
      fieldBoxes: verificationResult?.field_boxes,
      hasImageSize: !!imageSize,
      imageSize,
      hasDisplayedSize: !!displayedSize,
      displayedSize,
      scaleX: displayedSize.width / imageSize.width,
      scaleY: displayedSize.height / imageSize.height,
    })
  }
  
  // Calculate scale factors - use defaults if sizes not available yet
  const scaleX = (imageSize && displayedSize) ? displayedSize.width / imageSize.width : 1
  const scaleY = (imageSize && displayedSize) ? displayedSize.height / imageSize.height : 1
  
  // Only render boxes if we have field_boxes and both sizes
  const hasBoxData = verificationResult?.field_boxes && imageSize && displayedSize

  const fieldColors: Record<string, string> = {
    brand: '#ff9800',
    class_type: '#9c27b0', // Purple for class/type
    abv: '#4caf50',
    net_contents: '#2196f3',
    warning: '#f44336',
  }

  const fieldLabels: Record<string, string> = {
    brand: 'Brand',
    class_type: 'Class/Type',
    abv: 'ABV',
    net_contents: 'Net Contents',
    warning: 'Warning',
  }

  // Helper function to convert hex to rgba
  const hexToRgba = (hex: string, alpha: number) => {
    const r = parseInt(hex.slice(1, 3), 16)
    const g = parseInt(hex.slice(3, 5), 16)
    const b = parseInt(hex.slice(5, 7), 16)
    return `rgba(${r}, ${g}, ${b}, ${alpha})`
  }

  const renderBoxes = () => {
    if (!hasBoxData) return []
    
    const boxes: JSX.Element[] = []
    
    Object.entries(verificationResult!.field_boxes!).forEach(([field, fieldBox]) => {
      if (!fieldBox?.boxes || fieldBox.boxes.length === 0) return
      
      const isActive = externalActiveField === field
      const isHovered = externalHoveredField === field
      const strokeColor = fieldColors[field] || '#ffffff'
      const strokeWidth = (isActive || isHovered) ? 3 : 2
      
      fieldBox.boxes.forEach((bbox, idx) => {
        // Bbox format: [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
        // Extract all x and y coordinates
        const xs = bbox.map(p => p[0])
        const ys = bbox.map(p => p[1])
        
        // Calculate bounding rectangle
        const minX = Math.min(...xs)
        const maxX = Math.max(...xs)
        const minY = Math.min(...ys)
        const maxY = Math.max(...ys)
        
        // Scale to displayed coordinates
        const left = minX * scaleX
        const top = minY * scaleY
        const width = (maxX - minX) * scaleX
        const height = (maxY - minY) * scaleY
        
        // Debug first box of each field
        if (idx === 0) {
          console.log(`Box for ${field}:`, {
            originalBbox: bbox,
            bboxCoords: { minX, maxX, minY, maxY },
            imageSize,
            displayedSize,
            scaleX,
            scaleY,
            calculated: { left, top, width, height },
            // Check if coordinates seem reasonable
            xRange: maxX - minX,
            yRange: maxY - minY,
            xPercent: (minX / imageSize.width * 100).toFixed(1) + '%',
            yPercent: (minY / imageSize.height * 100).toFixed(1) + '%',
          })
        }
        
        // Skip if this is the editable box (we'll render it separately)
        if (isActive && idx === 0) return
        
        boxes.push(
          <rect
            key={`${field}-${idx}`}
            data-field={field}
            x={left}
            y={top}
            width={width}
            height={height}
            fill={hexToRgba(strokeColor, 0.25)}
            stroke={strokeColor}
            strokeWidth={strokeWidth}
            style={{ pointerEvents: 'none' }}
          />
        )
      })
    })
    
    return boxes
  }

  const handleMouseDown = (e: React.MouseEvent, type: 'drag' | 'resize', handle?: string) => {
    if (!editableBox) return
    
    e.preventDefault()
    e.stopPropagation()
    
    if (type === 'drag') {
      setIsDragging(true)
      setDragStart({ x: e.clientX, y: e.clientY })
    } else if (type === 'resize' && handle) {
      setIsResizing(true)
      setResizeHandle(handle)
      setDragStart({ x: e.clientX, y: e.clientY })
    }
  }

  const handleMouseMove = (e: React.MouseEvent) => {
    if (!editableBox || !dragStart || !imageSize || !displayedSize) return
    
    const deltaX = (e.clientX - dragStart.x)
    const deltaY = (e.clientY - dragStart.y)
    
    if (isDragging) {
      const newX = Math.max(0, Math.min(displayedSize.width - editableBox.width, editableBox.x + deltaX))
      const newY = Math.max(0, Math.min(displayedSize.height - editableBox.height, editableBox.y + deltaY))
      setEditableBox({
        ...editableBox,
        x: newX,
        y: newY,
      })
      setDragStart({ x: e.clientX, y: e.clientY })
    } else if (isResizing && resizeHandle) {
      let newBox = { ...editableBox }
      
      if (resizeHandle.includes('n')) {
        const newH = editableBox.height - deltaY
        const newY = editableBox.y + deltaY
        if (newH > 10 && newY >= 0) {
          newBox.height = newH
          newBox.y = newY
        }
      }
      if (resizeHandle.includes('s')) {
        const newH = editableBox.height + deltaY
        if (newH > 10 && editableBox.y + newH <= displayedSize.height) {
          newBox.height = newH
        }
      }
      if (resizeHandle.includes('w')) {
        const newW = editableBox.width - deltaX
        const newX = editableBox.x + deltaX
        if (newW > 10 && newX >= 0) {
          newBox.width = newW
          newBox.x = newX
        }
      }
      if (resizeHandle.includes('e')) {
        const newW = editableBox.width + deltaX
        if (newW > 10 && editableBox.x + newW <= displayedSize.width) {
          newBox.width = newW
        }
      }
      
      setEditableBox(newBox)
      setDragStart({ x: e.clientX, y: e.clientY })
    }
  }

  const handleMouseUp = () => {
    setIsDragging(false)
    setIsResizing(false)
    setDragStart(null)
    setResizeHandle(null)
  }

  const handleApplyAdjustment = async () => {
    if (!editableBox || !imageFile || !imageSize || !displayedSize || externalActiveField !== 'brand') return
    
    // Convert displayed coordinates back to image coordinates
    const scaleX = displayedSize.width / imageSize.width
    const scaleY = displayedSize.height / imageSize.height
    
    const x = editableBox.x / scaleX
    const y = editableBox.y / scaleY
    const width = editableBox.width / scaleX
    const height = editableBox.height / scaleY
    
    // Build bbox in image coordinates
    const box = [
      [x, y],
      [x + width, y],
      [x + width, y + height],
      [x, y + height],
    ]
    
    // Prepare form data
    const formData = new FormData()
    formData.append('image', imageFile)
    formData.append('field', 'brand')
    formData.append('box', JSON.stringify(box))
    
    try {
      const response = await fetch('/api/verify/adjust_field', {
        method: 'POST',
        body: formData,
      })
      
      if (!response.ok) {
        throw new Error('Adjustment request failed')
      }
      
      const result = await response.json()
      
      if (result.success && result.text && onFieldAdjust) {
        onFieldAdjust('brand', result.text)
      } else {
        alert('Failed to extract text from adjusted region')
      }
    } catch (error) {
      console.error('Error applying adjustment:', error)
      alert('Failed to apply adjustment. Please try again.')
    }
  }

  return (
    <div style={{ marginTop: '24px', display: 'flex', justifyContent: 'center', gap: '24px', flexWrap: 'wrap' }}>
      <div style={{ maxWidth: '600px', width: '100%', flex: '1 1 600px' }}>
        <h3 style={{ color: '#ffffff', marginBottom: '16px' }}>Label View</h3>
        <div
          ref={containerRef}
          style={{ 
            position: 'relative', 
            width: '100%',
            display: 'inline-block' // Ensure container fits image exactly
          }}
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
          onMouseLeave={handleMouseUp}
        >
          <img
            ref={imageRef}
            src={imageUrl || ''}
            alt="Label"
            style={{ 
              width: '100%', 
              height: 'auto', 
              display: 'block',
              maxWidth: '100%'
            }}
            onLoad={handleImageLoad}
            onError={(e) => {
              console.error('Image load error:', e)
            }}
          />
          {displayedSize && imageSize && (
            <svg
              style={{
                position: 'absolute',
                top: 0,
                left: 0,
                width: `${displayedSize.width}px`,
                height: `${displayedSize.height}px`,
                pointerEvents: externalActiveField ? 'auto' : 'none',
              }}
              viewBox={`0 0 ${displayedSize.width} ${displayedSize.height}`}
            >
            {hasBoxData && renderBoxes()}
            {editableBox && externalActiveField === 'brand' && (
              <>
                <rect
                  x={editableBox.x}
                  y={editableBox.y}
                  width={editableBox.width}
                  height={editableBox.height}
                  fill="rgba(255, 152, 0, 0.1)"
                  stroke="#ff9800"
                  strokeWidth={3}
                  style={{ cursor: isDragging ? 'move' : 'default' }}
                  onMouseDown={(e) => handleMouseDown(e, 'drag')}
                />
                {/* Resize handles */}
                {['nw', 'ne', 'sw', 'se'].map((handle) => {
                  const positions: Record<string, { x: number; y: number }> = {
                    nw: { x: editableBox.x, y: editableBox.y },
                    ne: { x: editableBox.x + editableBox.width, y: editableBox.y },
                    sw: { x: editableBox.x, y: editableBox.y + editableBox.height },
                    se: { x: editableBox.x + editableBox.width, y: editableBox.y + editableBox.height },
                  }
                  const pos = positions[handle]
                  return (
                    <circle
                      key={handle}
                      cx={pos.x}
                      cy={pos.y}
                      r={6}
                      fill="#ff9800"
                      stroke="#ffffff"
                      strokeWidth={2}
                      style={{ cursor: `${handle}-resize` }}
                      onMouseDown={(e) => handleMouseDown(e, 'resize', handle)}
                    />
                  )
                })}
              </>
            )}
            </svg>
          )}
        </div>
        {externalActiveField === 'brand' && (
          <div style={{ marginTop: '12px', textAlign: 'center' }}>
            <button
              onClick={handleApplyAdjustment}
              style={{
                padding: '8px 16px',
                fontSize: '14px',
                cursor: 'pointer',
                backgroundColor: '#455A64',
                color: '#ffffff',
                border: '1px solid #546E7A',
                borderRadius: '4px',
              }}
            >
              Apply Brand Adjustment
            </button>
          </div>
        )}
      </div>
      
      {/* Color Legend and Test Box Container */}
      <div style={{ 
        minWidth: '200px', 
        flex: '0 0 200px',
        display: 'flex',
        flexDirection: 'column',
        gap: '0'
      }}>
        {/* Color Legend */}
        <div style={{ 
          backgroundColor: '#37474F',
          padding: '16px',
          borderRadius: '4px',
          height: 'fit-content'
        }}>
        <h4 style={{ color: '#ffffff', marginTop: '0', marginBottom: '12px', fontSize: '16px' }}>Legend</h4>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          {Object.entries(fieldColors).map(([field, color]) => {
            const label = fieldLabels[field] || field
            const hasBoxes = verificationResult?.field_boxes?.[field]?.boxes?.length > 0
            return (
              <div 
                key={field}
                style={{ 
                  display: 'flex', 
                  alignItems: 'center', 
                  gap: '8px',
                  opacity: hasBoxes ? 1 : 0.5
                }}
              >
                <div
                  style={{
                    width: '20px',
                    height: '20px',
                    backgroundColor: hexToRgba(color, 0.25),
                    border: `2px solid ${color}`,
                    borderRadius: '2px',
                    flexShrink: 0
                  }}
                />
                <span style={{ color: '#ffffff', fontSize: '14px' }}>{label}</span>
              </div>
            )
          })}
        </div>
        </div>
        
        {/* Test Progress Box - shown below the legend */}
        {testStatus !== 'idle' && (
          <div style={{
            marginTop: '24px',
            backgroundColor: '#37474F',
            padding: '20px',
            borderRadius: '8px',
            color: '#ffffff'
          }}>
            <h4 style={{ marginTop: '0', marginBottom: '16px', color: '#ffffff', fontSize: '16px' }}>
              Automated OCR Tests
            </h4>
            
            {testStatus === 'running' && (
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                <div style={{
                  border: '4px solid rgba(255, 255, 255, 0.3)',
                  borderTop: '4px solid #ffffff',
                  borderRadius: '50%',
                  width: '24px',
                  height: '24px',
                  animation: 'spin 1s linear infinite'
                }}></div>
                <span>Running automated tests...</span>
              </div>
            )}
            
            {testStatus === 'complete' && testSummary && (
              <div>
                <div style={{ 
                  marginBottom: '12px',
                  padding: '12px',
                  backgroundColor: testSummary.failed === 0 ? '#2E7D32' : '#C62828',
                  borderRadius: '4px'
                }}>
                  <strong>
                    {testSummary.failed === 0 ? '✓ All Tests Passed' : '✗ Tests Failed'}
                  </strong>
                  <div style={{ marginTop: '8px' }}>
                    Passed: {testSummary.passed} / {testSummary.total_cases}
                    {testSummary.failed > 0 && (
                      <span style={{ marginLeft: '12px' }}>
                        Failed: {testSummary.failed}
                      </span>
                    )}
                  </div>
                </div>
                
                {testSummary.failed > 0 && (
                  <div style={{ marginTop: '12px' }}>
                    <strong>Failed Cases:</strong>
                    <ul style={{ marginTop: '8px', paddingLeft: '20px' }}>
                      {testSummary.cases
                        .filter(c => !c.passed)
                        .slice(0, 5) // Show first 5 failures
                        .map((c, idx) => (
                          <li key={idx} style={{ marginBottom: '4px' }}>
                            {c.image}
                            {c.failed_fields.length > 0 && (
                              <span style={{ color: '#FFB74D', marginLeft: '8px' }}>
                                ({c.failed_fields.join(', ')})
                              </span>
                            )}
                          </li>
                        ))}
                    </ul>
                  </div>
                )}
              </div>
            )}
            
            {testStatus === 'error' && testError && (
              <div style={{
                padding: '12px',
                backgroundColor: '#C62828',
                borderRadius: '4px'
              }}>
                <strong>Error:</strong> {testError}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

export default LabelViewer

