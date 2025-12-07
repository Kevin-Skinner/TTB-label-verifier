import React from 'react'
import { VerifyResponse } from '../types/verify'

interface ResultsPanelProps {
  result: VerifyResponse | null
  onFieldHover?: (field: string | null) => void
  onFieldClick?: (field: string) => void
  activeField?: string | null
}

const ResultsPanel: React.FC<ResultsPanelProps> = ({ result, onFieldHover, onFieldClick, activeField }) => {
  if (!result) {
    return (
      <section className="results-panel">
        <h2 style={{ color: '#ffffff', marginTop: '0', marginBottom: '20px' }}>Verification Results</h2>
        <div className="results-content">
          <p style={{ color: '#ffffff' }}>Submit a label to see verification results.</p>
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
      <h2 style={{ color: '#ffffff', marginTop: '0', marginBottom: '20px' }}>Verification Results</h2>
      <div className="results-content">
        <div style={{ marginBottom: '20px' }}>
          <strong style={{ color: '#ffffff' }}>Overall Status: </strong>
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

        <h3 style={{ color: '#ffffff', marginBottom: '12px' }}>Field Checks</h3>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr>
              <th style={{ border: '1px solid #ddd', padding: '8px', backgroundColor: '#455A64', color: '#ffffff' }}>Field</th>
              <th style={{ border: '1px solid #ddd', padding: '8px', backgroundColor: '#455A64', color: '#ffffff' }}>Form Value</th>
              <th style={{ border: '1px solid #ddd', padding: '8px', backgroundColor: '#455A64', color: '#ffffff' }}>Label Value</th>
              <th style={{ border: '1px solid #ddd', padding: '8px', backgroundColor: '#455A64', color: '#ffffff' }}>Result</th>
              <th style={{ border: '1px solid #ddd', padding: '8px', backgroundColor: '#455A64', color: '#ffffff' }}>Notes</th>
            </tr>
          </thead>
          <tbody>
            {result.field_checks.map((check, index) => {
              const isActive = activeField === check.field
              return (
              <tr
                key={index}
                data-field={check.field}
                onMouseEnter={() => onFieldHover?.(check.field)}
                onMouseLeave={() => onFieldHover?.(null)}
                onClick={() => check.field === 'brand' && onFieldClick?.(check.field)}
                style={{
                  cursor: check.field === 'brand' ? 'pointer' : 'default',
                  backgroundColor: isActive ? '#546E7A' : '#37474F',
                }}
              >
                <td style={{ border: '1px solid #ddd', padding: '8px', backgroundColor: 'inherit', color: '#ffffff' }}>
                  {check.field}
                </td>
                <td style={{ border: '1px solid #ddd', padding: '8px', backgroundColor: 'inherit', color: '#ffffff' }}>
                  {String(check.form_value)}
                </td>
                <td style={{ border: '1px solid #ddd', padding: '8px', backgroundColor: 'inherit', color: '#ffffff' }}>
                  {String(check.label_value)}
                </td>
                <td style={{ border: '1px solid #ddd', padding: '8px', backgroundColor: 'inherit', color: '#ffffff' }}>
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
                <td style={{ border: '1px solid #ddd', padding: '8px', backgroundColor: 'inherit', color: '#ffffff' }}>
                  {check.notes || '-'}
                </td>
              </tr>
            )})}
          </tbody>
        </table>
      </div>
    </section>
  )
}

export default ResultsPanel

