export interface FieldCheck {
  field: string
  form_value: any
  label_value: any
  result: 'pass' | 'fail' | 'review'
  notes?: string
}

export interface VerifyResponse {
  status: 'pass' | 'fail' | 'review'
  field_checks: FieldCheck[]
}

