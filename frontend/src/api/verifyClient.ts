import { VerifyResponse } from '../types/verify'

export interface VerifyFormData {
  brand: string
  class_type: string
  abv: number
  net_contents: string
  warning_claimed: boolean
  image: File
}

export const verifyLabel = async (
  formData: VerifyFormData
): Promise<VerifyResponse> => {
  const data = new FormData()
  data.append('brand', formData.brand)
  data.append('class_type', formData.class_type)
  data.append('abv', formData.abv.toString())
  data.append('net_contents', formData.net_contents)
  data.append('warning_claimed', formData.warning_claimed.toString())
  data.append('image', formData.image)

  const response = await fetch('/api/verify', {
    method: 'POST',
    body: data,
  })

  if (!response.ok) {
    throw new Error('Verification request failed')
  }

  return response.json()
}

