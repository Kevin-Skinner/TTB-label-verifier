import React, { useState, FormEvent } from 'react'
import { VerifyFormData } from '../api/verifyClient'
import { VerifyResponse } from '../types/verify'

interface FormSectionProps {
  onVerify: (result: VerifyResponse) => void
}

const FormSection: React.FC<FormSectionProps> = ({ onVerify }) => {
  const [brand, setBrand] = useState('')
  const [classType, setClassType] = useState('')
  const [abv, setAbv] = useState('')
  const [netContents, setNetContents] = useState('')
  const [warningClaimed, setWarningClaimed] = useState(false)
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)

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

    try {
      const { verifyLabel } = await import('../api/verifyClient')
      const formData: VerifyFormData = {
        brand,
        class_type: classType,
        abv: parseFloat(abv) || 0,
        net_contents: netContents,
        warning_claimed: warningClaimed,
        image: selectedFile,
      }

      const result = await verifyLabel(formData)
      onVerify(result)
    } catch (error) {
      console.error('Verification failed:', error)
      alert('Verification failed. Please try again.')
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <section className="form-section">
      <h2>Upload Label</h2>
      <form onSubmit={handleSubmit}>
        <div>
          <label htmlFor="brand">Brand:</label>
          <input
            id="brand"
            type="text"
            value={brand}
            onChange={(e) => setBrand(e.target.value)}
            required
          />
        </div>
        
        <div>
          <label htmlFor="class_type">Class/Type:</label>
          <input
            id="class_type"
            type="text"
            value={classType}
            onChange={(e) => setClassType(e.target.value)}
            required
          />
        </div>
        
        <div>
          <label htmlFor="abv">ABV (%):</label>
          <input
            id="abv"
            type="number"
            step="0.1"
            value={abv}
            onChange={(e) => setAbv(e.target.value)}
            required
          />
        </div>
        
        <div>
          <label htmlFor="net_contents">Net Contents:</label>
          <input
            id="net_contents"
            type="text"
            value={netContents}
            onChange={(e) => setNetContents(e.target.value)}
            placeholder="e.g., 750 ml"
            required
          />
        </div>
        
        <div>
          <label htmlFor="warning">
            <input
              id="warning"
              type="checkbox"
              checked={warningClaimed}
              onChange={(e) => setWarningClaimed(e.target.checked)}
            />
            Warning Present
          </label>
        </div>
        
        <div>
          <label htmlFor="image">Image:</label>
          <input
            id="image"
            type="file"
            accept="image/*"
            onChange={handleFileChange}
            required
          />
          {selectedFile && <p>Selected: {selectedFile.name}</p>}
        </div>
        
        <button type="submit" disabled={isSubmitting}>
          {isSubmitting ? 'Verifying...' : 'Verify Label'}
        </button>
      </form>
    </section>
  )
}

export default FormSection

