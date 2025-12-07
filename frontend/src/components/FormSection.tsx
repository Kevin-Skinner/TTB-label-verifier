import React, { useState, FormEvent } from 'react'
import { VerifyFormData } from '../api/verifyClient'
import { VerifyResponse } from '../types/verify'

interface FormSectionProps {
  onVerify: (result: VerifyResponse, imageFile: File) => void
}

const FormSection: React.FC<FormSectionProps> = ({ onVerify }) => {
  const [brand, setBrand] = useState('')
  const [classType, setClassType] = useState('N/A')
  const [abv, setAbv] = useState('')
  const [abvMode, setAbvMode] = useState<'%' | 'decimal'>('%')
  const [abvNA, setAbvNA] = useState(false)
  const [netContents, setNetContents] = useState('')
  const [volumeUnit, setVolumeUnit] = useState<'ml' | 'oz'>('ml')
  const [netContentsNA, setNetContentsNA] = useState(false)
  const [warningClaimed, setWarningClaimed] = useState(false)
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [verificationStatus, setVerificationStatus] = useState<'idle' | 'processing' | 'complete'>('idle')

  const handleFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    if (event.target.files && event.target.files[0]) {
      setSelectedFile(event.target.files[0])
    }
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    
    if (!selectedFile) {
      alert('Please select an image file')
      return
    }

    setIsSubmitting(true)
    setVerificationStatus('processing')

    try {
      const { verifyLabel } = await import('../api/verifyClient')
      
      // Handle ABV: if N/A is checked, send "n/a", otherwise convert based on mode
      let abvValue: number | string = 'n/a'
      if (!abvNA) {
        abvValue = parseFloat(abv) || 0
        if (abvMode === 'decimal') {
          // Validate decimal mode: values should be between 0 and 1
          if (abvValue < 0 || abvValue > 1) {
            alert('Decimal mode requires a value between 0 and 1 (e.g., 0.145 for 14.5%)')
            setIsSubmitting(false)
            setVerificationStatus('idle')
            return
          }
          abvValue = abvValue * 100
        }
      }
      
      // Handle net contents: if N/A is checked, send "n/a", otherwise compose with unit
      const netContentsValue = netContentsNA ? 'n/a' : `${netContents} ${volumeUnit}`
      
      const formData: VerifyFormData = {
        brand,
        class_type: classType,
        abv: abvValue,
        net_contents: netContentsValue,
        warning_claimed: warningClaimed,
        image: selectedFile,
      }

      const result = await verifyLabel(formData)
      setVerificationStatus('complete')
      onVerify(result, selectedFile)
      // Reset status after a brief delay to show completion
      setTimeout(() => setVerificationStatus('idle'), 500)
    } catch (error) {
      console.error('Verification failed:', error)
      alert('Verification failed. Please try again.')
      setVerificationStatus('idle')
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <section className="form-section">
      <h2 style={{ color: '#ffffff', marginTop: '0', marginBottom: '20px' }}>Upload Label</h2>
      <form onSubmit={handleSubmit}>
        <div style={{ marginBottom: '14px' }}>
          <label htmlFor="brand" style={{ display: 'block', marginBottom: '6px', color: '#ffffff' }}>Brand:</label>
          <input
            id="brand"
            type="text"
            value={brand}
            onChange={(e) => setBrand(e.target.value)}
            required
            className="input-wide"
          />
        </div>
        
        <div style={{ marginBottom: '14px' }}>
          <label htmlFor="class_type" style={{ display: 'block', marginBottom: '6px', color: '#ffffff' }}>Class/Type:</label>
          <select
            id="class_type"
            value={classType}
            onChange={(e) => setClassType(e.target.value)}
            required
            className="input-wide"
          >
            <option value="Distilled Spirits">Distilled Spirits</option>
            <option value="Wine">Wine</option>
            <option value="Malt Beverages">Malt Beverages</option>
            <option value="N/A">N/A</option>
          </select>
        </div>
        
        <div style={{ marginBottom: '14px' }}>
          <label htmlFor="abv" style={{ display: 'block', marginBottom: '6px', color: '#ffffff' }}>ABV:</label>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
            <input
              id="abv"
              type="number"
              step="0.1"
              value={abv}
              onChange={(e) => setAbv(e.target.value)}
              disabled={abvNA}
              required={!abvNA}
              className="input-wide"
              style={{ marginBottom: '0', opacity: abvNA ? 0.5 : 1, backgroundColor: abvNA ? '#f0f0f0' : 'white' }}
            />
            <label style={{ display: 'flex', alignItems: 'center', gap: '5px', cursor: 'pointer', color: '#ffffff' }}>
              <input
                type="checkbox"
                checked={abvMode === '%'}
                onChange={() => setAbvMode('%')}
                disabled={abvNA}
              />
              %
            </label>
            <label style={{ display: 'flex', alignItems: 'center', gap: '5px', cursor: 'pointer', color: '#ffffff' }}>
              <input
                type="checkbox"
                checked={abvMode === 'decimal'}
                onChange={() => setAbvMode('decimal')}
                disabled={abvNA}
              />
              Decimal
            </label>
            <label style={{ display: 'flex', alignItems: 'center', gap: '5px', cursor: 'pointer', color: '#ffffff' }}>
              <input
                type="checkbox"
                checked={abvNA}
                onChange={(e) => {
                  setAbvNA(e.target.checked)
                  if (e.target.checked) {
                    setAbv('')
                  }
                }}
              />
              N/A
            </label>
          </div>
        </div>
        
        <div style={{ marginBottom: '14px' }}>
          <label htmlFor="net_contents" style={{ display: 'block', marginBottom: '6px', color: '#ffffff' }}>Net Contents:</label>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
            <input
              id="net_contents"
              type="text"
              value={netContents}
              onChange={(e) => {
                const value = e.target.value
                // Only allow numbers and a single decimal point
                const filtered = value.replace(/[^0-9.]/g, '')
                // Ensure only one decimal point
                const parts = filtered.split('.')
                const sanitized = parts.length > 2 
                  ? parts[0] + '.' + parts.slice(1).join('')
                  : filtered
                setNetContents(sanitized)
              }}
              placeholder="e.g., 750"
              disabled={netContentsNA}
              required={!netContentsNA}
              className="input-wide"
              style={{ marginBottom: '0', opacity: netContentsNA ? 0.5 : 1, backgroundColor: netContentsNA ? '#f0f0f0' : 'white' }}
            />
            <label style={{ display: 'flex', alignItems: 'center', gap: '5px', cursor: 'pointer', color: '#ffffff' }}>
              <input
                type="checkbox"
                checked={volumeUnit === 'ml'}
                onChange={() => setVolumeUnit('ml')}
                disabled={netContentsNA}
              />
              mL
            </label>
            <label style={{ display: 'flex', alignItems: 'center', gap: '5px', cursor: 'pointer', color: '#ffffff' }}>
              <input
                type="checkbox"
                checked={volumeUnit === 'oz'}
                onChange={() => setVolumeUnit('oz')}
                disabled={netContentsNA}
              />
              oz
            </label>
            <label style={{ display: 'flex', alignItems: 'center', gap: '5px', cursor: 'pointer', color: '#ffffff' }}>
              <input
                type="checkbox"
                checked={netContentsNA}
                onChange={(e) => {
                  setNetContentsNA(e.target.checked)
                  if (e.target.checked) {
                    setNetContents('')
                  }
                }}
              />
              N/A
            </label>
          </div>
        </div>
        
        <div style={{ marginBottom: '14px' }}>
          <label htmlFor="warning" style={{ display: 'flex', alignItems: 'center', gap: '5px', cursor: 'pointer', color: '#ffffff' }}>
            <input
              id="warning"
              type="checkbox"
              checked={warningClaimed}
              onChange={(e) => setWarningClaimed(e.target.checked)}
            />
            Warning Present
          </label>
        </div>
        
        <div style={{ marginBottom: '14px' }}>
          <label htmlFor="image" style={{ display: 'block', marginBottom: '6px', color: '#ffffff' }}>Image:</label>
          <input
            id="image"
            type="file"
            accept="image/*"
            onChange={handleFileChange}
            required
            style={{ marginBottom: '8px' }}
          />
          {selectedFile && <p style={{ color: '#ffffff', marginTop: '8px', marginBottom: '0' }}>Selected: {selectedFile.name}</p>}
        </div>
        
        <div style={{ display: 'flex', alignItems: 'center', gap: '15px', marginTop: '10px', flexWrap: 'wrap' }}>
          <button 
            type="submit" 
            disabled={isSubmitting}
            style={{
              padding: '10px 20px',
              fontSize: '16px',
              cursor: isSubmitting ? 'not-allowed' : 'pointer',
            }}
          >
            {isSubmitting ? 'Verifying...' : 'Verify Label'}
          </button>
          
          {verificationStatus === 'processing' && (
            <div style={{ 
              display: 'flex', 
              alignItems: 'center', 
              gap: '10px',
              padding: '8px 12px',
              backgroundColor: '#455A64',
              borderRadius: '4px',
              color: '#ffffff'
            }}>
              <div style={{
                width: '16px',
                height: '16px',
                border: '2px solid #ffffff',
                borderTop: '2px solid transparent',
                borderRadius: '50%',
                animation: 'spin 1s linear infinite'
              }}></div>
              <span>Processing image and verifying label...</span>
            </div>
          )}
        </div>
      </form>
    </section>
  )
}

export default FormSection

