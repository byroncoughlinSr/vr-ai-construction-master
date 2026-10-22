// The small piece of markdown the copilot writes (bold, italics, code, bullet
// and numbered lists, paragraphs) as HTML. Everything is escaped first, so the
// result is safe for v-html whatever the model sends.

const escapeHtml = (text: string) =>
  text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;')

const inline = (text: string) =>
  text
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/(^|[^*])\*([^*\s][^*]*)\*/g, '$1<em>$2</em>')

export function renderMarkdown(source: string): string {
  const lines = escapeHtml(source.replace(/\r\n/g, '\n')).split('\n')
  const out: string[] = []
  let list: 'ul' | 'ol' | null = null
  let paragraph: string[] = []

  const flushParagraph = () => {
    if (paragraph.length) out.push(`<p>${inline(paragraph.join('<br>'))}</p>`)
    paragraph = []
  }
  const closeList = () => {
    if (list) out.push(`</${list}>`)
    list = null
  }

  for (const raw of lines) {
    const line = raw.trimEnd()
    const bullet = line.match(/^\s*(?:[-*•])\s+(.*)$/)
    const numbered = line.match(/^\s*\d+[.)]\s+(.*)$/)
    const heading = line.match(/^#{1,4}\s+(.*)$/)
    if (bullet || numbered) {
      flushParagraph()
      const kind = bullet ? 'ul' : 'ol'
      if (list !== kind) {
        closeList()
        out.push(`<${kind}>`)
        list = kind
      }
      out.push(`<li>${inline((bullet ?? numbered)![1])}</li>`)
    } else if (heading) {
      flushParagraph()
      closeList()
      out.push(`<p><strong>${inline(heading[1])}</strong></p>`)
    } else if (!line.trim()) {
      flushParagraph()
      closeList()
    } else {
      closeList()
      paragraph.push(line)
    }
  }
  flushParagraph()
  closeList()
  return out.join('')
}
