import { describe, expect, it } from 'vitest'
import { renderMarkdown } from '../markdown'
import { formatDate, formatIndex, initials, parseDate } from '../format'
import { errorMessage } from '../errors'

describe('renderMarkdown', () => {
  it('escapes HTML the model sends', () => {
    const html = renderMarkdown('<img src=x onerror="alert(1)"> **bold**')
    expect(html).not.toContain('<img')
    expect(html).toContain('&lt;img')
    expect(html).toContain('<strong>bold</strong>')
  })

  it('renders bullet and numbered lists', () => {
    expect(renderMarkdown('- one\n- two')).toBe('<ul><li>one</li><li>two</li></ul>')
    expect(renderMarkdown('1. first\n2. second')).toBe('<ol><li>first</li><li>second</li></ol>')
  })

  it('splits paragraphs on blank lines', () => {
    expect(renderMarkdown('a\nb\n\nc')).toBe('<p>a<br>b</p><p>c</p>')
  })
})

describe('format', () => {
  it('reads a date-only string as a local calendar day', () => {
    const d = parseDate('2026-11-02')!
    expect([d.getFullYear(), d.getMonth(), d.getDate()]).toEqual([2026, 10, 2])
    expect(formatDate('2026-11-02')).toBe('Nov 2, 2026')
  })

  it('shows a dash for missing values', () => {
    expect(formatDate(null)).toBe('—')
    expect(formatIndex(null)).toBe('—')
    expect(formatIndex(1.056)).toBe('1.06')
  })

  it('makes initials from the first and last name', () => {
    expect(initials('Dana Park')).toBe('DP')
    expect(initials('David & Helena Sterling')).toBe('DS')
    expect(initials('')).toBe('?')
  })
})

describe('errorMessage', () => {
  it("uses FastAPI's detail", () => {
    expect(errorMessage({ response: { data: { detail: 'Project not found' } } })).toBe('Project not found')
    expect(errorMessage({ response: { data: { detail: [{ msg: 'field required' }] } } })).toBe('field required')
    expect(errorMessage({}, 'fallback')).toBe('fallback')
  })
})
