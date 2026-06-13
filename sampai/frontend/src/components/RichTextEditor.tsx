import { type ReactNode } from 'react'
import { EditorContent, useEditor, type Editor } from '@tiptap/react'
import StarterKit from '@tiptap/starter-kit'
import { Bold, Italic, Link as LinkIcon, List, ListOrdered, Strikethrough, Underline as UnderlineIcon } from 'lucide-react'

/**
 * Minimal TipTap editor matching SAMpai's allowed formatting: bold, italic,
 * underline, strikethrough, bullet/ordered lists, links (auto-https). Headings,
 * code and blockquote are disabled here; the server (nh3) is the real guard.
 */
export default function RichTextEditor({
  onChange,
  resetSignal = 0,
}: {
  onChange: (html: string) => void
  resetSignal?: number
}) {
  const editor = useEditor(
    {
      extensions: [
        StarterKit.configure({
          heading: false,
          codeBlock: false,
          blockquote: false,
          code: false,
          horizontalRule: false,
          link: { openOnClick: false, autolink: true, defaultProtocol: 'https' },
        }),
      ],
      content: '',
      onUpdate: ({ editor }) => onChange(editor.getHTML()),
      editorProps: {
        attributes: {
          class:
            'prose prose-invert prose-sm max-w-none min-h-[110px] max-h-72 overflow-y-auto rounded-b-lg bg-neutral-950/60 px-3 py-2 text-sm text-neutral-100 outline-none prose-p:my-1',
        },
      },
    },
    [resetSignal], // remounting the editor (new key) is how the parent clears it
  )

  if (!editor) return null

  return (
    <div className="rounded-lg border border-neutral-700 focus-within:border-violet-500">
      <Toolbar editor={editor} />
      <EditorContent editor={editor} />
    </div>
  )
}

function Toolbar({ editor }: { editor: Editor }) {
  function addLink() {
    const prev = editor.getAttributes('link').href as string | undefined
    const url = window.prompt('Link URL', prev ?? 'https://')
    if (url === null) return
    if (url === '') {
      editor.chain().focus().unsetLink().run()
      return
    }
    editor.chain().focus().extendMarkRange('link').setLink({ href: url }).run()
  }

  const Btn = ({
    on,
    active,
    title,
    children,
  }: {
    on: () => void
    active?: boolean
    title: string
    children: ReactNode
  }) => (
    <button
      type="button"
      title={title}
      onMouseDown={(e) => {
        e.preventDefault()
        on()
      }}
      className={`flex h-7 w-7 items-center justify-center rounded transition ${
        active ? 'bg-violet-600/30 text-violet-200' : 'text-neutral-400 hover:bg-neutral-800 hover:text-neutral-200'
      }`}
    >
      {children}
    </button>
  )

  return (
    <div className="flex flex-wrap items-center gap-0.5 border-b border-neutral-800 bg-neutral-900/60 px-2 py-1.5">
      <Btn on={() => editor.chain().focus().toggleBold().run()} active={editor.isActive('bold')} title="Bold">
        <Bold className="h-3.5 w-3.5" />
      </Btn>
      <Btn on={() => editor.chain().focus().toggleItalic().run()} active={editor.isActive('italic')} title="Italic">
        <Italic className="h-3.5 w-3.5" />
      </Btn>
      <Btn on={() => editor.chain().focus().toggleUnderline().run()} active={editor.isActive('underline')} title="Underline">
        <UnderlineIcon className="h-3.5 w-3.5" />
      </Btn>
      <Btn on={() => editor.chain().focus().toggleStrike().run()} active={editor.isActive('strike')} title="Strikethrough">
        <Strikethrough className="h-3.5 w-3.5" />
      </Btn>
      <span className="mx-1 h-4 w-px bg-neutral-700" />
      <Btn on={() => editor.chain().focus().toggleBulletList().run()} active={editor.isActive('bulletList')} title="Bullet list">
        <List className="h-3.5 w-3.5" />
      </Btn>
      <Btn on={() => editor.chain().focus().toggleOrderedList().run()} active={editor.isActive('orderedList')} title="Numbered list">
        <ListOrdered className="h-3.5 w-3.5" />
      </Btn>
      <span className="mx-1 h-4 w-px bg-neutral-700" />
      <Btn on={addLink} active={editor.isActive('link')} title="Link">
        <LinkIcon className="h-3.5 w-3.5" />
      </Btn>
    </div>
  )
}
