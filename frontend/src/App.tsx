import React, { useState } from 'react'
import FormSection from './components/FormSection'
import ResultsPanel from './components/ResultsPanel'
import { VerifyResponse } from './types/verify'

function App() {
  const [verificationResult, setVerificationResult] = useState<VerifyResponse | null>(null)

  const handleVerify = (result: VerifyResponse) => {
    setVerificationResult(result)
  }

  return (
    <div className="app" style={{ maxWidth: '1200px', margin: '0 auto', padding: '20px' }}>
      <header style={{ marginBottom: '30px' }}>
        <h1>TTB Label Verifier</h1>
      </header>
      <main style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
        <FormSection onVerify={handleVerify} />
        <ResultsPanel result={verificationResult} />
      </main>
    </div>
  )
}

export default App

