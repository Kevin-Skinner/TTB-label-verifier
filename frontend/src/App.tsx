import React, { useState } from 'react'
import FormSection from './components/FormSection'
import ResultsPanel from './components/ResultsPanel'
import LabelViewer from './components/LabelViewer'
import { VerifyResponse } from './types/verify'
import { SHOW_AUTOMATED_TESTS } from './config'

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

function App() {
  const [verificationResult, setVerificationResult] = useState<VerifyResponse | null>(null)
  const [imageFile, setImageFile] = useState<File | null>(null)
  const [hoveredField, setHoveredField] = useState<string | null>(null)
  const [activeField, setActiveField] = useState<string | null>(null)
  const [testStatus, setTestStatus] = useState<TestStatus>('idle')
  const [testSummary, setTestSummary] = useState<SelftestResponse | null>(null)
  const [testError, setTestError] = useState<string | null>(null)

  const handleVerify = (result: VerifyResponse, file: File) => {
    setVerificationResult(result)
    setImageFile(file)
    setActiveField(null) // Clear active field when new verification runs
    // Clear test progress box when verify label is run
    setTestStatus('idle')
    setTestSummary(null)
    setTestError(null)
  }

  const handleFieldAdjust = (field: string, newText: string) => {
    if (!verificationResult) return
    
    // Update the field_checks with new label_value
    const updatedFieldChecks = verificationResult.field_checks.map(check => {
      if (check.field === field) {
        return { ...check, label_value: newText }
      }
      return check
    })
    
    // Update field_boxes if needed
    const updatedFieldBoxes = { ...verificationResult.field_boxes }
    if (updatedFieldBoxes && updatedFieldBoxes[field as keyof typeof updatedFieldBoxes]) {
      updatedFieldBoxes[field as keyof typeof updatedFieldBoxes] = {
        ...updatedFieldBoxes[field as keyof typeof updatedFieldBoxes],
        text: newText,
      }
    }
    
    setVerificationResult({
      ...verificationResult,
      field_checks: updatedFieldChecks,
      field_boxes: updatedFieldBoxes,
    })
    
    // Clear active field after adjustment
    setActiveField(null)
  }

  const handleRunSelftest = async () => {
    setTestStatus('running')
    setTestSummary(null)
    setTestError(null)
    
    try {
      const response = await fetch('/api/selftest/ocr')
      if (!response.ok) {
        throw new Error('Self-test request failed')
      }
      const summary: SelftestResponse = await response.json()
      setTestSummary(summary)
      setTestStatus('complete')
      
      // Also show alert for quick feedback
      if (summary.failed === 0) {
        window.alert(`OCR self-test passed: ${summary.passed}/${summary.total_cases} cases.`)
      } else {
        const firstFailure = summary.cases.find(c => !c.passed)
        const failedFields = firstFailure?.failed_fields.join(', ') || 'unknown'
        window.alert(
          `OCR self-test FAILED: ${summary.failed}/${summary.total_cases} cases failed.\n` +
          `First failure: ${firstFailure?.image || 'unknown'}, fields: ${failedFields}`
        )
      }
    } catch (error) {
      console.error('Self-test error:', error)
      const errorMessage = error instanceof Error ? error.message : 'Failed to run self-test. Please check the console for details.'
      setTestError(errorMessage)
      setTestStatus('error')
      window.alert('Failed to run self-test. Please check the console for details.')
    }
  }

  return (
    <div className="app" style={{ maxWidth: '1200px', margin: '0 auto', padding: '20px' }}>
      <header style={{ marginBottom: '30px', color: '#ffffff', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h1 style={{ margin: 0 }}>TTB Label Verifier</h1>
        {SHOW_AUTOMATED_TESTS && (
          <button
            onClick={handleRunSelftest}
            style={{
              padding: '8px 16px',
              fontSize: '14px',
              cursor: 'pointer',
              backgroundColor: '#455A64',
              color: '#ffffff',
              border: '1px solid #546E7A',
              borderRadius: '4px'
            }}
          >
            Run Automated OCR Tests
          </button>
        )}
      </header>
      <main style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
        <div style={{
          backgroundColor: '#37474F',
          padding: '16px',
          borderRadius: '8px',
          marginBottom: '20px'
        }}>
          <FormSection onVerify={handleVerify} />
        </div>
        <div style={{
          backgroundColor: '#37474F',
          padding: '16px',
          borderRadius: '8px',
          marginBottom: '20px'
        }}>
          <ResultsPanel
            result={verificationResult}
            onFieldHover={setHoveredField}
            onFieldClick={setActiveField}
            activeField={activeField}
          />
        </div>
      </main>
      
      {/* Label Viewer with overlay */}
      {verificationResult && imageFile && (
        <LabelViewer
          imageFile={imageFile}
          verificationResult={verificationResult}
          hoveredField={hoveredField}
          activeField={activeField}
          onFieldHover={setHoveredField}
          onFieldClick={setActiveField}
          onFieldAdjust={handleFieldAdjust}
          testStatus={testStatus}
          testSummary={testSummary}
          testError={testError}
        />
      )}
    </div>
  )
}

export default App

