import React from 'react'
import { VerifyResponse } from '../types/verify'

interface ResultsPanelProps {
  result: VerifyResponse | null
}

const ResultsPanel: React.FC<ResultsPanelProps> = ({ result }) => {
  if (!result) {
    return (
      <section className="results-panel">
        <h2>Verification Results</h2>
        <div className="results-content">
          <p>Submit a label to see verification results.</p>
        </div>
      </section>
    )
  }

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'pass':
        return '#4caf50'
      case 'fail':
        return '#f44336'
      case 'review':
        return '#ff9800'
      default:
        return '#666'
    }
  }

  const getResultColor = (result: string) => {
    switch (result) {
      case 'pass':
        return '#4caf50'
      case 'fail':
        return '#f44336'
      case 'review':
        return '#ff9800'
      default:
        return '#666'
    }
  }

  return (
    <section className="results-panel">
      <h2>Verification Results</h2>
      <div className="results-content">
        <div style={{ marginBottom: '20px' }}>
          <strong>Overall Status: </strong>
          <span
            style={{
              color: getStatusColor(result.status),
              fontWeight: 'bold',
              textTransform: 'uppercase',
            }}
          >
            {result.status}
          </span>
        </div>

        <h3>Field Checks</h3>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr>
              <th style={{ border: '1px solid #ddd', padding: '8px' }}>Field</th>
              <th style={{ border: '1px solid #ddd', padding: '8px' }}>Form Value</th>
              <th style={{ border: '1px solid #ddd', padding: '8px' }}>Label Value</th>
              <th style={{ border: '1px solid #ddd', padding: '8px' }}>Result</th>
              <th style={{ border: '1px solid #ddd', padding: '8px' }}>Notes</th>
            </tr>
          </thead>
          <tbody>
            {result.field_checks.map((check, index) => (
              <tr key={index}>
                <td style={{ border: '1px solid #ddd', padding: '8px' }}>
                  {check.field}
                </td>
                <td style={{ border: '1px solid #ddd', padding: '8px' }}>
                  {String(check.form_value)}
                </td>
                <td style={{ border: '1px solid #ddd', padding: '8px' }}>
                  {String(check.label_value)}
                </td>
                <td style={{ border: '1px solid #ddd', padding: '8px' }}>
                  <span
                    style={{
                      color: getResultColor(check.result),
                      fontWeight: 'bold',
                      textTransform: 'uppercase',
                    }}
                  >
                    {check.result}
                  </span>
                </td>
                <td style={{ border: '1px solid #ddd', padding: '8px' }}>
                  {check.notes || '-'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}

export default ResultsPanel

