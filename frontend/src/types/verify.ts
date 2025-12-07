export interface FieldCheck {
  field: string
  form_value: any
  label_value: any
  result: 'pass' | 'fail' | 'review'
  notes?: string
}

export interface FieldBox {
  text: string | null
  boxes: number[][][]  // Array of bboxes, each bbox is [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
}

export interface VerifyResponse {
  status: 'pass' | 'fail' | 'review'
  field_checks: FieldCheck[]
  image_size?: { width: number; height: number }
  field_boxes?: {
    brand?: FieldBox
    abv?: FieldBox
    net_contents?: FieldBox
    warning?: FieldBox
  }
}

